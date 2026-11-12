/**
 * The hero object: three iridescent glass rings orbiting a stack of frosted
 * legal sheets, with small technical labels pinned to it. Pure CSS 3D, no
 * images; it tilts with scroll through the --scroll variable.
 */
const TAGS = [
  { label: "§ 16(4)", x: "8%", y: "22%" },
  { label: "RULE 36", x: "74%", y: "14%" },
  { label: "NOTIF. 11/2017", x: "70%", y: "76%" },
  { label: "CIRC. 183", x: "4%", y: "70%" },
];

export default function GlassOrbit() {
  return (
    <div className="orbit relative aspect-square w-full" aria-hidden>
      <div className="orbit-spin absolute inset-0">
        <div className="ring ring-a" style={{ ["--w" as string]: "44px" }} />
        <div className="ring ring-b" style={{ ["--w" as string]: "30px", inset: "7%" }} />
        <div className="ring ring-c" style={{ ["--w" as string]: "24px", inset: "14%" }} />
      </div>

      <div className="float absolute inset-0">
        <div className="sheet" style={{ left: "34%", top: "26%", width: "34%", height: "44%", transform: "rotate(-9deg)" }} />
        <div className="sheet" style={{ left: "31%", top: "29%", width: "34%", height: "44%", transform: "rotate(4deg)" }} />
        <div
          className="sheet flex flex-col justify-between p-[6%] text-black/70"
          style={{ left: "33%", top: "28%", width: "34%", height: "44%" }}
        >
          <span className="font-mono text-[clamp(8px,1vw,12px)] tracking-widest">CGST · 2017</span>
          <span className="text-[clamp(48px,9vw,120px)] font-medium leading-none text-black/80">§</span>
          <span className="space-y-1.5">
            <span className="block h-1 w-full rounded bg-black/15" />
            <span className="block h-1 w-4/5 rounded bg-black/15" />
            <span className="block h-1 w-3/5 rounded bg-black/15" />
          </span>
        </div>
      </div>

      {TAGS.map((tag) => (
        <span
          key={tag.label}
          className="absolute hidden border border-white/70 px-1.5 py-0.5 font-mono text-[10px]
                     tracking-widest text-white/90 sm:block"
          style={{ left: tag.x, top: tag.y }}
        >
          {tag.label}
        </span>
      ))}
    </div>
  );
}
