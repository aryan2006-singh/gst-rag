import type { QueryTrace } from "../types";

interface TracePanelProps {
  question: string;
  rewrittenQuery: string;
  trace: QueryTrace;
}

export default function TracePanel({ question, rewrittenQuery, trace }: TracePanelProps) {
  const stages = Object.entries(trace.stage_latency_ms);
  const maxMs = Math.max(...stages.map(([, ms]) => ms), 1);

  return (
    <div
      className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs
                 font-mono text-slate-500 dark:border-slate-800 dark:bg-slate-900/50
                 dark:text-slate-400"
    >
      {rewrittenQuery !== question && (
        <div className="mb-2">
          rewritten: <span className="text-slate-700 dark:text-slate-300">{rewrittenQuery}</span>
        </div>
      )}
      <div className="space-y-1">
        {stages.map(([stage, ms]) => (
          <div key={stage} className="flex items-center gap-2">
            <span className="w-20 shrink-0">{stage}</span>
            <div className="h-1.5 flex-1 rounded-full bg-slate-200 dark:bg-slate-800">
              <div
                className="h-1.5 rounded-full bg-slate-500 dark:bg-slate-400"
                style={{ width: `${(ms / maxMs) * 100}%` }}
              />
            </div>
            <span className="w-16 shrink-0 text-right">{ms.toFixed(1)}ms</span>
          </div>
        ))}
      </div>
      <div className="mt-2">
        total {trace.total_ms.toFixed(1)}ms · {trace.config}
      </div>
    </div>
  );
}
