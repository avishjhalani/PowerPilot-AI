import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import {
  Activity,
  ArrowUpRight,
  Check,
  ChevronDown,
  Clipboard,
  Code2,
  Compass,
  Cpu,
  Database,
  FileArchive,
  FileCheck2,
  FileDown,
  FileSpreadsheet,
  HardDrive,
  Layers,
  LoaderCircle,
  Orbit,
  Play,
  Settings2,
  Sparkles,
  UploadCloud,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PipelineProgress } from "@/components/PipelineProgress";
import { apiDownload, apiPost } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";

interface PipelineMetric {
  label: string;
  value: string;
  sub_value: string;
}

interface PreviewRow {
  order_id: string;
  customer: string;
  revenue: string;
  order_date: string;
  region: string;
}

interface PipelineMeasure {
  name: string;
  expression: string;
  description: string;
}

interface PipelineResult {
  run_id: string;
  filename: string;
  source_type: string;
  project_name: string;
  model_format: string;
  row_count: number;
  created_at: string;
  status: string;
  engine_message: string;
  metrics: PipelineMetric[];
  changelog: string[];
  preview: PreviewRow[];
  measures: PipelineMeasure[];
}

const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const metricIcons = [Activity, Zap, HardDrive, Database];

export default function Home() {
  const [sourceType, setSourceType] = useState<"sample" | "custom">("sample");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dropzoneOpen, setDropzoneOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [projectName, setProjectName] = useState("PowerPilot_Benchmark");
  const [modelFormat, setModelFormat] = useState("TMDL");

  const runMutation = useMutation<PipelineResult, Error, FormData>({
    mutationFn: (body) => apiPost<PipelineResult>("/pipeline/run", body),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["pipeline"] });
      toast.success("Pipeline complete", { description: `${result.project_name} is ready to inspect.` });
    },
    onError: () => toast.error("Pipeline could not run", { description: "Check the file type and try again." }),
  });

  const result = runMutation.data;

  const acceptFile = (file: File) => {
    const isSupported = /\.(csv|parquet)$/i.test(file.name);
    if (!isSupported) {
      toast.error("Unsupported file", { description: "Choose a .csv or .parquet file." });
      return;
    }
    setSelectedFile(file);
    setSourceType("custom");
    setDropzoneOpen(true);
    toast.success("File attached", { description: `${file.name} is ready to stream.` });
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) acceptFile(file);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) acceptFile(file);
  };

  const handleRun = () => {
    const body = new FormData();
    body.append("source_type", sourceType);
    body.append("prompt", prompt);
    body.append("project_name", projectName);
    body.append("model_format", modelFormat);
    if (selectedFile) body.append("file", selectedFile);
    runMutation.mutate(body);
  };

  const removeFile = () => {
    setSelectedFile(null);
    setSourceType("sample");
    toast.message("Back to benchmark data");
  };

  const handleDownload = async (artifactType: string, filename: string, label: string) => {
    if (!result) return;
    try {
      await apiDownload(`/pipeline/artifacts/${result.run_id}/${artifactType}`, filename);
      toast.success(`${label} downloaded`);
    } catch {
      toast.error("Download failed", { description: "The generated artifact is no longer available." });
    }
  };

  return (
    <main className="min-h-svh overflow-x-hidden bg-[#F7F4EE] text-slate-900 relative">
      <BackgroundArtifacts />
      <div className="relative mx-auto max-w-5xl px-6 py-14 sm:px-8 sm:py-20 lg:px-10 z-10">
        <header className="mx-auto mb-12 max-w-3xl text-center sm:mb-16" data-testid="hero-header">
          <div className="mx-auto mb-6 flex size-16 items-center justify-center rounded-2xl border border-amber-400/30 bg-amber-400/10 text-amber-500 shadow-[inset_0_1px_0_rgba(255,255,255,.08)]" data-testid="brand-logo-mark">
            <Orbit className="size-8" strokeWidth={1.5} />
          </div>
          <p className="mb-3 font-mono text-xs uppercase tracking-[0.26em] text-amber-600 sm:text-sm" data-testid="brand-kicker">Autonomous data engineering</p>
          <h1 className="font-heading text-5xl font-bold tracking-[-0.05em] text-slate-900 sm:text-6xl lg:text-7xl" data-testid="brand-title">PowerPilot <span className="text-amber-500">AI</span></h1>
          <p className="mt-5 text-base leading-7 text-slate-500 sm:text-lg" data-testid="hero-subtitle">What data would you like to transform into Power BI today?</p>
        </header>

        <section className="card-light relative rounded-[2.25rem] border border-slate-200 bg-white p-4 shadow-[0_20px_50px_rgba(0,0,0,0.14)] backdrop-blur-xl sm:p-6" data-testid="pipeline-workspace">
          <div className="card-light mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3.5 font-mono text-xs uppercase tracking-[0.12em] text-slate-500 sm:p-4 sm:text-sm" data-testid="telemetry-bar">
            <span className="flex items-center gap-2.5" data-testid="engine-status"><span className="status-dot" /> Polars Out-of-Core Streaming <span className="text-slate-400">v0.21.0</span></span>
            <span className="flex items-center gap-2.5" data-testid="export-target"><FileCheck2 className="size-4 text-sky-600" /> Power BI Desktop .pbip <span className="text-slate-400">/ Semantic Model v2</span></span>
          </div>

          <div className="card-light relative rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-[inset_0_1px_0_rgba(15,23,42,.05),0_14px_30px_rgba(0,0,0,.10)] sm:p-10" data-testid="workspace-inner-card">
            <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="mb-2.5 font-mono text-xs uppercase tracking-[0.2em] text-slate-500" data-testid="input-label">Input stream</p>
                <div className="flex flex-wrap items-center gap-3" data-testid="active-data-pill">
                  <Badge className="h-auto rounded-full border border-amber-400/30 bg-amber-400/10 px-4 py-2 font-mono text-xs text-amber-800 hover:bg-amber-400/15 sm:text-sm">
                    <FileSpreadsheet className="size-4 text-amber-600" />
                    {selectedFile ? `${selectedFile.name} · ${formatBytes(selectedFile.size)} · Ready to stream` : "messy_sales_500k.csv · 500K rows · Ready to stream"}
                  </Badge>
                  <button type="button" onClick={() => setDropzoneOpen(true)} className="inline-flex items-center gap-1 text-sm text-slate-500 transition-colors hover:text-amber-600" data-testid="change-file-button">Change <ArrowUpRight className="size-3.5" /></button>
                  {selectedFile && <button type="button" onClick={removeFile} className="inline-flex items-center gap-1 text-sm text-slate-500 transition-colors hover:text-rose-600" data-testid="remove-file-button">Remove <X className="size-3.5" /></button>}
                </div>
              </div>
              <div className="hidden items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 font-mono text-xs uppercase tracking-[0.15em] text-emerald-700 sm:flex" data-testid="ready-status"><Check className="size-4" /> ready</div>
            </div>

            <Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Describe what insights, charts, or measures you want in Power BI..." className="min-h-44 resize-none rounded-none border-0 bg-transparent px-0 py-4 text-lg leading-8 text-slate-900 shadow-none placeholder:text-slate-400 focus-visible:ring-0 sm:min-h-48 sm:text-xl" data-testid="pipeline-prompt-textarea" />

            {dropzoneOpen && (
              <div className="card-light mb-6 animate-float-in rounded-2xl border-2 border-dashed border-slate-300 bg-white p-8 text-center transition-colors hover:border-amber-400" onDragOver={(event) => event.preventDefault()} onDrop={handleDrop} data-testid="custom-file-dropzone">
                <input id="custom-file-input" type="file" accept=".csv,.parquet" onChange={handleFileChange} className="sr-only" data-testid="custom-file-input" />
                <UploadCloud className="mx-auto mb-3 size-9 text-slate-500" />
                <p className="text-base font-medium text-slate-800" data-testid="dropzone-title">Drop a CSV or Parquet file here</p>
                <p className="mt-1 text-sm text-slate-500" data-testid="dropzone-caption">Your file stays in the local demo stream · up to 2 GB</p>
                <label htmlFor="custom-file-input" className="mt-5 inline-flex cursor-pointer items-center rounded-xl border border-slate-300 bg-slate-100 px-4 py-2.5 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-200" data-testid="browse-files-label">Browse files</label>
              </div>
            )}

            <div className="mt-4 flex flex-col gap-3 border-t border-slate-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap gap-2.5">
                <Button type="button" variant="secondary" size="sm" className="h-11 border border-[#353B55] bg-[#22273A] px-4 text-xs font-medium !text-white hover:bg-[#2C324A] hover:!text-white sm:text-sm" onClick={() => { setSourceType("sample"); setSelectedFile(null); setDropzoneOpen(false); toast.success("Benchmark loaded", { description: "500,000 messy sales rows are ready." }); }} data-testid="use-sample-button"><Zap className="size-4 text-amber-300" /> Use Sample Benchmark Data</Button>
                <Button type="button" variant="ghost" size="sm" className="h-11 px-4 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 sm:text-sm" onClick={() => setDropzoneOpen((open) => !open)} data-testid="custom-file-button"><UploadCloud className="size-4" /> Custom File</Button>
              </div>
              <Button type="button" size="lg" className="h-12 rounded-xl border border-slate-300 bg-white px-6 text-sm font-semibold text-slate-950 shadow-sm transition-transform hover:bg-slate-50 active:scale-[.98] sm:text-base" onClick={handleRun} disabled={runMutation.isPending} data-testid="run-pipeline-button">
                {runMutation.isPending ? <LoaderCircle className="size-4 animate-spin text-amber-600" /> : <Play className="size-4 fill-current" />}
                {runMutation.isPending ? "Streaming Pipeline..." : "Run Pipeline"}
                {!runMutation.isPending && <ArrowUpRight className="size-4" />}
              </Button>
            </div>
          </div>
        </section>

        {/* Real-time Interactive Pipeline Progress Tracker */}
        <PipelineProgress isPending={runMutation.isPending} />

        <p className="mx-auto mt-5 max-w-3xl text-center font-mono text-xs leading-6 tracking-tight text-slate-500 sm:text-sm" data-testid="pipeline-disclaimer">Autonomous streaming pipeline with AST sandboxing <span className="text-slate-400">•</span> Compiles Fabric-ready .pbip models, DAX measures, and audit reports.</p>

        <details className="card-light group mt-9 rounded-2xl border border-slate-200 bg-white" data-testid="advanced-settings">
          <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4 text-sm font-medium text-slate-600 transition-colors hover:text-slate-900 sm:text-base" data-testid="advanced-settings-summary">
            <span className="flex items-center gap-2.5"><Settings2 className="size-4 text-slate-500" /> Advanced engine &amp; export settings</span><ChevronDown className="size-4 transition-transform duration-300 group-open:rotate-180" />
          </summary>
          <div className="grid gap-4 border-t border-slate-200 p-5 sm:grid-cols-[1fr_200px]">
            <label className="space-y-2 text-xs font-medium text-slate-500 sm:text-sm" data-testid="project-name-field"><span>Project name</span><Input value={projectName} onChange={(event) => setProjectName(event.target.value)} className="h-10 border-slate-300 bg-white text-sm text-slate-900 placeholder:text-slate-400" data-testid="project-name-input" /></label>
            <label className="space-y-2 text-xs font-medium text-slate-500 sm:text-sm" data-testid="model-format-field"><span>Semantic model format</span><select value={modelFormat} onChange={(event) => setModelFormat(event.target.value)} className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-amber-400/50" data-testid="model-format-select"><option value="TMDL">TMDL</option><option value="TMSL">TMSL</option></select></label>
          </div>
        </details>

        {runMutation.isError && <div className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/5 px-4 py-3 text-sm text-rose-600" role="alert" data-testid="pipeline-error-message">The engine returned an error. Please check your file and run again.</div>}

        {result && (
          <section className="mt-16 animate-float-in space-y-10" data-testid="pipeline-results">
            <div className="flex flex-col gap-3 border-b border-slate-200 pb-6 sm:flex-row sm:items-end sm:justify-between">
              <div><p className="mb-2 font-mono text-xs uppercase tracking-[0.2em] text-emerald-600 sm:text-sm" data-testid="results-kicker">Pipeline completed</p><h2 className="font-heading text-3xl font-semibold tracking-[-0.04em] text-slate-900 sm:text-4xl" data-testid="results-title">Your model is ready to inspect.</h2></div>
              <div className="flex items-center gap-2.5 font-mono text-xs text-slate-500 sm:text-sm" data-testid="results-run-meta"><span className="status-dot" /> {result.filename} <span className="text-slate-400">·</span> {result.model_format}</div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="metric-scorecards">
              {result.metrics.map((metric, index) => { const Icon = metricIcons[index]; return <div key={metric.label} className="card-light rounded-2xl border border-slate-200 bg-white p-5 shadow-[inset_0_1px_0_rgba(15,23,42,.04)]" data-testid={`result-metric-${index}`}><div className="mb-5 flex items-center justify-between"><span className="font-mono text-xs uppercase tracking-[0.12em] text-slate-500" data-testid={`metric-label-${index}`}>{metric.label}</span><Icon className="size-5 text-amber-500" /></div><p className="font-heading text-3xl font-semibold tracking-tight text-slate-900" data-testid={`metric-value-${index}`}>{metric.value}</p><p className="mt-1.5 text-xs text-slate-500 sm:text-sm" data-testid={`metric-sub-value-${index}`}>{metric.sub_value}</p></div>; })}
            </div>

            <div className="card-light rounded-2xl border border-slate-200 bg-white p-6 sm:p-7" data-testid="changelog-panel">
              <div className="mb-5 flex items-center gap-2.5"><FileCheck2 className="size-5 text-emerald-500" /><h3 className="font-heading text-xl font-semibold text-slate-900" data-testid="changelog-title">Transformation changelog</h3></div>
              <div className="flex flex-wrap gap-2.5">{result.changelog.map((item) => <span key={item} className="rounded-full border border-sky-200 bg-sky-50 px-3.5 py-2 font-mono text-xs text-sky-700" data-testid="changelog-tag">{item}</span>)}</div>
            </div>

            <div className="grid gap-6 lg:grid-cols-[1.35fr_.9fr]">
              <div className="card-light overflow-hidden rounded-2xl border border-slate-200 bg-white" data-testid="data-preview-panel">
                <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5"><div><h3 className="font-heading text-xl font-semibold text-slate-900" data-testid="data-preview-title">Cleaned data preview</h3><p className="mt-1 text-sm text-slate-500" data-testid="data-preview-caption">Top 5 records · normalized schema</p></div><Code2 className="size-5 text-slate-500" /></div>
                <div className="overflow-x-auto"><table className="w-full text-left font-mono text-xs" data-testid="cleaned-data-table"><thead className="bg-slate-50 text-slate-500"><tr><th className="px-6 py-3.5 font-medium">ORDER_ID</th><th className="px-4 py-3.5 font-medium">CUSTOMER</th><th className="px-4 py-3.5 font-medium">REVENUE</th><th className="px-4 py-3.5 font-medium">DATE</th><th className="px-6 py-3.5 font-medium">REGION</th></tr></thead><tbody className="divide-y divide-slate-200 text-slate-700">{result.preview.map((row) => <tr key={row.order_id} className="transition-colors hover:bg-slate-50" data-testid={`preview-row-${row.order_id}`}><td className="px-6 py-3.5 text-amber-700">{row.order_id}</td><td className="whitespace-nowrap px-4 py-3.5">{row.customer}</td><td className="px-4 py-3.5">{row.revenue}</td><td className="whitespace-nowrap px-4 py-3.5">{row.order_date}</td><td className="px-6 py-3.5">{row.region}</td></tr>)}</tbody></table></div>
              </div>

              <div className="card-light rounded-2xl border border-slate-200 bg-white p-6" data-testid="artifact-panel"><div className="mb-5 flex items-center gap-2.5"><FileArchive className="size-5 text-amber-500" /><div><h3 className="font-heading text-xl font-semibold text-slate-900" data-testid="artifact-title">Artifact center</h3><p className="text-sm text-slate-500" data-testid="artifact-caption">Generated for {result.project_name}</p></div></div><div className="space-y-3"><Button type="button" className="h-11 w-full justify-between bg-amber-500 px-4 text-sm font-semibold text-slate-950 hover:bg-amber-400" onClick={() => handleDownload("project", `${result.project_name}.zip`, "Power BI project")} data-testid="download-project-button">Power BI Project (.zip) <FileDown className="size-4" /></Button><Button type="button" variant="secondary" className="h-11 w-full justify-between border border-slate-300 bg-slate-100 px-4 text-sm text-slate-800 hover:bg-slate-200" onClick={() => handleDownload("audit", `${result.project_name}_audit.pdf`, "Audit report")} data-testid="download-audit-button">Audit Report (PDF) <FileDown className="size-4" /></Button><Button type="button" variant="ghost" className="h-11 w-full justify-between px-4 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900" onClick={() => handleDownload("parquet", `${result.project_name}_cleaned.parquet`, "Cleaned Parquet")} data-testid="download-parquet-button">Cleaned Parquet <FileDown className="size-4" /></Button></div><p className="mt-5 font-mono text-xs leading-6 text-slate-500" data-testid="artifact-note">Artifacts include the semantic model definition, audit metadata, and cleaned columnar output.</p></div>
            </div>
          </section>
        )}

        <footer className="mt-20 flex flex-col items-center justify-between gap-4 border-t border-slate-200 pt-6 font-mono text-xs uppercase tracking-[0.14em] text-slate-500 sm:flex-row" data-testid="page-footer"><span data-testid="footer-brand">PowerPilot AI / Control room</span><span className="flex items-center gap-2" data-testid="footer-security"><ShieldIcon /> Local-first demo workspace</span></footer>
      </div>
    </main>
  );
}

