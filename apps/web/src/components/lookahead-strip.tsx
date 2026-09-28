"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";

import { HazardCode } from "@/components/hazard";
import { hours, int, metres } from "@/lib/format";
import { hazardMeta } from "@/lib/hazards";
import {
  bandAt,
  binEvents,
  formationBands,
  inWindow,
  selectOffsets,
  type DepthEvent,
  type OffsetInfo,
  type TopLike,
} from "@/lib/lookahead";
import { cn } from "@/lib/utils";
import { shortName } from "@/lib/wells";

export interface StripWell {
  name: string;
  tdTvdssM: number;
  waterDepthM: number | null;
  tops: TopLike[];
  offsets: OffsetInfo[];
}

const W = 560;
const H = 880;
const PAD_TOP = 28;
const PAD_BOTTOM = 16;
const BIN_M = 50;
const X_AXIS = 52;
const X_FM = 60;
const W_FM = 170;
const X_HIST = 244;
const W_HIST = 230;
const X_OWN = 494;
const W_OWN = 54;

const AHEAD_OPTIONS = [150, 300, 500] as const;
const RADIUS_OPTIONS = [
  { m: 250, label: "250 m" },
  { m: 1000, label: "1 km" },
  { m: 3000, label: "3 km" },
  { m: Number.POSITIVE_INFINITY, label: "Field" },
] as const;
const PLAY_SECONDS = 16;

