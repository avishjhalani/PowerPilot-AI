import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
import re
import uuid
import tempfile
from typing import Dict, Any, List
from groq import Groq

from backend.src.config import (
    GROQ_API_KEY,
    DEFAULT_GROQ_MODEL,
    MAX_SELF_HEALING_RETRIES,
    MAX_SAMPLE_ROWS_FOR_LLM,
    MAX_SAMPLE_CHARS_FOR_LLM,
    CLEANED_DATA_DIR
)
from backend.src.tools.streaming_executor import StreamingExecutor

class CleanerAgent:
    def __init__(self):
        self.executor = StreamingExecutor()
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = DEFAULT_GROQ_MODEL

    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1
        )
        return response.choices[0].message.content

    def _clean_json_response(self, text: str) -> Dict[str, Any]:
        """Safely parses JSON even if wrapped in markdown code blocks."""
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return json.loads(cleaned)

    @staticmethod
    def _get_adaptive_sample_records(
        sample_records: List[Dict[str, Any]],
        max_chars: int = MAX_SAMPLE_CHARS_FOR_LLM,
        min_rows: int = 3,
        max_rows: int = MAX_SAMPLE_ROWS_FOR_LLM
    ) -> tuple[str, int]:
        """
        Dynamically packs as many sample rows as possible into the prompt
        without exceeding the character/token budget:
        - Narrow datasets (5-8 cols) get up to 15 sample rows.
        - Wide datasets (25+ cols) safely scale down to 3-5 rows to prevent 413 TPM limits.
        """
        if not sample_records:
            return "[]", 0
        total_available = min(max_rows, len(sample_records))
        for n in range(total_available, min_rows - 1, -1):
            chunk = json.dumps(sample_records[:n], indent=1, default=str)
            if len(chunk) <= max_chars or n == min_rows:
                return chunk, n
        return json.dumps(sample_records[:min_rows], indent=1, default=str), min_rows

    def _build_heuristic_recipe(self, profile: Dict[str, Any], input_csv_str: str, output_parquet_str: str, user_intent: str = None) -> tuple[str, List[str]]:
        """Constructs a deterministic, high-speed Polars 1.0+ streaming pipeline."""
        transforms = []
        changelog = []

        for col in profile["columns"]:
            c_name = col["name"]
            c_type = col.get("inferred_type", "VARCHAR")
            issues = col.get("detected_issues", [])

            if "date" in c_name.lower():
                transforms.append(
                    f"pl.coalesce([\n"
                    f"        pl.col('{c_name}').cast(pl.String, strict=False).str.to_date('%Y-%m-%d', strict=False),\n"
                    f"        pl.col('{c_name}').cast(pl.String, strict=False).str.to_date('%d-%m-%Y', strict=False),\n"
                    f"        pl.col('{c_name}').cast(pl.String, strict=False).str.to_date('%d/%m/%Y', strict=False),\n"
                    f"        pl.col('{c_name}').cast(pl.String, strict=False).str.to_date('%m/%d/%Y', strict=False),\n"
                    f"        pl.col('{c_name}').cast(pl.String, strict=False).str.to_date('%m-%d-%Y', strict=False)\n"
                    f"    ]).alias('{c_name}')"
                )
                changelog.append(f"Parsed multi-format dates in '{c_name}' into ISO Date")
            elif "CONTAINS_CURRENCY_SYMBOLS" in issues or any(k in c_name.lower() for k in ["revenue", "price", "amount", "sales", "cost", "total"]):
                transforms.append(
                    f"pl.col('{c_name}').cast(pl.String, strict=False).str.replace_all(r'[\\$,]', '').str.strip_chars().cast(pl.Float64, strict=False)"
                )
                changelog.append(f"Stripped currency symbols and cast '{c_name}' to Float64")
            elif c_name.lower() in ["qty", "quantity"] or c_name.lower().endswith("_qty") or c_name.lower().endswith("count") or c_type in ["BIGINT", "INTEGER"]:
                transforms.append(
                    f"pl.col('{c_name}').cast(pl.String, strict=False).str.strip_chars().cast(pl.Int64, strict=False).abs()"
                )
                changelog.append(f"Sanitized negative values and cast '{c_name}' to positive Int64")
            elif c_type == "VARCHAR":
                if "name" in c_name.lower() or "category" in c_name.lower():
                    transforms.append(f"pl.col('{c_name}').cast(pl.String, strict=False).str.strip_chars().str.to_titlecase()")
                    changelog.append(f"Trimmed whitespace and capitalized '{c_name}'")
                elif "region" in c_name.lower() or "country" in c_name.lower():
                    transforms.append(f"pl.col('{c_name}').cast(pl.String, strict=False).str.strip_chars().str.to_uppercase()")
                    changelog.append(f"Trimmed and normalized '{c_name}' to uppercase")
                else:
                    transforms.append(f"pl.col('{c_name}').cast(pl.String, strict=False).str.strip_chars()")

        col_exprs = ",\n        ".join(transforms)
        id_cols = [c["name"] for c in profile["columns"] if "id" in c["name"].lower()]
        dedup = f"query = query.unique(subset=['{id_cols[0]}'])" if id_cols else ""
        if dedup:
            changelog.append(f"Deduplicated repeated record identifiers on '{id_cols[0]}'")

        # Filter out obvious rogue anomalies (e.g. dates outside Q4 for Q4 datasets or flagged data issues)
        filters = []
        issue_cols = [c["name"] for c in profile["columns"] if c["name"].lower() in ["data issue", "data_issue", "issue", "data_error"]]
        if issue_cols:
            filters.append(f"pl.col('{issue_cols[0]}').cast(pl.String, strict=False).str.to_lowercase().str.contains('outside q4|date outside|corrupt').not_()")
            changelog.append(f"Filtered out rogue records flagged in '{issue_cols[0]}'")

        date_cols = [c["name"] for c in profile["columns"] if "date" in c["name"].lower()]
        if ("q4" in input_csv_str.lower() or (user_intent and "q4" in user_intent.lower())) and date_cols:
            filters.append(f"((pl.col('{date_cols[0]}').dt.month() >= 10) & (pl.col('{date_cols[0]}').dt.month() <= 12))")
            changelog.append(f"Filtered '{date_cols[0]}' strictly to Quarter 4 (Oct-Dec) removing outlier dates")

        filter_lines = ("\n" + "\n".join(f"query = query.filter({flt})" for flt in filters)) if filters else ""

        code = f"""import polars as pl

query = (
    pl.scan_csv(r'{input_csv_str}', ignore_errors=True)
    .with_columns([
        {col_exprs}
    ])
)
{dedup}{filter_lines}
query.sink_parquet(r'{output_parquet_str}')
"""
        return code, changelog

    def clean_dataset(self, profile: Dict[str, Any], output_name: str = "cleaned_data.parquet", user_intent: str = None) -> Dict[str, Any]:
        input_csv = profile["file_path"]
        raw_rows = profile["total_rows"]
        output_parquet = CLEANED_DATA_DIR / output_name
        temp_script_path = Path(tempfile.gettempdir()) / f"_temp_cleaner_{uuid.uuid4().hex[:8]}.py"

        input_csv_str = str(input_csv).replace("\\", "/")
        output_parquet_str = str(output_parquet).replace("\\", "/")

        compact_columns = [
            {
                "name": c["name"],
                "type": c.get("inferred_type", "VARCHAR"),
                "issues": c.get("detected_issues", [])
            }
            for c in profile.get("columns", [])
        ]
        columns_json = json.dumps(compact_columns, default=str)
        sample_records_json, sample_row_count = self._get_adaptive_sample_records(profile.get("sample_records", []))
        print(f"📊 [Adaptive Token Budget] Selected {sample_row_count} sample rows ({len(sample_records_json):,} chars) for LLM context.")

        system_instruction = (
            "You are a Principal Data Engineer. You respond ONLY with a raw, valid JSON object containing keys 'changelog' and 'code'. "
            "Write modern Polars 1.0+ code: use `.cast(pl.String, strict=False).str.strip_chars()`, `pl.scan_csv(r'...', ignore_errors=True)`, and `.sink_parquet(r'...')`."
        )

        id_cols = [c["name"] for c in profile.get("columns", []) if "id" in c["name"].lower()]
        id_col_example = id_cols[0] if id_cols else "order_id"

        user_scope_text = f"\nUSER CLEANING REQUIREMENTS & DOMAIN SCOPE:\n\"{user_intent}\"\n" if user_intent and user_intent.strip() else ""

        initial_prompt = f"""
Given a dirty dataset of {raw_rows:,} rows at: "{input_csv_str}"

Columns & Profiling Metadata:
{columns_json}

Sample records (sample rows):
{sample_records_json}
{user_scope_text}
Write an out-of-core streaming Polars 1.0+ cleaning pipeline.
Return a JSON object with EXACTLY this structure:
{{
  "changelog": [
    "Stripped currency symbols ($) and converted revenue to Float64",
    "Standardized customer names and regions using .cast(pl.String, strict=False).str.strip_chars().str.to_titlecase()",
    "Parsed order_date into ISO Date format with strict=False",
    "Deduplicated repeated record identifiers"
  ],
  "code": "import polars as pl\\n\\nquery = (\\n    pl.scan_csv(r'{input_csv_str}', ignore_errors=True)\\n    .with_columns([\\n        pl.col('revenue').cast(pl.String, strict=False).str.replace_all(r'[\\\\$,]', '').str.strip_chars().cast(pl.Float64, strict=False),\\n        pl.col('quantity').cast(pl.String, strict=False).str.strip_chars().cast(pl.Int64, strict=False).abs(),\\n        pl.col('customer_name').cast(pl.String, strict=False).str.strip_chars().str.to_titlecase(),\\n        pl.col('region').cast(pl.String, strict=False).str.strip_chars().str.to_uppercase(),\\n        pl.col('category').cast(pl.String, strict=False).str.strip_chars().str.to_titlecase(),\\n        pl.coalesce([\\n            pl.col('order_date').cast(pl.String, strict=False).str.to_date('%Y-%m-%d', strict=False),\\n            pl.col('order_date').cast(pl.String, strict=False).str.to_date('%d-%m-%Y', strict=False),\\n            pl.col('order_date').cast(pl.String, strict=False).str.to_date('%d/%m/%Y', strict=False),\\n            pl.col('order_date').cast(pl.String, strict=False).str.to_date('%m/%d/%Y', strict=False),\\n            pl.col('order_date').cast(pl.String, strict=False).str.to_date('%m-%d-%Y', strict=False)\\n        ]).alias('order_date')\\n    ])\\n    .unique(subset=['{id_col_example}'])\\n)\\nquery.sink_parquet(r'{output_parquet_str}')"
}}

STRICT RULES:
1. Input path MUST BE EXACTLY: r'{input_csv_str}'
2. Output path MUST BE EXACTLY: r'{output_parquet_str}'
3. ONLY import 'polars' and standard safe modules ('datetime', 're').
4. Do NOT pass 'dtype' or 'dtypes' to pl.scan_csv(). Just use: pl.scan_csv(r'{input_csv_str}', ignore_errors=True)
5. CRITICAL TYPE SAFETY: Polars scan_csv will infer clean numeric columns as i64 or f64. Calling `.str` directly on numeric columns causes 'expected String type, got: i64'. Therefore, ALWAYS use `.cast(pl.String, strict=False)` before any `.str` operation!
   - Numbers with currency ($), commas, or dirty text:
     pl.col('col_name').cast(pl.String, strict=False).str.replace_all(r'[\\$,]', '').str.strip_chars().cast(pl.Float64, strict=False)
   - Integer / count columns:
     pl.col('col_name').cast(pl.String, strict=False).str.strip_chars().cast(pl.Int64, strict=False).abs()
   - String whitespace / casing:
     pl.col('col_name').cast(pl.String, strict=False).str.strip_chars().str.to_titlecase()
   - Multi-format dates:
     pl.coalesce([
         pl.col("col_name").cast(pl.String, strict=False).str.to_date("%Y-%m-%d", strict=False),
         pl.col("col_name").cast(pl.String, strict=False).str.to_date("%d-%m-%Y", strict=False),
         pl.col("col_name").cast(pl.String, strict=False).str.to_date("%d/%m/%Y", strict=False),
         pl.col("col_name").cast(pl.String, strict=False).str.to_date("%m/%d/%Y", strict=False),
         pl.col("col_name").cast(pl.String, strict=False).str.to_date("%m-%d-%Y", strict=False)
     ]).alias("col_name")
6. Use the EXACT column names and casing from the provided metadata (e.g. '{id_col_example}').
7. End with: `query.sink_parquet(r'{output_parquet_str}')`. NEVER call `.collect()`.
8. NEVER USE `.cast(pl.Date)` on string date columns! In Polars, `.cast(pl.Date)` on non-ISO strings like '02-10-2024' silently nullifies them into null! ALWAYS use `pl.coalesce` with `str.to_date` patterns ('%d-%m-%Y', '%Y-%m-%d', etc.).
9. DOMAIN & TEMPORAL INTEGRITY:
   - If the dataset or user intent refers to Q4 (Quarter 4), filter dates strictly to Oct 1 - Dec 31 (months 10 to 12) or drop records flagged with 'Date Outside Q4'.
   - Always sanitize negative quantities: use `.abs()` on quantity columns.
   - If an issue/audit column exists (e.g. 'Data Issue'), filter out corrupt or out-of-scope rows.
"""

        attempt = 0
        error_context = ""

        while attempt < MAX_SELF_HEALING_RETRIES:
            attempt += 1
            print(f"[Attempt {attempt}/{MAX_SELF_HEALING_RETRIES}] GENERATING POLARS STREAMING CODE & CHANGELOG...")

            if attempt > 1:
                prompt_content = (
                    f"{initial_prompt}\n\n"
                    f"CRITICAL FIX NEEDED: Your previous attempt failed with error:\n"
                    f"{error_context}\n"
                    f"Please correct the error, follow the rules, and return ONLY a valid JSON object."
                )
            else:
                prompt_content = initial_prompt

            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt_content}
            ]

            raw_response = ""
            try:
                raw_response = self._call_llm(messages)
                parsed = self._clean_json_response(raw_response)
                code = parsed["code"]
                changelog = parsed.get("changelog", [])
            except Exception as parse_err:
                error_context = f"Failed to parse JSON response: {parse_err}. Make sure to return valid JSON."
                print(f"⚠️ JSON Parse Error on attempt {attempt}: {parse_err}")
                continue

            print(f"🛡️ Validating code AST safety & executing stream...")
            exec_result = self.executor.execute_script(code, temp_script_path, output_parquet, raw_row_count=raw_rows)

            if exec_result["success"]:
                print(f"🎉 Pipeline succeeded!")
                print(f"⏱️ Time: {exec_result['execution_time_seconds']}s | Peak RAM: {exec_result['peak_memory_mb']} MB")
                print(f"📊 Cleaned Rows Retained: {exec_result['cleaned_rows']:,} ({exec_result['retention_percentage']}%)")

                if temp_script_path.exists():
                    temp_script_path.unlink()

                return {
                    "success": True,
                    "output_parquet": str(output_parquet),
                    "execution_time_seconds": exec_result["execution_time_seconds"],
                    "peak_memory_mb": exec_result["peak_memory_mb"],
                    "file_size_mb": exec_result["file_size_mb"],
                    "cleaned_rows": exec_result["cleaned_rows"],
                    "total_raw_rows": raw_rows,
                    "retention_percentage": exec_result["retention_percentage"],
                    "cleaning_code": code,
                    "changelog": changelog,
                    "attempts_needed": attempt
                }
            else:
                print(f"\n❌ ATTEMPT {attempt} FAILED WITH ERROR:")
                print(exec_result['error_message'])
                print("=" * 60 + "\n")
                error_context = exec_result["error_message"]

        # Deterministic Fallback Engine
        print("⚠️ LLM retries exhausted. Activating high-speed deterministic Polars fallback engine...")
        fallback_code, fallback_changelog = self._build_heuristic_recipe(profile, input_csv_str, output_parquet_str, user_intent=user_intent)
        fallback_exec = self.executor.execute_script(fallback_code, temp_script_path, output_parquet, raw_row_count=raw_rows)

        if temp_script_path.exists():
            temp_script_path.unlink()

        if fallback_exec["success"]:
            print(f"✅ Fallback engine succeeded in {fallback_exec['execution_time_seconds']}s!")
            return {
                "success": True,
                "output_parquet": str(output_parquet),
                "execution_time_seconds": fallback_exec["execution_time_seconds"],
                "peak_memory_mb": fallback_exec["peak_memory_mb"],
                "file_size_mb": fallback_exec["file_size_mb"],
                "cleaned_rows": fallback_exec["cleaned_rows"],
                "total_raw_rows": raw_rows,
                "retention_percentage": fallback_exec["retention_percentage"],
                "cleaning_code": fallback_code,
                "changelog": fallback_changelog,
                "attempts_needed": attempt + 1
            }

        return {
            "success": False,
            "error_message": f"Failed after {MAX_SELF_HEALING_RETRIES} attempts and fallback: {fallback_exec.get('error_message')}"
        }

if __name__ == "__main__":
    from backend.src.tools.streaming_profiler import StreamingProfiler
    profiler = StreamingProfiler(sample_size=5)
    print("1. Profiling dirty data...")
    profile = profiler.profile_file("data/raw/messy_sales_500k.csv")
    print("\n2. Initializing Production Cleaner Agent...")
    agent = CleanerAgent()
    result = agent.clean_dataset(profile, output_name="sales_cleaned_500k.parquet")
    if result["success"]:
        print("\n" + "="*50)
        print("✅ PRODUCTION STREAMING CLEANING SUCCESSFUL!")
        print(f"📁 Output Parquet: {result['output_parquet']} ({result['file_size_mb']} MB)")
        print(f"💾 Peak RAM: {result['peak_memory_mb']} MB")
        print(f"📝 Transformation Changelog:")
        for item in result["changelog"]:
            print(f"   • {item}")
        print("="*50)
    else:
        print("\n❌ Failed:", result["error_message"])
