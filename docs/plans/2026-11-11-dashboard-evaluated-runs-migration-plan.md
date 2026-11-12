# Dashboard And `report`: Evaluated Runs Only

**Status: Plan, executed 2026-11-12.** This page plans the migration the owner chose on 2026-11-11
([roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed),
decision 4 and Lane D stage 3): the dashboard and `report` stop reading runs of
the retired runtime, and the dashboard reads evaluated runs. It is a plan, not
a contract, and nothing in it is copy-safe guidance. Behavior is owned by the
[CLI spec](../../specs/cli.md), [observability](../../specs/observability.md)
and [security](../../specs/security.md); the view both tools render is owned
by `orchestrator/workflow/evaluated/views.py`. Until the tasks land, both
tools behave as those specs say today. No provider spend. The plan stops
before the old IR stack is deleted and lists what it leaves for that stage.

## What Is True Today

Checked against the code and three provider-free probes on 2026-11-11 (a
completed command run, a parallel map with a failing item, a run killed and
resumed).

- The dashboard already reads evaluated runs: `RunScanner` calls
  `load_evaluated_view`, `RunProjector._project_evaluated_detail` builds the
  page model and `ExecutionCursorProjector._project_evaluated` the cursor.
  `server.py` has no evaluated branch because it renders that model with the
  pages built for old runs. "The dashboard reads only the old bundles" is
  wrong for `/runs`, the run page, the effect page and file previews, and
  right for the rest of `server.py`. 36 collected tests cover the path
  (`tests/test_workflow_evaluated_dashboard.py`, `..._dashboard_previews.py`).
- For an evaluated run the Summary Hub, `summaries/live.json` and the tmux
  page show nothing: no production code writes `summaries/index.json` or
  `monitor_process.json` (`SummaryObserver`, `LiveAgentNoteObserver` and
  `write_process_metadata` have no caller in `orchestrator/`).
- `report` has a complete evaluated path (`_report_evaluated`,
  `report_snapshot`) beside a state-only path for old runs.

## Views

| View | Today for an evaluated run | After |
| --- | --- | --- |
| Run list with status, workflow, start, update, cursor, failure text | Exists. Six columns are always empty or duplicate (persisted status, elapsed, current-step start, state mtime, heartbeat, availability) | Kept; the empty columns go; elapsed comes from `started_at` and `updated_at` |
| One run's effects in memo order with status and class | Exists | Kept |
| Attempt number and timing per effect | Not rendered: attempt shows only in the file path, duration only on the effect page, start and completion nowhere | **New (small):** attempt, start, completion and duration on the run page and the effect page, from the view row |
| Where stdout, stderr, prompt and result live | Exists for `command` and `provider`, from a class table in `_evaluated_file_refs`. Other classes (`agent_turn`, phased providers, `run_ref`) get `result` only, although `agent_turn` attempts write `stdout.txt` | **New (small):** link every regular file in the attempt directory through the same resolver; the class table goes |
| Inputs and outputs | Exists | Kept |
| Pending host-input request (question, answer type, deadline, shown evidence) | Exists, tested | Kept |
| Parallel-map items | Exist as ordinary rows whose identity carries the item index (`par-map:<binder>[i]`); not tested through the dashboard | Kept; one test added; no grouping |
| The failing effect and its error | Partly: run error on the run page, effect error on the effect page, failure text in the list; the run page does not point at the failed effect | **New (small):** the run page links each failed effect with its error code |
| Effect to artifacts with safe preview | Exists (escaped preview, size cap, raw download as attachment) | Kept unchanged |
| Derived `state.json` preview, copyable `report` and `resume` commands, `refresh=` | Exist | Kept |
| Summary Hub, live panel, provider-flow diagram, workflow-structure panel, tmux page, observability-file groups, common artifacts, finalization, artifact lineage, call-frame cursor, visit count, debug and provider-session blocks | Empty or absent | **Dropped**, with the routes `/summaries`, `/summaries/live.json` and `/tmux` |

