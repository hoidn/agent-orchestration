# Calibration ladder

Plan Task 8 ("Candidate ladder"), ruling R42. This file fixes the candidate order and metrics before any
calibration run. Rung *n* is the *n*-th row of the ranked table. Each rung's package is built and verified when the
rung is reached; only rung 1 (`cf1-generic-unions`) has a package now. `eb-repl` is not a rung (live smoke only).

## Rules

- **Candidates.** Features on `main` after 2026-07-01 (R4): one capability with its own design or plan document and
  the commits that implement it.
- **Base and solution.** Base = parent of the feature's first design or plan commit. Solution = its last
  implementation commit, tests included.
- **Single feature in the range.** Commits in `base..solution` that change `orchestrator/` but belong to another
  workstream are *foreign*. A candidate is excluded when foreign lines are more than 10% of the range's
  `orchestrator/` lines. Without this rule the anchor carries other features, and the hidden tests may depend on
  them.
- **Thresholds.** At least 1500 changed lines under `orchestrator/`. At least 10 new or changed test functions.
  Refactors, moves and retirements that add no behaviour are not candidates.
- **Exclusions.** The REPL first release, which is already used (`eb-repl`). Any feature whose tests need live
  providers. Live opt-in tests skip, and a skip counts as a pass at the base, so a hidden set never contains them.
- **Order.** Ascending in the primary key, lines changed under `orchestrator/`: rung 1 has the fewest. The ladder
  raises difficulty until a rung qualifies (design, "Difficulty calibration for follow-on experiments"). The plan's
  first draft ordered rungs "by expected difficulty", with `eb-repl` (886 lines) as step 0 below the rest. Ties are
  broken by more modules touched, then more spec and design changes, then more hidden tests, and each places a row
  later.
  Keep 6 rows.
- **Metrics.** Each is measured on `git diff base solution`:
  - *orch* is added plus deleted lines under `orchestrator/`.
  - *modules* is the number of `orchestrator/**.py` files changed.
  - *spec/design* is files (lines) changed under `specs/` and `docs/design/`.
  - *test files* is changed `tests/**/test_*.py` files.
  - *test fns* is the count of added `def test_` lines.
  - *hidden* is the verified hidden set: node ids that fail at the base and pass at the solution, each run alone.
    It is measured only when a rung's package is built.
- **What task.txt names.** Every public entry and every literal a hidden test checks (code, reason, file name), and
  nothing about implementation. A hidden node that checks a literal neither named in task.txt nor defined at the
  base is dropped. A node that calls a private function whose signature or return shape the solution changed is
  dropped by the same rule: naming the private function would describe the implementation. Some literals follow
  from a base convention applied to the test's own program, and task.txt does not list them. Examples are
  flattened output names such as `return__value__title`, step-name suffixes, and probe payloads.

## Search method

1. Timeline: one row per non-merge commit on `main` since 2026-07-01, with `orchestrator/` lines and the test files
   it adds or changes.

   ```bash
   git log main --since=2026-07-01 --no-merges --reverse --numstat --format='@@%h|%ad|%s' --date=short | awk -F'\t' '
     /^@@/{ if(h!="") print h"|"o"|"ta"|"tm; h=substr($0,3); o=0; ta=0; tm=0; next}
     NF==3{ if($3 ~ /^orchestrator\//) o+=$1+$2; if($3 ~ /^tests\/.*test_.*\.py$/){ if($2==0 && $1>0) ta++; else tm++ } }
     END{print h"|"o"|"ta"|"tm}'
   ```

   From this list, group commits into features by their design or plan document. Also list the branch merges with
   `git merge-base M^1 M^2` and the size of `M^2`'s side.
2. Find each feature's first design or plan commit with
   `git log main --diff-filter=A --format='%h %ad' --date=short -- <design or plan doc>`.
