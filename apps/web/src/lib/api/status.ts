import type { Readiness, ServiceMeta } from "./client";

export type StatusLevel = "operational" | "degraded" | "down";

export interface StatusCheck {
  name: string;
  healthy: boolean;
  detail: string;
}

export interface SystemStatus {
  level: StatusLevel;
  headline: string;
  checks: StatusCheck[];
  meta: ServiceMeta | null;
}

const CHECK_LABELS: Record<string, string> = {
  database: "Database",
  field_snapshot: "Field snapshot",
};

/**
 * Reduce raw API probes to what the operator needs to see.
 *
 * `meta` is null when the API itself did not answer; `readiness` is null when the readiness
 * probe could not be read at all (a 503 still carries a readiness body).
 */
export function deriveSystemStatus(
  meta: ServiceMeta | null,
  readiness: Readiness | null,
): SystemStatus {
  if (meta === null) {
    return {
      level: "down",
      headline: "API unreachable",
      checks: [{ name: "API", healthy: false, detail: "No response from the DrillSage API" }],
      meta: null,
    };
  }

  const dependencyChecks: StatusCheck[] =
    readiness === null
      ? [{ name: "Readiness probe", healthy: false, detail: "Probe did not respond" }]
      : Object.entries(readiness.checks)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([name, state]) => ({
            name: CHECK_LABELS[name] ?? name,
            healthy: state === "ok",
            detail: state === "ok" ? "Connected" : "Unavailable",
          }));

  const checks: StatusCheck[] = [
    { name: "API", healthy: true, detail: `v${meta.version} · ${meta.environment}` },
    ...dependencyChecks,
  ];
  const allHealthy = checks.every((check) => check.healthy);

  return {
    level: allHealthy ? "operational" : "degraded",
    headline: allHealthy ? "All systems operational" : "Degraded: some dependencies unavailable",
    checks,
    meta,
  };
}
