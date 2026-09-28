/**
 * Runtime configuration.
 *
 * Server components call the API directly. `API_INTERNAL_URL` lets containers use the
 * internal service name; browsers use `NEXT_PUBLIC_API_BASE_URL`. On Render, the blueprint
 * passes the API service's host as `API_RENDER_HOST` and its public URL is derived from it.
 */
const DEFAULT_API_BASE_URL = "http://localhost:8000";

export function serverApiBaseUrl(
  env: Readonly<Record<string, string | undefined>> = process.env,
): string {
  if (env.API_INTERNAL_URL) return env.API_INTERNAL_URL;
  if (env.API_RENDER_HOST) return `https://${env.API_RENDER_HOST}.onrender.com`;
  return env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL;
}

/**
 * Upper bound for server-side API calls made while rendering a page. Hosted free tiers put the
 * API to sleep, so deployments raise it with `API_TIMEOUT_MS` to survive a cold start.
 */
export const SERVER_FETCH_TIMEOUT_MS = Number(process.env.API_TIMEOUT_MS) || 2_500;
