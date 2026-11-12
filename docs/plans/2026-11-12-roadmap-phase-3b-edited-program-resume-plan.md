# Roadmap Phase 3b: Resume Under An Edited Program, Reusing The Committed Prefix

**Status: Plan, accepted 2026-11-12.** Implements part 3b of
[roadmap Phase 3](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-3-edit-and-continue).
Its specification is the accepted design,
[Edit And Continue](../design/workflow_lisp_edit_and_continue.md) ("the
design" below); this page does not restate it. This page owns the order of
work, the tests and the gates. Behavior is owned by
[evaluated execution](../design/workflow_lisp_evaluated_execution.md),
[specs/cli.md](../../specs/cli.md), [specs/state.md](../../specs/state.md) and
[specs/versioning.md](../../specs/versioning.md). Until a task lands, those
documents describe what the tool does: a run resumes only under the program
it started with. Nothing here is copy-safe guidance. No provider call is made
or authorized. Planned against `main` at `4bc14b7d`.

**Goal:** a run continues under an edited workflow and keeps the committed
results whose identity and inputs the edit did not change.

**Headline exit test** (the roadmap's three cases, in
`tests/test_first_hour_e2e.py`, installed command line):

- (a) `test_fixed_script_resumes_the_failed_step_and_the_one_after`. True
  since 3a. Passes unchanged.
- (b) `test_inserted_step_before_step_two_reruns_steps_two_to_four` (T7).
- (c) `test_file_dependence_under_an_edit_never_mixes_old_and_new_results`
  (T7).

What fails today for (b) and (c): plain `resume` exits 2 with
`resume_program_changed`, prints no accepting command, and
`resume --accept-changes` gives the same refusal.

**Approach:** the design's sections 2 to 6. New logic goes in three new
modules (`declaration.py`, `memo_reducer_lineage.py`, `rebase.py`); existing
oversized modules get calls and arguments only.

**Order.** T1 proves the design's nine claims and writes no feature code.
Then T2 the `declaration` rule, T3 reading a lineage, T4 the readers, T5
non-replacing publication, T6 the read-only planner, T7 the write path, T8
guides and closeout. T4 and T5 may run beside T6. Four ordering choices,
each checked against the code:

1. **Readers come before the write path.** Once a command can write the
   record, every reader must already read it: today `_attach_root`
   (`cli/commands/repl.py`) compares the header's digest, and the W4 message
   of design §4 points to a `report` listing that would not exist yet.
2. **The exit tests land in T7,** written first, not in the closeout.
3. **T2 alone shows an author nothing for a comment line.** Probe on `main`:
   a comment line above a committed provider leaves the program digest
   equal, the stored artifact runs, and `resume` exits 0 with no dispatch.
   The "Positions" row of design §9 becomes observable in T7.
4. **T6 prints the plan and a `plan token:` line, not a command**
   ([decision 3](#decisions-for-the-coordinator)): a printed command must
   work when it is printed.

## Global constraints

- Tests first: see each new test fail for the stated reason, implement, see
  it pass, run the controls, commit by pathspec (`git commit -- <paths>`),
  no assistant attribution, no `git stash`. Other sessions hold uncommitted
  edits to `specs/cli.md` and evaluated execution: use a separate worktree.
- Tests drive the public command line with stand-in commands, and provider
  stand-ins on a closed path (`closed_path()` in
  `tests/agent_session_shims.py`). No mocks, no provider or model call, no
  assertion on prompt text. Assert exit codes, the stable first line,
  journal rows, which steps started, run-tree bytes, and that a printed
  command works.
- The provider guard of `tests/conftest.py` stays on. For manual commands,
  put `experiments/thread_m/no_provider` first on `PATH` and check that it
  logged nothing; set `PYTHONPATH` to the working tree, since the editable
  install points at another worktree.
- New test modules are named `tests/test_workflow_evaluated_*.py` (the fold
  guard), with `resume` or `kill` in the name where a journal is written
  (the start-view guard).
- Contract text lands in the commit of the code that makes it true
  ([table](#contract-edits)).
- Narrow selectors, then `pytest -q -n 16 --dist=worksteal --sample 10`. The
  full suite before each merge to `main`, in tmux, against the
  [test baseline](../reports/2026-11-11-test-baseline.md). Check `df` first.
- If a T1 claim fails, the plan stops at that claim
  ([T1](#t1-prove-the-nine-claims-l)).

Sizes: **S** up to one day, **M** two to four, **L** five to eight.

## State of the code, verified 2026-11-12

Probes ran outside the repository with `experiments/thread_m/no_provider`
first on `PATH`; none calls a model and the stub logged nothing. Scratch
directory (not durable):
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/plan-3b/`.

| Claim | Check |
| --- | --- |
| `read_memo` can load a program without an import cycle: importing `machine` loads only `calls`, `provider_io` and `values`; `authority` loads no `memo*` module | Probe |
| Loading and checking one stored artifact costs 2 ms (4 kB), 14 ms (92 kB), 102 ms (193 kB); its site table 0.02 to 0.2 ms. `read_memo` runs several times per effect, so tables must be cached per digest | Probe, 458 artifacts |
| A no-replace rename exists: `rename_noreplace_at` (`orchestrator/_common/io_atomic.py`, used by `prompt_resume_record.py`). `WorkspaceFiles.write_atomic` replaces | Read |
| A recorded run root is a usable fixture: the designer's provider run, copied to another directory, resumes with exit 0, equal journal bytes and no call. `tests/fixtures/provider_delivery_pre_change` is the precedent, and `test_resume_reuses_the_checked_in_pre_change_provider_commit` already resumes a provider commit written under the old `declaration` rule | Probe; read |
| Fresh input is compared with a recorded one at `_reuse_effect_commit`, `_recovered_attempt`, the two host-request checks (position-free) and `confined_recovery._verify_started_input` (children run commands only). No other place | Search |
| Class lookups by identity beyond the four of design §4: `_Reducer.started` (pending scan) and `_dependencies`, `launch_authority._checked_pending_site`, and `cli/recovery._flag_accepts` (reads the header's program) | Search |
| `validate_checked_request` receives no snapshot, so the program in force at a `started` row must be answerable from `RunAuthority` | Read |
| `_attach_root` (`cli/commands/repl.py`) compares `header["program_digest"]` directly | Read |
| The whole `resume` command already runs under the run writer lock (`resume_workflow`), so the plan printed by a refusal is computed under the lock too | Read |
| `_legacy_provider_prompt` (`tests/workflow_evaluated_consumer_sources.py`) recomputes the old `declaration` rule to find a node | Read |
| `tests/test_workflow_evaluated_fast_paths.py` unpacks `_LAST` as a pair; `test_tutorial_blocks_run_as_written` requires a `printed` block to equal every command the refusal printed | Read |

## Limits: where new code goes

Modules at most 500 lines, functions at most complexity 12. Measured with an
AST count on `4bc14b7d`.

- **Over the module limit; calls and arguments only:** `runtime.py` (590),
  `effect_inputs.py` (569), `phased_providers.py` (836), `cli/main.py` (826).
- **Near the limit; must end at or under 500:** `cli/commands/evaluated.py`
  (496; T6 moves `_stored_context` to `cli/recovery.py`), `memo_reducer.py`
  (484), `repl.py` (473), `host_input.py` (461), `workspace_files.py` (456),
  `authority.py` (415).
- **No new branch in:** `execute_pure_run` (26), `prepare_effect` (22),
  `execute_pure_resume` (19), `finish_effect` (18), `host_input._settle`
  (26), `execute_request` (18), `validate_checked_request` (14),
  `_Reducer.started` and `committed` (16), `_resolve_command_input` (16),
  `_check_resume_boundary` (15), `views._update_effect_row` (15),
  `resolve_provider_input` (14), `cli/main.main` (20), `resume_workflow`
  (13), `repl._dispatch` (40), `cli/recovery._effect_diverged` (11).
- **New modules** (all under `orchestrator/workflow/evaluated/`):
  `declaration.py` (both digest rules and the comparison, T2);
  `memo_reducer_lineage.py` (the record's rule, per-row class, step 7's
  scan, the cache comparison, T3); `rebase.py` (plan, refusals, token,
  write, T6 and T7). Plan text is rendered in `cli/recovery.py` (289).

## T1: prove the nine claims (L)

No feature code. Three kinds of output:

- **Tests that pass on `main` and stay** as controls, in
  `tests/test_workflow_evaluated_edit_resume_baseline.py`.
- **Recorded fixtures** under `tests/fixtures/declaration_pre_change/`, one
  run root per case, written by `4bc14b7d`, with a README that says they are
  never regenerated.
- **Scaffolds** on an unmerged branch `proof/phase-3b` in its own worktree
  (not under `.worktrees/`). They start from the designer's and reviewer's
  probes (`plan_probe.py`, `round2_probe.py`, `round3_probe.py`,
  `repeat_probe.py`, `host_probe.py`). One Ledger row per claim records the
  result and the branch commit.

Claims run in the design's order. **If one fails, work stops there.** Tasks
that depend on it do not start, and the coordinator returns the question to
design. T2 depends on claim 2 only and may still land.

| # | Claim | Test or probe | Lets the next task start | Sends the question back |
| --- | --- | --- | --- | --- |
| 1 | Lineage form | Scaffold: per-row reducer, `read_memo` loading named artifacts, the changed `_LAST` comparison and fold guard. Journals: rename then `invalidate` before the record; a second cut before the first record; a return to the first program; an agent turn attempt that failed after dispatch whose identity is a command in the next program, then a cut over it. Reduce "journal plus record" with supplied tables before any artifact exists. Time a 300-step command run with and without one record, three times each | All four reduce and the tree's strict replay passes; the class-change case refuses `invalidate_agent_session_advanced`; every lookup in the search list is marked "row's program" or "safe because kept rows are sites of the new program"; fold-guarded modules pass unchanged; median time per effect within 10% and each artifact parsed once per process | A lookup that needs more than the row's position; an import cycle; a cost above the threshold |
| 2 | Old-digest rule at three points | Record five run roots: committed provider; committed agent turns (`test_clean_run_commits_four_turns_on_two_native_sessions`); a pending agent turn; a committed phased provider; a pending phased attempt. Scaffold: new rule plus the substitution at points 1 and 2 and the kept-pending test. Resume each with no edit. Control: the new rule alone | Each resumes as on `main`, with no new `started` row and unchanged stand-in call logs; the control refuses at the first provider-class row; the substitution is about ten lines per point | A comparison point that cannot take the substitution; a class whose proof or receipt binds the digest so that parts cannot be replaced |
| 3 | Coordinators under an edit | Scaffold planner plus claim 1's reducer, with the suite's stand-ins for a run reference, agent turns and a phased provider. Edit after each (kept); edit before each (refused). A cut at a pending command start's offset. A pending agent turn at or after the cut. A pending run reference or phased attempt that is not kept. `guard_confined_invalidation` on the journal as it will be | Kept ones are reused, reconciled and never dispatched again; refusals carry `invalidate_coordinator_committed`, `invalidate_agent_session_advanced` or `resume_program_changed` and change no byte; the reducer accepts a cut at a pending start | Any coordinator that binds the program digest (only the host request ID is known to); a guard that needs a commit's offset |
| 4 | Preflight precedence | Stays: `test_bare_flag_never_accepts_an_edited_program` and `test_bare_flag_never_accepts_a_committed_divergence`, each with and without an unproven attempt (exit 2, today's code, bytes unchanged). Scaffold: the plan computed after the decision; run `test_program_comparison_precedes_invalid_file_inputs_and_artifact` as written | Both stay green; the resume test passes unmodified; the scaffold's write has one caller | The test needs more than a restated guard |
| 5 | Token coverage | A table of every input the scaffold planner reads, each with the field that binds it. Change each and recompute: source, manifests, a kept commit's prompt file and script, a cancelled commit's script, a reached and an unreached unproven attempt's script, a journal append, the input file, the workspace, an interpreter binary, the price table | Each input changes a field, refuses on its own code, or is listed as "not accepted: it runs as it is" (cancelled steps' files, the price shown) | An input that changes what acceptance cancels and no field |
| 6 | Publication and crash windows | `rename_noreplace_at` on the run root's file system and on tmpfs: a second publication fails and leaves the bytes. A scaffold writer (publish, repair, append) killed at W1 to W5 with the gate of `tests/test_workflow_evaluated_invalidate_windows.py` | Each recovered state is a row of design §4's table; nothing is dispatched before the record is durable | A state with the program switched and the cut not applied |
| 7 | `must_not_repeat` | The scaffold's check on: a committed step declared by the writing program; one declared only by the edit; an uncommitted attempt after a rename and after a dropped declaration; then `invalidate` of the step and a new plan | Each refuses before any write; after `invalidate` the step runs once more; the strict pass on the journal as it will be raises no such refusal | A refusal that can only be decided after the record |
| 8 | Readers | On a scaffold-written run with two programs: `report`, the dashboard projection, REPL attach, `input pending`, `input answer`, `input get`, the monitor scanner. A gate between authority load and journal read in `host_input.pending` | The list of lines to change equals T4's file list; the race gives one transient `memo_inconsistent` that a single reload clears | A reader that needs the writer lock |
| 9 | Metering and cost | Stays: `test_invalidated_provider_attempts_stay_counted_by_report_and_the_cap`, with a metered stand-in and C8 `invalidate` on `main`. Time the scaffold plan on a 300-commit journal against `checked_resume_prefix` | Cancelled attempts stay in `report`'s total and in the cap; the plan costs at most twice the preflight | Spend dropped by a cancellation; a cost that makes decision 6 of the design untenable |

## T2: the `declaration` rule and the old digest (M)

Needs claim 2. **Relaxes a guard**: a recorded digest that differs from the
fresh one can now be accepted.

**Files:** `orchestrator/contracts/closed_program/program.py`
(`strip_node_provenance(node)`, sharing the loop of `strip_provenance`);
create `evaluated/declaration.py`; `providers.py` (the `declaration`
expression in `resolve_provider_input`, no branch); `effect_inputs.py` (one
call in `_resolve_external_input` when `commit` is given, so both callers of
`_reuse_effect_commit` are covered); `agent_turn_recovery.py` (one call in
`_recovered_attempt`, before its comparison).

**New names:** `declaration_digest(subject) -> str`;
`legacy_declaration_digest(subject) -> str` (today's expression, kept
verbatim); `declaration_for_replay(recorded, subject, written_subject) ->
str` (the three lines of design §2). The subject is the site node, or
`provider_view(node, agent)` for a turn. Until T3, `written_subject` is
`subject`. A new attempt after a failure always records the new rule.

Tests, in `tests/test_workflow_evaluated_declaration_resume.py`:

- [ ] `test_comment_and_blank_lines_give_the_same_provider_declaration`: two
      workspaces whose sources differ by a comment line, blank lines and
      keyword order; the provider's `started` rows have equal `declaration`.
- [ ] `test_model_literal_operand_shape_and_binder_name_change_the_declaration`.
- [ ] `test_agent_turn_declaration_ignores_positions` (suite shims).
- [ ] `test_pre_change_agent_turns_resume_without_dispatch`,
      `test_pre_change_pending_agent_turn_is_recovered_at_its_ordinal`,
      `test_pre_change_phased_commit_resumes_without_dispatch`,
      `test_pre_change_pending_phased_attempt_is_recovered`: each T1 fixture
      resumes with no new `started` row and unchanged call logs.
- [ ] `test_recorded_declaration_that_matches_neither_rule_diverges`: set the
      part to another digest in the `started` and `committed` rows and
      recompute `input_digest`; `resume` exits 2 with
      `effect_input_diverged` naming `declaration`.
- [ ] `test_a_retry_after_a_failed_provider_records_the_new_rule`.

**Digest comparison (gate):** compile the catalog and every tracked `.orc`
file that compiles on the base, before and after. Program digests must be
equal for every file; any difference stops the task. List each
provider-class site's old and new `declaration`; all are expected to differ,
and every exception is explained in the Ledger.

**Changes:** `_legacy_provider_prompt` uses `declaration_digest`.
**Controls:** `test_resume_reuses_the_checked_in_pre_change_provider_commit`,
`tests/test_workflow_evaluated_{providers,provider_usage,agent_turns,agent_turn_recovery,phased,phased_recovery,resume_replay,resume_kills,recovery,consumers}.py`,
`tests/test_phase2_exit_e2e.py`.

## T3: read a lineage (L)

Needs claims 1, 3 and 7. **Relaxes guards**: the reducer accepts a record
that cancels commits and switches the program; step 7 compares with the
current program; interpreter pins become a subset for later programs; a
request ID is checked against the writing program. No command writes the
record yet, so no existing run changes.

**Files:** create `evaluated/memo_reducer_lineage.py`; `memo_reducer.py`
(`rebased` in `_RECORDS`, in the terminal guard and in the handler table;
`MemoSnapshot.lineage`; `reduce_memo(raw, site_classes, earlier=())`);
`memo.py` (`read_memo` resolves earlier tables from the artifacts beside the
journal, each verified to its name, cached per digest; a journal without the
text `rebased` takes today's path); `authority.py` (both loaders, the pin
subset); `memo_reducer_agents.py`, `agent_guards.py`, `attempts.py`,
`views.py` (the four lookups; `_retry_baseline`'s range test becomes one
helper that also knows a cut); `capture.py` and `views.py` (pass the
authority's tables); `host_input.py` (`_request_id`);
`cli/commands/evaluated.py` (step 7 only); `tests/memo_fold_guard.py`.

**New names:** `Lineage(tables, record_offsets)` with
`class_at(offset, identity)`; `current_program_digest(raw, header_digest)`;
`program_artifact_name(digest)`; `RunAuthority.earlier`, a tuple of
`(program, offset of the record that ended it)`, and
`RunAuthority.program_at(offset)`;
`load_run_authority_from_bytes(..., memo_bytes=None, read_artifact=None)`;
`attempts.cancelled(snapshot, commit)`;
`_request_id(header, program_digest, identity, attempt)`. `_LAST` stays a
`(reducer, bytes)` pair; tables and record offsets live on the reducer.

Fixtures are built by a helper, `tests/rebased_fixture.py`: it runs the
edited program in a second workspace through the command line, copies that
run's `closed_program.json` under the digest name, and appends the record.
Tests, in `tests/test_workflow_evaluated_lineage_resume.py`:

- [ ] `test_resume_continues_under_the_program_a_record_names` (state W5):
      exit 0; steps at or after the cut start again; kept steps do not.
- [ ] `test_artifact_that_no_record_names_is_ignored` (state W2).
- [ ] `test_missing_or_altered_artifact_is_memo_inconsistent`: `resume` and
      `invalidate` exit 2, `report` exits 1, bytes unchanged.
- [ ] `test_invalid_records_are_memo_inconsistent`: the same program named
      again; a cut that is no active commit or pending start; a cut over a
      committed coordinator; a kept commit that is no site of the new program.
- [ ] `test_invalidate_reaches_back_past_a_record_after_a_rename`.
- [ ] `test_second_record_may_cut_before_the_first`.
- [ ] `test_three_programs_one_returning_to_the_first_resume_and_complete`.
- [ ] `test_dispatched_agent_attempt_keeps_its_class_across_a_record`: the
      later `invalidate` refuses `invalidate_agent_session_advanced`.
- [ ] `test_host_reply_committed_before_a_record_is_kept`.
- [ ] `test_record_reopens_a_completed_terminal`.
- [ ] `test_edit_that_drops_a_pinned_interpreter_stays_readable` and
      `test_later_program_with_an_unpinned_interpreter_is_refused`.
- [ ] `test_child_journal_with_a_record_fails_closed`.
- [ ] `test_fold_cache_continues_across_a_record_and_refolds_under_other_tables`
      (`tests/test_workflow_evaluated_memo_incremental.py`).
- [ ] Gate, a measurement: claim 1's timing, repeated on the real code.

**Changes:** `FoldGuard.check` re-reduces a tip with all its tables;
`install_start_view_guard` passes the authority's earlier tables;
`test_loop_visits_and_procedure_activations_keep_separate_request_ids`
(`tests/test_workflow_host_input_e2e.py`) follows the new signature.
**Controls:** the design's "Must pass unchanged" list (§9), plus
`tests/test_workflow_evaluated_{fast_paths,memo_incremental,memo_agent_classes,agent_invalidate,host_input,host_input_recovery}.py`.

## T4: readers of a run with several programs (M)

Needs claims 8 and 9 and T3. Mostly mechanical; `_attach_root` and the
reload relax a check each.

**Files:** `views.py` (`programs` and each row's `program`, set in
`_effect_rows` and `_view`); `orchestrator/observability/report.py`;
`orchestrator/dashboard/{projection,run_page}.py`; `cli/commands/repl.py`
(`_attach_root` compares with the current program); `host_input.py`
(`pending` reloads the lineage once); `cli/commands/evaluated.py`
(`_stored_context` reads the current program through the loader).

Tests, in `tests/test_workflow_evaluated_lineage_readers.py`, on T3's
fixtures:

- [ ] `test_view_of_a_run_without_a_record_is_byte_identical`.
- [ ] `test_report_and_dashboard_list_programs_and_each_row_program`.
- [ ] `test_rows_stay_for_steps_the_current_program_dropped`: a cancelled
      commit and a retired start show `invalidated`.
- [ ] `test_repl_attaches_to_a_rebased_run_under_its_current_program`.
- [ ] `test_input_pending_and_answer_read_a_rebased_run`.
- [ ] `test_reader_racing_a_record_returns_old_or_new_or_says_rebasing`: the
      gate of claim 8; the reader never writes.
- [ ] `test_cancelled_metered_attempts_stay_in_report_and_under_the_cap`,
      also when the step becomes another class at the same identity.
- [ ] `test_invalidate_on_a_rebased_run_never_changes_the_program`.

**Controls:** `tests/test_workflow_evaluated_{views,readers,recovery_views,dashboard,dashboard_e2e,repl,repl_introspection,report_usage,spend_cap,child_authority}.py`,
`tests/test_cli_report_command.py`, `tests/test_dashboard_*.py`.

## T5: publication without replacing (S)

Needs claim 6. Mechanical. **Files:** `orchestrator/workflow/workspace_files.py`:
`WorkspaceFiles.publish_new(path, content, *, mode=0o600) -> None`:
temporary file, sync, `rename_noreplace_at`, directory sync;
`FileExistsError` when the name is taken; the temporary file is removed on
failure. Tests, in `tests/test_workspace_files_publish_new.py`:
`test_publish_new_writes_durable_bytes`,
`test_publish_new_refuses_an_existing_name_and_leaves_its_bytes`,
`test_publish_new_leaves_no_temporary_file_on_failure`.

## T6: the read-only plan (L)

Needs claims 3, 4, 5 and 7 and T3. Writes nothing. Guarded review all the
same: the author consents to what this prints.

**Files:** create `evaluated/rebase.py`; `resume_prefix.py`
(`checked_resume_prefix(..., snapshot=None)` for the in-memory pass);
`cli/recovery.py` (receives `_stored_context`; `plan_lines`; `_Context.plan`;
plan lines are appended in `recovery_lines`, not inside `_effect_diverged`);
`cli/commands/evaluated.py` (the two handlers pass the plan). `replay.py`
does not change: the lenient pass wraps `_Discovery` and takes back both a
consumed commit and a reached frontier.

**New names:**

```python
@dataclass(frozen=True)
class Plan:            # record is "rebased" or "invalidated"
    record: str; program: ClosedProgram | None; cut: int | None
    kept: tuple[JournalEntry, ...]; cancelled: tuple[JournalEntry, ...]
    retired: tuple[JournalEntry, ...]; asked_again: tuple[str, ...]
    unproven: tuple[tuple[str, int, str | None], ...]   # evidence digest, None if unreached
    runs_first: tuple[str, ...]; cut_reason: str; token: str

class PlanRefusal(Exception): ...     # code, message, identity

def plan_resume(run_root, workspace, *, run_files=None) -> Plan   # the H-G3 entry
def compute_plan(authority, candidate, inputs, *, workspace, provider_io) -> Plan
def token_difference(printed: str, current: str) -> list[str]     # field names
```

`compute_plan` runs rule C10, the refusals of design §5, and the strict
replay on the journal as it will be, so a printed plan is one that would be
accepted. The plan is computed after the refusal is decided.

Tests, in `tests/test_workflow_evaluated_edit_resume_plan.py`:

- [ ] `test_each_edit_kind_prints_its_kept_and_cancelled_steps`: one case per
      row of both tables of design §3; no kept commit follows a cancelled one.
- [ ] `test_plan_refusal_changes_no_byte_and_keeps_code_and_exit`.
- [ ] `test_each_refusal_of_section_5_replaces_the_plan_with_its_reason`:
      first line `resume_program_changed`, no token line.
- [ ] `test_committed_must_not_repeat_step_in_the_cancelled_range_prints_invalidate`.
- [ ] `test_token_is_stable_and_each_change_moves_its_field`: a declared
      script (cut and sets), the source again (program, cut, sets), a journal
      append (journal), an unfinished attempt's script (sets).
- [ ] `test_cut_earlier_than_the_edit_names_the_commit_and_what_differed`.
- [ ] `test_committed_divergence_prints_the_plan_beside_invalidate`.
- [ ] `test_plan_lists_cancelled_provider_cost` (metered stand-in) and
      `test_plan_lists_stop_at_twenty`.
- [ ] `test_host_reply_before_the_cut_is_kept_and_one_after_is_asked_again`.
- [ ] `test_input_answer_under_an_unaccepted_edit_refuses_and_says_why`.
- [ ] `test_plan_resume_returns_the_printed_plan_and_writes_nothing`.

**Changes:** `test_preflight_refusals_preserve_all_evidence` (case
`program`): the `load_run_authority` guard ends when the refusal is decided;
its code, exit and byte assertions stay. The tutorial's `exit 2` block shows
the plan lines; `test_tutorial_blocks_run_as_written` passes unchanged, since
no command is added. **Controls:**
`test_program_comparison_precedes_invalid_file_inputs_and_artifact` as
written, `tests/test_cli_recovery_messages.py`,
`tests/test_workflow_evaluated_script_fix_{retry,review}.py`,
`tests/test_first_hour_e2e.py`, T1's baseline module.

## T7: accept a plan (L)

Needs every claim and T3 to T6. **Relaxes the central guard**: an edited
program and a committed divergence can be accepted.

**Files:** `rebase.py`
(`accept_plan(authority, candidate, inputs, token, *, workspace,
provider_io) -> RunAuthority`: recompute, compare the token at one place,
then publish the artifact or reuse a verified one, repair a torn tail,
append the record, log `[changes_accepted]`;
`plan_token_argument(text) -> str` for argparse); `cli/main.py` (the flag
becomes `nargs="?"`; no branch in `main`); `cli/commands/{resume,evaluated}.py`
(pass the token; with one, `prepare_evaluated_resume` returns the candidate
after the entry, target, representation and interpreter checks;
`accept_plan` is called before `execute_pure_resume`); `cli/recovery.py`
(the token command replaces the `plan token:` line; the W4 message). The
flag and the token are never passed to a child run.

Tests. Exit cases (b) and (c) in `tests/test_first_hour_e2e.py`, as named
above. In `tests/test_workflow_evaluated_edit_resume_accept.py`:

- [ ] `test_printed_command_accepts_and_a_second_resume_writes_nothing`: one
      record, a second artifact, the old token refused.
- [ ] `test_stale_token_is_refused_and_names_what_changed`, one case per
      field; no byte changes.
- [ ] `test_bare_flag_and_a_token_for_another_run_accept_nothing`.
- [ ] `test_flag_before_the_run_id_is_a_usage_error_that_names_the_fix`.
- [ ] `test_token_with_nothing_to_accept_is_refused`.
- [ ] `test_each_refusal_of_section_5_with_a_token`: its code, exit 2, bytes
      unchanged.
- [ ] `test_must_not_repeat_refuses_until_invalidated_then_runs_once`, also
      for a declaration the edit adds.
- [ ] `test_comment_line_above_a_committed_provider_dispatches_nothing`.
- [ ] `test_committed_prompt_file_change_writes_the_journal_invalidate_would`.
- [ ] `test_edit_and_a_failed_steps_fixed_script_take_one_resume`.
- [ ] `test_asked_again_request_gets_a_new_id_and_the_old_one_is_stale`.
- [ ] `test_coordinators_before_the_cut_are_kept_and_after_it_refuse`.

In `tests/test_workflow_evaluated_edit_resume_kills.py`:

- [ ] `test_kill_in_each_window_leaves_the_old_program_or_the_new_one`: W1 to
      W5; nothing is dispatched before the record is durable; an artifact
      left at W2 is reused after the source is reformatted.
- [ ] `test_failed_sync_exits_2_and_says_the_change_may_be_in_force`.
- [ ] `test_kills_under_an_edited_program_reach_the_uninterrupted_value`.
- [ ] `test_journal_with_a_record_reduced_without_the_kind_is_memo_inconsistent`.

**Changes** (each refusal gains the token command):
`test_program_edit_refusal_names_the_changed_step_and_a_run_command_that_works`,
`test_committed_script_edit_refusal_prints_invalidate_and_resume_that_recover`,
`test_a_shared_script_edit_after_invalidating_later_steps_offers_invalidate_that_recovers`
(`tests/test_cli_recovery_messages.py`);
`test_shared_script_fix_recovers_through_printed_invalidate_and_resume`
(`tests/test_workflow_evaluated_script_fix_retry.py`); the tutorial's
`invalidate` block with `test_tutorial_blocks_run_as_written`
([decision 6](#decisions-for-the-coordinator)). Tests of T3 and T4 that used
the fixture helper switch to the printed command where they can.
**Controls:** the design's "Must pass unchanged" list; every test of the
bare flag; T1's baseline module.

## T8: guides and closeout (M)

- [ ] `docs/runtime_execution_lifecycle.md` ("Resume", "Edit a prompt and
      continue"); `docs/lisp_workflow_drafting_guide.md` (hygiene names,
      Python-built runs, the loss in a parallel map, workspace files are not
      rolled back); the tutorial's "Two limits".
- [ ] H-G3: document `plan_resume` and plain `resume` as the planning
      command, with the workspace rule of design §10. No command is added.
- [ ] Statuses: the design page, the spike page, the roadmap's Phase 3 state
      and known-limits row, `docs/design/README.md`,
      `docs/capability_status_matrix.md`, rows in `docs/index.md`.
- [ ] Exit gate: the three headline tests, the kill suites, the sample, then
      the full suite; results in the Ledger.

## Contract edits

Row numbers count the design's before/after table from 1 ("§3, goals") to 51
(`specs/versioning.md`). The rule: until T7 no command writes the record, so
every sentence of evaluated execution stays true of every run the tool can
produce. `specs/state.md` defines the record, the artifact and the view keys
as soon as the code honors them.

| Rows | Document | Task |
| --- | --- | --- |
| 5 | Evaluated execution §7.2, the `declaration` sentence | T2 |
| 47, 48, 50 | `specs/state.md`: the artifact, the `rebased` record, request identity | T3 |
| 49 | `specs/state.md`: view `steps`, `programs` and `program` | T4 |
| 10, 33, 36, 38, the clause "the plan is printed" only | Evaluated execution §8.1; `specs/cli.md` steps 7 and 10 and the names column of `resume_program_changed` | T6 |
| 1 to 4, 6 to 30 (the rest of 10), and the new rule C10 | Evaluated execution §3, §7.1, §7.3, §8.1, §8.3 to §8.5, §9.5, §10, §11, §12, §17 | T7 |
| 31, 32, 34, 35, 37, 39 to 46, the rest of 33, 36 and 38 | `specs/cli.md`: synopsis, the flag, steps 7 and 9 to 11, Diagnostics | T7 |
| 51 | `specs/versioning.md` | T7 |

**Accepted temporary bridge.** Between T3 and T7 `specs/state.md` describes a
record that no command writes, and evaluated execution does not name it.
Between T6 and T7 the refusal prints a token that no command accepts.

## Review load

3a needed three rounds for 60 lines. Here four tasks relax a guard. Each
gets a reviewer who did not write it, an adversarial brief, and mutation
checks: the reviewer breaks the rule and names the test that fails. Plan for
three rounds on T7 and two on T2, T3 and T6.

| Task | Class | Attacks to try |
| --- | --- | --- |
| T1 | Evidence | Rerun each probe independently; look for a claim shown on a fixture that cannot fail |
| T2 | Guarded | Return the recorded digest always (which test fails?); drop the condition that both rules agree on the written subject; use the site node for a turn; substitute after the digest is taken; let a retry record the old rule; a refactor of `strip_provenance` that moves a program digest |
| T3 | Guarded | A planted artifact that no record names; a record naming the program in force; a cut past the end, at a `failed` row, over a coordinator or over a dispatched agent attempt; classify by the identity's latest row; continue a cached fold under other tables; a record in a child journal; a later program with an unpinned interpreter; a torn record; a host reply checked against the current program |
| T4 | Mostly mechanical | A reader that writes; a reload that loops; a view of an unedited run that changes by one byte |
| T5 | Mechanical | A crash between the rename and the directory sync |
| T6 | Guarded (read-only) | Any byte written by a refusal; the lenient pass swallowing a `memo_inconsistent` that is corruption; a plan printed that the strict pass would refuse; a list cut at 20 that the token does not bind in full; a token equal across two different plans |
| T7 | Guarded, central | A second path to the write (remove the token comparison: which test fails?); the bare flag, `input answer` or a child run reaching the write; change the source, a script, the journal or an unfinished step's script between print and accept; accept twice; a token from another run; a kill at each window; `must_not_repeat` by rename, dropped or added declaration and class change; a coordinator or a pending turn in the range; a human reply asked again without being listed; the exit code and message after W4; a view failure after the record |
| T8 | Mechanical | Every printed command in a guide runs |

## What this makes harder

The design's list stands. The plan adds:

- Two digest rules for `declaration` stay in the code until old runs age
  out, and five recorded run roots must never be regenerated.
- The reducer reads a record three tasks before anything writes it; tests
  build it by hand until T7.
- `RunAuthority` grows a lineage with record offsets. A loader that ignored
  the journal now scans it.
- A per-digest table cache joins `_LAST` as process state that tests must
  reset.
- `cli/commands/evaluated.py` and `memo_reducer.py` sit at the module limit:
  the next change to either must move code out first.
- The build is longer than the roadmap's three to four weeks (decision 10).

## Decisions for the coordinator

1. **Token field width.** Recommended: four fields of eight hex digits, as
   designed. Separate fields let a mismatch say what changed; 32 bits each
   guards against accident, which is the token's job. Alternative: sixteen
   digits per field (a 69-character token) if it should also resist a
   process that searches for a collision. The width is one constant.
2. **Readers before the write path** (T4 before T7). Recommended.
   Alternative: the brief's order, with `report` and the REPL unable to read
   a rebased run between two merges.
3. **What T6 prints.** Recommended: the plan and a `plan token:` line, no
   command. Alternatives: merge T6 and T7 to `main` together; or keep the
   token unprinted until T7 and test it through `plan_resume`.
4. **Old-rule journals in tests.** Recommended: run roots recorded on the
   base commit by T1 and checked in, as `provider_delivery_pre_change` is.
   Alternative: edit digests in a fresh journal, which must also rewrite
   agent receipts and phased proofs.
5. **The publication primitive.** Recommended: the existing
   `rename_noreplace_at`; where the system lacks it, acceptance refuses
   before any write. Alternative: `os.link` then unlink.
6. **The tutorial after T7.** Recommended: keep the `invalidate` then
   `resume` block, add one sentence on the one-command form, and let a
   `printed` block be an ordered subset of the printed commands.
   Alternative: teach the token command, with a placeholder the test fills.
7. **Contract timing** (the rule above the table). Recommended as written.
   Alternative: all `rebased` text in T7, with the reducer ahead of the
   specification for three tasks.
8. **Thresholds for T1.** Recommended: time per effect within 10% of the
   unedited run; plan cost at most twice the resume preflight.
9. **Scope lever, not recommended:** accepting a committed divergence under
   an unchanged program (design decision 4) can leave T6 and T7 if time is
   short; `invalidate` then `resume` already covers it.
10. **Total.** Four L, three M, one S: 27 to 45 working days, about 35
    single-threaded, before review rounds. Recommended: accept, and run T4
    and T5 beside T6.

## Not verified

- The scaffolds of T1 do not exist yet. Everything in "Sends the question
  back" is open, and claims 2 and 3 hold the design's largest unread risk.
- Only a provider run root was relocated and resumed. That agent-turn and
  phased run roots relocate with their native stores and receipts is assumed
  (decision 4 falls back to the alternative for a class that does not).
- That one call in `_resolve_external_input` reaches both callers of
  `_reuse_effect_commit`, and that `validate_turn` and
  `validate_phased_commit` read the substituted parts, was read, not run.
- `strip_node_provenance` is specified by a property (it equals the node
  taken from the stripped program), not prototyped.
- Line budgets and complexities are counted on `4bc14b7d`; the new code's
  size is estimated. That `evaluated.py` stays under 500 after T7 depends on
  moving `_stored_context` in T6.
- The class-change fixture (a dispatched agent attempt whose identity
  becomes a command) is designed from the reducer's rules, not built.
- The digest comparison of T2 was not run; "no program digest changes" is
  reasoned from the code path.
- `renameat2` was not tried on the file systems runs live on.
- No test of this plan was written or run. Sizes are estimates.

## Ledger

| Date | Decision or event | Detail | Spend |
| --- | --- | --- | --- |
| 2026-11-12 | Plan accepted by the coordinator | T1 starts now and writes no feature code; the plan stops at the first failed claim and returns the question to design. T4 and T5 run beside T6. The total (27 to 45 working days before review rounds) is accepted; it is longer than the roadmap's three to four weeks for the build | none |
| 2026-11-12 | Rulings, decisions 1 to 8 and 10 | As recommended. The token keeps four fields of eight hex digits: it guards against accidents and lets a mismatch name what changed. Readers land before the write path, so `report` and the REPL can read a rebased run from the first merge that can write one. T6 prints the plan and a `plan token:` line and no command; the command is printed from T7. Old-rule journals are run roots recorded on the base commit by T1 and checked in. Publication uses `rename_noreplace_at`, and acceptance is refused before any write where it is unavailable. The tutorial keeps its `invalidate` then `resume` block and gains one sentence. `specs/state.md` rows land with the reader tasks, the rest in T7 except the plan-is-printed clauses in T6. T1 thresholds: time per effect within 10% of an unedited run; plan cost at most twice the resume preflight | none |
| 2026-11-12 | Ruling, decision 9 | Token acceptance of a committed divergence under an unchanged program (design decision 4) stays in scope. It is the one piece that may be dropped later, by a recorded ruling, if T7's review rounds run long | none |
| 2026-11-12 | Corrections to the design found while planning, accepted | A comment line above a committed provider does not re-run it on `main` when the program is otherwise unchanged (the program digest is equal), so T2 alone shows nothing for that case and the design's "Positions" row is observable only from T7. A no-replace rename already exists (`rename_noreplace_at`). `RunAuthority` must carry record offsets, not only earlier programs. Two tests the design did not list change in T2 (`_legacy_provider_prompt` in `tests/workflow_evaluated_consumer_sources.py`; `test_resume_reuses_the_checked_in_pre_change_provider_commit` is an existing control). Four class lookups beyond the design's four are checked by T1 claim 1 | none |
| 2026-11-12 | T1 done: none of the nine claims was refuted | Control tests and recorded pre-change run roots are merged (`tests/test_workflow_evaluated_edit_resume_baseline.py`, `tests/fixtures/declaration_pre_change/`); scaffolds stay on the unmerged branch `proof/phase-3b` (worktree `/home/ollie/p3b-proof`), last commit `886373e3`. T2 starts | none |
| 2026-11-12 | T1 claim 1, lineage: proved | All four journals reduce and pass the strict replay; the class change refuses with `invalidate_agent_session_advanced`. Time per effect with one record over none: 0.965 (limit 1.10), valid only when the edited program does the same evaluation work as the base, because the view replay per commit is O(prefix). Findings: a fifth class lookup, `attempts._retry_baseline`, must use the row's program; `test_the_saved_fold_covers_every_reducer_state_field` must list the new reducer field. Open: run noise of about 8% is close to the threshold | none |
| 2026-11-12 | T1 claim 2, old-digest rule: proved | The position-free rule alone refuses at the first provider-class row; with the old digest accepted at all three comparison points, all five recorded run roots resume as on `main`. Points 2 and 3 are each needed. One to three lines per call site plus a `declaration` module | none |
| 2026-11-12 | T1 claim 3, coordinators: proved, one case not run | A kept run reference, kept agent turns and a kept phased provider are reused and never dispatched again; edits before them and pending ones not kept refuse with the expected codes and change no byte. Not run: a live confined child under `guard_confined_invalidation` | none |
| 2026-11-12 | T1 claim 4, preflight precedence: proved | The guard of `test_preflight_refusals_preserve_all_evidence[program]` can end at the refusal decision with every assertion kept | none |
| 2026-11-12 | T1 claim 5, token coverage: proved | Each token field moves only when its own input changes. Undeclared files, cancelled commits' scripts and pinned interpreter binaries do not move it; the scripts of unproven attempts move it only when the plan reaches them | none |
| 2026-11-12 | T1 claim 6, publication and kill windows: proved | `rename_noreplace_at` refuses a second publication on ext4 and tmpfs (errno 17, to be mapped to `FileExistsError`). Kills at W1 to W5 refuse or resume correctly with nothing dispatched in between. Open: W1 leaves a stale `.tmp`; power loss at W4 was not injected | none |
| 2026-11-12 | T1 claim 7, `must_not_repeat`: proved | Refuses for a committed step in the range, a declaration added only by the edit, and an uncommitted attempt that was renamed or had its declaration dropped; `invalidate` first lets the step repeat | none |
| 2026-11-12 | T1 claim 8, readers: proved | `report`, the view loader, the dashboard projection, REPL attach, `input pending`, `input answer`, `input get` and the monitor scanner read a two-program run without errors and without writing. Finding: the end-at-caller check compares tables, so a stale reader with an equal table is not detected | none |
| 2026-11-12 | T1 claim 9, metering and plan cost: proved at the margin | Cancelled attempts stay counted by `report` and the cap. Plan cost over the resume preflight: 1.91 in the worst case (limit 2.0), 1.43 with half the journal kept. Ruling: measure again at the T7 gate; if per-plan work pushes it over 2.0, the strict pass reuses the lenient pass's verified prefix before the threshold is raised | none |
| 2026-11-12 | Ruling on the proof branch's program cache | The proof branch caches the whole verified program per process under its digest, where the design caches only the site table. T3 caches the table only, as designed: a second run root in the same process (the REPL, a daemon) must verify its own copy of an artifact | none |
| 2026-11-12 | T2: the pending phased fixture has no T2 comparison | Outside a plan a pending phased attempt is never compared with a fresh input: its receipt and proof bind the recorded digest, cleanup checks receipt against row, and recovery starts a new attempt with the new rule. The recorded `phased_pending` root also refuses `provider_phased_cleanup_failed` on the base, because its transport reservation under `/tmp` is gone. So T2 has no test for it (`test_pre_change_pending_phased_attempt_is_recovered` was dropped); the comparison is the planner's kept-pending test (comparison point 3), which T6 writes and tests | none |
| 2026-11-12 | Ruling carried from the Lane D stage 3 review: run references and package changes | Today a run that uses a run reference cannot be resumed after any package file changes (`resume_program_changed`): the parent's program digest embeds the compiler and runtime identity, while child recovery already ignores it. Whether the parent's resume check should ignore the compiler identity is assigned to T6/T7, which own the program-equality refusal. No code for it now | none |
| 2026-11-12 | T2 merged (`deb3e5a0`) | New provider rows record a `declaration` digest with no source positions; a recorded earlier-rule value is accepted at the two comparison points in code (`effect_inputs._resolve_external_input`, `agent_turn_recovery._recovered_attempt`) only when it equals the earlier rule applied to the current node; the third point (kept pending start) arrives with T6, whose review checks that `rebase.py` calls `replay_parts`. Independent review: approve with fixes, 0 blockers, 1 major (no test that the digest covers the whole node; closed with two tests that fail when any one of six fields is left out), 5 minors (all applied; the design's row on moving a provider into a procedure is corrected: the declaration stays, the identity changes). No program digest moved (690 files compiled on both trees). Note for T3 and T7 reviewers: two identical calls at different sites share a `declaration` digest and are kept apart by identity only. Full suite on the branch: 14,673 passed, the four nanoBragg baseline failures, no provider called. | none |
