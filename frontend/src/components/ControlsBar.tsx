import type { Variant } from "../types";

interface ControlsBarProps {
  variants: Variant[];
  selectedVariant: string;
  onVariantChange: (name: string) => void;
  asOf: string;
  onAsOfChange: (value: string) => void;
}

export default function ControlsBar({
  variants,
  selectedVariant,
  onVariantChange,
  asOf,
  onAsOfChange,
}: ControlsBarProps) {
  const active = variants.find((variant) => variant.name === selectedVariant);

  return (
    <div className="mt-4 flex flex-wrap items-center gap-4 text-sm">
      <label className="flex items-center gap-2">
        <span className="text-slate-500 dark:text-slate-400">Variant</span>
        <select
          value={selectedVariant}
          onChange={(event) => onVariantChange(event.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1
                     dark:border-slate-700 dark:bg-slate-900"
        >
          {variants.map((variant) => (
            <option key={variant.name} value={variant.name} disabled={variant.available === false}>
              {variant.name}
              {variant.available === false ? " (not loaded)" : ""}
            </option>
          ))}
        </select>
      </label>
      {active && (
        <span className="text-xs text-slate-400">
          {[
            active.use_bm25 && "BM25",
            active.use_dense && "dense",
            active.rerank && "reranker",
            active.query_rewrite && "rewrite",
          ]
            .filter(Boolean)
            .join(" + ")}
        </span>
      )}
      <label className="flex items-center gap-2">
        <span className="text-slate-500 dark:text-slate-400">As of</span>
        <input
          type="date"
          value={asOf}
          onChange={(event) => onAsOfChange(event.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1
                     dark:border-slate-700 dark:bg-slate-900"
        />
        {asOf && (
          <button
            type="button"
            onClick={() => onAsOfChange("")}
            className="text-xs text-slate-400 underline"
          >
            clear
          </button>
        )}
      </label>
    </div>
  );
}
