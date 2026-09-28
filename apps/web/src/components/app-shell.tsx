import Link from "next/link";
import type { ReactNode } from "react";

import { Nav } from "@/components/nav";
import { StatusPill } from "@/components/status-pill";
import { ThemeToggle } from "@/components/theme-toggle";
import { Ticker } from "@/components/ticker";
import { Wordmark } from "@/components/wordmark";
import { fetchField } from "@/lib/api/field";
import { fetchSystemStatus } from "@/lib/api/system-status";
import { VOLVE_ATTRIBUTION } from "@/lib/constants";
import { day, hours, int } from "@/lib/format";

async function tickerItems(): Promise<string[]> {
  const field = await fetchField();
  if (!field.ok) return ["No field snapshot yet", "Run make snapshot", "Then refresh"];
  const s = field.data.stats;
  return [
    `${int(s.events)} drilling problems extracted`,
    `${hours(s.npt_h)} of lost time, located`,
    `${s.wellbores} wellbores`,
    `${int(s.reports)} daily reports read`,
    `${int(s.activities)} report lines`,
    "Every event linked to its report line",
    `${field.data.field} field, North Sea`,
    "Built for Oil India",
    "SIH26121",
  ];
}

export async function AppShell({ children }: { children: ReactNode }) {
  const [status, items, field] = await Promise.all([
    fetchSystemStatus(),
    tickerItems(),
    fetchField(),
  ]);

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="label sr-only z-50 bg-brand px-3 py-2 text-brand-foreground focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur-md">
        <div className="flex items-stretch justify-between gap-2">
          <div className="flex items-stretch">
            <Link
              href="/"
              aria-label="DrillSage home"
              className="flex items-center border-r px-3 py-2.5 md:px-5"
            >
              <Wordmark />
            </Link>
            <div className="hidden md:flex">
              <Nav />
            </div>
          </div>
          <div className="flex items-center gap-2 pr-3 md:pr-5">
            <StatusPill status={status} />
            <ThemeToggle />
          </div>
        </div>
        <div className="border-t md:hidden">
          <Nav />
        </div>
        <Ticker items={items} />
      </header>

      <main id="main" className="w-full flex-1">
        {children}
      </main>

      <footer className="relative mt-24 overflow-hidden border-t">
        <div className="mx-auto grid max-w-[1400px] gap-8 px-4 pt-10 pb-6 md:grid-cols-3 md:px-8">
          <div className="flex flex-col gap-3">
            <Wordmark />
            <p className="font-serif text-2xl leading-tight italic">
              Drishti (foresight) for every well you drill.
            </p>
          </div>
          <div className="label flex flex-col gap-1.5 text-muted-foreground">
            <span>Smart India Hackathon 2026</span>
            <span>Problem statement SIH26121</span>
            <span>Oil India Limited</span>
          </div>
          <div className="label flex flex-col gap-1.5 text-muted-foreground">
            {field.ok ? (
              <>
                <span>Snapshot {day(field.data.generated_at)}</span>
                <span>Extractor {field.data.extractor_version}</span>
                <span>Basin pack {field.data.basin_pack}</span>
              </>
            ) : (
              <span>No snapshot loaded</span>
            )}
          </div>
        </div>
        <p className="mx-auto max-w-[1400px] px-4 pb-6 text-xs text-muted-foreground md:px-8">
          {VOLVE_ATTRIBUTION}
        </p>
        <div
          aria-hidden
          className="melt outline-text pointer-events-none -mb-[0.18em] px-2 text-center text-[20vw] leading-none uppercase select-none"
        >
          Drishti
        </div>
      </footer>
    </div>
  );
}
