# 0011 · Recession status is dated by the announcement that settled it

Date: 2026-09-21 · Status: accepted

## Context

Debt D14. The registry gives recession dating one publication lag,
`publication_lag_days: 400`, so a month's recession code counted as known 400 days
after the month began. The National Bureau of Economic Research does not publish
months. It announces turning points, and a month is known to be contraction or
expansion only once the turning point opening its phase has been announced.

Every peak since 1990 was announced inside 400 days (128 to 366). Every trough
after them (474 to 662). So the months just after each trough, coded 0, entered the
benchmark and the conditional rates before anyone knew the recession had ended.

## Decision

`configuration/business_cycle_announcements.py` holds the eight turning points
since 1990 and the date each was announced, every one checked at nber.org on
2026-09-15. `announced_by(month)` returns the announcement of the most recent
turning point at or before that month: the call that settles which side of a
boundary the month falls on.

A recession value is published at the **later** of its constant-lag date and that
announcement. The rule only ever delays.

Two implementations, deliberately not shared. `walk_forward.publication_dates`
serves the pipeline; `look_ahead_audit.perturbed_snapshot` computes its own, because
the audit's whole worth is that a mistake in the pipeline's rule cannot agree with
the check about it. They read the same verified table; the code applying it is
separate. One test holds the two side by side at four cutoffs, because independence
is only worth having if the two are also compared: where they disagree the audit
either leaves post-trough months untested or scrambles values the pipeline
legitimately used and fails for a leak that is not there.

## The first version leaked, and the audit caught it

The first version let the announcement **replace** the constant lag. The
announcement settling a month is the most recent turning point at or *before* it,
and is routinely years older than the month itself — the December 1992 call on the
1991 trough settles every month up to the 2001 peak. So values were dated before
the months they describe existed. 1995-01 was published 1992-12-22, 740 days early.
Across 1995–2006, 115 of 144 labels inverted, and a panel built in 1994-05 could
read 74 future labels out to 2001-02.

`forecast audit-look-ahead` exited 1 with more than 400 moved rows, the earliest at
forecast date 1994-05-01, on `climatology_probability` and `predicted_probability`
for both recession indicators.

The suite was 509 green at the time and had nothing to say about it, because no
test anywhere required a publication date to follow its own label. That sentence is
now written down, along with the one-directional property:

- `test_a_publication_date_is_never_earlier_than_the_month_it_describes`
- `test_announcement_dating_only_ever_delays_a_publication`
- `test_both_keys_into_the_announcement_table_name_the_registrys_recession_series`

The last one exists because the two layers key the same rule off different things —
the pipeline off the registry name, the audit off the series id — and a silent
disagreement there would stop the audit applying the rule it exists to check while
every test of the rule itself still passed.

## What it moved

Measured against baseline `a4-pre-d14` (`fec79a040f9ca6f9`), the A4-adopted run
captured immediately before this change, so A4's effect is not folded into it.

Field diff: 329 IDENTICAL, 1 NUMERICAL, 57 MOVED, 0 ADDED, 0 REMOVED. Every moved
indicator row is one of the two recession indicators.

Paired, 90% moving-block bootstrap, 10,000 resamples, seed 20260908, on the 9,702
forecasts both runs resolved:

| horizon | before | after | difference | 90% interval |
|---|---:|---:|---:|---|
| 12 months | +0.2744 | +0.2673 | −0.0071 | [−0.0165, −0.0009] |
| 60 months | +0.1192 | +0.1194 | +0.0002 | [−0.0014, +0.0070] |
| 120 months | −0.1673 | −0.1624 | +0.0049 | [+0.0014, +0.0136] |

One-year skill **falls**, and the interval excludes zero. That is the expected sign
for closing a leak: part of that skill was earned on post-trough codings no
forecaster could have read at the time. The other eight indicators are +0.0000 at
every horizon.

The verdicts do not change: 12 months SHIP MODEL, 60 and 120 months SHIP BASE RATE,
the same as the baseline.

## Eighteen forecast dates moved, where D14 predicted eight

D14's table names 8 scored dates. All 8 moved. Ten more did, and the whole
difference is accounted for:

| group | dates | why |
|---|---|---|
| same-date divergence (D14's 8) | 2003-02 to 2003-07, 2010-09, 2021-07 | between the 400-day release and the announcement, the conditions available differ |
| benchmark only (3) | 2003-01, 2010-08, 2021-06 | the expanding climatology's deciding label shifted; D14's table enumerated outcome resolution alone |
| refit carry-forward (7) | 2003-08 to 2004-02 | the 2003-03-01 refit fell inside the divergence window, so its per-regime rates were estimated from different conditions and govern every date to 2004-02, one month short of the 2004-03-01 refit |

The 2010 and 2021 refits predate their divergences, which is why those episodes move
single dates rather than a year.

## What this decision does not claim

- **Not that the table covers everything.** It starts at the 1990 peak. Earlier
  months get `None` and the caller keeps the registry's constant lag. The scored
  backtest begins 1994-03, by which time the 1991 trough had been announced.
- **Not that the trough month is dated as tightly as it could be.** Each trough
  month is withheld until its own trough call, though its coding was inferable
  earlier: with the recession believed still running, every month up to the present
  was coded 1, which is what the trough month turns out to be. Being late is never a
  leak, and the alternative is a second rule about which side of a boundary a month
  falls on, bought for four months since 1990. It is why this marks 23 labels as read
  early by a 400-day lag where D14's table, excluding those four, counts 19.
- **Not a change of identity.** `configuration_hash` stays `fec79a040f9ca6f9`. The
  hash is a pure function of the `RunSettings` fields and this adds none. Unlike the
  three switches in the omission map, this is not a variant anyone would select —
  there is no reading under which the leaky rule is the one you want. What
  distinguishes a pre- and post-change run is the regression baseline, not the hash,
  exactly as in ADR 0009.

## Consequences

- `forecast audit-look-ahead` PASSES at cutoff 2000-03-01: 73 forecast dates, 7
  refits, 2,190 rows compared, both runs choosing 16 regimes, 367 s.
- `baselines/a4-pre-d14.*` is committed as the reference this was measured against,
  so the measurement can be reproduced rather than taken on trust.
- The submission is **not** re-shipped. `submission/` still carries the older
  configuration; re-shipping needs the owner's token.

## Options considered

- **A longer fixed lag, at least 662 days.** Simple, and D14 offered it. Rejected
  because it also withholds every month near a peak for 262 days after it was really
  known, trading one error for another.
- **Availability by turning point.** Chosen. Exact, at the cost of a registry of
  eight rows. D14 recorded the choice between these two as the owner's; it was taken
  here under the standing instruction to resolve the open debts, and is flagged as a
  decision made rather than one deferred.
