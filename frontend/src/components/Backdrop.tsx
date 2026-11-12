import { useEffect, useRef, useState } from "react";
import GlassOrbit from "./GlassOrbit";

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

type Pose = { x: number; y: number; z: number; ry: number };

/**
 * Camera keyframes, pinned to sections: each pose applies when that section's
 * top reaches the top of the viewport, and scroll blends between them. The
 * camera starts far out with the object to the right, flies into it through
 * the statement and the glass cards, then pulls back out for How it works.
 */
const KEYS: { id: string; desktop: Pose; mobile: Pose }[] = [
  { id: "top", desktop: { x: 2.3, y: -0.15, z: 11, ry: 0 }, mobile: { x: 0.6, y: -1.5, z: 14, ry: 0 } },
  { id: "statement", desktop: { x: 1.7, y: 0, z: 6.2, ry: 0.7 }, mobile: { x: 0, y: -0.4, z: 8.5, ry: 0.7 } },
  { id: "why", desktop: { x: 0, y: 0.1, z: 2.9, ry: 1.5 }, mobile: { x: 0, y: 0, z: 3.4, ry: 1.5 } },
  { id: "search", desktop: { x: 0, y: 0.1, z: 2.9, ry: 1.7 }, mobile: { x: 0, y: 0, z: 3.4, ry: 1.7 } },
  { id: "how", desktop: { x: -2.4, y: -0.3, z: 10, ry: 3.0 }, mobile: { x: 0, y: -1.2, z: 13, ry: 3.0 } },
];

const smooth = (x: number) => x * x * (3 - 2 * x);

function pose(mobile: boolean): Pose {
  const pick = (k: (typeof KEYS)[number]) => (mobile ? k.mobile : k.desktop);
  const tops = KEYS.map((k) => document.getElementById(k.id)?.offsetTop ?? 0);
  const y = window.scrollY;
  if (y <= tops[0]) return pick(KEYS[0]);
  for (let i = 0; i < KEYS.length - 1; i++) {
    if (y < tops[i + 1]) {
      const t = smooth((y - tops[i]) / Math.max(tops[i + 1] - tops[i], 1));
      const a = pick(KEYS[i]);
      const b = pick(KEYS[i + 1]);
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, z: a.z + (b.z - a.z) * t, ry: a.ry + (b.ry - a.ry) * t };
    }
  }
  return pick(KEYS[KEYS.length - 1]);
}

/**
 * Fixed layer behind the page: misty gradient, the WebGL scene and film
 * grain. Sections with their own background cover it; the hero and the
 * pipeline section are transparent windows onto it.
 */
export default function Backdrop({ motion }: { motion: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [fallback, setFallback] = useState(false);

  useEffect(() => {
    if (!webglAvailable()) {
      setFallback(true);
      return;
    }
    let disposed = false;
    let handle: { dispose: () => void } | null = null;
    const reducedMotion = !motion;

    import("../three/scene")
      .then(({ createScene }) => {
        if (disposed || !canvasRef.current) return;
        handle = createScene({
          canvas: canvasRef.current,
          reducedMotion,
          pose,
          windows: () => Array.from(document.querySelectorAll<HTMLElement>("[data-scene-window]")),
        });
        canvasRef.current.classList.add("opacity-100");
      })
      .catch(() => setFallback(true));

    return () => {
      disposed = true;
      handle?.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      aria-hidden
      className="grain pointer-events-none fixed inset-0 -z-10
                 bg-[radial-gradient(120%_90%_at_60%_45%,#dfe4e7_0%,#b3bcc2_45%,#7f8a91_100%)]
                 dark:bg-[radial-gradient(120%_90%_at_60%_45%,#3a4146_0%,#1b1f22_50%,#080909_100%)]"
    >
      {fallback ? (
        <div className="absolute right-[-20%] top-[30%] w-[90vw] max-w-[820px] sm:right-[2%] sm:top-[12%] sm:w-[54vw]">
          <GlassOrbit />
        </div>
      ) : (
        <canvas ref={canvasRef} className="absolute inset-0 h-full w-full opacity-0 transition-opacity duration-1000" />
      )}
    </div>
  );
}
