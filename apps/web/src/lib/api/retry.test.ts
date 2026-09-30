import { describe, expect, it } from "vitest";

import { untilAwake, type Attempt } from "./retry";

/** A fake clock: `sleep` advances time instantly. */
function clock() {
  let t = 0;
  return { now: () => t, sleep: async (ms: number) => void (t += ms) };
}

describe("untilAwake", () => {
  it("keeps trying through 503s and connection failures until the API answers", async () => {
    const replies: (Attempt<string> | Error)[] = [
      new Error("ECONNREFUSED"),
      { response: { status: 503 } },
      { response: { status: 502 } },
      { data: "field", response: { status: 200 } },
    ];
    let calls = 0;
    const outcome = await untilAwake(
      async () => {
        const reply = replies[calls++];
        if (!reply || reply instanceof Error) throw reply ?? new Error("none");
        return reply;
      },
      { budgetMs: 60_000, ...clock() },
    );
    expect(outcome).toEqual({ kind: "data", data: "field" });
    expect(calls).toBe(4);
  });

  it("returns a real error at once instead of retrying it", async () => {
    let calls = 0;
    const outcome = await untilAwake<string>(
      async () => {
        calls++;
        return { error: { detail: "No event 9" }, response: { status: 404 } };
      },
      { budgetMs: 60_000, ...clock() },
    );
    expect(outcome).toEqual({ kind: "error", error: { detail: "No event 9" }, status: 404 });
    expect(calls).toBe(1);
  });

  it("gives up when the budget runs out", async () => {
    const outcome = await untilAwake<string>(
      async () => {
        throw new Error("down");
      },
      { budgetMs: 10_000, pauseMs: 2_000, ...clock() },
    );
    expect(outcome).toEqual({ kind: "unreachable" });
  });
});
