# Core package: what ships in `pip install spritemotion`

The package (`common/`, imports as `spritemotion`) depends on the standard library only. Numpy and Pillow are the
`imaging` extra. GUO and other consumers install it and call the same code the Fit Lab uses.

| Step | What it added |
|---|---|
| 1 | JSON schemas as package data (`spritemotion.schemas`, `version()`, `path()`, `load_file()`), `imaging` extra |
| 2 | Transfer artifact schema and reader (`spritemotion.transfer`), see [transfer-artifact.md](transfer-artifact.md) |
| 3 | Fit rules: `spritemotion.fit_rules` (Python) and `common/web/fit-rules.mjs` (JavaScript), below |

## Step 3: fit rules

`spritemotion.fit_rules.resolve(document, mapping, item, action, direction)` returns the fit (offset, rotate, scale,
depth scale, bind, body hiding, occlusion, side offsets) for one item, one action and one facing from a saved
`lab-adjustments.json`. `fit-rules.mjs` is the same rule set for the browser (`resolveFit`); a parity test
(`tests/unit/test_fit_rules.py`) runs both on the same cases. The `.mjs` ships as package data at
`spritemotion/web/fit-rules.mjs`.

One source each, no copies:

- The Fit Lab server answers `/fit-rules.mjs` (the URL `lab.js` imports) from `common/web/fit-rules.mjs`.
- `tools/fit-lab/fit_rules.py` is a shim that loads `common/fit_rules.py` by path. Blender's Python has no installed
  `spritemotion`, and `tools/uo-content/fit_runtime.py` and `rebuild.py` keep importing `fit_rules` from `tools/fit-lab`.
- `pipeline.py render_fingerprint()` hashes `common/fit_rules.py`, so a rule change still invalidates partial rebuilds.

The rules did not change in this step.
