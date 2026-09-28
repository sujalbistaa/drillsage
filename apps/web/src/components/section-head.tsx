import type { ReactNode } from "react";

/** Section header: a big title with an optional right-hand slot. */
export function SectionHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b pb-3">
      <h2 className="headline headline-hover text-3xl uppercase md:text-5xl">{title}</h2>
      {children}
    </div>
  );
}
