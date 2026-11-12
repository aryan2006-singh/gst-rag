import { useEffect, useRef } from "react";

const TEXT =
  "We don't write answers. We find the passage that already says it, check that it still holds, and show you exactly where it came from.";

/**
 * A big statement over the 3D scene. Words light up one by one as the
 * section scrolls through the viewport, while the camera flies in behind.
 */
export default function Statement() {
  const ref = useRef<HTMLParagraphElement>(null);
  const words = TEXT.split(" ");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const spans = Array.from(el.querySelectorAll<HTMLSpanElement>("span"));
    let frame = 0;
    const update = () => {
      frame = 0;
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight;
      // 0 when the paragraph's top enters at 85% of the viewport, 1 when its bottom reaches 45%.
      const p = Math.min(Math.max((vh * 0.85 - r.top) / (r.height + vh * 0.4), 0), 1);
      const lit = p * spans.length;
      spans.forEach((s, i) => {
        const o = Math.min(Math.max(lit - i, 0), 1);
        s.style.opacity = String(0.14 + o * 0.86);
        s.style.filter = o < 1 ? `blur(${((1 - o) * 4).toFixed(1)}px)` : "";
      });
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <section id="statement" data-scene-window className="relative">
      <div className="container-x flex min-h-[130vh] flex-col justify-center py-32">
        <p className="eyebrow text-white/80">Our approach</p>
        <p
          ref={ref}
          aria-label={TEXT}
          className="mt-8 max-w-5xl text-[clamp(32px,5.4vw,76px)] font-medium leading-[1.06] tracking-tightest text-white
                     [text-shadow:0_2px_40px_rgba(0,0,0,0.35)]"
        >
          {words.map((w, i) => (
            <span key={i} aria-hidden className="transition-[opacity,filter] duration-200">
              {w}{" "}
            </span>
          ))}
        </p>
      </div>
    </section>
  );
}
