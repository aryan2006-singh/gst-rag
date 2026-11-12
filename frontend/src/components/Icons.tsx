export function ArrowDot({ invert = false }: { invert?: boolean }) {
  return (
    <span
      aria-hidden
      className={
        "grid h-6 w-6 place-items-center rounded-full " +
        (invert ? "bg-white text-black dark:bg-black dark:text-white" : "bg-black text-white")
      }
    >
      <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.2">
        <path d="M6 3.5 10.5 8 6 12.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function Asterisk({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" stroke="currentColor" strokeWidth="3" aria-hidden>
      <path d="M16 3v26M4.7 9.5l22.6 13M4.7 22.5l22.6-13" strokeLinecap="round" />
    </svg>
  );
}

export function NodesIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden>
      <circle cx="16" cy="6" r="3" />
      <circle cx="6" cy="25" r="3" />
      <circle cx="26" cy="25" r="3" />
      <path d="M16 9v8M16 17l-8 6M16 17l8 6" strokeLinecap="round" />
    </svg>
  );
}

export function ClockIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden>
      <circle cx="16" cy="16" r="12" strokeDasharray="2 3.2" />
      <path d="M16 9v7l5 3" strokeLinecap="round" />
    </svg>
  );
}
