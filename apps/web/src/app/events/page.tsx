import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { EventCard } from "@/components/event-card";
import { HazardCode } from "@/components/hazard";
import { NoSignal } from "@/components/no-signal";
import type { EventSort } from "@/lib/api/client";
import { fetchEvents } from "@/lib/api/field";
import { hours, int } from "@/lib/format";
import { HAZARD_KEYS, hazardMeta, isHazardKey } from "@/lib/hazards";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Events" };
export const dynamic = "force-dynamic";

const PAGE_SIZE = 20;
const SORTS: { value: EventSort; label: string }[] = [
  { value: "recent", label: "Recent" },
  { value: "npt", label: "Most hours" },
  { value: "severity", label: "Worst" },
  { value: "depth", label: "Shallow first" },
];
const SEVERITIES = [
  { value: undefined, label: "All" },
  { value: 2, label: "2+" },
  { value: 3, label: "3+" },
  { value: 4, label: "4" },
] as const;

interface Filters {
  well?: string;
  hazard?: string;
  q?: string;
  sort: EventSort;
  sev?: number;
  page: number;
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function parse(raw: Record<string, string | string[] | undefined>): Filters {
  const hazard = first(raw.hazard);
  const sort = first(raw.sort);
  const sev = Number(first(raw.sev));
  const page = Number(first(raw.page));
  return {
    well: first(raw.well)?.trim() || undefined,
    hazard: isHazardKey(hazard) ? hazard : undefined,
    q: first(raw.q)?.trim() || undefined,
    sort: SORTS.some((s) => s.value === sort) ? (sort as EventSort) : "recent",
    sev: sev >= 1 && sev <= 4 ? sev : undefined,
    page: Number.isInteger(page) && page > 1 ? page : 1,
  };
}

function href(f: Filters, patch: Partial<Filters>): string {
  const next = { ...f, page: 1, ...patch };
  const params = new URLSearchParams();
  if (next.well) params.set("well", next.well);
  if (next.hazard) params.set("hazard", next.hazard);
  if (next.q) params.set("q", next.q);
  if (next.sort !== "recent") params.set("sort", next.sort);
  if (next.sev) params.set("sev", String(next.sev));
  if (next.page > 1) params.set("page", String(next.page));
  const qs = params.toString();
  return qs ? `/events?${qs}` : "/events";
}

function Chip({
  href: to,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={to}
      aria-current={active ? "true" : undefined}
      className={cn(
        "label flex items-center gap-2 border px-2 py-1 transition-colors",
        active ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </Link>
  );
}

export default async function EventsPage({ searchParams }: { searchParams: SearchParams }) {
  const f = parse(await searchParams);
  const result = await fetchEvents({
    wellbore: f.well,
    hazard: f.hazard,
    q: f.q,
    sort: f.sort,
    severityMin: f.sev,
    offset: (f.page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  });
  if (!result.ok) return <NoSignal reason={result.reason} />;
  const page = result.data;
  const pages = Math.max(1, Math.ceil(page.total / PAGE_SIZE));

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-10 px-4 pt-10 md:px-8 md:pt-16">
      <header className="grid items-end gap-6 lg:grid-cols-[1fr_auto]">
        <div className="flex flex-col gap-4">
          <h1 className="headline text-[clamp(2rem,8vw,7rem)] uppercase">The logbook.</h1>
          <p className="max-w-2xl text-lg text-pretty text-muted-foreground">
            Every problem DrillSage pulled out of the daily reports, with the words that gave it
            away highlighted in the original text.
          </p>
        </div>
        <div className="brutal bg-surface px-5 py-4">
          <p className="label text-muted-foreground">Matching</p>
          <p className="headline text-6xl">{int(page.total)}</p>
          <p className="label text-brand-text">{hours(page.npt_h)} lost</p>
        </div>
      </header>

      <div className="flex flex-col gap-4 border-y py-5">
        <form action="/events" method="get" role="search" className="flex gap-2">
          {f.well && <input type="hidden" name="well" value={f.well} />}
          {f.hazard && <input type="hidden" name="hazard" value={f.hazard} />}
          {f.sort !== "recent" && <input type="hidden" name="sort" value={f.sort} />}
          {f.sev && <input type="hidden" name="sev" value={f.sev} />}
          <label htmlFor="q" className="sr-only">
            Search report text, wells and formations
          </label>
          <input
            id="q"
            name="q"
            defaultValue={f.q}
            placeholder="search the reports: overpull, LCM, Hugin, F-12…"
            className="w-full border bg-surface px-4 py-3 font-mono text-sm placeholder:text-muted-foreground focus:border-foreground"
          />
          <button
            type="submit"
            className="brutal brutal-hover label shrink-0 bg-brand px-5 text-brand-foreground"
          >
            Search
          </button>
        </form>

        <div className="flex flex-wrap items-center gap-1.5">
          {f.well && (
            <Chip href={href(f, { well: undefined })} active>
              Well {f.well} &times;
            </Chip>
          )}
          <Chip href={href(f, { hazard: undefined })} active={!f.hazard}>
            All hazards
          </Chip>
          {HAZARD_KEYS.map((key) => (
            <Chip
              key={key}
              href={href(f, { hazard: f.hazard === key ? undefined : key })}
              active={f.hazard === key}
            >
              <HazardCode hazard={key} className="h-4 min-w-6 text-[9px]" />
              {hazardMeta(key).short}
            </Chip>
          ))}
        </div>

        <div className="flex flex-wrap gap-6">
          <div className="flex items-center gap-1.5">
            <span className="label mr-1 text-muted-foreground">Sort</span>
            {SORTS.map((s) => (
              <Chip key={s.value} href={href(f, { sort: s.value })} active={f.sort === s.value}>
                {s.label}
              </Chip>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="label mr-1 text-muted-foreground">Severity</span>
            {SEVERITIES.map((s) => (
              <Chip key={s.label} href={href(f, { sev: s.value })} active={f.sev === s.value}>
                {s.label}
              </Chip>
            ))}
          </div>
          {(f.q || f.hazard || f.sev || f.well) && (
            <Link href="/events" className="label self-center text-danger hover:underline">
              Clear all
            </Link>
          )}
        </div>
      </div>

      {page.items.length === 0 ? (
        <div className="border border-dashed px-6 py-16 text-center">
          <p className="headline text-4xl uppercase">Dry hole.</p>
          <p className="mt-3 text-muted-foreground">
            Nothing matches. Loosen a filter or search for something else.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {page.items.map((e) => (
            <EventCard key={e.id} event={e} />
          ))}
        </div>
      )}

      {pages > 1 && (
        <nav aria-label="Pages" className="label flex items-center justify-between border-t pt-5">
          {f.page > 1 ? (
            <Link
              href={href(f, { page: f.page - 1 })}
              className="border px-4 py-2 hover:bg-surface"
            >
              &larr; Prev
            </Link>
          ) : (
            <span />
          )}
          <span className="text-muted-foreground">
            Page {f.page} / {pages}
          </span>
          {f.page < pages ? (
            <Link
              href={href(f, { page: f.page + 1 })}
              className="border px-4 py-2 hover:bg-surface"
            >
              Next &rarr;
            </Link>
          ) : (
            <span />
          )}
        </nav>
      )}
    </div>
  );
}
