export default function WarningsBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;

  return (
    <div className="space-y-2">
      {warnings.map((warning) => {
        const severe =
          warning.includes("superseded") || warning.includes("no in-force") || warning.includes("abstain");
        return (
          <div
            key={warning}
            role="status"
            className="flex gap-3 rounded-lg border border-line bg-paper px-4 py-3 text-sm"
          >
            <span
              aria-hidden
              className={"mt-1.5 h-2 w-2 shrink-0 rounded-full " + (severe ? "bg-red-500" : "bg-amber")}
            />
            <span>{warning}</span>
          </div>
        );
      })}
    </div>
  );
}
