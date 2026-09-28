import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { EventCard } from "@/components/event-card";
import { LookaheadStrip } from "@/components/lookahead-strip";
import { NoSignal } from "@/components/no-signal";
import { SectionHead } from "@/components/section-head";
import { fetchEvents, fetchField } from "@/lib/api/field";
import { day, hours, int, metres } from "@/lib/format";
import type { DepthEvent } from "@/lib/lookahead";
import { findBySlug, shortName, wellSlug } from "@/lib/wells";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const field = await fetchField();
  const well = field.ok ? findBySlug(field.data.wellbores, slug) : null;
  return { title: well ? `${well.name} cockpit` : "Well" };
}

export default async function WellPage({ params }: Params) {
  const { slug } = await params;
  const result = await fetchField();
  if (!result.ok) return <NoSignal reason={result.reason} />;
  const field = result.data;
  const well = findBySlug(field.wellbores, slug);
  if (!well) notFound();

  const depthEvents: DepthEvent[] = field.events
    .filter((e) => e.geological)
    .map((e) => ({
      id: e.id,
      wellbore: e.wellbore,
      hazard: e.hazard,
      geological: e.geological,
      tvdss_top_m: e.tvdss_top_m,
      npt_h: e.npt_h,
    }));
  const own = await fetchEvents({
    wellbore: well.name,
    geological: true,
    sort: "depth",
    limit: 100,
  });
  const honest = well.offsets.filter((o) => o.completed_before_spud).length;
  const parent = well.parent_name ? field.wellbores.find((w) => w.name === well.parent_name) : null;

  const facts = [
    { label: "First report", value: day(well.first_report_at) },
    { label: "Last report", value: day(well.last_report_at) },
    { label: "TD", value: `${metres(well.td_md_m)} MD` },
    { label: "TD TVDSS", value: metres(well.td_tvdss_m) },
    { label: "Water depth", value: metres(well.water_depth_m) },
    { label: "KB elevation", value: metres(well.kb_elevation_m) },
    { label: "Reports", value: int(well.reports) },
    { label: "Lost time", value: hours(well.npt_h) },
  ];

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-14 px-4 pt-8 md:px-8 md:pt-12">
      <header className="flex flex-col gap-6">
        <nav aria-label="Breadcrumb" className="label text-muted-foreground">
          <Link href="/wells" className="hover:text-foreground">
            Wells
          </Link>{" "}
          / {well.name}
        </nav>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="melt-hover">
            <p className="label text-muted-foreground">
              {well.kind.replaceAll("_", " ")} &middot; {well.purpose ?? well.era}
              {parent && (
                <>
                  {" "}
                  &middot; from{" "}
                  <Link
                    href={`/wells/${wellSlug(parent.name)}`}
                    className="underline decoration-brand decoration-2 underline-offset-4"
                  >
                    {shortName(parent.name)}
                  </Link>
                </>
              )}
            </p>
            <h1 className="melt mt-2 text-[clamp(2.5rem,10vw,8rem)] uppercase">
              {shortName(well.name)}
            </h1>
          </div>
          <p className="max-w-md text-pretty text-muted-foreground">
            <span className="font-serif text-2xl text-foreground italic">
              {honest} offset {honest === 1 ? "well" : "wells"}
            </span>{" "}
            were finished before this one started. That is what the crew could have learned from,
            and all the cockpit uses unless you switch on hindsight.
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-px border bg-border sm:grid-cols-4 lg:grid-cols-8">
          {facts.map((f) => (
            <div key={f.label} className="bg-background p-3">
              <dt className="label text-muted-foreground">{f.label}</dt>
              <dd className="mt-1 font-mono text-sm">{f.value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <section className="flex flex-col gap-6">
        <SectionHead n="A" kicker="look-ahead" title="Drive the bit" />
        <LookaheadStrip
          well={{
            name: well.name,
            tdTvdssM: well.td_tvdss_m ?? 0,
            waterDepthM: well.water_depth_m,
            tops: well.tops,
            offsets: well.offsets,
          }}
          ownEvents={depthEvents.filter((e) => e.wellbore === well.name)}
          fieldEvents={depthEvents.filter((e) => e.wellbore !== well.name)}
          formationOrder={field.formations.map((f) => f.name)}
        />
        <p className="max-w-3xl text-sm text-muted-foreground">
          This strip counts what offset wells reported at each depth below sea level. It is
          evidence, not yet a probability: the calibrated risk model and its backtest arrive in the
          next phase.
        </p>
      </section>

      <section className="flex flex-col gap-6">
        <SectionHead n="B" kicker="geological, shallow to deep" title="What this well hit">
          <Link
            href={`/events?well=${encodeURIComponent(well.name)}`}
            className="label text-muted-foreground hover:text-foreground"
          >
            All {int(well.events)} events, incl. operational &rarr;
          </Link>
        </SectionHead>
        {!own.ok ? (
          <p className="text-danger">{own.reason}</p>
        ) : own.data.items.length === 0 ? (
          <p className="text-muted-foreground">
            No geological problems were extracted for this well.
          </p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {own.data.items.map((e) => (
              <EventCard key={e.id} event={e} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
