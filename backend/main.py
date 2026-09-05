import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
import argparse
from backend.src.config import (
    GROQ_API_KEY,
    RAW_DATA_DIR,
    OUTPUT_DIR,
    CLEANED_DATA_DIR,
    PBIP_OUTPUT_DIR,
    REPORTS_OUTPUT_DIR
)
from backend.src.tools.streaming_profiler import StreamingProfiler
from backend.src.agents.cleaner_agent import CleanerAgent
from backend.src.agents.modeler_agent import ModelerAgent
from backend.src.reporting.audit_pdf_builder import AuditPDFBuilder
from backend.src.powerbi.pbip_builder import PBIPBuilder

def run_pipeline(
    input_file: str | Path,
    user_intent: str = None,
    project_name: str = "Executive_Dashboard",
    model_format: str = "tmsl",
    output_parquet_name: str = "clean_dataset.parquet"
):
    input_path = Path(input_file).resolve()
    if not input_path.exists():
        print(f"❌ Error: Input file not found at: {input_path}")
        sys.exit(1)

    if not os.environ.get("GROQ_API_KEY"):
        if GROQ_API_KEY:
            os.environ["GROQ_API_KEY"] = GROQ_API_KEY
        else:
            print("❌ Error: GROQ_API_KEY is not set in environment or .env file.")
            sys.exit(1)

    print("=" * 65)
    print("⚡ AUTONOMOUS BIG DATA & POWER BI AGENT PIPELINE")
    print(f"📁 Source File: {input_path} ({round(input_path.stat().st_size / (1024*1024), 2)} MB)")
    if user_intent:
        print(f"🎯 Objective:   {user_intent}")
    print(f"📊 Target PBIP: {project_name} (Format: {model_format.upper()})")
    print("=" * 65 + "\n")

    # Step 1: Profiling
    print("🔍 [Step 1/4] Running Single-Pass DuckDB Profiler...")
    profiler = StreamingProfiler(sample_size=15)
    profile = profiler.profile_file(input_path)
    print(f"   • Total Rows Scanned: {profile['total_rows']:,}")
    print(f"   • Columns Analyzed:   {profile['column_count']}")
    print(f"   • Profiling Speed:    {profile['profiling_duration_seconds']}s")
    for col in profile["columns"]:
        issues = ", ".join(col["detected_issues"]) if col["detected_issues"] else "Clean"
        print(f"     - {col['name']} ({col['inferred_type']}): Nulls={col['null_percentage']} | {issues}")

    # Step 2: Cleaner Agent
    print("\n🤖 [Step 2/4] Cleaner Agent Writing Out-of-Core Polars Pipeline & AST Sandboxing...")
    cleaner = CleanerAgent()
    clean_res = cleaner.clean_dataset(profile, output_name=output_parquet_name)

    if not clean_res.get("success"):
        print(f"❌ Data cleaning failed: {clean_res.get('error_message')}")
        sys.exit(1)

    print(f"   • Cleaned Rows Retained: {clean_res['cleaned_rows']:,} ({clean_res['retention_percentage']}%)")
    print(f"   • Execution Runtime:     {clean_res['execution_time_seconds']}s")
    print(f"   • Peak Memory:           {clean_res['peak_memory_mb']} MB (Streaming out-of-core)")
    print(f"   • Output Parquet:        {clean_res['output_parquet']} ({clean_res['file_size_mb']} MB)")
    print("   • Applied Transformations:")
    for change in clean_res.get("changelog", []):
        print(f"     - {change}")

    # Step 3: Modeler Agent
    print("\n📊 [Step 3/4] Modeler Agent Generating DAX Measures & Visual Blueprints...")
    modeler = ModelerAgent()
    blueprint = modeler.model_dataset(
        parquet_path=clean_res["output_parquet"],
        table_name="sales",
        user_intent=user_intent
    )

    print(f"   • Business Domain: {blueprint.get('business_domain')}")
    print(f"   • Generated DAX Measures ({len(blueprint.get('dax_measures', []))}):")
    for m in blueprint.get("dax_measures", []):
        print(f"     - {m.get('name')}: {m.get('dax')}")
    print(f"   • Visual Containers ({len(blueprint.get('visual_blueprints', []))}):")
    for v in blueprint.get("visual_blueprints", []):
        print(f"     - [{v.get('type').upper()}] {v.get('title')}")

    # Step 4: Artifact Generation
    print("\n📄 [Step 4/4] Building Power BI Project (.pbip) & Executive Audit PDF...")
    
    # Audit PDF
    pdf_builder = AuditPDFBuilder()
    pdf_filename = f"{project_name.lower()}_audit_report.pdf"
    pdf_path = pdf_builder.generate_report(clean_res, blueprint, output_filename=pdf_filename)
    print(f"   • Audit PDF Report: {pdf_path}")

    # PBIP Project
    pbip_builder = PBIPBuilder()
    proj_dir = pbip_builder.build_pbip_project(
        parquet_path=clean_res["output_parquet"],
        modeling_blueprint=blueprint,
        project_name=project_name,
        format=model_format
    )
    zip_path = PBIP_OUTPUT_DIR / f"{project_name}.zip"

    print("\n" + "=" * 65)
    print("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
    print(f"📁 Power BI Project: {proj_dir / (project_name + '.pbip')}")
    print(f"📦 Downloadable Zip: {zip_path}")
    print(f"📄 Executive PDF:    {pdf_path}")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(
        description="Autonomous Big Data & Power BI Agent CLI"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=str(RAW_DATA_DIR / "messy_sales_500k.csv"),
        help="Path to the input CSV or Parquet file (defaults to data/raw/messy_sales_500k.csv)"
    )
    parser.add_argument(
        "--prompt", "-p",
        type=str,
        default=None,
        help="Custom user intent or specific metrics/charts desired"
    )
    parser.add_argument(
        "--name", "-n",
        type=str,
        default="Executive_Dashboard",
        help="Project name for PBIP output (default: Executive_Dashboard)"
    )
    parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["tmsl", "tmdl"],
        default="tmsl",
        help="Semantic model format: 'tmsl' (model.bim, default) or 'tmdl' (definition/ folder)"
    )

    args = parser.parse_args()
    run_pipeline(
        input_file=args.input,
        user_intent=args.prompt,
        project_name=args.name,
        model_format=args.format
    )

if __name__ == "__main__":
    main()
