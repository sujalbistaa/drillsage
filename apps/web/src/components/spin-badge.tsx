/** A rotating circular-text sticker around a big number. Pure SVG; stops for reduced motion. */
export function SpinBadge({ value, ring }: { value: string; ring: string }) {
  return (
    <div className="relative size-44 shrink-0 md:size-56">
      <svg
        viewBox="0 0 200 200"
        className="absolute inset-0 animate-[spin_22s_linear_infinite]"
        aria-hidden
      >
        <defs>
          <path id="ring" d="M100,100 m-78,0 a78,78 0 1,1 156,0 a78,78 0 1,1 -156,0" />
        </defs>
        <circle cx="100" cy="100" r="98" fill="var(--brand)" />
        <text
          className="fill-brand-foreground font-mono text-[13.5px] uppercase"
          style={{ letterSpacing: "0.22em" }}
        >
          <textPath href="#ring" textLength={488} lengthAdjust="spacing">
            {ring}
          </textPath>
        </text>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-brand-foreground">
        <span className="melt text-6xl md:text-7xl">{value}</span>
      </div>
    </div>
  );
}
