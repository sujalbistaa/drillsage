import { Spark } from "@/components/spark";

/** The lime news-ticker under the header. Items repeat twice so the loop is seamless. */
export function Ticker({ items }: { items: string[] }) {
  const run = (hidden: boolean) => (
    <div className="flex shrink-0 items-center" aria-hidden={hidden || undefined}>
      {items.map((item, i) => (
        <span key={i} className="label flex items-center gap-4 px-4 whitespace-nowrap">
          {item}
          <Spark className="size-3" />
        </span>
      ))}
    </div>
  );
  return (
    <div className="overflow-hidden border-b bg-brand py-1.5 text-brand-foreground">
      <div className="flex w-max animate-marquee hover:[animation-play-state:paused]">
        {run(false)}
        {run(true)}
      </div>
    </div>
  );
}
