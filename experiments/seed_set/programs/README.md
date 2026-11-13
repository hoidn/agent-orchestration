# Seed-set programs

The four workflow programs of the [seed-set calibration plan](../../../docs/plans/2026-11-11-seed-set-calibration-plan.md)
(Step 1, "1c. Programs"). Each is one `.orc` file at target 2.40 with the entry
`run ((task String) (intent String) (repo String) (model String) (effort String)) -> Outcome`;
`common.orc` holds the shared types. All four use the same implementer prompt,
so they differ in structure only. Every provider call has `:timeout-sec 1200`.

| Program | Lines | Max provider calls | Different from `direct` |
| --- | --- | --- | --- |
| `direct.orc` | 22 | 1 | Nothing: the reference. |
| `retry_until_check.orc` | 31 | 3 | When the visible check fails, it resets the clone and makes a fresh attempt. |
| `implement_check_repair.orc` | 40 | 3 | When the visible check fails, the next call repairs the same tree and sees the check output. |
| `implement_review_revise.orc` | 45 | 3 | A review call follows, and a revision call when the review requests changes. |

**Size limit** (owner, 2026-11-11): every program an arm runs has fewer than 50 physical lines, every line
counted (code, comments, blank lines); `selection.MAX_PROGRAM_LINES` holds the limit, a test and the selection
rule enforce it. `common.orc` is not counted but may define only the shared `Change`, `CheckReport` and `Outcome`.

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

**Runner limits** (`../study.py`, `../units.py`). After each candidate run and judgment the runner audits the
unit's whole private home: every session-shaped `.jsonl` must sit under the unit's own project directory, there
may be no more top-level sessions than physical calls, and any model outside the binding stops the study. It
cannot see a session written inside the unit's tree or its `/tmp` (indistinguishable from the repository's own
test fixtures), a session kept only in memory (`/dev/shm`, `--no-session-persistence`), or a direct API request
made with the sandbox's copied credential; the model pin and `COMPARE_MAX_CALLS` remain the bound there.

**Known limits** (coordinator rulings, 2026-11-12; recorded, not changed; the readout states each, `readout.LIMITS`):

- A candidate can reach the network: the comparison harness's sandbox does not unshare it, so an agent could fetch
  the fix if the repository is public (unverified); the contamination scan matches the fix's commit hash in a run's
  transcripts and patches, not the fix's content.
- The visible check runs the candidate's code on the host, outside the sandbox, so that code could read the
  runtime checkout (the hidden tests among it); the scan of patches and transcripts for hidden names is the control.
- The per-run time limit does not include time spent in checks; a run cut short is a natural failure and is never
  pooled.
- A candidate patch that legitimately adds a token of the arm-identity scan costs its whole task: the pool is
  refused, not scrubbed.
- The check-withheld check on the study's own path was rehearsed only through a single run on a separate ledger,
  and no planned calibration arm runs it.
- G2 and G3 average over the tasks where both arms have a score, and V4 over the rated candidates; a run that
  failed or was never pooled is not among the plan's 100 natural candidates (review2 minor 3).
- A check-withheld run whose patch creates or edits the withheld test's path fails the host visible check (its patch
  does not apply to the in-tree view); this touches the visible-check figures only (review2 minor 10).
- A T5 choice is always a stop: T4 and T5 hold 11 tasks together (review2 minor 12).
- T2: short commit message plus the names of the files to change. A recorded deviation from the plan
  (coordinator ruling on review2 M8): with the message alone every T2 statement falls under the 80-character
  floor and the rung disappears. T2 differs from T1 by the commits selected (up to two files and 60 lines,
  against one file and 20), not by the form of the statement; the probe measures the difference.
- A unit's copied credentials are removed when it ends in any way (settled, refused, failed, or after its judge's
  launch), and a pool's `<pool>/.private-homes` copies are removed when pooling ends, refused or not; no command
  leaves a credential under a results or pool directory (coordinator ruling, round 4).
- A runner that dies between launch and settle leaves the agents' tree on disk until `settle` (a calibration
  run) or the next `probe` (a probe run) settles it (review2 minor 9).

**Check-withheld runs.** For a package with `withheld/`, the runner copies those test files into the run's records
directory (outside the agents' tree and the sandbox) and names the copy in `SEED_SET_WITHHELD` for the launch;
`dev_check.py`, a host-side command boundary, inherits it, places the files for each check and removes them. The
sandbox clears its environment, so an agent never sees the path. No program gives a command step a timeout (a
test holds that none is below dev-check.json's 600 s), since the orchestrator SIGKILLs a timed-out step and would
leave the test files in the tree.
