# Data pipeline and canonical model

This is how DrillSage turns raw daily drilling reports into data an offset-well comparison
can trust. Every rule below exists because the real Volve data needed it; the example that
forced each rule is named so it can be checked.

```
data/raw/                         apps/api/src/drillsage/
  volve_ddr_mirror/Reports/*.xml ─► ingest/witsml_ddr.py  (parse, units, nulls)
  sodir/wellbore_*_all.csv ───────► ingest/sodir.py        (coordinates, KB, parents, KOP)
  sodir/strat_litho_wellbore.csv ─► ingest/sodir.py        (formation tops)
                                    ingest/registry.py     (reconcile wellbores)
                                    domain/trajectory.py   (minimum curvature + TVD reconciliation)
                                    domain/formations.py   (basin pack, tops, inheritance, correlation)
                                    ingest/pipeline.py     (idempotent load into Postgres)
```

Run it with `make data`. Reports land in `eval/reports/`.

## 1. Sources and provenance

| Source | How it is fetched | Reproducibility |
|---|---|---|
| Volve DDR mirror (1,380 WITSML 1.4 `drillReport` files) | GitHub tarball at a pinned commit | SHA-256 of the tarball is checked; a mismatch aborts |
| Sodir wellbore tables (exploration, development) | FactPages CSV export | SHA-256 and fetch time recorded in `data/raw/MANIFEST.json` |
| Sodir lithostratigraphy | FactPages CSV export | as above |

Archive extraction refuses absolute paths, `..` components and links (zip-slip), and keeps
only the report files. Every loaded report points to a `source_files` row holding its hash,
path and parser version; re-ingesting a file with a known hash is a no-op.

## 2. Parsing (`ingest/witsml_ddr.py`)

- **XML safety.** Documents with a DOCTYPE or entity declaration are refused before parsing;
  the lxml parser runs with entity resolution, DTD loading and network access disabled.
- **Declarative mapping.** Each Pydantic field names its XML element and quantity kind, for
  example `md_m: Annotated[float | None, Xml("md", Kind.LENGTH)]`. The same declaration drives
  parsing, unit conversion and the fidelity check, so a field cannot be parsed without being
  counted.
- **Units.** Every value is converted from its `uom` attribute to the canonical unit
  (`core/units.py`: metres, g/cm³, hours, kPa, °C, …). An unknown or missing unit is an
  error, never a guess.
- **Nulls.** WITSML's `-999.99` sentinel becomes `None`.
- **Format drift.** Elements the model does not know are counted as *unmapped* and appear in
  the fidelity report instead of being silently dropped.

Result on Volve: 245,516 of 245,516 leaf values accounted for, 7,477 nulls, 0 unmapped
(`eval/reports/parser_fidelity.md`).

## 3. Wellbore registry (`ingest/registry.py`)

The DDR's `NPD number` alias is the regulator's wellbore id and the join key to Sodir.

| Rule | Why (Volve example) |
|---|---|
| A trailing `T<n>` marks a **technical sidetrack**: it shares the regulator id, its parent is the base name, its kick-off comes from the DDR `mdKickoff` | `15/9-19 BT2`, `15/9-19 ST2`, `15/9-F-11 T2` have no Sodir row of their own |
| When Sodir names a parent that was later technically sidetracked, children tie onto the **latest** technical sidetrack | `15/9-F-11 A` kicks off at 2,578 m from the hole drilled as `F-11 T2`; `F-11` itself was only surveyed to 342 m |
| Sodir's total depth and final TVD are not attributed to a wellbore that was later redrilled | For a shared id, Sodir describes the final hole (`15/9-19 B`'s Sodir TD is `BT2`'s) |
| Surface coordinates come from Sodir (ED50), converted to WGS84 and WGS84/UTM 31N with pyproj | Every wellbore of a well shares its surface location |

## 4. Trajectories (`domain/trajectory.py`)

Survey stations come from the daily reports. A sidetrack's path is its parent's stations
above the kick-off plus its own, recursively. The geometry is minimum curvature from a
vertical tie-in at the rig floor (RKB).

