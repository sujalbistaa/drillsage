import { cn } from "@/lib/utils";

/** An eight-point spark: the separator glyph of the DrillSage identity (drawn, not an icon font). */
export function Spark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("inline-block shrink-0", className)} aria-hidden>
      <path
        d="M12 0l2.2 8.1L21 3l-5.1 6.8L24 12l-8.1 2.2L21 21l-6.8-5.1L12 24l-2.2-8.1L3 21l5.1-6.8L0 12l8.1-2.2L3 3l6.8 5.1z"
        fill="currentColor"
      />
    </svg>
  );
}
