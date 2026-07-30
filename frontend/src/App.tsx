import { useEffect, useState } from "react";
import SearchBar from "./components/SearchBar";
import ControlsBar from "./components/ControlsBar";
import TracePanel from "./components/TracePanel";
import WarningsBanner from "./components/WarningsBanner";
import ResultsList from "./components/ResultsList";
import { fetchVariants, runQuery } from "./api";
import type { QueryResponse, Variant } from "./types";

function useDarkMode(): [boolean, () => void] {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem("gst-rag-theme");
    if (stored) return stored === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("gst-rag-theme", dark ? "dark" : "light");
  }, [dark]);

  return [dark, () => setDark((value) => !value)];
}

export default function App() {
  const [dark, toggleDark] = useDarkMode();
  const [variants, setVariants] = useState<Variant[]>([]);
  const [selectedVariant, setSelectedVariant] = useState("");
  const [asOf, setAsOf] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVariants()
      .then((fetched) => {
        setVariants(fetched);
        const preferred = fetched.find((v) => v.name === "Hybrid + reranker");
        setSelectedVariant((preferred ?? fetched[0])?.name ?? "");
      })
      .catch((err) => setError(String(err)));
  }, []);

  async function handleSearch(question: string) {
    setLoading(true);
    setError(null);
    try {
      const response = await runQuery({
        question,
        variant: selectedVariant || undefined,
        as_of: asOf || undefined,
      });
      setResult(response);
    } catch (err) {
      setError(String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="mx-auto max-w-3xl px-4 py-10">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">GST retrieval</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Retrieval only — citations carry legal status, no generated answer.
            </p>
          </div>
          <button
            type="button"
            onClick={toggleDark}
            className="rounded-full border border-slate-300 px-3 py-1 text-xs dark:border-slate-700"
          >
            {dark ? "light" : "dark"}
          </button>
        </header>

        <SearchBar onSearch={handleSearch} loading={loading} />
        <ControlsBar
          variants={variants}
          selectedVariant={selectedVariant}
          onVariantChange={setSelectedVariant}
          asOf={asOf}
          onAsOfChange={setAsOf}
        />

        {error && (
          <div
            className="mt-4 rounded-lg border-l-4 border-red-500 bg-red-50 px-3 py-2
                       text-sm text-red-800 dark:bg-red-950/40 dark:text-red-300"
          >
            {error}
          </div>
        )}

        {result && (
          <>
            <TracePanel
              question={result.question}
              rewrittenQuery={result.rewritten_query}
              trace={result.trace}
            />
            <WarningsBanner warnings={result.warnings} />
            <ResultsList citations={result.citations} />
          </>
        )}

        {!result && !error && !loading && (
          <p className="mt-8 text-sm text-slate-500 dark:text-slate-400">
            Try a question above, or pick one of the examples.
          </p>
        )}

        <footer className="mt-16 border-t border-slate-200 pt-4 text-xs text-slate-400 dark:border-slate-800">
          Data from cbic.gov.in, redistributed as derived indices. Research project — not legal advice.
        </footer>
      </div>
    </div>
  );
}
