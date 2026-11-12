import { Asterisk, ClockIcon, NodesIcon } from "./Icons";

const ITEMS = [
  {
    icon: Asterisk,
    title: "Cited, not generated",
    body: "You get the passage itself, with the document and section it came from. No model paraphrases the law for you.",
    featured: true,
  },
  {
    icon: NodesIcon,
    title: "Status-aware",
    body: "Each passage is tagged in force, amended or superseded, and the results warn you when nothing current matches.",
  },
  {
    icon: ClockIcon,
    title: "Point in time",
    body: "Set an “as of” date to see what the rules said then, which is what matters for an old return or a notice.",
  },
];

export default function Principles() {
  return (
    <section id="why" data-scene-window className="relative scroll-mt-24"><div className="container-x flex min-h-[110vh] flex-col justify-center py-24 lg:py-32">
      <p className="eyebrow reveal text-white/80">Why it's different</p>
      <h2 className="reveal mt-6 max-w-3xl text-[clamp(32px,4.6vw,60px)] font-medium leading-[1.04] tracking-tightest text-white [text-shadow:0_2px_30px_rgba(0,0,0,0.3)]">
        Built for answers you can defend.
      </h2>

      <div className="mt-14 grid gap-6 md:grid-cols-3">
        {ITEMS.map(({ icon: Icon, title, body, featured }) => (
          <article
            key={title}
            data-tilt
            className={
              "reveal flex min-h-[340px] flex-col justify-between rounded-lg p-8 lg:p-10 " +
              (featured
                ? "bg-white/90 text-black backdrop-blur-xl"
                : "border border-white/15 bg-black/45 text-white backdrop-blur-2xl")
            }
          >
            <Icon className="h-9 w-9" />
            <div>
              <h3 className="text-[28px] font-medium tracking-tight">{title}</h3>
              <p className={"mt-5 text-[17px] leading-snug " + (featured ? "text-black/70" : "text-white/75")}>{body}</p>
            </div>
          </article>
        ))}
      </div>
      </div>
    </section>
  );
}
