# Seed-set programs

The four workflow programs of the [seed-set calibration plan](../../../docs/plans/2026-11-11-seed-set-calibration-plan.md)
(Step 1, "1c. Programs"). Each is one `.orc` file at target 2.39 with the entry
`run ((task String) (intent String) (repo String) (model String) (effort String)) -> Outcome`;
`common.orc` holds the shared types. All four use the same implementer prompt,
so they differ in structure only. Every provider call has `:timeout-sec 1200`.

| Program | Lines | Max provider calls | Different from `direct` |
| --- | --- | --- | --- |
| `direct.orc` | 22 | 1 | Nothing: the reference. |
| `retry_until_check.orc` | 31 | 3 | When the visible check fails, it resets the clone and makes a fresh attempt. |
| `implement_check_repair.orc` | 40 | 3 | When the visible check fails, the next call repairs the same tree and sees the check output. |
| `implement_review_revise.orc` | 45 | 3 | A review call follows, and a revision call when the review requests changes. |

**Model and effort** are workflow inputs, not program text. `arms.json` binds
them per arm (`claude-haiku-5-5`, `medium`; the calibration arm `direct_sonnet`
is `direct.orc` with `claude-sonnet-5-5`) together with the source, entry and
maximum calls; the runner passes them in `inputs.json` (`--set model=...
--set effort=...` through `prepare.run_arm`).

**Boundaries.** `dev_check.py` (the visible check, a copy of the structural
search catalog's) and `reset_clone.py` (hard reset to the harness's
`compare seed` commit, then `git clean -fd`) run in the clone, the working
directory. The runner copies both into the clone and lists them in
`.git/info/exclude`, as `experiments/orc_structural_search/evaluation.py` does
for `dev_check.py`; being ignored, they and `.orchestrate/` survive a reset.

**Evidence.** `tests/experiments/test_seed_set_programs.py` compiles each
program and runs it through the public CLI with a scripted `claude` and the
real boundaries: result values, call counts on the pass and fail paths, the
distinctive step, the bound, the bound model and effort on every call, and a
resume after the orchestrator is killed inside a call.
