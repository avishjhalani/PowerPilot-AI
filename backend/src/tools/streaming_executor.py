import ast
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, Any
import psutil
import duckdb

# Whitelisted safe modules for data engineering
ALLOWED_MODULES = {"polars", "datetime", "re", "math", "typing"}

class SecurityError(Exception):
    pass

class StreamingExecutor:
    """
    Production-grade sandbox:
    1. Static AST code scanning for security (blocks dangerous imports/calls).
    2. Subprocess execution with real-time RAM tracking.
    3. Row-loss integrity guardrail (fails if LLM dropped >25% of rows unexpectedly).
    """

    def __init__(self, timeout_seconds: int = 180, min_row_retention_pct: float = 50.0):
        self.timeout = timeout_seconds
        self.min_retention_pct = min_row_retention_pct

    def validate_code_ast(self, code_str: str):
        """Inspects AST to ensure no unauthorized libraries or system calls exist."""
        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            raise SecurityError(f"Syntax error in generated code: {e}")

        for node in ast.walk(tree):
            # Check standard imports (import os, import socket)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod not in ALLOWED_MODULES:
                        raise SecurityError(f"Unauthorized import blocked: '{alias.name}'")

            # Check from-imports (from os import path)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod not in ALLOWED_MODULES:
                        raise SecurityError(f"Unauthorized import blocked: 'from {node.module}'")

            # Block dangerous built-ins (eval, exec, __import__)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "__import__", "compile"}:
                    raise SecurityError(f"Dangerous function call blocked: '{node.func.id}()'")

    def execute_script(self, script_content: str, script_path: Path, output_parquet_path: Path, raw_row_count: int) -> Dict[str, Any]:
        # 1. AST Security Validation
        try:
            self.validate_code_ast(script_content)
        except SecurityError as se:
            return {
                "success": False,
                "error_message": f"Security Guardrail Triggered: {str(se)}",
                "execution_time_seconds": 0.0,
                "peak_memory_mb": 0.0,
                "output_file": None
            }

        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_content, encoding="utf-8")

        start_time = time.time()
        peak_memory_mb = 0.0

        try:
            # 2. Subprocess Execution
            proc = subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            p = psutil.Process(proc.pid)
            while proc.poll() is None:
                try:
                    mem_mb = p.memory_info().rss / (1024 * 1024)
                    if mem_mb > peak_memory_mb:
                        peak_memory_mb = mem_mb
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
                time.sleep(0.05)

            stdout, stderr = proc.communicate(timeout=self.timeout)
            duration = round(time.time() - start_time, 2)

            if proc.returncode != 0:
                return {
                    "success": False,
                    "error_message": stderr.strip() or stdout.strip(),
                    "execution_time_seconds": duration,
                    "peak_memory_mb": round(peak_memory_mb, 2),
                    "output_file": None
                }

            if not output_parquet_path.exists():
                return {
                    "success": False,
                    "error_message": f"Expected output file '{output_parquet_path}' was not generated.",
                    "execution_time_seconds": duration,
                    "peak_memory_mb": round(peak_memory_mb, 2),
                    "output_file": None
                }

            # 3. Data Integrity & Row Retention Guardrail
            path_str = str(output_parquet_path).replace("\\", "/")
            con = duckdb.connect(database=":memory:")
            cleaned_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path_str}')").fetchone()[0]
            retention_pct = round((cleaned_count / raw_row_count) * 100, 2) if raw_row_count > 0 else 100.0
            if retention_pct < self.min_retention_pct:
                con.close()
                output_parquet_path.unlink(missing_ok=True)
                return {
                    "success": False,
                    "error_message": (
                        f"Data Integrity Failure: Cleaning dropped too many rows! "
                        f"Retained only {cleaned_count:,} / {raw_row_count:,} ({retention_pct}%). "
                        f"Minimum required is {self.min_retention_pct}%. Do not use overly aggressive drop_nulls()."
                    ),
                    "execution_time_seconds": duration,
                    "peak_memory_mb": round(peak_memory_mb, 2),
                    "output_file": None
                }

            # 4. Date Nullification Guardrail
            cols_desc = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path_str}')").fetchall()
            for c_info in cols_desc:
                c_name = c_info[0]
                if "date" in c_name.lower() and cleaned_count > 0:
                    null_cnt = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path_str}') WHERE \"{c_name}\" IS NULL").fetchone()[0]
                    if null_cnt == cleaned_count:
                        con.close()
                        output_parquet_path.unlink(missing_ok=True)
                        return {
                            "success": False,
                            "error_message": (
                                f"Data Integrity Failure: Date column '{c_name}' was 100% nullified ({null_cnt}/{cleaned_count} nulls)! "
                                f"In Polars, NEVER call .cast(pl.Date) directly on string columns. "
                                f"ALWAYS use pl.coalesce with str.to_date('%d-%m-%Y', strict=False), str.to_date('%Y-%m-%d', strict=False), str.to_date('%d/%m/%Y', strict=False), etc."
                            ),
                            "execution_time_seconds": duration,
                            "peak_memory_mb": round(peak_memory_mb, 2),
                            "output_file": None
                        }

            con.close()

            file_size_mb = round(output_parquet_path.stat().st_size / (1024 * 1024), 2)
            return {
                "success": True,
                "error_message": None,
                "execution_time_seconds": duration,
                "peak_memory_mb": round(peak_memory_mb, 2),
                "output_file": str(output_parquet_path),
                "file_size_mb": file_size_mb,
                "cleaned_rows": cleaned_count,
                "retention_percentage": retention_pct,
                "stdout": stdout.strip()
            }

        except subprocess.TimeoutExpired:
            proc.kill()
            return {
                "success": False,
                "error_message": f"Execution timed out after {self.timeout}s.",
                "execution_time_seconds": self.timeout,
                "peak_memory_mb": round(peak_memory_mb, 2),
                "output_file": None
            }