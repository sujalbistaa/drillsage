import "server-only";

import createClient from "openapi-fetch";

import { serverApiBaseUrl } from "@/lib/config";

import type { components, paths } from "./schema";

/** Typed API client for server components. Types come only from the generated schema. */
export function serverApiClient() {
  return createClient<paths>({ baseUrl: serverApiBaseUrl(), cache: "no-store" });
}

export type ServiceMeta = components["schemas"]["ServiceMeta"];
export type Readiness = components["schemas"]["Readiness"];
export type FieldOverview = components["schemas"]["FieldOverview"];
export type Wellbore = components["schemas"]["WellboreOut"];
export type EventPoint = components["schemas"]["EventPoint"];
export type DrillEvent = components["schemas"]["EventOut"];
export type EventPage = components["schemas"]["EventPage"];
export type EventSort = components["schemas"]["EventSort"];
export type EvidenceLine = components["schemas"]["EvidenceLine"];
export type HazardSummary = components["schemas"]["HazardSummary"];
export type FormationUnit = components["schemas"]["FormationUnit"];
export type FormationTop = components["schemas"]["TopOut"];
