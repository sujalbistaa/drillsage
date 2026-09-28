import type { Metadata } from "next";
import Link from "next/link";

import { NoSignal } from "@/components/no-signal";
import { SectionHead } from "@/components/section-head";
import { fetchField } from "@/lib/api/field";
import type { EventPoint, Wellbore } from "@/lib/api/client";
import { hours, int, year } from "@/lib/format";
import { hazardMeta } from "@/lib/hazards";
import { shortName, wellSlug } from "@/lib/wells";

export const metadata: Metadata = { title: "Wells" };
export const dynamic = "force-dynamic";

/** A tiny vertical depth strip: one tick per geological event, at its TVDSS. */
function MiniStrip({
  well,
  events,
  maxDepth,
}: {
  well: Wellbore;
  events: EventPoint[];
  maxDepth: number;
}) {
  const td = well.td_tvdss_m ?? 0;
  return (
    <svg viewBox="0 0 24 100" preserveAspectRatio="none" className="h-28 w-6 shrink-0" aria-hidden>
      <rect
        x="10"
        y="0"
        width="4"
        height={(td / maxDepth) * 100}
        fill="var(--foreground)"
        opacity="0.25"
      />
      {events.map((e) =>
        e.tvdss_top_m == null ? null : (
          <rect
            key={e.id}
            x="0"
            y={(e.tvdss_top_m / maxDepth) * 100 - 0.8}
            width="24"
            height="1.6"
            fill={hazardMeta(e.hazard).color}
          />
        ),
      )}
    </svg>
  );
}

function WellCard({
  well,
  events,
  maxDepth,
}: {
  well: Wellbore;
  events: EventPoint[];
  maxDepth: number;
}) {
  const honest = well.offsets.filter((o) => o.completed_before_spud).length;
  return (
    <Link
      href={`/wells/${wellSlug(well.name)}`}
      className="melt-hover brutal-hover group flex gap-4 border bg-surface p-4 hover:border-foreground"
    >
      <MiniStrip well={well} events={events.filter((e) => e.geological)} maxDepth={maxDepth} />
      <div className="flex min-w-0 flex-1 flex-col justify-between gap-3">
        <div>
          <p className="label text-muted-foreground">
            {well.kind.replaceAll("_", " ")}
            {well.parent_name && ` of ${shortName(well.parent_name)}`}
          </p>
          <h3 className="melt mt-1 text-3xl uppercase">{shortName(well.name)}</h3>
        </div>
        <dl className="label grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
          <dt>Events</dt>
          <dd className="text-right text-foreground">{int(well.events)}</dd>
          <dt>Lost</dt>
          <dd className="text-right text-foreground">{hours(well.npt_h)}</dd>
          <dt>TD</dt>
          <dd className="text-right text-foreground">{int(well.td_tvdss_m ?? 0)} m</dd>
          <dt>Offsets</dt>
          <dd className="text-right text-foreground">{honest} prior</dd>
        </dl>
      </div>
    </Link>
  );
}

export default async function WellsPage() {
  const result = await fetchField();
  if (!result.ok) return <NoSignal reason={result.reason} />;
  const field = result.data;
  const maxDepth = Math.max(...field.wellbores.map((w) => w.td_tvdss_m ?? 0));
  const byWell = new Map<string, EventPoint[]>();
  for (const e of field.events) byWell.set(e.wellbore, [...(byWell.get(e.wellbore) ?? []), e]);

  const eras = [
    { key: "development", title: "The F-template", note: "Development wells and sidetracks" },
    { key: "exploration", title: "The discovery", note: "Exploration and appraisal, 15/9-19" },
  ] as const;

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-16 px-4 pt-10 md:px-8 md:pt-16">
      <header className="flex flex-col gap-4">
        <h1 className="melt text-[clamp(2rem,8vw,7rem)] uppercase">
          {field.wellbores.length} holes
          <br />
          in the ground.
        </h1>
        <p className="max-w-2xl text-lg text-pretty text-muted-foreground">
          Pick a well to open its cockpit: its formations, every problem the wells around it hit,
          and a bit you can drive down the hole.
        </p>
      </header>
      {eras.map((era) => {
        const wells = field.wellbores.filter((w) => w.era === era.key);
        if (wells.length === 0) return null;
        const years = wells.map((w) => year(w.first_report_at));
        return (
          <section key={era.key} className="flex flex-col gap-6">
            <SectionHead title={era.title}>
              <span className="label text-muted-foreground">
                {Math.min(...years)}&ndash;{String(Math.max(...years)).slice(2)} &middot; {era.note}
              </span>
            </SectionHead>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {wells.map((w) => (
                <WellCard
                  key={w.name}
                  well={w}
                  events={byWell.get(w.name) ?? []}
                  maxDepth={maxDepth}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
