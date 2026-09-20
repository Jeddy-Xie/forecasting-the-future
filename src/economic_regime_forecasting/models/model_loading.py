"""Read back a fitted regime model, whichever kind of model wrote it.

One function reads both kinds, so a caller that only wants "the model this run fitted" never
has to know which class wrote the file. It lives in its own module because it must import
both: the two-chain model already imports the single-chain one, so a dispatcher in either
would be a cycle, and a dispatcher inside the two-chain module hides the general path behind
one particular model's name.
"""

from __future__ import annotations

from typing import Any

from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
    HiddenMarkovModelError,
)
from economic_regime_forecasting.models.two_timescale_hidden_markov_model import (
    MODEL_CLASS,
    TwoTimescaleHiddenMarkovModel,
)


def regime_model_from_dictionary(payload: dict[str, Any]) -> GaussianHiddenMarkovModel:
    """Read back either kind of fitted model, by what the payload says it is."""
    model_class = payload.get("model_class")
    if model_class == MODEL_CLASS:
        return TwoTimescaleHiddenMarkovModel.from_dictionary(payload)
    if model_class is not None:
        raise HiddenMarkovModelError(
            f"unknown model_class {model_class!r} in a fitted-model payload. Delete the cached "
            "file and refit rather than guessing what it holds."
        )
    return GaussianHiddenMarkovModel.from_dictionary(payload)
