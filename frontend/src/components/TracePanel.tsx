import type { QueryTrace } from "../types";

interface TracePanelProps {
  question: string;
  rewrittenQuery: string;
  trace: QueryTrace;
  count: number;
}

export default function TracePanel({ question, rewrittenQuery, trace, count }: TracePanelProps) {
  const stages = Object.entries(trace.stage_latency_ms);
  const maxMs = Math.max(...stages.map(([, ms]) => ms), 1);

  return (
    <aside className="rounded-lg bg-black p-6 text-white dark:bg-card">
      <p className="eyebrow text-[10px] text-white/60">Trace</p>
      <p className="mt-4 text-[44px] font-medium leading-none tracking-tightest">
        {trace.total_ms.toFixed(0)}
        <span className="ml-1 text-lg text-white/60">ms</span>
      </p>
      <p className="mt-2 text-sm text-white/60">
        {count} passage{count === 1 ? "" : "s"} · {trace.config}
        {trace.cache === "hit" ? " · cached" : ""}
      </p>

      {rewrittenQuery !== question && (
        <p className="mt-5 border-t border-white/15 pt-4 text-sm text-white/80">
          <span className="text-white/50">Rewritten as </span>
          {rewrittenQuery}
        </p>
      )}

      <div className="mt-5 space-y-2.5 border-t border-white/15 pt-5 font-mono text-xs">
        {stages.map(([stage, ms]) => (
          <div key={stage} className="grid grid-cols-[72px_1fr_56px] items-center gap-3">
            <span className="text-white/70">{stage}</span>
            <span className="h-1 rounded-full bg-white/15">
              <span className="block h-1 rounded-full bg-amber" style={{ width: `${(ms / maxMs) * 100}%` }} />
            </span>
            <span className="text-right text-white/70">{ms.toFixed(1)}ms</span>
          </div>
        ))}
        {trace.skipped_stages?.map((stage) => (
          <div key={stage} className="grid grid-cols-[72px_1fr_56px] items-center gap-3 text-white/35">
            <span>{stage}</span>
            <span className="h-px border-t border-dashed border-white/20" />
            <span className="text-right">skipped</span>
          </div>
        ))}
      </div>
    </aside>
  );
}