function ShieldIcon() {
  return <span className="inline-block size-1.5 rounded-full bg-emerald-400/60" aria-hidden="true" />;
}

function BackgroundArtifacts() {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden select-none z-0" aria-hidden="true">
      {/* 1. Engineering Grid Wash */}
      <div className="absolute inset-0 grid-wash opacity-80" />

      {/* 2. Soft Ambient Radial Glows */}
      <div className="absolute left-1/2 -top-40 -translate-x-1/2 h-[520px] w-[900px] rounded-full bg-gradient-to-b from-amber-400/12 via-amber-200/4 to-transparent blur-3xl" />
      <div className="absolute -left-32 top-1/4 h-[440px] w-[440px] rounded-full bg-gradient-to-tr from-sky-400/8 via-sky-200/3 to-transparent blur-3xl" />
      <div className="absolute -right-32 top-1/2 h-[460px] w-[460px] rounded-full bg-gradient-to-tl from-amber-400/8 via-amber-200/3 to-transparent blur-3xl" />

      {/* 3. Architectural Vertical Guide Lines */}
      <div className="absolute inset-y-0 left-8 hidden 2xl:block w-px bg-slate-900/[0.04]">
        <div className="sticky top-12 -left-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest text-slate-400/60 -rotate-90 origin-left">
          <span>+ 01 // SYS_AXIS_L</span>
        </div>
        <div className="sticky top-1/2 -left-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest text-slate-400/60 -rotate-90 origin-left">
          <span>+ STREAM_PORT_01</span>
        </div>
      </div>
      <div className="absolute inset-y-0 right-8 hidden 2xl:block w-px bg-slate-900/[0.04]">
        <div className="sticky top-12 -right-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest text-slate-400/60 rotate-90 origin-right">
          <span>+ 02 // SYS_AXIS_R</span>
        </div>
        <div className="sticky top-1/2 -right-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest text-slate-400/60 rotate-90 origin-right">
          <span>+ TMDL_PORT_02</span>
        </div>
      </div>

      {/* 4. Top Technical Telemetry Stamps */}
      <div className="absolute top-6 left-10 hidden lg:flex items-center gap-2 font-mono text-[10px] text-slate-400/70 tracking-widest uppercase">
        <span className="text-amber-500 font-semibold">+</span>
        <span>NODE: PP-AI-01</span>
        <span className="text-slate-300">/</span>
        <span>LATENCY: 0.38ms</span>
      </div>
      <div className="absolute top-6 right-10 hidden lg:flex items-center gap-2 font-mono text-[10px] text-slate-400/70 tracking-widest uppercase">
        <span>RUNTIME: POLARS_STREAMING</span>
        <span className="text-emerald-500 font-bold">●</span>
        <span>ACTIVE</span>
      </div>

      {/* 5. Floating Side Holographic Artifacts (Left & Right Gutters on widescreen) */}
      {/* Left Gutter: DuckDB Engine Card */}
      <div className="absolute left-6 xl:left-10 2xl:left-14 top-48 hidden xl:block w-52 rounded-2xl border border-slate-200/80 bg-white/75 p-3.5 shadow-sm backdrop-blur-md animate-float-drift">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Database className="size-3.5 text-amber-500" />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-700">DuckDB Core</span>
          </div>
          <span className="font-mono text-[9px] rounded-md bg-amber-50 border border-amber-200/60 px-1.5 py-0.5 text-amber-700 font-medium">0.04s</span>
        </div>
        <p className="font-mono text-[10px] text-slate-500">Zero-copy arrow profiling</p>
        <div className="mt-2.5 flex items-center justify-between font-mono text-[9px] text-slate-400 border-t border-slate-100 pt-2">
          <span>SCAN: 500K ROWS</span>
          <span className="text-emerald-600 font-medium">PASS</span>
        </div>
      </div>

      {/* Left Gutter: AST Sandbox Card */}
      <div className="absolute left-8 xl:left-12 2xl:left-18 top-[440px] hidden xl:block w-48 rounded-2xl border border-slate-200/70 bg-white/65 p-3 shadow-sm backdrop-blur-md animate-float-drift-reverse">
        <div className="flex items-center gap-1.5 mb-1">
          <Cpu className="size-3.5 text-sky-600" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-700">AST Sandbox</span>
        </div>
        <p className="font-mono text-[10px] text-slate-500">Bytecode isolation tree</p>
        <div className="mt-2 flex items-center gap-1.5 font-mono text-[9px] text-emerald-600">
          <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" /> RESTRICTED_EXEC
        </div>
      </div>

      {/* Left Gutter: Decorative Dot Matrix */}
      <div className="absolute left-10 xl:left-14 top-[640px] hidden 2xl:grid grid-cols-4 gap-2.5 opacity-35">
        {Array.from({ length: 16 }).map((_, i) => (
          <span key={i} className="size-1 rounded-full bg-slate-400" />
        ))}
      </div>

      {/* Right Gutter: Power BI Fabric / TMDL Card */}
      <div className="absolute right-6 xl:right-10 2xl:right-14 top-52 hidden xl:block w-52 rounded-2xl border border-slate-200/80 bg-white/75 p-3.5 shadow-sm backdrop-blur-md animate-float-drift-reverse">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <FileArchive className="size-3.5 text-amber-500" />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-700">Fabric PBIP</span>
          </div>
          <span className="font-mono text-[9px] rounded-md bg-sky-50 border border-sky-200/60 px-1.5 py-0.5 text-sky-700 font-medium">v2.0</span>
        </div>
        <p className="font-mono text-[10px] text-slate-500">TMDL semantic definitions</p>
        <div className="mt-2.5 flex items-center justify-between font-mono text-[9px] text-slate-400 border-t border-slate-100 pt-2">
          <span>DESKTOP 2026</span>
          <span className="text-sky-600 font-medium">READY</span>
        </div>
      </div>

      {/* Right Gutter: Groq DAX Synthesizer Card */}
      <div className="absolute right-8 xl:right-12 2xl:right-18 top-[450px] hidden xl:block w-48 rounded-2xl border border-slate-200/70 bg-white/65 p-3 shadow-sm backdrop-blur-md animate-float-drift">
        <div className="flex items-center gap-1.5 mb-1">
          <Sparkles className="size-3.5 text-amber-500" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-700">DAX Agent</span>
        </div>
        <p className="font-mono text-[10px] text-slate-500">Groq LLaMA-3.3 70B</p>
        <div className="mt-2 flex items-center gap-1.5 font-mono text-[9px] text-amber-700">
          <span>SYNTHESIZER: ACTIVE</span>
        </div>
      </div>

      {/* Right Gutter: Decorative Dot Matrix */}
      <div className="absolute right-10 xl:right-14 top-[650px] hidden 2xl:grid grid-cols-4 gap-2.5 opacity-35">
        {Array.from({ length: 16 }).map((_, i) => (
          <span key={i} className="size-1 rounded-full bg-slate-400" />
        ))}
      </div>
    </div>
  );
}