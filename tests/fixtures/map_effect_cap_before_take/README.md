A run root written before `list/take`, `list/all` and `list/any` were operators. **Never regenerate it**: it exists
to prove that a run recorded under the old compiler still resumes to the same outcome.

Recorded on 2026-11-14 with the package at `9bb55dda` (a `git archive` export), in a scratch workspace with a
scratch `HOME`, by `python -m orchestrator run main.orc --command-boundaries-file commands.json`; no provider. The
command is the executable `./step.py` (a path, so no interpreter is pinned) and `run.json` names no path of the
machine that recorded it. The source is `PRE_TAKE_SOURCE` of `tests/test_workflow_evaluated_loops.py`, which the
test writes as `main.orc` (it is not kept here as a `.orc` file, so the compile of every tracked `.orc` is unchanged
by this fixture). It maps nine items under `:max 8`: the run committed items 1 to 8 and ended
`list_map_effect_cap_exceeded`.

`runs/<run id>/` is copied to `.orchestrate/runs/`; the lock, the build cache and the call log are not kept.
`tests/test_workflow_evaluated_loops.py` resumes it.
