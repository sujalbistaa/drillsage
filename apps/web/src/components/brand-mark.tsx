import { cn } from "@/lib/utils";

/**
 * DrillSage mark: a well path bending toward a target, above three formation bands.
 * Kept in sync with `src/app/icon.svg`.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("shrink-0", className)} role="img" aria-hidden>
      <rect width="32" height="32" rx="8" className="fill-brand" />
      <path d="M6 21h20M6 25h20" className="stroke-brand-foreground/35" strokeWidth="1.5" />
      <path
        d="M11 5v7c0 5 3 8 9 9"
        fill="none"
        className="stroke-brand-foreground"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx="21.5" cy="21" r="2.6" className="fill-brand-foreground" />
    </svg>
  );
}
