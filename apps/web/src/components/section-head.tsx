import type { ReactNode } from "react";

/** Numbered section header: `01 / THE FIELD FROM ABOVE` with an optional right-hand slot. */
export function SectionHead({
  n,
  title,
  kicker,
  children,
}: {
  n: string;
  title: string;
  kicker?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b pb-3">
      <div className="flex flex-col gap-2">
        <span className="label text-muted-foreground">
          {n} / {kicker ?? "section"}
        </span>
        <h2 className="melt text-3xl uppercase md:text-5xl">{title}</h2>
      </div>
      {children}
    </div>
  );
}
