/**
 * Retry an API call while the API is waking up.
 *
 * Free hosting puts the API to sleep when idle. While it wakes, the host's proxy answers with
 * 502/503/504 (or the connection fails) for up to a minute. Instead of showing "no signal" on
 * the first failure, keep trying until `budgetMs` runs out.
 */
export interface Attempt<T> {
  data?: T;
  error?: unknown;
  response: { status: number };
}

const WAKING = new Set([502, 503, 504]);

export interface RetryOptions {
  budgetMs: number;
  pauseMs?: number;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
}

export type Outcome<T> =
  | { kind: "data"; data: T }
  | { kind: "error"; error: unknown; status: number }
  | { kind: "unreachable" };

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export async function untilAwake<T>(
  call: (signal: AbortSignal) => Promise<Attempt<T>>,
  { budgetMs, pauseMs = 2_000, now = Date.now, sleep = defaultSleep }: RetryOptions,
): Promise<Outcome<T>> {
  const deadline = now() + budgetMs;
  for (;;) {
    const remaining = deadline - now();
    let waking: boolean;
    try {
      const attempt = await call(AbortSignal.timeout(Math.max(1, remaining)));
      if (attempt.data !== undefined) return { kind: "data", data: attempt.data };
      if (!WAKING.has(attempt.response.status)) {
        return { kind: "error", error: attempt.error, status: attempt.response.status };
      }
      waking = true;
    } catch {
      waking = false;
    }
    if (deadline - now() <= pauseMs) {
      return waking ? { kind: "error", error: undefined, status: 503 } : { kind: "unreachable" };
    }
    await sleep(pauseMs);
  }
}
