# Generated storage

Content builds, block rebuilds, client staging and checkout environment setup
check their external stores before allocating large outputs. Content builds
monitor the Blender child every 250 ms and terminate it on overflow. A failed
fresh build removes its regenerable derivatives and newly generated scene;
inputs and any pre-existing editable scene are preserved. Building over an
existing editable scene is refused: create a new job instead.

Settings resolve environment > launcher configuration > defaults:

| Setting | Default | Meaning |
|---|---|---|
| `SPRITEMOTION_MAX_WORK_GB` | `5` | Decimal GB per content/environment/Godot or explicit staging store |
| `SPRITEMOTION_OUTPUT_DAYS` | `7` | Minimum age before completed/failed derivatives expire |
| `SPRITEMOTION_KEEP_OUTPUT_JOBS` | `10` | Retain at least this many newest finished jobs |
| `SPRITEMOTION_WORK_ROOT` | Fleet shared work area; user cache off Windows | External work root |
| `SPRITEMOTION_CONTENT_HOME` | `<work-root>/content-studio` | Content job store |
| `SPRITEMOTION_BACKEND` | `<work-root>/inputs/canonical-model` | One canonical input installation shared by checkouts |

Positive limits are required. The byte cap counts preserved inputs and scenes
too; when these fill the store, new work is refused. Choose another external
store or explicitly manage inputs; retention never deletes them. Set
`SPRITEMOTION_BACKEND` to an existing external canonical installation when
migrating, or run pipeline `setup --source` once. No input migration is automatic.

Every content producer session expires only finished jobs that are BOTH older
than the age threshold AND outside the newest-job allowance. Only the fixed
derivative allowlist in `common/storage.py` is eligible. Inputs, job settings,
editable `.blend` files, staging/client payloads, unknown files and protected
fleet filenames never expire. Queued/building jobs, `.keep` jobs and pinned
rebuild sources are excluded. Protected/unknown contents abort the deletion
plan before any candidate is removed. Links are never traversed for deletion.

`python tools/storage/run.py check` reports current use; `prune` runs the same
retention policy immediately. Locks serialize builds and cleanup. After a
crash, verify the PID in `.storage.lock` or `.storage.pin` is no longer active
before removing that marker. There is no unattended timer or stale-lock bypass.

This is a producer guard, not an operating-system disk quota. A child can
overshoot during one write/poll interval. ZIPs and client copies reserve a
conservative size before allocation. Environment setup stops its subprocess
on overflow but retains the partial external environment for explicit rebuild.
Independent explicit stores have independent caps; this is not a fleet-wide
quota. Direct manual writes and historical scripts are outside the producer
guard. Review story stores and remove obsolete derivatives at story closure.

## Startup and historical checkouts

Run `launchers/dev/check-storage.bat` (`.sh` elsewhere) before resuming work.
For an old checkout use `--checkout PATH --python EXTERNAL_PYTHON`. Missing
guard code or launcher checks fail closed; update/rebase that checkout before
launching it. No script can retrofit protection into an untouched historical
checkout: the resume procedure must invoke this guard first.

Updated launchers reject output roots and interpreters inside any Git checkout,
verify the editable install maps to that exact checkout, and use the keyed
external environment. `--paths-only` supports first-time setup without an
existing environment. Legacy in-checkout venv fallback was removed. Godot
downloads now target `<work-root>/godot`; existing configured executables remain
usable. Download chunks and archive extraction check available store capacity.
Content-studio and pipeline CLI also validate direct startup.

Other explicit exporters must select external destinations; not every legacy
one-off Blender script has automatic age retention. Do not call an untouched
historical producer directly as a substitute for the guarded launchers.
