"""Run the command line interface with observe_the_unemployment_rate_and_the_term_spread off.

The arm's branch defaults the setting on; the registered check off_reproduces_main needs
the same code with it off. Workspace.open is the only place the CLI reads the default
settings, so its default is replaced and nothing else is touched.
"""

import dataclasses
import sys

import economic_regime_forecasting
from economic_regime_forecasting import command_line_interface as cli
from economic_regime_forecasting.configuration import run_settings

print(f"imported from {economic_regime_forecasting.__file__}", file=sys.stderr)
OFF = dataclasses.replace(
    run_settings.DEFAULT_RUN_SETTINGS, observe_the_unemployment_rate_and_the_term_spread=False
)
print(f"configuration hash with the setting off: {OFF.configuration_hash()}", file=sys.stderr)
_original_open = cli.Workspace.open.__func__  # type: ignore[attr-defined]
cli.Workspace.open = classmethod(lambda cls, settings=OFF: _original_open(cls, settings))  # type: ignore[method-assign,assignment]
sys.exit(cli.main(sys.argv[1:]))
