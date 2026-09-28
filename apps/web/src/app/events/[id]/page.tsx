import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { EvidenceText } from "@/components/evidence-text";
import { Outcome } from "@/components/event-card";
import { HazardCode, SeverityPips } from "@/components/hazard";
import { NoSignal } from "@/components/no-signal";
import { fetchEvent } from "@/lib/api/field";
import { day, density, holeInches, hours, metres } from "@/lib/format";
import { hazardMeta, SEVERITY_LABELS } from "@/lib/hazards";
import { shortName, wellSlug } from "@/lib/wells";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

function eventId(raw: string): number | null {
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const id = eventId((await params).id);
  const result = id ? await fetchEvent(id) : null;
  const event = result?.ok ? result.data : null;
  return { title: event ? `${hazardMeta(event.hazard).label}, ${event.wellbore}` : "Event" };
}

/** A barcode drawn from the event id: decoration that is at least deterministic. */
function Barcode({ seed }: { seed: number }) {
  const bars: number[] = [];
  let x = Math.imul(seed, 2654435761) >>> 0;
  for (let i = 0; i < 48; i++) {
    x = (Math.imul(x, 1103515245) + 12345) >>> 0;
    bars.push(1 + ((x >>> 16) % 4));
  }
  return (
    <div className="flex h-12 items-stretch gap-[2px]" aria-hidden>
      {bars.map((w, i) => (
        <span key={i} className="bg-[#0b0b0c]" style={{ width: w }} />
      ))}
    </div>
  );
}

