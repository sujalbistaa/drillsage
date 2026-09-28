import { describe, expect, it } from "vitest";

import {
  bandAt,
  binEvents,
  formationBands,
  inWindow,
  selectOffsets,
  type DepthEvent,
} from "./lookahead";

const ev = (id: number, tvdss: number | null, wellbore = "A", geological = true): DepthEvent => ({
  id,
  wellbore,
  hazard: "LOST_CIRCULATION",
  geological,
  tvdss_top_m: tvdss,
  npt_h: 1,
});

describe("selectOffsets", () => {
  const offsets = [
    { name: "near-old", surface_distance_m: 10, completed_before_spud: true },
    { name: "near-new", surface_distance_m: 10, completed_before_spud: false },
    { name: "far-old", surface_distance_m: 5000, completed_before_spud: true },
  ];
  it("is honest by default and respects the radius", () => {
    expect([...selectOffsets(offsets, { radiusM: 1000, hindsight: false })]).toEqual(["near-old"]);
    expect(selectOffsets(offsets, { radiusM: Infinity, hindsight: true }).size).toBe(3);
  });
});

describe("binEvents / inWindow", () => {
  const events = [ev(1, 120), ev(2, 149), ev(3, 150), ev(4, null), ev(5, 130, "A", false)];
  it("counts geological events with a depth into their bin", () => {
    const bins = binEvents(events, 0, 300, 50);
    expect(bins.map((b) => b.total)).toEqual([0, 0, 2, 1, 0, 0]);
    expect(bins[2]?.counts.get("LOST_CIRCULATION")).toBe(2);
  });
  it("returns the events between the bit and the look-ahead depth, shallow first", () => {
    expect(inWindow(events, 125, 30).map((e) => e.id)).toEqual([2, 3]);
    expect(inWindow(events, 500, 100)).toEqual([]);
  });
});

describe("formationBands", () => {
  it("uses formation tops, each band ending at the next top or TD", () => {
    const bands = formationBands(
      [
        { name: "Grid Fm", level: "formation", tvdss_top_m: 100 },
        { name: "Hordaland Gp", level: "group", tvdss_top_m: 50 },
        { name: "Balder Fm", level: "formation", tvdss_top_m: 300 },
      ],
      400,
    );
    expect(bands).toEqual([
      { name: "Grid Fm", topM: 100, baseM: 300 },
      { name: "Balder Fm", topM: 300, baseM: 400 },
    ]);
    expect(bandAt(bands, 350)?.name).toBe("Balder Fm");
    expect(bandAt(bands, 50)).toBeNull();
  });
  it("falls back to groups when a well has no formation tops", () => {
    expect(
      formationBands([{ name: "Viking Gp", level: "group", tvdss_top_m: 10 }], 20),
    ).toHaveLength(1);
  });
});
