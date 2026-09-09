import { useState, useEffect } from "react";
import {
  Activity,
  Check,
  Cpu,
  Database,
  FileArchive,
  LoaderCircle,
  Sparkles,
  Terminal,
} from "lucide-react";

interface PipelineProgressProps {
  isPending: boolean;
}

const STEPS = [
  {
    id: 1,
    name: "Data Ingestion & Profiling",
    desc: "DuckDB zero-copy schema & anomaly detection",
    icon: Database,
    minTime: 0,
    maxTime: 2.5,
  },
  {
    id: 2,
    name: "Polars Streaming Cleaner",
    desc: "AST sandboxed code synthesis & out-of-core stream",
    icon: Cpu,
    minTime: 2.5,
    maxTime: 6.5,
  },
  {
    id: 3,
    name: "Semantic Modeling Agent",
    desc: "Groq LLaMA-3.3 synthesizing DAX measures & KPIs",
    icon: Sparkles,
    minTime: 6.5,
    maxTime: 11.0,
  },
  {
    id: 4,
    name: "PBIP & Audit Engine",
    desc: "Compiling Fabric TMDL, report layout & audit PDF",
    icon: FileArchive,
    minTime: 11.0,
    maxTime: 999,
  },
];

const LOG_MESSAGES = [
  { time: 0.0, msg: "Initializing streaming engine · Probing schema & data anomalies with DuckDB..." },
  { time: 1.5, msg: "Profiling column cardinality, null ratios, and data types..." },
  { time: 2.5, msg: "AST Sandbox active (RESTRICTED_EXEC) · Synthesizing Polars streaming code..." },
  { time: 4.5, msg: "Executing out-of-core streaming transforms · Stripping currency & normalizing dates..." },
  { time: 6.5, msg: "Invoking Modeler Agent · Prompting Groq LLaMA-3.3 70B for executive KPIs..." },
  { time: 8.5, msg: "Synthesizing DAX business formulas, format strings, and time intelligence..." },
  { time: 10.5, msg: "Generating Fabric PBIP project structure & report.json visual grid..." },
  { time: 12.5, msg: "Rendering Executive Forensic Audit PDF report and packaging .pbip.zip..." },
  { time: 15.0, msg: "Verifying artifact integrity · Finalizing response payload..." },
];