export default async function EventPage({ params }: Params) {
  const id = eventId((await params).id);
  if (id == null) notFound();
  const result = await fetchEvent(id);
  if (!result.ok) return <NoSignal reason={result.reason} />;
  const event = result.data;
  if (!event) notFound();
  const meta = hazardMeta(event.hazard);

  const rows: [string, string | null][] = [
    ["Well", event.wellbore],
    [
      "Depth MD",
      event.md_top_m != null
        ? `${metres(event.md_top_m)}${event.md_bottom_m && event.md_bottom_m !== event.md_top_m ? ` – ${metres(event.md_bottom_m)}` : ""}`
        : null,
    ],
    ["Depth TVDSS", metres(event.tvdss_top_m)],
    ["Depth from", event.depth_source],
    ["Formation", event.formation ?? event.formation_group],
    ["Mud", density(event.mud_density_gcc)],
    ["Hole", holeInches(event.hole_diameter_m)],
    ["Started", day(event.start_at)],
    ["Ended", day(event.end_at)],
    ["Sidetracked after", event.led_to_sidetrack ? "yes" : "no"],
    ["Found by", `${event.detected_by} (${event.confidence_tier} tier)`],
  ];

  return (
    <div className="mx-auto grid max-w-[1400px] gap-10 px-4 pt-8 md:px-8 md:pt-12 lg:grid-cols-[1fr_minmax(0,560px)]">
      <div className="flex flex-col gap-6">
        <nav aria-label="Breadcrumb" className="label text-muted-foreground">
          <Link href="/events" className="hover:text-foreground">
            Events
          </Link>{" "}
          / #{String(event.id).padStart(4, "0")}
        </nav>
        <div className="flex items-center gap-3">
          <HazardCode hazard={event.hazard} className="h-9 min-w-12 text-sm" />
          <span className="label text-muted-foreground">
            {meta.geological ? "Geological hazard" : "Operational NPT"}
          </span>
        </div>
        <h1
          className="melt melt-hover text-[clamp(2rem,7vw,6rem)] uppercase"
          style={{ color: meta.color }}
        >
          {meta.label}
        </h1>
        <p className="text-xl text-pretty">
          <Link
            href={`/wells/${wellSlug(event.wellbore)}`}
            className="underline decoration-brand decoration-2 underline-offset-4 hover:bg-brand hover:text-brand-foreground"
          >
            {shortName(event.wellbore)}
          </Link>
          {event.formation && (
            <>
              , in the <span className="font-serif text-2xl italic">{event.formation}</span>
            </>
          )}
          {event.tvdss_top_m != null && <>, {metres(event.tvdss_top_m)} below sea level</>}.{" "}
          {hours(event.npt_h)} lost.
        </p>
        <div className="flex items-center gap-3">
          <SeverityPips severity={event.severity} />
          <span className="label">
            Severity {event.severity}/4 &middot; {SEVERITY_LABELS[event.severity]}
          </span>
        </div>

        {event.mitigations.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="label text-muted-foreground">What the crew tried</p>
            <ul className="flex flex-col border">
              {event.mitigations.map((m) => (
                <li
                  key={m.action}
                  className="flex items-center justify-between border-b px-3 py-2 last:border-b-0"
                >
                  <span>{m.action}</span>
                  <Outcome outcome={m.outcome} />
                </li>
              ))}
            </ul>
          </div>
        )}

        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 border-t pt-5">
          {rows.map(([label, value]) =>
            value ? (
              <div key={label} className="contents">
                <dt className="label pt-0.5 text-muted-foreground">{label}</dt>
                <dd className="font-mono text-sm">{value}</dd>
              </div>
            ) : null,
          )}
        </dl>

        <div className="flex flex-wrap gap-3">
          <Link
            href={`/events?hazard=${event.hazard}`}
            className="brutal brutal-hover label bg-surface px-4 py-3"
          >
            More {meta.short.toLowerCase()} events &rarr;
          </Link>
          <Link
            href={`/wells/${wellSlug(event.wellbore)}`}
            className="brutal brutal-hover label bg-brand px-4 py-3 text-brand-foreground"
          >
            Open {shortName(event.wellbore)} cockpit &rarr;
          </Link>
        </div>
      </div>

      <article
        aria-label="Evidence receipt"
        className="perforated self-start bg-[#f4f1e8] px-6 py-9 font-mono text-[#0b0b0c] shadow-[8px_8px_0_0_var(--shadow)] md:px-8"
      >
        <header className="flex flex-col items-center gap-1 border-b border-dashed border-[#0b0b0c]/40 pb-4 text-center">
          <span className="melt text-2xl uppercase">DrillSage</span>
          <span className="text-[11px] tracking-[0.2em] uppercase">Evidence receipt</span>
          <span className="text-[11px]">
            #{String(event.id).padStart(6, "0")} &middot; {day(event.start_at)}
          </span>
        </header>
        <p className="mt-4 text-[11px] tracking-wider uppercase">
          {event.evidence_lines_total} report {event.evidence_lines_total === 1 ? "line" : "lines"}
          {event.evidence_lines_total > event.evidence.length &&
            `, first ${event.evidence.length} shown`}
        </p>
        <ol className="mt-3 flex flex-col">
          {event.evidence.map((line) => (
            <li
              key={`${line.report_on}-${line.line}`}
              className="border-b border-dashed border-[#0b0b0c]/30 py-3 last:border-b-0"
            >
              <p className="flex justify-between gap-3 text-[10px] tracking-wider uppercase opacity-70">
                <span>
                  {day(line.report_on)} &middot; line {line.line + 1}
                </span>
                <span>{line.md_m != null ? metres(line.md_m) : ""}</span>
              </p>
              {line.code && (
                <p className="mt-1 text-[10px] tracking-wider uppercase">[{line.code}]</p>
              )}
              <p className="mt-1.5 text-[12.5px] leading-relaxed">
                <EvidenceText text={line.text} spans={line.spans} />
              </p>
            </li>
          ))}
        </ol>
        <footer className="mt-4 flex flex-col items-center gap-3 border-t border-dashed border-[#0b0b0c]/40 pt-4">
          <div className="flex w-full justify-between text-[12px] uppercase">
            <span>Time lost</span>
            <span className="font-bold">{hours(event.npt_h)}</span>
          </div>
          <Barcode seed={event.id} />
          <span className="text-[10px] tracking-[0.2em] uppercase">
            Source: Volve DDR, WITSML 1.4
          </span>
        </footer>
      </article>
    </div>
  );
}