3. Metrics and foreign commits for one candidate:

   ```bash
   b=BASE; s=SOLUTION
   git diff --numstat $b $s -- orchestrator | awk '{t+=$1+$2} END{print t+0}'   # orch
   git diff --name-only $b $s -- 'orchestrator/*.py' | wc -l                     # modules
   git diff --name-only $b $s -- specs docs/design | wc -l                       # spec/design files
   git diff --name-only $b $s -- 'tests/*.py' | grep -c '/test_'                 # test files
   git diff $b $s -- tests | grep -c -E '^\+\s*(async )?def test_'               # test fns
   git log --no-merges --reverse --numstat --format='@@%h %s' $b..$s -- orchestrator   # read for foreign commits
   ```

4. Build the hidden set, for rung 1 now and for later rungs when they are reached.
   - Make depth-one clones of the base and the solution (`git init`; `git fetch --depth 1` with
     `uploadpack.allowAnySHA1InWant`).
   - Copy each without `.git`, as `summarize.hidden_failures` does, and copy `hidden/` over the base copy.
   - For every node id of the hidden test files, run
     `PYTHONPATH=<copy> /home/ollie/miniconda3/bin/python -m pytest -q -p no:cacheprovider <nodeid>` alone in the
     base copy and in the solution copy.
   - Qualifying means FAIL at the base and PASS at the solution. Apply the drop rule, then sort with `LC_ALL=C`.
   - Verify the anchors the same way. Apply them with `git apply` at the base, copy without `.git`, and copy
     `hidden/` over the copy.

## Ranked candidates

| rung | slug | base | solution | orch | modules | spec/design files (lines) | test files | test fns | foreign | hidden | capability |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- | --- |
| 1 | `cf1-generic-unions` | `c77e7ec0` | `1798fc70` | 2060 | 33 | 8 (609) | 18 | 103 | 0 | **164** (166 qualify, 2 dropped) | Target 2.33 with first-order generic unions, `std/improve`, the loop-exhaustion and checkpoint-restore repairs, and an example (CF-1). |
| 2 | `resume-projection-integrity` | `1cd60767` | `db988993` | 2555 | 16 | 5 (1390) | 18 | 76 | 0 (corrected, see note) | **169** (175 qualify, 6 dropped) | Audit resume projections: exact projection slots, scoped auditor, atomic failure recorders, retry lineage. |
| 3 | `adopted-attempt-lineage` | `db210752` | `1eb06773` | 3214 | 5 | 0 (0) | 3 | 43 | 0 | at its build | Retirement tooling: lineage incident contracts, adopted-attempt disposition v2, restart authority (`orchestrator/retirement/`). |
| 4 | `pure-result-replay` | `f80e551a` | `76427bde` | 4161 | 14 | 5 (1061) | 13 | 94 | 14 (0.3%) | at its build | Pure-result replay feasibility (dependency index, atomic witnesses, runtime) and its activation. |
| 5 | `dsl-232-composition` | `2effff14` | `2574fa2b` | 10478 | 74 | 19 (3835) | 44 | 308 | 0 | at its build | Value and continuation composition, targets 2.28 to 2.32: union prompt inputs, rich loop values, pure-call composition, portable context, durable host input. |
| 6 | `provider-peer-messaging` | `31f3aedf` | `b08c04a6` | 12835 | 54 | 7 (1425) | 19 | 253 | 0 | at its build | Provider peer groups (`with-live-provider-peers`): contracts, ledgers, protocol, coordinator, runtime, frontend and lowering. |

Full hashes: rung 1 `c77e7ec0b0626914f81b7d1bd6249491e6c59c89` to `1798fc7034d38dc5938472a7cff883b8381703e4`.
Rung 2 `1cd60767` to `db988993`. Rung 3 `db210752` to `1eb06773`. Rung 4 `f80e551a` to `76427bde`. Rung 5
`2effff14` to `2574fa2b`. Rung 6 `31f3aedf` to `b08c04a6`. Resolve the short forms with `git rev-parse` in this
repository. No two rows tie on the primary key.

### Candidate notes

