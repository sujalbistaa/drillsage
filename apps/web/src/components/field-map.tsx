"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { HazardCode } from "@/components/hazard";
import { hours, int, metres } from "@/lib/format";
import { boundsOf, mercatorPx, niceLength, project } from "@/lib/geo";
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
function slots(
  wells: readonly MapWell[],
): { e: number; n: number; label: string; bores: number }[] {
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
      bores: g.names.length,
      label: g.names.length > 1 ? `${base} · ${g.names.length} bores` : base,
    };
  });
}

/** Tiles shipped in /public/basemap: NASA Blue Marble with bathymetry, zoom 5, x 15-17, y 8-10. */
const TILE_ZOOM = 5;
const TILE_X0 = 15;
const TILE_Y0 = 8;
const TILES = [0, 1, 2].flatMap((j) => [0, 1, 2].map((i) => [i, j] as const));
const PLACES = [
  { name: "Norway", lat: 60.8, lon: 7.5 },
  { name: "Denmark", lat: 56.2, lon: 9.1 },
  { name: "UK", lat: 57.2, lon: -3.8 },
] as const;

function local(lat: number, lon: number): [number, number] {
  const [x, y] = mercatorPx(lat, lon, TILE_ZOOM);
  return [x - TILE_X0 * 256, y - TILE_Y0 * 256];
}

/** Where on Earth this is: real satellite imagery with a pin on the field. */
function Locator({ lat, lon, field }: { lat: number; lon: number; field: string }) {
  const [px, py] = local(lat, lon);
  const w = 440;
  const h = 330;
  return (
    <figure className="brutal pointer-events-none absolute top-3 left-3 z-[1] w-40 bg-background md:w-56">
      <svg viewBox={`${px - w / 2} ${py - h / 2} ${w} ${h}`} className="block w-full" aria-hidden>
        {TILES.map(([i, j]) => (
          <image
            key={`${i}-${j}`}
            href={`/basemap/bm5-${TILE_X0 + i}-${TILE_Y0 + j}.jpg`}
            x={i * 256}
            y={j * 256}
            width={256.5}
            height={256.5}
            className="dark:[filter:saturate(1.35)_contrast(1.1)_brightness(0.85)]"
          />
        ))}
        {PLACES.map((p) => {
          const [x, y] = local(p.lat, p.lon);
          return (
            <text
              key={p.name}
              x={x}
              y={y}
              textAnchor="middle"
              className="fill-white font-mono text-[15px] uppercase"
              style={{
                letterSpacing: "0.12em",
                paintOrder: "stroke",
                stroke: "#0008",
                strokeWidth: 3,
              }}
            >
              {p.name}
            </text>
          );
        })}
        <circle
          cx={px}
          cy={py}
          r={9}
          fill="var(--brand)"
          className="animate-ping"
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
        />
        <circle cx={px} cy={py} r={6} fill="var(--brand)" stroke="#0a0a0b" strokeWidth={2} />
      </svg>
      <figcaption className="label flex items-center justify-between gap-2 border-t bg-background px-2 py-1">
        <span className="text-foreground">{field} &middot; North Sea</span>
        <span className="text-[9px] text-muted-foreground normal-case">NASA</span>
      </figcaption>
    </figure>
  );
}

