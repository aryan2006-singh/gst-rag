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

function readTheme(): boolean {
  try {
    const stored = localStorage.getItem("gst-rag-theme");
    if (stored) return stored === "dark";
  } catch {
    // storage unavailable; fall through to the OS preference
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function useDarkMode(): [boolean, () => void] {
  const [dark, setDark] = useState(readTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("gst-rag-theme", dark ? "dark" : "light");
    } catch {
      // ignore
    }
  }, [dark]);

  return [dark, () => setDark((value) => !value)];
}

function readMotion(): boolean {
  try {
    const stored = localStorage.getItem("gst-rag-motion");
    if (stored) return stored === "on";
  } catch {
    // storage unavailable
  }
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Motion follows the OS setting until the visitor flips the switch in the nav. */
function useMotion(): [boolean, () => void] {
  const [motion, setMotion] = useState(() => {
    const value = readMotion();
    document.documentElement.classList.toggle("reduce-motion", !value);
    return value;
  });
  useEffect(() => {
    document.documentElement.classList.toggle("reduce-motion", !motion);
  }, [motion]);
  return [
    motion,
    () =>
      setMotion((value) => {
        try {
          localStorage.setItem("gst-rag-motion", value ? "off" : "on");
        } catch {
          // ignore
        }
        return !value;
      }),
  ];
}

export default function App() {
  const [dark, toggleDark] = useDarkMode();
  const [motion, toggleMotion] = useMotion();
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
      <Backdrop key={motion ? "m" : "s"} motion={motion} />
      <Nav dark={dark} onToggleDark={toggleDark} motion={motion} onToggleMotion={toggleMotion} />
      <main>
        <Hero motion={motion} onToggleMotion={toggleMotion} />
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
