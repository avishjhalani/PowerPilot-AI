import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import json
import re
import duckdb
from typing import Dict, Any, Optional
from groq import Groq

from backend.src.config import GROQ_API_KEY, DEFAULT_GROQ_MODEL

class ModelerAgent:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = DEFAULT_GROQ_MODEL

    def _call_llm(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
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
        return response.choices[0].message.content

    def _clean_json_response(self, text: str) -> Dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return json.loads(cleaned)

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
        sample_rows = con.execute(f"SELECT * FROM read_parquet('{path_str}') LIMIT 3").fetchdf().to_dict(orient="records")
        row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path_str}')").fetchone()[0]
        con.close()

        schema_summary = [{"column": col[0], "data_type": col[1]} for col in schema_info]

        # 2. Dynamic User Guidance
        user_guidance = (
            f"USER SPECIFIC REQUIREMENTS & DESIRED ANALYSIS:\n\"{user_intent}\"\n"
            f"IMPORTANT: You MUST tailor the DAX measures and visuals specifically to satisfy the user's request above."
            if user_intent and user_intent.strip()
            else "No specific user prompt provided. Auto-detect the 4-6 most valuable executive business metrics and charts."
        )

        prompt = f"""
I have a cleaned dataset for table '{table_name}' with {row_count:,} rows.
Schema:
{json.dumps(schema_summary, indent=2, default=str)}

Sample Data:
{json.dumps(sample_rows, indent=2, default=str)}

{user_guidance}

Return a raw JSON object with EXACTLY this structure:
{{
  "business_domain": "Short descriptive title of this dashboard",
  "table_name": "{table_name}",
  "user_request_fulfilled": "{user_intent if user_intent else 'Auto-detected executive metrics'}",
  "dimensions": [
    {{"column": "region", "description": "Geographical territory"}},
    {{"column": "category", "description": "Product taxonomy"}}
  ],
  "dax_measures": [
    {{
      "name": "Total Revenue",
      "dax": "SUM('{table_name}'[revenue])",
      "format": "$#,##0.00",
      "description": "Total gross revenue generated."
    }}
  ],
  "visual_blueprints": [
    {{
      "title": "Revenue by Region",
      "type": "bar_chart",
      "dimension": "region",
      "measure": "Total Revenue"
    }}
  ]
}}

RULES:
1. Provide 4-8 DAX measures matching the user's intent.
2. Design up to 9 visuals (up to 4 KPI Cards for Tier 1, plus 5 Charts like Bar Chart, Donut Chart, Line Chart for Tiers 2 & 3). If the user requests 9 visuals or specific metrics/charts, provide all 9!
3. Ensure DAX formulas reference '{table_name}'[column_name] accurately using columns that EXIST in the Schema.
4. CRITICAL: The 'dax' field must contain ONLY the DAX formula expression (e.g. "SUM('{table_name}'[revenue])" or "DIVIDE([Total Profit], [Total Revenue], 0)"). NEVER include the measure name or '=' in the 'dax' string.
5. CRITICAL - TIME INTELLIGENCE ON TRANSACTION TABLES:
The dataset is a transaction table ('{table_name}') where date columns contain DUPLICATE timestamps/dates.
Power BI Desktop STRICTLY FORBIDS built-in time-intelligence functions (like DATEADD, TOTALYTD, DATESYTD, SAMEPERIODLASTYEAR, PARALLELPERIOD, PREVIOUSMONTH) on columns with duplicate dates and will CRASH with:
"A date column containing duplicate values was specified in the call to function 'DATEADD'."
Instead, use standard duplicate-safe DAX:
- For Month-over-Month (MoM):
  VAR Current = [Total Revenue]
  VAR MaxDate = MAX('{table_name}'[date_col])
  VAR PriorMonth = IF(MONTH(MaxDate) = 1, 12, MONTH(MaxDate) - 1)
  VAR PriorYear = IF(MONTH(MaxDate) = 1, YEAR(MaxDate) - 1, YEAR(MaxDate))
  VAR Prior = CALCULATE([Total Revenue], FILTER(ALL('{table_name}'), MONTH('{table_name}'[date_col]) = PriorMonth && YEAR('{table_name}'[date_col]) = PriorYear))
  RETURN DIVIDE(Current - Prior, Prior, 0)
- For Cumulative / YTD:
  CALCULATE([Total Revenue], FILTER(ALLSELECTED('{table_name}'[date_col]), '{table_name}'[date_col] <= MAX('{table_name}'[date_col])))
6. VISUAL BLUEPRINTS:
- 'dimension' MUST be an exact column name that actually exists in the Schema above (e.g. use "order_date" or "category", NOT invented names like "order_month" or "region" if not present in Schema). Never leave empty for charts.
- 'measure' MUST be a SINGLE measure name from your dax_measures list (e.g. "Total Revenue"). NEVER list multiple measures separated by commas.
"""

        print(f"📊 Modeler Agent designing dashboard...")
        if user_intent:
            print(f"🎯 Incorporating User Request: \"{user_intent}\"")
            
        try:
            raw_response = self._call_llm(prompt)
            blueprint = self._clean_json_response(raw_response)
        except Exception as e:
            print(f"⚠️ Modeler LLM call failed ({e}). Generating high-speed deterministic blueprint...")
            num_cols = [c["column"] for c in schema_summary if any(t in c["data_type"].upper() for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL"])]
            cat_cols = [c["column"] for c in schema_summary if any(t in c["data_type"].upper() for t in ["VARCHAR", "TEXT", "STRING"])]

            val_col = "revenue" if any(c["column"] == "revenue" for c in schema_summary) else (num_cols[0] if num_cols else "value")
            qty_col = "quantity" if any(c["column"] == "quantity" for c in schema_summary) else (num_cols[1] if len(num_cols) > 1 else None)
            reg_col = "region" if any(c["column"] == "region" for c in schema_summary) else (cat_cols[0] if cat_cols else "dimension")
            cat_col = "category" if any(c["column"] == "category" for c in schema_summary) else (cat_cols[1] if len(cat_cols) > 1 else reg_col)

            # Ensure distinct names even if only 1 numeric column exists
            fallback_measures = [
                {
                    "name": f"Total {val_col.title()}",
                    "dax": f"SUM('{table_name}'[{val_col}])",
                    "format": "$#,##0.00",
                    "description": f"Total aggregate of {val_col}."
                }
            ]
            if qty_col:
                fallback_measures.append({
                    "name": f"Total {qty_col.title()}",
                    "dax": f"SUM('{table_name}'[{qty_col}])",
                    "format": "#,##0",
                    "description": f"Total aggregate of {qty_col}."
                })
            else:
                fallback_measures.append({
                    "name": "Total Records",
                    "dax": f"COUNTROWS('{table_name}')",
                    "format": "#,##0",
                    "description": "Total record count."
                })

            fallback_measures.append({
                "name": f"Average {val_col.title()}",
                "dax": f"AVERAGE('{table_name}'[{val_col}])",
                "format": "$#,##0.00",
                "description": f"Average per transaction."
            })

            sec_kpi = f"Total {qty_col.title()}" if qty_col else "Total Records"
            blueprint = {
                "business_domain": "Executive Performance Dashboard",
                "table_name": table_name,
                "user_request_fulfilled": user_intent or "Automated Executive Metrics",
                "dimensions": [
                    {"column": reg_col, "description": "Primary breakdown dimension"},
                    {"column": cat_col, "description": "Secondary category dimension"}
                ],
                "dax_measures": fallback_measures,
                "visual_blueprints": [
                    {"type": "card", "title": f"Total {val_col.title()}", "measure": f"Total {val_col.title()}"},
                    {"type": "card", "title": sec_kpi, "measure": sec_kpi},
                    {"type": "card", "title": f"Average {val_col.title()}", "measure": f"Average {val_col.title()}"},
                    {"type": "bar_chart", "title": f"{val_col.title()} by {reg_col.title()}", "dimension": reg_col, "measure": f"Total {val_col.title()}"},
                    {"type": "donut_chart", "title": f"{val_col.title()} by {cat_col.title()}", "dimension": cat_col, "measure": f"Total {val_col.title()}"}
                ]
            }

        # Deduplicate measure names (case-insensitive) so TMDL never encounters duplicate measure definitions
        from backend.src.powerbi.tmdl_builder import TMDLBuilder
        tmdl_builder = TMDLBuilder()
        seen_names = set()
        col_names = {c["column"].lower() for c in schema_summary}

        for m in blueprint.get("dax_measures", []):
            orig_name = (m.get("name") or "Metric").strip()
            unique_name = orig_name
            counter = 2
            while unique_name.lower() in seen_names or unique_name.lower() in col_names:
                unique_name = f"{orig_name} ({counter})"
                counter += 1
            seen_names.add(unique_name.lower())
            m["name"] = unique_name

            dax = (m.get("dax") or "").strip()
            clean_dax = tmdl_builder._clean_and_format_dax(dax, unique_name)
            m["dax"] = clean_dax

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