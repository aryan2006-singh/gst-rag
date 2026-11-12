import GlassOrbit from "./GlassOrbit";
import { Asterisk } from "./Icons";

const STEPS = [
  { title: "Read the question", body: "GST shorthand like ITC, RCM or GSTR-3B is expanded so the search sees the words the law uses." },
  { title: "Search two ways", body: "Keyword search (BM25) finds exact terms and section numbers. Dense vectors find passages that mean the same thing." },
  { title: "Fuse and rerank", body: "Both lists are merged, and a reranker can reorder the top passages by how well each one answers the question." },
  { title: "Check legal status", body: "Superseded or out-of-date passages are flagged, and an “as of” date drops anything not yet in force." },
];

export default function Pipeline() {
  return (
    <section
      id="how"
      className="grain relative isolate scroll-mt-0 overflow-hidden
                 bg-[radial-gradient(110%_80%_at_28%_85%,#dfe4e7_0%,#aeb7bd_45%,#76818a_100%)]
                 dark:bg-[radial-gradient(110%_80%_at_28%_85%,#3a4146_0%,#1b1f22_55%,#080909_100%)]"
    >
      <div className="pointer-events-none absolute -left-[30%] bottom-[-20%] w-[90vw] max-w-[820px] opacity-70 lg:-left-[10%] lg:w-[50vw]">
        <GlassOrbit />
      </div>

      <div className="container-x relative grid gap-12 py-24 lg:grid-cols-[1fr_1.35fr] lg:py-36">
        <div>
          <p className="eyebrow text-white/90">How it works</p>
          <h2 className="mt-6 max-w-md text-[clamp(32px,4.6vw,60px)] font-medium leading-[1.04] tracking-tightest text-white">
            Four steps from question to source.
          </h2>
        </div>

        <ol className="space-y-4">
          {STEPS.map((step, i) => (
            <li
              key={step.title}
              className="reveal grid gap-6 rounded-lg bg-black/45 p-7 text-white backdrop-blur-xl sm:grid-cols-[1fr_1.1fr] lg:p-9"
            >
              <div className="flex flex-col justify-between gap-10">
                <span className="flex items-center gap-3 font-mono text-xs text-white/70">
                  <Asterisk className="h-6 w-6 text-white" /> 0{i + 1}
                </span>
                <h3 className="text-[28px] font-medium leading-tight tracking-tight">{step.title}</h3>
              </div>
              <p className="self-end text-[16px] leading-snug text-white/85">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