Both tools keep one projection, `load_evaluated_view`. `report_snapshot` stays
the `report` adapter; the dashboard keeps reading the view rows and gains no
second projection. Token and cost display is a later item that needs the
metering of roadmap Phase 2. Not changed here: an effect in flight when its
writer died still shows `running` under a run status of `interrupted` (the
shared view's row status).

## What A Retired Run Shows Afterwards

A run directory with a `state.json` entry and no evaluated authority is a
retired run. Neither tool opens its `state.json`.

- `report --run-id <id>`: exit 2, empty stdout, one stderr line:
  `Error: workflow_execution_profile_retired: run <id> was written by the
  retired runtime; report and the dashboard read evaluated runs only (old
  readers: git tag <tag>)`. Without `--run-id`, `report` picks the latest
  evaluated run and ignores retired ones.
- Dashboard: the run stays in the list with status `retired` and that line as
  its failure text; its run page shows the line and nothing from the old
  state; every route below it returns 404 with the line.

## What Is Deleted

Production code, about 11,000 lines (`wc -l` and an AST import scan of
`orchestrator/`; partial files are estimates):

| Path | Lines now | After | What goes |
| --- | --- | --- | --- |
| `orchestrator/dashboard/server.py` | 3,891 | about 750, then split | `_ProviderFlowBuilder`; the `_summary_*`, `_tmux_*`, `_workflow_*`, `_provider_flow_*`, live-note and context-label methods (86 methods, 2,547 lines); the legacy sections of `_run_detail`, `_runs_index`, `_step_detail` |
| `orchestrator/dashboard/projection.py` | 808 | about 130 | `_project_legacy_detail` except its unreadable-row branch, `_load_workflow`, both `_steps_from_*`, artifact lineage, observability files, availability and heartbeat helpers |
| `orchestrator/dashboard/cursor.py` | 229 | about 60 | call-frame, loop and finalization cursor |
| `orchestrator/dashboard/scanner.py` | 171 | about 95 | `_read_legacy_run` |
| `orchestrator/dashboard/models.py` | 158 | about 130 | fields only the old pages read; the bundle and surface-graph imports |
| `orchestrator/dashboard/compiled_workflow.py` | 431 | 0 | whole module |
| `orchestrator/cli/commands/report.py` | 322 | about 70 | `_state_only_snapshot`, `_state_only_step_kind`, `_legacy_report_snapshot` |
| `orchestrator/observability/report.py` | 830 | about 70 | all but `render_status_markdown`, `_render_evaluated_status_markdown` and their two helpers |
| `orchestrator/runtime_observability.py` | 363 | 0 | whole module (only the old report imports it) |
| `orchestrator/workflow/judgment_views.py` | 1,816 | 0 | whole module |
| `orchestrator/workflow/prompt_context_report.py` | 585 | 0 | whole module |
| `orchestrator/workflow/prompt_attempt_result_binding.py` | 422 | 0 | whole module (only `judgment_views` imports it) |
| `orchestrator/workflow/persisted_surface.py` | 2,034 | 0 | whole module; its last importers are the modules above |
| `orchestrator/workflow/prompt_identity.py` | 2,224 | about 1,950 | the comparison and v1 validation only the old report used: `compare_prompt_attempt_history`, `compare_prompt_attempt_records`, `PromptComparisonRecord`, `validate_prompt_attempt_identity`, `ROLE_CLASSIFICATIONS` and private helpers nothing else uses |

Tests: about 285 collected items deleted and about 23 re-based on evaluated
fixtures (`pytest --collect-only`, 2026-11-11; the removal plan's "about 220"
was an estimate whose per-group record was not kept):

| Test file (items) | Action |
| --- | --- |
| `test_dashboard_compiled_workflow.py` (38), `test_dashboard_projection.py` (10), `test_dashboard_cursor.py` (4), `test_observability_report.py` (10), `test_prompt_context_report.py` (21), `test_workflow_judgment_views.py` (37), `test_workflow_judgment_result_contracts.py` (24), `test_workflow_lisp_judgment_views_e2e.py` (0), `test_prompt_attempt_result_binding.py` (5), `test_persisted_workflow_surface.py` (15), `test_workflow_shared_validation.py` (1), `test_workflow_trial_observability.py` (8) | Delete the files: 173 items, 4,914 lines |
| `test_dashboard_server.py` (57) | Delete about 42 (Summary Hub, live notes, tmux, structure, lineage, legacy links); re-base about 15 route and security tests |
| `test_cli_report_command.py` (15) | Keep the parser test; re-base 4 (Markdown, latest run, JSON, `--output`); delete 10 |
| `test_dashboard_scanner.py` (8) | Keep 3 workspace tests; delete 5 legacy-state tests |
| `test_dashboard_commands.py` (4) | Re-base on `RunRecord` values built directly |
| `test_cli_dashboard_command.py` (6) | Delete the 3 persisted-surface cases |
| `test_runtime_observability.py` (5) | Delete the 3 `compute_active_runtime` tests; the 2 state round-trip tests stay |
| `test_workflow_lisp_build_artifacts.py` (29) | Delete the 17 persisted-surface decoder cases |
| `test_prompt_identity.py` (89), `test_provider_phased_delivery_identity.py` (28) | Delete the tests of the removed comparison and v1 validation (about 27 and 4) |
| `test_workflow_lisp_transportable_value.py` (33), `test_yaml_frontend_retirement.py` (8) | Delete 1; replace 2 with refusal assertions |

Fixtures deleted with them: `tests/fixtures/historical_observability_bundles.py`
(2,491 lines, the last constructor of `LoadedWorkflowBundle`), the four
`tests/fixtures/historical_*.json` files (judgment contract, judgment view,
prompt identity, trial observability), `historical_readers.md`, and
`tests/fixtures/workflow_lisp/judgment_views/review_revise_design_docs_judgment_panel_case.json`
(the two `.orc` files beside it stay; a list-traversal test uses them).

## What This Leaves For The IR-Stack Deletion

After this plan, live code outside the stack still imports these names:

| Stack module | Names | Live importers |
| --- | --- | --- |
| `workflow/loaded_bundle.py` | `LoadedWorkflowBundle` (annotations), `WorkflowBoundaryProjectionView`, `workflow_boundary_projection`, `workflow_input_contracts`, `workflow_output_contracts`, `workflow_public_input_contracts` | `workflow_lisp/compiler.py`, `workflows.py`, `workflow_refs.py`, `closed/frontend.py` |
| `workflow/surface_ast.py` | `SurfaceContract`, `SurfaceStepKind`, `SurfaceStep`, `PrivateExecContextBinding` | `workflow_lisp/contracts.py`, `typed_prompt_inputs.py`, `build_manifest_io.py`, `phase_family_boundary.py` |
| `workflow/executable_ir.py` | `RunRefStepConfig`, `StepCommonConfig`, `ManagedJobsConfig`, `ExecutableContract` | `workflow/evaluated/run_ref.py`, `workflow/run_ref/{runtime,child,path_compile}.py`, `managed_jobs/runtime.py`, `workflow/signatures.py` |
| `workflow/statements.py` | the branch, match and finally token helpers | `workflow/identity.py`, whose `STEP_ID_PATTERN` `provider_attempts.py` imports |

`WorkflowProvenance` leaves the live list (its importer is deleted here). The
stack modules stay: `surface_ast`, `core_ast`, `semantic_ir`, `executable_ir`,
`runtime_plan`, `state_projection`, `loaded_bundle`, `statements`,
`runtime_step`, `provider_context`, and `elaboration` and `linting`, which
already have no importer. Also left, because the decision names only the
dashboard and `report`: the monitor's flat-route classification,
`StateManager` loading of old state, `input get` on old runs, the summary and
live-note observers with their CLI flags (Lane D stage 2), the builders in
`prompt_identity.py`, and about 570 lines of `prompt_dependency_evidence.py`
the same scan finds unreachable.

## Security

The dashboard serves files. `orchestrator/dashboard/files.py` and `preview.py`
do not change, and the dashboard rules in `specs/security.md` stay as written.
These tests prove them:

- `tests/test_dashboard_files.py` (6) and `tests/test_dashboard_preview.py`
  (5): traversal, paths outside the roots, symlink escape, escaping, size cap,
  binary files, inert raw-download headers. Unchanged.
- `tests/test_workflow_evaluated_dashboard_previews.py`:
  `test_attempt_file_routes_reject_symlink_escape_and_traversal`,
  `test_actual_stream_preview_escapes_limits_and_raw_download`; and in
  `tests/test_workflow_evaluated_dashboard.py`,
  `test_scanner_confines_root_before_authority_detector` and the view-hint
  tests (regular file only, no symlink follow, FIFO deadline). Unchanged.
- Re-based in `tests/test_dashboard_server.py` (Task 1): the route checks of
  security headers, escaping on the list, effect and preview pages (workspace
  and run scope, Markdown), preview caps, raw download as attachment,
  traversal refusal, `refresh=`, and a `state.json` symlink leaving the
  workspace (400, no outside bytes).

Listing the attempt directory (Task 2) adds links, not a new way to serve
files: each link goes through `FileReferenceResolver.run_ref`.

## Global Constraints

- Smallest change that works: the server shrinks by deletion; no rewrite, no
  new frontend, no second projection, no feature outside the view table.
- New or substantially changed code: modules at most 500 lines, functions at
  most cyclomatic complexity 12 (Task 6 brings `server.py` under both).
- Tests assert behavior through `DashboardApp.handle` or the CLI on real
  evaluated runs; no mocks of the runtime; no assertions on prompt text.
- Verify with narrow selectors first, then
  `pytest -q -n 16 --dist=worksteal --sample 10`, and the full suite (the same
  command without `--sample`, in tmux) before merging; `pytest --collect-only`
  on each test module added or renamed; `PYTHONPATH` set to the working tree.
- Separate worktree; pathspec commits (`git commit -- <paths>`); no assistant
  attribution in commit messages.
- No commit leaves a failing test: each task deletes or re-bases the tests of
  the code it removes and lists each removed test with the code it covered.
  If a deletion target has a caller the scan missed, stop and record it in the
  ledger instead of adding a shim.

## Tasks

Sizes are engineer-days. Order: 0; 1 and 2 in parallel; 3; then 4, 6 and 7 in
parallel; 5 after 4; 8 last.

**Task 0: Tag and baseline (0.25).** Create the annotated tag
`archive/retired-run-readers-<date>` on the last commit that still reads old
runs; record it and the suite baseline in the ledger. No file changes.

**Task 1: Evaluated fixtures under the route and security tests (1.5).**
Files: `tests/test_dashboard_server.py`, `tests/test_dashboard_commands.py`,
`tests/test_cli_report_command.py`. Before: these tests build old `state.json`
runs. After: the tests marked re-based above run on evaluated runs from
`_pure_run` (`tests/test_workflow_evaluated_readers.py`) and `_completed_run`
(`tests/test_workflow_evaluated_invalidate.py`), keep their names and
assertions (status code, headers, escaped body, no outside bytes, unchanged
tree) and pass on current code. Legacy-only tests wait for Task 3.

**Task 2: Attempt, timing, attempt files, failed-effect links, end-to-end
check (2).** Files: `orchestrator/dashboard/models.py` (`DashboardStep` gains
`attempt`, `started_at`, `completed_at`), `projection.py` (`_evaluated_step`,
`_evaluated_file_refs`), `server.py` (`_run_detail`, `_step_detail`), and the
two evaluated dashboard test files. Before and after: the view table. Tests,
in `tests/test_workflow_evaluated_dashboard.py` (the fourth in the previews
file):

| Test | Asserts |
| --- | --- |
| `test_run_page_shows_attempt_and_timing_per_effect` | After an invalidate and resume the run page shows attempts 1, 2, 2; each row's start, completion and duration equal `report --format json` |
| `test_run_page_links_failed_effect_with_error_code` | A command exiting 3 gives a run page whose failed-effect link opens the effect page showing `command_exit_nonzero` and exit code 3 |
| `test_parallel_map_items_are_rows_with_item_index` | A three-item map with one failing item gives rows with indices 0 to 2, two completed and one failed, each linking its own attempt directory |
| `test_attempt_directory_files_are_linked_for_every_class` | A provider attempt and an agent-turn attempt (existing shim fixtures) link every regular file in the attempt directory; a planted symlink out of the workspace is not linked and warns |

End-to-end, `test_dashboard_handlers_follow_real_run_through_kill_and_resume`:
a two-command workflow whose second command waits for a `release` file,
started with `python -m orchestrator run` in its own process group. While it
waits: the list says `running`; the run page shows the first effect completed
at attempt 1 with a stdout preview containing its output, the second running
at attempt 1, outputs null. After `SIGKILL` of the group: `interrupted`,
cursor on the second effect, the `resume` command text present. After creating
`release` and `orchestrate resume <id>`: `completed`, the workflow output on
the page, the second effect completed at attempt 2 with links under
`attempt-2/`, the first still at attempt 1 and dispatched once. Reads leave
the run tree byte-identical at each point.

**Task 3: Refuse retired runs in the dashboard and delete its old pages (2).**
Files: `orchestrator/workflow/evaluated/views.py` (the one refusal line),
`orchestrator/dashboard/{scanner,projection,cursor,models,server}.py`, and the
dashboard rows of the test table. Before: an old run renders state-only pages.
After: the refusal above; `/summaries`, `/summaries/live.json` and `/tmux`
return 404 for every run; no dashboard module imports `loaded_bundle`,
`persisted_surface`, `surface_ast`, `compiled_workflow` or
`observability.report`. Tests: `test_removed_routes_return_404` and
`test_dashboard_lists_retired_run_as_one_line_refusal` (one evaluated run
beside a directory holding only an old `state.json` with a marker string: both
are listed; the retired row and page carry
`workflow_execution_profile_retired`; the marker appears nowhere; `/state`,
`/steps/x` and `/files/run/state.json` return 404; the tree is unchanged).

**Task 4: Refuse retired runs in `report` (0.5).** Files:
`orchestrator/cli/commands/report.py`, `tests/test_cli_report_command.py`,
`tests/test_yaml_frontend_retirement.py`. Tests:
`test_report_refuses_retired_run_with_one_line` (exit 2, empty stdout, one
stderr line with the code and run id, tree unchanged) and
`test_report_latest_skips_retired_runs`.

**Task 5: Delete the modules with no caller left (1.5).** The whole modules
and the rest of `observability/report.py` from the production table, their
tests and fixtures, then the `prompt_identity.py` definitions. Delete a
definition only when a scan of `orchestrator/`, `experiments/` and `scripts/`
(including `importlib` use) finds no importer; keep what a remaining
phased-delivery test needs as input. Proof: the remaining suite passes.

**Task 6: Bring `server.py` under the limits (0.5).** Move the file and
`state.json` preview routes with the Markdown renderer to
`orchestrator/dashboard/file_pages.py`, and split the run page into section
functions. Moves only; the existing tests are the proof.

**Task 8: Final verification (0.5).** Add
`test_dashboard_and_report_do_not_load_the_bundle_stack`: a subprocess imports
`orchestrator.dashboard.server` and `orchestrator.cli.commands.report` and
finds none of `loaded_bundle`, `core_ast`, `semantic_ir`, `runtime_plan`,
`state_projection` in `sys.modules` (`surface_ast` and `executable_ir` still
load through the evaluated runtime until the next stage). Then the full suite
and one smoke: run a command-only catalog example, start
`orchestrator dashboard`, fetch `/runs` and the run page with `curl`. Record
removed tests, line counts and results in the ledger.

Total: about 10 engineer-days; two calendar weeks with review.

## Task 7: Specs And Documents To Update (1)

- `specs/cli.md`: the sentence that `report` and the dashboard read retained
  evidence of historical runs (keep `input get`); the `dashboard` entry (what
  it scans, the routes without the three removed, the retired row); the trial
  paragraph on state-only trial rows; the evaluated "Readers" bullet (attempt,
  timing, attempt-directory files); the error-table row for
  `workflow_execution_profile_retired` (add `report`, exit 2).
- `specs/observability.md`: the "Status/report surfaces" bullets on legacy-run
  projection, report self-heal, summary pages and the live endpoint; the
  trial section's sentence on the state-only report; the "Workflow Lisp
  Judgment Views" section becomes a short historical notice naming the tag.
- `specs/state.md`: the sentence on historical report and dashboard readers.
  `specs/security.md`: no change.
- `docs/capability_status_matrix.md`: add a row for the dashboard and `report`
  (implemented for evaluated runs; retired runs refused); correct the rows for
  evaluated execution (derived readers), canonical trial runs (state-only
  trial rows withdrawn), judgment views Q4 (read-only views removed) and
  prompt identity diagnostics Q3 (the report's comparison projection existed
  only on the old path).
- `docs/design/dashboard_observability_summary_gui.md`: status Historical with
  a scope notice, body preserved. `dashboard_summary_invocation_tabs.md`:
  Retired. `observability_step_visit_summaries.md` and
  `workflow_lisp_judgment_views.md`: scope notices. `docs/design/README.md`:
  the three dashboard and summary rows.
- `docs/index.md` (the "Inspect or monitor a run" row, the clarification on
  historical readers, the dashboard design row, a row for this plan);
  `docs/workflow_monitoring.md`, `docs/runtime_execution_lifecycle.md`,
  `README.md` and `tests/README.md` where they mention historical readers; one
  roadmap ledger line that stage 3 is unblocked.

## What This Makes Harder

Runs written by the retired runtime can no longer be inspected with `report`
or the dashboard: no state-only report, Summary Hub, judgment views or
prompt-context comparison. The run directories are not touched. Fallback: the
tag from Task 0, which the refusal line names. Check it out in a worktree and
run the old readers from there:
`git worktree add ../orc-retired-readers <tag>`, then
`PYTHONPATH=../orc-retired-readers python -m orchestrator report --run-id <id> --runs-root <path>`
(or `dashboard --workspace <root>`). No compatibility reader stays in the tree.

## Not Verified

- Which files an `agent_turn` or phased-provider attempt directory holds; only
  the `stdout.txt` read in `agent_turns.py` was seen. Task 2 settles it.
- The `prompt_identity.py` list is from a static scan; its tests import the
  module through `importlib`, so Task 5 re-checks each name. Test counts are
  collected items classified by name and import.
- Whether any evaluated consumer of prompt-identity comparison exists (the
  scan found none, against the matrix row's "admitted evaluated forms"), and
  whether route-readiness registry rows cite a test file deleted here.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-11 | Plan accepted by the coordinator. Rulings on its open choices: `report` on a retired run exits 2 with `workflow_execution_profile_retired`; retired runs stay listed in the dashboard with status `retired`; `persisted_surface.py` is deleted here; `prompt_identity.py` is pruned conservatively. The Summary Hub, live panel, provider-flow and structure panels, tmux page and lineage views are dropped: nothing writes their inputs for evaluated runs. |
| 2026-11-11 | Tasks 0 to 2 done on `feat/dashboard-migration` (local tag `archive/retired-run-readers-2026-11-11` on `d469e391`; `c256ac1c`, `8984db2b`) and reviewed: approve with fixes. The re-based security tests are as strong as before and the new figures equal `report --format json`. Findings being fixed before the deletions: a file named `..txt` in an attempt directory crashed every route; a file name that is not valid UTF-8 crashed the run page; the attempt listing was recursive, unbounded and ran on every request. A dashboard-route test is added for symlinked authority files pointing outside the workspace, which the reviewer verified are refused. |
| 2026-11-11 | Coordinator ruling: an agent turn's `receipt.json` and `stdout.txt` are not linked from the run or effect pages (native session locator, process group id, raw provider stream). They stay reachable through the file route by typed path; for a local read-only tool that is accepted, not refused. Not addressed here and left for later: the server does not check the `Host` header. |
| 2026-11-12 | Tasks 3 to 8 done, reviewed twice more and merged as `2eaf80c5` (with `main`'s other merges: 77 files, 25,538 lines deleted, 1,932 added). The dashboard lists a retired run as `retired` and refuses its pages; `report` on one exits 2 with one line; `orchestrator/dashboard/server.py` went from 3,898 to 330 lines. Review fixes: a file named `..txt` and non-UTF-8 names no longer break routes; the attempt-file listing is top-level, regular files only, at most 50; the dashboard refuses any `Host` other than a loopback name or the bound host with the bound port (421), which closes a DNS-rebinding read that existed before this plan; monitor emails for a retired run show the refusal. Full suite on the branch with `main` merged: 14,209 passed; one failure beyond the four worktree-artifact ones was a test helper the branch had deleted while another module still imported it, restored in `c1b7a64e`. Kept against the plan because they have live callers: `cursor.py`, `validate_prompt_attempt_identity`. Known and left: with two `Host` headers the first wins; an email for a run whose directory has vanished calls it retired; the tag `archive/retired-run-readers-2026-11-11` that refusals name is local only, since nothing is pushed. |
