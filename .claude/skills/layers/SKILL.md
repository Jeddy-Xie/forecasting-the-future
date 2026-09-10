---
name: layers
description: Check that dependencies point one way only, against the layer table declared in the package docstring. Use before a refactor, when adding a module, and whenever an import feels like it is going the wrong way.
argument-hint: [--json]
---

Check the layering: **$ARGUMENTS**

```
python3 scripts/layer_check.py $ARGUMENTS
```

`src/economic_regime_forecasting/__init__.py` declares which layer may import
which. That table is the specification; this reads it and checks every import in
the package against it with `ast`. Exit 0 clean, 1 on a violation.

The docstring stays the single source of truth — change the declared layering and
the check follows. There is no second copy of the rules to drift.

## Reading a violation

Each one names `file:line` and what the table permits. Two things it can mean,
and they need different fixes:

- **The import is wrong.** Something reached across the architecture because it
  was convenient. Move the code, or invert the dependency.
- **The table is out of date.** A dependency is real, sensible, and simply was
  never written down. Then the fix is to amend the docstring — deliberately, in
  the commit that argues for it, not silently to turn the check green.

Deciding which is the defect is the whole job. Never edit the table just to make
this pass; that converts a specification into a description of whatever the code
happens to do, which is worth nothing.

Package-root modules the table does not name (`command_line_interface.py`,
`pipeline_gates.py`) are treated as orchestration and exempt — they are listed in
the output so the exemption is visible rather than assumed.
