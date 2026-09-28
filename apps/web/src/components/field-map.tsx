"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { HazardCode } from "@/components/hazard";
import { hours, int, metres } from "@/lib/format";
import { boundsOf, niceLength, project } from "@/lib/geo";
import { GEOLOGICAL_KEYS, HAZARD_KEYS, hazardMeta, type HazardKey } from "@/lib/hazards";
import { cn } from "@/lib/utils";
import { shortName } from "@/lib/wells";

export interface MapWell {
  name: string;
  slug: string;
  era: "exploration" | "development";
  path: [number, number][];
  events: number;
  npt: number;
}

export interface MapEvent {
  id: number;
  hazard: string;
  geological: boolean;
  e: number;
  n: number;
  npt: number;
  wellbore: string;
  tvdss: number | null;
  formation: string | null;
}

const WIDTH = 1000;

function radius(npt: number): number {
  return 3 + Math.min(9, Math.sqrt(npt) * 1.3);
}

/** Wellheads within 60 m of each other share a slot (a template or a re-entered well). */
function slots(wells: readonly MapWell[]): { e: number; n: number; label: string }[] {
  const groups: { e: number; n: number; names: string[] }[] = [];
  for (const w of wells) {
    const head = w.path[0];
    if (!head) continue;
    const g = groups.find((s) => Math.hypot(s.e - head[0], s.n - head[1]) < 60);
    if (g) g.names.push(w.name);
    else groups.push({ e: head[0], n: head[1], names: [w.name] });
  }
  return groups.map((g) => {
    let prefix = g.names[0] ?? "";
    for (const name of g.names) while (!name.startsWith(prefix)) prefix = prefix.slice(0, -1);
    const base = prefix.replace(/[-\s]+$/, "");
    return {
      e: g.e,
      n: g.n,
      label: g.names.length > 1 ? `${base} · ${g.names.length} bores` : base,
    };
  });
}

