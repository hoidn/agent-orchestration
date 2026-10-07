# Evaluated Execution Phase 3 Size Correction Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. The coordinator owns integration and the single verification window; implementers must not launch competing test campaigns.

**Goal:** Satisfy the Phase 3 Source Map limits with responsibility-based extractions and unchanged runtime behavior, test coverage and diagnostic contracts.

**Architecture:** Keep durable IO and effect dispatch in their current owners. Extract pure header validation, pure memo reduction, and reached-effect input preparation/comparison into three concrete modules; simplify three newly introduced branch-heavy functions and regroup existing test oracles without dropping assertions.

**Tech Stack:** Existing Python, pytest and Radon 6.0.1; no new dependency, framework, configuration, protocol, persisted field or user-facing API.

**Status:** Cuts 1, 2a, 2b, 3C, 3A and 3B are independently reviewed and integrated through `ef689a3982bb6a722926dd4ec35801a5ee14baf6`. Final affected execution passed 2857 cases at `ef689a39`, including the public smoke and recovery subsets. Refreshed old-target audit and qualified real-provider smoke are recorded below; final independent code/evidence review is PASS; final documentation review and delivery remain PENDING; this plan does not close Phase 3 or satisfy delivery. The original design snapshot was documentation `0cef3a4b9b8b87e8a8ff957e5f3fabbeaa9b3050`, code/tests `c5f4011e`, against baseline `71fbbb746de947b712f55b9c149859649b29c345`.

## Authority and boundaries

