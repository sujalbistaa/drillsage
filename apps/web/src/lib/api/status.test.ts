import { describe, expect, it } from "vitest";

import type { Readiness, ServiceMeta } from "./client";
import { deriveSystemStatus } from "./status";

const meta: ServiceMeta = {
  name: "DrillSage",
  version: "0.1.0",
  environment: "development",
  local_only: false,
  data_attribution: "Contains data from the Volve field dataset…",
};

const ready: Readiness = { status: "ready", checks: { database: "ok" } };
const notReady: Readiness = { status: "not_ready", checks: { database: "unavailable" } };

describe("deriveSystemStatus", () => {
  it("is operational when the API and every dependency are healthy", () => {
    const status = deriveSystemStatus(meta, ready);
    expect(status.level).toBe("operational");
    expect(status.checks.map((c) => [c.name, c.healthy])).toEqual([
      ["API", true],
      ["Database", true],
    ]);
  });

  it("is degraded when the API answers but a dependency is down", () => {
    const status = deriveSystemStatus(meta, notReady);
    expect(status.level).toBe("degraded");
    expect(status.checks.find((c) => c.name === "Database")).toMatchObject({
      healthy: false,
      detail: "Unavailable",
    });
  });

  it("is degraded when the readiness probe itself fails", () => {
    const status = deriveSystemStatus(meta, null);
    expect(status.level).toBe("degraded");
    expect(status.checks.at(-1)?.name).toBe("Readiness probe");
  });

  it("is down when the API does not answer, regardless of readiness", () => {
    const status = deriveSystemStatus(null, ready);
    expect(status.level).toBe("down");
    expect(status.meta).toBeNull();
    expect(status.checks).toHaveLength(1);
  });

  it("orders dependency checks deterministically and labels unknown ones verbatim", () => {
    const status = deriveSystemStatus(meta, {
      status: "ready",
      checks: { zeta_queue: "ok", database: "ok" },
    });
    expect(status.checks.map((c) => c.name)).toEqual(["API", "Database", "zeta_queue"]);
  });
});
