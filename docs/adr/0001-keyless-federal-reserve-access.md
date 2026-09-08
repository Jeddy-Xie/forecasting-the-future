# 0001. Point-in-time data without an API key

Date: 2026-09-08 · Status: accepted

## Context and problem
The brief assumed a `FRED_API_KEY` in the environment and said to fail loudly if
it was absent. That would make the project unrunnable by anyone who has not
registered with the St. Louis Fed, for a project whose whole value is that a
reader can reproduce it. Before accepting the constraint it was worth checking
whether it is real.

It is not. Both endpoints this project needs serve comma-separated values over
plain HTTP with no key and no registration, verified against the live service on
2026-09-08:

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDPRO
    https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=INDPRO&vintage_date=1990-01-02

The second returns industrial production exactly as it stood on 2 January 1990,
ending in November 1989 because December had not been published. That is genuine
archival vintage data, which is the one thing an honest backtest cannot do
without. The keyed JSON interface returns the same numbers.

## Decision
Fetch through the keyless comma-separated endpoints. `FRED_API_KEY` is read if
present and used only to raise the service's rate limit; it changes neither the
code path nor any answer. A missing key is not an error and is never mentioned.

## Consequences
- Good: `poetry install && poetry run forecast fetch-data` works on a clean
  machine with no account, no secret and no onboarding step.
- Good: no credential handling, so no credential to leak.
- Bad / accepted cost: the keyless endpoint has no documented rate limit, so the
  client backs off and retries on failure rather than budgeting requests against
  a published quota. A full cache build makes a few hundred requests, which the
  service absorbs without complaint.
- Bad / accepted cost: the archival endpoint gives no machine-readable list of
  which vintages exist, so coverage is detected from the response instead. See
  ADR 0002.

## Options considered
- Require the key as the brief said — rejected: it buys nothing and costs every
  reader a registration.
- Use a third-party wrapper package — rejected: the dependency checklist stops at
  step one. Two URLs and a comma-separated-values parser are not worth a package,
  and the wrapper would need the key this decision removes.
