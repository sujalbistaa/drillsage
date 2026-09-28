import "server-only";

import { cache } from "react";

import { SERVER_FETCH_TIMEOUT_MS } from "@/lib/config";

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
  reason: "The DrillSage API is not answering. Start it with `make api`.",
};

function problemDetail(error: unknown): string | null {
  if (error && typeof error === "object" && "detail" in error) {
    const { detail } = error as { detail: unknown };
    return typeof detail === "string" ? detail : null;
  }
  return null;
}

/** The field overview, fetched once per render however many components ask for it. */
export const fetchField = cache(async (): Promise<Result<FieldOverview>> => {
  try {
    const { data, error } = await serverApiClient().GET("/api/v1/field", {
      signal: AbortSignal.timeout(SERVER_FETCH_TIMEOUT_MS),
    });
    if (data) return { ok: true, data };
    return { ok: false, reason: problemDetail(error) ?? "The field overview is unavailable." };
  } catch {
    return API_DOWN;
  }
});

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

export async function fetchEvents(filters: EventFilters): Promise<Result<EventPage>> {
  try {
    const { data, error } = await serverApiClient().GET("/api/v1/events", {
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
      signal: AbortSignal.timeout(SERVER_FETCH_TIMEOUT_MS),
    });
    if (data) return { ok: true, data };
    return { ok: false, reason: problemDetail(error) ?? "The event search failed." };
  } catch {
    return API_DOWN;
  }
}

/** One event, or null when it does not exist (a 404 is an answer, not an outage). */
export async function fetchEvent(id: number): Promise<Result<DrillEvent | null>> {
  try {
    const { data, error, response } = await serverApiClient().GET("/api/v1/events/{event_id}", {
      params: { path: { event_id: id } },
      signal: AbortSignal.timeout(SERVER_FETCH_TIMEOUT_MS),
    });
    if (data) return { ok: true, data };
    if (response.status === 404) return { ok: true, data: null };
    return { ok: false, reason: problemDetail(error) ?? "The event is unavailable." };
  } catch {
    return API_DOWN;
  }
}
