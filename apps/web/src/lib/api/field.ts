import "server-only";

import { cache } from "react";

import { SERVER_FETCH_TIMEOUT_MS } from "@/lib/config";

import { untilAwake, type Attempt } from "./retry";

import {
  serverApiClient,
  type DrillEvent,
  type EventPage,
  type EventSort,
  type FieldOverview,
} from "./client";

/** A fetch that did not produce data: why, in words an operator can act on. */
export interface Unavailable {
  ok: false;
  reason: string;
}

export type Result<T> = { ok: true; data: T } | Unavailable;

const API_DOWN: Unavailable = {
  ok: false,
  reason:
    "The DrillSage API is not answering. On the hosted demo it sleeps when idle and takes about a minute to wake; this page keeps retrying. Locally, start it with `make ui`.",
};

function problemDetail(error: unknown): string | null {
  if (error && typeof error === "object" && "detail" in error) {
    const { detail } = error as { detail: unknown };
    return typeof detail === "string" ? detail : null;
  }
  return null;
}

/** Call the API, riding out a cold start, and turn the outcome into data or a reason. */
async function awake<T>(
  call: (signal: AbortSignal) => Promise<Attempt<T>>,
  fallback: string,
): Promise<Result<T> | { ok: false; status: number; reason: string }> {
  const outcome = await untilAwake(call, { budgetMs: SERVER_FETCH_TIMEOUT_MS });
  switch (outcome.kind) {
    case "data":
      return { ok: true, data: outcome.data };
    case "unreachable":
      return API_DOWN;
    case "error":
      return {
        ok: false,
        status: outcome.status,
        reason:
          problemDetail(outcome.error) ?? (outcome.status >= 500 ? API_DOWN.reason : fallback),
      };
  }
}

/** The field overview, fetched once per render however many components ask for it. */
export const fetchField = cache((): Promise<Result<FieldOverview>> =>
  awake(
    (signal) => serverApiClient().GET("/api/v1/field", { signal }),
    "The field overview is unavailable.",
  ),
);

export interface EventFilters {
  hazard?: string;
  wellbore?: string;
  geological?: boolean;
  severityMin?: number;
  q?: string;
  sort?: EventSort;
  offset?: number;
  limit?: number;
}

export function fetchEvents(filters: EventFilters): Promise<Result<EventPage>> {
  return awake(
    (signal) =>
      serverApiClient().GET("/api/v1/events", {
        params: {
          query: {
            hazard: filters.hazard,
            wellbore: filters.wellbore,
            geological: filters.geological,
            severity_min: filters.severityMin,
            q: filters.q,
            sort: filters.sort,
            offset: filters.offset,
            limit: filters.limit,
          },
        },
        signal,
      }),
    "The event search failed.",
  );
}

/** One event, or null when it does not exist (a 404 is an answer, not an outage). */
export async function fetchEvent(id: number): Promise<Result<DrillEvent | null>> {
  const result = await awake(
    (signal) =>
      serverApiClient().GET("/api/v1/events/{event_id}", {
        params: { path: { event_id: id } },
        signal,
      }),
    "The event is unavailable.",
  );
  if (!result.ok && "status" in result && result.status === 404) return { ok: true, data: null };
  return result;
}
