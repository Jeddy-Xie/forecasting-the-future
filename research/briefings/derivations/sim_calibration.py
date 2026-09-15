"""Two derived numbers for the briefing (seeded, deterministic).
A. Noise floor of 10-bin ECE for a PERFECTLY calibrated forecaster at small n.
B. Out-of-sample effect of recalibration (Platt, isotonic, beta, shrink-to-climatology,
   ridge-Platt) fitted on n observations, scored on 200k fresh observations."""
import numpy as np
rng = np.random.default_rng(20260915)
sig = lambda z: 1/(1+np.exp(-z)); logit = lambda p: np.log(p/(1-p))

def ece(p, y, bins=10):
    idx = np.clip(np.digitize(p, np.linspace(0,1,bins+1)[1:-1]), 0, bins-1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.any(): tot += m.sum()*abs(p[m].mean()-y[m].mean())
    return tot/len(p)

def draw_p(n, mu=-1.2, sd=1.2):  # latent true probabilities, base rate ~0.28
    return sig(rng.normal(mu, sd, n))

print("A. ECE of a perfectly calibrated forecaster (true p ~ logit-normal(-1.2,1.2)), 10 bins, 20000 reps")
for n in [31, 50, 62, 100, 155, 310, 1000]:
    e = np.array([ece(p:=draw_p(n), (rng.random(n) < p).astype(float)) for _ in range(20000)])
    print(f"  n={n:5d}  median ECE={np.median(e):.3f}  90th pct={np.quantile(e,.9):.3f}  P(ECE<0.10)={np.mean(e<0.10):.2f}")

def fit_logistic(X, y, ridge=1e-6, prior=None, iters=50):
    # Newton-Raphson; ridge penalises distance from `prior` (default 0)
    w = np.zeros(X.shape[1]) if prior is None else prior.copy()
    pr = np.zeros(X.shape[1]) if prior is None else prior
    for _ in range(iters):
        p = sig(X@w); g = X.T@(p-y) + ridge*(w-pr)
        H = X.T@(X*(p*(1-p))[:,None]) + ridge*np.eye(X.shape[1])
        w = w - np.linalg.solve(H, g)
    return w

def pav(x, y):
    o = np.argsort(x); xs, ys = x[o], y[o].astype(float)
    vals, wts, ends = [], [], []
    for i, v in enumerate(ys):
        vals.append(v); wts.append(1.0); ends.append(i)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v2, w2 = vals.pop(), wts.pop(); e2 = ends.pop()
            vals[-1] = (vals[-1]*wts[-1]+v2*w2)/(wts[-1]+w2); wts[-1] += w2; ends[-1] = e2
    fitted = np.empty(len(ys)); start = 0
    for v, e in zip(vals, ends): fitted[start:e+1] = v; start = e+1
    return xs, fitted

def iso_predict(xs, fitted, q):
    return np.clip(np.interp(q, xs, fitted), 0.01, 0.99)  # clip avoids 0/1 blow-ups

def run(scenario, a_true, b_true, n, reps=1000, ntest=40000):
    pt = draw_p(ntest); yt = (rng.random(ntest) < pt).astype(float)
    qt = sig(a_true*logit(pt)+b_true)
    raw = np.mean((qt-yt)**2)
    res = {k: [] for k in ["platt","ridge_platt","beta","isotonic","shrink","climatology"]}
    for _ in range(reps):
        p = draw_p(n); y = (rng.random(n) < p).astype(float); q = sig(a_true*logit(p)+b_true)
        if y.min() == y.max():  # all-same outcomes: cannot fit; keep raw (recorded as zero change)
            for k in res: res[k].append(0.0)
            continue
        Xq = np.c_[np.ones(n), logit(q)]; Xt = np.c_[np.ones(ntest), logit(qt)]
        w = fit_logistic(Xq, y); res["platt"].append(np.mean((sig(Xt@w)-yt)**2)-raw)
        w = fit_logistic(Xq, y, ridge=5.0, prior=np.array([0.,1.])); res["ridge_platt"].append(np.mean((sig(Xt@w)-yt)**2)-raw)
        Xb = np.c_[np.ones(n), np.log(q), -np.log(1-q)]; Xbt = np.c_[np.ones(ntest), np.log(qt), -np.log(1-qt)]
        w = fit_logistic(Xb, y); res["beta"].append(np.mean((sig(Xbt@w)-yt)**2)-raw)
        xs, f = pav(q, y); res["isotonic"].append(np.mean((iso_predict(xs,f,qt)-yt)**2)-raw)
        # shrink toward in-sample base rate, weight chosen by leave-one-out Brier on a grid
        grid = np.linspace(0,1,21); base = y.mean()
        loo_base = (y.sum()-y)/(n-1)
        best = min(grid, key=lambda lam: np.mean((lam*q+(1-lam)*loo_base-y)**2))
        res["shrink"].append(np.mean((best*qt+(1-best)*base-yt)**2)-raw)
        res["climatology"].append(np.mean((base-yt)**2)-raw)
    print(f"  {scenario:28s} n={n:4d} raw Brier={raw:.4f} | " + " | ".join(
        f"{k}: {np.mean(v):+.4f} (hurt {np.mean(np.array(v)>0):.0%})" for k, v in res.items()))

print("\nB. Change in out-of-sample Brier from recalibrating on n obs (negative = helps). 'hurt' = share of reps where it made things worse.")
for n in [31, 50, 100, 300]:
    run("well-calibrated (a=1,b=0)", 1.0, 0.0, n)
    run("overconfident (a=1.6,b=0)", 1.6, 0.0, n)
    run("overconf+biased (a=1.6,b=.5)", 1.6, 0.5, n)
    run("underconfident (a=0.6,b=0)", 0.6, 0.0, n)
