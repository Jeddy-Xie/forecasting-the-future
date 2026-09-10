---
name: resolve
description: Score every registered forecast whose resolution date has passed, against the same rule the backtest uses, and print live Brier skill against climatology. The only thing in this repository that produces evidence from the actual future.
disable-model-invocation: true
---

Resolve and score what has come due.

```
poetry run forecast fetch-data   # outcomes need current data
poetry run forecast resolve
```

Every forecast in `forecasts/register.jsonl` whose `resolves_on` has passed is
scored with `data.indicator_outcomes.resolve` — the same rule the walk-forward
backtest scores against, so a live forecast and a historical one are graded by
identical code. Results append to `forecasts/resolutions.jsonl`.

## The two things to be careful about

**Pending is not missing.** A forecast whose date has passed but whose outcome
the published data cannot yet settle is reported as `awaiting data`, never as a
miss. Report that count; silence about an unresolvable forecast would be a silent
fallback, and this repository does not do those.

**Below ten resolved forecasts, the scorecard prints INERT.** The numbers are
shown and the inference is refused. A skill score on three observations is a
number, not evidence. Do not summarise an inert scorecard as though the model is
beating or losing to climatology — say how many have resolved and how many are
still needed.

## Exercising it before 2027

The first live forecast resolves in July 2027. To prove the machinery works now,
backdate: copy the register to a temp file, rewrite `data_as_of` and
`resolves_on` to dates in the past, and call
`forecast_register.resolve(series, today, temp_register, temp_resolutions)`.
That runs the whole path against real outcomes today. Never do this against
`forecasts/` itself — the real register is append-only for a reason.
