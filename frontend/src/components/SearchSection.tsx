import SearchBar from "./SearchBar";
import ControlsBar from "./ControlsBar";
import TracePanel from "./TracePanel";
import WarningsBanner from "./WarningsBanner";
import ResultsList from "./ResultsList";
import type { QueryResponse, Variant } from "../types";

interface Props {
  variants: Variant[];
  selectedVariant: string;
  onVariantChange: (name: string) => void;
  asOf: string;
  onAsOfChange: (value: string) => void;
  onSearch: (question: string) => void;
  loading: boolean;
  error: string | null;
  result: QueryResponse | null;
}

export default function SearchSection(props: Props) {
  const { result, error, loading } = props;

  return (
    <section id="search" className="scroll-mt-20 border-y border-line bg-paper py-24 lg:py-32">
      <div className="container-x">
        <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <p className="eyebrow reveal text-muted">Search</p>
            <h2 style={{ ["--d" as string]: "80ms" }} className="reveal mt-6 max-w-3xl text-[clamp(32px,4.6vw,60px)] font-medium leading-[1.04] tracking-tightest">
              Ask in plain words. Get the source.
            </h2>
          </div>
        </div>

        <div style={{ ["--d" as string]: "160ms" }} className="reveal mt-12">
          <SearchBar onSearch={props.onSearch} loading={loading} />
          <ControlsBar
            variants={props.variants}
            selectedVariant={props.selectedVariant}
            onVariantChange={props.onVariantChange}
            asOf={props.asOf}
            onAsOfChange={props.onAsOfChange}
          />
        </div>

        {error && (
          <div role="alert" className="mt-8 flex gap-3 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm">
            <span aria-hidden className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-red-500" />
            {error}
          </div>
        )}

        {loading && !result && (
          <div className="mt-10 grid gap-4" aria-busy>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-40 animate-pulse rounded-lg bg-card" />
            ))}
          </div>
        )}

        {result && (
          <div className={"mt-10 grid gap-6 lg:grid-cols-[1fr_340px] " + (loading ? "opacity-50" : "")}>
            <div className="order-2 space-y-4 lg:order-1">
              <WarningsBanner warnings={result.warnings} />
              <ResultsList citations={result.citations} />
            </div>
            <div className="order-1 lg:order-2">
              <div className="lg:sticky lg:top-28">
                <TracePanel
                  question={result.question}
                  rewrittenQuery={result.rewritten_query}
                  trace={result.trace}
                  count={result.citations.length}
                />
              </div>
            </div>
          </div>
        )}

        {!result && !error && !loading && (
          <p className="mt-10 text-muted">Pick an example above to see how results look.</p>
        )}
      </div>
    </section>
  );
}
