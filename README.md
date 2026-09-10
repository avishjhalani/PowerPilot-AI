---
title: PowerPilot AI
emoji: ⚡
colorFrom: amber
colorTo: slate
sdk: gradio
app_file: app.py
pinned: false
---

# ⚡ Autonomous Big Data & Power BI Agent

An enterprise AI data engineering and business intelligence agent that ingests millions of dirty records, stream-cleans out-of-core on your CPU with sub-second performance, dynamically engineers DAX measures, and compiles fully compliant Microsoft Power BI Project (`.pbip`) dashboards and technical audit PDFs.

---

## 🌟 Key Features

1. **⚡ Single-Pass DuckDB SIMD Profiler (`StreamingProfiler`)**
   - Scans 500,000+ rows directly on disk in ~1–2 seconds.
   - Extracts column data types, min/max bounds, approx distinct counts, and null percentages.
   - Automatically detects currency strings, masked nulls (`"N/A"`, `"FREE"`, `"-"`), and date pattern anomalies.

2. **🤖 Self-Healing Polars Streaming Cleaner (`CleanerAgent`)**
   - Leverages Polars out-of-core streaming (`pl.scan_csv().sink_parquet()`).
   - Constant low memory consumption (< 35 MB peak RAM) even on millions of rows.
   - Multi-turn self-healing code generator with an automatic recovery loop.

3. **🛡️ AST Static Security Sandbox (`StreamingExecutor`)**
   - Validates generated Python code before execution.
   - Blocks unauthorized imports (e.g. `os`, `socket`) and dangerous functions (`eval`, `exec`, `compile`).
   - Row-loss guardrail: aborts if data retention drops unexpectedly.

4. **📊 Power BI Modeler Agent (`ModelerAgent`)**
   - Understands business domains and user requirements.
   - Synthesizes 4–6 robust DAX measures (`SUM`, `DIVIDE`, `DISTINCTCOUNT`, `SAMEPERIODLASTYEAR`).
   - Designs an executive visual layout tailored to the dataset.

5. **📁 Production Power BI Project (`.pbip`) Compiler (`PBIPBuilder`)**
   - Generates 100% compliant Microsoft Power BI Project (`.pbip`) folder structures.
   - Fully compatible with modern Power BI Desktop (including 2024–2026 releases).
   - Provides both modern `.SemanticModel` and legacy `.Dataset` support.
   - Includes mandatory `definition.pbism` (`DatasetDefinition` schema) and `model.bim` (TMSL).
   - Optional TMDL format support (`definition/` folder with `definition.pbism` v4.0).
   - Arranges visuals on a 1280x720 canvas using an executive 3-tier grid layout.

6. **📄 Executive Audit PDF Documentation (`AuditPDFBuilder`)**
   - Automatically documents every transformation in a clean, professional PDF audit report.
   - Includes data lineage, KPI benchmarks, runtime performance, and DAX dictionaries.

---

## 📂 Project Structure

```text
Automate powerBi/
├── backend/
│   ├── main.py                             # CLI entrypoint for running pipelines
│   ├── requirements.txt                    # Backend dependencies
│   └── src/
│       ├── config.py                       # Project paths and LLM settings
│       ├── agents/
│       │   ├── cleaner_agent.py            # Polars streaming code generation agent
│       │   └── modeler_agent.py            # DAX measure & visual blueprint agent
│       ├── powerbi/
│       │   ├── pbip_builder.py             # PBIP project folder & zip generator
│       │   ├── report_layout.py            # Visual grid layout calculation engine
│       │   └── tmdl_builder.py             # Tabular Model Definition Language engine
│       ├── reporting/
│       │   └── audit_pdf_builder.py        # Executive PDF audit report builder
│       └── tools/
│           ├── streaming_executor.py       # AST security sandbox & RAM tracker
│           └── streaming_profiler.py       # Single-pass DuckDB profiler
├── data/
│   ├── generate_sample_data.py             # Synthetic dirty enterprise generator
│   ├── raw/
│   │   └── messy_sales_500k.csv            # 500k sample benchmark dataset
│   └── cleaned/
│       └── clean_dataset.parquet           # High-compression Snappy Parquet
├── frontend/                               # React 19 + shadcn/ui + Tailwind v4 Web App
│   ├── src/
│   │   ├── pages/Home.tsx                  # Emergent Minimalist Workspace Interface
│   │   ├── components/ui/                  # shadcn UI components (Card, Button, Badge, etc.)
│   │   ├── lib/api.ts                      # Typed API client for FastAPI
│   │   └── index.css                       # Warm light palette (#F7F4EE), typography & motion
│   ├── package.json                        # Node dependencies
│   └── vite.config.ts                      # Vite configuration with /api proxy
├── server.py                               # FastAPI backend service
├── output/
│   ├── pbip/                               # Generated PBIP dashboard folders & zips
│   └── reports/                            # Generated PDF audit reports
├── .env                                    # API credentials (GROQ_API_KEY)
├── .gitignore                              # Git exclusion rules
└── README.md                               # System documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- Power BI Desktop (for opening generated `.pbip` projects)
- A free Groq API key ([console.groq.com](https://console.groq.com))

### 2. Environment Setup
Clone or navigate to the repository and activate your virtual environment:

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r backend/requirements.txt
```

### 3. API Configuration
Create or edit `.env` in the project root:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
LLM_PROVIDER=groq
MODEL_NAME=openai/gpt-oss-120b
```

---

## 💻 Usage

### Option A: Command Line Interface (CLI)

Run the autonomous pipeline directly from the terminal:

```powershell
# Standard run with 500k benchmark dataset
python backend/main.py

# Custom dataset and specific business intent
python backend/main.py --input "data/raw/my_dirty_data.csv" --prompt "Focus on regional revenue and average order value" --name "Regional_Sales_2026"

# Export with TMDL format
python backend/main.py --format tmdl --name "Executive_TMDL_Report"
```

### Option B: Modern Full-Stack Web Application (React + shadcn + FastAPI)

1. Start the FastAPI backend:
```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

2. Start the React frontend:
```powershell
cd frontend
npm run dev
```

Then open `http://127.0.0.1:5173` in your browser.

---

## 🔍 Fixing the Power BI PBIP Error (`definition.pbism`)

### The Issue
In Power BI Desktop (November 2025 release onwards), opening an incomplete PBIP project resulted in:
```text
Cannot read '...\Executive_Dashboard.Dataset\definition.pbism'. 
DatasetDefinition: Required artifact is missing in '...\Executive_Dashboard.Dataset\definition.pbism'.
```

### The Fix Implemented in This Codebase
1. **Mandatory `definition.pbism`**: Every semantic model folder now includes `definition.pbism` referencing Microsoft's official `DatasetDefinition` schema (`definitionProperties/1.0.0/schema.json`) with `"version": "1.0"`.
2. **Clean Artifact Separation**: Erroneous `definition.pbir` files (which belong exclusively to reports) have been eliminated from dataset directories.
3. **Dual Compatibility (`.SemanticModel` & `.Dataset`)**: PBIPBuilder populates both folder structures so that whether Power BI resolves via modern Fabric naming or legacy conventions, the required files are immediately found.
4. **Self-Contained Packages**: Parquet data files are bundled within the project archive, ensuring models open immediately without broken external references.
