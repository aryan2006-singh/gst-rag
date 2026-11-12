import GlassOrbit from "./GlassOrbit";
import { ArrowDot } from "./Icons";

export default function Hero() {
  return (
    <section
      id="top"
      className="grain relative isolate overflow-hidden
                 bg-[radial-gradient(120%_90%_at_72%_45%,#dfe4e7_0%,#b3bcc2_45%,#7f8a91_100%)]
                 dark:bg-[radial-gradient(120%_90%_at_72%_45%,#3a4146_0%,#1b1f22_50%,#080909_100%)]"
    >
      <div className="container-x relative grid min-h-[100svh] grid-rows-[1fr_auto] pb-10 pt-28 lg:pt-32">
        <div className="pointer-events-none absolute right-[-28%] top-[46%] w-[92vw] max-w-[860px]
                        opacity-70 sm:right-[-6%] sm:top-[18%] sm:opacity-90 sm:w-[70vw] lg:right-[2%] lg:top-[12%] lg:w-[54vw]">
          <GlassOrbit />
        </div>

        <div className="relative max-w-[900px] self-center">
          <p className="eyebrow mb-6 text-white/90">CGST rules · circulars · notifications</p>
          <h1 className="text-[clamp(44px,8vw,104px)] font-medium leading-[0.98] tracking-tightest text-white
                         [text-shadow:0_2px_30px_rgba(0,0,0,0.12)]">
            GST law,
            <br />
            retrieved with receipts.
          </h1>
          <div className="mt-10 flex flex-wrap gap-3">
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
