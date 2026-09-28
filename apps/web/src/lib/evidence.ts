/** Split report text into plain and highlighted segments from (possibly overlapping) spans. */
export interface Segment {
  text: string;
  hit: boolean;
}

export interface SpanLike {
  start: number;
  end: number;
}

export function mergeSpans(spans: readonly SpanLike[], length: number): SpanLike[] {
  const sorted = spans
    .map((s) => ({ start: Math.max(0, s.start), end: Math.min(length, s.end) }))
    .filter((s) => s.end > s.start)
    .sort((a, b) => a.start - b.start);
  const merged: SpanLike[] = [];
  for (const s of sorted) {
    const last = merged.at(-1);
    if (last && s.start <= last.end) last.end = Math.max(last.end, s.end);
    else merged.push({ ...s });
  }
  return merged;
}

export function segments(text: string, spans: readonly SpanLike[]): Segment[] {
  const out: Segment[] = [];
  let at = 0;
  for (const s of mergeSpans(spans, text.length)) {
    if (s.start > at) out.push({ text: text.slice(at, s.start), hit: false });
    out.push({ text: text.slice(s.start, s.end), hit: true });
    at = s.end;
  }
  if (at < text.length) out.push({ text: text.slice(at), hit: false });
  return out;
}

/**
 * A window of about `radius` characters either side of the first highlight, so a card can
 * quote the trigger without printing a whole 1,000-character report line.
 */
export function excerpt(
  text: string,
  spans: readonly SpanLike[],
  radius = 160,
): { text: string; spans: SpanLike[]; clippedStart: boolean; clippedEnd: boolean } {
  const merged = mergeSpans(spans, text.length);
  const first = merged[0];
  if (text.length <= radius * 2 || !first) {
    const end = Math.min(text.length, radius * 2);
    return {
      text: text.slice(0, end),
      spans: merged.filter((s) => s.end <= end),
      clippedStart: false,
      clippedEnd: end < text.length,
    };
  }
  const start = Math.max(0, first.start - radius);
  const end = Math.min(text.length, first.end + radius);
  return {
    text: text.slice(start, end),
    spans: merged
      .filter((s) => s.start >= start && s.end <= end)
      .map((s) => ({ start: s.start - start, end: s.end - start })),
    clippedStart: start > 0,
    clippedEnd: end < text.length,
  };
}
