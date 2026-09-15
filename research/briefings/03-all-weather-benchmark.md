# All Weather as a benchmark: what it is, what is public, and what it would cost to build

Research briefing. Compiled 2026-09-12. Every source marked **[F]** was fetched and read in
this session; **[S]** means it reached me only via search-result summary and the primary text
was **not** retrieved (403 or paywall). Treat **[S]** claims as unverified.

No recommendation is made here. This is what is true and what it would cost.

---

## 1. What All Weather actually is

### 1.1 The published origin story

Bridgewater has published two substantial primary documents, both of which I fetched and read in
full:

- **Dalio, "Engineering Targeted Returns and Risks", August 2011** — a reprint, "with relevant
  updates", of a 2004 Dalio article. [F]
  `https://bridgewater.brightspotcdn.com/fa/e3/d09e72bd401a8414c5c0bdaf88bb/bridgewater-associates-engineering-targeted-returns-and-risks-aug-2011.pdf`
- **Podolsky, Johnson & Jennings, "The All Weather Story", January 2012** — written by Bridgewater
  employees, third person, based on interviews with the strategy's creators. [F]
  `https://www.bridgewater.com/_document/the-all-weather-story?id=00000171-8623-d7de-affd-feaf4ee20000`

Facts stated in those documents:

- All Weather was **launched in 1996**, created by Dalio with Bob Prince and Greg Jensen, originally
  to invest **Dalio's own family trust assets**. It "was never envisaged as a product."
- It is explicitly described as **passive**: "the best portfolio Ray and his close associates could
  build without any requirement to predict future conditions." Pure Alpha (1991) is the separate
  active strategy. The alpha/beta split is the organising principle: `return = cash + beta + alpha`.
- The precursor was a 1990 memo to Rusty Olson (CIO of a large US consumer-goods pension) arguing
  that "low-risk/low-return assets can be converted into high-risk/high-return assets" — i.e. that
  risk-adjusted returns across betas are broadly similar, so diversification need not cost return.
- Inflation-linked bonds are called "the final ingredient". Bridgewater states that when the US
  Treasury decided to issue inflation-linked bonds, "officials came to Bridgewater to seek advice
  on how to structure the securities. Bridgewater's recommendations in 1997 led to TIPS being
  designed as they now are."

### 1.2 The four-box framework — published, with numbers

This is the single most useful published artefact. From "The All Weather Story" (2012), the
strategy is mapped onto a 2x2 of **Growth** and **Inflation** against **market expectations**
(rising / falling), with **25% of risk in each box**, and the asset classes named:

|  vs. market expectations | **Growth** | **Inflation** |
|---|---|---|
| **Rising** (25% of risk each) | Equities, Commodities, Corporate Credit, EM Credit | IL Bonds, Commodities, EM Credit |
| **Falling** (25% of risk each) | Nominal Bonds, IL Bonds | Equities, Nominal Bonds |

The document's own one-sentence summary: All Weather "can be sketched out on a napkin. It is as
simple as holding four different portfolios each with the same risk, each of which does well in a
particular environment: when (1) inflation rises, (2) inflation falls, (3) growth rises, and
(4) growth falls **relative to expectations**."

The "relative to expectations" clause is load-bearing and routinely dropped by commentators. The
axes are **surprises**, not levels.

### 1.3 The construction principle, in Bridgewater's own words

From "Engineering Targeted Returns and Risks":

- Betas have Sharpe ratios "typically ranging from 0.2 to 0.3", and this is asserted as a structural
  feature, not an estimate: the ratio must be positive to compensate for risk, but cannot be very
  positive or capital would bid it away.
- Because risk-adjusted returns across asset classes are broadly similar, "the expected returns and
  risks of these asset classes can be made similar and adjusted to deliver returns closer to your
  target by using leverage or leverage-like techniques."
- The quantitative claim: a traditional portfolio of assets with individual Sharpe ratios of 0.2–0.3
  "typically yields a portfolio Sharpe ratio of about 0.4"; the risk-balanced version reaches
  "approximately 0.65". "For a portfolio exhibiting a 10% annual volatility, we estimate this higher
  Sharpe ratio implies about 2.5% per year higher return than a conventional portfolio."
- Downside acknowledged explicitly: "the risk of this portfolio is that other asset classes will, on
  average, underperform cash."
- Validation claim: "we have stress-tested these concepts back to 1925 across multiple countries."

### 1.4 The published hypothetical track record

Chart 3 of "Engineering Targeted Returns and Risks", covering **1970 to ~2011**, run at the
conventional portfolio's risk level:

| | US Conventional Asset Mix | All Weather Asset Mix (same risk) |
|---|---|---|
| Annualised total return | 9.8% | 13.8% |
| Excess return | 3.9% | 7.9% |
| Std. dev. | 10.6% | 10.6% |
| Sharpe | 0.37 | 0.75 |

Chart 4, run at the same *return*: All Weather 9.8% total / 3.9% excess at **5.1%** vol, Sharpe 0.76.

**Critically**: this is labelled hypothetical, not a fund track record. The PDF carries a full-page
CFTC-style hypothetical-performance disclaimer: "HYPOTHETICAL PERFORMANCE RESULTS HAVE MANY INHERENT
LIMITATIONS... GENERALLY PREPARED WITH THE BENEFIT OF HINDSIGHT." Dalio's own framing: "We can
illustrate how these concepts would have performed by applying the asset allocation mix weights to
market returns... **but is not indicative of how it would look if implemented** for an institutional
investor."

---

## 2. What is public vs. what is asserted

### 2.1 Published by Bridgewater (verifiable)

| Item | Status |
|---|---|
| 1996 launch, family-trust origin, named creators | Published [F] |
| The 2x2 growth/inflation surprise framework | Published [F] |
| "25% of risk" per box | Published [F] |
| Asset classes assigned to each box | Published [F] |
| Leverage as an implementation tool; the principle that betas are levered/de-levered to a common expected return | Published [F] |
| Beta Sharpe assumption of 0.2–0.3, portfolio Sharpe target ~0.65, +2.5%/yr at 10% vol | Published [F] |
| Hypothetical 1970– simulated performance at two risk levels | Published, labelled hypothetical [F] |
| ALLW (the 2025 ETF) target vol band of 10–12%, current notional allocations, daily holdings | Published by State Street [F] |

