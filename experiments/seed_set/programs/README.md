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

**Providers.** `providers.json` binds both aliases to `claude_unrestricted_workspace_metered`, and
`judge.providers.json` binds the judge route (`score_functional.orc`'s `providers.judge`) to it as well; the
harness's shared `score.providers.json` keeps the plain template. The metered template prints stream-json, so the
runner prices every call's usage by the frozen price table and the runtime can take `--max-cost-usd` (coordinator
ruling R4, 2026-11-14): the unit's worst case times the table's highest tier over its ordinary rate for the model,
since the runtime counts every call at the highest tier (review 3 X3).

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
- A unit's copied credentials are removed when it ends normally, is refused or raises, and a pool's
  `<pool>/.private-homes` copies when pooling ends. A launcher killed with SIGKILL, or a host reboot, runs no
  clean-up: its copies stay on disk until the next study command, which starts by removing every copy no live unit
  holds and prints each path (review 3 X5). The agent under test can read its unit's copy during its call; a copy it
  makes under another name, or text it writes into its output or patch, is not removed. The route is the owner's
  decision (coordinator ruling R7).
- A unit's whole process tree, its provider calls' own sessions and sandboxes included, dies with its launcher
  however the launcher ends (`../reaper.py`). The unit's command runs as the guard's child from its first instant;
  the guard is a child subreaper, so what a root shell that died leaves behind is killed when the command ends; a
  kill reaches a pid only while its start time matches the scan that listed it, so a reused pid is never
  signalled. Killing the guard itself is an operator act: the launcher then kills the unit's session tree in its
  place, and what the guard had adopted is lost. Only one study command that starts, prepares or settles units runs
  at a time on a study (`study.lock` beside the ledger).
- The host-side checks of candidate code (`settle`'s visible check, the probe's hidden check, `summarize`'s hidden
  tests) run under the same guard, with a bound: 600 s for a patch's hidden set (five times the plan's 120 s for a
  hidden run on the oracle), 1,200 s for the visible check (dev-check.json's 600 s plus 600 s), 600 s per clone for a
  pool's summary. A check past its bound is recorded as timed out, never as a pass or a failure: the visible
  figure counts it apart (the readout's "visible check past its bound"), a probe run whose hidden check timed out is
  an incident (relaunched once), and a summary that times out makes its pool an incident. `summarize.py` gives
  each hidden test 1,800 s and counts a hanging one as failing, so a candidate whose code makes a hidden test hang
  now costs its pool once the per-clone bound passes.
- A runner that dies between launch and settle leaves the agents' tree on disk until `settle` (a calibration
  run) or the next `probe` (a probe run) settles it (review2 minor 9); `settle` refuses while the unit's session
  still runs.
- A runner killed between a unit's reservation and its launch leaves a reserved unit that made no call: `settle`
  files it as an incident ("expected one orchestrator run, found 0"), counted by the 10% stop, and prices it at
  USD 0; its slot is not run again (review 3 minor 11).
- A slot cut by a usage limit runs again once from the same cap (coordinator ruling R1, 2026-11-14), so only where
  the cap has room: the smoke's caps, the calibration's Sonnet candidates and both judges' calibration caps are
  fully planned, so a cut there is not run again (the smoke never runs a cut slot again and its check fails; a
  cut judge pool is rebuilt, its judges find no room, and the pool ends as an incident). A re-run beyond the
  room is left out with a message, not refused; a pool whose judges the caps cannot both hold gets no judge.
- A call is recognised as a possible usage limit in any shape that may be one (an error result with status 429,
  an error result beside a rejected rate-limit event, a provider error line in a limit wording that no other named
  status explains); a shape other than the recorded one is flagged "unrecognised limit shape", and the operator
  reads the raw result the refusal names before `resume-after-limit` (review 3 X2). The wording rule, and the
  provider-error rule of incidents, read only a call that did not succeed (an error result, or no result event at
  all): a warning on stderr beside a call that succeeded is neither, and a stream line cut mid-write (a line that
  starts with `{` and is not JSON) is never read. The pause and every refusal it causes name the rule that fired
  and the line it read; an older CLI's `Claude AI usage limit reached|<epoch>` gives its reset.
- When the raw result shows no usage limit, `study.py not-a-limit UNIT --reason R` records the operator's decision
  and reason in the ledger while the pause is open: the settled unit is no longer `cut` but what the rules make it
  (the incident its cut set aside, an incident when it failed with a provider error, else its outcome), its pause
  stops closing starts, and nothing runs again. A unit not yet settled refuses; a probe run is settled only by
  `probe`, which refuses while starts are closed, so for it the way is `resume-after-limit` (where no pause named a
  reset, a typed reset after the hit is accepted).

**Check-withheld runs.** For a package with `withheld/`, the runner copies those test files into the run's records
directory (outside the agents' tree and the sandbox) and names the copy in `SEED_SET_WITHHELD` for the launch;
`dev_check.py`, a host-side command boundary, inherits it, places the files for each check and removes them. The
sandbox clears its environment, so an agent never sees the path. No program gives a command step a timeout (a
test holds that none is below dev-check.json's 600 s), since the orchestrator SIGKILLs a timed-out step and would
leave the test files in the tree.
