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

import time
import json
import re
import duckdb
from typing import Dict, Any, List, Optional
from groq import Groq

from backend.src.config import GROQ_API_KEY, DEFAULT_GROQ_MODEL
from backend.src.powerbi.tmdl_builder import TMDLBuilder

# Power BI / DAX reserved keywords that cause parser errors or collisions when used as measure names
DAX_RESERVED_KEYWORDS = {
    "TOTAL", "VALUE", "DATE", "YEAR", "MONTH", "DAY", "TIME", "CURRENT",
    "TABLE", "FILTER", "ALL", "ALLEXCEPT", "ROW", "MEASURE", "BLANK",
    "TRUE", "FALSE", "IN", "ORDER", "RANK", "CALCULATE", "CALCULATETABLE",
    "COUNT", "SUM", "AVERAGE", "MIN", "MAX", "DISTINCT", "VALUES",
    "DIVIDE", "VAR", "RETURN", "IF", "SWITCH", "AND", "OR", "NOT",
    "USERELATIONSHIP", "CROSSFILTER", "EARLIER", "EARLIEST", "FORMAT",
    "ISBLANK", "SELECTEDVALUE", "HASONEVALUE", "RELATED", "RELATEDTABLE"
}

class ModelerAgent:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = DEFAULT_GROQ_MODEL
        self.tmdl_builder = TMDLBuilder()

    def _sanitize_measure_name(self, name: str, col_names: set, seen_names: set) -> str:
        """
        Sanitizes measure names:
        - Prevents Power BI reserved keyword collisions (e.g. 'Total', 'Value', 'Date', 'Current').
        - Prevents collisions with existing table column names.
        - Ensures uniqueness across all measures (case-insensitive).
        """
        clean_name = (name or "Metric").strip()
        upper_name = clean_name.upper()

        # 1. Resolve DAX / Power BI reserved keyword clash
        if upper_name in DAX_RESERVED_KEYWORDS:
            if upper_name == "TOTAL":
                clean_name = "Total Amount"
            elif upper_name == "VALUE":
                clean_name = "Metric Value"
            elif upper_name == "DATE":
                clean_name = "Selected Date"
            elif upper_name == "CURRENT":
                clean_name = "Current Value"
            elif upper_name == "COUNT":
                clean_name = "Record Count"
            elif upper_name == "ORDER":
                clean_name = "Order Count"
            elif upper_name == "RANK":
                clean_name = "Rank Score"
            else:
                clean_name = f"{clean_name.title()} Metric"

        # 2. Resolve collision with existing column name in the table
        if clean_name.lower() in col_names:
            clean_name = f"{clean_name} Metric"

        # 3. Ensure uniqueness among measures
        base_name = clean_name
        counter = 2
        while clean_name.lower() in seen_names or clean_name.lower() in col_names:
            clean_name = f"{base_name} ({counter})"
            counter += 1

        return clean_name

    def _call_llm(self, prompt: str) -> str:
        """
        Calls Groq with exponential backoff on 429 rate limit errors
        and multi-model fallback to keep pipeline running reliably.
        """
        models_to_try = [self.model, "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        last_error = None

        for model_candidate in models_to_try:
            for attempt in range(2):
                try:
                    response = self.client.chat.completions.create(
                        model=model_candidate,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are a Principal Power BI Architect & DAX Expert. "
                                    "You respond ONLY with a raw, valid JSON object without conversational text or markdown blocks."
                                )
                            },
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1
                    )
                    content = response.choices[0].message.content
                    if content and content.strip():
                        return content
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    if "429" in err_str or "rate limit" in err_str:
                        wait_sec = 3.5 * (attempt + 1)
                        print(f"⚠️ Groq rate limit on {model_candidate}. Backing off {wait_sec:.1f}s...")
                        time.sleep(wait_sec)
                    else:
                        break  # Try alternative model if non-rate-limit error

        raise last_error or RuntimeError("All LLM attempts failed")

    def _clean_json_response(self, text: str) -> Dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return json.loads(cleaned)

    def _generate_deterministic_blueprint(
        self,
        table_name: str,
        schema_summary: List[Dict[str, Any]],
        user_intent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Schema-aware deterministic blueprint generator.
        Distinguishes between transactional/numeric datasets vs categorical/directory datasets.
        NEVER invents fictitious columns like 'value'.
        """
        col_types = {c["column"]: c["data_type"].upper() for c in schema_summary}
        all_cols = [c["column"] for c in schema_summary]

        id_keywords = ["id", "key", "guid", "uuid", "pk", "fk"]
        code_keywords = ["zip", "postal", "code", "phone", "prefix", "ssn", "number", "num"]

        # Date columns
        date_cols = [
            c for c in all_cols 
            if any(t in col_types[c] for t in ["DATE", "TIME", "TIMESTAMP"]) 
            or any(k in c.lower() for k in ["date", "timestamp"])
        ]

        # Additive numeric metrics (Float, Double, Decimal, and non-ID integers)
        num_raw = [
            c for c in all_cols 
            if any(t in col_types[c] for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL", "HUGEINT"])
        ]
        additive_metrics = [
            c for c in num_raw 
            if not any(k in c.lower() for k in id_keywords)
            and not any(k in c.lower() for k in code_keywords)
            and not any(k in c.lower() for k in ["year", "month", "day"])
        ]

        # Categorical columns
        cat_raw = [
            c for c in all_cols 
            if any(t in col_types[c] for t in ["VARCHAR", "TEXT", "STRING"])
        ]
        grouping_dims = [
            c for c in cat_raw
            if not any(k in c.lower() for k in id_keywords)
            and not any(k in c.lower() for k in code_keywords)
        ]
        if not grouping_dims:
            grouping_dims = cat_raw if cat_raw else all_cols

        # Identifier columns
        id_cols = [c for c in all_cols if any(k in c.lower() for k in id_keywords)]

        # Preferred business keywords
        preferred_val = ["revenue", "sales", "amount", "price", "total", "spend", "cost", "profit", "margin", "balance", "salary"]
        preferred_qty = ["quantity", "qty", "units", "volume", "count", "items", "score", "weight"]
        preferred_dims = ["state", "region", "city", "category", "type", "segment", "status", "country", "department", "channel"]

        # -------------------------------------------------------------
        # BRANCH A: Genuine Additive Numeric Metrics Exist
        # -------------------------------------------------------------
        if additive_metrics:
            val_col = None
            for p in preferred_val:
                for c in additive_metrics:
                    if p in c.lower():
                        val_col = c
                        break
                if val_col:
                    break
            if not val_col:
                val_col = additive_metrics[0]

            rem_metrics = [c for c in additive_metrics if c != val_col]
            qty_col = None
            for p in preferred_qty:
                for c in rem_metrics:
                    if p in c.lower():
                        qty_col = c
                        break
                if qty_col:
                    break
            if not qty_col and rem_metrics:
                qty_col = rem_metrics[0]

            dim1 = None
            for p in preferred_dims:
                for c in grouping_dims:
                    if p in c.lower():
                        dim1 = c
                        break
                if dim1:
                    break
            if not dim1:
                dim1 = grouping_dims[0] if grouping_dims else all_cols[0]

            rem_dims = [c for c in grouping_dims if c != dim1]
            dim2 = None
            for p in preferred_dims:
                for c in rem_dims:
                    if p in c.lower():
                        dim2 = c
                        break
                if dim2:
                    break
            if not dim2:
                dim2 = rem_dims[0] if rem_dims else dim1

            val_title = val_col.replace("_", " ").title()
            val_fmt = "$#,##0.00" if any(k in val_col.lower() for k in ["revenue", "sales", "amount", "price", "profit", "cost"]) else "#,##0.00"

            measures = [
                {
                    "name": f"Total {val_title}",
                    "dax": f"SUM('{table_name}'[{val_col}])",
                    "format": val_fmt,
                    "description": f"Total aggregate of {val_title}."
                }
            ]
            if qty_col:
                qty_title = qty_col.replace("_", " ").title()
                measures.append({
                    "name": f"Total {qty_title}",
                    "dax": f"SUM('{table_name}'[{qty_col}])",
                    "format": "#,##0",
                    "description": f"Total aggregate of {qty_title}."
                })
            measures.append({
                "name": "Total Records",
                "dax": f"COUNTROWS('{table_name}')",
                "format": "#,##0",
                "description": "Total record count."
            })
            measures.append({
                "name": f"Average {val_title}",
                "dax": f"AVERAGE('{table_name}'[{val_col}])",
                "format": val_fmt,
                "description": f"Average {val_title} per transaction."
            })

            sec_kpi = f"Total {qty_col.replace('_', ' ').title()}" if qty_col else "Total Records"
            visuals = [
                {"type": "card", "title": f"Total {val_title}", "measure": f"Total {val_title}"},
                {"type": "card", "title": sec_kpi, "measure": sec_kpi},
                {"type": "card", "title": f"Average {val_title}", "measure": f"Average {val_title}"},
                {"type": "card", "title": "Total Records", "measure": "Total Records"},
                {"type": "bar_chart", "title": f"{val_title} by {dim1.replace('_', ' ').title()}", "dimension": dim1, "measure": f"Total {val_title}"},
                {"type": "donut_chart", "title": f"{val_title} by {dim2.replace('_', ' ').title()}", "dimension": dim2, "measure": f"Total {val_title}"}
            ]
            if date_cols:
                visuals.append({
                    "type": "line_chart", "title": f"{val_title} Trend", "dimension": date_cols[0], "measure": f"Total {val_title}"
                })

            domain = f"{val_title} Performance Dashboard"

        # -------------------------------------------------------------
        # BRANCH B: Categorical / Directory Datasets (Zero Numeric Columns)
        # -------------------------------------------------------------
        else:
            prim_id = id_cols[0] if id_cols else all_cols[0]
            sec_id = id_cols[1] if len(id_cols) > 1 else None

            dim1 = None
            for p in preferred_dims:
                for c in grouping_dims:
                    if p in c.lower():
                        dim1 = c
                        break
                if dim1:
                    break
            if not dim1:
                dim1 = grouping_dims[0] if grouping_dims else all_cols[0]

            rem_dims = [c for c in grouping_dims if c != dim1]
            dim2 = None
            for p in preferred_dims:
                for c in rem_dims:
                    if p in c.lower():
                        dim2 = c
                        break
                if dim2:
                    break
            if not dim2:
                dim2 = rem_dims[0] if rem_dims else dim1

            prim_id_title = prim_id.replace("_", " ").title()
            dim1_title = dim1.replace("_", " ").title()
            dim2_title = dim2.replace("_", " ").title()

            measures = [
                {
                    "name": "Total Records",
                    "dax": f"COUNTROWS('{table_name}')",
                    "format": "#,##0",
                    "description": "Total record count."
                },
                {
                    "name": f"Unique {prim_id_title}",
                    "dax": f"DISTINCTCOUNT('{table_name}'[{prim_id}])",
                    "format": "#,##0",
                    "description": f"Distinct count of {prim_id_title}."
                }
            ]
            if sec_id:
                sec_id_title = sec_id.replace("_", " ").title()
                measures.append({
                    "name": f"Unique {sec_id_title}",
                    "dax": f"DISTINCTCOUNT('{table_name}'[{sec_id}])",
                    "format": "#,##0",
                    "description": f"Distinct count of {sec_id_title}."
                })
            measures.append({
                "name": f"Total {dim1_title} Count",
                "dax": f"DISTINCTCOUNT('{table_name}'[{dim1}])",
                "format": "#,##0",
                "description": f"Distinct count of {dim1_title}."
            })
            measures.append({
                "name": "% of Total Records",
                "dax": f"DIVIDE(COUNTROWS('{table_name}'), CALCULATE(COUNTROWS('{table_name}'), ALL('{table_name}')), 0)",
                "format": "0.0%",
                "description": "Percentage of total records."
            })

            visuals = [
                {"type": "card", "title": "Total Records", "measure": "Total Records"},
                {"type": "card", "title": f"Unique {prim_id_title}", "measure": f"Unique {prim_id_title}"},
                {"type": "card", "title": f"Total {dim1_title}", "measure": f"Total {dim1_title} Count"},
                {"type": "bar_chart", "title": f"Records by {dim1_title}", "dimension": dim1, "measure": "Total Records"},
                {"type": "donut_chart", "title": f"Records by {dim2_title}", "dimension": dim2, "measure": "Total Records"},
                {"type": "column_chart", "title": f"Unique {prim_id_title} by {dim1_title}", "dimension": dim1, "measure": f"Unique {prim_id_title}"}
            ]
            domain = f"{dim1_title} & {prim_id_title} Executive Overview"

        return {
            "business_domain": domain,
            "table_name": table_name,
            "user_request_fulfilled": user_intent or "Automated Executive Metrics",
            "dimensions": [
                {"column": dim1, "description": "Primary breakdown dimension"},
                {"column": dim2, "description": "Secondary category dimension"}
            ],
            "dax_measures": measures,
            "visual_blueprints": visuals
        }

    def _validate_and_heal_blueprint(
        self,
        blueprint: Dict[str, Any],
        schema_summary: List[Dict[str, Any]],
        table_name: str
    ) -> Dict[str, Any]:
        """
        Universal Validator & Self-Healing Engine:
        1. Sanitizes measure names against Power BI reserved keywords & column names.
        2. Validates that every column referenced in DAX exists in the schema.
        3. Prevents calling SUM or AVERAGE on String/VARCHAR columns (auto-converts to DISTINCTCOUNT).
        4. Synchronizes visual blueprints to use the sanitized measure & valid dimension names.
        """
        col_names = {c["column"].lower(): c["column"] for c in schema_summary}
        col_types = {c["column"].lower(): c["data_type"].upper() for c in schema_summary}
        existing_cols_lower = set(col_names.keys())

        # Determine real additive numeric columns if needed for healing
        id_keywords = ["id", "key", "guid", "uuid", "pk", "code", "zip", "prefix"]
        real_numeric_cols = [
            col_names[c_low] for c_low, t in col_types.items()
            if any(nt in t for nt in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL"])
            and not any(k in c_low for k in id_keywords)
        ]

        seen_measure_names = set()
        rename_map = {}
        validated_measures = []

        for m in blueprint.get("dax_measures", []):
            orig_name = (m.get("name") or "Metric").strip()
            clean_name = self._sanitize_measure_name(orig_name, existing_cols_lower, seen_measure_names)
            seen_measure_names.add(clean_name.lower())
            if clean_name.lower() != orig_name.lower():
                rename_map[orig_name.lower()] = clean_name
            m["name"] = clean_name

            raw_dax = (m.get("dax") or "").strip()

            # Inspect and heal column references in DAX: 'table'[col] or table[col] or [col]
            def heal_col_ref(match):
                col = match.group(1)
                col_low = col.lower()

                # If column exists, enforce exact casing
                if col_low in existing_cols_lower:
                    real_col = col_names[col_low]
                    return f"'{table_name}'[{real_col}]"

                # Fuzzy match if typo occurred
                for ec_low, ec_real in col_names.items():
                    if ec_low in col_low or col_low in ec_low:
                        return f"'{table_name}'[{ec_real}]"

                # Column does NOT exist! Heal to a real column if numeric, or first column fallback
                if real_numeric_cols:
                    return f"'{table_name}'[{real_numeric_cols[0]}]"
                return f"'{table_name}'[{list(col_names.values())[0]}]"

            # Replace invalid/hallucinated column references
            healed_dax = re.sub(
                rf"(?:'?(?:{re.escape(table_name)})'?)?\[([^\]]+)\]",
                heal_col_ref,
                raw_dax,
                flags=re.IGNORECASE
            )

            # Prevent SUM or AVERAGE on String/VARCHAR columns
            for c_low, c_real in col_names.items():
                if any(st in col_types[c_low] for st in ["VARCHAR", "TEXT", "STRING"]):
                    pattern = rf"\b(SUM|AVERAGE)\s*\(\s*'?{re.escape(table_name)}'?\[{re.escape(c_real)}\]\s*\)"
                    if re.search(pattern, healed_dax, flags=re.IGNORECASE):
                        healed_dax = re.sub(
                            pattern,
                            f"DISTINCTCOUNT('{table_name}'[{c_real}])",
                            healed_dax,
                            flags=re.IGNORECASE
                        )
                        m["format"] = "#,##0"

            # Format and sanitize time intelligence & variables using TMDLBuilder
            clean_dax = self.tmdl_builder._clean_and_format_dax(healed_dax, m_name=clean_name)
            m["dax"] = clean_dax
            validated_measures.append(m)

        # Fallback if no measures survived
        if not validated_measures:
            validated_measures = [{
                "name": "Total Records",
                "dax": f"COUNTROWS('{table_name}')",
                "format": "#,##0",
                "description": "Total record count."
            }]
            seen_measure_names.add("total records")

        blueprint["dax_measures"] = validated_measures

        # Synchronize Visual Blueprints
        available_measure_names = [m["name"] for m in validated_measures]
        grouping_dims = [
            c["column"] for c in schema_summary
            if not any(k in c["column"].lower() for k in ["id", "key", "guid", "uuid"])
        ]
        if not grouping_dims:
            grouping_dims = [c["column"] for c in schema_summary]

        for v in blueprint.get("visual_blueprints", []):
            req_m = (v.get("measure") or "").strip()
            # Update renamed measure references
            if req_m.lower() in rename_map:
                v["measure"] = rename_map[req_m.lower()]
            elif req_m.lower() not in {m.lower() for m in available_measure_names}:
                v["measure"] = available_measure_names[0]

            # Clean duplicate "by Dim by Dim" titles if any
            if "title" in v and v["title"]:
                v["title"] = re.sub(r"\s+by\s+(\b\w+\b)(?:\s+by\s+\1)+", r" by \1", v["title"], flags=re.IGNORECASE).strip()

            # Validate dimension
            if "dimension" in v and v["dimension"]:
                dim_req = str(v["dimension"]).strip()
                if dim_req.lower() in existing_cols_lower:
                    v["dimension"] = col_names[dim_req.lower()]
                else:
                    v["dimension"] = grouping_dims[0]

        return blueprint

    def model_dataset(
        self, 
        parquet_path: str | Path, 
        table_name: str = "sales", 
        user_intent: Optional[str] = None
    ) -> Dict[str, Any]:
        path_str = str(parquet_path).replace("\\", "/")

        # 1. Fast Schema & Data Probe using DuckDB
        con = duckdb.connect(database=":memory:")
        schema_info = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path_str}')").fetchall()
        sample_rows = con.execute(f"SELECT * FROM read_parquet('{path_str}') LIMIT 2").fetchdf().to_dict(orient="records")
        row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path_str}')").fetchone()[0]
        con.close()

        schema_summary = [{"column": col[0], "data_type": col[1]} for col in schema_info]

        # Compact sample rows to strictly preserve prompt token budget (<800 tokens)
        compact_samples = []
        for row in sample_rows:
            compact_row = {}
            for k, val in row.items():
                if isinstance(val, str) and len(val) > 25:
                    compact_row[k] = val[:25] + "..."
                else:
                    compact_row[k] = val
            compact_samples.append(compact_row)

        user_guidance = (
            f"USER SPECIFIC REQUIREMENTS & DESIRED ANALYSIS:\n\"{user_intent}\"\n"
            f"IMPORTANT: You MUST tailor the DAX measures and visuals specifically to satisfy the user's request above."
            if user_intent and user_intent.strip()
            else "Auto-detect the 4-6 most valuable executive business metrics and charts."
        )

        prompt = f"""
Cleaned dataset for table '{table_name}' ({row_count:,} rows).
Schema:
{json.dumps(schema_summary, default=str)}

Sample Records:
{json.dumps(compact_samples, default=str)}

{user_guidance}

Return a raw JSON object with EXACTLY this structure:
{{
  "business_domain": "Short descriptive title of this dashboard",
  "table_name": "{table_name}",
  "user_request_fulfilled": "{user_intent if user_intent else 'Auto-detected executive metrics'}",
  "dimensions": [
    {{"column": "dimension_col_1", "description": "Primary breakdown dimension"}},
    {{"column": "dimension_col_2", "description": "Secondary category dimension"}}
  ],
  "dax_measures": [
    {{
      "name": "Total Metric Name",
      "dax": "SUM('{table_name}'[existing_column])",
      "format": "$#,##0.00",
      "description": "Metric description."
    }}
  ],
  "visual_blueprints": [
    {{
      "title": "Metric by Dimension",
      "type": "bar_chart",
      "dimension": "dimension_col_1",
      "measure": "Total Metric Name"
    }}
  ]
}}

STRICT RULES:
1. Provide 4-8 DAX measures matching the dataset and user intent.
2. Ensure DAX formulas reference '{table_name}'[column_name] using ONLY columns that ACTUALLY exist in the Schema above. NEVER invent column names.
3. If dataset has NO numeric columns (e.g. customer directory, user list), use COUNTROWS('{table_name}') and DISTINCTCOUNT('{table_name}'[id_or_category_col]). NEVER call SUM or AVERAGE on strings!
4. CRITICAL - NO RESERVED KEYWORDS: NEVER name a measure with a DAX/Power BI reserved keyword (e.g. 'Total', 'Value', 'Date', 'Current', 'Rank', 'Row', 'Order', 'Filter', 'Table', 'Measure'). Always use descriptive names like 'Total Revenue', 'Average Price', 'Distinct Customers'.
5. CRITICAL: The 'dax' field must contain ONLY the DAX formula expression. NEVER include the measure name or '=' in the 'dax' string.
6. TIME INTELLIGENCE: Transaction dates contain duplicates. Power BI Desktop strictly forbids built-in functions (DATEADD, TOTALYTD, SAMEPERIODLASTYEAR) on duplicate dates. Use duplicate-safe CALCULATE/FILTER/MAX expressions.
7. VISUAL BLUEPRINTS: 'dimension' must be an exact column from Schema (prefer state, city, category over 99k-cardinality ID keys). 'measure' must be an exact measure name from dax_measures.
"""

        print(f"📊 Modeler Agent designing dashboard...")
        if user_intent:
            print(f"🎯 Incorporating User Request: \"{user_intent}\"")
            
        try:
            raw_response = self._call_llm(prompt)
            blueprint = self._clean_json_response(raw_response)
        except Exception as e:
            print(f"⚠️ Modeler LLM call failed ({e}). Generating schema-aware deterministic blueprint...")
            blueprint = self._generate_deterministic_blueprint(table_name, schema_summary, user_intent)

        # Universal validation, reserved keyword check, and visual synchronization
        blueprint = self._validate_and_heal_blueprint(blueprint, schema_summary, table_name)

        return blueprint

if __name__ == "__main__":
    cleaned_file = "data/cleaned/sales_cleaned_500k.parquet"
    if not Path(cleaned_file).exists():
        print(f"⚠️ {cleaned_file} not found. Run cleaner_agent.py first.")
        sys.exit(1)

    agent = ModelerAgent()

    # TEST WITH A CUSTOM USER PROMPT:
    custom_user_prompt = "I want to focus on high-value orders and compare regional revenue against product categories"
    blueprint = agent.model_dataset(cleaned_file, table_name="sales", user_intent=custom_user_prompt)

    print("\n" + "="*50)
    print(f"✅ DASHBOARD BLUEPRINT: {blueprint['business_domain']}")
    print(f"🎯 User Request: {blueprint['user_request_fulfilled']}")
    print("="*50)
    print("\n📌 CUSTOM DAX MEASURES:")
    for m in blueprint["dax_measures"]:
        print(f"   • {m['dax']}")

    print("\n📊 CUSTOM VISUALS:")
    for v in blueprint["visual_blueprints"]:
        print(f"   • [{v['type'].upper()}] {v['title']}")