export function PipelineProgress({ isPending }: PipelineProgressProps) {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (!isPending) {
      setElapsedMs(0);
      return;
    }

    const start = Date.now();
    const timer = setInterval(() => {
      setElapsedMs(Date.now() - start);
    }, 80);

    return () => clearInterval(timer);
  }, [isPending]);

  if (!isPending) return null;

  const seconds = elapsedMs / 1000;

  // Calculate dynamic progress percentage with smooth easing
  let progress = 0;
  if (seconds < 2.5) {
    progress = 5 + (seconds / 2.5) * 25; // 5% -> 30%
  } else if (seconds < 6.5) {
    progress = 30 + ((seconds - 2.5) / 4.0) * 28; // 30% -> 58%
  } else if (seconds < 11.0) {
    progress = 58 + ((seconds - 6.5) / 4.5) * 24; // 58% -> 82%
  } else {
    // Asymptotically approach 96%
    const extra = seconds - 11.0;
    progress = 82 + (1 - Math.exp(-extra / 6)) * 14;
  }
  progress = Math.min(96, Math.max(5, progress));

  // Determine active step
  let activeStepIndex = 0;
  if (seconds >= 11.0) activeStepIndex = 3;
  else if (seconds >= 6.5) activeStepIndex = 2;
  else if (seconds >= 2.5) activeStepIndex = 1;
  else activeStepIndex = 0;

  // Current log message
  const activeLog = [...LOG_MESSAGES].reverse().find((l) => seconds >= l.time)?.msg || LOG_MESSAGES[0].msg;

  // Format elapsed
  const mins = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(1);
  const formattedTime = `${String(mins).padStart(2, "0")}:${parseFloat(secs) < 10 ? "0" : ""}${secs}s`;

  return (
    <div
      className="card-light mt-8 animate-float-in rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-[inset_0_1px_0_rgba(15,23,42,.05),0_14px_30px_rgba(0,0,0,.10)] sm:p-8"
      data-testid="pipeline-progress-card"
    >
      {/* Top Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div className="flex items-center gap-3">
          <div className="relative flex size-10 items-center justify-center rounded-xl bg-amber-400/15 border border-amber-400/30">
            <Activity className="size-5 text-amber-600 animate-pulse" />
            <span className="absolute -top-1 -right-1 size-2.5 rounded-full bg-amber-500 animate-ping" />
          </div>
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.16em] text-amber-700">
              Autonomous Pipeline Active
            </p>
            <h3 className="font-heading text-xl font-semibold text-slate-900 sm:text-2xl">
              Processing Stream...
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 font-mono text-xs text-slate-700">
            <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>ELAPSED: {formattedTime}</span>
          </div>
          <span className="font-mono text-sm font-semibold text-amber-600">
            {Math.round(progress)}%
          </span>
        </div>
      </div>

      {/* Main Progress Bar */}
      <div className="mb-8">
        <div className="relative h-3 w-full overflow-hidden rounded-full border border-slate-200/80 bg-slate-100 p-0.5">
          <div
            className="h-full rounded-full bg-gradient-to-r from-amber-500 via-amber-400 to-amber-500 transition-all duration-150 ease-out relative overflow-hidden"
            style={{ width: `${progress}%` }}
          >
            <div className="absolute inset-0 bg-[linear-gradient(90deg,transparent_0%,rgba(255,255,255,0.45)_50%,transparent_100%)] animate-[shimmer_2s_infinite]" />
          </div>
        </div>
        <div className="mt-2 flex justify-between font-mono text-[11px] text-slate-400">
          <span>Stage {activeStepIndex + 1} of 4: {STEPS[activeStepIndex].name}</span>
          <span>Target: PBIP + TMDL + Audit PDF</span>
        </div>
      </div>

      {/* 4 Interactive Steps Grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 mb-6">
        {STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isDone = idx < activeStepIndex;
          const isActive = idx === activeStepIndex;

          return (
            <div
              key={step.id}
              className={`relative rounded-2xl border p-4 transition-all duration-300 ${
                isActive
                  ? "border-amber-400/60 bg-amber-500/[0.04] shadow-sm ring-1 ring-amber-400/20"
                  : isDone
                  ? "border-emerald-200 bg-emerald-500/[0.03]"
                  : "border-slate-200/80 bg-slate-50/50 opacity-60"
              }`}
            >
              <div className="flex items-center justify-between mb-2.5">
                <div
                  className={`flex size-8 items-center justify-center rounded-lg ${
                    isActive
                      ? "bg-amber-100 text-amber-700"
                      : isDone
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-slate-200/70 text-slate-500"
                  }`}
                >
                  <Icon className="size-4" />
                </div>

                {isDone && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-300/60 bg-emerald-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-800">
                    <Check className="size-3" /> Done
                  </span>
                )}
                {isActive && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-amber-300/80 bg-amber-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-800">
                    <LoaderCircle className="size-3 animate-spin" /> In Progress
                  </span>
                )}
                {!isDone && !isActive && (
                  <span className="rounded-full bg-slate-200/80 px-2 py-0.5 font-mono text-[10px] text-slate-500">
                    Queued
                  </span>
                )}
              </div>

              <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
                0{step.id} // STEP
              </div>
              <p
                className={`text-sm font-semibold leading-tight ${
                  isActive ? "text-amber-950" : isDone ? "text-slate-900" : "text-slate-500"
                }`}
              >
                {step.name}
              </p>
              <p className="mt-1 text-xs text-slate-500 leading-snug">
                {step.desc}
              </p>
            </div>
          );
        })}
      </div>

      {/* Live Console / Telemetry Log Ticker */}
      <div className="rounded-xl border border-white/5 bg-[#090A0F] p-4 text-slate-300 shadow-inner">
        <div className="flex items-center justify-between border-b border-white/10 pb-2 mb-2 font-mono text-[11px] text-slate-400">
          <div className="flex items-center gap-2">
            <Terminal className="size-3.5 text-amber-400" />
            <span className="uppercase tracking-wider">Live Execution Stream</span>
          </div>
          <span className="text-[10px] text-emerald-400 font-medium">STREAMING 127.0.0.1:8000</span>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs text-amber-100/90 min-h-6">
          <span className="text-amber-500 font-bold">&gt;</span>
          <span className="truncate">{activeLog}</span>
          <span className="inline-block size-1.5 bg-amber-400 animate-pulse ml-1" />
        </div>
      </div>
    </div>
  );
}
