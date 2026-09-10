---
name: register
description: Record the shipped forecasts as dated, resolvable claims about the actual future — append-only, tied to the configuration hash that produced them. Run after `forecast submit`.
disable-model-invocation: true
---

Record the current submission in the forecast register.

```
poetry run forecast submit      # if the submission is not current
poetry run forecast register
```

This reads `submission/forecasts.csv` and `submission/manifest.json` and appends
one line per forecast to `forecasts/register.jsonl`, adding the two things the
CSV lacks: the date the forecast was **made**, and the date it **resolves**
(`data_as_of` plus the horizon).

## Why it is append-only

A forecast that can be edited after the fact is not a forecast. The register is
guarded by `.claude/hooks/freeze_guard.py`, which refuses an in-place rewrite;
appending is the only way in. Re-registering the same run is a no-op rather than
an error — running `submit && register` twice has not made a claim twice. A
*different* configuration hash for the same indicator and horizon is a new claim
and lands alongside the old one, because which one you believed at the time is
exactly what is being tested.

## What to tell the operator afterwards

How many were written, how many were already on record, and the next resolution
date. Nothing resolves until `data_as_of` plus one year, so the honest report is
usually "recorded, nothing due yet" — say so plainly rather than dressing it up.

Then `/resolve` when a date has passed.
