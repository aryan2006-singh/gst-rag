interface WarningsBannerProps {
  warnings: string[];
}

export default function WarningsBanner({ warnings }: WarningsBannerProps) {
  if (warnings.length === 0) return null;

  return (
    <div className="mt-4 space-y-2">
      {warnings.map((warning) => {
        const severe = warning.includes("superseded") || warning.includes("no in-force");
        return (
          <div
            key={warning}
            className={
              "rounded-lg border-l-4 px-3 py-2 text-sm " +
              (severe
                ? "border-red-500 bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-300"
                : "border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300")
            }
          >
            {warning}
          </div>
        );
      })}
    </div>
  );
}
