import { Gauge } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { VOLVE_ATTRIBUTION } from "@/lib/constants";

/** Primary navigation. Each phase adds its screen here when the screen ships. */
const NAV_ITEMS = [{ href: "/", label: "Overview", Icon: Gauge }] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col border-b bg-surface md:w-60 md:border-r md:border-b-0">
        <div className="flex items-center justify-between gap-3 px-4 py-4 md:px-5">
          <Link href="/" className="flex items-center gap-2.5" aria-label="DrillSage home">
            <BrandMark className="size-8" />
            <span className="flex flex-col leading-tight">
              <span className="font-semibold tracking-tight">DrillSage</span>
              <span className="text-[11px] text-muted-foreground">Offset-well intelligence</span>
            </span>
          </Link>
          <div className="md:hidden">
            <ThemeToggle />
          </div>
        </div>
        <nav aria-label="Primary" className="px-2 pb-2 md:flex-1 md:px-3">
          <ul className="flex gap-1 md:flex-col">
            {NAV_ITEMS.map(({ href, label, Icon }) => (
              <li key={href}>
                <Link
                  href={href}
                  className="flex items-center gap-2.5 rounded-md bg-surface-muted px-3 py-2 text-sm font-medium text-foreground"
                  aria-current="page"
                >
                  <Icon className="size-4 text-brand" aria-hidden />
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="hidden border-t px-5 py-4 md:block">
          <ThemeToggle />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-8">{children}</main>
        <footer className="border-t px-4 py-4 text-xs text-muted-foreground md:px-8">
          <p>{VOLVE_ATTRIBUTION}</p>
          <p className="mt-1">
            Built for Smart India Hackathon 2026 · Problem statement SIH26121 · Oil India Limited
          </p>
        </footer>
      </div>
    </div>
  );
}