Start at [docs/index](../index.md). The [Phase 3 plan, Source Map And Ownership](2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md#source-map-and-ownership) requires every new module to have **fewer than 500 physical lines** and every genuinely new function to have **cyclomatic complexity below 12**. Default Radon includes assertions and nested closures. [Task 17](2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md#task-17-phase-wide-compatibility-verification-and-handoff) owns the integrated check. The [accepted design](../design/workflow_lisp_evaluated_execution.md), [state specification](../../specs/state.md#evaluated-execution-persistence-profile-target-235), [IO specification](../../specs/io.md#evaluated-command-and-provider-io-target-235) and [CLI specification](../../specs/cli.md#evaluated-execution-target-235) retain their existing behavior. [Test guidance](../../tests/README.md) governs collection and execution.

This is plan compliance, not a new runtime feature or target selection. Do not redesign validation, change diagnostics or their precedence, alter identity/request/result bytes, adjust old-target admission, remove tests, weaken fault injection, or split existing large legacy owners merely because they are large. Preserve the completed RED full-suite evidence and its separately owned dispositions.

`C` below means the physical, untracked control directory `/home/ollie/Documents/agent-orchestration/.superpowers/sdd/2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan`. The independent census is `C/task-17-phase-code-review-codex.md`, section *Exact new-name complexity census*. It identifies 56 new-name candidates: three genuinely new production functions, seven historical extraction/rename candidates, and 46 test functions. Names alone are not proof of new logic.

`C/CONTINUATION.md`, the Task 13B-I integration entry, historically accepted `test_workflow_evaluated_provider_lifecycle.py` and `test_workflow_evaluated_command_templates.py` at exactly 500 lines, plus two test functions unchanged from that cut's HEAD. That bounded acceptance is retained as history. It does not change the strict whole-phase gate selected for this correction or make functions introduced after `71fbbb74` historical baseline logic.

## Current ownership and selected change

| Current owner | Observed size / issue | Selected boundary |
| --- | --- | --- |
| `orchestrator/workflow/evaluated/authority.py` | 538 lines; pure header validation mixed with retained-FD reading and durable publication | Move only header schema/decoding/shape validation to `run_header.py`; retain filesystem operations, program binding and publication in `authority.py` |
| `orchestrator/workflow/evaluated/memo.py` | 533 lines; pure reduction and journal IO in one owner | Move types, record validation and the one reducer to `memo_reducer.py`; retain locking, read/append/repair/invalidate IO in `memo.py` |
| `orchestrator/workflow/evaluated/runtime.py` | 733 lines; run/resume, input preparation and durable effect lifecycle | Move input preparation, reuse comparison and the two read-only replay-boundary checks to `effect_inputs.py`; retain all writes, dispatch, allocation and settlement in `runtime.py` |
| `evaluated/values.py::_field_descriptor` | CC18 | Separate union-field descriptor selection from record/proven-case selection inside the same file |
| `closed/command_templates.py::elaborate_command_scopes` | CC13 | Extract its existing prerequisite validation as one local helper; keep both elaboration passes and their order |
| `wcc/elaborate.py::_select_elaboration_procedure_edges` | CC12 | Separate the per-site ambiguity/selection decision from traversal; reuse the existing specialization enumeration |

The alternative of moving the entire effect dispatch block would fit the size gate but would relocate append, allocation, performer and settlement hooks used by recovery campaigns. The chosen input-only boundary preserves those hooks and requires fewer dependent edits. Merely deleting blank lines, turning assertions into opaque Boolean aggregates, or changing the measurement would not address ownership and is not accepted.

Expected sizes are approximately 330–380 lines for authority, 190–230 for `run_header`, below 400 for `memo_reducer`, below 200 for memo IO, 460–480 for runtime, and about 300 for `effect_inputs`. These are planning estimates, not verification evidence; the final default measurement must pass without padding tricks. New helpers must also meet CC<12.

**Tradeoffs:** Header and memo behavior will require following one extra module each. Runtime preflight and execution will share module-qualified input helpers, so the few tests spying on those helpers must patch their actual new owner. The design deliberately leaves durable write mechanics and inherited large owners in place; a future change to those responsibilities must still fit their owning module and undergo its own review.

## Cut 1 — Three production complexity corrections

Role: Implementation / bounded production code, then independent Review / code. Exclusive owners are the three production files below; no simultaneous writer may edit them.

- [x] In `orchestrator/workflow/evaluated/values.py`, add `_union_field_descriptor(descriptor, name)` containing the existing union discriminator/common-field branches, and dispatch to it from `_field_descriptor`. Preserve exact enum names (`union_name` for a proven case; `descriptor['name'] + '.variant'` for an ordinary union), common-field equality/count checks, error codes/messages and descriptor values. Keep record/proven-case field lookup in `_field_descriptor`. Reusing `pure_expr._field_type` would change ordinary-union common-field admission, enum naming and error mapping, so do not substitute it.
- [x] In `orchestrator/workflow_lisp/closed/command_templates.py`, move only the existing schema-1/2, closed-program and command-plan prerequisite checks into `_validate_command_scope_inputs(...)`, called before the current first elaboration. Pass the existing values directly; do not add a request object. Preserve check order, messages, the neutral/annotated passes, call preparation/verification and selected roots. The file currently fits just below 500; measure the added helper and keep this concrete extraction below the limit.
- [x] In `orchestrator/workflow_lisp/wcc/elaborate.py`, keep `_site_procedure_specializations` as the enumerator and extract the subsequent ambiguity decision into `_selected_site_specialization(candidates, procedure, *, closed_program)`, returning the selected procedure or `None`. Multiple candidates still defer only for the existing closed WorkflowRef-parameter case; otherwise they raise the same `TypeError`. Zero candidates leave the current edge unchanged; one candidate selects its definition name. Preserve traversal and mutation order.
- [x] Statically compare the before/after branch tables and measure default Radon, including helpers and nested closures. The three named production functions and every new helper must be below 12. Do not claim runtime verification until the coordinator's window.

## Cut 2 — Production responsibility extraction

Role: Implementation / code structure and directly affected test seams. This is a cross-file cut; use one owner at a time and escalate to Sol 6.1 high if the bounded Luna task cannot safely preserve shared seams.

### Header validation

- [x] Create `orchestrator/workflow/evaluated/run_header.py` with `PROFILE`, `SCHEMA_VERSION`, `_HEADER_FIELDS`, `_RESUME_REQUEST_FIELDS`, `RunAuthorityError`, and the existing `_validate_locator`, `_validate_run_ref_root`, `_validate_result_root`, `_validate_json_value`, `_validate_requested_entry`, `validate_resume_request`, `_reject_duplicate_keys`, `_decode_header_json`, `_validate_header_shape`, `_validate_header_metadata`. These are syntactic/structural checks; do not add locator reads or filesystem resolution.
- [x] Import these definitions directly into `authority.py`, preserving the existing imported names used by CLI, readers and run-reference callers. These imports preserve one definition and one exception class; do not add forwarding functions or a second validator. Keep `RunAuthority`, `CommandTransportRequiredError`, `_read_file`, `_read_header_json`, `_read_header`, checked-program/input/interpreter binding, root checks, fsync helpers and all publication/load entry points in `authority.py`. `run_header.py` must never import `authority.py`.
- [x] Preserve exception wrapping and the boundary where header validation precedes artifact/memo reading. Existing IO monkeypatches on `authority._read_header_json`, `_sync_directory` and `run_writer_lock` must still intercept the same operations.

### Memo reduction

- [x] Create `orchestrator/workflow/evaluated/memo_reducer.py` with the constants, `MemoError`, `JournalEntry`, `MemoSnapshot`, pure row-validation helpers, `_Reducer` and `reduce_memo` now preceding `_read_bytes` in `memo.py`. Move their bodies unchanged apart from imports. It has no filesystem, locking, append, repair, view-publication or reconciliation responsibility.
- [x] Keep `_read_bytes`, `read_memo`, `memo_writer_lock`, `_open_append`, `_encode_record`, `_checked_writer_context`, `append_record`, `repair_torn_tail` and `invalidate_suffix` in `memo.py`. Import the types/reducer and only the existing pure helpers these functions need. Preserve existing imported names, including `_DYNAMIC_INDEX` used by views and run-reference launch authority, by direct imports; do not maintain duplicate definitions. Keep the current writer-to-view lazy import and its timing.
- [x] Preserve exact record acceptance/order, error code/message, complete-prefix offsets, torn-tail treatment, retry ordinals, suffix invalidation and checked-authority requirements. All actual IO hooks remain at `memo.py`; do not change their signatures.

### Reached-effect inputs

- [x] Create `orchestrator/workflow/evaluated/effect_inputs.py` with `_PreflightRefusal`, `_EffectInputDiverged`, `_replay_committed_effect`, `_check_resume_boundary`, `_resolve_effect_input`, `_ensure_effect_can_start`, `_resolve_command_input`, `_render_resolved_argv`, `_resolve_command_implementation`, `_check_retry_implementation`, `_reuse_effect_commit`, `_retry_baseline`, `_command_destinations`, `_command_input_parts`, `_changed_evidence` and `_is_destination_overlap`.
- [x] `runtime.py` imports this module and calls `effect_inputs.<name>` at its existing call sites. Module-qualified lookup ensures the same preparation/reuse spy observes both replay and live execution; do not capture moved helpers into aliases that bypass patches. The new module must not import `runtime.py`.
- [x] Keep `execute_pure_run`, `execute_pure_resume`, `_ResumeBoundary`, prefix traversal, halt/terminal handling, `_execute_effect`, `_reuse_reached_commit`, `_start_and_perform_effect`, `_dispatch_command`, `_rehash_command_implementation` and `_fail_started_effect` in runtime. In particular keep `allocate_attempt`, `append_record`, `perform_command`, `perform_provider`, `ProviderExecutor`, settlement/reconciliation and repair lookup sites where they are. `_rehash_command_implementation` may call `effect_inputs._changed_evidence`; it still owns the post-child rehash and its failure mapping.
- [x] Move only tests' preparation/reuse spies to the new owner: `_resolve_effect_input`, `_reuse_effect_commit` and `resolve_provider_input`. Initial known callers are `test_workflow_evaluated_input_document_contracts.py`, `test_workflow_evaluated_command_templates.py` (then command replay), `test_workflow_evaluated_provider_lifecycle.py`, `test_workflow_evaluated_artifacts.py` and `test_workflow_evaluated_resume_retry.py`. Also move both zero-effect guards in `test_workflow_evaluated_views.py` (`_resolve_effect_input` and `_check_resume_boundary`) to `effect_inputs`; keep its `_execute_effect` and child guards at their actual runtime owners. Search all callers again before editing. `ProviderExecutor` guards and `runtime.read_memo` preflight guards remain on runtime. Leave append/allocate/perform/settle hooks in the recovery, run-ref, context, totality and consumer helpers intact.
- [x] Check import direction and compare moved function ASTs modulo import qualification; preserve signatures, diagnostic class identity through one imported definition, operation order, C4's reached-command locality and all bytes entering digests. No new IO happens during replay and no second execution planner is introduced.

## Cut 3 — Test placement and all 46 complexity findings

Role: Revision / tests and concrete oracle helpers, with independent Review / tests. Preserve function names and parameter IDs when moving tests. Do not import test functions into another collected module: import only needed helpers/fixtures. Keep the known helper entry points used by other modules unless their concrete owner is deliberately moved below.

| Existing test module | Initial lines | Responsibility transfer |
| --- | ---: | --- |
| `test_workflow_evaluated_authority.py` | 508 | Move the three interpreter-publication/coverage tests, `_VALID_PIN`, `_write_command_source` and `_checked_command_program` into existing `test_workflow_evaluated_interpreters.py` (169 lines initially). Keep `program` and `_publish` in authority; update `test_workflow_evaluated_command_readiness.py` to import `_checked_command_program` from interpreters and `_publish` from authority |
| `test_workflow_evaluated_command_lifecycle.py` | 500 | Move `test_committed_command_replay_does_not_redispatch_or_revalidate_result_file` and `test_command_dependency_records_only_values_read_by_current_effect` into new `test_workflow_evaluated_command_replay.py`; import `_program`, `_publish`, `_script`, `_InterruptedRun` as needed from their existing lifecycle owner |
| `test_workflow_evaluated_command_templates.py` | 500 | Move `_InterruptedAfterCommit` and `test_committed_must_exist_path_can_be_rendered_after_artifact_disappears` into that same command-replay module. Keep template/transport helpers, including `_write_boundaries`, in their current owner |
| `test_workflow_evaluated_provider_lifecycle.py` | 500 | Move `test_supplied_staged_provider_selection_reaches_real_performer` into existing `test_workflow_evaluated_provider_activation.py` (137 lines initially), importing the concrete lifecycle helpers it already uses |
| `test_workflow_evaluated_resume.py` | 502 | Move `test_malformed_recipe_locators_refuse_at_publication_before_root` and `test_nontransportable_override_refuses_before_creating_any_run_directory` into authority tests. Keep `_snapshot`, `_completed`, `_resume_cli`, and actual resume tests in place |
| `test_workflow_evaluated_values.py` | 534 | Move its final three union-field tests (`test_built_union_variant_field_retains_checked_enum_descriptor`, `test_checked_shared_field_preserves_declared_path_dependencies_without_reads`, `test_pure_ordinary_union_common_field_works_without_shared_evidence`) into existing `test_workflow_evaluated_shared_union.py` (283 lines initially); reuse its ordinary values/constants through explicit imports |
| `test_workflow_lisp_command_control.py` | 702 | Move the lexical-reference/capture group starting at `test_closed_workflow_ref_aliases_remain_compile_time_values` through `test_forwarded_workflow_reference_is_not_a_runtime_command_root`, including `_assert_erased_proc_ref_binders`, into new `test_workflow_lisp_command_captures.py`. Keep the earlier independent control-summary witnesses in control |

Three nearby new modules also need room for their required CC corrections. Move `test_pure_bound_capture_uses_incoming_type_before_same_name_shadow` and `test_retained_capture_reads_original_value_in_actual_lexical_frame` from `test_workflow_lisp_command_scopes.py` (493 lines) into command captures. Move `test_promoted_parent_reuses_runtime_child_shape_with_final_residual_operands` and `test_inline_literal_homonym_inherits_whole_root_while_native_keeps_its_runtime_parameter` from `test_workflow_lisp_closed_command_requests.py` (483) into command captures, retaining their original `_compile` → `build_closed_program` path. **Accepted execution disposition (Cut 3B):** these two tests inspect the built artifact; routing through `_prepared_entry` would prepare twice or lose that oracle. The existing concrete compiler helpers are reused, without a second fixture execution. Move `test_call_preparation_consumes_real_alias_facts_after_operand_normalization` from `test_workflow_lisp_closed_command_transport.py` (497) into the reduced command-control module, importing its existing concrete compiler helpers. Do not duplicate those helpers or move all test setup into a generic support package. Recheck the resulting two new test modules and every affected Phase 3-added module against the strict line limit.

- [x] Address every function in the appendix using cohesive assertion groups or concrete setup/observation helpers within its existing/final owner. Keep each assertion, its evaluation order where side effects matter, each scenario, monkeypatch, timeout and parameter combination. Keep a single execution of each expensive fixture. A helper should express an actual proof such as committed-attempt preservation, typed result/digest agreement, lexical owner continuity or no-publication-on-refusal, rather than an arbitrary chunk of N assertions.
- [x] In the large existing closed-program test owners, revise only the listed functions and their concrete helpers; the 500-line requirement does not authorize splitting entire legacy modules. For nested `record_request`, extract the request-contract assertions into a helper called by the recorder, keeping both caller observations.
- [x] Do not disable Radon's assertion counting, replace explicit checks with opaque `all()` aggregates to lower the number, weaken equality/type/identity assertions, add a test framework, or turn scenarios into a configurable runner. An assertion moved to a helper remains a real assertion and the helper itself must pass default CC.
- [x] Record an old→new collected-node mapping for moved tests and compare parameterized case counts. Because some names are used by retained historical receipts, preserve those receipts and explain the move in the new correction receipt rather than rewriting history.

## Verification and integration order

The coordinator reviews this plan before implementation. Execute sequentially across shared owners; Cuts 1 and 2 may be prepared in parallel in isolated worktrees because their write sets are disjoint, but their tests still share one exclusive window. Cut 3 starts after the affected Cut 2 test seams are integrated. The runtime/input extraction is one exclusive write task. Independent read-only review may overlap. Implementers may prepare static evidence but launch no tests while another coordinator campaign runs.

- [x] Before edits, retain the current source hashes, independent size/CC census and exact legacy-body provenance in `C`. The gate is a red static baseline; this behavior-preserving refactor does not need invented failing behavior tests.
- [x] After the cuts, freeze one candidate, inspect its complete diff, and rerun the static census against `71fbbb74`. Count physical lines in every Phase 3-added module, including newly extracted helpers/tests; use default `radon.complexity.cc_visit` with assertions/closures. Retained tooling is `/tmp/task7a-radon/radon` (6.0.1); record the actual interpreter/tool version and command. Check changed/new functions, not just top-level names, and explicitly account for the seven historical names below. Every genuine new violation must be resolved. Run `git diff --check`.
- [x] Collect all added, moved and otherwise changed test modules before execution, including both new modules and both ends of each move. Compare collection with the retained node mapping; no lost or duplicate parametrized cases. Standard command from the repo root: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest --collect-only -q -p no:cacheprovider <explicit affected modules>`.
- [x] Run narrow owner selectors first: the values/shared-union owners and existing record/proven-case errors; command scopes/control/captures plus closed command requests/transport; authority/interpreters/command-readiness; memo/memo-writes/memo-FD; command replay/lifecycle/templates; provider lifecycle/activation; input-document contracts and resume retry/replay. Record the concrete resolved selector list in the receipt, including every appendix owner whose oracle changed. Do not invent new prompt-text tests.
- [x] Run the frozen affected selection in one tmux window with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest -q -n 16 --dist=worksteal -p no:cacheprovider --basetemp=<fresh short task-owned path> -rfE <explicit affected modules>`. The affected set includes the appendix owners, their moved destinations, authority/memo/retained-FD tests, and the evaluated suites using the moved preparation/reuse seams. Apply the existing scratch-capacity protocol and retain SHA, command, output, exit and failures. Do not run concurrent suites.
- [x] Include real orchestrator integration checks: `tests/test_workflow_evaluated_invalidate_smoke.py` (compile/run/resume/report/invalidate route), `tests/e2e/test_e2e_workflow_evaluated_run_ref.py` (path child), and the existing maintained consumer plus producer→consumer handoff selectors. Keep public fresh-run, refused preflight, committed replay, retry and read-only readers covered. Reuse the final Task 17 smoke window for these obligations when its frozen candidate includes this correction.
- [x] Authority and memo ownership changed, so include existing durability/invalidation/view-failure owners: `tests/test_workflow_evaluated_durability_model.py`, `tests/test_workflow_evaluated_invalidate_windows.py`, `tests/test_workflow_evaluated_recovery_views.py`, and their retained-FD controls. The external-kill test hooks must still target the same operations; rerun the existing affected recovery selection on the corrected candidate rather than claiming an unchanged import graph. Keep 434 kill cells, 11 census tests and the separate combined counts distinct.
- [x] Repeat the relevant old-target comparison on this candidate: shared compiler functions changed and source/package bytes moved, so the earlier audit cannot certify the new tree. Use the existing Task 17 method and its 2.14/2.23/2.33/2.34 specimens, imports and nested capsules; record authentic package-pin changes separately from fixed-identity raw byte equality, plus the old run/resume smoke. No normalization or production-pin patching.
- [x] Keep the earlier completed RED full run and all completed failure dispositions as evidence of their original SHA. The coordinator decides the further affected/full scope under the existing Task 17 rule based on the actual correction diff; this plan grants no waiver and does not claim a new full run. Finish outstanding post-integration provider/reader/handoff smokes on the actual final candidate.
- [x] An independent reviewer checks the source diff, every moved test/oracle, static gate and fresh receipts. The coordinator integrates only after that review, updates the Phase 3 Source Map paths with the three concrete owners, and records test moves in the closeout receipt. Do not mark Task 17 or Phase 3 complete merely because the size correction passed.

## Recorded Execution, 2026-10-07

The [closeout report](../reports/2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md#corrective-cuts-and-final-candidate-evidence) indexes the implementation/review receipt digests. Cut 1 (`36645e15`) has 8 narrow passes; Cut 2a (`a9535680`) 105; Cut 2b (`b55db232`) 18 plus 4 final view-guard cases. Cut 3C (`5692f430`, 17 listed functions) has independent Astra review, 34 passes and the same 307 ordered node IDs. Cut 3A (`89023914`, 15 functions) has 46 passes and a bijective 294-case mapping with 28 relocated nodes. Cut 3B (`ef689a39`, 14 functions) has 67 passes and a bijective 333-case mapping with 24 relocated nodes; the earlier missing-helper-import failure and intermediate attempts remain retained, with final corrected evidence separate. These results are not summed into a suite total.

The final qualified-AST-name census against `71fbbb74` (`C/evidence-17-size-correction/new-function-cc-final.json`, Python 3.13.9, Radon 6.0.1) includes default assertions and nested closures: no new-module line violations, no test-function CC violations, and only the seven historical production names with provenance below remain at CC ≥12. Embedded runner strings are not measured by this census; it is not a universal behavior proof or a waiver of function limits. Every genuinely new finding in the correction inventory has a bounded source/oracle review; the independent final code/evidence review now passes at `ef689a39` (`C/task-17-final-code-evidence-review.md`), preserving the original source-review scope and separately reviewed embedded-runner metrics rather than claiming census coverage of strings.

The 95-owner final selection at `ef689a39` collected 2857 cases, exit 0, and passed all 2857 with zero failures/errors/skips, exit 0 (665.09 s pytest / 665.44 s wall); all 507 production-file hashes match preflight. The 12 public smoke cases and 472-case recovery selection pass within that total, including 434 external-kill cells and 11 census cases, not additional runs. Evidence: `C/task-17-final-affected-report.md` and `C/evidence-17-final-affected/receipt.json`. A setup-only exit 3 before workers/tests (missing basetemp parent) is retained as `C/evidence-17-final-affected/setup-attempt0.*` and `setup-disposition.json`; the same code/selection/16 workers were relaunched after creating that parent. The refreshed audit at `ef689a39` records 88/88 raw public pairs, 55/67 authentic-pin capsule pairs (12 pin/derived-identity differences, exit 1), separate fixed-identity 67/67 equality (exit 0) and old run/resume 0/0 without redispatch. `C/task-17-final-old-target-audit-report.md` retains the manifest hashes and raw evidence. The separate configured-provider run completed READY after two external refusals (coder attempt 3, reviewer attempt 1); no deliberate exit-75 interruption occurred, and the completion transition changed 11 files. Two actual completed replays subsequently exited 0/0 without changing 29 files or appending memo/attempts (`C/task-17-final-live-report.md`). These qualified results do not replace the affected campaign’s committed-boundary evidence. Independent Astra final code/evidence review is PASS; final documentation review and delivery remain PENDING. Completed execution/source-review steps above are checked; Task 17 and Phase 3 closure remain open. The Source Map already routes to `run_header.py`, `memo_reducer.py` and `effect_inputs.py`; no persistence format, effect admission or old-target route has changed.

## Historical complexity: seven names retained, no general exception

The Task 6 result-byte review and root inspection accepted AST-identical historical validation suffixes; Task 10A explicitly accepted renamed legacy bodies; Task 10C and Task 11 reader reviews preserve unchanged legacy projections/classification. Confirm the exact old/new body mapping against the candidate; retain the finding if it no longer matches. This is evidence that the logic predates Phase 3, not a claim that its measured CC is below 12.

| Existing owner and extracted/renamed function | CC | Provenance |
| --- | ---: | --- |
| `contracts/output_contract.py::_validate_output_bundle_document_bytes` | 17 | `C/task-6-result-bytes-quality-review.md` and root inspection: original record-validation suffix from `fields` |
| `contracts/output_contract.py::_validate_variant_output_bundle_document_bytes` | 48 | Same receipts: original variant-validation suffix from `discriminant` |
| `state.py::RunState._legacy_dict` | 15 | `C/task-10a-renderer-seam-acceptance.json` and v3 reviews: renamed `to_dict` body |
| `state.py::RunState._from_legacy_dict` | 15 | Same receipts: renamed `from_dict` body |
| `observability/report.py::_render_legacy_status_markdown` | 49 | Same receipts: renamed renderer body |
| `dashboard/projection.py::RunProjector._project_legacy_detail` | 19 | `C/task-10c-quality-review.md` and conformity review: renamed projector body |
| `monitor/classifier.py::_classify_legacy_run` | 16 | Reader extraction provenance and original/candidate AST comparison, retained by the independent Task 17 reviewer |

Paths in this table are relative to `orchestrator/`. No listed historical body is an edit target for this correction.

## Appendix: 46 test functions to correct

The exact names and initial default CC below are the independent census snapshot. File paths are relative to `tests/`; destination changes above do not remove the CC obligation. All helpers created while correcting these functions are also measured.

| Module | Function | Initial CC |
| --- | --- | ---: |
| `test_workflow_evaluated_call_lineage.py` | `test_imported_effect_uses_producer_configuration_on_name_conflicts` | 17 |
| `test_workflow_evaluated_calls.py` | `test_imported_boundary_call_projects_cached_values_and_native_result` | 15 |
| `test_workflow_evaluated_cli.py` | `test_public_run_dispatches_command_once_and_commits_typed_result` | 19 |
| `test_workflow_evaluated_cli.py` | `test_public_run_skips_c4_for_an_unreached_command_branch` | 13 |
| `test_workflow_evaluated_cli.py` | `test_public_run_preserves_an_earlier_commit_on_later_local_c4_refusal` | 23 |
| `test_workflow_evaluated_cli.py` | `test_command_template_loop_index_reaches_each_attempt_argv` | 16 |
| `test_workflow_evaluated_command_lifecycle.py` | `test_pending_start_retry_with_unchanged_closure_runs_next_ordinal_once` | 15 |
| `test_workflow_evaluated_command_lifecycle.py` | `test_invalidation_releases_only_the_invalidated_commit_closure_baseline` | 12 |
| `test_workflow_evaluated_command_lifecycle.py` | `test_closure_change_or_appearance_during_child_fails_the_started_ordinal` | 18 |
| `test_workflow_evaluated_command_templates.py` | `test_committed_must_exist_path_can_be_rendered_after_artifact_disappears` | 17 |
| `test_workflow_evaluated_control.py` | `test_selected_select_prefix_uses_the_machine_binding_callback` | 15 |
| `test_workflow_evaluated_loops.py` | `test_loop_continue_done_and_parser_ordered_seed_budget` | 12 |
| `test_workflow_evaluated_phase_context.py` | `test_fixed_phase_target_values_match_legacy_after_readback` | 12 |
| `test_workflow_evaluated_providers.py` | `_assert_prepare_parity` | 12 |
| `test_workflow_evaluated_reserved.py` | `test_both_prompt_callers_supply_complete_requests_at_target_227.record_request` | 14 |
| `test_workflow_lisp_closed_command_requests.py` | `test_promoted_parent_reuses_runtime_child_shape_with_final_residual_operands` | 12 |
| `test_workflow_lisp_closed_command_requests.py` | `test_inline_literal_homonym_inherits_whole_root_while_native_keeps_its_runtime_parameter` | 15 |
| `test_workflow_lisp_closed_command_requests.py` | `test_workflow_diamond_prepares_each_owner_once_and_retains_each_edge` | 12 |
| `test_workflow_lisp_closed_command_transport.py` | `test_nested_loop_index_names_survive_actual_state_binder_hygiene` | 16 |
| `test_workflow_lisp_closed_command_transport.py` | `test_call_preparation_consumes_real_alias_facts_after_operand_normalization` | 13 |
| `test_workflow_lisp_closed_program_artifact.py` | `_projected_k6_negative_target` | 17 |
| `test_workflow_lisp_closed_program_build.py` | `test_three_static_call_sites_retain_exact_value_keys_and_three_frames` | 12 |
| `test_workflow_lisp_closed_program_build.py` | `_assert_shared_ref_static_variants` | 17 |
| `test_workflow_lisp_closed_program_build.py` | `_assert_created_ref_variants` | 18 |
| `test_workflow_lisp_closed_program_build.py` | `test_source_owned_command_rows_preserve_native_projection_and_dynamic_suffix` | 13 |
| `test_workflow_lisp_closed_program_build.py` | `test_reference_and_command_captures_keep_their_distinct_binding_owners` | 16 |
| `test_workflow_lisp_closed_program_build.py` | `_assert_opaque_body_continuity` | 12 |
| `test_workflow_lisp_closed_program_build.py` | `_assert_runtime_proof_frames` | 12 |
| `test_workflow_lisp_closed_program_build.py` | `test_constructor_alias_memo_retains_nested_tags_and_original_shadowed_fact` | 22 |
| `test_workflow_lisp_closed_program_build.py` | `test_partial_union_constructor_labels_get_projected_keys_while_preserving_runtime_input` | 25 |
| `test_workflow_lisp_closed_program_build.py` | `_assert_partial_command` | 12 |
| `test_workflow_lisp_closed_program_build.py` | `_assert_shadow_constructor_operands` | 12 |
| `test_workflow_lisp_closed_program_corpus.py` | `test_phase_reference_variants_keep_their_exact_call_owners` | 15 |
| `test_workflow_lisp_closed_program_effects.py` | `test_projected_union_tag_finalizes_its_phantom_run_ref_owner` | 17 |
| `test_workflow_lisp_closed_program_effects.py` | `_reject_forged_projected_run_ref_tag` | 12 |
| `test_workflow_lisp_closed_program_effects.py` | `test_repeated_mixed_reference_calls_keep_both_original_materialized_bindings` | 18 |
| `test_workflow_lisp_closed_program_frontend.py` | `test_mixed_schema_capsule_pairs_each_original_snapshot_after_relocation` | 30 |
| `test_workflow_lisp_command_control.py` | `test_imported_helper_reads_its_original_snapshot_alias_view` | 23 |
| `test_workflow_lisp_command_control.py` | `test_forwarded_workflow_reference_is_not_a_runtime_command_root` | 12 |
| `test_workflow_lisp_command_scopes.py` | `test_surface_arm_certificate_keeps_variant_roots_and_neutral_body` | 14 |
| `test_workflow_lisp_command_scopes.py` | `test_pure_bound_capture_uses_incoming_type_before_same_name_shadow` | 12 |
| `test_workflow_lisp_command_scopes.py` | `test_hygiene_scopes_variant_roots_and_preserves_source_formal` | 13 |
| `test_workflow_lisp_command_scopes.py` | `test_distinct_caller_values_leave_neutral_elaboration_untouched` | 16 |
| `test_workflow_lisp_command_scopes.py` | `test_retained_capture_reads_original_value_in_actual_lexical_frame` | 13 |
| `test_workflow_lisp_target_evaluated_execution.py` | `test_public_run_235_dispatches_commands_and_commits_dependency_chain` | 13 |
| `test_workflow_pure_catalog_agreement.py` | `test_closed_value_evaluator_matches_catalog_for_generated_applications` | 14 |
