import { hazardMeta, SEVERITY_LABELS } from "@/lib/hazards";
import { cn } from "@/lib/utils";

/** Two-letter hazard stamp in the hazard's colour (LC, WC, SP…). */
export function HazardCode({ hazard, className }: { hazard: string; className?: string }) {
  const meta = hazardMeta(hazard);
  return (
    <span
      className={cn(
        "label inline-flex h-6 min-w-8 items-center justify-center px-1 font-bold text-[#0a0a0b]",
        className,
      )}
      style={{ background: meta.color }}
      title={meta.label}
    >
      {meta.code}
    </span>
  );
}

export function HazardChip({ hazard, className }: { hazard: string; className?: string }) {
  const meta = hazardMeta(hazard);
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <HazardCode hazard={hazard} />
      <span className="label">{meta.label}</span>
    </span>
  );
}

/** Severity 1–4 as filled blocks. */
export function SeverityPips({ severity }: { severity: number }) {
  return (
    <span
      className="inline-flex items-center gap-0.5"
      role="img"
      aria-label={`Severity ${severity} of 4: ${SEVERITY_LABELS[severity] ?? ""}`}
      title={`Severity ${severity}/4 · ${SEVERITY_LABELS[severity] ?? ""}`}
    >
      {[1, 2, 3, 4].map((level) => (
        <span
          key={level}
          className={cn(
            "h-3 w-1.5 border border-foreground/60",
            level <= severity && (severity >= 3 ? "border-danger bg-danger" : "bg-foreground"),
          )}
        />
      ))}
    </span>
  );
}