### 2.2 NOT public

- **The actual weights of the institutional All Weather fund.** Neither document gives them. The
  widely circulated "55% bonds / 30% stocks / 15% hard assets" figure appeared in a search-result
  summary and I could **not** locate it in either Bridgewater primary document. Treat it as
  commentator assertion, not Bridgewater disclosure.
- **The risk model.** Which covariance estimator, what lookback, whether correlations are estimated
  or structurally imposed, how "environmental bias" is quantified. "The All Weather Story" is explicit
  that they distrust estimated inputs: "Anything else (asset class returns, correlations, or even
  precise volatilities) is an attempt to predict the future." That tells you the *philosophy*, not
  the *estimator*.
- **The rebalancing rule.** The 2012 document says only that in the pilot "it was someone's part-time
  job to rebalance the portfolio from time to time."
- **Leverage ratio, financing arrangements, financing spread over cash.**
- **The actual fund NAV track record.** Bridgewater is a private fund manager; monthly returns are
  not filed publicly. Every performance number circulating for the All Weather *fund* (as opposed to
  the hypothetical asset mix) is press reporting from anonymous investor letters.
- **Whether the live fund deviates tactically from the static mix.** Both documents insist All
  Weather is passive. Bridgewater has since published on "systematic rebalancing" and All Weather
  variants; the ETF prospectus language ("Bridgewater constructs a *daily* model portfolio") is not
  obviously the same thing as a static mix.

### 2.3 Asserted by commentators, unverified here

- The 55/30/15 split.
- "All Weather gained 43% since 2008 while conventional was flat" (surfaced in search summaries;
  primary source not retrieved). [S]
- Most published "All Weather backtests" on retail sites are backtests of the **All Seasons**
  portfolio (§3), not of All Weather.

---

## 3. The canonical public approximations

### 3.1 "All Seasons" (Robbins, *Money: Master the Game*, 2014)

30% US stocks / 40% long-term US Treasuries / 15% intermediate US Treasuries / 7.5% gold /
7.5% broad commodities, rebalanced annually.

**Is it All Weather? No, and its own authors say so.** The distinguishing features, per the sources:

- **No leverage.** All Weather's entire construction logic is levering low-vol assets up to a common
  expected return. Strip the leverage and you have a bond-heavy static mix, not a risk-balanced one.
  Dalio reportedly told Robbins the weights "would not be exact or perfect". [S — I could not fetch
  a primary Dalio quote; Bogleheads and CNBC both returned 403.]
- **No inflation-linked bonds**, which Bridgewater's own document calls "the final ingredient" and the
  only asset that "helped balance out both boxes... in a way no other asset class could". All Seasons
  substitutes 7.5% gold + 7.5% commodities for the entire rising-inflation quadrant.
- **No credit, no non-US assets, no currency hedging.** Bridgewater's published box map includes
  Corporate Credit and EM Credit.
- **Static dollar weights, not risk weights.** All Seasons fixes capital shares; All Weather fixes
  risk shares. These coincide only if vols and correlations never move.

The honest summary: **All Seasons is a capital-weighted retail caricature that happens to land near
risk parity because long Treasuries were the low-vol asset of the era.** Benchmarking against it is
benchmarking against a fixed 55/30/15 mix, not against Bridgewater.

### 3.2 The Robbins backtest, and why it is the wrong number

Ben Carlson's replication [F] `https://awealthofcommonsense.com/2014/11/back-testing-tony-robbins-weather-portfolio/`:

