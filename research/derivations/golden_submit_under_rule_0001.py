"""Golden check (delegated decision P2-2): the rule-driven submit, asked for rule 0001
on the artifacts that produced the committed 2026-09-29 submission, must write that
forecasts.csv byte for byte.

Run once, on 2026-09-29, before the command line's default rule became 0007:
"byte for byte: True 6672 6672". Its inputs are local and not reproducible from
the repository alone: the fec79a040f9ca6f9 artifacts in the cache of a detached
worktree pinned at e7755ef, and the submission committed at f6ad511. It is kept as
the record of what was checked, not as a test.
"""
import dataclasses, filecmp, subprocess, sys, tempfile
from datetime import date
from pathlib import Path
from economic_regime_forecasting import command_line_interface as cli
from economic_regime_forecasting.configuration.run_settings import DEFAULT_RUN_SETTINGS
from economic_regime_forecasting.data.cache import ArtifactStore

store = ArtifactStore(Path('/Users/jpmorgan/Projects/forecasting-the-future-arms/reference-e7755ef/.cache/models'))
base = cli.Workspace.open()
settings = dataclasses.replace(DEFAULT_RUN_SETTINGS, blend_the_model_equally_with_the_condition_chain=False)
assert settings.configuration_hash() == 'fec79a040f9ca6f9'
workspace = dataclasses.replace(base, artifacts=store, settings=settings)
committed = subprocess.run(['git','show','f6ad511:submission/forecasts.csv'], capture_output=True, check=True).stdout
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / 'golden'
    cli.submit(workspace, date(2026, 9, 29), destination=out, rule='0001')
    written = (out / 'forecasts.csv').read_bytes()
print('byte for byte:', written == committed, len(written), len(committed))
sys.exit(0 if written == committed else 1)
