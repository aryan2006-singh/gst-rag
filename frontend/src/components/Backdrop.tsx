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

/** 0 at the top of the page, 1 once the "How it works" section fills the view. */
function anchor() {
  const pipeline = document.getElementById("how");
  if (!pipeline) return 0;
  const end = pipeline.offsetTop - window.innerHeight * 0.15;
  const x = Math.min(Math.max(window.scrollY / Math.max(end, 1), 0), 1);
  return x * x * (3 - 2 * x);
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
          anchor,
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
