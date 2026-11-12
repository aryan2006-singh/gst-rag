import { useRef } from "react";
import { cardProgress, useScrollProgress } from "../hooks/useScrollProgress";
import { Asterisk, ClockIcon, NodesIcon } from "./Icons";

const ITEMS = [
  {
    icon: Asterisk,
    title: "Cited, not generated",
    body: "You get the passage itself, with the document and section it came from. No model paraphrases the law for you.",
    featured: true,
  },
  {
    icon: NodesIcon,
    title: "Status-aware",
    body: "Each passage is tagged in force, amended or superseded, and the results warn you when nothing current matches.",
  },
  {
    icon: ClockIcon,
    title: "Point in time",
    body: "Set an “as of” date to see what the rules said then, which is what matters for an old return or a notice.",
  },
];

/**
 * The section is three screens tall with a pinned (sticky) inner frame, so
 * scrolling through it deals the cards in one at a time: each one rises out
 * of the scene, tilting up in 3D, and lands next to the last.
 */
export default function Principles() {
  const sectionRef = useRef<HTMLElement>(null);
  const cardRefs = useRef<(HTMLElement | null)[]>([]);

  useScrollProgress(sectionRef, (p) => {
    cardRefs.current.forEach((card, i) => {
      if (!card) return;
      const e = cardProgress(p, i, ITEMS.length);
      card.style.opacity = String(Math.min(e * 1.6, 1));
      card.style.transform =
        `perspective(1200px) translate3d(0, ${((1 - e) * 70).toFixed(2)}vh, ${((1 - e) * -240).toFixed(1)}px) ` +
        `rotateX(${((1 - e) * 38).toFixed(2)}deg) rotateZ(${((1 - e) * (i - 1) * 6).toFixed(2)}deg)`;
    });
  });

  return (
    <section ref={sectionRef} id="why" data-scene-window className="relative h-[300vh]">
      <div className="sticky top-0 flex min-h-[100svh] items-center overflow-hidden">
        <div className="container-x py-24">
          <p className="eyebrow text-white/80">Why it's different</p>
          <h2 className="mt-6 max-w-3xl text-[clamp(32px,4.6vw,60px)] font-medium leading-[1.04] tracking-tightest text-white [text-shadow:0_2px_30px_rgba(0,0,0,0.3)]">
            Built for answers you can defend.
          </h2>

          <div className="mt-10 grid gap-4 md:mt-14 md:grid-cols-3 md:gap-6">
            {ITEMS.map(({ icon: Icon, title, body, featured }, i) => (
              <article
                key={title}
                ref={(el) => (cardRefs.current[i] = el)}
                style={{ opacity: 0 }}
                className={
                  "flex flex-col justify-between gap-6 rounded-lg p-6 will-change-transform md:min-h-[340px] lg:p-10 " +
                  (featured
                    ? "bg-white/90 text-black backdrop-blur-xl"
                    : "border border-white/15 bg-black/45 text-white backdrop-blur-2xl")
                }
              >
                <span className="flex items-center justify-between">
                  <Icon className="h-8 w-8 md:h-9 md:w-9" />
                  <span className={"font-mono text-xs " + (featured ? "text-black/50" : "text-white/50")}>0{i + 1}</span>
                </span>
                <div>
                  <h3 className="text-[22px] font-medium tracking-tight md:text-[28px]">{title}</h3>
                  <p className={"mt-3 text-[15px] leading-snug md:mt-5 md:text-[17px] " + (featured ? "text-black/70" : "text-white/75")}>
                    {body}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
