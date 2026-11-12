import type { Variant } from "../types";

interface ControlsBarProps {
  variants: Variant[];
  selectedVariant: string;
  onVariantChange: (name: string) => void;
  asOf: string;
  onAsOfChange: (value: string) => void;
}

const field =
  "rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink focus:border-ink focus:outline-none";

export default function ControlsBar({
  variants,
  selectedVariant,
  onVariantChange,
  asOf,
  onAsOfChange,
}: ControlsBarProps) {
  const active = variants.find((variant) => variant.name === selectedVariant);
  const parts = active
    ? [
        active.use_bm25 && "BM25",
        active.use_dense && "dense",
        active.rerank && "reranker",
        active.query_rewrite && "rewrite",
      ].filter(Boolean)
    : [];

  return (
    <div className="mt-6 flex flex-wrap items-end gap-x-6 gap-y-4 border-t border-line pt-6 text-sm">
      <label className="flex flex-col gap-2">
        <span className="eyebrow text-[10px] text-muted">Retrieval</span>
        <select value={selectedVariant} onChange={(event) => onVariantChange(event.target.value)} className={field}>
          {variants.map((variant) => (
            <option key={variant.name} value={variant.name} disabled={variant.available === false}>
              {variant.name}
              {variant.available === false ? " (not loaded)" : ""}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-2">
        <span className="eyebrow text-[10px] text-muted">As of</span>
        <span className="flex items-center gap-2">
          <input type="date" value={asOf} onChange={(event) => onAsOfChange(event.target.value)} className={field} />
          {asOf && (
            <button type="button" onClick={() => onAsOfChange("")} className="text-xs text-muted underline">
              clear
            </button>
          )}
        </span>
      </label>

      {parts.length > 0 && (
        <span className="pb-2 font-mono text-xs text-muted">{parts.join(" + ")}</span>
      )}
    </div>
  );
}
