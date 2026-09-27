import "server-only";

import { SERVER_FETCH_TIMEOUT_MS } from "@/lib/config";

import { serverApiClient, type Readiness, type ServiceMeta } from "./client";
import { deriveSystemStatus, type SystemStatus } from "./status";

async function probeMeta(): Promise<ServiceMeta | null> {
  try {
    const { data } = await serverApiClient().GET("/api/v1/meta", {
      signal: AbortSignal.timeout(SERVER_FETCH_TIMEOUT_MS),
    });
    return data ?? null;
  } catch {
    return null; // network error or timeout: the API is unreachable
  }
}

async function probeReadiness(): Promise<Readiness | null> {
  try {
    // A 503 is an expected answer here: the body still describes which checks failed.
    const { data, error } = await serverApiClient().GET("/readyz", {
      signal: AbortSignal.timeout(SERVER_FETCH_TIMEOUT_MS),
    });
    return data ?? error ?? null;
  } catch {
    return null;
  }
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const [meta, readiness] = await Promise.all([probeMeta(), probeReadiness()]);
  return deriveSystemStatus(meta, readiness);
}
