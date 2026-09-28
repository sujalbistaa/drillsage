import Link from "next/link";

import { HazardCode } from "@/components/hazard";
import type { HazardSummary } from "@/lib/api/client";
import { hours, int } from "@/lib/format";
import { hazardMeta } from "@/lib/hazards";

/** Events and lost hours per hazard, geological first; each row opens the filtered logbook. */
export function HazardBars({ hazards }: { hazards: HazardSummary[] }) {
  const maxNpt = Math.max(1, ...hazards.map((h) => h.npt_h));
  const maxEvents = Math.max(1, ...hazards.map((h) => h.events));
  const groups = [
    { title: "Geological: these drive depth alerts", rows: hazards.filter((h) => h.geological) },
    {
      title: "Operational: counted, never on the depth strip",
      rows: hazards.filter((h) => !h.geological),
    },
  ];

  return (
    <div className="grid gap-10 lg:grid-cols-2">
      {groups.map((group) => (
        <div key={group.title}>
          <p className="label mb-3 text-muted-foreground">{group.title}</p>
          <div className="label mb-1 grid grid-cols-[2.5rem_1fr_1fr] gap-3 text-muted-foreground">
            <span />
            <span>Events</span>
            <span>Hours lost</span>
          </div>
          <ul className="flex flex-col">
            {group.rows.map((h) => {
              const meta = hazardMeta(h.hazard);
              return (
                <li key={h.hazard}>
                  <Link
                    href={`/events?hazard=${h.hazard}`}
                    className="group grid grid-cols-[2.5rem_1fr_1fr] items-center gap-3 border-t border-hairline py-2 hover:bg-surface"
                  >
                    <HazardCode hazard={h.hazard} />
                    <span className="flex flex-col gap-1">
                      <span className="text-sm leading-none">{meta.label}</span>
                      <span className="flex items-center gap-2">
                        <span
                          className="h-2.5"
                          style={{
                            width: `${(h.events / maxEvents) * 100}%`,
                            background: meta.color,
                            minWidth: h.events ? 3 : 0,
                          }}
                        />
                        <span className="label">{int(h.events)}</span>
                      </span>
                    </span>
                    <span className="flex items-center gap-2 self-end">
                      <span
                        className="h-2.5 border border-foreground/70"
                        style={{
                          width: `${(h.npt_h / maxNpt) * 100}%`,
                          minWidth: h.npt_h ? 3 : 0,
                          background: `repeating-linear-gradient(135deg, ${meta.color} 0 3px, transparent 3px 6px)`,
                        }}
                      />
                      <span className="label whitespace-nowrap">{hours(h.npt_h)}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
