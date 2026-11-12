import { ArrowDot } from "./Icons";

export default function Hero({ motion, onToggleMotion }: { motion: boolean; onToggleMotion: () => void }) {
  return (
    <section id="top" data-scene-window className="relative isolate overflow-hidden">
      <div className="container-x relative grid min-h-[100svh] grid-rows-[1fr_auto] pb-10 pt-28 lg:pt-32">

        <div className="relative max-w-[900px] self-center">
          <p className="eyebrow rise3d mb-6 text-white/90" style={{ animationDelay: "0.05s" }}>CGST rules · circulars · notifications</p>
          <h1 className="text-[clamp(44px,8vw,104px)] font-medium leading-[0.98] tracking-tightest text-white
                         [text-shadow:0_2px_30px_rgba(0,0,0,0.12)]">
            <span className="rise3d block" style={{ animationDelay: "0.15s" }}>GST law,</span>
            <span className="rise3d block" style={{ animationDelay: "0.3s" }}>retrieved with receipts.</span>
          </h1>
          <div className="rise3d mt-10 flex flex-wrap gap-3" style={{ animationDelay: "0.45s" }}>
            <a href="#search" className="btn-light">
              Ask a question <ArrowDot />
            </a>
            <a href="#how" className="btn-ghost">
              How it works
            </a>
          </div>
          {!motion && (
            <button
              type="button"
              onClick={onToggleMotion}
              className="mt-5 inline-flex items-center gap-2 rounded-full bg-black/30 px-4 py-2 text-sm text-white
                         backdrop-blur-md transition hover:bg-black/45"
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
                <path d="M8 5.5v13l10-6.5-10-6.5Z" />
              </svg>
              Motion is off on this device. Turn on 3D motion
            </button>
          )}
        </div>

        <p className="relative mt-16 max-w-md justify-self-end rounded-lg bg-black/25 p-4 text-[17px]
                      leading-snug text-white backdrop-blur-md">
          Every answer is a cited passage from the source, with its legal status attached. Nothing is
          generated, so nothing is made up.
        </p>
      </div>
    </section>
  );
}
