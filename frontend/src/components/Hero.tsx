import { ArrowDot } from "./Icons";

export default function Hero() {
  return (
    <section id="top" data-scene-window className="relative isolate overflow-hidden">
      <div className="container-x relative grid min-h-[100svh] grid-rows-[1fr_auto] pb-10 pt-28 lg:pt-32">

        <div className="hero-zoom relative max-w-[900px] self-center">
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