| Period | Ann. return | Vol | Note |
|---|---|---|---|
| 1984–2013 (Robbins' window) | 9.7% | 7.6% | 86% winning years; worst drawdown −3.9% |
| 1972–2013 | 9.5% | 7.9% | worst loss −4.2% |
| 1928–1983, 35/65 stock/bond proxy | **5.8%** | 8.5% | gold & commodities omitted — no data |

The 1984–2013 window beat 1928–1983 by roughly **400 basis points a year**, which Carlson attributes
directly to "the past 30 years of falling interest rates". His own caveat: "it would be a mistake to
assume future returns in bonds will be anywhere close to what they were from 1984-2013." Note also
that he **could not construct the gold and commodity sleeves before the early 1990s** — the same gap
this project would face (§6).

### 3.3 The one genuinely investable public approximation: ALLW

**State Street Bridgewater All Weather ETF (ALLW)**, sub-advised by Bridgewater. [F]
`https://www.ssga.com/us/en/intermediary/etfs/state-street-bridgewater-all-weather-etf-allw`

- Inception **2025-03-05**. Gross expense ratio **0.85%**. AUM ~**$1.79bn** (2026-09-10).
- Stated benchmark: **MSCI ACWI IMI** (an equity index — note the mismatch).
- Target: "an annualized volatility level for the portfolio ranging between 10%-12%", allocating
  "risk equally to different growth and inflation environments".
- Notional allocations as of 2026-09-10:

| Sleeve | Notional |
|---|---|
| Global nominal bonds | 68.98% |
| Global equities | 42.66% |
| Inflation-linked bonds | 40.54% |
| Commodities | 33.49% |
| **Total** | **185.67%** — i.e. ~1.86x gross notional |

- Since-inception NAV return to 2026-08-31: **+16.67%** vs benchmark **+23.71%**.
- **Daily holdings are published, keyless, as an .xlsx** (verified 200 OK, valid OOXML):
  `https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-allw.xlsx`
  I parsed it. It reveals the actual implementation: SSI US Gov Money Market (33.15%), SPDR
  Portfolio S&P 500 (SPYM), T-bills, SPDR Portfolio EM (SPEM), SPDR S&P China (GXC), a long ladder
  of individual TIPS (07/34 through 02/56), **a total-return swap on BCOMTR (Bloomberg Commodity
  Index Total Return)**, COMEX gold futures, FTSE 100 futures, TOPIX futures, and FX positions.

**This is the most important practical finding in this briefing.** It is a live, daily-priced,
publicly reported vehicle actually constructed by Bridgewater, with disclosed holdings. It has
**18 months of history and an 85bp fee drag**, so it settles nothing statistically — but it is the
only honest thing in the public domain that can be called "All Weather" without a caveat.

---

## 4. Risk parity construction, properly

### 4.1 Risk contributions (Maillard, Roncalli & Teiletche)

Fetched: `http://www.thierry-roncalli.com/download/erc.pdf` [F] — "On the properties of
equally-weighted risk contributions portfolios", first version June 2008, this version May 2009;
published *Journal of Portfolio Management* 36(4), 60–70, 2010.

For weights `x = (x_1,...,x_n)` and covariance `Σ`, portfolio volatility is `σ(x) = sqrt(x'Σx)`.

**Marginal risk contribution:**

```
∂_i σ(x) = ∂σ(x)/∂x_i = ( x_i σ_i² + Σ_{j≠i} x_j σ_ij ) / σ(x)  =  (Σx)_i / σ(x)
```

**Total risk contribution:** `σ_i(x) = x_i · ∂_i σ(x)`

Because σ is homogeneous of degree 1, **Euler's theorem** gives the exact decomposition:

```
σ(x) = Σ_{i=1}^{n} σ_i(x)
```

This is the whole justification for the phrase "risk contribution" — it is an exact additive
decomposition of portfolio volatility, not an approximation.

**The ERC portfolio** is defined (paper's equation 1–2), long-only:

```
x* = { x ∈ [0,1]^n : Σ x_i = 1,  x_i·(Σx)_i = x_j·(Σx)_j  for all i,j }
```

The budget constraint is pure normalisation: any positive `y` with equal risk contributions
rescales to the ERC solution.

**Two-asset closed form.** With `x = (w, 1−w)`, equal risk contributions requires
`w²σ_1² = (1−w)²σ_2²`, whose unique solution in [0,1] is

```
x* = ( σ_1^{-1} , σ_2^{-1} ) / ( σ_1^{-1} + σ_2^{-1} )
```

**This is the key result for honest benchmarking:** in two assets, ERC *is* inverse-volatility
weighting, and correlation drops out entirely. More generally, **inverse-vol weighting equals ERC
exactly when all pairwise correlations are equal.** When they are not, they differ — and the
stock/bond correlation regime shift of 2021–2023 is precisely the case where they diverge.

**Inverse-volatility (naive risk parity):**

```
w_i = (1/σ_i) / Σ_j (1/σ_j)
```

**General risk budgeting** (budgets `b_i`, `Σb_i = 1`): `x_i·(Σx)_i = b_i · σ²(x)`. Under this
notation, All Weather's published "25% of risk per environment box" is a risk budget over
*environments*, not over assets — a strictly harder object to replicate, because it requires
mapping assets to environmental exposures first.

**Ordering result from the paper:** `σ_min-variance ≤ σ_ERC ≤ σ_equal-weight`. ERC sits between
minimum variance and 1/n, and is "similar to a minimum variance portfolio subject to a
diversification constraint on the weights".

**Solving it.** Equations (2) are a nonlinear system. Standard practicable routes:
(a) least-squares `min Σ_{i,j} ( x_i(Σx)_i − x_j(Σx)_j )²` — non-convex, seed-sensitive;
(b) the convex log-barrier form `min ½ x'Σx − Σ_i b_i ln(x_i)` subject to `x > 0`, then renormalise —
this is convex and has a unique solution, and is what you should use if you want determinism.

### 4.2 Adding leverage

The ERC/inverse-vol portfolio is low-volatility by construction. To reach an equity-like target vol
`σ*`, scale:

```
k = σ* / σ(x_ERC)
w_levered = k · x_ERC
```

The levered portfolio's return, honestly accounted:

```
r_p = r_f + k·( r_ERC − r_f ) − (k − 1)·s
```

where `r_f` is the cash rate and **`s` is the financing spread over cash**. That last term is the
one every promotional backtest omits, and it is exactly where the academic argument lives (§5.2).
At k ≈ 1.86 (ALLW's current notional) a 50bp financing spread costs ~43bp/yr; a 100bp spread
costs ~86bp/yr, against Bridgewater's own claimed edge of ~250bp/yr.

Two implementation notes that matter for a replication:

- **Futures returns are already excess returns.** AQR make this point explicitly: "When we apply
  leverage by using futures, the return series is clearly implementable and no assumption of the
  financing cost is needed because futures returns, F_t/F_{t−1} − 1, are already excess returns."
  This is true, but it relocates the financing cost into the futures basis rather than eliminating it.
- ALLW's actual implementation confirms the futures/swap route: gold futures, FTSE 100 futures,
  TOPIX futures, a BCOMTR total-return swap, plus ~33% in a government money-market fund as
  collateral.

---

## 5. The sceptical case

### 5.1 The case FOR (AQR)

Asness, Frazzini & Pedersen, "Leverage Aversion and Risk Parity", *FAJ* 68(1), 47–59, 2012. [F]
`https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Leverage-Aversion-and-Risk-Parity.pdf`

Construction: monthly, weight each asset class at the inverse of its vol estimated from **three-year
monthly excess returns up to month t−1**, then scale by a constant to match the ex-post realised vol
of the value-weighted benchmark. Note that last step: the leverage constant is chosen using the
**full-sample realised volatility of the benchmark** — a global, forward-looking scaling. It is not
implementable in real time as stated.

Table 2, long sample (CRSP US stocks and bonds, 1926–2010), annualised:

| | Excess return | t-stat | Vol | Sharpe |
|---|---|---|---|---|
| CRSP stocks | 6.71%* | 3.18 | 19.05% | 0.35 |
| CRSP bonds | 1.56%* | 4.28 | 3.28% | 0.47 |
| Value-weighted | 3.84%* | 2.30 | 15.08% | 0.25 |
| 60/40 | 4.65%* | 3.59 | 11.68% | 0.40 |
| RP, unlevered | 2.20%* | 4.67 | 4.25% | 0.52 |
| **RP, levered** | **7.99%*** | 4.78 | 15.08% | **0.53** |
| RP minus 60/40 | 3.34%* | 2.93 | 10.31% | 0.32 |

Broad sample (global stocks, US bonds, credit, S&P GSCI commodities, **1973–2010**):

| | Excess return | t-stat | Vol | Sharpe |
|---|---|---|---|---|
| Value-weighted | 4.31%* | 2.50 | 10.10% | 0.43 |
| RP, levered | 6.15%* | 3.57 | 10.10% | 0.61 |
| **RP minus value-weighted** | **1.84%** | **1.43** | 7.52% | 0.24 |

Read that last row carefully. In the **broad** sample — the one that actually includes commodities,
i.e. the one resembling All Weather — the outperformance over the market portfolio is **1.84% with a
t-statistic of 1.43, not significant at 5%**. The starred, significant results are the stocks-and-bonds-
only long sample. This is stated in AQR's own table and is routinely not quoted.

AQR's own disclosed limitation, verbatim: "the simulated performance of the levered RP portfolio
**does not reflect any adjustment of the returns for the costs of leverage**, such as financing
spreads and costs associated with deleveraging."

Their pre-emption of the bond-bull-market objection: 1926–2010 "reveals a near-perfect round trip in
bond yields and a near doubling of the equity market's valuation (using the 10-year P/Es of Robert
Shiller). Thus, if anything, 1926–2010 was a period biased in favor of equities over bonds."

AQR's "Risk Parity: Why We Lever" [F] adds: "Risk parity is often referred to as a 'levered bet on
bonds.' It's more accurate to think of risk parity as levering an entire diversified portfolio."
That piece does not discuss financing costs.

### 5.2 The case AGAINST — Anderson, Bianchi & Goldberg

"Will My Risk Parity Strategy Outperform?", *FAJ* 68(6), 75–93, 2012. Working paper (10 Nov 2011)
fetched in full: `https://eml.berkeley.edu/~anderson/risk%20parity111111.pdf` [F]

Same universe as AQR's long sample (CRSP US equity + US Treasuries, 1926–2010, monthly rebalance,
levered RP scaled to match the market's ex-post vol). Their result is a sequence, and the sequence
is the argument:

1. **Financed at the 90-day T-bill rate**: levered risk parity has the highest cumulative return
   "by a factor of three."
2. **Financed realistically**: they substitute the 3-month Eurodollar deposit rate (a LIBOR proxy)
   from 1971, and T-bill + 60bp for 1926–1970, on the grounds that "we financed the levered risk
   parity strategy at the 90-day T-Bill Rate, but that is **not possible in practice**." Result:
   "the 60/40 strategy had a slightly higher return than levered risk parity over the long horizon,
   1926–2010."
3. **Adding trading costs** (1% 1926–1955, 0.5% 1956–1970, 0.1% 1971–2010, applied to price-change-
   induced turnover; "leverage exacerbates turnover"): "From the perspective of return, 60/40 is
   the dominant strategy."

**The entire long-sample advantage of levered risk parity is consumed by a ~60bp financing spread
plus turnover costs.** That is the single most important number in the sceptical literature.

Their sub-period decomposition is equally damaging to any single headline figure:

| Sub-period | Winner |
|---|---|
| Pre-1946 (1926–1945) | Levered risk parity |
| Post-War (1946–1982) | 60/40 and value-weighted both beat risk parity |
| Bull Market (1983–2000) | Levered RP, 60/40, value-weighted — tie |
| Last 10 years (2001–2010) | Levered RP; even *unlevered* RP beat 60/40 and VW |

The 1946–1982 sub-period is the one with rising rates. Their conclusion, stated as a general
methodological warning rather than a verdict: "even over periods lasting decades, the specific start
and end dates of a backtest can have a material effect on the results."

They also note the reflexivity problem, which is worth quoting because it applies to this project
directly: "since we do not know how the availability of modern financing methods during the period
1926–1971 might have affected the course of history, our results should be interpreted with caution."
And: "The cost of financing the high degree of leverage in a levered risk parity strategy can [erode
returns]... when interest rates go up, the cost of financing also goes up."

### 5.3 Other critics

- **Ben Inker / GMO, "The hidden risks of risk parity portfolios" (2010).** Primary source
  (top1000funds.com) returned **403 — not fetched**. [S] The reported arguments: investors adopting
  risk parity are "loading up on fixed income duration after the best run for bonds in history";
  risk parity confuses volatility with risk and includes negatively-skewed assets; corporate
  leverage embedded in equities is long-term and not marked to market, unlike portfolio leverage
  (a direct rebuttal of Dalio's "S&P 500 debt-to-equity is about 1:1" argument). **Verify before
  citing.**
- **Sullivan & Wey, "Risk Parity and its Discontents", Darden working paper, 4 Mar 2025**
  (SSRN 5165202). SSRN returned **403 — abstract not fetched**. [S] Reported: using both realised
  net-of-fee risk parity manager returns and a backtest from 1951, risk parity "generally
  underperforms a traditional 60/40 portfolio", with lower annualised returns and inferior Sharpe
  and Sortino ratios; "the magnitude of bond yield changes and the starting level of bond yields
  plays a critical role in explaining historical risk parity drawdowns." This is the most recent and
  most directly relevant critique. **Get the PDF before relying on it.**

### 5.4 2022 — the out-of-sample test

Reported by Markov Processes International [F]
`https://www.markovprocesses.com/blog/risk-parity-not-performing-blame-the-weather/`:

| | |
|---|---|
| All Weather 2022 | **−22%** |
| All Weather 2008 | −20% |
| Global 60/40, 2022 | −16.1% |
| All Weather AUM (at time of writing) | $32bn |
| All Weather 2023 through Nov | +4.5% vs global 60/40 +10.5% |

All Weather's worst year was **not** the Global Financial Crisis — it was the inflation shock. That
is precisely the quadrant the strategy exists to cover. MPI attribute this to (a) commodities being
the only genuine inflation hedge that worked, (b) a historic rate-hiking cycle hitting a
duration-heavy book, and (c) the stock-bond correlation flipping positive, which destroys the
diversification the leverage is predicated on.

**This is a secondary source reporting private fund returns.** It is the best available, and it is
not audited. Any use of "−22% in 2022" must carry that caveat.

### 5.5 The even-handed summary

The pro case rests on a stocks-and-bonds-only 1926–2010 sample, with leverage scaled using
full-sample realised vol, and with financing costs explicitly excluded. When commodities are added
(1973–2010) the outperformance loses significance. When realistic financing and turnover costs are
added, the long-sample advantage disappears entirely and 60/40 dominates on return. The strategy
won 2001–2010, lost 1946–1982, and had its worst-ever year in 2022. The honest reading is that
**a large fraction of the measured edge is a joint bet on falling rates and negative stock-bond
correlation**, and that both of those were features of a specific 40-year regime. That does not make
the diversification argument wrong; it makes the historical evidence for it far weaker than the
marketing implies.

---

## 6. Data availability, series by series, with gaps named

All availability below was **tested by HTTP request in this session** on 2026-09-12. "Keyless" means
no API key, no account, no auth header.

### 6.1 The headline finding about FRED

**FRED is close to useless for total returns.** Verified:

| Series | What happened |
|---|---|
| `SP500` | Returns data only from **2016-09-12** — a hard 10-year rolling window. Price index only, no dividends. |
| `DJIA` | Same 10-year window (from 2016-09-12). |
| `BAMLCC0A0CMTRIV` (ICE BofA US Corporate **Total Return** Index) | Returns only from **2023-09-12** — a **3-year rolling window**, even with `&cosd=1900-01-01`. |
| `BAMLHYH0A0HYM2TRIV` | Same 3-year window. |
| `GOLDAMGBD228NLBM` / `GOLDPMGBD228NLBM` (LBMA gold) | **HTTP 404 — series removed from FRED.** |
| `WILL5000IND`, `WILL5000INDFC` | 404 — discontinued. |

The licensed vendor series (S&P, Dow Jones, ICE BofA, LBMA) are either truncated to a rolling window
or gone. **There is no long US equity or bond total-return series on FRED.** Plan accordingly.

The keyless CSV endpoint that does work:
`https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=1900-01-01`

### 6.2 What FRED IS good for — yields and cash rates (all verified keyless)

| Series | Starts | Use |
|---|---|---|
| `DGS5` | 1962-01-02 | 5y CMT yield |
| `DGS10` | 1962-01-02 | 10y CMT yield |
| `DGS20` | 1962-01-02 | 20y CMT yield |
| `DGS30` | 1977-02-15 | 30y CMT yield. Verified **continuous with no missing values** through the 2002–2006 window when the 30-year bond was not issued — Treasury supplied an extrapolated factor. Treat 2002–2006 as derived, not observed. |
| `DFII5` | 2003-01-02 | 5y TIPS real yield |
| `DFII7` | 2003-01-02 | 7y TIPS real yield |
| `DFII10` | 2003-01-02 | 10y TIPS real yield |
| `DFII20` | 2004-07-27 | 20y TIPS real yield |
| `DFII30` | **2010-02-22** | 30y TIPS real yield |
| `DLTIIT` | 2000-01-03 | Treasury inflation-indexed long-term average yield — the **earliest** TIPS yield on FRED |
| `T10YIE` | 2003-01-02 | 10y breakeven inflation |
| `EXPINF10YR` | 1982-01-01 | Cleveland Fed 10y expected inflation (model-based, not market) |
| `TB3MS` | **1934-01-01** | 3m T-bill, monthly — best long cash rate |
| `DTB3` | 1954-01-04 | 3m T-bill, daily |
| `FEDFUNDS` | 1954-07-01 | Fed funds |
| `DGS1MO` | 2001-07-31 | 1m CMT |
| `SOFR` | 2018-04-03 | Overnight financing rate (post-LIBOR) |
| `PPIACO` | 1913-01-01 | All-commodities PPI — **not investable, not a return series** |
| `PALLFNFINDEXQ` | 1992-01-01 | IMF global commodity price index — **not investable** |

**Named gap:** there is **no keyless public series for the pre-2018 financing rate at which a levered
portfolio could actually borrow.** FRED's LIBOR series (`USD3MTD156N` and family) were discontinued
after the LIBOR transition. Anderson-Bianchi-Goldberg used the 3-month Eurodollar deposit rate
(`DED3` was FRED's id; **not tested this session — verify**). Without it, you are forced into either
T-bill + an assumed spread (which is the exact assumption the entire debate turns on) or futures-
implied financing (which requires futures data you do not have).

### 6.3 Asset class by asset class

#### US equities — **SOLVED, free, long**

- **Kenneth French Data Library** — verified keyless, HTTP 200, 13,067 bytes.
  `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip`
  Contains `F-F_Research_Data_Factors.csv`: monthly `Mkt-RF, SMB, HML, RF`, **1,201 monthly rows
  from 192607 to 202607**, built from the 202607 CRSP database. `Mkt-RF + RF` gives a US total-return
  market series from **July 1926**. `RF` gives the 1-month T-bill (Ibbotson to 202405, ICE BofA
  1-Month T-Bill Index thereafter — documented in the file header). This also solves your cash rate.
- **Robert Shiller's `ie_data.xls`** — verified, HTTP 200, 1,623,552 bytes, valid Excel, last saved
  2024-09-04. `https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/ie_data.xls`
  Monthly S&P composite price, dividends and earnings from 1871 — a total return series can be
  constructed. (HEAD returns 204; you must use GET.)
- **Damodaran, NYU** — `https://pages.stern.nyu.edu/~adamodar/pc/datasets/histretSP.xls`, verified
  HTTP 200, 527,872 bytes. **Annual** S&P 500, 10y T-bond and T-bill returns from 1928. Annual only.

#### Nominal Treasuries — **SOLVED via a derived public dataset**

FRED has yields but no returns. The gap is filled by:

**Swinkels (2019), "Treasury Bond Return Data Starting in 1962", *Data* 4(3), 91.** Paper fetched
in full: `https://repub.eur.nl/pub/117405/Swinkels-2019-Data.pdf` [F]

He converts constant-maturity yields to total returns with par-bond duration/convexity formulas:

```
D_t(Y_t, M_t) = (1/Y_t)·[ 1 − 1/(1 + 0.5·Y_t)^(2·M_t) ]                                     (1)

C_t(Y_t, M_t) = (2/Y_t²)·[ 1 − 1/(1 + 0.5·Y_t)^(2·M_t) ] − (2·M_t)/[ Y_t·(1 + 0.5·Y_t)^(2·M_t + 1) ]   (2)

R_t(Y_{t−1}, Y_t, M_t) = Y_{t−1} − D_t·(Y_t − Y_{t−1}) + ½·C_t·(Y_t − Y_{t−1})²             (3)
```

with the carry term `Y_{t−1}` expressed per period, i.e. `(1+Y_t)^{1/12} − 1` for a monthly return,
and duration/convexity terms in annual units. Applicable to **par bonds** — valid for on-the-run CMT
inputs, and he is explicit that the formulas assume promised cash flows are always paid, so they are
**not valid for corporate bonds**.

He validates against Global Financial Data (`TRUSG10M`), CRSP's US Treasury and Inflation Indexes,
Ibbotson (a 63.5% long / 36.5% intermediate blend chosen to match volatility), and Bloomberg, and
concludes the series are "very close to alternative series that can be purchased."

The published dataset: **"Historical Data: International monthly government bond returns"**, DOI
`10.25397/eur.8152748.v6` (figshare API confirms the record; the DOI currently redirects to
DataverseNL `doi:10.34894/YWT2IX`, HTTP 200). Coverage per his data page [F]
`https://laurensswinkels.com/data/`: **US from 1947**, Norway 1921, Sweden 1920, Australia 1969,
UK 1970, Germany 1972, Japan 1974, Canada 1986, France 1987. Monthly.

**Caveat to state plainly:** this is a *constant-maturity 10-year* return, derived from yields via a
second-order approximation. It is not an index of a real bond portfolio, has no roll-down from a
laddered book, no bid-ask, and no maturity dispersion (he flags the last one himself: "For better
approximations, the dispersion in maturity of the bond portfolio is needed as an input, which we do
not have available"). For a long/intermediate split you would apply the same formulas to `DGS20` or
`DGS30` and `DGS5` from FRED yourself — and for the long sleeve you are limited to **1977-02-15**
(DGS30) or **1962-01-02** (DGS20).

#### TIPS / inflation-linked bonds — **HARD GAP**

- **The asset did not exist before 1997-01-29**, the date of the first 10-year TIPS auction (5-year
  later in 1997; 30-year in 1998). [S — TreasuryDirect history page surfaced in search; not fetched.
  Verify at `https://www.treasurydirect.gov/research-center/history-of-marketable-securities/tips/`]
- **The earliest usable FRED real yield is 2000-01-03 (`DLTIIT`); the clean constant-maturity series
  start 2003-01-02 (`DFII5/7/10`), 2004-07-27 (`DFII20`), 2010-02-22 (`DFII30`).**
- The `TIP` ETF's price history on Yahoo begins **2003-12-01** (verified, 275 monthly observations).
- **No free TIPS total-return index exists.** Bloomberg US TIPS and ICE BofA TIPS are paid. FRED's
  ICE BofA total-return family is capped at a 3-year rolling window (§6.1).
- Swinkels's public data page lists **no inflation-linked bond series** (confirmed by reading it).

**Consequence:** you can build a TIPS total return from ~2003 by applying the Swinkels formulas to
`DFII10`, accepting that it ignores the inflation-accrual on principal and the deflation floor, or
you can use `TIP` from Dec 2003 and eat the 19bp fee. **Before 1997 there is nothing, and nothing
can be honestly simulated without a paid source or a model.** This removes the entire rising-
inflation quadrant — Bridgewater's self-described "final ingredient" — from any pre-1997 backtest.

#### Gold — **SOLVED, free, long**

- **LBMA price JSON, keyless, verified**: `https://prices.lbma.org.uk/json/gold_pm.json` returns
  **14,681 daily observations, 1968-04-01 to 2026-09-11**. Also available: `gold_am.json`,
  `silver.json` (both HTTP 200).
- **datahub gold-prices monthly CSV, keyless, verified**:
  `https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv` — **1833-01 to
  2026-08**. Provenance beyond 1968 is a compilation; treat pre-1968 with suspicion and note that
  the price was administratively fixed for much of it.
- **The FRED LBMA series are gone (404).** Anyone whose pipeline uses `GOLDAMGBD228NLBM` has a
  broken pipeline.
- Caveat: **gold has no yield, so spot price return IS total return, less storage.** This is the one
  asset where a price series is honestly a total-return series. GLD's 40bp expense ratio is the real-
  world drag; `GLD` on Yahoo starts 2004-11.

#### Broad commodities — **THE HARDEST GAP**

| Source | Verified availability |
|---|---|
| `^SPGSCI` (Yahoo) | **1985-01 to present**, 502 monthly obs — but this is the S&P GSCI headline index and I could **not** establish whether Yahoo serves the spot, excess-return or total-return variant. **Do not use until identified.** |
| `^SPGSCITR` (Yahoo) | **n = 1.** No history. |
| `^BCOM` (Yahoo) | **n = 1** (a single 2020-05-28 point). No usable history. |
| `GSG` (iShares S&P GSCI ETF) | 2006-07 |
| `DBC` (Invesco DB Commodity) | 2006-02 |
| `DJP` (iPath Bloomberg Commodity ETN) | 2006-10 |
| `PDBC` | 2014-11 |
| FRED `PPIACO` / `PALLFNFINDEXQ` | Long, but **price indices, not investable returns** — no roll yield, no collateral yield |

**Plainly: there is no free, keyless, correctly-identified broad commodity total-return series.**
S&P GSCI Total Return and Bloomberg Commodity Index Total Return are licensed products. Bridgewater
themselves access BCOMTR through a **total-return swap** (visible in the ALLW holdings file) — i.e.
they pay for it.

With free data your commodity sleeve starts **2006** (ETFs), or 1985 with an unidentified index
variant. Everything earlier requires either a paid index licence or building your own index from
futures curves, which needs futures data you also do not have keylessly.

#### The ALLW benchmark itself

- Daily holdings .xlsx: keyless, verified 200, valid OOXML (20,103 bytes). **This is a genuine,
  free, daily disclosure of a real Bridgewater-constructed portfolio.**
- NAV/price history: `ALLW` via Yahoo (unofficial API) from 2025-03.
- **18 months of history.** Statistically it can settle nothing. It is a sanity check on
  construction, not a benchmark with power.

### 6.4 Access mechanisms — what works and what does not

| Source | Keyless? | Verified result |
|---|---|---|
| FRED `fredgraph.csv` | Yes | Works; series coverage is the problem, not access |
| Ken French data library | Yes | 200, zip, parsed |
| Shiller `ie_data.xls` | Yes | 200 on GET (204 on HEAD), 1.6MB |
| Damodaran `histretSP.xls` | Yes | 200, 528KB |
| LBMA `prices.lbma.org.uk/json/*.json` | Yes | 200, 14,681 gold PM observations |
| datahub gold-prices (GitHub raw) | Yes | 200 |
| Swinkels figshare/DataverseNL | Yes | DOI resolves 200 |
| SSGA ALLW daily holdings .xlsx | Yes | 200, valid OOXML |
| **Stooq** | **No longer** | Serves a **JavaScript SHA-256 proof-of-work challenge**; CSV endpoint returns an HTML interstitial, not data. **A pipeline depending on Stooq will silently break.** |
| **iShares product ajax CSV** | **No** | Returns the HTML product page, not CSV |
| **Yahoo `query1.finance.yahoo.com/v8/finance/chart/`** | Technically yes | Works, returns adjusted close, but it is an **undocumented, unsupported, ToS-ambiguous endpoint**. It is the only free route to `^SP500TR` (1988-01), `VUSTX` (1986-05), `VFITX` (1991-10), `TIP` (2003-12), `GLD` (2004-11). Do not build a reproducible pipeline on it without accepting it may be revoked. |
| SSRN, CFA Institute, MDPI supplementary, top1000funds, CNBC, Bogleheads | **No** | All returned **403** to WebFetch this session |

### 6.5 The honest CAN / CANNOT list

**CAN be built, monthly, keyless, deterministically:**

- US equity total return from **1926-07** (Ken French `Mkt-RF + RF`), or from 1871 (Shiller).
- Risk-free / cash rate from **1926-07** (French `RF`) or **1934-01** (FRED `TB3MS`).
- Nominal Treasury total returns: 10-year from **1962** (Swinkels formulas on `DGS10`, or his
  published dataset from **1947** for the US); 20-year from **1962** (`DGS20`); 30-year from
  **1977** (`DGS30`); 5-year from **1962** (`DGS5`).
- Gold total return from **1968** (LBMA), arguably earlier with a caveat.
- A live, disclosed Bridgewater All Weather portfolio from **2025-03** (ALLW).
- Therefore: a **three-asset (equity / long Treasury / gold) risk parity backtest from 1968**, and a
  **two-asset (equity / Treasury) one from 1926**, both fully reproducible from free sources.

**CANNOT be built without a paid source:**

- **Any broad commodity total return before 2006.** Not obtainable. This is the binding constraint.
- **Any TIPS return before 1997** — the security did not exist. Any TIPS return before **2003**
  requires `DLTIIT` (2000) plus modelling, and no TIPS *total-return index* is free at any date.
- **A realistic financing rate before 2018** for the levered leg — LIBOR series are discontinued;
  Eurodollar deposit rates need verification.
- **Credit (corporate, EM)** — two of the four boxes in Bridgewater's published map include credit.
  FRED's ICE BofA total-return series are truncated to 3 years. No free long credit TR series was
  found. Swinkels's formulas explicitly do not apply to corporates.
- **Non-US equities and bonds** beyond what Swinkels publishes (his country bond coverage starts
  1969–1987 outside the US/Nordics).
- **Bridgewater's actual All Weather fund returns.** Not public at any price.

**The structural consequence:** a full four-quadrant replication — equities, nominal bonds, IL bonds,
commodities, credit — **cannot start before 2006 on free data**, and even then the commodity sleeve
is an ETF with tracking error and fees rather than an index. Any backtest claiming a 1970s or 1980s
start has either bought index licences or has quietly substituted something that did not exist.

---

## 7. Look-ahead and backtest traps specific to this

### 7.1 The index-inception problem (the big one here)

- **S&P GSCI**: launched **1991**, with history **backfilled to 1970** (some sources say 1969; one
  source says traded from 1992). [S — Wikipedia and a SummerHaven history PDF surfaced in search;
  not fetched. Verify.]
- **Bloomberg Commodity Index**: launched **1998** as the Dow Jones-AIG Commodity Index, history
  **backfilled to 1991**; renamed DJ-UBS 2009, Bloomberg Commodity Index 2014-07-01. [S]

So any commodity sleeve before 1991 is backfilled index construction, and before 1970 does not exist
at all. The index designer chose the weights and roll rules **knowing** the 1970s. AQR's own broad
sample starts 1973 with S&P GSCI — i.e. it uses 18 years of backfill.

- **TIPS**: first auction **1997-01-29**. Any inflation-linked sleeve before then is a simulation,
  and a simulation calibrated by people who knew what inflation did.
- **The ETF vehicles**: GLD 2004-11, TIP 2003-12, GSG 2006-07, DBC 2006-02, DJP 2006-10. If you use
  an ETF as a proxy, your investable history starts when it started, not when the index did.

**The rule this implies for a project with an `as_of` discipline:** an asset class should not enter
the investable universe at date `t` unless an investable vehicle for it existed at `t`. Applied
honestly, that means no commodities before 1991 (index) or 2006 (fund), no TIPS before 1997 (bond)
or 2003 (fund). Applied to All Weather, **the strategy's own published four-box map cannot be fully
populated with investable assets before 1997.**

### 7.2 Rebalancing assumptions

- **Frequency is a free parameter and it moves results.** AQR rebalance monthly. ABG rebalance
  monthly. Robbins/All Seasons rebalances annually. None of these is "correct"; picking the one that
  looks best is a look-ahead choice.
- **The vol estimate used for weights is a look-ahead trap.** AQR use "three-year monthly excess
  returns up to month t−1" — correctly lagged. But note what they do next: "these weights are
  multiplied by a constant to match the **ex post realised volatility** of the value-weighted
  benchmark." That constant is estimated over the **full sample**. A real-time implementation cannot
  know it. Any replication must either fix the leverage target ex ante (e.g. ALLW's stated 10–12%
  band) or use an expanding-window vol estimate — never a full-sample one.
- **Rebalancing timing within the month.** Rebalancing at the close of month `t` using data through
  month `t` is instantaneous execution at the price you used to decide. A one-day or one-week lag
  changes 2008 and 2020 materially.
- **Rebalancing is a short-volatility, mean-reversion bet.** A large part of the measured "diversification
  premium" in any fixed-weight backtest is the rebalancing bonus, which is not a risk premium and
  which requires the counterparties to exist.

### 7.3 Transaction and financing costs

- ABG's cost schedule — **1% (1926–1955), 0.5% (1956–1970), 0.1% (1971–2010)** — is the only
  explicit, published, era-varying schedule I found. Using a flat modern cost (say 5bp) across a
  1926-start backtest is a look-ahead assumption that flatters every high-turnover strategy.
- "Leverage exacerbates turnover" (ABG). A 2x levered portfolio rebalancing to constant risk trades
  roughly twice the notional. Cost scales with leverage; the benefit does not.
- **Financing spread is the pivot of the whole literature.** T-bill financing → levered RP wins by
  3x. T-bill + ~60bp → 60/40 wins. That is the entire result. A backtest that does not state its
  financing assumption in the first paragraph is not reporting a result.
- **Deleveraging costs.** AQR acknowledge: "at high levels of leverage, the potential cost of forced
  deleveraging could be much more meaningful." No backtest models the March 2020 or September 2022
  margin spiral.

### 7.4 Survivorship and selection

- Less acute for asset-class indices than for single stocks, but not absent: the asset classes that
  *are* in the standard risk-parity universe are the ones that survived. Weimar bonds, Russian
  equities 1917, Japanese equities as a 1989 allocation — the universe is chosen with hindsight.
  Dalio's claim to have "stress-tested these concepts back to 1925 across multiple countries" is the
  right instinct; the published simulation starts in **1970**.
- **Strategy survivorship**: All Weather is the risk-parity strategy we are discussing *because* it
  survived and grew. The risk parity funds that closed after 2013 or 2022 are not in anyone's sample.
  Sullivan & Wey claim to use realised net-of-fee manager returns, which partially addresses this —
  another reason to get that paper. [S]

### 7.5 The regime-dependence trap, stated precisely

The specific danger for this project: a monthly risk-parity backtest over 1970–2021 is, mechanically,
**a levered long-duration position held across the largest bond bull market in recorded history**,
with a leverage multiplier that is *itself* larger precisely because bond volatility was low. Two
distinct tailwinds compound:

1. Falling yields → capital gains on the levered bond leg.
2. Low realised bond vol → inverse-vol weighting assigns *more* notional to bonds → more of (1).

And a third, which is the one 2022 exposed:

3. Negative stock-bond correlation → the diversification that justifies the leverage in the first
   place. When that correlation flipped positive in 2022, All Weather posted **−22%**, worse than
   2008, and worse than a global 60/40's −16.1%.

Carlson's 400bp gap between 1984–2013 (9.7%) and 1928–1983 (5.8%) for essentially the same allocation
is the cleanest single-number statement of this. Any benchmark comparison that does not report
sub-period results — at minimum a rising-rate period such as 1946–1982 and the 2021–2023 window —
is reporting the regime, not the strategy.

---

## Source ledger

**Fetched and read in full [F]:**

1. Dalio, *Engineering Targeted Returns and Risks*, Bridgewater, Aug 2011 (2004 article reprinted) — `https://bridgewater.brightspotcdn.com/fa/e3/d09e72bd401a8414c5c0bdaf88bb/bridgewater-associates-engineering-targeted-returns-and-risks-aug-2011.pdf`
2. Podolsky, Johnson & Jennings, *The All Weather Story*, Bridgewater, Jan 2012 — `https://www.bridgewater.com/_document/the-all-weather-story?id=00000171-8623-d7de-affd-feaf4ee20000`
3. Bridgewater, *The All Weather Story* landing page — `https://www.bridgewater.com/research-and-insights/the-all-weather-story`
4. Maillard, Roncalli & Teiletche, *On the properties of equally-weighted risk contributions portfolios*, May 2009 / JPM 36(4) 2010 — `http://www.thierry-roncalli.com/download/erc.pdf`
5. Asness, Frazzini & Pedersen, *Leverage Aversion and Risk Parity*, FAJ 68(1) 2012 — `https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Leverage-Aversion-and-Risk-Parity.pdf`
6. Anderson, Bianchi & Goldberg, *Will My Risk Parity Strategy Outperform?*, working paper 10 Nov 2011 (FAJ 68(6) 2012) — `https://eml.berkeley.edu/~anderson/risk%20parity111111.pdf`
7. Swinkels, *Treasury Bond Return Data Starting in 1962*, Data 4(3) 91, 2019 — `https://repub.eur.nl/pub/117405/Swinkels-2019-Data.pdf`
8. Swinkels data page — `https://laurensswinkels.com/data/`
9. AQR, *Risk Parity: Why We Lever* — `https://www.aqr.com/Insights/Perspectives/Risk-Parity-Why-We-Fight-Lever`
10. Carlson, *Back-Testing The Tony Robbins All-Weather Portfolio*, 2014 — `https://awealthofcommonsense.com/2014/11/back-testing-tony-robbins-weather-portfolio/`
11. Markov Processes International, *Risk Parity Not Performing? Blame The Weather* — `https://www.markovprocesses.com/blog/risk-parity-not-performing-blame-the-weather/`
12. State Street, ALLW product page — `https://www.ssga.com/us/en/intermediary/etfs/state-street-bridgewater-all-weather-etf-allw`
13. State Street, ALLW daily holdings — `https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-allw.xlsx`
14. Goldberg & Mahmoud, *Risk Without Return*, arXiv 1307.0114 — fetched; **note: this is Goldberg & Mahmoud, NOT the Anderson-Bianchi-Goldberg FAJ paper.** Relevant on turnover costs and risk-only strategies, not the source of the 60/40 comparison.

**NOT fetched — 403 or paywall, flagged in text [S]:**

- Sullivan & Wey, *Risk Parity and its Discontents*, Darden WP, Mar 2025 (SSRN 5165202) — **get this; it is the most current critique**
- Anderson, Bianchi & Goldberg, published FAJ version (CFA Institute paywall) — working paper used instead
- Inker / GMO, *The hidden risks of risk parity portfolios* (top1000funds, 403)
- CNBC 2018 Dalio interview (403)
- Bogleheads All Seasons thread (403)
- TreasuryDirect TIPS history page (search summary only)
- S&P GSCI and Bloomberg Commodity Index inception/backfill dates (search summary only)
- MDPI supplementary data for Swinkels 2019 (403) — the figshare/DataverseNL DOI resolves instead

**Live availability tests performed 2026-09-12** (all results in §6): 30+ FRED series ids, Ken French,
Shiller, Damodaran, Stooq, LBMA, datahub, Yahoo chart API (16 tickers), iShares ajax, SSGA holdings,
Swinkels figshare DOI.
