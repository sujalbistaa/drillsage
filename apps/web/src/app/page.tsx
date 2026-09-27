import { StatusPanel } from "@/components/status-panel";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchSystemStatus } from "@/lib/api/system-status";
import { TAGLINE } from "@/lib/constants";

// Status reflects live dependencies; never serve it from a build-time cache.
export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const status = await fetchSystemStatus();

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <p className="text-xs font-semibold tracking-widest text-brand uppercase">
          Nearby Wells Intelligence System
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">
          DrillSage
        </h1>
        <p className="max-w-2xl text-base text-pretty text-muted-foreground">
          {TAGLINE} DrillSage learns from every report drilled nearby and warns your team, before
          the bit gets there, where offset wells lost mud, got stuck, or took a kick, and what fixed
          it. Every warning links to the exact report line behind it.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <StatusPanel status={status} />
        </div>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Data sources</CardTitle>
            <CardDescription>Real industry data, openly licensed.</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
              <dt className="text-muted-foreground">Field</dt>
              <dd>Volve, North Sea (Equinor)</dd>
              <dt className="text-muted-foreground">Reports</dt>
              <dd>WITSML 1.4 daily drilling reports</dd>
              <dt className="text-muted-foreground">Licence</dt>
              <dd>CC BY-NC-SA 4.0</dd>
            </dl>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
