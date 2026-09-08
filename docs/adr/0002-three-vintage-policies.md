# 0002. Three vintage policies, chosen by measuring coverage rather than declaring it

Date: 2026-09-08 · Status: accepted

## Context and problem
Point-in-time reconstruction is the difference between a backtest and a
daydream. The brief offered two routes, archival vintages preferred and a
publication-lag shift as fallback, and left the choice per series to the author.

Probing the archive showed the choice cannot be made per series in advance,
because it varies by *date within* a series. Coverage measured on 2026-09-08:

| series | vintage at 1970 | at 1990 | at 2010 |
|---|---|---|---|
| industrial production | full, 612 rows | full, 852 rows | full, 1092 rows |
| unemployment rate | full, 264 rows | full, 504 rows | full, 744 rows |
| consumer price index | nothing | **20 rows** | full, 756 rows |
| three-month bill rate | nothing | nothing | full, 913 rows |

The consumer price index row is the dangerous one. The archive answers a 1990
vintage request with twenty rows covering 1988 to 1989 rather than the 504 rows
the series had by then. Nothing about that response is an error: it parses, it
has the right column name, and it would produce a model fitted on twenty months
of data with no exception raised anywhere.

## Decision
Three named policies, selected at fetch time by measuring the response:

1. `unrevised_series` — the series is a market rate that is never revised, so
   today's file is the historical file and censoring by publication lag gives
   exact point-in-time data.
2. `archival_vintage` — the archive returned a vintage whose first observation is
   within two years of the series' declared start. Used as published, with **no**
   further lag censoring, because a vintage already reflects what had been
   released by then and censoring twice discards a month.
3. `publication_lag_fallback` — used when the archive has nothing usable that far
   back. Timing is right, values are revised. This is the weaker path, so it is
   detected rather than assumed, logged at warning level, and reported per series
   in every run manifest.

The two-year coverage tolerance is the threshold separating "an old vintage that
was not fully backfilled" from "a truncated archive entry".

## Consequences
- Good: the twenty-row failure mode is impossible; it is now a detected fallback
  with a warning naming the date the archive actually covers from.
- Good: every panel can say which policy produced each of its series, so a reader
  can discount the parts that rest on the weaker path.
- Bad / accepted cost: the consumer price index uses the fallback for every
  forecast date before 1997, which is a large share of the backtest. The report
  says so rather than burying it.
- Bad / accepted cost: one extra request per series per forecast date to discover
  that a vintage is unusable. Cached, so it happens once.

## Options considered
- Declare the earliest usable vintage per series in the registry — rejected: a
  fact that must be kept true by hand, and one that goes stale silently the day
  the archive backfills.
- Use the publication-lag shift everywhere for simplicity — rejected: it throws
  away genuine archival data for the two thirds of the sample where it exists.
- Trust the archive and skip the coverage check — rejected: that is precisely the
  twenty-row disaster, and it announces itself nowhere.
