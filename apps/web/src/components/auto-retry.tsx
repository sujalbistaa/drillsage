"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/** Counts down and re-renders the page, so a sleeping hosted API recovers without a click. */
export function AutoRetry({ seconds = 20 }: { seconds?: number }) {
  const router = useRouter();
  const [left, setLeft] = useState(seconds);

  useEffect(() => {
    const tick = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1_000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    if (left > 0) return;
    router.refresh();
    setLeft(seconds);
  }, [left, router, seconds]);

  return (
    <p className="label mt-6 flex items-center gap-2 text-muted-foreground" aria-live="polite">
      <span aria-hidden className="size-2 animate-blink bg-warn" />
      Retrying in {left}s
      <button
        type="button"
        onClick={() => setLeft(0)}
        className="ml-2 border px-2 py-0.5 text-foreground hover:bg-brand hover:text-brand-foreground"
      >
        Retry now
      </button>
    </p>
  );
}
