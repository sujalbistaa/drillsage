/**
 * Look-ahead strip maths (pure). Offset events are compared with the active well by TVDSS,
 * never by MD or RKB depth (CLAUDE.md §4).
 *
 * This is an evidence view, not the Phase 4 risk model: it counts what offset wells reported
 * at each depth and shows which of them were finished before this well started.
 */
export interface DepthEvent {
  id: number;
  wellbore: string;
  hazard: string;
  geological: boolean;
  tvdss_top_m: number | null;
  npt_h: number;
}

export interface OffsetInfo {
  name: string;
  surface_distance_m: number;
  completed_before_spud: boolean;
}

export interface OffsetSelection {
  radiusM: number;
  /** Include wells finished after this one started (hindsight). Off by default: honest. */
  hindsight: boolean;
}

export function selectOffsets(offsets: readonly OffsetInfo[], sel: OffsetSelection): Set<string> {
  return new Set(
    offsets
      .filter((o) => o.surface_distance_m <= sel.radiusM)
      .filter((o) => sel.hindsight || o.completed_before_spud)
      .map((o) => o.name),
  );
}

export interface Bin {
  topM: number;
  counts: Map<string, number>;
  total: number;
}

/** Geological offset events per `stepM` TVDSS bin, from `fromM` to `toM`. */
export function binEvents(
  events: readonly DepthEvent[],
  fromM: number,
  toM: number,
  stepM: number,
): Bin[] {
  const bins: Bin[] = [];
  for (let top = fromM; top < toM; top += stepM)
    bins.push({ topM: top, counts: new Map(), total: 0 });
  for (const e of events) {
    if (!e.geological || e.tvdss_top_m == null) continue;
    const i = Math.floor((e.tvdss_top_m - fromM) / stepM);
    const bin = bins[i];
    if (!bin) continue;
    bin.counts.set(e.hazard, (bin.counts.get(e.hazard) ?? 0) + 1);
    bin.total += 1;
  }
  return bins;
}

export function inWindow(
  events: readonly DepthEvent[],
  bitTvdssM: number,
  aheadM: number,
): DepthEvent[] {
  return events
    .filter(
      (e) =>
        e.geological &&
        e.tvdss_top_m != null &&
        e.tvdss_top_m >= bitTvdssM &&
        e.tvdss_top_m <= bitTvdssM + aheadM,
    )
    .sort((a, b) => (a.tvdss_top_m ?? 0) - (b.tvdss_top_m ?? 0));
}

export interface TopLike {
  name: string;
  level: "group" | "formation";
  tvdss_top_m: number | null;
}

export interface Band {
  name: string;
  topM: number;
  baseM: number;
}

/** Formation bands (formation level, else groups) down to `tdM`, each until the next top. */
export function formationBands(tops: readonly TopLike[], tdM: number): Band[] {
  const formations = tops.filter((t) => t.level === "formation" && t.tvdss_top_m != null);
  const chosen = formations.length > 0 ? formations : tops.filter((t) => t.tvdss_top_m != null);
  const sorted = [...chosen].sort((a, b) => (a.tvdss_top_m ?? 0) - (b.tvdss_top_m ?? 0));
  return sorted
    .map((t, i) => ({
      name: t.name,
      topM: t.tvdss_top_m ?? 0,
      baseM: sorted[i + 1]?.tvdss_top_m ?? tdM,
    }))
    .filter((b) => b.baseM > b.topM);
}

export function bandAt(bands: readonly Band[], tvdssM: number): Band | null {
  return bands.find((b) => tvdssM >= b.topM && tvdssM < b.baseM) ?? null;
}
