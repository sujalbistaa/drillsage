# ADR 0002: Web identity, drawn charts, and a database-free field snapshot

- **Status:** Accepted
- **Date:** 2026-09-29

## Context

The web cockpit has to (1) look like a product with its own identity, not a component-kit
template, in front of Oil India engineers and SIH judges; (2) work offline and on-premises,
since OIL data is confidential; and (3) demo on a laptop where Docker is not always available.
ADR 0001 and the original stack plan had pencilled in shadcn/ui, an icon set, MapLibre GL and visx/D3.

## Decision

- **Identity.** Headlines, the wordmark, big numbers and sticker tags are Archivo (extra bold,
  widened with its width axis; condensed for stickers), data and labels are IBM Plex Mono, body
  text is IBM Plex Sans, accents are Instrument Serif italic. Formal enough for an engineering
  review panel, distinct from default app fonts. (A first cut used Climate Crisis and Rubik
  Glitch; they read as too playful for the audience and were replaced on 2026-09-29.) The
  palette is ink black and bone with one acid-lime signal colour; each hazard has its own colour
  token, saturated for geological hazards and muted for operational ones. Light and dark themes
  share the tokens in `globals.css`.
- **No icon library and no emoji.** Glyphs are drawn for DrillSage (wordmark, spark, north
  arrow, bit marker); hazards are two-letter stamps (`LC`, `WC`, `SP`…) that drillers read
  faster than pictograms. `lucide-react` was removed.
- **Charts are hand-written SVG.** The field plan view and the look-ahead depth strip are
  small, domain-specific drawings (tens of wells, one depth axis); a map or charting library
  would add weight and online tile dependencies without adding capability. Volve is open sea,
  where no imagery provider has detail at field scale, so the field view is a "sonar" plan
  (sea gradient, decorative sweep and range rings) with a real locator inset: NASA Blue Marble
  with bathymetry (public domain), nine zoom-5 tiles shipped in `public/basemap` so it works
  offline. A tiled basemap (MapLibre) can be added for onshore Assam fields where roads and
  villages matter.
- **Field snapshot.** `drillsage-data snapshot` builds the whole field (wellbores,
  trajectories, formation tops, offsets, rule-tier events with evidence spans) from the raw
  files with the same domain code the database pipeline uses, and writes
  `data/processed/web/field-snapshot.json`. The API serves it (`GET /api/v1/field`,
  `/api/v1/events`, `/api/v1/events/{id}`), so the web client still talks only to the typed
  API. `make ui` runs API + web with no database.

## Consequences

- The UI runs on any machine that has run `make data-fetch`, with no Docker and no network.
- The snapshot carries the rule tier only (LLM results live in the database); its
  `extractor_version` says so. When the database is up, later phases can serve the same DTOs
  from Postgres without changing the web app.
- Four web fonts (~latin subsets) are loaded; they are self-hosted by `next/font`, so no
  request leaves the machine at runtime.