- **1 `cf1-generic-unions`.**
  - First design commit: `ca0a1be3`, the composition-first design and the CF-1 workstream.
  - The range holds CF-1a, the runtime prerequisites (`5a02cb0f`, plus `cdb60211`), and CF-1b, generic unions and
    `std/improve`.
  - Two merges brought main-side material into the branch without touching `orchestrator/`: the
    `experiments/orc_vs_single_call/` record, `docs/reports`, and an `AGENTS.md` line. They therefore appear in the
    upstream anchor.
  - Hidden-test files:
    - `test_structured_control_flow.py` (M), `test_workflow_lisp_generic_exhaustion_resume.py`,
      `test_workflow_lisp_generic_state_exhaustion.py`;
    - `test_workflow_lisp_generic_union_binding.py`, `test_workflow_lisp_generic_union_identity.py`,
      `test_workflow_lisp_generic_union_provider_results.py`, `test_workflow_lisp_generic_unions.py`,
      `test_workflow_lisp_generic_unions_runtime.py`;
    - `test_workflow_lisp_improve_example_e2e.py`, `test_workflow_lisp_improve_stdlib.py`;
    - `test_workflow_lisp_lexical_checkpoint_restore.py` (M), `test_workflow_lisp_loop_recur.py` (M),
      `test_workflow_lisp_restore_source_identity.py`, `test_workflow_lisp_run_ref.py` (M),
      `test_workflow_lisp_target_233.py`, `test_workflow_lisp_union_record_field_targets.py`;
    - `test_workflow_loops_exhaustion_state.py` (M), `test_workflow_shared_validation.py` (M);
    - helpers `workflow_lisp_generic_union_runtime_sources.py`, `workflow_lisp_improve_example_sources.py` and
      `workflow_lisp_improve_stdlib_sources.py`, and `tests/fixtures/workflow_lisp/generic_unions/**` (13 files).
- **2 `resume-projection-integrity`.**
  - First design commit: `52e2b05f`. Base `1cd60767` is the tests-only commit that characterizes the ordering.
  - Foreign commits: none. The first version of this note listed duplicate import aliases (`b095db21`,
    `af051c79`), frontend provenance (`e7068d7a`, `ccbfc1cc`) and import sections (`0b5aa4c5`, `fdf1e06b`), 191
    lines, as foreign. The feature's implementation plan owns all three: Task 1 rejects duplicate import aliases,
    including the repeated and merge-mediated sections, and the plan requires typed `frontend_kind`. The rank does
    not change, because foreign lines never entered the metric.
  - Hidden-test files (all M):
    - `test_adjudicated_provider_resume.py`, `test_adjudicated_provider_runtime.py`,
      `test_at72_provider_state_persistence.py`, `test_cli_observability_config.py`, `test_loader_validation.py`;
    - `test_observability_report.py`, `test_resume_command.py`, `test_runtime_step_lifecycle.py`,
      `test_state_manager.py`, `test_subworkflow_calls.py`;
    - `test_workflow_lisp_build_artifacts.py`, `test_workflow_lisp_drain_roadmap_routing.py`,
      `test_workflow_lisp_key_migrations.py`, `test_workflow_lisp_lexical_checkpoint_restore.py`;
    - `test_workflow_lisp_materialize_view_runtime.py`, `test_workflow_lisp_modules.py`,
      `test_workflow_lisp_pure_projection_runtime.py`, `test_workflow_state_projection.py`;
    - helper `workflow_bundle_helpers.py`, and 7 fixture files.
  - `test_workflow_lisp_key_migrations.py` has one opt-in live environment variable (`..._LIVE_...`), and that test
    skips.
- **3 `adopted-attempt-lineage`.**
  - Design `fad60bb4`, plan `7981f7b9`.
  - Hidden-test files (all M): `test_retirement_attempt_migration.py`, `test_retirement_broad_evidence.py`,
    `test_retirement_source_bindings.py`.
  - The module was retired on main later (`2f7d736f`). The capability is internal migration tooling. Its task text
    will need the retirement-drain vocabulary.
