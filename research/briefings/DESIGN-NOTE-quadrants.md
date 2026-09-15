# The quadrant framing is about surprises, not levels

Recorded 2026-09-15 from the primary-source research in `03-all-weather-benchmark.md`. It changes
what a "four-quadrant" branch should actually build.

## The finding

Dalio's own texts — *Engineering Targeted Returns and Risks* (2004, reprinted 2011) and *The All
Weather Story* (2012) — define the four boxes over growth and inflation **surprises**: outcomes
relative to what is already discounted. Each box gets 25% of portfolio *risk*, not capital. They do
not define the boxes over the *levels* of growth and inflation.

The widely quoted "55% bonds / 30% stocks / 15% hard assets" split appears in neither primary
document. It is commentator assertion. Nothing here should be built against it.

## Why it matters for a regime model

The existing hidden Markov model observes **levels**: year-over-year industrial production growth,
year-over-year consumer price inflation, and the three-month bill rate. Mapping those onto four named
quadrants would borrow All Weather's vocabulary without its idea. So there are two separate
experiments, and they should not be conflated:

- **Quadrant structure over levels.** Fix four states and initialise them from the growth × inflation
  2×2. This is a structural prior on the state space. It is cheap and honest, provided the cut points
  are not chosen by someone who knows the sample. It should be named for what it is, not called All
  Weather.
- **Quadrant structure over surprises.** Replace growth and inflation in the observation vector with
  their surprises. That needs a model of what was expected at each date. The data layer holds no
  market-implied expectations, so the honest proxies are point-in-time statistical forecasts (an
  autoregression refitted on data available at each date) or simple changes. This is closer to the
  source idea, and it is also where look-ahead creeps in most easily: an "expectation" fitted on the
  full sample would recreate the leak the previous unit spent a day closing.

## The trap inherited from D12

`docs/TECHNICAL_DEBT.md` D12 records that the ten indicator thresholds are canonical round numbers,
chosen by someone who knew the history. Quadrant boundaries are the same hazard under a more
respectable name. Any branch that needs a growth or inflation cut point must either derive it from
the point-in-time panel at each date (an expanding median, for example) or register the number before
looking at how often each quadrant is occupied.

## What the sceptical literature says about the source

This is relevant to how loudly any positive result should be announced. AQR's own broad-sample table
gives levered risk parity a 1.84% advantage over the market portfolio at **t = 1.43**, which is not
significant, and it explicitly excludes leverage costs. Anderson, Bianchi and Goldberg show the
ranking flips to 60/40 once financing is charged at a realistic rate and turnover is costed. All
Weather's worst year was −22% in 2022, worse than its −20% in 2008.

None of that bears directly on whether regime structure improves a macro *forecast*, which is what
this project measures. It does bear on how much evidential weight the All Weather name carries.
Borrow the structure. Do not borrow the authority.
