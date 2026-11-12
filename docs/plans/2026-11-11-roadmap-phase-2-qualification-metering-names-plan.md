# Roadmap Phase 2: Qualification, Metering And Stable Names Plan

**Status: Plan, accepted 2026-11-11.** Implements Phase 2 of the
[current roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-2-qualification-metering-and-stable-names).
This page owns the order of work, the tests and the gates of the phase.
Behavior is owned elsewhere: parallel map by
[evaluated execution §11](../design/workflow_lisp_evaluated_execution.md#11-parallel-effects)
and the contract text of the
[Phase 5 execution plan](2026-10-07-evaluated-execution-phase-5-plan.md),
providers by [specs/providers.md](../../specs/providers.md), the command line
by [specs/cli.md](../../specs/cli.md), Agent Sessions by
[their design](../design/workflow_lisp_agent_sessions.md). Nothing here is
copy-safe guidance and nothing here authorizes provider spend: the
[budget request](#budget-request) goes to the owner first. Until a task
lands, the documents above describe what the tool does.

**Goal:** parallel map is qualified through the public command line, a run
records what its provider calls cost, generated step names survive an
insertion, and the Agent Sessions comparison is ready to run.

**Headline exit test:** a parallel best-of-N run survives a kill and resumes,
and its report shows tokens per step and a total
([one automated test](#headline-exit-test)).

**Architecture:** qualification adds public tests on code that exists and
changes production code only where a test fails. Metering turns on the
structured output the agent CLIs already offer, through the executor's
existing transport decoding, and writes one `usage.json` beside each
attempt's `stdout.txt`; the memo, effect identities and program digests do
not change, and `report` reads those files. Names change in the Python
emitter first (a Python run resumes from its retained `.orc` snapshot, so
none is stranded); the `.orc` site rule waits for the Phase 3 spike.

## Global constraints

- New or substantially changed modules: at most 500 lines; functions: at
  most cyclomatic complexity 12. `executor.py` and `elaborate.py` are far
  over already: add calls there, not logic.
- Tests assert behavior, through the public command line where one exists.
  No mocks (stand-in `claude` and `codex` executables on `PATH` are the
  provider) and no assertion on literal prompt text.
- Narrow selectors first, then `pytest -q -n 16 --dist=worksteal --sample 10`
  as the broad check, and the full suite before a lane merges, compared with
  the [test baseline](../reports/2026-11-11-test-baseline.md).
  `PYTHONPATH` is the checkout under test.
- Commit by pathspec; no assistant attribution.
- A runtime or language change needs an end-to-end check through
  `orchestrator run` and `resume`.
- No provider call outside an owner-approved budget, never a Fable model in
  an experiment call. Only A3's live smoke and D2 spend.
- Every task ends the same way: see the new tests fail for the stated
  reason, implement, see them pass, run the named controls, commit.

Sizes: **S** up to one day, **M** two to four days, **L** five to eight.

## State of the code, re-verified 2026-11-11 at `60f8b13d`

| Claim | Check |
| --- | --- |
| Parallel map runs and replays; the 69 tests of four `tests/test_workflow_evaluated_parallel*.py` modules pass | Ran |
| The Phase 5 plan has 17 open boxes: Task 3 two, Task 5 five, Task 6 five, Task 7 five. Its `..._parallel_consumers.py` does not exist; no public test kills a parallel run | Read |
| `.orc`: inserting an unnamed effect before two others turns `#1, #2` into `#2, #3` | Probe |
| `.orc`: an `if` whose `then` arm has no effect puts its `else` sites under `#1 / body / else`; an effect in `then` moves them to `else` | Probe |
| Python: inserting one command renames `_e0 _e1 _e2` to `_e0 … _e3` | Probe |
| Resume recompiles the source and refuses a different digest (`prepare_evaluated_resume`); a Python run resumes from its retained generated `.orc`, never from Python | Read |
| A provider attempt keeps `prompt.txt`, `stdout.txt`, `stderr.txt` in `effects/<sha>/attempt-<n>/`; nothing under `orchestrator/workflow/evaluated/` records usage | Read |
| The provider command line is not among an effect's `input_parts`; memo rows reject unknown fields (`memo_reducer._shape`) | Read |
| Built-in `claude*` and `codex*` templates run in plain-text mode; only Agent Sessions turns use `--output-format stream-json --verbose` and `exec --json` | Read |
| A template's `command_metadata_mode` sends a plain call through the transport decoder, which keeps raw stdout and streams assistant text; only OMP templates set it | Read; not run for Claude or Codex |

What the CLIs report: Claude's stream-json output ends with a `result` line
carrying `usage`, `modelUsage` (per model) and `total_cost_usd`
(`experiments/authoring_check/readout.py` read it in today's live sessions).
`codex exec --json` ends a turn with `turn.completed` and a `usage` object
(`tests/experiments/fixtures/es_task3/codex-0.145.0-success.jsonl`). The
plain modes report no structured usage. Parsers exist in
`experiments/orc_structural_search/{metering,pricing}.py`, but only
`orchestrator*` is packaged, so the runtime cannot import them from there.

## Order and lanes

Four worktrees, one per lane.

| Lane | Tasks, in order | Waits for |
| --- | --- | --- |
| 1 parallel | A1, A2, A3, A4 | nothing |
| 2 metering | B1, B2, B3, then B4 | B4: the [dashboard migration](2026-11-11-dashboard-evaluated-runs-migration-plan.md) branch merged (it rewrites `report`) |
| 3 names | C1 and C2 together, then C3 | C3: the Phase 3 spike's finding and decision 4 |
| 4 comparison | D1, then D2 | D1: B3 merged. D2: B4 merged and owner approval |

Shared files: `orchestrator/workflow/evaluated/runtime.py` (a lane 1 fix and
the B3 check; B3 rebases) and `tests/workflow_evaluated_recovery_helpers.py`
(B2 adds usage output to `install_standins`; lane 1 only calls it). The exit
test lands after lanes 1 and 2. Phase 3 implementation starts after A2 and
A3 merge (its baseline) and after C1, C2 and the C3 decision; its spike runs
beside this phase.

## Lane 1: parallel-map qualification

The Phase 5 plan stays the contract text. Stale in it: the status paragraph
and baselines (targets 2.38 to 2.40, phased settlement and today's test
removal landed since); the test owners it names; its live smoke's models,
which are above the ceiling; Task 7's sole test window, fast-forward push,
Phase 6b, Phase 7 and decision 8. A4 marks these in place.

### A1: item working directories through the command line (M)

Closes Task 3, boxes 2 and 3. **Files:** create
`tests/test_workflow_evaluated_parallel_cwd_variants.py`; production only on
a failing case: `orchestrator/workflow/evaluated/{effect_inputs,closure,commands}.py`,
`orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`.
**Consumes:** the D2 clauses; the fixtures of `..._parallel_cwd_cli.py`.

- [ ] `test_parallel_item_cwd_variant_follows_d2`, parametrized over the
      variants the execution record lists as missing: prior script gone, new
      homonym in the item directory, symlink and `..` component order,
      absolute cwd outside the workspace, destination overlap, mutation
      after commit, package shadow, unsafe carrier (absolute, `..`, escaping
      symlink), workspace relocated before resume. Each runs and resumes
      through the CLI with different same-name files in the outer and item
      directories and asserts which bytes ran, or the refusal code with no
      row written. A D2 clause the code contradicts goes to the coordinator.
- [ ] `test_reserved_workspace_root_is_never_inherited`: a poisoned
      `ORCHESTRATOR_WORKSPACE_ROOT`, ambient and authored, reaches no
      command, provider, nested `orchestrator` or run-reference child.
- [ ] Control: `tests/test_logical_workspace_coordinates.py`. The built-in
      adapter's inline signature omits `schema_version`: record as a limit.

### A2: public kill, resume and invalidate (L)

Closes Task 5. **Files:** create
`tests/test_workflow_evaluated_parallel_{kill_resume,invalidate}.py`; fixes,
if any, in `orchestrator/workflow/evaluated/{parallel,replay,runtime}.py`.
**Consumes:** `kill_at`, `resume`, `dispatches` of
`tests/workflow_evaluated_recovery_helpers.py`.

- [ ] `test_kill_after_two_of_four_commits_resumes_only_missing_effects`:
      four items, two active, one item with two sequential effects; SIGKILL
      the process group after exactly two commits. The memo holds two
      commits; resume exits 0; results are in input order; no committed
      identity is dispatched again; the two-effect item continues from its
      second effect.
- [ ] `test_kill_in_each_parallel_window_resumes_to_the_same_value`, over
      start reservation, output before commit, commit before view and
      coordinator commit before settle, each with a retryable and a
      `must_not_repeat` command (the latter refuses by its existing code).
- [ ] Refusals that write nothing: `test_later_sibling_divergence_refuses`,
      `test_missing_result_bytes_refuse`,
      `test_malformed_settlement_obligations_refuse`. Also
      `test_relocated_workspace_keeps_relative_item_cwd`,
      `test_two_completed_resumes_leave_identical_bytes` and
      `test_unsettled_run_ref_behind_a_full_pool_is_not_launched_twice`.
- [ ] `test_invalidate_cancels_the_whole_suffix_across_interleaved_items`,
      `test_invalidate_refuses_a_committed_run_reference_suffix`.
- [ ] Controls: `tests/test_workflow_evaluated_{resume_kills,recovery,invalidate_windows}.py`.

### A3: the best-of-N consumer (M)

Closes Task 6. **Files:** create
`tests/test_workflow_evaluated_parallel_consumers.py`. **Consumes:**
`PROGRAMS["best_of_n"]`, `install`, `compile_current`, `resume_to_completion`
of `tests/workflow_evaluated_consumer_sources.py`, and `install_standins`.
The test installs a copy of
`experiments/orc_vs_single_call/workflows/best_of_n.orc` at target 2.37 and
at the newest target, adding only `:parallel 2 :workspace repo`.

- [ ] `test_parallel_best_of_n_overlaps_within_its_bound_and_judges_once`:
      two implementations overlap and never three; the judge starts once,
      after all four, with repositories and accounts in input order;
      requests match commits by identity and attempt.
- [ ] `test_failed_implementation_keeps_sibling_commits_and_resume_judges_once`,
      `test_compile_dry_run_run_report_and_two_completed_resumes`.
- [ ] Live smoke, only after tranche T1 is approved: the same copy, both
      aliases bound to `claude_unrestricted_workspace`, every model
      `claude-haiku-5-5`, four candidates, then a completed resume. Keep the
      request, attempt and usage files; retry a failure by `resume`.

### A4: closeout (M)

Closes Task 7. **Files:** the capability matrix, the drafting guide, the
evaluated design §11, `specs/providers.md`, the
[execution record](../reports/2026-10-07-evaluated-execution-phase-5-closeout.md),
the Phase 5 plan (boxes and a stale-text notice), the delivery plan's Phase 5
status, `docs/index.md`.

- [ ] Census of new modules and functions (lines, Radon). Rename
      `test_live_parallel_execution_is_still_refused` (it tests the bare
      evaluator).
- [ ] Rerun the old-target artifact comparison and the full suite only if
      lane 1 changed bytes under `orchestrator/`; otherwise say so and reuse
      the recorded evidence.
- [ ] Write the recipe and its limits; mark parallel map publicly qualified;
      a reviewer distinct from the authors reads diff and evidence.

**Regression baseline for Phase 3:** the three new modules of A2 and A3,
`tests/test_workflow_evaluated_parallel_resume.py`,
`tests/test_workflow_evaluated_resume_{replay,replay_boundary,retry,kills}.py`
and the exit test. Phase 3 may change the two invalidate tests and any
`resume_program_changed` expectation only through its accepted design
revision; every other test in the list must pass unchanged.

## Lane 2: token and cost metering

**Makes harder:** `stdout.txt` of a built-in provider step becomes transport
JSON, not prose; a CLI release that changes that JSON turns usage into
`unknown` without failing anything; the cap is local to one invocation.

### B1: one usage reader and one price table in the package (M)

**Files:** create `orchestrator/providers/{usage.py,pricing.py,price_table.json}`,
`tests/test_provider_usage.py` and
`tests/fixtures/provider_usage/claude-stream-json.jsonl` (a real transcript,
content emptied); modify `experiments/orc_structural_search/{metering,pricing}.py`
to import the moved functions (the row reader of `claude_usage`,
`_charge_tokens`, `_codex_charge_tokens`, `validate`, `usage_cost`) and drop
their copies; `pyproject.toml` package data.

```python
def usage_from_stdout(metadata_mode: str | None, raw_stdout: bytes, *, model: str | None) -> dict:
    """{"status": "reported", "source": str, "reported_cost_usd": float | None,
        "rows": [{"model": str, "tokens": {"input", "output", "cache_read", "cache_write"}}]}
    or {"status": "unknown", "reason": "no_transport" | "no_usage_event" | "malformed"}."""
def priced(rows: list[dict], table: dict) -> float | None:  # None if a model has no rates
```

Claude: the `result` line's `modelUsage`; without one (a killed turn), the
`assistant` rows, once per message id. Codex: the last `turn.completed`;
charged input is input minus cached and cache-write tokens (the first
branch of `_codex_charge_tokens`); the model comes from the call's policy.
The table has `currency`, `tokens_per_unit`, `source` (the vendors' price
pages), `date` and four rates for every model a built-in template or
catalog workflow names.

- [ ] `test_claude_result_line_gives_tokens_per_model_and_reported_cost`,
      `test_claude_killed_turn_counts_each_message_once`,
      `test_codex_turn_completed_separates_cached_input`,
      `test_plain_text_or_malformed_stdout_is_unknown_not_zero`,
      `test_price_table_names_source_date_and_four_rates_per_model`,
      `test_model_without_rates_prices_as_none`.
- [ ] Control: `ORCHESTRATE_CAMPAIGN_TESTS=1 pytest -q tests/experiments/test_orc_structural_search_metering.py`.

### B2: record usage per attempt (M)

**Files:** `orchestrator/providers/registry.py` (the plain `command` of each
built-in `claude*` and `codex*` template gains the structured flags and
`command_metadata_mode`), `orchestrator/workflow/evaluated/providers.py`
(`launch_provider` writes `usage.json` in its existing `finally`;
`_reply_excerpt` reads the decoded text),
`orchestrator/providers/executor.py` only if a plain call fails on a
transport parse error, `tests/workflow_evaluated_recovery_helpers.py`
(stand-ins print transport lines with fixed usage), `specs/providers.md`;
create `tests/test_workflow_evaluated_provider_usage.py`.

**After:** `effects/<sha>/attempt-<n>/usage.json` holds the B1 result for
every provider, agent-turn and phased attempt, failed ones included. A
template without a transport mode, and a phased provider, record `unknown`
with reason `no_transport`. No memo row, input part or program byte changes.

- [ ] Through `orchestrator run` with stand-ins:
      `test_provider_step_writes_usage_beside_its_stdout`,
      `test_failed_attempt_keeps_the_usage_it_reported`,
      `test_template_without_transport_records_unknown`,
      `test_unreadable_transport_never_fails_a_call_that_wrote_its_result`,
      `test_terminal_shows_assistant_text_not_transport_lines`,
      `test_memo_rows_and_program_digests_are_unchanged` (row key sets, and
      the digests of three catalog programs recorded before the change),
      `test_run_completed_before_metering_resumes_as_a_no_op`.
- [ ] Controls: `tests/test_provider_execution.py`,
      `tests/test_workflow_evaluated_providers.py`, the agent-turn modules.

### B3: spend cap (S to M)

**Files:** `orchestrator/cli/main.py` (`--max-cost-usd` on `run`, `py run`,
`resume`), `orchestrator/cli/commands/evaluated.py`,
`orchestrator/workflow/evaluated/runtime.py` (one check before a
provider-class attempt is reserved), `orchestrator/providers/usage.py`
(`spent(run_root, table)`), `orchestrator/cli/recovery.py`, `specs/cli.md`;
create `tests/test_workflow_evaluated_spend_cap.py`.

**After:** with the flag, before the `started` row of a provider-class
effect, the run sums the priced cost of every `usage.json` in the run. At or
over the cap it stops with `spend_cap_reached`, printing spent, cap and the
`resume` command; no row is written. An earlier provider attempt with
unknown usage or an unpriced model stops it with `spend_cap_unmetered`
(decision 3). Without the flag nothing is read. The cap is not stored.

- [ ] `test_cap_stops_before_the_next_provider_call_and_a_higher_cap_resumes`
      (the second stand-in is never launched; resume does not repeat the
      first), `test_cap_with_an_unmetered_attempt_stops_before_the_next_call`,
      `test_commands_run_under_a_reached_cap`,
      `test_parallel_batch_overshoots_only_by_calls_already_started`,
      `test_run_without_cap_ignores_unknown_usage`.

### B4: `report` shows tokens and cost (S; after the dashboard branch merges)

**Files:** `orchestrator/providers/usage.py`
(`run_usage(run_root, steps, table)`),
`orchestrator/workflow/evaluated/views.py` (`report_snapshot` only; the
shared view stays memo-only), `orchestrator/observability/report.py`,
`orchestrator/cli/main.py` (`report --price-table PATH`),
`specs/{observability,cli}.md`, `docs/workflow_monitoring.md`, the
[backlog item](../backlog/active/2026-04-30-provider-step-token-usage-accounting.md)
(disposition: implemented here); create
`tests/test_workflow_evaluated_report_usage.py`.

**After:** each provider-class step has
`"usage": {"tokens": {...} | null, "cost_usd": float | null, "attempts": n, "unknown_attempts": k}`
summed over all its attempts; `run.usage` is the same over the run plus the
table's `source` and `date`. Markdown prints `unknown` when no attempt
reported, a leading `≥` when some did not, and never `0` for an unmetered
step. Once migrated, the dashboard shows `usage.json` as an attempt file; a
totals column calling `run_usage` is a later change.

- [ ] `test_report_shows_tokens_per_provider_step_and_a_run_total`,
      `test_unmetered_step_shows_unknown_and_marks_the_total_partial`,
      `test_retried_step_sums_every_attempt`,
      `test_unpriced_model_shows_tokens_and_no_cost`,
      `test_report_names_the_price_table_source_and_date`,
      `test_command_steps_carry_no_usage`.

## Lane 3: stable generated names

**What Phase 3 needs from names** (the interface with
`docs/design/workflow_lisp_edit_and_continue_spike.md`, not yet written):

1. Locality: an edit changes the identity of no effect outside the edited
   scope, and inside it only of unnamed effects with the same callee.
2. No silent aliasing: an identity that denotes a different effect after an
   edit has a different input digest. True today: the `declaration` input
   part hashes the whole node.
3. Binders, not only sites: that hash includes operand references by binder
   name, so a renamed upstream binder changes downstream digests.
4. Compiler-made path segments (the `#1 / body` of a join) do not depend on
   whether a sibling arm has effects. False today.
5. The last segment names the callee.

If the spike matches effects by something other than names, C3 is dropped
and C1 and C2 stay for readability. If it needs item 4, C3 covers join
labels too.

### C1: Python binder names from the callee (M)

**Files:** `orchestrator/py/{trace,declarations,imports}.py`,
`docs/design/python_workflow_frontend.md`,
`docs/python_workflow_drafting_guide.md`; create
`tests/test_workflow_python_names.py`; update the tests that pin `_e0` or
`_loop0`.

**Rule:** the first use of a callee (command, prompt, called workflow, or
`when`, `match`, `loop`, `ask`) in a workflow function binds `_<callee>`,
later uses `_<callee>_<k>`; other characters become `_`. Any effect call
accepts `name="x"`, which is the binder; a reused name is refused at its
Python line with `python_binder_name_taken`. No inference from the Python
variable. **Breaks:** no run in flight; rebuilding an unchanged Python
source gives a new program digest once, hence a new run.

- [ ] `test_inserting_a_step_of_another_callee_keeps_later_names`,
      `test_inserting_a_step_of_the_same_callee_moves_only_that_callee`,
      `test_explicit_name_survives_any_insertion`,
      `test_reused_explicit_name_is_refused_at_its_python_line`,
      `test_run_built_before_the_rule_resumes_from_its_snapshot`.
- [ ] End to end: `py build`, `run`, kill, `resume` on
      `workflows/examples/python_command_loop.py`; the terminal lines name
      the callee.

### C2: warn on positional `.orc` sites (S)

**Files:** `orchestrator/workflow_lisp/{lints,compiler}.py` (the
required-lint collector, after site assignment), the frontend
specification's lint list, the drafting guide; create
`tests/test_workflow_lisp_positional_site_warning.py`.

Lint `effect_site_positional`, warn by default and error under strict: a
scope with two or more compiler-numbered effect sites, reported at the
second, naming both and the fix (bind each with `let*`). No digest changes.

- [ ] `test_two_unnamed_effects_in_one_scope_warn_at_both_places`,
      `test_one_unnamed_tail_effect_and_named_effects_do_not_warn`,
      `test_the_warning_changes_no_program_digest`.
- [ ] Record in the ledger how many warnings the catalog and the packaged
      library produce.

### C3: callee-derived `.orc` site labels (M; gated)

Starts only after the spike's finding and decision 4. **Files:**
`orchestrator/contracts/closed_program/{sites,targets}.py`,
`specs/versioning.md`, evaluated design §6. Sketch: an unnamed effect is
`#<callee>`, a repeat `#<callee>#2`, under a new target only. Tests: the
insertion probe keeps the sites of unchanged effects; recorded digests of
programs on older targets do not move; read-back recomputes the labels.

## Lane 4: the Agent Sessions comparison

### D1: kit, no calls (S)

**Files:** create
`experiments/pq1c/{README.md,criterion.json,providers.json,inputs.json,run_cell.sh,readout.py}`
and `tests/test_pq1c_kit.py`, on the pattern of `experiments/authoring_check`
(a slot ledger outside the checkout, so no cell runs twice).

- [ ] The launcher refuses without `PQ1C_SPEND_AUTHORIZED=yes`, and refuses
      any model but `claude-haiku-5-5`, the no-provider stub, a fifth cell
      and a second retry; `readout.py` on stand-in run trees returns each of
      the three outcomes, and an undetermined cost for unknown usage.
- [ ] Rehearse the four cells with stand-ins; record the SHA-256 of
      `criterion.json` in the ledger.

### D2: run it (owner-gated)

Follows the [protocol](#pq-1c-protocol) once T2 and T3 are approved; readout
and owner judgment go in the ledger and the delivery plan's PQ-1c row.

## Headline exit test

`tests/test_phase2_exit_e2e.py::test_parallel_best_of_n_survives_a_kill_and_reports_tokens`,
with the installed CLI as in `tests/test_first_hour_e2e.py`, stand-in
providers that print transport lines with fixed usage, and no model call.

1. Install the A3 copy of best-of-N with four repositories; `run` it under
   `kill_at`; SIGKILL the process group after exactly two implementation
   commits while two are in flight.
2. `orchestrator resume <run id>` exits 0 and prints the expected winner.
   The two committed implementations were dispatched once, the two killed
   ones twice, the judge once.
3. `orchestrator report --run-id <run id> --format json`: each provider
   step's `usage.tokens` equals the sum the stand-in printed for its
   completed attempts; the two killed attempts count as `unknown_attempts`;
   `run.usage` equals the sum over steps, has a `cost_usd` and names the
   price table's source and date. The markdown form shows the total with `≥`.

It fails today at step 3 (no usage is recorded); steps 1 and 2 have never
been run.

## PQ-1c protocol

Governed by `AGENTS.md` "Experiment rules". It reports measure-free figures
only: no judge, no calibration, no claim about "better".

**Cells.** Variant `workflows/examples/design_review_execute_agents.orc` and
baseline `design_review_execute.orc`, sources unchanged, each run clean and
resumed: four cells, one run each. Same task text, a fresh clone of one
small fixture repository per cell (the `design_docs` fixture of
`tests/workflow_evaluated_consumer_sources.py`, not this repository), same
timeouts. A resumed cell is stopped by the wrapper the deterministic
consumer test uses (`STOP_AFTER_RECORD`) right after the reviewer's first
turn settles, then resumed; no paid turn is in flight at the stop.

**Models.** The sources default to `claude-opus-5-5` and `gpt-6.1-sol`,
above the ceiling. Rebind without editing them: the `planner_model` and
`reviewer_model` inputs to `claude-haiku-5-5`, and the `providers.codex`
alias to `claude_unrestricted_workspace`. Every call is then Haiku. The
sources fix `:effort "high"`; whether the CLI accepts it for Haiku is
unverified, and the first turn of the first cell is the check. The axes
below are mechanism facts that do not depend on the model. Lost at Haiku:
the Codex session adapter is not exercised and the reviewer is no longer
another model family.

**Axes**, read by `readout.py` from each run's `memo.jsonl`,
`report --format json` and terminal log:

| Axis | Pass |
| --- | --- |
| Completion | `run.status` is `completed` with four committed typed results |
| No repeated paid work | every turn identity has one `started` row; the resume log has no `effect_rerun` or `agent_bootstrap_restarted` line |
| Usage recorded | every provider attempt's `usage.json` is `reported` |
| Cost | `run.usage.cost_usd`, variant over baseline, per pair |
| Invalidate | on a copy of each clean run, `invalidate <run> <feedback identity>` exits 2 with `invalidate_coordinator_committed` and unchanged bytes for the variant, and exits 0 for the baseline |
| Elapsed time | reported; decides nothing |

**Outcomes**, fixed in `criterion.json` before the first call:

- **Retire:** a variant cell does not complete while its baseline cell does,
  or a committed turn is dispatched again, or the cost ratio is at or above
  1.25 in both pairs.
- **Retain:** all four cells complete, no paid work repeats, and the cost
  ratio is at or below 0.8 in both pairs.
- **Improve:** anything else. Agent Sessions stays opt-in at target 2.38,
  the Python `Agent` item is not opened, and no further spend follows unless
  the consumer thread names a need.

The owner then records the judgment the gate requires: whether what was
observed justifies losing the ability to invalidate feedback.

**One run per cell can decide** completion, repeated dispatch, the
invalidate behavior, whether usage was recorded, and a cost difference
outside the 0.8 to 1.25 band. **It cannot decide** retained context,
document quality, elapsed time, a cost difference inside the band, or how
often a cell fails.

### Budget request

All calls `claude-haiku-5-5`; each run under `--max-cost-usd 2`; no top-up
after a null. Cost basis: today's authoring check (six Haiku sessions, USD
0.07), with a design or execute turn assumed at most ten times one of those
sessions.

| Tranche | Calls | Released by |
| --- | --- | --- |
| T1 best-of-N live smoke (A3) | 5, plus 2 for one retry by `resume` | A3's deterministic tests pass; B2 merged |
| T2 PQ-1c, four cells | 16 | D1 rehearsal passes; B4 merged; criterion hash in the ledger |
| T3 reserved: one infrastructure retry per cell | 4 | a cell stopped by a cause outside the workflow |
| Total | 27 calls, USD 10 | |

## What Phase 2 leaves out

Python `parallel_map` and `Agent` (Phase 4); token columns in the dashboard;
a cap stored in the run or shared across runs; usage for OMP, gateway and
phased providers and for agent CLIs a provider starts itself; matching calls
to the CLIs' session stores; the stderr `tokens used` fallback and per-step
statistics of the backlog item; a global concurrency limit; any quality
claim; any change to the resume refusals (Phase 3); `invalidate` by name.

## Decisions for the coordinator

1. **Where usage lives.** Recommended: `usage.json` in the attempt
   directory, not referenced from the memo. A field on commit and failure
   rows changes a record shape that readers reject when unknown, and puts a
   view into the authority.
2. **Built-in templates switch to structured output.** Recommended: yes; it
   is the only way an ordinary call reports usage. Cost: `stdout.txt` is
   transport JSON. Alternative: separate opt-in metered templates.
3. **Cap with unknown usage.** Recommended: stop (`spend_cap_unmetered`).
   Counting known usage only lets an unmetered step spend without limit.
4. **The `.orc` naming rule.** Recommended: C2 now, C3 on a new target after
   the spike. A new target strands nothing but is a seventh target, against
   Lane D's direction. Changing the rule in place refuses resume
   (`resume_program_changed`) for every unfinished run of a program with an
   unnamed effect or an effectful join, and moves the recorded digests of
   the library and of tests. Lint only keeps `#1` in terminal output and
   leaves interface item 4 unmet. This is also the versioning rule Lane D
   stage 4 was to write.
5. **PQ-1c models.** All Haiku as written, or the reviewer on
   `gpt-5.6-terra` (inside the ceiling, not Haiku) to exercise the Codex
   adapter. Either needs the owner's budget approval.
6. **The A3 live smoke** is the phase's only real-provider evidence for
   parallel working directories and for metering. Drop it and T1 if the
   stand-in evidence is enough.
7. **Smaller choices already taken above:** Python `name=` is a new keyword
   in the authoring API (C1); A4 reruns the compatibility comparison only if
   lane 1 changed production bytes.

## Ledger

| Date | Decision or event | Detail | Spend |
| --- | --- | --- | --- |
| 2026-11-11 | Plan accepted by the coordinator | Lanes 1 to 3 start now (A1, B1, C1 and C2); B4 waits for the dashboard branch, C3 for the Phase 3 spike, lane 4 for B3 | none |
| 2026-11-11 | Ruling, decision 1 | Usage lives in `usage.json` in the attempt directory, not in the memo. Reason: memo rows reject unknown fields and usage is a view, not authority. If wrong: a reader that needs usage without the run tree has no source | none |
| 2026-11-11 | Ruling, decision 2 | Built-in `claude*` and `codex*` templates switch to structured output, provided B2's first test shows a plain call through the transport decoder gives the same result value and terminal text as today. If that test cannot be made to pass, B2 stops and metered templates become opt-in. If wrong: tools that read `stdout.txt` as prose see transport JSON | none |
| 2026-11-11 | Ruling, decision 3 | A cap with an earlier unmetered provider attempt stops with `spend_cap_unmetered`. If wrong: a capped run with a phased or OMP provider step cannot proceed without dropping the cap | none |
| 2026-11-11 | Ruling, decision 4 | C2 now; C3 only on a new target and only if the Phase 3 spike needs names to match effects. The rule is never changed in place | none |
| 2026-11-11 | Ruling, decisions 5 and 6 | PQ-1c and the A3 live smoke are planned all on `claude-haiku-5-5` (owner cost default). Neither runs before the owner approves the tranche; the request (27 calls, USD 10) is put to the owner when A3's deterministic tests and D1's rehearsal pass | none authorized |
| 2026-11-11 | Ruling, decision 7 | Accepted as written: Python `name=` keyword; A4 reruns the compatibility comparison only if lane 1 changed bytes under `orchestrator/` | none |
| 2026-11-11 | C3 dropped | The [Phase 3 spike](../design/workflow_lisp_edit_and_continue_spike.md) found that prefix reuse does not match effects by name, so callee-derived `.orc` site labels are not needed; C1 and C2 stay for readability. No new target is added | none |
