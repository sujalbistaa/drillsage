import type { Metadata, Viewport } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans, Instrument_Serif } from "next/font/google";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/components/theme-provider";
import { TAGLINE } from "@/lib/constants";

import "./globals.css";

/** Headlines, wordmark, big numbers and stickers: Archivo, whose width axis we widen for display. */
const display = Archivo({
  variable: "--font-display-face",
  subsets: ["latin"],
  axes: ["wdth"],
});
/** Data and labels: a report-style monospace, so depths line up like a mud log. */
const data = IBM_Plex_Mono({
  variable: "--font-data",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});
const body = IBM_Plex_Sans({ variable: "--font-body", subsets: ["latin"], axes: ["wdth"] });
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
      <body className={`${display.variable} ${data.variable} ${body.variable} ${accent.variable}`}>
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
