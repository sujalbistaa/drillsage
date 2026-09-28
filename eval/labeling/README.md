# Gold-set labelling

The gold set is what makes DrillSage's extraction accuracy a measured number rather than a
claim. Each item is one activity line from a daily drilling report. A person with drilling
knowledge marks which problems, if any, it shows.

## Steps

1. `make gold-sample` writes `data/processed/gold/gold-v1.jsonl` (309 lines, stratified and
   seeded, so everyone gets the same sample). The file contains Volve report text and is
   never committed.
2. Open `eval/labeling/label.html` in a browser (double-click it; it needs no server and no
   internet) and load that `.jsonl` file.
3. Label. Keyboard: `1`–`9`, `0`, `-`, `=` toggle hazards · `N` no problem · `U` unsure ·
   `→` or `Enter` next · `←` previous · `G` next unlabelled · `S` show DrillSage's suggestion.
   Work is saved in the browser as you go.
4. Click **Export labels** and save the file as `eval/gold/labels-gold-v1.json`. It contains
   keys and labels only (no report text), so it is committed.
5. `make gold-eval` writes `eval/reports/extraction_gold.md`.

Several people can label: each exports their own file, and a labeller can resume from an
exported file with **Resume labels**.

## The question for every line

*Is this activity part of, or evidence of, a drilling problem that actually happened?*

- Tick every hazard that applies. Lines that handle an ongoing problem count (the trips and
  meetings of a fishing job are part of the fishing problem).
- Drills, tests, precautions, plans and negated statements ("no losses", "well static",
  "flow checked, static") are **No problem**.
- If the line states the depth of the problem, enter it; this measures depth error.
- Use **Unsure** instead of guessing. Unsure lines are left out of the metrics.
- Keep DrillSage's suggestion hidden while deciding (it is off by default) so the labels
  stay independent of the system they measure.

About 10–15 seconds per line: 309 lines take one to one and a half hours.
