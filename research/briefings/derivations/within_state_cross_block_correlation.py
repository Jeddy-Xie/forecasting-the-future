#!/usr/bin/env python3
"""Does the two-chain model discard a dependence the data actually has?

The model gives growth its own chain and inflation-with-rates another, so within any
joint regime it assumes growth is uncorrelated with the other two. That assumption is
checkable on the same panel the model is fitted to.

For each joint regime this measures the occupancy-weighted correlation of the residuals
about that regime's own means, and compares the two the model DISCARDS (growth with
inflation, growth with rates) against the one it KEEPS (inflation with rates). A model
whose discarded dependence is comparable to its kept one is throwing away structure.

Method, and its limits, stated plainly: responsibilities are the filtered probabilities
on today's panel, where the fit itself uses smoothed joint posteriors. That makes this a
diagnostic of the fitted model, not a forecasting claim, and it is why the number belongs
in a briefing rather than in a gate.

    .venv/bin/python research/briefings/derivations/within_state_cross_block_correlation.py
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np

from economic_regime_forecasting.configuration.registry import load_registries
from economic_regime_forecasting.configuration.run_settings import ARTIFACTS, DEFAULT_RUN_SETTINGS
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel
from economic_regime_forecasting.features.observation_matrix import build_observation_matrix
from economic_regime_forecasting.models.model_loading import regime_model_from_dictionary

MINIMUM_OCCUPANCY_IN_MONTHS = 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default=None,
        help="the fitted-model store to measure; defaults to this configuration's own. "
        "Name it explicitly to measure a model that a different run fitted.",
    )
    arguments = parser.parse_args()
    settings = DEFAULT_RUN_SETTINGS
    registry, _ = load_registries()
    cache = SeriesCache(settings.cache.raw, settings.cache.vintage)
    artifacts = ArtifactStore(Path(arguments.models) if arguments.models else settings.cache.models)
    model = regime_model_from_dictionary(artifacts.read_json(ARTIFACTS.selected_model))
    matrix = build_observation_matrix(
        assemble_point_in_time_panel(registry, date.today(), cache), registry
    )
    values = matrix.values
    responsibilities = model.filtered_state_probabilities(values)
    print(f"model store : {artifacts.directory}")
    print(f"model       : {type(model).__name__}, {model.state_count} states")
    print(f"panel       : {values.shape[0]} months to {matrix.dates[-1].date()}")

    rows = []
    for state in range(int(model.state_count)):
        weights = responsibilities[:, state]
        occupancy = float(weights.sum())
        if occupancy < MINIMUM_OCCUPANCY_IN_MONTHS:
            continue
        deviations = values - model.means[state]
        covariance = (deviations * weights[:, None]).T @ deviations / occupancy
        spread = np.sqrt(np.diag(covariance))
        correlation = covariance / np.outer(spread, spread)
        rows.append((state, occupancy, correlation[0, 1], correlation[0, 2], correlation[1, 2]))

    print(f"\n{'state':>6}{'months':>9}{'growth~inflation':>19}{'growth~rates':>15}{'inflation~rates':>18}")
    for state, occupancy, gi, gr, ir in rows:
        print(f"{state:>6}{occupancy:>9.1f}{gi:>19.3f}{gr:>15.3f}{ir:>18.3f}")

    weights = np.array([occupancy for _, occupancy, _, _, _ in rows])
    discarded_inflation = np.average([abs(row[2]) for row in rows], weights=weights)
    discarded_rates = np.average([abs(row[3]) for row in rows], weights=weights)
    kept = np.average([abs(row[4]) for row in rows], weights=weights)
    print("\noccupancy-weighted mean absolute correlation:")
    print(f"  discarded by the model, growth with inflation : {discarded_inflation:.3f}")
    print(f"  discarded by the model, growth with rates     : {discarded_rates:.3f}")
    print(f"  kept by the model, inflation with rates       : {kept:.3f}")
    print(f"\ndiscarded as a fraction of kept: "
          f"{discarded_inflation / kept:.2f} and {discarded_rates / kept:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
