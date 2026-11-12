import { useEffect } from "react";

/** Tilts any [data-tilt] element toward the pointer, like a card held in hand. */
export function useTilt(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    if (!window.matchMedia("(hover: hover)").matches) return;
    let active: HTMLElement | null = null;

    const reset = (el: HTMLElement) => {
      el.style.setProperty("--rx", "0deg");
      el.style.setProperty("--ry", "0deg");
      el.style.setProperty("--tz", "0px");
    };

    const onMove = (e: PointerEvent) => {
      const el = (e.target as HTMLElement | null)?.closest<HTMLElement>("[data-tilt]") ?? null;
      if (active && active !== el) reset(active);
      active = el;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      el.style.setProperty("--rx", `${(-py * 8).toFixed(2)}deg`);
      el.style.setProperty("--ry", `${(px * 10).toFixed(2)}deg`);
      el.style.setProperty("--tz", "12px");
    };
    const onLeave = () => active && reset(active);

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    return () => {
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, [enabled]);
}
