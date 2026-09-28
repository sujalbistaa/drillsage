import { fetchSystemStatus } from "@/lib/api/system-status";
import type { SystemStatus } from "@/lib/api/status";
import { cn } from "@/lib/utils";

const TEXT = {
  operational: "All systems go",
  degraded: "DB offline · snapshot",
  down: "API down",
} as const;

/** Compact live status. The full check list is in the title for the curious. */
export function StatusPill({ status }: { status: SystemStatus }) {
  const detail = status.checks.map((c) => `${c.name}: ${c.detail}`).join("\n");
  return (
    <span
      className="label hidden items-center gap-2 border px-2 py-1 sm:inline-flex"
      title={`${status.headline}\n${detail}`}
    >
      <span
        aria-hidden
        className={cn(
          "size-2",
          status.level === "operational" && "animate-blink bg-ok",
          status.level === "degraded" && "bg-warn",
          status.level === "down" && "bg-danger",
        )}
      />
      {TEXT[status.level]}
      <span className="sr-only">{status.headline}</span>
    </span>
  );
}

/** Fetches its own status so a slow readiness probe never holds up the page. */
export async function LiveStatusPill() {
  return <StatusPill status={await fetchSystemStatus()} />;
}

export function StatusPillPlaceholder() {
  return (
    <span className="label hidden items-center gap-2 border px-2 py-1 text-muted-foreground sm:inline-flex">
      <span aria-hidden className="size-2 bg-muted-foreground" />
      Checking
    </span>
  );
}
