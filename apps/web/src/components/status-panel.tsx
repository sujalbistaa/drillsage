import { CircleCheck, CircleX, TriangleAlert } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { StatusLevel, SystemStatus } from "@/lib/api/status";
import { cn } from "@/lib/utils";

const LEVEL_STYLE: Record<StatusLevel, { dot: string; text: string }> = {
  operational: { dot: "bg-ok", text: "text-ok" },
  degraded: { dot: "bg-warn", text: "text-warn" },
  down: { dot: "bg-danger", text: "text-danger" },
};

export function StatusPanel({ status }: { status: SystemStatus }) {
  const style = LEVEL_STYLE[status.level];

  return (
    <Card aria-labelledby="system-status-title">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle id="system-status-title">System status</CardTitle>
          <span className={cn("flex items-center gap-2 text-sm font-medium", style.text)}>
            <span className="relative flex size-2.5" aria-hidden>
              {status.level === "operational" && (
                <span
                  className={cn(
                    "absolute inline-flex size-full animate-ping rounded-full opacity-60",
                    style.dot,
                  )}
                />
              )}
              <span className={cn("relative inline-flex size-2.5 rounded-full", style.dot)} />
            </span>
            {status.headline}
          </span>
        </div>
        {status.meta?.local_only && (
          <CardDescription>
            Local-only mode: no data leaves this machine; all models run on-premises.
          </CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {status.checks.map((check) => (
            <li key={check.name} className="flex items-center justify-between py-2.5 text-sm">
              <span className="flex items-center gap-2">
                {check.healthy ? (
                  <CircleCheck className="size-4 text-ok" aria-hidden />
                ) : status.level === "down" ? (
                  <CircleX className="size-4 text-danger" aria-hidden />
                ) : (
                  <TriangleAlert className="size-4 text-warn" aria-hidden />
                )}
                {check.name}
                <span className="sr-only">{check.healthy ? "healthy" : "unhealthy"}</span>
              </span>
              <span className="font-mono text-xs text-muted-foreground">{check.detail}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
