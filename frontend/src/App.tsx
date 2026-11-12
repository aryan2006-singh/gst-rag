import { useEffect, useState } from "react";
import Nav from "./components/Nav";
import Hero from "./components/Hero";
import Principles from "./components/Principles";
import SearchSection from "./components/SearchSection";
import Pipeline from "./components/Pipeline";
import Stats from "./components/Stats";
import Footer from "./components/Footer";
import Backdrop from "./components/Backdrop";
import { useTilt } from "./hooks/useTilt";
import { fetchHealth, fetchVariants, runQuery } from "./api";
import { useReveal, useScrollVar } from "./hooks/useReveal";
import type { QueryResponse, Variant } from "./types";

// The site is always dark and always in motion; there are no toggles.
document.documentElement.classList.add("dark");
document.documentElement.classList.remove("reduce-motion");
const motion = true;

export default function App() {
  const [variants, setVariants] = useState<Variant[]>([]);
  const [chunks, setChunks] = useState<number | null>(null);
  const [selectedVariant, setSelectedVariant] = useState("");
  const [asOf, setAsOf] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useScrollVar();
  useTilt(motion);
  useReveal([result]);

  useEffect(() => {
    fetchVariants()
      .then((fetched) => {
        setVariants(fetched);
        const preferred =
          fetched.find((v) => v.default) ?? fetched.find((v) => v.name === "Hybrid + reranker");
        setSelectedVariant((preferred ?? fetched[0])?.name ?? "");
      })
      .catch((err) => setError(String(err)));
    fetchHealth()
      .then((health) => setChunks(health.n_chunks ?? null))
      .catch(() => setChunks(null));
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
    <>
      <a href="#search" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-black">
        Skip to search
      </a>
      <Backdrop motion={motion} />
      <Nav />
      <main>
        <Hero />
        <Principles />
        <SearchSection
          variants={variants}
          selectedVariant={selectedVariant}
          onVariantChange={setSelectedVariant}
          asOf={asOf}
          onAsOfChange={setAsOf}
          onSearch={handleSearch}
          loading={loading}
          error={error}
          result={result}
        />
        <Pipeline />
        <Stats chunks={chunks} variants={variants} />
      </main>
      <Footer />
    </>
  );
}
