import { describe, expect, it } from "vitest";

import { excerpt, mergeSpans, segments } from "./evidence";

describe("segments", () => {
  it("merges overlapping spans and keeps every character", () => {
    const text = "Observed losses of 10 m3/h at 2500 m.";
    const parts = segments(text, [
      { start: 9, end: 15 },
      { start: 12, end: 18 },
    ]);
    expect(parts.map((p) => p.text).join("")).toBe(text);
    expect(parts.filter((p) => p.hit).map((p) => p.text)).toEqual(["losses of"]);
  });
  it("clamps spans outside the text", () => {
    expect(mergeSpans([{ start: -3, end: 99 }], 10)).toEqual([{ start: 0, end: 10 }]);
  });
});

describe("excerpt", () => {
  it("quotes a window around the first highlight and shifts the spans", () => {
    const text = `${"a".repeat(500)}STUCK${"b".repeat(500)}`;
    const view = excerpt(text, [{ start: 500, end: 505 }], 20);
    expect(view.clippedStart && view.clippedEnd).toBe(true);
    const span = view.spans[0];
    expect(span && view.text.slice(span.start, span.end)).toBe("STUCK");
  });
  it("returns short text whole", () => {
    expect(excerpt("short", [], 20)).toMatchObject({ text: "short", clippedEnd: false });
  });
});
