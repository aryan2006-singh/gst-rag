import { useEffect, useRef, useState } from "react";
import type { Variant } from "../types";

interface StatsProps {
  chunks: number | null;
  variants: Variant[];
}

/** Counts from 0 up to `to` once it scrolls into view, fast then easing out. */
function CountUp({ to }: { to: number | null }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [seen, setSeen] = useState(false);
  const [value, setValue] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!seen || to === null) return;
    const duration = 1600;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      setValue(Math.round(to * (1 - Math.pow(1 - t, 4))));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [seen, to]);

  return <span ref={ref}>{to === null ? "—" : value.toLocaleString()}</span>;
}

export default function Stats({ chunks, variants }: StatsProps) {
  const items = [
    { value: chunks, label: "Passages indexed" },
    { value: variants.length || null, label: "Retrieval variants" },
    { value: 4, label: "Legal statuses tracked" },
    { value: 0, label: "Generated sentences" },
  ];

  return (
    <section id="about" className="relative scroll-mt-24 bg-paper">
      <div className="container-x py-24 lg:py-32">
      <div className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <p className="eyebrow reveal text-muted">Key stats</p>
          <h2 style={{ ["--d" as string]: "80ms" }} className="reveal mt-6 max-w-md text-[clamp(32px,4.6vw,60px)] font-medium leading-[1.04] tracking-tightest">
            A research tool, honest about what it knows.
          </h2>
          <p style={{ ["--d" as string]: "160ms" }} className="reveal mt-6 max-w-md text-[17px] leading-snug text-muted">
            The live index covers a starter set of CBIC GST rules, circulars, instructions and FAQs. It is a
            research project, not legal advice.
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-4">
          {items.map((item, i) => (
            <div
              key={item.label}
              style={{ ["--d" as string]: `${i * 140}ms` }}
              className="reveal flex min-h-[180px] flex-col justify-between rounded-lg bg-card p-6 lg:p-8">
              <dt className="text-sm text-muted">{item.label}</dt>
              <dd className="text-[clamp(40px,5vw,72px)] font-medium tabular-nums leading-none tracking-tightest">
                <CountUp to={item.value} />
              </dd>
            </div>
          ))}
        </dl>
      </div>
      </div>
    </section>
  );
}