**Cleaning.**
- Duplicate MDs (reports repeat the previous day's last stations): the newest measurement wins.
- A survey run measured on a later day **supersedes** earlier stations inside its MD span.
  `15/9-F-12` drilled a vertical 8½" pilot hole to 1,353 m before the deviated 26" hole, and
  both sets of stations sit interleaved in the same reports.

**TVD reconciliation.** Each station carries both inclination/azimuth and the operator's
reported TVD, and each has errors:

| Error | Example | Signature | Handling |
|---|---|---|---|
| Reported-TVD typo | `15/9-F-4`: TVD 24.8 m at MD 2,620.8 m | Residual (reported − computed) jumps away and returns within ≤ 8 stations | Rejected; TVD from minimum curvature shifted onto neighbours |
| Run of reported-TVD typos | `15/9-19 BT2`: 172.1 → 130.4 m at MD 2,916–3,000 m | Same, over several stations | Rejected as one excursion |
| Wrong inclinations | `15/9-F-15 A`: 40° reported at MD 1,827–2,392 m where the operator's own TVDs imply ~25° | Residual ramps smoothly and never returns | Reported TVD kept; it matches Sodir's final TVD to 1 m |

The final TVD follows accepted reported values exactly and uses the minimum-curvature shape
between them. Horizontal offsets always come from minimum curvature. Each station stores its
minimum-curvature TVD, reported TVD, the source of the final value and whether the reported
value was rejected.

**Independent check.** Sodir publishes each wellbore's total depth and final TVD. Across the
20 wellbores where that comparison is valid, the median absolute error at TD is 0.6 m.
`15/9-F-15 D` differs by 15 m: the operator's own reported TVDs disagree with Sodir by about
13 m, and DrillSage reports that discrepancy rather than hiding it.

**Datum.** Depths are from the rig's kelly bushing. Kelly-bushing elevation is 22 m
(Treasure Prospect) and 25 m (Byford Dolphin) for the 1990s wells and 54–54.9 m (Mærsk
Inspirer) for the F-template wells, so cross-well comparisons use **TVDSS** (TVD below mean
sea level), which is stored alongside TVD.

## 5. Formations (`domain/formations.py`)

A **basin pack** (`config/basin_packs/*.yaml`) is the dictionary of stratigraphic units for a
basin, listed top to bottom with the spellings seen in reports. `north_sea` holds the Sodir
units found in block 15/9; `assam_arakan` holds the Upper Assam column for Oil India
(dictionary only, with no well data). Select it with `DRILLSAGE_BASIN_PACK`.

Tops per wellbore, in priority order:

1. **Sodir** interpreted lithostratigraphy (authoritative).
2. **DDR picks** (`stratInfo`) resolved against the pack; among picks of the same unit, the
   shallowest wins. Names outside the pack are kept in `strat_picks` but never used; Volve's
   reports contain 13 Norwegian Sea formations (Kai, Brygge, Lysing, …) that do not occur in
   block 15/9.
3. **Inherited** from the parent hole above a sidetrack's kick-off. A geologist's "formation
   at kick-off" entry in the sidetrack's first report is not a top, and the parent's shallower
   pick wins.
4. **Field-correlated**, only for a wellbore with no tops at all: the unit's median TVDSS
   across wellbores that picked it (at least 3), converted to MD along the wellbore's own
   trajectory. Four shallow or unpicked Volve wellbores use this, and it is labelled as lower
   confidence everywhere it is shown.

## 6. Canonical tables

| Table | Grain | Notes |
|---|---|---|
| `source_files` | file | SHA-256, path, parser version |
| `wells`, `wellbores` | well / wellbore | WGS84 + UTM surface location, parent, kind, kick-off, KB, spud, completion |
| `daily_reports` | report | status section, 24 h summary and forecast; bit, core, log, perforation and well-test sections in `extra` (JSONB) |
| `activities` | activity | time, depth, operator code, state, detail, free-text comments; `seq` is the position in the report (the evidence anchor for Phase 2) |
| `fluids`, `pore_pressures`, `survey_stations`, `lithology_shows`, `strat_picks`, `gas_readings`, `casing_strings`, `equipment_failures` | section row | as reported, canonical units |
| `trajectory_stations` | station | derived; MD, TVD, TVDSS, N/E offsets, UTM, DLS, TVD source and flags |
| `formation_tops` | unit per wellbore | derived; MD, TVD, TVDSS, source, inherited-from |

Derived tables are rebuilt deterministically on every load.
