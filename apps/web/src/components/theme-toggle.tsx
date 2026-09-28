"use client";

import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Lite", title: "Light theme" },
  { value: "dark", label: "Dark", title: "Dark theme" },
  { value: "system", label: "Auto", title: "Follow the system theme" },
] as const;

const subscribe = () => () => {};

/** Three-way theme switch in words. Renders neutral until mounted to avoid a hydration mismatch. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

  return (
    <div role="radiogroup" aria-label="Colour theme" className="label flex border">
      {OPTIONS.map(({ value, label, title }) => {
        const active = mounted && theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            title={title}
            onClick={() => setTheme(value)}
            className={cn(
              "px-2 py-1 text-muted-foreground transition-colors hover:text-foreground",
              active && "bg-foreground text-background hover:text-background",
            )}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