function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="label text-muted-foreground">{label}</span>
      <div role="radiogroup" aria-label={label} className="label flex border">
        {options.map((o) => (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={o.value === value}
            onClick={() => onChange(o.value)}
            className={cn(
              "flex-1 px-2 py-1.5 whitespace-nowrap transition-colors",
              o.value === value
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The depth where a window of `aheadM` catches the most offset events: a telling start. */
function busiestDepth(
  events: readonly DepthEvent[],
  fromM: number,
  toM: number,
  aheadM: number,
): number {
  let best = fromM;
  let bestCount = -1;
  for (let d = fromM; d <= toM; d += 25) {
    const n = inWindow(events, d, aheadM).length;
    if (n > bestCount) {
      best = d;
      bestCount = n;
    }
  }
  return best;
}

export function LookaheadStrip({
  well,
  ownEvents,
  fieldEvents,
  formationOrder,
}: {
  well: StripWell;
  ownEvents: DepthEvent[];
  fieldEvents: DepthEvent[];
  formationOrder: string[];
}) {
  const seabed = well.waterDepthM ?? 0;
  const td = Math.max(well.tdTvdssM, seabed + 50);
  const [aheadM, setAheadM] = useState<number>(300);
  const [radiusM, setRadiusM] = useState<number>(Number.POSITIVE_INFINITY);
  const [hindsight, setHindsight] = useState(false);
  const [playing, setPlaying] = useState(false);

  const offsetNames = useMemo(
    () => selectOffsets(well.offsets, { radiusM, hindsight }),
    [well.offsets, radiusM, hindsight],
  );
  const offsetEvents = useMemo(
    () => fieldEvents.filter((e) => offsetNames.has(e.wellbore)),
    [fieldEvents, offsetNames],
  );

  const [bitM, setBitM] = useState(() =>
    busiestDepth(
      fieldEvents.filter((e) =>
        well.offsets.some((o) => o.name === e.wellbore && o.completed_before_spud),
      ),
      seabed,
      Math.max(seabed, td - 100),
      300,
    ),
  );

  const maxDepth = Math.ceil((td + 150) / 250) * 250;
  const y = (m: number) => PAD_TOP + (m / maxDepth) * (H - PAD_TOP - PAD_BOTTOM);
  const bands = useMemo(() => formationBands(well.tops, td), [well.tops, td]);
  const bins = useMemo(() => binEvents(offsetEvents, 0, maxDepth, BIN_M), [offsetEvents, maxDepth]);
  const maxBin = Math.max(1, ...bins.map((b) => b.total));
  const ahead = inWindow(offsetEvents, bitM, aheadM);
  const actual = inWindow(ownEvents, bitM, aheadM);
  const aheadWells = new Set(ahead.map((e) => e.wellbore));
  const aheadNpt = ahead.reduce((sum, e) => sum + e.npt_h, 0);
  const crossing = bands.filter((b) => b.baseM > bitM && b.topM < bitM + aheadM);
  const here = bandAt(bands, bitM);
  const mix = new Map<string, number>();
  for (const e of ahead) mix.set(e.hazard, (mix.get(e.hazard) ?? 0) + 1);

  // Replay: drive the bit from where it is (or the seabed, if already at TD) down to TD.
  const bitRef = useRef(bitM);
  useEffect(() => {
    bitRef.current = bitM;
  }, [bitM]);
  useEffect(() => {
    if (!playing) return;
    let depth = bitRef.current >= td - 1 ? seabed : bitRef.current;
    let last: number | null = null;
    let frame = 0;
    const rate = (td - seabed) / PLAY_SECONDS;
    const step = (now: number) => {
      depth = Math.min(td, depth + (last == null ? 0 : ((now - last) / 1000) * rate));
      last = now;
      setBitM(depth);
      if (depth >= td) setPlaying(false);
      else frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing, td, seabed]);

  const svgRef = useRef<SVGSVGElement>(null);
  const dragging = useRef(false);
  const depthAt = (clientY: number): number => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return bitM;
    const units = ((clientY - rect.top) / rect.height) * H;
    const m = ((units - PAD_TOP) / (H - PAD_TOP - PAD_BOTTOM)) * maxDepth;
    return Math.round(Math.min(td, Math.max(0, m)) / 5) * 5;
  };
  const onPointerDown = (e: PointerEvent<SVGSVGElement>) => {
    dragging.current = true;
    setPlaying(false);
    e.currentTarget.setPointerCapture(e.pointerId);
    setBitM(depthAt(e.clientY));
  };
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    if (dragging.current) setBitM(depthAt(e.clientY));
  };

  const fmColour = (name: string) => {
    const i = formationOrder.indexOf(name);
    return `var(--fm-${(i < 0 ? 0 : i) % 8})`;
  };
  const ticks: number[] = [];
  for (let d = 0; d <= maxDepth; d += 250) ticks.push(d);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,560px)_1fr]">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-2">
          <Segmented
            label="Look ahead"
            options={AHEAD_OPTIONS.map((m) => ({ value: m, label: `${m} m` }))}
            value={aheadM}
            onChange={setAheadM}
          />
          <Segmented
            label="Offset radius"
            options={RADIUS_OPTIONS.map((o) => ({ value: o.m, label: o.label }))}
            value={radiusM}
            onChange={setRadiusM}
          />
          <div className="col-span-2 flex flex-col gap-1.5">
            <label htmlFor="bit-depth" className="label flex justify-between text-muted-foreground">
              <span>Bit depth</span>
              <span className="text-foreground">{metres(Math.round(bitM))} TVDSS</span>
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPlaying((p) => !p)}
                aria-pressed={playing}
                className="label brutal-hover shrink-0 border bg-brand px-3 py-1.5 text-brand-foreground"
              >
                {playing ? "Pause" : "Replay"}
              </button>
              <input
                id="bit-depth"
                type="range"
                min={0}
                max={Math.round(td)}
                step={5}
                value={Math.round(bitM)}
                onChange={(e) => {
                  setPlaying(false);
                  setBitM(Number(e.target.value));
                }}
                className="w-full accent-[var(--brand-text)]"
              />
            </div>
          </div>
        </div>

        <label className="label flex cursor-pointer items-start gap-2 border px-3 py-2">
          <input
            type="checkbox"
            checked={hindsight}
            onChange={(e) => setHindsight(e.target.checked)}
            className="mt-0.5 accent-[var(--warn)]"
          />
          <span className="leading-relaxed">
            Hindsight mode{" "}
            <span className="text-muted-foreground normal-case">
              (also use wells finished after this one started. Off = what the crew could have known
              on the day)
            </span>
          </span>
        </label>

        <div className="relative border bg-surface">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="block w-full cursor-ns-resize touch-none select-none"
            role="img"
            aria-label={`Depth strip for ${well.name}: ${ahead.length} offset events in the ${aheadM} m below the bit`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={() => (dragging.current = false)}
            onPointerCancel={() => (dragging.current = false)}
          >
            <text x={X_FM} y={16} className="fill-muted-foreground font-mono text-[10px] uppercase">
              Formations (this well)
            </text>
            <text
              x={X_HIST}
              y={16}
              className="fill-muted-foreground font-mono text-[10px] uppercase"
            >
              Offset events per {BIN_M} m
            </text>
            <text
              x={X_OWN}
              y={16}
              className="fill-muted-foreground font-mono text-[10px] uppercase"
            >
              Actual
            </text>

            {ticks.map((d) => (
              <g key={d}>
                <line x1={X_AXIS} x2={W} y1={y(d)} y2={y(d)} stroke="var(--hairline)" />
                <text
                  x={X_AXIS - 6}
                  y={y(d) + 3}
                  textAnchor="end"
                  className="fill-muted-foreground font-mono text-[10px]"
                >
                  {int(d)}
                </text>
              </g>
            ))}

            {seabed > 0 && (
              <g>
                <rect
                  x={X_FM}
                  y={y(0)}
                  width={W - X_FM}
                  height={y(seabed) - y(0)}
                  fill="var(--hz-lc)"
                  fillOpacity={0.08}
                />
                <text
                  x={X_FM + 6}
                  y={y(seabed) - 4}
                  className="fill-muted-foreground font-mono text-[9px] uppercase"
                >
                  Sea {metres(seabed)}
                </text>
              </g>
            )}

            {bands.map((b) => {
              const top = y(b.topM);
              const height = Math.max(1, y(b.baseM) - top);
              return (
                <g key={`${b.name}-${b.topM}`}>
                  <rect
                    x={X_FM}
                    y={top}
                    width={W_FM}
                    height={height}
                    fill={fmColour(b.name)}
                    stroke="var(--background)"
                    strokeWidth={0.8}
                  />
                  {height > 13 && (
                    <text
                      x={X_FM + 6}
                      y={top + 11}
                      className="fill-foreground font-mono text-[9.5px]"
                    >
                      {b.name.length > 24 ? `${b.name.slice(0, 23)}…` : b.name}
                    </text>
                  )}
                </g>
              );
            })}

            {bins.map((bin) => {
              let x = X_HIST;
              const top = y(bin.topM) + 0.5;
              const height = Math.max(1, y(bin.topM + BIN_M) - y(bin.topM) - 1);
              return (
                <g key={bin.topM}>
                  {[...bin.counts.entries()].map(([hazard, n]) => {
                    const width = (n / maxBin) * W_HIST;
                    const rect = (
                      <rect
                        key={hazard}
                        x={x}
                        y={top}
                        width={width}
                        height={height}
                        fill={hazardMeta(hazard).color}
                      />
                    );
                    x += width;
                    return rect;
                  })}
                </g>
              );
            })}

            {ownEvents.map((e) =>
              e.tvdss_top_m == null ? null : (
                <rect
                  key={e.id}
                  x={X_OWN}
                  y={y(e.tvdss_top_m) - 2}
                  width={W_OWN}
                  height={4}
                  fill={hazardMeta(e.hazard).color}
                />
              ),
            )}
            <line
              x1={X_OWN - 6}
              x2={X_OWN - 6}
              y1={y(0)}
              y2={y(td)}
              stroke="var(--foreground)"
              strokeWidth={2}
            />
            <text
              x={X_OWN - 10}
              y={y(td) + 12}
              textAnchor="end"
              className="fill-foreground font-mono text-[9px] uppercase"
            >
              TD {int(td)}
            </text>

            <rect
              x={X_FM - 4}
              y={y(bitM)}
              width={W - X_FM}
              height={Math.max(2, y(bitM + aheadM) - y(bitM))}
              fill="var(--brand)"
              fillOpacity={0.16}
              stroke="var(--brand-text)"
              strokeDasharray="5 4"
            />
            <line
              x1={X_AXIS - 44}
              x2={W}
              y1={y(bitM)}
              y2={y(bitM)}
              stroke="var(--brand-text)"
              strokeWidth={2.5}
            />
            <path
              d={`M${X_AXIS - 44} ${y(bitM) - 9} h16 l-8 10 z`}
              fill="var(--brand)"
              stroke="var(--border)"
            />
          </svg>
          <p className="label border-t px-3 py-2 text-muted-foreground">
            Drag on the strip or use the slider. Depths are TVDSS, metres below sea level.
          </p>
        </div>
      </div>

      <section
        aria-live="polite"
        aria-label="Ahead of the bit"
        className="flex flex-col gap-5 xl:sticky xl:top-36 xl:self-start"
      >
        <div
          className={cn(
            "brutal p-5",
            ahead.length > 0 ? "bg-brand text-brand-foreground" : "bg-surface",
          )}
        >
          <p className="label opacity-70">Ahead of the bit &middot; next {aheadM} m</p>
          <div className="mt-2 flex items-end gap-4">
            <span className="headline text-8xl leading-none">{ahead.length}</span>
            <span className="pb-2 text-lg leading-tight font-semibold">
              {ahead.length === 1 ? "offset event" : "offset events"}
              <br />
              <span className="font-normal opacity-80">
                in {aheadWells.size} {aheadWells.size === 1 ? "well" : "wells"} &middot;{" "}
                {hours(aheadNpt)} lost
              </span>
            </span>
          </div>
          {ahead.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              Clear ahead: no selected offset well reported a geological problem in this window.
            </p>
          )}
          {mix.size > 0 && (
            <div className="mt-4 flex h-3 w-full overflow-hidden border border-current">
              {[...mix.entries()].map(([hazard, n]) => (
                <span
                  key={hazard}
                  title={`${hazardMeta(hazard).label}: ${n}`}
                  style={{
                    width: `${(n / ahead.length) * 100}%`,
                    background: hazardMeta(hazard).color,
                  }}
                />
              ))}
            </div>
          )}
        </div>

        <dl className="grid grid-cols-2 border">
          <div className="border-r p-3">
            <dt className="label text-muted-foreground">Bit is in</dt>
            <dd className="mt-1 font-semibold">{here?.name ?? "—"}</dd>
          </div>
          <div className="p-3">
            <dt className="label text-muted-foreground">Crossing next</dt>
            <dd className="mt-1 font-semibold">
              {crossing
                .filter((b) => b.name !== here?.name)
                .map((b) => b.name)
                .join(", ") || "—"}
            </dd>
          </div>
          <div className="col-span-2 border-t p-3">
            <dt className="label text-muted-foreground">
              Offsets in play: {offsetNames.size} of {well.offsets.length}
            </dt>
            <dd className="mt-2 flex flex-wrap gap-1">
              {well.offsets
                .filter((o) => offsetNames.has(o.name))
                .map((o) => (
                  <span
                    key={o.name}
                    className={cn(
                      "label border px-1.5 py-0.5",
                      aheadWells.has(o.name) && "border-foreground bg-foreground text-background",
                    )}
                  >
                    {shortName(o.name)}
                  </span>
                ))}
              {offsetNames.size === 0 && (
                <span className="text-sm text-muted-foreground">
                  No well in this radius finished before this one started. Try a wider radius or
                  hindsight mode.
                </span>
              )}
            </dd>
          </div>
        </dl>

        {ahead.length > 0 && (
          <ol className="flex flex-col border">
            {ahead.slice(0, 8).map((e) => (
              <li key={e.id} className="border-b last:border-b-0">
                <Link
                  href={`/events/${e.id}`}
                  className="grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3 py-2 hover:bg-surface"
                >
                  <HazardCode hazard={e.hazard} />
                  <span className="text-sm">
                    {shortName(e.wellbore)}
                    <span className="label ml-2 text-muted-foreground">
                      {metres(e.tvdss_top_m)}
                    </span>
                  </span>
                  <span className="label text-muted-foreground">{hours(e.npt_h)} &rarr;</span>
                </Link>
              </li>
            ))}
            {ahead.length > 8 && (
              <li className="label px-3 py-2 text-muted-foreground">
                + {ahead.length - 8} more in this window
              </li>
            )}
          </ol>
        )}

        <div className="border border-dashed p-4">
          <p className="label text-muted-foreground">
            Hindsight check &middot; what {shortName(well.name)} actually hit here
          </p>
          {actual.length > 0 ? (
            <p className="mt-2 flex flex-wrap items-center gap-2">
              {actual.map((e) => (
                <Link
                  key={e.id}
                  href={`/events/${e.id}`}
                  title={`${hazardMeta(e.hazard).label} at ${metres(e.tvdss_top_m)}`}
                >
                  <HazardCode hazard={e.hazard} />
                </Link>
              ))}
            </p>
          ) : (
            <p className="mt-2 text-sm">Nothing reported by this well in this window.</p>
          )}
        </div>
      </section>
    </div>
  );
}
