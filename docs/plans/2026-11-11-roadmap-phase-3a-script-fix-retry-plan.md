# Roadmap Phase 3a: Retry A Failed Step After Its Script Is Fixed

**Status: Plan, accepted 2026-11-11; implemented (T1–T3).** Implements part 3a of
[roadmap Phase 3](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-3-edit-and-continue)
under rulings 1 and 3 of the
[feasibility spike](../design/workflow_lisp_edit_and_continue_spike.md#coordinator-rulings-2026-11-11).
This page owns the order of work, the tests and the gates. Behavior is owned
by [evaluated execution](../design/workflow_lisp_evaluated_execution.md)
(§7.1, §7.3 C4, §8.1, §8.5), [specs/cli.md](../../specs/cli.md) and
[specs/state.md](../../specs/state.md); until a task lands they describe
what the tool does, and nothing here is copy-safe guidance. No provider call
is made or authorized. Planned against `fix/phase1-leftovers` (`1f7a69c6`),
which merges first: its `after_started` callback (`attempts.py`,
`runtime.py`) and its `cli/recovery.py` are the starting state.

**Goal:** a command step that failed can be retried in the same run after
its author fixes its script; a step that wrote its own script, or was killed,
is still not retried with changed files unless the author says so.

**Headline exit test:** a four-step pipeline whose third step fails; fix its
script; plain `resume` runs steps three and four only
([T2](#t2-the-retry-rule-the-flag-and-the-recovery-lines-m)).

**Approach:** when a host command's attempt fails, rehash its declared files
and write `closure: unchanged|changed` on its `failed` record; the retry
check admits changed files after `unchanged`, or under
`resume --accept-changes`. New logic goes in `attempts.py` (62 lines);
`runtime.py` and `effect_inputs.py` get calls and arguments only.

## Global constraints

- Tests first: see each new test fail for the stated reason, implement, see
  it pass, run the controls, commit by pathspec, no assistant attribution.
- Tests drive the public command line with stand-in scripts: no mocks, no
  provider call, no assertion on prompt text. Assert exit codes, the stable
  first line, journal rows, which steps started and that a printed command
  works; not whole recovery sentences.
- Modules at most 500 lines, functions at most complexity 12. `runtime.py`
  (580), `effect_inputs.py` (594), `main.py`, `execute_pure_resume` (18) and
  `finish_effect` (14) are over already: no branch is added to them, and T2
  moves `_retry_baseline` out of `effect_inputs.py`.
- Contract text lands in the commit of the code that makes it true
  ([table](#contract-edits)).
- Narrow selectors, then `pytest -q -n 16 --dist=worksteal --sample 10`; the
  full suite before merging, in tmux, against the
  [test baseline](../reports/2026-11-11-test-baseline.md).

Sizes: **S** up to one day, **M** two to four days.

## State of the code, verified 2026-11-11

Probes ran a copy of the branch outside the repository, unmodified and with a
prototype of this plan (about 55 new production lines); none calls a model.
Scripts and the diff are in the session scratch directory
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/plan3a-probe/`
(`probe*.py`, `prototype-3a.patch`), which is not durable.

| Claim | Check |
| --- | --- |
| After a failed third step's own script is fixed, `resume` refuses `effect_input_diverged` ("retry implementation files changed") and advises restoring the file or a new run | Probe |
| A dispatched attempt's `failed` row is written in one place, `_fail_started_effect`, called from `finish_effect` on the serial and the parallel path. `finish_effect` rehashes only after a valid result. The other `failed` writers (`allocate_attempt`, agent-turn recovery, confined recovery) are not a host command that ran | Read |
| The retry check `_check_retry_implementation` runs at resume preflight and again at the retry's start, both through `_resolve_command_input`, which receives `authority`; only `prepare_effect` passes the memo snapshot | Read |
| Memo rows reject unknown keys. The unmodified build on a journal with `closure`: `resume`, `invalidate` and `report` all answer `memo_inconsistent` | Probe |
| A command with `closure: []` whose script does not exist yet starts with empty evidence; creating the script after the failure refuses today | Probe |
| `must_not_repeat`, failed, script edited: today `effect_input_diverged`, because the file comparison precedes the repeat check | Probe |
| One script shared by three steps, the third fails, the script is edited: `resume` refuses at the first committed step; after `invalidate` of it, `resume` runs the committed steps again and then refuses at the third | Probe |
| A failed parallel-map item's `failed` row is followed by its siblings' starts and commits; a killed map leaves one pending start per item in flight | Probe |
| A pending start retired by an `invalidated` range is neither "pending" nor "failed" for `memo._uncommitted_state`, yet keeps its retry baseline | Probe |
| With the prototype, 779 of 781 tests in 25 modules pass (kill, recovery, invalidate, parallel, memo, closure, resume, CLI output); the two failures are the ones T2 changes | Ran |

**Cost of the rehash.** It is the precommit rehash's call
(`resolve_command_evidence` with the start's evidence as `prior`): one
`lstat` per stable-command token and one SHA-256 pass over each declared
file. Measured: 0.4 ms for one script, 96 ms for a declared directory of 812
files (19 MB). A failed attempt pays once what a successful one already pays.

## The rule

"Changed" means the declared files resolved at resume differ from the latest
uncommitted attempt's `started` evidence. Host `command` effects only.

| Latest attempt of the reached command | Plain `resume` | `resume --accept-changes` |
| --- | --- | --- |
| `failed`, `closure: unchanged`, files changed since | Retries with the current bytes; the new `started` row holds the new evidence and is the next baseline | Refused as not needed, unless another attempt needs it |
| `failed`, `closure: changed` (it wrote, removed or made unreadable a declared file) | Refuses `effect_input_diverged`, as today | Retries with the current bytes |
| Interrupted: `started` with no `failed` (kill, crash, Ctrl-C) | Refuses, as today | Retries |
| `failed` without the field (journal written before this change; allocation failure) | Refuses, exactly as today | Retries ([decision 2](#decisions-for-the-coordinator)) |
| Any of the above, files restored to the `started` bytes | Retries, as today | Retries |
| `must_not_repeat` | Refuses `lexical_restore_pending_effect_unsafe` whatever the field says; after a clean failure and an edit this replaces today's `effect_input_diverged` | Same refusal |
| A declared file missing or unreadable at resume; a changed launch directory | Refuses `effect_input_diverged`, as today | Same refusal |
| A committed step binds the changed file | Refuses at that step, as today (3b); `invalidate` then `resume` now completes | Not covered; needed after the `invalidate` only if the unfinished step is not proven clean |
| Provider, agent turn, run reference, host request | No closure: never rehashed, no field, retry rules unchanged (a failed provider already retries with an edited prompt file) | Not covered |
| Command in a confined run-reference child | No field, today's rule; the flag is not passed to children | Not covered |
| Parallel-map item | The same rule per item; a failed item retries alone | Accepts every interrupted item the resume reaches |

**The rehash** happens in `finish_effect`'s failure branch, immediately
before `_fail_started_effect`, for class `command` outside a confined child.
It also runs for a command whose `started` evidence is empty (selection only,
no file read), so "the script did not exist yet" is retried once the author
creates it. A rehash that cannot complete (`ClosureEvidenceError`, `OSError`)
records `changed`; the attempt's own code and `exit_info` are never replaced.
Ctrl-C and a kill write no `failed` row and stay on the refusing side.

**The flag** admits, for this invocation, the changed files of uncommitted
command attempts that no `closure: unchanged` record covers. It writes
nothing of its own: the retry's `started` row carries the new evidence, and
acceptance by flag can be read from the journal (the evidence differs and
the previous attempt has no `unchanged` record). It prints nothing of its
own: every retry that runs with changed files, automatic or accepted, adds
` changed_files=<names>` to its `[effect_rerun]` line. With nothing to cover
it is **refused**: exit 2, `[resume_preflight_failed]`, after memo replay
and before any write. Coverage is computed from the retry baseline, not from
"pending or failed": a killed step whose start an invalidation retired still
needs the flag (probed; the first prototype left it with no route).

## T1: record whether a failed command left its files unchanged (S)

**Files:** `orchestrator/workflow/evaluated/attempts.py`
(`closure_after_failure(attempt)`: `"unchanged"`, `"changed"` or `None`);
`runtime.py` (one argument at the `_fail_started_effect` call; the row gains
the key when not `None`); `memo_reducer.py` (`failed`: optional `closure`,
one of the two values, on a command site only); create
`tests/test_workflow_evaluated_script_fix_retry.py` with a four-step,
four-script fixture. The retry rule does not change in this task.

- [x] `test_failed_command_records_its_files_unchanged`: step three exits 3;
      the journal's one `failed` row has `closure == "unchanged"`.
- [x] `test_failed_command_that_wrote_its_script_records_changed`.
- [x] `test_failed_command_that_removed_a_declared_file_records_changed`:
      also `code == "command_exit_nonzero"` and run exit 1.
- [x] `test_command_without_start_evidence_records_unchanged`: `closure: []`,
      script absent, `started.implementation_files == {}`.
- [x] `test_failed_provider_row_has_no_closure_field` (stand-in provider
      that exits non-zero).
- [x] `test_misplaced_or_unknown_closure_value_is_memo_inconsistent`: edit
      the journal on disk (value `maybe`; the key on a provider's row);
      `resume` exits 2 and `report` exits 1 with `memo_inconsistent`.
- [x] Controls: `tests/test_workflow_evaluated_{memo,attempts,command_lifecycle,views,recovery_views}.py`,
      `tests/test_cli_run_output.py`.

## T2: the retry rule, the flag and the recovery lines (M)

One commit, so printed advice never names a flag that does not exist.
**Files:** `attempts.py` (receives `_retry_baseline`, moved unchanged; adds
`retry_change_admitted`, `unproven_command_retries`, `changed_files_note`);
`effect_inputs.py` (passes the snapshot to `_resolve_command_input` and
`_check_retry_implementation`; re-imports `_retry_baseline`);
`resume_prefix.py` (`_replay_resume_prefix` raises the not-needed refusal);
`runtime.py` (the rerun note's extra argument); `authority.py`
(`RunAuthority.accept_changes`, default false, not compared, set with
`replace` like `observer`); `cli/main.py` and
`cli/commands/{resume,evaluated}.py` (the flag); `cli/recovery.py` (the
unfinished-step branch of `_effect_diverged` becomes its own function).

Installed command line, in `tests/test_first_hour_e2e.py`:

- [x] `test_fixed_script_resumes_the_failed_step_and_the_one_after`: third
      step exits 3; rewrite its script; run the printed `resume` line. Exit
      0; the steps started are exactly three (attempt 2) and four; steps one
      and two were dispatched once; the rerun line names the script.
- [x] `test_step_that_wrote_its_own_script_refuses_until_accepted`: exit 2,
      first line `[effect_input_diverged]`, run tree bytes unchanged, nothing
      dispatched; the printed command ending `--accept-changes` exits 0 and
      starts steps three and four only.
- [x] `test_killed_step_with_an_edited_script_refuses_until_accepted`: kill
      the process group while step three sleeps; then as above.

In `tests/test_workflow_evaluated_script_fix_retry.py`:

- [x] `test_journal_without_the_field_refuses_until_accepted` (strip the key
      from the journal, fix the script).
- [x] `test_must_not_repeat_refuses_after_a_fix_with_and_without_the_flag`.
- [x] `test_missing_declared_file_refuses_with_and_without_the_flag`; no
      printed command contains the flag.
- [x] `test_accept_changes_with_nothing_to_accept_is_refused`, over a
      completed run, a clean failure with a fixed script, and a run whose
      only unfinished attempt is a provider's: exit 2,
      `[resume_preflight_failed]`, tree bytes unchanged; plain `resume` then
      succeeds.
- [x] `test_failed_parallel_item_retries_alone_with_its_fixed_script` (three
      items, each with its own script in its item directory) and
      `test_killed_parallel_items_refuse_until_accepted` (one accepted
      resume retries both).
- [x] `test_shared_script_fix_recovers_through_printed_invalidate_and_resume`,
      over a failed and a killed third step: the refusal at the committed
      step prints `invalidate` and `resume` (with the flag for the killed
      case); running them exits 0. It replaces
      `test_a_script_fix_after_a_failure_prints_a_fresh_run_and_never_invalidate`
      (`tests/test_cli_recovery_messages.py`), which would still pass but
      pins "resume would still refuse", false after this task.

Existing tests that pin the old refusal:

- `test_failed_step_script_edit_refusal_names_the_file_and_a_run_command_that_works`
  (`tests/test_cli_recovery_messages.py`) becomes
  `test_failed_step_script_edit_resumes_with_the_edited_script`: exit 0, the
  result line, step one at attempt 2.
- `test_resume_preflights_failed_attempt_baseline_before_tail_repair`
  (`tests/test_workflow_evaluated_resume_replay.py`) keeps its name and
  assertions (refusal before tail repair, restore, one retry); its probe
  script appends to itself in attempt 1, so the row says `changed`. Tried:
  it passes with the prototype.

Recovery lines (`specs/cli.md` owns the rows): for an unfinished step with
changed files, say whether it was interrupted, changed its own files or has
no record; then the `resume --accept-changes` command, then
restore-and-`resume`, then a new run. For a committed step whose change an
unfinished step shares: `invalidate` then `resume`, with the flag when that
step is not proven clean. A missing file keeps today's text.

Must pass unchanged: `tests/test_workflow_evaluated_{resume_kills,recovery,recovery_branches,resume_retry,invalidate,invalidate_durability,invalidate_smoke,invalidate_windows,parallel,parallel_resume,parallel_failures,parallel_e1_faults,parallel_cwd_cli,closure,closure_evidence,resume}.py`,
`tests/test_resume_command.py`, and the other tests of
`tests/test_cli_recovery_messages.py`.

## T3: guides and closeout (S)

- [x] `docs/tutorial_first_pipeline.md`, "Two limits": replace the first
      bullet (a script fix after a failure resumes; a killed step needs the
      flag). `test_tutorial_blocks_run_as_written` still passes.
- [x] `docs/runtime_execution_lifecycle.md`: "Edit a prompt and continue"
      gains the command-script case; "Resume" step 6 names the flag.
- [x] The spike page's status, the roadmap's known-limits row and current
      state, and this plan's row in `docs/index.md`.
- [ ] Gates: the T1 and T2 selectors, the sample, then the full suite. The
      installed tests of T2 are the end-to-end check.

## Contract edits

| Document, section | Edit | Task |
| --- | --- | --- |
| Design §7.1, `failed` row | Adds: for a host command, `closure`, whether its declared files were unchanged when it failed | T1 |
| Design §7.3 C4 | The first new sentence of the spike's text ("Rehash also when a started attempt fails…") | T1 |
| `specs/state.md`, "Memo records" | `failed`: optional `closure`; the reducer rule; an earlier build cannot read a journal that has the field | T1 |
| `specs/versioning.md`, evaluated execution | Profile and schema unchanged. Journals are read forward only: an earlier build answers `memo_inconsistent` once a host command has failed under this one; journals without the field reduce as before | T1 |
| Design §7.3 C4, §8.1, §8.5 | The spike's "After" text with the flag named; §8.1 also states the not-needed refusal and that a rehash that cannot complete counts as `changed` | T2 |
| Design §17, "Retry after a closure change" | Adds the author-edit, flag and parallel cases with their tests | T2 |
| `specs/cli.md`: synopsis; preflight step 10; the three `effect_input_diverged` recovery rows; `effect_rerun`; `resume_preflight_failed` | The flag; the rule and the not-needed refusal; the new advice; `changed_files=`; the new raiser | T2 |

## What this makes harder

- An earlier build cannot read a run in which a command failed under this
  one, and the header does not say so: it reports `memo_inconsistent`.
- A `failed` row now carries a judgment made after the attempt ended; every
  future writer of `failed` for a command must decide what it records.
- Plain `resume` after a failure runs whatever is on disk. An author who
  wanted to look first gets a retry; the old bytes survive only as digests.
- In a parallel map, a sibling still running can write a failed item's
  script after its `unchanged` record. C4 never covered other effects; the
  old refusal caught this by accident.
- One flag will mean three things after 3b, and "not needed" must then be
  defined for all three.
- `RunAuthority` carries a third per-invocation field.

Left out: an edited program and a committed step's changed file under the
flag (3b); confined children; a closure record for allocation failures;
`closure` in `report` or the dashboard; a Python-surface resume.

## Decisions for the coordinator

1. **The flag with nothing to accept.** Recommended: refuse. A flag that
   always succeeds becomes a habit and switches the protection off; the
   refusal costs one rerun without it. Alternative: proceed and print a note.
2. **What the flag covers.** Recommended: every uncommitted host command
   attempt not proven clean (interrupted, `closure: changed`, a `failed` row
   without the field). Ruling 3 names only the interrupted attempt; read
   literally, a step that wrote its own script, and a run in flight across
   the upgrade, keep "restore the file" as the only route.
3. **Versioning.** Recommended: no schema bump. A bump makes earlier builds
   refuse every new run, not only one with a failed command, for a clearer
   message.
4. **Commands with empty start evidence.** Recommended: rehash them too. The
   brief says the rehash must not run without a declared closure; taken
   literally, "the script did not exist yet" keeps refusing, and the call
   reads no file in that case.
5. **A rehash that cannot complete.** Recommended: `changed`, as the
   precommit rehash treats it. Alternative: omit the field.
6. **The shared-script advice.** Recommended: fix it in T2 (one branch, one
   spec row, one replaced test). Left alone, it states something this plan
   makes false.
7. **Parallel-map items.** Recommended: the same rule. Alternative: require
   the flag when a sibling's record follows the failure.
8. **What a retry with changed files prints.** Recommended: extend the
   `[effect_rerun]` line. Alternative: a new diagnostic code.
9. **Smaller choices taken above:** the flag travels on `RunAuthority`;
   `must_not_repeat` after a clean failure reports its own code; the
   tutorial gets a sentence, not a new executed section.

## Not verified

- Only `command_exit_nonzero` and Ctrl-C were probed; that contract,
  projection, origin and `command_closure_written` failures reach the same
  call was read.
- Confined children, and the flag beside a pending agent turn or phased
  provider, were read, not run.
- The prototype did not change `cli/recovery.py`: the new advice is designed
  from the probes, and its complexity after the split is not measured.
- A sibling writing a failed item's script after its record is reasoned.
- The full suite and the broad sample were not run against the prototype;
  the 25 modules above were. Rehash timings are from one machine.
- Line counts and call sites are those of `1f7a69c6` and may move when the
  branch merges.

## Ledger

| Date | Decision or event | Detail | Spend |
| --- | --- | --- | --- |
| 2026-11-11 | Plan accepted by the coordinator | Implementation starts after `fix/phase1-leftovers` and Phase 2 lane 1 (A2, A3) are merged, since the plan is written against the first and uses the second as its regression baseline | none |
| 2026-11-11 | Rulings, decisions 1, 3, 4, 5, 6, 8, 9 | As recommended: the flag with nothing to accept is refused and writes nothing; no schema bump, journals are read forward only and `specs/versioning.md` says so; the rehash also runs with empty evidence; a rehash that cannot complete records `changed`; the shared-script advice is corrected in T2; a retry under changed files adds `changed_files=` to the `[effect_rerun]` line; the flag travels in `RunAuthority` | none |
| 2026-11-11 | Ruling, decision 2 | The flag covers every uncommitted command attempt not proven clean: interrupted, `closure: changed`, and a `failed` record without the field. This widens ruling 3 of the spike, whose literal reading left restoring the file as the only route in two cases. If wrong: a step that rewrote its own script can be retried by an author who did not read the refusal | none |
| 2026-11-11 | Ruling, decision 7 | Conservative, against the recommendation: inside a parallel map a changed script is not accepted automatically when a sibling could have written it after the failure; the retry then needs `--accept-changes`. The implementer takes the simpler of two forms (a sibling record follows the failure record, or any item of a parallel map) and records which. Reason: that a sibling cannot write the script after the `unchanged` record is reasoning, not a probe. If wrong: one more flag for parallel authors; relax with evidence | none |
| 2026-11-12 | Implementation, decision 7 form | Any item of a parallel map: an identity with a `par-map:` segment is never proven clean, so its changed files need the flag and the flag is "needed" for it. Chosen over "a sibling record follows the failure": that form is timing-dependent within a map (flaky to test), and, read as "any later start", it would also refuse the serial shared-script case after `invalidate`, where the plan requires plain `resume` to complete. Test: `test_failed_parallel_item_retries_alone_with_its_fixed_script` | none |
| 2026-11-12 | Implementation note | A rehash at failure that raises anything records `changed` (not only `ClosureEvidenceError`/`OSError`), so an unexpected error can never drop the `failed` row. The unfinished-step refusal for a missing or unreadable file keeps its text minus the clause "cannot yet be retried with changed files in the same run", which this plan makes false | none |
| 2026-11-12 | Review fix F1 (major): live processes of a failed attempt | The review reproduced a detached child that rewrote the script after the rehash while the row said `unchanged`. Ruling: `unchanged` also requires that no process of the attempt is alive. Mechanism: before the rehash, scan `/proc` for a same-user process whose environment carries the attempt's own `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` (already set per attempt by the launcher; ends with `<run id>/effects/<digest>/attempt-<n>/result.json`); found, or no `/proc`, records `changed`. Liveness first, then rehash, so no attempt process can write after the proof. Launch, kill and Ctrl-C behavior unchanged (no process group). Cost about 10 ms per failed attempt with 679 processes, nothing on success. Outside: a process that scrubs the variable or changes user (C5). Tests: `test_failed_attempt_with_a_live_detached_child_records_changed_and_resume_refuses`, `test_command_that_waits_for_its_children_records_unchanged` | none |
| 2026-11-12 | Review fix F2 (major): the refusal lists everything the flag accepts | In a parallel map the refusal named one item while `--accept-changes` also retried a sibling that wrote its own script. Now every unfinished-step refusal, and the committed-shared refusal when it adds the flag, lists before the offering line every attempt the flag would accept (`unproven_command_retries` over the stored program's site classes), each with its reason. Test: `test_parallel_refusal_names_every_attempt_the_flag_accepts` | none |
| 2026-11-12 | Review fixes F3–F6 (minor) | F3: a parallel item is the compiler segment `par-map:<label>[<n>]` (labels escape brackets), not the substring; a serial binder `par-map:c` retries on plain `resume`. F4: the flag is needed only when an unproven attempt's files differ from its `started` evidence (rehashed in preflight for a reached frontier); an unproven attempt replay does not reach yet (after an `invalidate`) counts, since it cannot be rehashed before it runs. A killed step with unchanged files resumes on plain `resume`, and the flag on it is refused. F5: `specs/cli.md` places the not-needed refusal last in step 10, where the code is. F6: the hand-edited fieldless journal test stays; the reviewer confirmed the same behavior on a journal recorded by the base build (`65cdc6d7`) | none |
| 2026-11-12 | Re-review R1 (major) and R2 (minor) | R1: the scan matched only the failing attempt's locator, so a writer left by attempt 1 let attempt 2 record `unchanged`. Now any live same-user process whose `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` contains `/<run id>/effects/` makes the row `changed` (any attempt, any step of the run). False positives measured with stand-ins: a failing serial command after a provider step and a completed parallel map, and after two agent turns with the run's tmux observation server alive, both record `unchanged` (the observation server and its panes start from the orchestrator's environment, without the variable), so no narrowing to command-class markers. A sibling still running at a parallel item's failure now makes it `changed` (items are unproven anyway). Real provider CLIs that leave background processes were not measured. R2: C4, C5, §8.1 and `specs/state.md` list what the check does not see (scrubbed environment, work handed to a running service, non-dumpable, another user). Tests: the reviewer's three-attempt sequence, a writer left by an earlier step, and the two false-positive cases | none |
