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
        <span aria-hidden className="w-px" />

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
