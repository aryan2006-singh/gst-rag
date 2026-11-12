import type { Variant } from "../types";

interface StatsProps {
  chunks: number | null;
  variants: Variant[];
}

export default function Stats({ chunks, variants }: StatsProps) {
  const items = [
    { value: chunks?.toLocaleString() ?? "—", label: "Passages indexed" },
    { value: variants.length ? String(variants.length) : "—", label: "Retrieval variants" },
    { value: "4", label: "Legal statuses tracked" },
    { value: "0", label: "Generated sentences" },
  ];

  return (
    <section id="about" className="container-x scroll-mt-24 py-24 lg:py-32">
      <div className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <p className="eyebrow reveal text-muted">Key stats</p>
          <h2 className="reveal mt-6 max-w-md text-[clamp(32px,4.6vw,60px)] font-medium leading-[1.04] tracking-tightest">
            A research tool, honest about what it knows.
          </h2>
          <p className="reveal mt-6 max-w-md text-[17px] leading-snug text-muted">
            The live index covers a starter set of CBIC GST rules, circulars, instructions and FAQs. It is a
            research project, not legal advice.
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-4">
          {items.map((item) => (
            <div key={item.label} className="reveal flex min-h-[180px] flex-col justify-between rounded-lg bg-card p-6 lg:p-8">
              <dt className="text-sm text-muted">{item.label}</dt>
              <dd className="text-[clamp(40px,5vw,72px)] font-medium leading-none tracking-tightest">{item.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
