"""D6: is the condition process first-order, as the composition assumes?

`models/indicator_forecast.py` composes an any-time-within-horizon question by
tracking survival, under one stated assumption: whether a condition holds depends
on last month's condition and this month's regime, and on nothing else. That
assumption is testable directly and, until now, was only tested indirectly through
calibration.

This fits both orders on the same months with the same regime weights and the same
shrinkage, and compares them by log likelihood with a BIC penalty for the extra
parameters. A clear preference for second order would mean the composition
understates persistence.

Run: .venv/bin/python research/derivations/condition_process_order.py
"""

from __future__ import annotations

from datetime import date

import numpy as np

from economic_regime_forecasting.backtest.walk_forward import prepare_indicator_history
from economic_regime_forecasting.command_line_interface import Workspace
from economic_regime_forecasting.configuration.run_settings import ARTIFACTS
from economic_regime_forecasting.models.model_loading import regime_model_from_dictionary

SHRINKAGE = 10.0


def _filtered(model: object, matrix: object) -> np.ndarray:
    """Filtered state probabilities, whichever model the artifact store holds.

    The default is the two-chain model since ADR 0010, and only the single-chain
    class is documented as exposing this. If a model cannot hand them back, say so
    with what it does expose rather than failing on an attribute name.
    """
    if hasattr(model, "filtered_state_probabilities"):
        return model.filtered_state_probabilities(matrix.values)  # type: ignore[attr-defined]
    raise SystemExit(
        "the selected model does not expose filtered_state_probabilities. It is a "
        f"{type(model).__name__} offering: "
        + ", ".join(sorted(n for n in dir(model) if not n.startswith("_")))
    )


def _weighted_rate(weights: np.ndarray, outcome: np.ndarray, pooled: float) -> np.ndarray:
    """One shrunk per-regime rate, the same estimator the pipeline uses."""
    totals = weights.sum(axis=0)
    successes = weights.T @ outcome
    return (successes + SHRINKAGE * pooled) / (totals + SHRINKAGE)


def _log_likelihood(probability: np.ndarray, outcome: np.ndarray) -> float:
    p = np.clip(probability, 1e-12, 1 - 1e-12)
    return float(np.sum(outcome * np.log(p) + (1 - outcome) * np.log(1 - p)))


def main() -> None:
    workspace = Workspace.open()
    today = date(2026, 9, 20)
    model = regime_model_from_dictionary(workspace.artifacts.read_json(ARTIFACTS.selected_model))
    matrix = workspace.observation_matrix_as_of(today)
    filtered = _filtered(model, matrix)
    index = matrix.dates

    histories = prepare_indicator_history(
        workspace.indicators,
        workspace.registry,
        workspace.cache,
        workspace.settings.forecast_horizons_in_months,
    )

    print(f"  regimes: {filtered.shape[1]}, months: {len(index)}\n")
    header = f"  {'indicator':<56} {'1st order':>11} {'2nd order':>11} {'dBIC':>9}  prefers"
    print(header)
    print("  " + "-" * (len(header) - 2))

    totals = {"first": 0.0, "second": 0.0, "n": 0}
    regimes = filtered.shape[1]
    for name, history in sorted(histories.items()):
        condition = history.monthly_condition.dropna()
        aligned = condition.reindex(index).dropna()
        if len(aligned) < 40:
            continue
        positions = index.get_indexer(aligned.index)
        weights_all = filtered[positions]
        values = aligned.to_numpy(dtype="float64")

        # First order: this month given last month, per regime.
        previous, current = values[:-1], values[1:]
        weights = weights_all[1:]
        held = previous >= 0.5
        entry = _weighted_rate(weights[~held], current[~held], float(current[~held].mean()))
        persist = (
            _weighted_rate(weights[held], current[held], float(current[held].mean()))
            if held.any()
            else np.full(regimes, float(current.mean()))
        )
        rate_first = np.where(held[:, None], persist[None, :], entry[None, :])

        # Second order: this month given the previous two, per regime.
        two_back, one_back, now = values[:-2], values[1:-1], values[2:]
        weights2 = weights_all[2:]
        rate_second = np.zeros((len(now), regimes))
        for a in (0.0, 1.0):
            for b in (0.0, 1.0):
                cell = (two_back == a) & (one_back == b)
                if not cell.any():
                    continue
                pooled = float(now[cell].mean())
                rate_second[cell] = _weighted_rate(weights2[cell], now[cell], pooled)[None, :]
        second = _log_likelihood((weights2 * rate_second).sum(axis=1), now)

        # Compare on the months both can score, so the counts match.
        first_on_common = _log_likelihood((weights2 * rate_first[1:]).sum(axis=1), now)
        extra_parameters = 2 * regimes
        delta_bic = -2 * (second - first_on_common) + extra_parameters * np.log(len(now))
        prefers = "second" if delta_bic < 0 else "first"
        totals["first"] += first_on_common
        totals["second"] += second
        totals["n"] += len(now)
        print(f"  {name:<56} {first_on_common:>11.1f} {second:>11.1f} {delta_bic:>9.1f}  {prefers}")

    extra = 2 * regimes * len(histories)
    overall = -2 * (totals["second"] - totals["first"]) + extra * np.log(totals["n"])
    print(f"\n  pooled log likelihood: first {totals['first']:.1f}, second {totals['second']:.1f}")
    print(f"  pooled dBIC (negative favours second order): {overall:.1f}")
    print(
        f"  -> the composition's first-order assumption is "
        f"{'NOT supported' if overall < 0 else 'supported'} by this comparison"
    )


if __name__ == "__main__":
    main()