- **4 `pure-result-replay`.**
  - Design `19a98c8b`, plans `09c286dc` (feasibility) and `a4a36422` (activation). The solution is the activation
    close.
  - Foreign commit: `ce02cd17`, 14 lines.
  - Hidden-test files:
    - `test_workflow_lisp_pure_result_replay.py` (A);
    - M: `test_provider_observation_workflow.py`, `test_resume_command.py`, `test_runtime_step_lifecycle.py`,
      `test_state_manager.py`, `test_subworkflow_calls.py`;
    - M: `test_workflow_lisp_drain_roadmap_routing.py`, `test_workflow_lisp_lexical_checkpoint_default_resume.py`,
      `test_workflow_lisp_lexical_checkpoint_restore.py`, `test_workflow_lisp_lexical_checkpoints.py`;
    - M: `test_workflow_lisp_list_traversal.py`, `test_workflow_lisp_phased_delivery_runtime.py`,
      `test_workflow_lisp_pure_projection_runtime.py`;
    - 1 fixture.
- **5 `dsl-232-composition`.**
  - Design `eedb9a4b`. The range is design documents plus one squash commit (`ebdfa740`) and a test-only follow-up
    (`2574fa2b`, which drops a check that depends on the checkout location).
  - It adds five targets (2.28 to 2.32), each with its own capability.
  - Hidden-test files, 44:
    - A: `test_cli_human_input.py`, `test_prompt_contract_recursive_schema.py`, `test_provider_context.py`,
      `test_workflow_human_input.py`, `test_workflow_human_input_carriage.py`, `test_workflow_human_input_runtime.py`;
    - A: `test_workflow_lisp_human_input.py`, `test_workflow_lisp_human_input_e2e.py`,
      `test_workflow_lisp_human_reply_checkpoints.py`;
    - A: `test_workflow_lisp_provider_context_e2e.py`, `test_workflow_lisp_provider_context_types.py`,
      `test_workflow_lisp_provider_context_values.py`, `test_workflow_lisp_pure_call_composition.py`;
    - A: `test_workflow_lisp_pure_projection_source_paths.py`, `test_workflow_lisp_rich_loop_values_e2e.py`,
      `test_workflow_lisp_scoped_union_guards.py`, `test_workflow_lisp_union_input_composition.py`;
    - A: `test_workflow_lisp_union_prompt_inputs_e2e.py`, `test_workflow_lisp_wcc_demand_scan.py`,
      `test_workflow_provider_context.py`, `test_workflow_provider_context_carriage.py`,
      `test_workflow_union_guard_metadata.py`;
    - M: `test_dashboard_compiled_workflow.py`, `test_output_contract.py`, `test_provider_session_transport.py`,
      `test_runtime_observability.py`, `test_v214_runtime_semantics.py`,
      `test_workflow_executor_characterization.py`;
    - M: `test_workflow_lisp_e1_normative_contract.py`, `test_workflow_lisp_e2_trial_contract.py`,
      `test_workflow_lisp_lexical_checkpoint_restore.py`, `test_workflow_lisp_list_traversal.py`;
    - M: `test_workflow_lisp_loop_recur.py`, `test_workflow_lisp_loop_state.py`, `test_workflow_lisp_lowering.py`,
      `test_workflow_lisp_phased_delivery_e2e.py`, `test_workflow_lisp_prompt_calculus.py`;
    - M: `test_workflow_lisp_prompt_identity_runtime.py`, `test_workflow_lisp_pure_projection_runtime.py`,
      `test_workflow_lisp_trial_lowering.py`, `test_workflow_lisp_typed_prompt_inputs.py`;
    - M: `test_workflow_pure_expr.py`, `test_workflow_run_ref_bundle_transport.py`, `test_workflow_shared_validation.py`;
    - 10 fixture files.
