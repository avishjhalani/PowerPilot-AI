from pathlib import Path
from typing import Dict, Any, List
import duckdb

class TMDLBuilder:
    """
    Constructs Tabular Model Definition Language (TMDL) files for modern Power BI Projects.
    Follows Microsoft Fabric & Power BI TMDL folder specifications:
      - definition.pbism (version 4.0)
      - definition/database.tmdl
      - definition/model.tmdl
      - definition/tables/<table_name>.tmdl
    """

    def __init__(self):
        pass

    def _map_duckdb_to_tmdl_type(self, duck_type: str) -> str:
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

    def _clean_and_format_dax(self, raw_dax: str, m_name: str = None) -> str:
        """
        Cleans DAX expressions:
        - Strips accidental 'MeasureName =' or '[MeasureName] =' prefixes
        - Safely preserves 'VAR ...' expressions without stripping
        - Expands single-line VAR/RETURN into multiline
        """
        clean_dax = (raw_dax or "").strip()
        while "=" in clean_dax:
            prefix, rest = clean_dax.split("=", 1)
            prefix_clean = prefix.strip()
            prefix_upper = prefix_clean.upper()

            # Check if prefix is NOT a measure assignment
            is_not_measure = (
                prefix_upper.startswith("VAR ")
                or prefix_upper.startswith("VAR\t")
                or prefix_upper.startswith("VAR\n")
                or prefix_upper == "VAR"
                or prefix_upper.startswith("RETURN ")
                or "(" in prefix_clean
                or ")" in prefix_clean
                or any(op in prefix_clean for op in ["+", "*", "/", "<", ">"])
                or ("-" in prefix_clean and not all(c.isalnum() or c in " _-" for c in prefix_clean))
            )

            # If m_name is provided and matches prefix (ignoring brackets/quotes)
            if m_name and prefix_clean.strip("[]'\" ").lower() == m_name.strip("[]'\" ").lower():
                is_not_measure = False

            if not is_not_measure and rest.strip():
                clean_dax = rest.strip()
            else:
                break

        # If DAX has inline VAR / RETURN statements on a single line, split them
        if "VAR " in clean_dax and "\n" not in clean_dax:
            clean_dax = clean_dax.replace(" VAR ", "\nVAR ").replace(" RETURN ", "\nRETURN ")

        return clean_dax

    def generate_tmdl(
        self,
        table_name: str,
        parquet_path: Path,
        dax_measures: List[Dict[str, Any]],
        output_semantic_model_dir: Path
    ) -> Path:
        definition_dir = output_semantic_model_dir / "definition"
        tables_dir = definition_dir / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)

        parquet_str = str(parquet_path.resolve()).replace("\\", "/")

        # 1. Probe schema using DuckDB
        con = duckdb.connect(database=":memory:")
        cols_info = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_str}')").fetchall()
        con.close()

        # 2. Write definition/database.tmdl
        db_content = (
            "database SemanticModel\n"
            "\tcompatibilityLevel: 1550\n"
        )
        (definition_dir / "database.tmdl").write_text(db_content, encoding="utf-8")

        # 3. Write definition/model.tmdl
        model_content = (
            "model Model\n"
            "\tculture: en-US\n"
            "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\n"
            f"ref table '{table_name}'\n"
        )
        (definition_dir / "model.tmdl").write_text(model_content, encoding="utf-8")

        # 4. Write definition/tables/<table_name>.tmdl
        table_lines = [f"table '{table_name}'\n"]

        # Columns
        for col_name, col_type, *_ in cols_info:
            tmdl_type = self._map_duckdb_to_tmdl_type(col_type)
            summarize = "none" if "ID" in col_name.upper() else "default"
            table_lines.append(f"\tcolumn '{col_name}'")
            table_lines.append(f"\t\tdataType: {tmdl_type}")
            table_lines.append(f"\t\tsourceColumn: {col_name}")
            table_lines.append(f"\t\tsummarizeBy: {summarize}\n")

        # Measures
        for m in dax_measures:
            m_name = m.get("name", "Metric")
            clean_dax = self._clean_and_format_dax(m.get("dax", ""), m_name=m_name)
            fmt = m.get("format", "$#,##0.00")

            # In TMDL, multi-line DAX or DAX containing VAR MUST be enclosed in triple backticks (```)
            # per Microsoft TMDL specification:
            #   measure 'Name' = ```
            #       <expression>
            #       ```
            #       formatString: ...
            if "\n" in clean_dax or "\r" in clean_dax or "VAR " in clean_dax:
                dax_lines = [line.strip() for line in clean_dax.splitlines() if line.strip()]
                indented_dax = "\n".join(f"\t\t{line}" for line in dax_lines)
                table_lines.append(f"\tmeasure '{m_name}' = ```\n{indented_dax}\n\t\t```")
            else:
                table_lines.append(f"\tmeasure '{m_name}' = {clean_dax}")

            table_lines.append(f"\t\tformatString: \"{fmt}\"\n")

        # Partition (Power Query M expression loading parquet)
        table_lines.append(f"\tpartition '{table_name}-Partition' = m")
        table_lines.append("\t\tmode: import")
        table_lines.append("\t\tsource =")
        table_lines.append("\t\t\tlet")
        table_lines.append(f'\t\t\t\tSource = Parquet.Document(File.Contents("{parquet_str}"))')
        table_lines.append("\t\t\tin")
        table_lines.append("\t\t\t\tSource\n")

        table_file = tables_dir / f"{table_name}.tmdl"
        table_file.write_text("\n".join(table_lines), encoding="utf-8")

        return definition_dir
