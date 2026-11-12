import { ArrowDot } from "./Icons";

const LINKS = [
  { href: "#why", label: "Why" },
  { href: "#search", label: "Search" },
  { href: "#how", label: "How it works" },
  { href: "#about", label: "About" },
];

export default function Nav() {
  return (
    <header className="fixed inset-x-0 top-0 z-50">
      <div className="container-x flex items-center justify-between gap-4 py-5">
        {/* The section sign from the 3D sheet doubles as the logo. The wrapper
            matches the right-hand button's width so the pill stays centred. */}
        <span className="flex md:w-[178px]">
          <a
            href="#top"
            aria-label="GST retrieval, back to top"
            className="grid h-11 w-11 place-items-center rounded-md border border-white/15 bg-white/[0.08]
                       text-[28px] font-medium leading-none text-white backdrop-blur-md transition hover:bg-white/15"
          >
            <span className="-mt-0.5">§</span>
          </a>
        </span>

        <nav
          aria-label="Sections"
          className="hidden items-center gap-1 rounded-full bg-neutral-500/55 px-3 py-2 text-[15px]
                     text-white backdrop-blur-md md:flex"
        >
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-full px-4 py-1.5 transition hover:bg-white/15"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <a href="#search" className="btn-light hidden sm:inline-flex">
            Ask a question <ArrowDot />
          </a>
        </div>
      </div>
    </header>
  );
}
