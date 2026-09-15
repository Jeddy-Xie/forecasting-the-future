"""Derived benchmarks for the briefing. Deterministic (bootstrap seed fixed).
1. SPF mean probability of a quarterly real-GDP decline (RECESS2..5) vs outcome, against expanding climatology.
2. Real-time expanding-window probit of NBER recession on the 10y-3m Treasury spread (NY Fed form),
   targets: (a) recession in month t+12, (b) any recession month in (t, t+12]; against expanding climatology.
   Outcomes enter the fit/climatology only once resolved AND announced (400-day NBER lag, as in the project).
Data: Philadelphia Fed SPF prob.xlsx (RECESS sheet); FRED GDPC1 (current vintage), USREC, GS10, TB3MS."""
import numpy as np, pandas as pd
from scipy.stats import norm
from scipy.optimize import minimize
S = __file__.rsplit('/', 1)[0]
rng = np.random.default_rng(20260915)

def ece(p, y, bins=10):
    idx = np.clip(np.digitize(p, np.linspace(0, 1, bins + 1)[1:-1]), 0, bins - 1)
    return sum((idx == b).sum() * abs(p[idx == b].mean() - y[idx == b].mean()) for b in range(bins) if (idx == b).any()) / len(p)

def calib_slope(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4); x = np.log(p / (1 - p)); X = np.c_[np.ones_like(x), x]; w = np.zeros(2)
    for _ in range(50):
        q = 1 / (1 + np.exp(-X @ w)); w -= np.linalg.solve(X.T @ (X * (q * (1 - q))[:, None]) + 1e-9 * np.eye(2), X.T @ (q - y))
    return w  # intercept, slope (slope<1 = overconfident, >1 = underconfident)

def block_boot_bss(f, c, y, block, reps=5000):
    n = len(y); starts = np.arange(n - block + 1); out = []
    for _ in range(reps):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.choice(starts, int(np.ceil(n / block)))])[:n]
        out.append(1 - np.mean((f[idx] - y[idx]) ** 2) / np.mean((c[idx] - y[idx]) ** 2))
    return np.quantile(out, [0.05, 0.95])

def report(name, f, c, y, block):
    bs, bc = np.mean((f - y) ** 2), np.mean((c - y) ** 2); lo, hi = block_boot_bss(f, c, y, block)
    a, b = calib_slope(f, y)
    print(f"{name:58s} n={len(y):4d} base={y.mean():.3f} Brier={bs:.4f} clim={bc:.4f} BSS={1-bs/bc:+.3f} "
          f"90%CI[{lo:+.3f},{hi:+.3f}] ECE={ece(f, y):.3f} calib-slope={b:.2f} int={a:+.2f}")

# ---------- 1. SPF ----------
spf = pd.read_excel(f"{S}/spf_prob.xlsx", sheet_name="RECESS")
gdp = pd.read_csv(f"{S}/fred_GDPC1.csv", parse_dates=["observation_date"]).set_index("observation_date")["GDPC1"]
decline = (gdp.diff() < 0).astype(float); decline[gdp.diff().isna()] = np.nan
q = pd.PeriodIndex(decline.index, freq="Q"); decline.index = q
print("1. SPF probability of a quarter-on-quarter real GDP decline (current-vintage GDP; outcome = decline in target quarter)")
for k, lead in [(2, 1), (3, 2), (4, 3), (5, 4)]:
    rows = []
    for _, r in spf.iterrows():
        if pd.isna(r[f"RECESS{k}"]): continue
        survey = pd.Period(year=int(r.YEAR), quarter=int(r.QUARTER), freq="Q"); target = survey + lead
        if target not in decline.index or pd.isna(decline[target]): continue
        known = decline[decline.index <= survey - 1].dropna()   # quarters published by survey time (approx.)
        rows.append((r[f"RECESS{k}"] / 100, known.mean(), decline[target]))
    f, c, y = map(np.array, zip(*rows))
    report(f"SPF RECESS{k} ({lead} quarter(s) ahead{', = Anxious Index' if k == 2 else ''})", f, c, y, block=max(lead, 1))

# ---------- 2. Real-time yield-curve probit ----------
m = lambda sid: pd.read_csv(f"{S}/fred_{sid}.csv", parse_dates=["observation_date"]).set_index("observation_date")[sid]
df = pd.concat([m("GS10"), m("TB3MS"), m("USREC")], axis=1).dropna()
df["spread"] = df.GS10 - df.TB3MS
h, lag = 12, 13     # horizon; announcement lag in months (~400 days)
rec = df.USREC.values
df["y_at"] = pd.Series(rec, index=df.index).shift(-h)
df["y_within"] = pd.Series(rec, index=df.index)[::-1].rolling(h, min_periods=h).max()[::-1].shift(-1)
def probit_fit(x, y):
    X = np.c_[np.ones_like(x), x]
    nll = lambda w: -np.sum(y * norm.logcdf(X @ w) + (1 - y) * norm.logcdf(-(X @ w)))
    return minimize(nll, np.zeros(2), method="BFGS").x
print("\n2. Real-time expanding probit, NBER recession on 10y-3m spread (GS10 - TB3MS), 400-day announcement lag")
dates = df.index
for target in ["y_at", "y_within"]:
    for start, end in [("1975-01-01", "2025-12-01"), ("1990-01-01", "2025-12-01"), ("2006-01-01", "2025-12-01")]:
        fs, cs, ys = [], [], []
        for i, t in enumerate(dates):
            if t < pd.Timestamp(start) or t > pd.Timestamp(end) or np.isnan(df[target].iloc[i]): continue
            last = i - h - lag           # latest origin whose outcome is resolved and announced at t
            train = df.iloc[:last + 1].dropna(subset=[target])
            if len(train) < 120: continue
            w = probit_fit(train.spread.values, train[target].values)
            fs.append(norm.cdf(w[0] + w[1] * df.spread.iloc[i])); cs.append(train[target].mean()); ys.append(df[target].iloc[i])
        report(f"probit {'recession in month t+12' if target=='y_at' else 'any recession in (t,t+12]'} {start[:4]}-{end[:4]}",
               np.array(fs), np.array(cs), np.array(ys), block=h)
# NY Fed published coefficients (fitted 1959-2005) scored only on 2006+ (genuinely out of sample for them)
sub = df.loc["2006-01-01":"2025-12-01"].dropna(subset=["y_at"])
f = norm.cdf(-0.6045 - 0.7374 * sub.spread.values)
c = np.array([df.y_at.iloc[:dates.get_loc(t) - h - lag + 1].dropna().mean() for t in sub.index])
report("NY Fed fixed coefficients (Estrella-Trubin 2006), month t+12, 2006-2025", f, c, sub.y_at.values, block=h)