- **6 `provider-peer-messaging`.**
  - Design `8001c016`, plan `f8d6d9e4`.
  - Hidden-test files:
    - A: `test_provider_interactive_terminal.py`, `test_provider_peer_group_contracts.py`,
      `test_provider_peer_group_executor.py`, `test_provider_peer_group_ir.py`,
      `test_provider_peer_group_protocol.py`;
    - A: `test_provider_peer_group_resume.py`, `test_provider_peer_group_runtime.py`,
      `test_workflow_lisp_provider_peer_group.py`, `test_workflow_lisp_provider_peer_group_e2e.py`;
    - M: `test_cli_report_command.py`, `test_resume_command.py`, `test_workflow_lisp_build_artifacts.py`,
      `test_workflow_lisp_cli.py`, `test_workflow_lisp_expressions.py`;
    - M: `test_workflow_lisp_provider_supervision_e2e.py`, `test_workflow_lisp_source_map.py`,
      `test_workflow_lisp_wcc_m4.py`;
    - 13 fixture files.
  - The `tests/e2e/test_e2e_provider_peer_delivery.py` and `test_e2e_provider_supervision.py` cases are live
    opt-ins and skip, so they never qualify. `test_provider_interactive_terminal.py` uses a terminal tool; check it
    when the rung is built.

Next in order, beyond the kept rows: `e1-run-ref` (`c0752ba6`..`7fbfc698`, 18265 lines, 74 modules, 34 test files,
423 test fns, no foreign commits).

### Excluded features

| feature | base..solution (or doc) | orch | reason |
| --- | --- | ---: | --- |
| REPL first release | `47e85a9c`..`fe49c1c4` | 886 | Already used (`eb-repl`), and under 1500 lines |
| strict Boolean control flow (2.26) | `a89681a5`..`8dbd13c7` | 4257 | Foreign about 676 lines (16%): the WCC-mapper owner-retention series `2aaf1ecc`..`88416e92`, and `3437f9ea` (peer-group prompt inputs) |
| provider prompt dependencies | `bb2d2111`..`bb9f34ad` | 6215 | Foreign 713 lines (11.5%), provider call policy |
| Q3 prompt identity | `e28a4f39`..`ba7bc148` | 6850 | Foreign 1001 lines (14.6%): L5 navigation and lean-pilot hardening |
| Q4 judgment views | `20cac777`..`000bfcfe` | 2989 | Foreign about 940 lines (31%): Q5 receipts and Q3 result binding |
| Q5 phased contract delivery | `c237e2c9`..`5d8a3151` | 22831 | Contains Q3 (impure) |
| W3 local hooks (2.36) | plan `e8dc30d8` (10-01)..`8e6e06b2` | n/a | Range carries Phase 3 execution and the 10-04..10-07 work |
| bounded parallel maps (2.37) | plan `a4666341` (10-07)..`46d3d3c0` | n/a | Range carries W3, the REPL and `f724b2b7` (5227 lines) |
| E2 trials (2.25) | design `3c773de7`..`8aad035d` | n/a | Shares its design commit with E1, so the range contains all of E1 |
| OMP-I1 | proposal `dd68523d` (08-14)..`fc6a9b1b` | n/a | Range contains strict Boolean (about 4.2k lines), and its tests drive a pinned OMP executable |
| provider live binding / supervision (stage 7) | design `14ac1662` (07-13)..`31f3aedf` | n/a | Range carries YAML retirement and much else |
| Workflow Lisp LSP v1 | `cfcac27f`/`e565fc84`..`c69c33a1` | n/a | Range carries rootfs sealing, bubblewrap and list traversal |
| bounded list traversal (2.18) | `33445be0`..`ecc6ba9e` | n/a | Range carries peer groups and rootfs sealing |
| provider sandbox (isolation, rootfs, bubblewrap, broker) | 07-23..07-26 | n/a | Interleaved with supervision and peer messaging, and depends on host tools |
| typed result guidance | plans 07-09/07-10..`58f90101` | n/a | Range carries the design-delta and certification deletions |
| evaluated execution, phases 0 to 3 | design `b8c9ed7a`..`be327102` | n/a | Range carries the shared defect repairs and the numeric surface. Each phase branch alone is larger than every kept row |
| persisted dashboard surfaces | `9d8a6792`..`816f61ca` | 1462 | Under 1500 lines |
| provider call policy | `069b8e79`^..`87e3cd50` | about 900 | Under 1500 lines |
| typed command input documents, evaluated views, delivery rendering, numeric surface 2.34, transportable Value | various | under 1500 | Under 1500 lines |
| validation split, typecheck and build extractions, design-delta and certification deletions, YAML retirement, migration-tooling retirement, evaluated consolidation (`f724b2b7`), flat retirement (`026f2fa4`), lean-pilot retirement (`61b7d04d`) | various | various | Refactor, move or retirement with no new behaviour |
| lean pilot and ES apparatus | 07-26..08-03 | various | Experiment apparatus, interleaved with Q2, Q3 and L1 |

