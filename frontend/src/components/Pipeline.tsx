import { useRef } from "react";
import { Asterisk } from "./Icons";
import { cardProgress, useScrollProgress } from "../hooks/useScrollProgress";

const STEPS = [
  { title: "Read the question", body: "GST shorthand like ITC, RCM or GSTR-3B is expanded so the search sees the words the law uses." },
  { title: "Search two ways", body: "Keyword search (BM25) finds exact terms and section numbers. Dense vectors find passages that mean the same thing." },
  { title: "Fuse and rerank", body: "Both lists are merged, and a reranker can reorder the top passages by how well each one answers the question." },
  { title: "Check legal status", body: "Superseded or out-of-date passages are flagged, and an “as of” date drops anything not yet in force." },
];

const PEEK = 18; // px each earlier card shows above the next

/**
 * Pinned for four screens of scroll; the steps are dealt onto a stack one at
 * a time. Each new card rises in from below, tilting up in 3D, and lands
 * slightly lower than the last, while the cards under it sink back.
 */
export default function Pipeline() {
  const sectionRef = useRef<HTMLElement>(null);
  const cardRefs = useRef<(HTMLLIElement | null)[]>([]);
  const counterRef = useRef<HTMLSpanElement>(null);

  useScrollProgress(sectionRef, (p) => {
    const landed = STEPS.map((_, i) => cardProgress(p, i, STEPS.length));
    cardRefs.current.forEach((card, i) => {
      if (!card) return;
      const e = landed[i];
      // How much the cards above this one have landed: push this one back.
      const covered = landed.slice(i + 1).reduce((sum, v) => sum + v, 0);
      card.style.opacity = String(Math.min(e * 1.6, 1) * (1 - covered * 0.12));
      card.style.transform =
        `perspective(1400px) translate3d(0, ${((1 - e) * 80).toFixed(2)}vh, ${(-covered * 40).toFixed(1)}px) ` +
        `rotateX(${((1 - e) * 42).toFixed(2)}deg) scale(${(1 - covered * 0.035).toFixed(3)})`;
    });
    if (counterRef.current) {
      const n = landed.filter((v) => v > 0.5).length;
      counterRef.current.textContent = `0${Math.max(n, 1)} / 0${STEPS.length}`;
    }
  });

  return (
    <section ref={sectionRef} id="how" data-scene-window className="relative h-[420vh]">
      <div className="sticky top-0 flex min-h-[100svh] items-center overflow-hidden">
        <div className="container-x grid py-24 lg:grid-cols-[0.85fr_1.15fr]">
          <div className="lg:col-start-2">
            <p className="eyebrow flex justify-between text-white/90">
              How it works <span ref={counterRef} className="font-mono tracking-normal text-white/60">01 / 04</span>
            </p>
            <h2 className="mt-6 max-w-xl text-[clamp(32px,4.6vw,60px)] font-medium leading-[1.04] tracking-tightest text-white
                           [text-shadow:0_2px_30px_rgba(0,0,0,0.15)]">
              Four steps from question to source.
            </h2>

            <ol className="relative mt-10 md:mt-12" style={{ height: `calc(var(--card-h) + ${PEEK * (STEPS.length - 1)}px)` }}>
              {STEPS.map((step, i) => (
                <li
                  key={step.title}
                  ref={(el) => (cardRefs.current[i] = el)}
                  style={{ top: i * PEEK, opacity: 0, zIndex: i }}
                  className="absolute inset-x-0 grid h-[var(--card-h)] origin-top gap-6 rounded-lg border border-white/10
                             bg-[#0d0f10]/80 p-7 text-white shadow-[0_30px_80px_-20px_rgba(0,0,0,0.6)] backdrop-blur-xl
                             will-change-transform sm:grid-cols-[1fr_1.1fr] lg:p-9"
                >
                  <div className="flex flex-col justify-between gap-6">
                    <span className="flex items-center gap-3 font-mono text-xs text-white/70">
                      <Asterisk className="h-6 w-6 text-white" /> 0{i + 1}
                    </span>
                    <h3 className="text-[26px] font-medium leading-tight tracking-tight md:text-[30px]">{step.title}</h3>
                  </div>
                  <p className="self-end text-[16px] leading-snug text-white/80">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}
