"""Forecast binary macroeconomic indicators from latent economic regimes.

The package is layered so that dependencies point one way only:

    configuration  ->  (nothing)
    data           ->  configuration
    features       ->  configuration
    models         ->  features, configuration
    backtest       ->  models, features, data, configuration
    evaluation     ->  (plain arrays; nothing above)
    reporting      ->  evaluation, models

Every module that touches the network or the filesystem lives in ``data``.
Everything else takes values and returns values, which is what makes it testable
without mocks.
"""

__version__ = "1.0.0"
