/**
 * Runtime configuration.
 *
 * Server components call the API directly. `API_INTERNAL_URL` lets containers use the
 * internal service name; browsers use `NEXT_PUBLIC_API_BASE_URL`.
 */
const DEFAULT_API_BASE_URL = "http://localhost:8000";

export function serverApiBaseUrl(): string {
  return (
    process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL
  );
}

/** Upper bound for server-side API calls made while rendering a page. */
export const SERVER_FETCH_TIMEOUT_MS = 2_500;
