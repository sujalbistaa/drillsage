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
