import { describe, expect, it } from "vitest";

import { boundsOf, niceLength, project } from "./geo";
import { density, holeInches, hours, metres } from "./format";
import { hazardMeta, isHazardKey } from "./hazards";
import { findBySlug, shortName, wellSlug } from "./wells";

describe("format", () => {
  it("speaks driller units", () => {
    expect(holeInches(0.2159)).toBe("8½″");
    expect(holeInches(0.3111)).toBe("12¼″");
    expect(holeInches(0.4445)).toBe("17½″");
    expect(holeInches(null)).toBeNull();
    expect(density(1.5)).toBe("1.50 sg");
    expect(metres(2768.4)).toBe("2,768 m");
    expect(metres(null)).toBe("n/a");
    expect(hours(4.5)).toBe("4.5 h");
    expect(hours(66)).toBe("66 h");
  });
});

describe("wells", () => {
  it("round-trips wellbore names through slugs", () => {
    const wells = [{ name: "15/9-F-1" }, { name: "15/9-F-1 A" }, { name: "15/9-19 BT2" }];
    expect(wells.map((w) => wellSlug(w.name))).toEqual(["15-9-f-1", "15-9-f-1-a", "15-9-19-bt2"]);
    expect(findBySlug(wells, "15-9-f-1-a")?.name).toBe("15/9-F-1 A");
    expect(findBySlug(wells, "nope")).toBeNull();
    expect(shortName("15/9-F-12")).toBe("F-12");
  });
});

describe("hazards", () => {
  it("knows the taxonomy and degrades gracefully", () => {
    expect(isHazardKey("STUCK_PIPE")).toBe(true);
    expect(isHazardKey("toString")).toBe(false);
    expect(hazardMeta("KICK").code).toBe("??");
  });
});

describe("geo", () => {
  it("projects north-up at equal scale", () => {
    const p = project(
      boundsOf(
        [
          [0, 0],
          [1000, 500],
        ],
        0,
      ),
      100,
    );
    expect(p.scale).toBe(10);
    expect(p.height).toBe(50);
    expect([p.x(1000), p.y(500)]).toEqual([100, 0]);
    expect(niceLength(730)).toBe(1000);
    expect(niceLength(180)).toBe(200);
  });
});