/** A banner plane and a supply ship crossing the map: team branding, drawn, not data. */
function SkyAndSea() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-[2]">
      <div className="fly absolute top-[9%] left-0 flex items-center">
        <div className="bob flex items-center">
          <div className="banner flex items-center gap-2 border-2 border-foreground bg-brand px-3 py-0.5 font-glitch text-sm whitespace-nowrap text-brand-foreground shadow-[3px_3px_0_0_var(--foreground)] md:text-lg">
            CodeY &middot; SIH 2026
          </div>
          <div className="h-px w-8 bg-foreground" />
          <svg viewBox="0 0 66 28" className="w-14 md:w-16">
            <path
              d="M8 13 L3 4 L11 4 L16 12 Z"
              fill="var(--brand)"
              stroke="var(--foreground)"
              strokeWidth={1.5}
              strokeLinejoin="round"
            />
            <path
              d="M4 14 C 12 10, 42 9, 56 12 L 61 14 L 56 16 C 42 19, 12 18, 4 14 Z"
              fill="var(--surface)"
              stroke="var(--foreground)"
              strokeWidth={1.5}
              strokeLinejoin="round"
            />
            <path d="M12 14 H52" stroke="var(--brand-text)" strokeWidth={1.5} />
            <path d="M44 11.2 L51 12.3 L49 13.4 L43.5 13 Z" fill="var(--foreground)" />
            <path
              d="M26 15 L35 15 L31 25 L24 25 Z"
              fill="var(--surface)"
              stroke="var(--foreground)"
              strokeWidth={1.5}
              strokeLinejoin="round"
            />
            <ellipse
              className="prop"
              cx={62.5}
              cy={14}
              rx={1.4}
              ry={8}
              fill="var(--foreground)"
              opacity={0.7}
            />
          </svg>
        </div>
      </div>

      <div className="sail absolute top-[74%] left-0">
        <svg viewBox="0 0 150 40" className="w-28 md:w-36">
          <path
            d="M78 8 L150 -6 M78 32 L150 46"
            stroke="#fff"
            strokeOpacity={0.55}
            strokeWidth={1.5}
            strokeDasharray="5 5"
          />
          <path
            d="M78 12 L120 6 M78 28 L120 34"
            stroke="#fff"
            strokeOpacity={0.35}
            strokeWidth={1}
          />
          <path
            d="M4 20 L18 9 L72 9 Q80 9 80 20 Q80 31 72 31 L18 31 Z"
            fill="var(--foreground)"
            stroke="var(--background)"
            strokeWidth={1.2}
          />
          <rect x={19} y={12} width={14} height={16} fill="var(--brand)" />
          <rect
            x={36}
            y={13}
            width={38}
            height={14}
            fill="none"
            stroke="var(--background)"
            strokeOpacity={0.5}
          />
          <text
            x={55}
            y={23.5}
            textAnchor="middle"
            className="fill-background font-mono text-[8px]"
            style={{ letterSpacing: "0.1em" }}
          >
            CodeY
          </text>
        </svg>
      </div>
    </div>
  );
}

export function FieldMap({
  wells,
  events,
  origin,
}: {
  wells: MapWell[];
  events: MapEvent[];
  origin: { lat: number; lon: number; field: string };
}) {
  const router = useRouter();
  const [active, setActive] = useState<Set<HazardKey>>(() => new Set(GEOLOGICAL_KEYS));
  const [hoverWell, setHoverWell] = useState<string | null>(null);
  const [hoverEvent, setHoverEvent] = useState<MapEvent | null>(null);

  const proj = useMemo(() => project(boundsOf(wells.flatMap((w) => w.path)), WIDTH), [wells]);
  const slotMarks = useMemo(() => slots(wells), [wells]);
  const visible = events.filter((e) => active.has(e.hazard as HazardKey));
  const bar = niceLength((WIDTH * proj.scale) / 6);
  const busiest = [...slotMarks].sort((a, b) => b.bores - a.bores)[0];
  const radarAt = busiest
    ? { left: (proj.x(busiest.e) / WIDTH) * 100, top: (proj.y(busiest.n) / proj.height) * 100 }
    : null;

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
      <div className="sea @container relative overflow-hidden border">
        <div className="grid-paper absolute inset-0 opacity-60" aria-hidden />
        {radarAt && (
          <div
            aria-hidden
            className="pointer-events-none absolute aspect-square w-[150%] -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${radarAt.left}%`, top: `${radarAt.top}%` }}
          >
            <div className="sonar-rings absolute inset-0 rounded-full" />
            <div className="radar absolute inset-0 rounded-full" />
          </div>
        )}
        <Locator lat={origin.lat} lon={origin.lon} field={origin.field} />
        <SkyAndSea />
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
