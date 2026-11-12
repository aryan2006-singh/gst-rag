import { ArrowDot } from "./Icons";

export default function Footer() {
  return (
    <footer className="bg-black text-white">
      <div className="container-x py-20">
        <div className="flex flex-col justify-between gap-10 md:flex-row md:items-end">
          <h2 className="max-w-xl text-[clamp(32px,4.6vw,60px)] font-medium leading-[1.04] tracking-tightest">
            Have a GST question?
          </h2>
          <a href="#search" className="btn-light self-start md:self-auto">
            Ask it now <ArrowDot />
          </a>
        </div>

        <div className="mt-20 flex flex-col gap-6 border-t border-white/15 pt-8 text-sm text-white/60 md:flex-row md:justify-between">
          <p>
            Data from cbic.gov.in, redistributed as derived indices. Research project, not legal advice.
          </p>
          <a href="https://github.com/aryan2006-singh/gst-rag" className="text-white/80 underline-offset-4 hover:underline">
            Source on GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}
