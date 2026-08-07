import json
import time
from pathlib import Path
import duckdb
from typing import Dict, Any

class StreamingProfiler:
    """
    Production-grade single-pass DuckDB profiler.
    Scans millions of rows in a SINGLE pass on disk in ~1-2 seconds.
    """

    def __init__(self, sample_size: int = 15):
        self.sample_size = sample_size

    def profile_file(self, file_path: str | Path) -> Dict[str, Any]:
        path_str = str(file_path).replace("\\", "/")
        start_time = time.time()
        
        con = duckdb.connect(database=":memory:")
        is_parquet = path_str.endswith(".parquet")
        table_scan = f"read_parquet('{path_str}')" if is_parquet else f"read_csv_auto('{path_str}', ignore_errors=true)"

        # 1. Inspect Schema
        schema_query = f"DESCRIBE SELECT * FROM {table_scan} LIMIT 1"
        columns_meta = con.execute(schema_query).fetchall()

        # 2. Build ONE Single-Pass Dynamic SQL Query for All Columns
        sql_parts = ["COUNT(*) as total_rows"]
        for i, (col_name, col_type, *_) in enumerate(columns_meta):
            safe_col = f'"{col_name}"'
            sql_parts.extend([
                f'COUNT({safe_col}) as "non_null_{i}"',
                f'COUNT(CASE WHEN {safe_col} IS NULL THEN 1 END) as "null_{i}"',
                f'APPROX_COUNT_DISTINCT({safe_col}) as "uniq_{i}"',
                f'MIN(CAST({safe_col} AS VARCHAR)) as "min_{i}"',
                f'MAX(CAST({safe_col} AS VARCHAR)) as "max_{i}"'
            ])

        unified_query = f"SELECT {', '.join(sql_parts)} FROM {table_scan}"
        stats_row = con.execute(unified_query).fetchone()
        total_rows = stats_row[0]

        # 3. Fast Pattern Check on a 1,000-Row Sample for String Flaws
        sample_check_parts = []
        varchar_indices = []
        for i, (col_name, col_type, *_) in enumerate(columns_meta):
            if col_type == "VARCHAR":
                varchar_indices.append((i, col_name))
                safe_col = f'"{col_name}"'
                sample_check_parts.extend([
                    f"SUM(CASE WHEN regexp_matches({safe_col}, '[\$,€,£]') THEN 1 ELSE 0 END) as curr_{i}",
                    f"SUM(CASE WHEN lower(trim({safe_col})) IN ('n/a', 'null', '-', 'none', '', 'free') THEN 1 ELSE 0 END) as mask_{i}"
                ])

        pattern_results = {}
        if sample_check_parts:
            pattern_query = f"SELECT {', '.join(sample_check_parts)} FROM (SELECT * FROM {table_scan} LIMIT 1000)"
            p_row = con.execute(pattern_query).fetchone()
            p_idx = 0
            for i, _ in varchar_indices:
                pattern_results[i] = {
                    "has_currency": (p_row[p_idx] or 0) > 0,
                    "has_masked_nulls": (p_row[p_idx + 1] or 0) > 0
                }
                p_idx += 2

        # 4. Map Results to Schema
        column_summaries = []
        idx = 1
        for i, (col_name, col_type, *_) in enumerate(columns_meta):
            non_null_count = stats_row[idx]
            null_count = stats_row[idx + 1]
            unique_count = stats_row[idx + 2]
            min_val = stats_row[idx + 3]
            max_val = stats_row[idx + 4]
            idx += 5

            null_pct = round((null_count / total_rows) * 100, 2) if total_rows > 0 else 0.0

            dirty_signals = []
            if i in pattern_results:
                if pattern_results[i]["has_currency"]:
                    dirty_signals.append("CONTAINS_CURRENCY_SYMBOLS")
                if pattern_results[i]["has_masked_nulls"]:
                    dirty_signals.append("CONTAINS_STRING_MASKED_NULLS")

            column_summaries.append({
                "name": col_name,
                "inferred_type": col_type,
                "null_count": null_count,
                "null_percentage": f"{null_pct}%",
                "unique_values_approx": unique_count,
                "min_sample": min_val,
                "max_sample": max_val,
                "detected_issues": dirty_signals
            })

        # 5. Token-Controlled 15-Row Sample
        sample_query = f"SELECT * FROM {table_scan} LIMIT {self.sample_size}"
        df_sample = con.execute(sample_query).fetchdf()
        sample_records = json.loads(df_sample.to_json(orient="records", date_format="iso"))

        con.close()
        duration = round(time.time() - start_time, 2)

        return {
            "file_path": path_str,
            "total_rows": total_rows,
            "column_count": len(column_summaries),
            "profiling_duration_seconds": duration,
            "columns": column_summaries,
            "sample_records": sample_records
        }

if __name__ == "__main__":
    from pprint import pprint
    test_file = "data/raw/messy_sales_500k.csv"
    profiler = StreamingProfiler(sample_size=5)
    print(f"🔍 Running single-pass profiling on {test_file}...")
    report = profiler.profile_file(test_file)
    print(f"\n⚡ PROFILED {report['total_rows']:,} ROWS IN JUST {report['profiling_duration_seconds']} SECONDS!")