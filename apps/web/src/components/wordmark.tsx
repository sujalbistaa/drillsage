import { cn } from "@/lib/utils";

/**
 * The DrillSage wordmark: a lime bit-block and the name in widened Archivo, which eases to its
 * normal width when hovered. The block's notch is the bit; the bar under it is the hole.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("headline-hover inline-flex items-center gap-2.5", className)}>
      <svg viewBox="0 0 28 28" className="size-7 shrink-0" aria-hidden>
        <rect width="28" height="28" className="fill-brand" />
        <path d="M9 4v9l5 5 5-5V4" className="fill-none stroke-brand-foreground" strokeWidth="3" />
        <rect x="12.5" y="20" width="3" height="5" className="fill-brand-foreground" />
      </svg>
      <span className="headline text-[1.35rem] tracking-tight uppercase">DrillSage</span>
    </span>
  );
}