export function FieldMap({ wells, events }: { wells: MapWell[]; events: MapEvent[] }) {
  const router = useRouter();
  const [active, setActive] = useState<Set<HazardKey>>(() => new Set(GEOLOGICAL_KEYS));
  const [hoverWell, setHoverWell] = useState<string | null>(null);
  const [hoverEvent, setHoverEvent] = useState<MapEvent | null>(null);

  const proj = useMemo(() => project(boundsOf(wells.flatMap((w) => w.path)), WIDTH), [wells]);
  const slotMarks = useMemo(() => slots(wells), [wells]);
  const visible = events.filter((e) => active.has(e.hazard as HazardKey));
  const bar = niceLength((WIDTH * proj.scale) / 6);

  const toggle = (key: HazardKey) =>
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const counts = new Map<string, number>();
  for (const e of events) counts.set(e.hazard, (counts.get(e.hazard) ?? 0) + 1);

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <div className="relative border bg-surface">
        <div className="grid-paper absolute inset-0 opacity-70" aria-hidden />
        <svg
          viewBox={`0 0 ${WIDTH} ${proj.height}`}
          className="relative block w-full"
          role="img"
          aria-label={`Plan view of ${wells.length} wellbores and ${visible.length} events`}
          onMouseLeave={() => {
            setHoverWell(null);
            setHoverEvent(null);
          }}
        >
          {wells.map((w) => {
            const points = w.path.map(([e, n]) => `${proj.x(e)},${proj.y(n)}`).join(" ");
            const hot = hoverWell === w.name;
            const end = w.path.at(-1);
            return (
              <g key={w.name}>
                <polyline
                  points={points}
                  fill="none"
                  stroke={hot ? "var(--brand-text)" : "var(--foreground)"}
                  strokeOpacity={hot ? 1 : w.era === "development" ? 0.55 : 0.4}
                  strokeWidth={hot ? 3.5 : 1.4}
                  strokeDasharray={w.era === "exploration" ? "6 4" : undefined}
                  strokeLinecap="round"
                />
                {end && (
                  <rect
                    x={proj.x(end[0]) - 3}
                    y={proj.y(end[1]) - 3}
                    width={6}
                    height={6}
                    fill={hot ? "var(--brand)" : "var(--background)"}
                    stroke="var(--foreground)"
                    strokeWidth={1.2}
                  />
                )}
                <polyline
                  points={points}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={14}
                  className="cursor-pointer"
                  onMouseEnter={() => setHoverWell(w.name)}
                  onClick={() => router.push(`/wells/${w.slug}`)}
                />
              </g>
            );
          })}

          {visible.map((e) => (
            <circle
              key={e.id}
              cx={proj.x(e.e)}
              cy={proj.y(e.n)}
              r={radius(e.npt)}
              fill={hazardMeta(e.hazard).color}
              fillOpacity={hoverWell && hoverWell !== e.wellbore ? 0.15 : 0.9}
              stroke="var(--background)"
              strokeWidth={1}
              className="cursor-pointer"
              onMouseEnter={() => {
                setHoverEvent(e);
                setHoverWell(e.wellbore);
              }}
              onClick={() => router.push(`/events/${e.id}`)}
            />
          ))}

          {slotMarks.map((s) => (
            <g key={s.label} transform={`translate(${proj.x(s.e)},${proj.y(s.n)})`}>
              <rect
                x={-7}
                y={-7}
                width={14}
                height={14}
                fill="var(--brand)"
                stroke="var(--border)"
              />
              <rect x={-2} y={-2} width={4} height={4} fill="var(--brand-foreground)" />
              <text
                x={proj.x(s.e) > WIDTH * 0.7 ? -12 : 12}
                y={-10}
                textAnchor={proj.x(s.e) > WIDTH * 0.7 ? "end" : "start"}
                className="fill-foreground font-mono text-[13px] uppercase"
                style={{ letterSpacing: "0.06em" }}
              >
                {s.label}
              </text>
            </g>
          ))}

          <g transform={`translate(${WIDTH - 60}, 30)`} aria-hidden>
            <path d="M0 -18 L9 12 L0 5 L-9 12 Z" fill="var(--foreground)" />
            <text y={32} textAnchor="middle" className="fill-foreground font-mono text-[13px]">
              N
            </text>
          </g>
          <g transform={`translate(24, ${proj.height - 24})`} aria-hidden>
            <rect width={bar / proj.scale} height={6} fill="var(--foreground)" />
            <rect width={bar / proj.scale / 2} height={6} fill="var(--brand)" />
            <text y={-8} className="fill-foreground font-mono text-[12px]">
              {bar >= 1000 ? `${bar / 1000} km` : `${bar} m`}
            </text>
          </g>
        </svg>

        {hoverEvent && (
          <div
            className="brutal pointer-events-none absolute z-10 w-60 bg-background p-3"
            style={{
              left: `${Math.min(70, (proj.x(hoverEvent.e) / WIDTH) * 100)}%`,
              top: `${Math.min(75, (proj.y(hoverEvent.n) / proj.height) * 100 + 3)}%`,
            }}
          >
            <div className="flex items-center gap-2">
              <HazardCode hazard={hoverEvent.hazard} />
              <span className="text-sm font-semibold">{hazardMeta(hoverEvent.hazard).label}</span>
            </div>
            <p className="label mt-2 flex flex-col gap-0.5 text-muted-foreground">
              <span className="text-foreground">{shortName(hoverEvent.wellbore)}</span>
              <span>{metres(hoverEvent.tvdss)} TVDSS</span>
              {hoverEvent.formation && <span>{hoverEvent.formation}</span>}
              <span>{hours(hoverEvent.npt)} lost</span>
            </p>
          </div>
        )}
      </div>

      <aside className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-1">
          <legend className="label mb-2 text-muted-foreground">Hazards on map</legend>
          {HAZARD_KEYS.map((key) => {
            const meta = hazardMeta(key);
            const on = active.has(key);
            return (
              <button
                key={key}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(key)}
                className={cn(
                  "flex items-center justify-between gap-2 border px-2 py-1 text-left transition-opacity",
                  !on && "opacity-40 hover:opacity-80",
                  !meta.geological && "border-dashed",
                )}
              >
                <span className="flex items-center gap-2">
                  <HazardCode hazard={key} />
                  <span className="text-sm">{meta.label}</span>
                </span>
                <span className="label text-muted-foreground">{int(counts.get(key) ?? 0)}</span>
              </button>
            );
          })}
        </fieldset>
        <div className="label flex flex-col gap-1 text-muted-foreground">
          <span className="flex items-center gap-2">
            <svg width="28" height="4" aria-hidden>
              <line x1="0" y1="2" x2="28" y2="2" stroke="currentColor" strokeWidth="1.5" />
            </svg>
            2007&ndash;14 development
          </span>
          <span className="flex items-center gap-2">
            <svg width="28" height="4" aria-hidden>
              <line
                x1="0"
                y1="2"
                x2="28"
                y2="2"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeDasharray="6 4"
              />
            </svg>
            1992&ndash;98 exploration
          </span>
          <span>Dot size = hours lost</span>
        </div>
        <nav aria-label="Wellbores on the map" className="flex flex-wrap gap-1">
          {wells.map((w) => (
            <Link
              key={w.name}
              href={`/wells/${w.slug}`}
              onMouseEnter={() => setHoverWell(w.name)}
              onFocus={() => setHoverWell(w.name)}
              onMouseLeave={() => setHoverWell(null)}
              className={cn(
                "label border px-1.5 py-0.5 transition-colors",
                hoverWell === w.name
                  ? "bg-brand text-brand-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {shortName(w.name)}
            </Link>
          ))}
        </nav>
      </aside>
    </div>
  );
}