Limits of the search:
- Grouping commits into features is a judgement, made from subjects and design or plan documents. The metrics are
  mechanical once base and solution are fixed.
- A medium feature built from many small commits with no design or plan of its own could have been missed.
- "Foreign" is judged from commit subjects and the feature's plan. The strict-Boolean attribution in particular is
  uncertain.

## Rung 1 package: `cf1-generic-unions`

- **Files.** `task.txt`, `intent.txt`, `base_commit`, `hidden/` (34 files) and `hidden_tests.txt` (164 node ids,
  `LC_ALL=C` sorted). Anchors:
  - `anchors/cf1-generic-unions-upstream.diff` is `base..solution` without `tests/`, `docs/design/` or
    `artifacts/`. It has 98 files and passes `git apply --check` at the base.
  - `anchors/cf1-generic-unions-stub.diff` adds only `GENERIC_UNION_MIN_TARGET_DSL_VERSION` and a
    `resolve_restore_source_node` that returns `None`. It applies.
  - There is no `seed/`.
- **Hidden set.** The 18 hidden test files hold 752 node ids. Run alone, 586 pass at the base and 166 fail; all 752
  pass at the solution. Qualifying: 166.
- **Dropped (2).** Each calls a private function whose signature or return shape the solution changed. task.txt does
  not name it, and the base does not define it in that form:
  - `tests/test_structured_control_flow.py::test_structured_invalid_output_value_preserves_contract_failure` unpacks
    an `(artifacts, failure)` pair from the private `WorkflowExecutor._resolve_structured_output_artifacts`. At the
    base that method returns a dict or `None`. The reason it checks, `invalid_output_value`, exists at the base.
  - `tests/test_workflow_lisp_lexical_checkpoint_restore.py::test_predicate_proof_revalidates_producer_discriminant_artifact`
    calls the private `_proof_matches_current_selector_variant` with a `descriptor=` keyword that the solution added.
- **Kept on base definitions.** Four other kept nodes use private executor methods or registries that exist at the
  base with the same signature:
  - `_restore_overlay_*` and `_resolve_restore_overlay_ref`;
  - `_emit_lexical_checkpoint_shadow_after_*`, patched as interruption points;
  - `run_ref.config._SUPPORTED_TARGET_DSL_VERSIONS` and `bundle_transport._SUPPORTED_TARGET_DSL_VERSIONS`, which
    task.txt names.
- **Verification.** Each of the 164 node ids was run alone:
  - Upstream anchor applied at the base: 164 of 164 pass.
  - Stub applied at the base: 1 of 164 passes, `tests/test_workflow_lisp_target_233.py::test_generic_union_minimum_target_is_233`,
    which checks the constant the stub registers.
