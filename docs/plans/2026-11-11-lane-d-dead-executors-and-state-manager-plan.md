# Lane D Stages 1 And 2: Dead Executors, `StateManager` Methods And CLI Vestiges

**Status: Plan, accepted 2026-11-11.** This page plans stages 1 and 2 of [Lane
D](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed)
(owner decision 4, approved 2026-11-11): delete the trial, adjudication, provider-peer-group and
provider-supervision executors with their commands, source forms, specs and tests, then the
`StateManager` methods and CLI parts that nothing calls. It is a plan, not a contract, and not
copy-safe guidance. Behavior is owned by `specs/` (chiefly [cli](../../specs/cli.md),
[dsl](../../specs/dsl.md), [state](../../specs/state.md)) and by [evaluated
execution](../design/workflow_lisp_evaluated_execution.md); until the tasks land, those documents
describe the checkout. No provider spend.

Not planned here: the dashboard, `report` and the readers of retired runs ([dashboard
plan](2026-11-11-dashboard-evaluated-runs-migration-plan.md), in execution on
`feat/dashboard-migration`; its files are off limits); the old IR stack as a whole (stage 3);
targets (stage 4); `prompt run` and `prompt import`.

## What Is True Today

Checked at `60f8b13d` (after today's removal of 3,134 tests) with an AST import scan of every
tracked `.py` file, `git grep`, `pytest --collect-only` (15,554 items) and CLI probes.

| Package | Lines | Importers outside itself | What they import |
| --- | ---: | --- | --- |
| `orchestrator/workflow/trial/` (10 files) | 8,343 | `workflow/{core_ast,executable_ir,surface_ast,semantic_ir,runtime_plan}.py`; `workflow/persisted_surface.py` (the dashboard plan deletes it); `tests/test_workflow_lisp_source_floor.py`; `experiments/evaluated_execution_spike/{closed_effects,trial}.py`; untracked `scripts/experiments/es/prompt_authority.py` | `TrialStaticConfig`, `validate_trial_static_config_authority`; the encoder and decoder only in `persisted_surface` |
| `orchestrator/workflow/adjudication/` (10 files) | 2,818 | `trial/ledger.py`, `trial/packets.py`; one frozen hidden test under `experiments/compare/tasks/resume-projection-integrity/`, which runs against its own base commit | score ledger, evaluator parsing |
| `orchestrator/workflow/provider_peer_group/` (7 files) | 5,704 | `cli/commands/peer.py`; `workflow/executable_ir.py`; `tests/test_workflow_lisp_cli.py`; `tests/e2e/test_e2e_provider_peer_delivery.py` | protocol calls and receipts; `PeerGroupPathPlan`, `derive_provider_peer_group_paths`; two model classes in the e2e test |
| `orchestrator/workflow/provider_supervision/` (7 files) | 3,076 | `workflow/executable_ir.py` (11 names); `provider_peer_group/bindings.py` | contracts, directive constants, models, paths |

Total 19,941 lines. No live name has to move: nothing reachable from `run`, `resume`, `invalidate`,
`compile`, `py`, `repl`, the LSP or `workflow/evaluated/` imports these packages,
`orchestrator/workflow_lisp/` does not import them, and nothing outside the IR stack, tests
included, constructs the stack's types for these three kinds. **Commands:** `trial`
(`cli/commands/trial.py`, 12 lines) prints `[workflow_execution_target_retired]` and exits 2; the
four `peer-*` commands (`cli/commands/peer.py`, 72 lines) still call the peer protocol and exit 2
without an active binding; all five are hidden from help.

**Source forms.** The frontend parses, type-checks and elaborates all three; the closed build then
refuses them (`[closed_program_gap] … has no closed form in this release`), only where the selected
entry reaches the form. The closed checker, the Python frontend, the LSP, the route-readiness
registry, the verification manifest and `README.md` do not name them.

| Form (effect atom) | Mentions in `workflow_lisp/` | Files | Estimated lines |
| --- | ---: | --- | ---: |
| `trial` (`runs-trial`) | about 480 | 19; two whole: `typecheck_trial.py` (230), `trial_result_contract.py` (584) | 2,200 |
| `with-live-providers` (`live-supervision`) | about 230 | 22 | 2,300 for both |
| `with-live-provider-peers` (`live-peer-messaging`) | about 205 | 23 | |

**Tracked `.orc` files that use a removed form: six, none admitted.**

| File | Target | Today | Afterwards |
| --- | --- | --- | --- |
| `workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc` | 2.25 | Refused at the header (`workflow_execution_target_retired`); pinned by the corpus test | Unchanged; kept as text |
| `tests/fixtures/workflow_lisp/current_effect_gaps/with-live-providers/provider_supervision_continue.orc`, `…/with-live-provider-peers/provider_peer_group_three.orc` | 2.35 | `closed_program_gap` | Deleted with their two test cases |
| `tests/fixtures/workflow_lisp/provider_supervision/` (5 files, 31 lines, one `.orc`) | 2.16 | No test reads it | Deleted |
| `tests/fixtures/workflow_lisp/provider_peer_group/` (13 files, 293 lines, two `.orc`) | 2.35, 2.17 | One parametrized case in `tests/test_workflow_lisp_source_read_trace.py` | Deleted with that case |

Other `.orc` matches for `trial` (`experiments/adversarial_daq/`, `experiments/mlevolve_pair/`,
`tests/fixtures/workflow_lisp/mlevolve_pair_legacy/`) are a `let*` name or a record field, not the
form, and must behave as today.

**`StateManager`** (`orchestrator/state.py`, 1,664 lines; 59 methods). Production constructs it
once, in `cli/commands/evaluated.py::run_evaluated_workflow`, for `run_id`, `run_root`, `workspace`
and `close()`; `workflow/provider_attempts.py` calls `_state_mutation()`. Of the other 55 methods,
47 have no caller in `orchestrator/` or `tests/` and 8 are called only by retained tests.

## Scope After Owner Decision 9

The owner keeps live supervision and peer groups as a future direction
([roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#owner-decisions),
decision 9). The [ledger](#ledger) has the rulings. Read the rest of this page
with these changes:

- **Task 5 is on hold.** The forms `with-live-providers` and
  `with-live-provider-peers` keep their parser, checker and elaboration and
  keep refusing with `closed_program_gap`. Only `trial` becomes a retired form
  (Task 4), so `RETIRED_FORMS` has one row.
- **Task 6** keeps the spec and guide sections of the two forms. It shortens
  only what describes the deleted executors and the `peer-*` commands, and
  points the two forms' status at the
  [salvage record](../design/live_provider_supervision_and_peers_salvage.md).
- **Tasks 1 and 2 stand:** the old executor packages are deleted; a port
  would not reuse them.
- **D4 is "keep":** the flags that do nothing stay parsed, so Task 6 removes no
  flag lines from `specs/cli.md`; it rewords the lines that still describe
  processed-directory checks and state backups as accepted with no effect.
- **Task 7 correction:** `ForEachState` stays, because `RunState` uses it.

## What A User Sees Afterwards

**Forms (D1, recommended): one retirement line.** Without it a removed form gets
`[procedure_call_unknown] unknown same-file procedure callee`, which reads as a typo. The addition
is a table in `form_registry.py`,
`RETIRED_FORMS = {"trial": "blinded trials", "with-live-providers": "live provider supervision", "with-live-provider-peers": "provider peer groups"}`,
and one check in `expressions.py::_elaborate_list`, where a list head is resolved (the reader only
tokenizes): after the checks that let a user's own procedure, function or bound name shadow the
head. Exit 2 with:

```text
main.orc:7:5: [form_retired] `with-live-providers` was removed: live provider supervision
is retired; the last version with it is git tag archive/dead-executors-2026-11-11
```

Intended differences from today: the refusal comes from elaboration, so it holds at every target and
for a definition the entry never reaches, and the code is `form_retired`, not `closed_program_gap`.
The three effect atoms get the existing unknown-effect error; no tracked source declares them.
**Commands:** `orchestrator trial …` and `orchestrator peer-*` get argparse's `invalid choice` (exit
2, nothing read or written); they were hidden, and `peer-*` was only called by a provider inside a
group. **Tests of today's refusals:** the three forms' cases leave the two located-gap tests (the
other cases stay), and Task 4 adds a test of the new line.

## Compatibility Of What Stays

- **Digests.** No admitted program's digest may change. Task 0 records `program.digest`, or the
  refusal code, for every row of `tests.workflow_lisp_closed_program_corpus.corpus()` through
  `try_build` (55 rows, 11 built; two runs gave identical files); Tasks 4, 5 and 9 must reproduce
  the file. The risk is Task 5: every body passes through `close_wcc_provider_supervision_members`.
- **Runs on disk.** Task 0 kills a run made with the old code; Task 9 resumes and reports it with
  the new code (resume recompiles and compares digests).
- **Names that stay.** The prelude union `ProviderSteeringDirective` and its reserved name (D7; a
  typed-import check compares type environments); run-ref error codes beginning `trial_` (a live
  feature; 27 mentions under `workflow/run_ref/`); the two implicit-empty reasons in
  `workflow/prompt_dependency_contract.py`.
- **Frozen experiment files.** Nothing under `experiments/` or `workflows/experiments/` changes
  except one README line (D8).

## How The Import Edges Are Cut

Order follows the edges, so it differs a little from "packages, forms, CLI": `peer.py` leaves with
the peer package it imports; the peer package imports supervision and leaves first; adjudication
leaves with trial, its only importer. The forms have no edge to the packages and run in parallel. In
the IR stack, delete what handles the three step kinds and nothing else (about 960 lines in six
modules, named in Tasks 1 to 3). `SurfaceStep` keeps its two untyped provider fields and the kind
enums keep their string members; neither needs an import. No type moves; no stub.
`workflow/elaboration.py` and `linting.py` have no importer and are not edited. The trial edge also
runs through `workflow/persisted_surface.py`, which the dashboard plan's Task 5 deletes; Task 3
waits for it (D2).

## Global Constraints

- Deletion only; the one addition is the retired-form table and its check. No refactor beyond
  cutting an import edge.
- Delete a definition only when a scan of `orchestrator/`, `tests/`, `scripts/` and non-frozen
  `experiments/`, `importlib` strings included, finds no reference left. If a missed caller appears,
  stop and record it; no shim.
- Tests assert behavior. Never weaken a test to make it pass: a test goes only with the code it
  covered, and the ledger lists both.
- Pathspec commits (`git commit -- <paths>`); no assistant attribution; no `--no-verify`. Separate
  worktrees; `PYTHONPATH` set to the working tree; long runs in tmux, started from an existing
  session.
- Off limits: the dashboard plan's files, including `tests/test_cli_report_command.py`,
  `tests/test_workflow_trial_observability.py` and `orchestrator/cli/commands/report.py`.
- **Gate, for every commit:** no test outside the four worktree-artifact ids of the [test
  baseline](../reports/2026-11-11-test-baseline.md) fails (a load-sensitive id is rerun alone
  first). During work: the task's narrow run, then `pytest -q -n 16 --dist=worksteal --sample 10`;
  before each merge to `main`, the same without `--sample`. `pytest --collect-only` on each test
  module added or edited.
- "IR tests":
  `$(git grep -lE "workflow\.(executable_ir|runtime_plan|core_ast|semantic_ir|surface_ast|runtime_step)\b" -- tests)`
  (14 modules). "Document tests": `$(git grep -lE "docs/|specs/" -- 'tests/*.py')` (76).

## Tasks

Sizes are engineer-days. Task 0 first. Worktree A: 1, 2, 7, 8, and 3 when unblocked. Worktree B: 4,
then 5. Worktree C drafts 6. A and B share no file. Code and Task 6 merge together, so specs and
code agree on `main`. Task 9 last.

### Task 0: Tag, baseline, digests, killed run (0.25)

- [ ] Create the local annotated tag `archive/dead-executors-2026-11-11` on the `main` commit the
      work starts from; do not push it. Record the suite result at that commit and the digest file's
      SHA-256.
- [ ] In a scratch workspace start the two-command pipeline of `docs/tutorial_first_pipeline.md`
      with a second command that waits for a file; kill the process group; keep the workspace for
      Task 9.

### Task 1: Peer commands, peer package, peer kind (1.5)

Delete `orchestrator/workflow/provider_peer_group/` and `orchestrator/cli/commands/peer.py`.

| Edit | Remove |
| --- | --- |
| `orchestrator/cli/main.py`, `cli/commands/__init__.py` | Four parsers, four dispatch branches; four exported names and the `peer_` rule in `__getattr__` |
| `orchestrator/workflow/executable_ir.py` | The two imports; `ProviderPeerGroupMemberConfig`, `ProviderPeerGroupMemberSourceOwnership`, `ProviderPeerGroupSourceOwnership`, `ProviderPeerGroupStepConfig`, `provider_peer_group_config_to_runtime_dict`, `_validate_provider_peer_group_step_config`, its branch in `_validate_node_shape`, `PROVIDER_PEER_GROUP_SCHEMA_VERSION` |
| `orchestrator/workflow/core_ast.py` | `CoreProviderPeerGroupStep`, `_provider_peer_group_to_json`, the branches in `_build_statement`, `_surface_step_from_core_statement`, `_statement_to_json` |
| `orchestrator/workflow/runtime_plan.py`, `runtime_step.py`, `semantic_ir.py` | `RuntimeProviderPeerGroupPlan`, `_derive_provider_peer_group_plan` and their uses; two key branches; one import |
| `orchestrator/workflow/provider_attempts.py` | `derive_provider_peer_group_member_scope` |
| `tests/test_workflow_lisp_cli.py`, `tests/test_cli_defaults_and_help.py` | The four peer tests (10 items); the `peer-*` entries |
| `tests/e2e/test_e2e_provider_peer_delivery.py` | The import of two peer model classes and the lines that build and assert on them; every assertion on the adapter stays |

- [ ] Add `tests/test_retired_executors_removed.py`, parametrized, with the peer rows:
      `test_removed_packages_are_absent` (`importlib.util.find_spec` returns `None`),
      `test_nothing_imports_removed_packages` (AST scan of `orchestrator/` and `tests/`),
      `test_removed_commands_are_refused` (subprocess: exit 2, `invalid choice`, workspace
      unchanged).
- [ ] Narrow run: the new module, the two CLI test modules, the IR tests.

### Task 2: Supervision package, supervision kind (1)

Delete `orchestrator/workflow/provider_supervision/`,
`orchestrator/workflow/legacy_provider_quarantine.py` (45 lines) and
`tests/test_workflow_lisp_provider_supervision_e2e.py` (167 lines, no test); neither file has an
importer.

| Edit | Remove |
| --- | --- |
| `orchestrator/workflow/executable_ir.py` | The eleven imports; `ProviderSupervisionMemberConfig`, `ProviderSupervisionStepConfig`, `provider_supervision_config_to_runtime_dict`, `_validate_provider_supervision_step_config`, its branch in `_validate_node_shape`, `PROVIDER_SUPERVISION_SCHEMA_VERSION` |
| `orchestrator/workflow/core_ast.py`, `runtime_plan.py`, `runtime_step.py`, `semantic_ir.py` | `CoreProviderSupervisionStep` and its three branches; `RuntimeProviderSupervisionPlan`, `_derive_provider_supervision_plan` and their uses; two key branches; one import |
| `orchestrator/providers/executor.py` | `_provider_supervision_worker_pre_execution_failure` and its call in `execute` |
| `orchestrator/workflow/provider_attempts.py` | `derive_provider_attempt_member_turn_scope`, only if the scan finds no caller but its own test in `tests/test_provider_attempt_allocation.py`; then that test goes too |
| `tests/test_provider_interactive_terminal.py` | The entry naming the deleted package in one forbidden-module list |

- [ ] Add the supervision rows to the new test module. Narrow run: that module,
      `tests/test_provider_execution.py`, `tests/test_provider_attempt_allocation.py`, the IR tests.

### Task 3: Trial command, trial and adjudication packages, trial kind (1.5)

Starts when `orchestrator/workflow/persisted_surface.py` is gone from `main`. Delete
`orchestrator/workflow/trial/`, `orchestrator/workflow/adjudication/` and
`orchestrator/cli/commands/trial.py`.

| Edit | Remove |
| --- | --- |
| `orchestrator/cli/main.py` | `trial_parser` and its dispatch branch |
| `orchestrator/workflow/surface_ast.py` | The import; `TrialSurfaceStep`; the `trial` field and its checks in `SurfaceStep.__post_init__` and `SurfaceWorkflow.__post_init__` |
| `orchestrator/workflow/core_ast.py` | The import; `CoreTrialStep`; the branches in `validate_core_workflow_ast`, `_build_statement`, `_surface_step_from_core_statement`, `_statement_to_json` |
| `orchestrator/workflow/executable_ir.py` | The import; `_serialize_trial_static_config`, `TrialArmStepConfig`, `TrialStepConfig`, `derive_unbound_trial_step_config`, `_validate_trial_step_config`, the branches in `_validate_node_shape` and `_validate_ir_payload` |
| `orchestrator/workflow/runtime_plan.py`, `runtime_step.py`, `semantic_ir.py` | The imports; `_derive_trial_config_digest`, `_derive_trial_result_contract_digest` and their uses in `RuntimePlanNode`, `validate_workflow_runtime_plan`, `_runtime_plan_node`; two key branches |
| `tests/test_workflow_lisp_source_floor.py`, `tests/test_cli_defaults_and_help.py` | The `trial_config` import and the one assertion on its default target; the `trial` entries |
| `tests/test_executor_retirement_cutoff.py` | `test_trial_cli_refuses_before_source_reads_or_publication` (the `trial` row of the new command test replaces it); the `find_spec("…trial.sdk")` line, which raises once the parent package is gone |

- [ ] Add the trial and adjudication rows to the new test module, and one line to
      `experiments/evaluated_execution_spike/README.md`: two of its files import a removed package;
      see the tag (D8).
- [ ] Narrow run: the new module, the three edited test modules, the IR tests.

### Task 4: Retired-form table; remove the `trial` form (2)

Delete `orchestrator/workflow_lisp/typecheck_trial.py` and `trial_result_contract.py`. Production
edits are under `orchestrator/workflow_lisp/`.

| Edit | Remove |
| --- | --- |
| `form_registry.py` | The `trial` spec. Add `RETIRED_FORMS` with the `trial` row |
| `expressions.py` | `TrialArm`, `TrialCheck`, `TrialEvaluation`, `TrialBudget`, `TrialExpr`; `parse_trial_expression`; `_route_trial` and its route row; `trial` in the target-gated head set of `_elaborate_list`; `_trial_fail` through `_trial_number`; `_parse_trial_evaluation`; `_parse_trial_budget`; `_parse_trial_syntax_list`. Add the retired-form check |
| `effects.py` | `RunsTrialEffect`; `runs-trial` in `_parse_effect_group`, `render_effect_atom`, `effect_summary_contains_runs_ref` |
| `typecheck_dispatch.py`, `typecheck_context.py`, `typecheck_run_ref.py`, `typecheck_structural_values.py` | The branch in `_typecheck`; the trial half of `effect_summary_requires_run_ref_placement_refusal` and `raise_run_ref_placement_invalid`; the atom in the effect tuples; the check in `_check_map_effect_body` |
| `functions.py`, `conditionals.py`, `expression_traversal.py`, `contracts.py`, `workflows.py` | Trial branches in `_validate_pure_function_expr`, `_find_purity_violation`, `normalize_resolved_inline_procedure_calls`; `_normalize_trial` and its table rows; the case in `iter_child_exprs`; the trial contract in `derive_workflow_signature_contracts` and `typecheck_workflow_definitions` |
| `wcc/model.py`, `wcc/elaborate.py`, `wcc/hygiene.py` | `WccTrialArmPayload`, `WccTrialPayload`; trial branches in `_elaborate_effect_expr_to_binding_value`, `_infer_expr_type`, `_prebind_effect_argument_matches`, `_substitute_wcc_payload`, `_elaborate_let_star`, `_elaborate_expr_to_body`, `_elaborate_workflow_call_binding_value`; two table rows |
| `closed/build.py`, `closed/effects.py` | The `TrialExpr` branch of `Builder._selected_callable_gap`; the `trial` row in `require_closed_perform` |
| Tests, deleted with the code | The `trial` cases of the two located-gap tests in `tests/test_workflow_lisp_closed_program_effects.py`; `test_closed_ordinary_positions_still_refuse_trial` (2 items); the `trial` parameter of `test_omitted_child_work_wrapper_cannot_enter_pure_function` (2); the `trial` case in `tests/test_workflow_lisp_run_ref_workflow_program.py`; `TrialExpr` in the traversal list of `tests/test_workflow_lisp_expressions.py`; `_trial_source`, `_run_ref` and the commit constants in `tests/test_workflow_lisp_trial.py` (its one test, 2 items, is about `Value` signatures and stays) |

- [ ] First add to `tests/test_retired_executors_removed.py`
      `test_retired_form_refuses_with_located_retirement_diagnostic[trial]` (code `form_retired`,
      span on the form's line, the tag in the message; at targets 2.35 and 2.40; also when the entry
      does not reach the form) and `test_user_definition_named_like_a_retired_form_still_compiles`
      (a `defproc trial` is called and the run completes). See them fail.
- [ ] Repeat the digest snapshot: identical to Task 0's, including the rows of the files that bind a
      name `trial`. Narrow run:
      `tests/test_workflow_lisp_{closed_program_*,effect_ceilings,expressions,run_ref*}.py`,
      `tests/test_first_hour_e2e.py`.

### Task 5: Remove `with-live-providers` and `with-live-provider-peers` (2.5)

**On hold** (see [Scope After Owner Decision 9](#scope-after-owner-decision-9)). Not to be executed without a new owner decision.

Production edits are under `orchestrator/workflow_lisp/`.

| Edit | Remove |
| --- | --- |
| `form_registry.py`, `syntax.py`, `__init__.py` | The two specs (add their two `RETIRED_FORMS` rows); `MAX_STATIC_LIVE_PROVIDER_PEERS`; the exports |
| `expressions.py` | `LiveProviderBinding`, `WithLiveProvidersExpr`, `LiveProviderPeerBinding`, `WithLiveProviderPeersExpr`, `_elaborate_with_live_providers`, `_elaborate_with_live_provider_peers`, two route rows |
| `typecheck_effects.py`, `effects.py` | `typecheck_with_live_providers_expr`, `typecheck_with_live_provider_peers_expr`, `_validated_live_provider_peer_bindings`, `_validated_live_provider_roles`, `_reject_provider_context_capture_in_group`; `LiveSupervisionEffect`, `LivePeerMessagingEffect` and their rendering |
| `macros.py`, `conditionals.py` | `_hygienic_with_live_providers`, `_hygienic_with_live_provider_peers`, two branches in `_apply_hygiene`; `_normalize_live_provider_owner`, `_normalize_with_live_providers`, `_normalize_with_live_provider_peers` and their table rows |
| `functions.py`, `procedure_typecheck.py`, `expression_traversal.py`, `typecheck_dispatch.py`, `typecheck_run_ref.py` | The two cases in `_normalize_expr`, `normalize_resolved_inline_procedure_calls`, `_find_purity_violation`, `_expr_returns_local_proc_value`, `iter_child_exprs`, `_typecheck`; the two atoms in `_PROVIDER_ATOMS` |
| `wcc/model.py`, `wcc/anf.py`, `wcc/hygiene.py`, `wcc/use_site_scope.py` | `WccProviderSupervisionMember`, `WccProviderSupervision`, `WccProviderPeerGroupMember`, `WccProviderPeerGroup`; their cases |
| `wcc/analysis.py` | `validate_wcc_provider_supervision`, `validate_wcc_provider_peer_group`, the two member validators, `_validate_wcc_provider_region_member`, the two settlement validators, `_nonidentity_supervisor_projection_metadata`, `_raise_member_ineligible`, `_raise_supervision_diagnostic`, `_raise_peer_group_diagnostic`; branches in `_effect_boundary_step_kind`, `analyze_wcc_body`, `_iter_specialized_loop_effect_values` |
| `wcc/elaborate.py` | `close_wcc_provider_supervision_members` and its call in `elaborate_typed_workflow_body`, `close_wcc_provider_peer_group_members`, `_close_provider_groups_in_body`, `_close_provider_supervision`, `_close_provider_peer_group`, `_inline_provider_region_member`, `_inline_linear_provider_region`, `_inline_provider_procedure_call` and the helpers only it calls, `_raise_provider_member_ineligible`, `_provider_region_role`, `_elaborate_live_provider_supervision`, `_elaborate_live_provider_peer_group` |
| `closed/build.py`, `closed/preparation_check.py`, `closed/command_templates.py`, `closed/effects.py` | The two branches of `Builder._binding_impl`; the two checks in `assert_closed_preparation`; two table rows; two map rows |
| Tests and fixtures, deleted with the code | `test_public_provider_member_refusals_preserve_order_and_provenance` (8 items) and `tests/fixtures/workflow_lisp/closed_program/provider_member_diagnostics.json` (578 lines); the two form rows of `test_each_selected_effect_outside_the_release_is_a_located_gap` and their fixture directories; `tests/test_workflow_lisp_provider_peer_group.py`; `test_stage3_live_provider_boundary_placement_rejected`; `test_run_ref_is_rejected_from_live_provider_evaluation_and_settlement` (4 items) with `_provider_steering_directive_type`; `test_live_provider_scope_is_refused_before_any_effect`; the `provider-peer-group` case of `test_default_wcc_nominal_lowering_reads_join_the_active_trace`; the three classes in the traversal list; `tests/fixtures/workflow_lisp/provider_peer_group/` and `provider_supervision/` |

- [ ] Add the two form rows to the retirement test; see them fail first.
- [ ] Repeat the digest snapshot. If it differs from Task 0's, stop: the closing pass was not an
      identity on some admitted body. Narrow run: `tests/test_workflow_lisp_*.py` (in tmux),
      `tests/test_workflow_evaluated_resume_kills.py`, `tests/test_first_hour_e2e.py`.

### Task 6: Specs and documents (1.5)

A removed section becomes at most three lines: what was removed, when, and the tag. Design documents
keep their body under a scope notice (D6).

| Document | Change |
| --- | --- |
| `specs/dsl.md` | The `trial` block with its refusal codes; the form list |
| `specs/providers.md`, `specs/io.md` | The supervision, peer-group, adjudicated-delivery and trial-evaluator bullets; the supervision and peer-group IO bullets and "Adjudicated Provider IO" |
| `specs/state.md` | "Target 2.25 Trial State…", "Provider-Supervision State…", "Provider-Peer-Group State…", "Adjudicated Provider State" |
| `specs/observability.md`, `specs/versioning.md`, `specs/index.md`, `specs/security.md` | "Target 2.25 Trial Observability" (one sentence there is also the dashboard plan's; coordinate); the v2.16, v2.17 and v2.25 entries and table rows; the three forms, three design links and two concurrency sentences; the adjudicated child-workspace bullet |
| `specs/cli.md` | "Workflow Lisp trials (target 2.25)"; the five commands in the hidden list; the trial clause of the `workflow_execution_target_retired` row; a new `form_retired` row; after Task 8, the flag lines it removes |
| `docs/design/workflow_lisp_evaluated_execution.md`, `docs/design/workflow_lisp_frontend_specification.md` | The list of classes outside the release, the two "Later" rows, the error table; the two elaboration anchors and bullets |
| `docs/design/workflow_lisp_provider_live_binding.md`, `workflow_lisp_provider_peer_messaging.md`, `workflow_lisp_trial_runs.md`, `docs/design/README.md` | Status Retired with a notice naming the tag; for trial runs, a notice on the `trial` and SDK parts only (run-ref stays current); three index rows |
| `docs/capability_status_matrix.md` | The trial-runs, `with-live-providers` and peer-messaging rows: Retired, code removed, `form_retired`, the tag |
| `docs/lisp_workflow_drafting_guide.md`, `docs/workflow_monitoring.md`, `tests/README.md` | Sections 8A and 8B and three sentences; the sentences naming the features |
| `docs/index.md`, the roadmap's "Routing and records" | A row for this plan; one line |

- [ ] Make the edits (about 840 lines of spec text go); the route-readiness registry needs no
      change. Run the document tests.

### Task 7: `StateManager` methods with no caller (1)

Files: `orchestrator/state.py`, `orchestrator/cli/commands/evaluated.py`. Delete these 47 methods,
about 990 lines:

| Group | Methods |
| --- | --- |
| Provider sessions and recovery | `publish_provider_session_link`, `provider_session_paths`, `provider_session_visit_dir`, `initialize_provider_session_visit`, `update_provider_session_metadata`, `recover_interrupted_provider_visit` |
| Step and loop mutation | `update_step`, `update_loop_step`, `clear_loop_step`, `update_loop_results`, `update_for_each`, `update_repeat_until_state`, `update_dataflow_state`, `finalize_step_with_dataflow`, `finalize_loop_step_with_dataflow`, `_mutate_scoped_state`, `start_step`, `heartbeat_step`, `clear_current_step`, `mark_current_step_recovery`, `get_step_result` |
| Run-level updates | `fail_run`, `_record_atomic_root_failure`, `record_resume_projection_integrity_failure`, `record_workflow_checksum_mismatch`, `record_resume_diagnostic`, `update_call_frame`, `update_workflow_outputs`, `update_bound_inputs`, `update_finalization_state`, `update_run_error`, `update_control_flow_counters`, `update_status`, `bind_run_ref_root` |
| Checksums, backup, repair | `_calculate_checksum`, `calculate_checksum`, `validate_checksum`, `backup_state`, `_rotate_backups`, `attempt_repair` |
| Paths and sidecars | `logical_run_root`, `_write_json_atomic`, `read_runtime_sidecar_json`, `write_runtime_sidecar_json`, `workflow_lisp_checkpoint_shadow_report_path`, `workflow_lisp_checkpoint_restore_report_path`, `workflow_lisp_checkpoint_default_resume_report_path` |

Kept (12): `__init__`, `_generate_run_id`, `close`, `_state_mutation` (production); `load`,
`_read_state_from_disk`, `io_run_root`, `_retain_run_root_fd`, `new_run_id`, `_write_state`,
`allocate_provider_attempt`, `state_transaction` (retained tests). The class stays (D5): the live
path needs only a run id and a run root, but 26 test constructions use it, 17 of them to check
through `.load()` that a run's derived `state.json` parses.

- [ ] Re-run the caller scan at the task's base; the table is the expected result. Delete the
      methods, then what they leave unreferenced (`_apply_result_with_dataflow`, `ForEachState`,
      imports; `ruff check --select F401,F841 orchestrator/state.py`).
- [ ] Remove `backup_enabled`, `debug`, `backup_count` and `max_backups` from `__init__`, and the
      two arguments passed in `evaluated.py`. No test is deleted. Narrow run: `tests/` modules
      `test_state_manager`, `test_workflow_evaluated_{views,readers,dashboard}`,
      `test_cli_{human_input,prompt_run_seam}`, `test_provider_attempt_allocation`,
      `test_workflow_lisp_prompt_calculus_runtime`.

### Task 8: CLI vestiges (1)

| Where (`orchestrator/cli/`) | Vestige | Tests |
| --- | --- | --- |
| `commands/run.py` 105–163 | `build_observability_config`: no caller | None |
| `commands/run.py` 166–204 | `parse_context`: no production caller | 5 in `tests/test_cli_safety.py` |
| `commands/run.py` 237–341 | `validate_clean_processed`, `clean_processed_directory`, `validate_archive_destination`, `archive_processed_directory`: no production caller | 10 in `tests/test_cli_safety.py` |
| `commands/run.py` 351–354, 384, 385, 406 | `run_workflow`: four parameters no caller passes (`no_tools_conf_root`, `no_tools_conf_identity`, `no_tools_conf_manifest_sha256`, `profile_conf_fd`); unused locals `state_dir_override`, `selected_target`; the name `run_ref_root` is unused but its call validates, so the call stays. Then the imports `shutil`, `zipfile`, `DEFAULT_SUMMARY_TIMEOUT_SEC` | `tests/test_cli_run_ref_root.py` still passes |
| `commands/resume.py` 53–75 | `resume_workflow`: 17 ignored parameters (`repair`, `on_error`, `max_retries`, `retry_delay_ms`, `backup_state`, `debug`, `stream_output`, five `summary_*`, five `live_agent_note*`) | None |
| `recovery.py` 81–82 | `_file_names`: no caller | None |
| `main.py`: `HIDDEN_RUN_FLAGS` and their `add_argument` calls (D4) | Parsed, never read: `--context`, `--context-file`, `--clean-processed`, `--archive-processed`, `--backup-state`, `--on-error`, `--max-retries`, `--retry-delay`, `--step-summaries`, five `--summary-*`, `--live-agent-notes`, four `--live-agent-note-*`, `--stream-output`; on `resume` also `--repair`. Then the `DEFAULT_SUMMARY_TIMEOUT_SEC` import | The flag rows of `test_hidden_commands_and_flags_still_parse`; `test_evaluated_run_does_not_apply_retired_processed_directory_flags`; one case in `tests/test_workflow_evaluated_providers.py` |

Not vestiges: the two `return None` branches of `resume.py::_evaluated_resume_route` (a header
swapped under the lock; `test_resume_header_swap_under_lock_preserves_refusal_code`); the `exc`
parameters in `recovery.py` (a shared handler signature); `--force-restart` and the `--emit-*`
flags, which refuse (stage 3 owns the latter).

- [ ] Delete the helpers and their 15 tests; remove the unused parameters, locals and imports.
- [ ] If D4 is "remove": delete the parser entries; replace the flag tests above with
      `test_removed_flags_are_refused` (each flag: exit 2, `unrecognized arguments`, no run
      directory); drop the two flags from the provider case. If "keep": leave `main.py` alone and
      record it. Narrow run: `tests/test_cli_*.py`, `tests/test_resume_command.py`,
      `tests/test_workflow_evaluated_cli.py`, `tests/test_first_hour_e2e.py`.

### Task 9: Final verification (0.5)

- [ ] `tests/test_retired_executors_removed.py` passes with every row; the digest snapshot equals
      Task 0's.
- [ ] End to end with the final code: `python -m orchestrator resume <id>` in Task 0's workspace
      completes the killed run, and `report` shows both effects with the first dispatched once. Then
      the same pipeline is compiled, run, killed in its second command and resumed afresh.
- [ ] Full suite within the gate. Record in the ledger the lines removed per task
      (`git diff --shortstat` against the tag), the collected items before and after, and every
      removed test with the code it covered.

Expected (estimates from function spans; the ledger records the real figures): stage 1 removes about
26,000 production lines (packages 19,941; frontend 4,500; IR stack 960; the rest 300), 1,500 lines
of tests and fixtures and 840 of spec text; stage 2 about 1,500 lines. About 40 collected items go
in stage 1 and 15 in stage 2; about 12 are added. Effort: about 12.75 engineer-days.

## What This Makes Harder

- Bringing back trials, supervision or peer groups means porting from the tag to evaluated
  execution; no parser, checker or reader for them stays. Fallback:
  `git worktree add ../orc-dead-executors archive/dead-executors-2026-11-11`.
- A module that only contains a retired form no longer compiles, even when the entry never reaches
  it. With D4, a script passing a removed flag fails.
- `experiments/evaluated_execution_spike/` and the untracked ES script stop importing. The
  unimported `workflow/elaboration.py` will name a removed field: stage 3 must delete that module,
  not repair it.

## Decisions For The Coordinator

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | A removed form gives a retirement line, or the ordinary unknown-callee error | The retirement line |
| D2 | Task 3 waits for the dashboard plan to delete `persisted_surface.py`, or this lane edits that file | Wait; no other task depends on it |
| D3 | IR stack: delete the three kinds' handling (about 960 lines), or only the lines that name an imported symbol | Delete the handling: no caller, no test, and a clear finish line |
| D4 | Flags that do nothing: remove them, or keep accepting them silently as Phase 1 decided today | Remove: an ignored `--on-error continue` misleads more than a parse error. It reverses a Phase 1 test, so it needs a ruling |
| D5 | `StateManager`: stop at the 47 uncalled methods, or also re-point the tests to `RunState.from_dict` and drop the class | Stop at 47 |
| D6 | Spec sections become notices; design documents stay under a Retired notice | As stated |
| D7 | Keep the prelude type `ProviderSteeringDirective` | Keep until stage 4 |
| D8 | `experiments/evaluated_execution_spike/` (its `trial.py` already imports a module that does not exist) and the untracked `scripts/experiments/es/prompt_authority.py` | Leave the files, add one README line, tell the script's owner |
| D9 | Tag name, local only | `archive/dead-executors-2026-11-11` |
| D10 | `workflows/experiments/qa_placement_effectiveness/` | Keep as text; its header already refuses |

## Not Verified

- That the digests stay equal through Task 5; only the snapshot method was run.
- The frontend and IR line totals, and which helpers in `wcc/elaborate.py` only the provider-group
  code calls (a text scan finds no other call site for `_partition_call_specialization_captures`,
  `_rewrite_specialization_value_captures` and `_provider_inline_name_ref`).
- Whether `resume --debug` has any effect; whether a document test pins a spec section this plan
  shortens; dynamic imports beyond a text search; the dashboard branch beyond its first two commits.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-11 | Plan accepted by the coordinator. Order: Tasks 0 to 2 start now in worktree A; Tasks 4 and 5 (worktree B) start when the Phase 1 leftover fixes are merged, because both edit the frontend; Task 3 waits for the dashboard branch (D2). No provider spend. |
| 2026-11-11 | Rulings D1, D3, D5, D6, D7, D9, D10: as recommended. A removed form gets the `form_retired` line; the IR stack loses the three kinds' handling; `StateManager` stops at the 47 uncalled methods; the tag is `archive/dead-executors-2026-11-11`, local only. |
| 2026-11-11 | Ruling D4: keep. The flags that do nothing stay parsed and ignored, as Phase 1 decided; Task 8 removes only the helpers, the ignored parameters and their tests, and leaves `main.py` alone. Reason: launch recipes and other sessions' scripts pass `--stream-output` and similar flags, and a refused launch of a long run costs more than an ignored flag. If wrong: an ignored `--on-error continue` keeps misleading a user who does not read the help. Revisit in stage 4. |
| 2026-11-11 | Ruling D8: leave `experiments/evaluated_execution_spike/` and the untracked `scripts/experiments/es/prompt_authority.py` as they are and add one README line to the spike. The untracked script belongs to another session; the owner is told in the coordinator's report. |
| 2026-11-11 | Owner decision (roadmap decision 9): live supervision and peer groups stay a future direction. **Task 5 is on hold**: the forms `with-live-providers` and `with-live-provider-peers` keep their parser, checker and elaboration, and the closed build keeps refusing them. Task 4 covers only the `trial` form; the retired-form table gets one row. Task 6 keeps the spec sections of the two forms and shortens only what describes the deleted executors and commands. Tasks 1 and 2 (the old executor packages) stand. The branch does not merge before the salvage page `docs/design/live_provider_supervision_and_peers_salvage.md` is committed. |
| 2026-11-11 | The [salvage record](../design/live_provider_supervision_and_peers_salvage.md) is committed, so the merge condition of the previous row is met. It notes that the tag does not hold the step-executor half that hosted the coordinators; the last tree with all of it is `08cdd59b`. |
| 2026-11-11 | Tasks 0, 1, 2, 7 and 8 done on `chore/lane-d-executors` and reviewed (two reviews: approve with fixes, then approve). From the tag: 11,714 lines deleted, 90 added; `orchestrator/state.py` 1,664 to 573 lines; the shipped-workflow digest snapshot is byte-identical after every task; a run started on the tag's code, killed and resumed on the new code completes. Corrections to this plan: `ForEachState` is kept (`RunState` uses it, Task 7's table is wrong); the test `test_provider_attempt_scope_prefix_like_legacy_ids_remain_opaque_and_canonical` is kept (it covers live code) and is recorded as weak, since it passes with the check it names disabled; `tests/test_retired_executors_removed.py` checks source files, not `find_spec`, so stale `__pycache__` folders do not fail it. For Task 6: with D4 keeping the do-nothing flags, the spec lines that still describe processed-directory checks and state backups (`specs/cli.md`, `specs/queue.md`, `specs/state.md`) are reworded as accepted with no effect. Not yet merged: the full suite runs first. |
| 2026-11-11 | Tasks 0, 1, 2, 7 and 8 merged as `dcc06435` (38 files, 11,714 lines deleted, 90 added). Full suite on `main` plus the branch: 14,456 passed, only the four worktree-artifact failures; no provider call attempted. Next: Task 6 for what has merged (the `peer-*` commands and the two executors are still described in `specs/`), then Task 4 (`trial` form); Task 3 waits for the dashboard branch. |
| 2026-11-12 | Task 4 (the `trial` form, as rescoped) and Task 6 for what has merged are done, reviewed (approve with fixes, six minors fixed) and merged. `trial` refuses with a located `form_retired` line at every target; a user's own definition named `trial` still compiles and runs; the two live-provider forms give identical diagnostics before and after. The reviewer compiled all 685 tracked `.orc` files on base and branch with identical output and exit codes. Full suite on the branch with `main` merged, provider stubs first on `PATH`: 14,275 passed, only the four worktree-artifact failures, stub log absent. Outside the plan: `effect_summary_requires_run_ref_placement_refusal` and its six call sites were deleted (it only ever detected trial effects), and `test_list_map_effect_pre_scan_surfaces_unknown_traversal_nodes` went with the pre-scan it covered (an unknown node now gets a located `list_map_effect_body_unsupported` where the base crashed). Known and left: the digest snapshot holds no run-reference program, and a run-reference program's digest changes with any package change, so the snapshot cannot catch a run-reference regression; two unused leftovers (`effect_summary=` of `raise_run_ref_placement_invalid`, `WorkflowSignature.compiler_direct_result_contract_digest`) for a later clean-up. Correction to earlier rows: the tag `archive/dead-executors-2026-11-11` holds the executor packages only; the last tree with the whole runtime is `08cdd59b`. Next: Task 3 (trial and adjudication packages, the `trial` command), after the trial salvage record is committed. |
| 2026-11-12 | Owner asked why `trial` is removed and for a recommendation. Recommended and applied: delete the form and the packages (a parallel map with a judge call already expresses an in-workflow pick; the form adds only language-level blinding and a budget), and write a salvage record first. The [record](../design/trial_and_adjudication_salvage.md) is committed, so Task 3 may start. It names three things the old design did that the comparison harness does not: clones built in an order that file times reveal (fixed on the seed-set branch, not on `main`), no leak check on the judged patches, and ratings not bound to a digest of what was judged. These go to the seed-set re-review. |
| 2026-11-12 | Task 3 and the rest of Task 6 done, reviewed (approve with fixes; four minors fixed) and merged. The `trial` command, `orchestrator/workflow/trial/`, `orchestrator/workflow/adjudication/`, the trial kind in the old IR stack and `orchestrator/workflow/elaboration.py` (which no longer imported) are gone; `orchestrator trial` exits 2 as an unknown command; the trial and adjudicated-provider spec sections are removal notices pointing to the [salvage record](../design/trial_and_adjudication_salvage.md). The reviewer compiled all 685 tracked `.orc` files and 17 run-reference programs on base and tip with identical results (run-reference digests compared with the package-hash field removed, including inside the encoded config), and showed with an instrumented base that the two removed leftovers were never read or set. Full suite on the branch with `main` merged, under the provider guard: 14,405 passed, only the four worktree-artifact failures. Stage 1 (dead executors) and stage 2 are complete except the two live-provider forms, kept by owner decision 9 (Task 5 on hold). Left for a later clean-up: `ControlFacts.signature` (never read), and five helpers that only the deleted elaboration module called (`conditions.parse_legacy_condition`, `identity.assign_finalization_step_ids`, `statements.STRUCTURED_FINALLY_VERSION`, `statements.is_repeat_until_statement`, `statements.normalize_repeat_until_block`). |
