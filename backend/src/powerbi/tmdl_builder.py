from pathlib import Path
from typing import Dict, Any, List
import re
import base64
import tempfile
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

    def _sanitize_time_intelligence(self, dax: str) -> str:
        """
        Replaces DATEADD, TOTALYTD, DATESYTD, and other time intelligence functions
        that require unique contiguous date tables with duplicate-safe DAX filter patterns.
        """
        # TOTALYTD(expr, date_col [, filter])
        def repl_totalytd(m):
            expr = m.group("expr").strip()
            date_col = m.group("date").strip()
            flt = m.group("filter")
            if flt:
                return f"CALCULATE({expr}, FILTER(ALLSELECTED({date_col}), {date_col} <= MAX({date_col})), {flt.strip()})"
            return f"CALCULATE({expr}, FILTER(ALLSELECTED({date_col}), {date_col} <= MAX({date_col})))"

        dax = re.sub(
            r"TOTALYTD\s*\(\s*(?P<expr>[^,]+)\s*,\s*(?P<date>[^,\)]+)(?:\s*,\s*(?P<filter>[^\)]+))?\s*\)",
            repl_totalytd,
            dax,
            flags=re.IGNORECASE
        )

        # DATESYTD(date_col)
        dax = re.sub(
            r"DATESYTD\s*\(\s*(?P<date>[^\)]+)\s*\)",
            r"FILTER(ALLSELECTED(\g<date>), \g<date> <= MAX(\g<date>))",
            dax,
            flags=re.IGNORECASE
        )

        # DATEADD(date_col, -1, MONTH) or PARALLELPERIOD / PREVIOUSMONTH
        def repl_dateadd_month(m):
            date_col = m.group("date").strip()
            return (
                f"FILTER(ALL({date_col}), "
                f"MONTH({date_col}) = IF(MONTH(MAX({date_col})) = 1, 12, MONTH(MAX({date_col})) - 1) && "
                f"YEAR({date_col}) = IF(MONTH(MAX({date_col})) = 1, YEAR(MAX({date_col})) - 1, YEAR(MAX({date_col}))))"
            )

        dax = re.sub(
            r"DATEADD\s*\(\s*(?P<date>[^,]+)\s*,\s*-[0-9]+\s*,\s*MONTH\s*\)",
            repl_dateadd_month,
            dax,
            flags=re.IGNORECASE
        )
        dax = re.sub(
            r"PREVIOUSMONTH\s*\(\s*(?P<date>[^\)]+)\s*\)",
            repl_dateadd_month,
            dax,
            flags=re.IGNORECASE
        )
        dax = re.sub(
            r"PARALLELPERIOD\s*\(\s*(?P<date>[^,]+)\s*,\s*-[0-9]+\s*,\s*MONTH\s*\)",
            repl_dateadd_month,
            dax,
            flags=re.IGNORECASE
        )

        # DATEADD(date_col, -1, YEAR) or SAMEPERIODLASTYEAR
        def repl_dateadd_year(m):
            date_col = m.group("date").strip()
            return f"FILTER(ALL({date_col}), YEAR({date_col}) = YEAR(MAX({date_col})) - 1)"

        dax = re.sub(
            r"DATEADD\s*\(\s*(?P<date>[^,]+)\s*,\s*-[0-9]+\s*,\s*YEAR\s*\)",
            repl_dateadd_year,
            dax,
            flags=re.IGNORECASE
        )
        dax = re.sub(
            r"SAMEPERIODLASTYEAR\s*\(\s*(?P<date>[^\)]+)\s*\)",
            repl_dateadd_year,
            dax,
            flags=re.IGNORECASE
        )

        return dax

    def _clean_and_format_dax(self, raw_dax: str, m_name: str = None) -> str:
        """
        Cleans DAX expressions:
        - Strips accidental 'MeasureName =' or '[MeasureName] =' prefixes
        - Safely preserves 'VAR ...' expressions without stripping
        - Replaces unsafe time intelligence on duplicate date transaction tables
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

        # Sanitize time intelligence that breaks on transaction tables with duplicate dates
        clean_dax = self._sanitize_time_intelligence(clean_dax)

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

        escaped_table_name = table_name.replace("'", "''")

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
            f"ref table '{escaped_table_name}'\n"
        )
        (definition_dir / "model.tmdl").write_text(model_content, encoding="utf-8")

        # 4. Write definition/tables/<table_name>.tmdl
        table_lines = [f"table '{escaped_table_name}'\n"]

        # Columns
        for col_name, col_type, *_ in cols_info:
            tmdl_type = self._map_duckdb_to_tmdl_type(col_type)
            summarize = "none" if "ID" in col_name.upper() else "default"
            escaped_col_name = col_name.replace("'", "''")
            escaped_source_col = col_name.replace('"', '""')
            table_lines.append(f"\tcolumn '{escaped_col_name}'")
            table_lines.append(f"\t\tdataType: {tmdl_type}")
            table_lines.append(f'\t\tsourceColumn: "{escaped_source_col}"')
            table_lines.append(f"\t\tsummarizeBy: {summarize}\n")

        # Measures
        for m in dax_measures:
            m_name = m.get("name", "Metric")
            clean_dax = self._clean_and_format_dax(m.get("dax", ""), m_name=m_name)
            fmt = m.get("format", "$#,##0.00")
            escaped_m_name = m_name.replace("'", "''")
            escaped_fmt = fmt.replace('"', '""')

            # In TMDL, multi-line DAX or DAX containing VAR MUST be enclosed in triple backticks (```)
            # per Microsoft TMDL specification:
            #   measure 'Name' = ```
            #       <expression>
            #       ```
            #       formatString: ...
            if "\n" in clean_dax or "\r" in clean_dax or "VAR " in clean_dax:
                dax_lines = [line.strip() for line in clean_dax.splitlines() if line.strip()]
                indented_dax = "\n".join(f"\t\t{line}" for line in dax_lines)
                table_lines.append(f"\tmeasure '{escaped_m_name}' = ```\n{indented_dax}\n\t\t```")
            else:
                table_lines.append(f"\tmeasure '{escaped_m_name}' = {clean_dax}")

            table_lines.append(f'\t\tformatString: "{escaped_fmt}"\n')

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

        # Partition (Power Query M expression loading embedded parquet directly into memory)
        table_lines.append(f"\tpartition '{escaped_table_name}-Partition' = m")
        table_lines.append("\t\tmode: import")
        table_lines.append("\t\tsource =")
        table_lines.append("\t\t\tlet")
        table_lines.append(f'\t\t\t\tSource = Parquet.Document(Binary.Buffer(Binary.FromText("{b64_parquet}", BinaryEncoding.Base64)))')
        table_lines.append("\t\t\tin")
        table_lines.append("\t\t\t\tSource\n")

        table_file = tables_dir / f"{table_name}.tmdl"
        table_file.write_text("\n".join(table_lines), encoding="utf-8")

        return definition_dir
