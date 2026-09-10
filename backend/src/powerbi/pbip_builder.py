import sys
from pathlib import Path

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
import shutil
import base64
import tempfile
import duckdb
from typing import Dict, Any, List, Optional
from backend.src.config import PBIP_OUTPUT_DIR
from backend.src.powerbi.report_layout import ReportLayoutBuilder
from backend.src.powerbi.tmdl_builder import TMDLBuilder

class PBIPBuilder:
    """
    Programmatic Power BI Project (.pbip) Generator.
    Produces compliant PBIP structures compatible with Microsoft Power BI Desktop
    (including 2024-2026 releases):
      - <ProjectName>.pbip (Root project descriptor)
      - <ProjectName>.Report/ (Report layout & dataset pointer)
      - <ProjectName>.SemanticModel/ (Semantic model & definitions)
      - definition.pbism (Mandatory SemanticModel schema)
      - model.bim (TMSL database object with defaultPowerBIDataSourceVersion)
      - TMDL definitions (when format='tmdl')
    """

    def __init__(self):
        self.output_dir = PBIP_OUTPUT_DIR
        self.layout_builder = ReportLayoutBuilder()
        self.tmdl_builder = TMDLBuilder()

    def _map_duckdb_to_pbi_type(self, duck_type: str) -> str:
        d = duck_type.upper()
        if "INT" in d:
            return "int64"
        elif "DOUBLE" in d or "FLOAT" in d or "DECIMAL" in d:
            return "double"
        elif "DATE" in d or "TIME" in d:
            return "dateTime"
        elif "BOOL" in d:
            return "boolean"
        return "string"

    def _generate_model_bim(
        self,
        table_name: str,
        parquet_path: Path,
        dax_measures: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generates Tabular Model Definition (TMSL) containing Parquet connector & DAX."""
        parquet_str = str(parquet_path.resolve()).replace("\\", "/")

        # Probe columns & types from Parquet
        con = duckdb.connect(database=":memory:")
        cols_info = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_str}')").fetchall()
        con.close()

        columns = []
        for col_name, col_type, *_ in cols_info:
            columns.append({
                "name": col_name,
                "dataType": self._map_duckdb_to_pbi_type(col_type),
                "sourceColumn": col_name,
                "summarizeBy": "none" if "ID" in col_name.upper() else "default"
            })

        # Read parquet binary and encode to base64 for self-contained zero-configuration portability
        parquet_bytes = parquet_path.read_bytes()
        if len(parquet_bytes) > 8 * 1024 * 1024:
            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            con = duckdb.connect(database=":memory:")
            con.execute(f"COPY (SELECT * FROM read_parquet('{parquet_str}') LIMIT 25000) TO '{str(tmp_path).replace(chr(92), '/')}' (FORMAT PARQUET)")
            con.close()
            parquet_bytes = tmp_path.read_bytes()
            if tmp_path.exists():
                tmp_path.unlink()

        b64_parquet = base64.b64encode(parquet_bytes).decode("ascii")

        # Power Query M expression to load Parquet directly from embedded memory
        m_query = f"""let
    Source = Parquet.Document(Binary.Buffer(Binary.FromText("{b64_parquet}", BinaryEncoding.Base64)))
in
    Source"""

        # Format DAX measures
        measures = []
        for m in dax_measures:
            clean_dax = self.tmdl_builder._clean_and_format_dax(m.get("dax") or "", m.get("name"))

            measures.append({
                "name": m.get("name") or "Metric",
                "expression": clean_dax,
                "formatString": m.get("format") or "$#,##0.00"
            })

        return {
            "name": "SemanticModel",
            "compatibilityLevel": 1550,
            "model": {
                "culture": "en-US",
                "defaultPowerBIDataSourceVersion": "powerBI_V3",
                "tables": [
                    {
                        "name": table_name,
                        "columns": columns,
                        "partitions": [
                            {
                                "name": f"{table_name}-Partition",
                                "mode": "import",
                                "source": {
                                    "type": "m",
                                    "expression": m_query.splitlines()
                                }
                            }
                        ],
                        "measures": measures
                    }
                ]
            }
        }

    def _populate_model_dir(
        self,
        target_dir: Path,
        table_name: str,
        parquet_path: Path,
        dax_measures: List[Dict[str, Any]],
        format: str = "tmsl"
    ):
        """Populates a semantic model / dataset directory with required metadata."""
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. definition.pbism (CRITICAL: Required by modern Power BI Desktop)
        is_tmdl = format.lower() == "tmdl"
        pbism_version = "4.0" if is_tmdl else "1.0"
        pbism_content = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": pbism_version,
            "settings": {
                "qnaEnabled": False
            }
        }
        (target_dir / "definition.pbism").write_text(
            json.dumps(pbism_content, indent=2), encoding="utf-8"
        )

        if is_tmdl:
            # TMDL Format: definition/ folder only; model.bim MUST NOT exist
            if (target_dir / "model.bim").exists():
                (target_dir / "model.bim").unlink()
            self.tmdl_builder.generate_tmdl(
                table_name=table_name,
                parquet_path=parquet_path,
                dax_measures=dax_measures,
                output_semantic_model_dir=target_dir
            )
        else:
            # TMSL Format: model.bim only; definition/ folder MUST NOT exist
            if (target_dir / "definition").exists():
                shutil.rmtree(target_dir / "definition")
            model_bim = self._generate_model_bim(table_name, parquet_path, dax_measures)
            (target_dir / "model.bim").write_text(
                json.dumps(model_bim, indent=2), encoding="utf-8"
            )

    def build_pbip_project(
        self,
        parquet_path: str | Path,
        modeling_blueprint: Dict[str, Any],
        project_name: str = "Sales_Dashboard",
        format: str = "tmsl",
        **kwargs
    ) -> Path:
        """
        Assembles the full .pbip project directory and produces a downloadable .zip archive.
        Ensures strict compliance with Power BI Desktop specifications:
          - Modern .SemanticModel folder naming matching Fabric standard
          - Valid definition.pbism with semanticModel schema
          - Correct definition.pbir pointing to the semantic model
          - Self-contained parquet data in project /data subfolder
          - Properly wrapped ZIP archive
        """
        parquet_path = Path(parquet_path).resolve()
        table_name = modeling_blueprint.get("table_name", "sales")
        domain_title = modeling_blueprint.get("business_domain", "Executive Dashboard")
        dax_measures = modeling_blueprint.get("dax_measures", [])
        visuals = modeling_blueprint.get("visual_blueprints", [])

        # Project directory
        proj_dir = self.output_dir / project_name
        report_dir = proj_dir / f"{project_name}.Report"
        semantic_model_dir = proj_dir / f"{project_name}.SemanticModel"
        data_dir = proj_dir / "data"

        if proj_dir.exists():
            shutil.rmtree(proj_dir)

        report_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)

        # Copy cleaned parquet data into package for portable self-containment
        local_data_path = data_dir / parquet_path.name
        try:
            shutil.copy2(parquet_path, local_data_path)
        except Exception as e:
            print(f"⚠️ Notice: could not copy parquet into package: {e}")
            local_data_path = parquet_path

        # 1. Root .pbip pointer
        pbip_meta = {
            "version": "1.0",
            "artifacts": [
                {
                    "report": {
                        "path": f"{project_name}.Report"
                    }
                }
            ],
            "settings": {
                "enableAutoRecovery": True
            }
        }
        (proj_dir / f"{project_name}.pbip").write_text(
            json.dumps(pbip_meta, indent=2), encoding="utf-8"
        )

        # 2. Report definition.pbir & report.json
        report_pbir = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json",
            "version": "1.0",
            "datasetReference": {
                "byPath": {
                    "path": f"../{project_name}.SemanticModel"
                },
                "byConnection": None
            }
        }
        (report_dir / "definition.pbir").write_text(
            json.dumps(report_pbir, indent=2), encoding="utf-8"
        )

        # Extract actual parquet columns and measures for 100% case-accurate visual bindings
        parquet_str = str(parquet_path.resolve()).replace("\\", "/")
        con = duckdb.connect(database=":memory:")
        cols_info = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_str}')").fetchall()
        con.close()
        available_cols = [c[0] for c in cols_info]
        available_measures = [m.get("name") for m in dax_measures]

        report_json = self.layout_builder.generate_layout(
            domain_title, 
            table_name, 
            visuals,
            available_columns=available_cols,
            available_measures=available_measures
        )
        (report_dir / "report.json").write_text(
            json.dumps(report_json, indent=2), encoding="utf-8"
        )

        # 3. Populate .SemanticModel directory (standard for Power BI Projects & Fabric)
        self._populate_model_dir(
            target_dir=semantic_model_dir,
            table_name=table_name,
            parquet_path=local_data_path,
            dax_measures=dax_measures,
            format=format
        )

        # 4. Create downloadable ZIP with project contents at zip root
        import zipfile
        zip_path = self.output_dir / f"{project_name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(proj_dir.rglob("*")):
                if file_path.is_file():
                    zf.write(file_path, arcname=str(file_path.relative_to(proj_dir)))

        return proj_dir

if __name__ == "__main__":
    cleaned_file = Path("data/cleaned/clean_dataset.parquet")
    if not cleaned_file.exists():
        cleaned_file = Path("data/cleaned/sales_cleaned_500k.parquet")

    if not cleaned_file.exists():
        print(f"⚠️ Cleaned parquet not found. Run cleaner_agent.py first.")
        sys.exit(1)

    blueprint_sample = {
        "business_domain": "Sales Executive Dashboard",
        "table_name": "sales",
        "dax_measures": [
            {"name": "Total Revenue", "dax": "Total Revenue = SUM('sales'[revenue])", "format": "$#,##0.00"},
            {"name": "Total Orders", "dax": "Total Orders = DISTINCTCOUNT('sales'[order_id])", "format": "#,##0"},
            {"name": "Average Order Value", "dax": "Average Order Value = DIVIDE([Total Revenue], [Total Orders], 0)", "format": "$#,##0.00"}
        ],
        "visual_blueprints": [
            {"type": "card", "title": "Total Revenue", "measure": "Total Revenue"},
            {"type": "card", "title": "Total Orders", "measure": "Total Orders"},
            {"type": "card", "title": "Avg Order Value", "measure": "Average Order Value"},
            {"type": "line_chart", "title": "Monthly Revenue Trend", "dimension": "order_date", "measure": "Total Revenue"},
            {"type": "donut_chart", "title": "Revenue by Region", "dimension": "region", "measure": "Total Revenue"},
            {"type": "bar_chart", "title": "Revenue by Category", "dimension": "category", "measure": "Total Revenue"}
        ]
    }

    builder = PBIPBuilder()
    print("🚀 Re-assembling Power BI Project (.pbip) with definition.pbism...")
    project_folder = builder.build_pbip_project(
        parquet_path=cleaned_file,
        modeling_blueprint=blueprint_sample,
        project_name="Executive_Dashboard"
    )

    print("\n" + "="*50)
    print("✅ POWER BI PROJECT GENERATED SUCCESSFULLY!")
    print(f"📁 Project Folder: {project_folder}")
    print(f"📄 Double-click to open in Power BI: {project_folder / 'Executive_Dashboard.pbip'}")
    print("="*50)
