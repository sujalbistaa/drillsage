# Event extraction

How DrillSage turns daily-report text into drilling-problem events with evidence. Every
event links to the report lines, and the exact characters, it came from.

```
activities ─► rule tier (codes + lexicon)  ─┐
          └► LLM tier (one call per report) ─┴► hits ─► episodes ─► events + evidence
```

Run `make extract` to rebuild events. It never calls a model: it merges the rules with LLM
results already stored. LLM calls happen only through `drillsage-data llm-extract`, which
needs `--yes`.

## 1. Hazard taxonomy (`domain/hazards.py`)

Twelve canonical types. The six geological ones drive look-ahead depth alerts: lost
circulation, well control, stuck pipe, tight hole, wellbore instability, and shallow gas/H2S.
The others (cementing, casing running, directional, equipment failure, fishing, waiting) are
NPT that is counted but never placed on the depth strip.

Severity runs from 1 to 4 by lost time (under 1 h, 1–6 h, 6–24 h, 24 h or more), plus one
level when the section was sidetracked within 72 h of the problem.

## 2. Rule tier (`extract/lexicon.py`, `extract/rules.py`)

- **Operator codes** (`interruption -- lost circulation`, `stuck equipment`, …) are weak,
  episode-level labels. A fishing job's toolbox talks are coded `fish` too. They seed events
  but are never used as text evidence.
- **Text rules** are phrase patterns, each with a stable id, an optional sentence-level
  *exclude* and *require*, and a negation check on the three preceding words. They were
  tuned by reading random samples of real Volve hits, which found routine wording that must
  not count as a problem:

| Looks like a hazard | Actually | How it is excluded |
|---|---|---|
| "kick drill", "kick-off", "kick valve", "kick joint" | drill, directional work, equipment | negative look-ahead |
| "overpull tested with 25 tons", overpull to set slips or a J-slot | routine verification | exclude, plus require hole context or a depth |
| "packoff running tool", "packer" | equipment | look-ahead, exclude |
| "no losses", "well static", "no restrictions" | negation | negation window |
| "lost mud from leak in slip joint" | surface spill | exclude |
| "soft cement in shoe track" | normal drill-out | pattern removed |
| "dropped object" on the drill floor | safety incident, not junk in the hole | pattern removed |
| "overshot" / "spear" in BOP and completion work | running tools | pattern removed |

## 3. LLM tier (`extract/llm_extractor.py`, `llm/`)

- **One call per daily report.** The model sees numbered activity lines and returns
  events as structured output (`extract/schemas.py`, validated by Pydantic). The prompt
  (`extract/prompts/extract_v1.md`) carries the same routine-versus-problem distinctions as
  the lexicon. Its version (`extract-v1-<hash>`) changes whenever the text changes.
- **Evidence is quoted, not located, by the model.** Each event must quote the report
  verbatim. DrillSage finds the quote in the stored comment (exact match, then a case- and
  whitespace-insensitive match) and computes the character span itself. Quotes that are not
  in the source are rejected and counted; an event with no surviving quote is dropped.
- **Gateway (`llm/gateway.py`).** This is the single choke point. In order: it fails closed
  in local-only mode, returns cached results for free (the key hashes model, prompt version
  and input), stops at the budget cap, calls the model, and records every call's tokens,
  cost, stop reason and request id in `llm_calls`. Output is accepted only after a normal
  finish and a successful validation; refusals and truncations are recorded and raised.
- **Providers.** For the demo, **Gemini** through a free Google AI Studio key
  (`llm/gemini.py`): JSON output constrained by the same Pydantic schema, retries with
  backoff, a fallback chain of lighter models when the free tier is overloaded, and a
  minimum interval between calls. **Claude** (`AnthropicProvider`) is the alternative:
  `claude-opus-5` with adaptive thinking, a cached system prompt and server-side refusal
  fallback. The provider is one setting (`DRILLSAGE_LLM_PROVIDER`); the prompt, schema,
  quote alignment and gateway are shared.
- **Bulk backfill.** The Message Batches API costs 50% less. Results are keyed by
  `custom_id`, and a batch can be resumed by id after an interruption.

## 4. Merge into events (`extract/episodes.py`)

Rule hits and LLM hits go through the same episode logic. Hits of one hazard in one
wellbore less than 6 h apart form one event. Each event's **confidence tier** follows from
its sources:

| Tier | Found by |
|---|---|
| `rule` | operator code and/or lexicon only |
| `llm` | the LLM only (wording the lexicon does not know) |
| `rule+llm` | both, independently |

The **depth** is where the problem was met: depths stated in the trigger text (by the lexicon
or by the LLM), else the activity depth, else the hole depth. The range is clustered near
the deepest value, and geological hazards are never placed above the mudline. **Mitigations**
come from the lexicon and the LLM, deduplicated by action.

## 5. Cost control

`drillsage-data llm-estimate --pilot 50` prints a cost range without calling a model.
Input tokens come from the text; output tokens are the unknown, because they include
adaptive thinking. After a pilot, estimates use the pilot's measured output tokens. A batch
is refused when the high end of its estimate exceeds the remaining budget
(`DRILLSAGE_LLM_BUDGET_USD`).

## 6. What is measured where

- `eval/reports/extraction_rules.md`: events per hazard and tier, text corroboration of
  operator codes, how many spans resolve to source text (target: all), and LLM quotes rejected.
- `eval/reports/extraction_gold.md`: accuracy against the hand-labelled gold set
  (precision, recall and F1 per hazard for codes, lexicon and rules, then the LLM tier, plus
  median depth error). The sample is stratified and every count is inverse-probability
  weighted, so the numbers estimate the whole corpus. No accuracy is claimed before the labels
  exist. How to label: `eval/labeling/README.md`.