- **Evidence** in `/home/ollie/Documents/agent-orchestration-compare-evidence/calibration/`:
  `cf1-generic-unions-hidden-base.txt` and `cf1-generic-unions-hidden-solution.txt` give per-node results for all
  752 nodes; `cf1-generic-unions-anchor-upstream.txt` and `cf1-generic-unions-anchor-stub.txt` cover the 164.

## Rung 2 package: `resume-projection-integrity`

- **Base check.** The base's `.gitignore` ignores `.orchestrate/` and `artifacts/` (lines 10 and 11, confirmed with
  `git check-ignore`).
- **Files.** `task.txt`, `intent.txt`, `base_commit`, `hidden/` (26 files) and `hidden_tests.txt` (169 node ids,
  `LC_ALL=C` sorted). Anchors:
  - `anchors/resume-projection-integrity-upstream.diff` is `base..solution` restricted to `orchestrator/`,
    `specs/` and `workflows/` (R48). It has 18 files, there are no merges in the range, and it passes
    `git apply --check` at the base.
  - `anchors/resume-projection-integrity-stub.diff` registers the entry points and checks nothing:
    - `ResumeProjectionValidationError`;
    - `WorkflowStateProjection.enumerate_resume_slots`, `resolve_resume_step_id` and `resolve_call_boundary`,
      which raise `NotImplementedError`;
    - a `resume_projection_integrity` module whose `audit_scope` accepts every scope, plus `ResumeScopePath`, the
      two error types, `RetryFrameMember`, and lineage functions that raise;
    - the two `StateManager` recorders, which raise.

    It applies.
  - There is no `seed/`.
- **Hidden set.** `hidden/` holds every test file the range adds or changes (18 test files, the helper
  `workflow_bundle_helpers.py` and 7 golden fixtures). Their 1130 node ids were each run alone, with TMPDIR under the
  scratch directory:
  - At the base, 951 pass and 179 fail.
  - At the solution, 1126 pass. The 4 that fail there (`test_workflow_lisp_key_migrations.py` tracked-plan
    evidence) fail at the base too.
  - Qualifying: 175.
- **Dropped (6).**
  - R44, private functions the solution added:
    - `tests/test_subworkflow_calls.py::test_reached_call_fresh_retry_audits_all_failed_history_before_allocation`
      patches the new private `CallExecutor._allocate_retry_frame_id` and expects it to be called.
    - `tests/test_workflow_state_projection.py::test_retry_target_and_projection_resolution_functions_use_typed_identity_only`
      parses the bodies of the new private `CallExecutor._retry_lineage_for_step` and others, and requires a
      private `_resume_slot_candidates`.
  - Literal rule: the four `tests/test_workflow_lisp_drain_roadmap_routing.py` nodes
    `test_historical_and_durable_authorities_do_not_claim_live_selector_ownership`,
    `test_procedure_first_status_surfaces_share_current_migration_wave_boundary`,
    `test_projection_integrity_acceptance_proof_ownership_is_complete` and
    `test_resume_projection_hardening_is_closed_without_claiming_migration`.
    - They check documentation-routing text: `docs/index.md`, the capability matrix, plan files and their
      wording.
    - task.txt does not name that text, the base does not define it, and it lies outside the anchor's paths.
- **Kept on base definitions.**
  - Private executor and CLI internals whose signatures are unchanged at the base: `_handle_control_flow`,
    `_execute_prologue`, `_execute_call`, `_typed_on_goto_transfer`, `_load_resume_workflow_bundle`,
    `_merge_observability_overrides`, `_is_workflow_lisp_target`, and the Workflow Lisp build internals
    `_compile_entry` and `_reattach_bundle_provenance`.
  - The module-level `audit_scope` bindings in `calls`, `executor` and `resume`, which eight kept test functions
    (15 nodes) substitute, and the auditor module's source guard (no receipts, no retirement readers). task.txt names both.
