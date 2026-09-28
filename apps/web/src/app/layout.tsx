import type { Metadata, Viewport } from "next";
import {
  Bricolage_Grotesque,
  Climate_Crisis,
  Instrument_Serif,
  Martian_Mono,
  Rubik_Glitch,
} from "next/font/google";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/components/theme-provider";
import { TAGLINE } from "@/lib/constants";

import "./globals.css";

/** Display: Climate Crisis. Its YEAR axis melts the letters; hover the wordmark. */
const melt = Climate_Crisis({ variable: "--font-melt", subsets: ["latin"], axes: ["YEAR"] });
/** Data and labels: a wide monospace, so depths line up like a mud log. */
const data = Martian_Mono({ variable: "--font-data", subsets: ["latin"], axes: ["wdth"] });
/** Stickers and team branding: a glitched grotesque. */
const glitch = Rubik_Glitch({ variable: "--font-sticker", subsets: ["latin"], weight: "400" });
const body = Bricolage_Grotesque({
  variable: "--font-body",
  subsets: ["latin"],
  axes: ["opsz", "wdth"],
});
const accent = Instrument_Serif({
  variable: "--font-accent",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: {
    default: "DrillSage · See trouble before the bit does",
    template: "%s · DrillSage",
  },
  description: `${TAGLINE} Evidence-backed warnings from nearby wells, for Oil India drilling teams.`,
  applicationName: "DrillSage",
  authors: [{ name: "Team CodeY" }],
  creator: "Team CodeY",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eeeadf" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0b" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${melt.variable} ${data.variable} ${body.variable} ${accent.variable} ${glitch.variable}`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <AppShell>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
