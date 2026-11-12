import { ArrowDot } from "./Icons";

const LINKS = [
  { href: "#why", label: "Why" },
  { href: "#search", label: "Search" },
  { href: "#how", label: "How it works" },
  { href: "#about", label: "About" },
];

interface NavProps {
  dark: boolean;
  onToggleDark: () => void;
  motion: boolean;
  onToggleMotion: () => void;
}

const iconBtn =
  "grid h-11 w-11 place-items-center rounded-md border border-black/10 bg-white/80 text-black backdrop-blur transition hover:bg-white";

export default function Nav({ dark, onToggleDark, motion, onToggleMotion }: NavProps) {
  return (
    <header className="fixed inset-x-0 top-0 z-50">
      <div className="container-x flex items-center justify-between gap-4 py-5">
        <a href="#top" className="text-2xl font-medium tracking-tight text-amber" aria-label="gst-rag home">
          /gst-rag
        </a>

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
          <button
            type="button"
            onClick={onToggleMotion}
            aria-pressed={motion}
            aria-label={motion ? "Turn motion off" : "Turn motion on"}
            title={motion ? "Motion on" : "Motion off"}
            className={iconBtn}
          >
            {motion ? (
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                <ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(-30 12 12)" />
                <ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(30 12 12)" />
                <circle cx="12" cy="12" r="1.6" fill="currentColor" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                <path d="M8 5.5v13l10-6.5-10-6.5Z" />
              </svg>
            )}
          </button>
          <button
            type="button"
            onClick={onToggleDark}
            aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
            className={iconBtn}
          >
            {dark ? (
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" strokeLinecap="round" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
              </svg>
            )}
          </button>
          <a href="#search" className="btn-light hidden sm:inline-flex">
            Ask a question <ArrowDot />
          </a>
        </div>
      </div>
    </header>
  );
}
