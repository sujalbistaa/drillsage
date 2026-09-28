"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

/** Primary navigation. Each phase adds its screen here when the screen ships. */
const ITEMS = [
  { href: "/", label: "Field", n: "01" },
  { href: "/wells", label: "Wells", n: "02" },
  { href: "/events", label: "Events", n: "03" },
] as const;

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function Nav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary">
      <ul className="flex items-stretch">
        {ITEMS.map(({ href, label, n }) => {
          const active = isActive(pathname, href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group label flex h-full items-center gap-1.5 px-3 py-2 transition-colors md:px-4",
                  active
                    ? "bg-brand text-brand-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <span className={cn("opacity-50", active && "opacity-70")}>{n}</span>
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
