# Local storage and cleanup

New content-studio jobs and per-checkout Python environments use `SPRITEMOTION_WORK_ROOT`.
The Windows default is `D:/_agentShared/work/spritemotion`; other systems default to
`~/.cache/spritemotion`. Content jobs can independently override `SPRITEMOTION_CONTENT_HOME`.
See the [studio storage settings](../tools/uo-content/README.md#outputs-and-importing).

`python tools/worktree-venv/run.py --path` prints the environment for this checkout without creating it.
The directory key hashes the absolute checkout path, so two worktrees never reuse another checkout's
editable install. The paired launchers select this environment before legacy in-repo environments.
Creation still verifies that `spritemotion.__file__` belongs to the current checkout.

Evidence belongs in central runs, with receipts from the fleet evidence CLI. Product assets and
test fixtures keep their tracked locations. Existing authoring scenes, reviewed fit adjustments,
source repositories and unclassified private inputs must be retained; an ignored path is not proof
that its contents are disposable. Historical studio jobs remain in their old directory until reviewed.

Before retiring a worktree, inspect tracked changes, untracked files, ignored payloads and junctions.
Move evidence and generated payloads to their central homes first, preserving any unique inputs.
Use plain `git worktree remove`, `git branch -d` for merged branches, then `git worktree prune`.
Never force removal or follow workspace junctions. If permissions interrupt removal, preserve any
residual files and record the partial result before pruning stale registrations.

CLEANUP-01's baseline, follow-up inventory, retained-path list, regeneration recipes and per-operation
receipts live in the `20261018_spritemotion-cleanup_repo-bloat` central evidence run. The CEF Cargo
cache now uses shared work through its local Cargo config. Retired environments and interrupted
detached-checkout residuals are preserved in shared work with README files; they are not purgeable evidence.
