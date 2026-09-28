import { excerpt, segments, type SpanLike } from "@/lib/evidence";

/** Report text with the trigger phrases highlighted; `clip` quotes a window around them. */
export function EvidenceText({
  text,
  spans,
  clip,
}: {
  text: string;
  spans: readonly SpanLike[];
  clip?: boolean;
}) {
  const view = clip
    ? excerpt(text, spans)
    : { text, spans, clippedStart: false, clippedEnd: false };
  if (!view.text) return <span className="text-muted-foreground italic">(no comment text)</span>;
  return (
    <>
      {view.clippedStart && "…"}
      {segments(view.text, view.spans).map((s, i) =>
        s.hit ? (
          <mark key={i} className="hl">
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
      {view.clippedEnd && "…"}
    </>
  );
}
