import Link from "next/link";

import { FieldMap, type MapEvent, type MapWell } from "@/components/field-map";
import { HazardBars } from "@/components/hazard-bars";
import { NoSignal } from "@/components/no-signal";
import { SectionHead } from "@/components/section-head";
import { SpinBadge } from "@/components/spin-badge";
import { fetchField } from "@/lib/api/field";
import type { FieldOverview } from "@/lib/api/client";
import { hours, int, year } from "@/lib/format";
import { shortName, wellSlug } from "@/lib/wells";

// The field can be rebuilt at any time; never serve it from a build-time cache.
export const dynamic = "force-dynamic";

/** The wellbore with the most honest offsets (finished before it started) makes the best demo. */
function demoWell(field: FieldOverview): string | null {
  const ranked = [...field.wellbores]
    .filter((w) => w.events > 0)
    .sort(
      (a, b) =>
        b.offsets.filter((o) => o.completed_before_spud).length -
          a.offsets.filter((o) => o.completed_before_spud).length || b.events - a.events,
    );
  return ranked[0]?.name ?? null;
}

const STEPS = [
  {
    n: "01",
    title: "Read",
    body: "Every WITSML daily drilling report, parsed with zero dropped values. Units normalised, surveys turned into true well paths, formations placed along each hole.",
  },
  {
    n: "02",
    title: "Extract",
    body: "Operator codes, a phrase lexicon tuned on real reports, and an LLM that must quote the report word for word. No quote, no event.",
  },
  {
    n: "03",
    title: "Warn",
    body: "Offset wells finished before yours, compared by formation and depth below sea level. The strip lights up before the bit gets there.",
  },
] as const;

export default async function FieldPage() {
  const result = await fetchField();
  if (!result.ok) return <NoSignal reason={result.reason} />;
  const field = result.data;
  const s = field.stats;
  const demo = demoWell(field);

  const wells: MapWell[] = field.wellbores.map((w) => ({
    name: w.name,
    slug: wellSlug(w.name),
    era: w.era,
    path: w.trajectory.map((p) => [p.easting_m, p.northing_m]),
    events: w.events,
    npt: w.npt_h,
  }));
  const events: MapEvent[] = field.events.flatMap((e) =>
    e.easting_m != null && e.northing_m != null
      ? [
          {
            id: e.id,
            hazard: e.hazard,
            geological: e.geological,
            e: e.easting_m,
            n: e.northing_m,
            npt: e.npt_h,
            wellbore: e.wellbore,
            tvdss: e.tvdss_top_m,
            formation: e.formation,
          },
        ]
      : [],
  );

  const heads = field.wellbores;
  const origin = {
    lat: heads.reduce((sum, w) => sum + w.lat_deg, 0) / Math.max(1, heads.length),
    lon: heads.reduce((sum, w) => sum + w.lon_deg, 0) / Math.max(1, heads.length),
    field: field.field,
  };

  const stats = [
    {
      value: int(s.events),
      label: "Drilling problems found",
      note: `${int(s.geological_events)} geological`,
    },
    {
      value: int(Math.round(s.npt_h)),
      label: "Hours lost, located",
      note: `${int(Math.round(s.npt_h / 24))} rig days`,
    },
    {
      value: int(s.reports),
      label: "Daily reports read",
      note: `${int(s.activities)} report lines`,
    },
    {
      value: String(s.wellbores),
      label: "Wellbores",
      note: `${year(s.first_report_on)}–${year(s.last_report_on)}`,
    },
  ];

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-24 px-4 pt-10 md:px-8 md:pt-16">
      <section className="grid items-center gap-10 lg:grid-cols-[1fr_auto]">
        <div className="flex flex-col gap-7">
          <ul aria-label="About DrillSage" className="flex flex-wrap items-center gap-2.5">
            <li className="-rotate-2 bg-foreground px-3 py-1 font-glitch text-lg text-background uppercase md:text-xl">
              Nearby wells intelligence
            </li>
            <li className="brutal rotate-2 bg-brand px-3 py-0.5 font-glitch text-lg text-brand-foreground uppercase md:text-xl">
              SIH26121
            </li>
            <li className="-rotate-1 bg-[var(--hz-wc)] px-3 py-1 font-glitch text-lg text-white uppercase md:text-xl">
              Oil India Ltd
            </li>
          </ul>
          <h1 className="melt melt-hover text-[clamp(2.25rem,9.5vw,9rem)] uppercase">
            See{" "}
            <span className="inline-block -rotate-2 bg-brand px-[0.08em] text-brand-foreground">
              trouble
            </span>
            <br />
            before the
            <br />
            bit does.
          </h1>
          <p className="max-w-2xl text-lg leading-relaxed text-pretty md:text-xl">
            DrillSage reads every daily report from the wells around yours, finds the losses, kicks,
            stuck pipe and tight spots, pins each one to a depth and a formation, and warns your
            crew <em className="font-serif text-2xl text-brand-text">before the bit gets there.</em>{" "}
            Every warning points to the exact report line behind it.
          </p>
          <div className="flex flex-wrap gap-4">
            {demo && (
              <Link
                href={`/wells/${wellSlug(demo)}`}
                className="brutal brutal-hover label bg-brand px-5 py-3.5 text-sm text-brand-foreground"
              >
                Open the cockpit: {shortName(demo)} &rarr;
              </Link>
            )}
            <Link
              href="/events"
              className="brutal brutal-hover label bg-surface px-5 py-3.5 text-sm"
            >
              Read all {int(s.events)} events &rarr;
            </Link>
          </div>
        </div>
        <div className="flex justify-center lg:justify-end">
          <SpinBadge value={String(s.wellbores)} ring="real data • volve field • wellbores • " />
          <span className="sr-only">
            {s.wellbores} wellbores of real data from the Equinor Volve field, {s.reports} reports.
          </span>
        </div>
      </section>

      <section aria-label="Field numbers" className="grid grid-cols-2 border lg:grid-cols-4">
        {stats.map((stat, i) => (
          <div
            key={stat.label}
            className={`flex flex-col gap-3 p-5 md:p-7 ${i > 0 ? "border-l" : ""} ${i > 1 ? "max-lg:border-t" : ""} ${i === 2 ? "max-lg:border-l-0" : ""}`}
          >
            <span className="label text-muted-foreground">{stat.label}</span>
            <span className="melt text-[clamp(1.75rem,3.7vw,3.9rem)] whitespace-nowrap">
              {stat.value}
            </span>
            <span className="label text-brand-text">{stat.note}</span>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-6">
        <SectionHead title="The field from above">
          <p className="max-w-sm text-sm text-muted-foreground">
            Well paths from minimum-curvature surveys. Each dot is a problem at the place it
            happened underground. Hover to inspect, click to open.
          </p>
        </SectionHead>
        <FieldMap wells={wells} events={events} origin={origin} />
      </section>

      <section className="flex flex-col gap-6">
        <SectionHead title="Where the hours went">
          <p className="label text-muted-foreground">
            {hours(s.npt_h)} across {s.wellbores} wellbores
          </p>
        </SectionHead>
        <HazardBars hazards={field.hazards} />
      </section>

      <section className="flex flex-col gap-6">
        <SectionHead title="How it works" />
        <ol className="grid gap-4 md:grid-cols-3">
          {STEPS.map((step) => (
            <li key={step.n} className="melt-hover brutal flex flex-col gap-4 bg-surface p-6">
              <span className="melt text-7xl text-brand-text">{step.n}</span>
              <h3 className="melt text-3xl uppercase">{step.title}</h3>
              <p className="leading-relaxed text-pretty text-muted-foreground">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
