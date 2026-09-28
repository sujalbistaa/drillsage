import Link from "next/link";

import { EvidenceText } from "@/components/evidence-text";
import { HazardCode, SeverityPips } from "@/components/hazard";
import type { DrillEvent } from "@/lib/api/client";
import { day, density, holeInches, hours, metres } from "@/lib/format";
import { hazardMeta } from "@/lib/hazards";
import { cn } from "@/lib/utils";
import { shortName, wellSlug } from "@/lib/wells";

const OUTCOME = {
  success: { text: "worked", className: "text-ok" },
  failure: { text: "failed", className: "text-danger" },
  unknown: { text: "outcome n/a", className: "text-muted-foreground" },
} as const;

export function Outcome({ outcome }: { outcome: string }) {
  const o = OUTCOME[outcome as keyof typeof OUTCOME] ?? OUTCOME.unknown;
  return <span className={cn("label", o.className)}>{o.text}</span>;
}

/** One drilling problem: what, where, how bad, the quoted evidence, and what was tried. */
export function EventCard({ event }: { event: DrillEvent }) {
  const meta = hazardMeta(event.hazard);
  const quote = event.evidence.find((line) => line.spans.length > 0) ?? event.evidence[0];
  const facts = [
    event.md_top_m != null ? `${metres(event.md_top_m)} MD` : null,
    event.tvdss_top_m != null && event.tvdss_top_m >= 0
      ? `${metres(event.tvdss_top_m)} TVDSS`
      : null,
    event.formation ?? event.formation_group,
    density(event.mud_density_gcc),
    holeInches(event.hole_diameter_m),
  ].filter(Boolean);

  return (
    <article
      className="group relative border bg-surface transition-colors hover:border-foreground"
      style={{ borderLeft: `6px solid ${meta.color}` }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-4 py-2.5">
        <div className="flex items-center gap-3">
          <HazardCode hazard={event.hazard} />
          <h3 className="text-lg leading-tight font-semibold tracking-tight">
            {meta.label}
            {event.subtype && (
              <span className="font-serif font-normal text-muted-foreground italic">
                {" "}
                &middot; {event.subtype.replaceAll("_", " ")}
              </span>
            )}
          </h3>
        </div>
        <div className="label flex items-center gap-4">
          <SeverityPips severity={event.severity} />
          <span className={cn(event.npt_h >= 24 && "text-danger")}>{hours(event.npt_h)} NPT</span>
        </div>
      </div>

      <div className="flex flex-col gap-3 px-4 py-3">
        <p className="label flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
          <Link
            href={`/wells/${wellSlug(event.wellbore)}`}
            className="relative z-10 text-foreground underline decoration-brand decoration-2 underline-offset-4 hover:bg-brand hover:text-brand-foreground"
          >
            {shortName(event.wellbore)}
          </Link>
          {facts.map((f) => (
            <span key={f}>{f}</span>
          ))}
        </p>

        {quote && (
          <blockquote className="border-l-2 border-hairline pl-3 font-mono text-[0.8rem] leading-relaxed">
            <EvidenceText text={quote.text} spans={quote.spans} clip />
          </blockquote>
        )}

        {event.mitigations.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {event.mitigations.map((m) => (
              <li key={m.action} className="flex items-center gap-2 border px-2 py-0.5">
                <span className="text-sm">{m.action}</span>
                <Outcome outcome={m.outcome} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="label flex flex-wrap items-center justify-between gap-2 border-t border-hairline px-4 py-2 text-muted-foreground">
        <span>
          {day(event.start_at)} &middot; {event.confidence_tier} tier &middot; {event.detected_by}
          {event.evidence_lines_total > 1 && ` · ${event.evidence_lines_total} report lines`}
        </span>
        <Link
          href={`/events/${event.id}`}
          className="text-foreground group-hover:text-brand-text after:absolute after:inset-0"
        >
          Open receipt &rarr;
        </Link>
      </div>
    </article>
  );
}
