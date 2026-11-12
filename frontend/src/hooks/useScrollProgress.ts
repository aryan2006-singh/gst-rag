import { RefObject, useEffect } from "react";

/**
 * Calls `onProgress` with 0..1 as a tall section scrolls past a pinned
 * (sticky) frame: 0 when its top reaches the viewport top, 1 when its bottom
 * reaches the viewport bottom.
 */
export function useScrollProgress(ref: RefObject<HTMLElement>, onProgress: (p: number) => void) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const r = el.getBoundingClientRect();
      const span = Math.max(r.height - window.innerHeight, 1);
      onProgress(Math.min(Math.max(-r.top / span, 0), 1));
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

/** Progress of card i of n, given section progress p (with a short hold at the end). */
export function cardProgress(p: number, i: number, n: number) {
  const c = Math.min(Math.max(p * (n + 0.6) - i * 1.05, 0), 1);
  return 1 - Math.pow(1 - c, 3);
}