- **Verification.** Each of the 169 node ids was run alone:
  - Upstream anchor applied at the base: 169 of 169 pass.
  - Stub applied at the base: 50 of 169 pass. These failed at the base only because a new name was missing, or
    they pass with an auditor that accepts everything:
    - 38 in `test_workflow_state_projection.py`, including 13 that exercise only the test file's own
      architecture-guard helper;
    - 5 lexical-restore resumes, 5 guard-ordering or no-load audit checks in `test_subworkflow_calls.py`, and the
      2 auditor-module source guards.

  So a single call that only adds the entry points scores 50/169 = 0.30.
- **Evidence** in `/home/ollie/Documents/agent-orchestration-compare-evidence/calibration/`:
  `resume-projection-integrity-hidden-base.txt` and `resume-projection-integrity-hidden-solution.txt` give
  per-node results for all 1130 nodes; `resume-projection-integrity-anchor-upstream.txt` and
  `resume-projection-integrity-anchor-stub.txt` cover the 169.
- **Rung 2's scan solution hash:** `db9889937a895d67810dee1ea0b1b53552d30eca`.

## Contamination

Every candidate is on `main`, so its solution is in the public GitHub repository and in every checkout of `main`
after the solution commit. The scan (design D5, R20, R35) is detection only. This section lists where the solutions
are on this machine, as of 2026-10-14.

- **Main checkout prefix.** `/home/ollie/Documents/agent-orchestration` and everything under it holds every
  solution: its `.git`, its working tree (main at `c0c46952`), and about 60 worktrees under `.worktrees/`. Two of
  those hold CF-1's own branches: `.worktrees/cf1b-composition-first` (`1fb5b167`) and
  `.worktrees/cf1-exhaustion-selector`. The sibling directories `agent-orchestration-{2,3,agent-sessions,compare,
  compare-evidence,delivery,print,repl,rerun,smoke}` are also covered. The scan matches this prefix unbounded,
  including the `~/` and `$HOME/` spellings, so all of them are detected.
- **Frozen runtime.** `/home/ollie/calib-runtime` (`26bb4d73`) holds every solution. The scan's frozen-runtime
  pattern detects it, provided the calibration criterion names this path as the runtime.
- **Outside the scan: `/var/tmp/agent-orchestration-orc-dynamic-core`.** This worktree (`1ecde6e4`,
  `feat/orc-dynamic-core`) contains every candidate's solution, rungs 1 to 6 included. It lies outside the main
  prefix, and the sandbox does not hide `/var/tmp`, which it does for `/tmp` and `/dev/shm`. No scan pattern matches
  it. Before any calibration run, either remove it (it belongs to another session, so the owner decides) or add its
  path to the scan patterns.
- **Hidden by the sandbox.** Worktrees under `/tmp`: `repl-feature-verification-20261013`, `repl-parent-20261013`,
  `repl-smoke-worktree-20261013`, and a scratchpad `wt-base` at `0c156966`, which holds every solution. The
  sandbox's private `/tmp` hides them. `/home/ollie/.config/superpowers/worktrees/.../dummy-agent-workflow-loop`
  (`b53be0d2`) holds none of these solutions.
- **Transcripts.** Other sessions' Claude and Codex transcripts discuss these features. They are detected by the
  transcript patterns (R35).
- **Solution hashes for each rung's scan:**

  | rung | solution |
  | --- | --- |
  | 1 | `1798fc7034d38dc5938472a7cff883b8381703e4` |
  | 2 | `db988993` |
  | 3 | `1eb06773` |
  | 4 | `76427bde` |
  | 5 | `2574fa2b` (implementation `ebdfa740`) |
  | 6 | `b08c04a6` |

  Expand each to full length when its criterion is frozen.
- **Rung 1 only.**
  - The E-A evidence under `agent-orchestration-compare-evidence/ea/` holds agents' patches that touch the
    loop-result code near CF-1a. E-A's solution hash `cdb60211` lies inside rung 1's range. Both are covered by the
    prefix pattern.
  - `docs/reports/2026-09-28-cf1a-exhaustion-projection-check.md` and the CF-1 plans exist only after the base.
