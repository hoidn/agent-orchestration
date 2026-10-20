# Calibration ladder

Plan Task 8 ("Candidate ladder"), ruling R42. This file fixes the candidate order and metrics before any
calibration run. Rung *n* is the *n*-th row of the ranked table. The packages for rungs 1, 2 and 4 are built;
rungs 3, 5 and 6 are not. `eb-repl` is not a rung (live smoke only).

**Task 3 package update (2026-10-19).** The current RPI and PRR packages use the separately promoted visible
checks and the amended first-existing-semantic-control selection recorded in the measurement plan. Current hidden
denominators are 111 and 129; earlier ladder scan counts below are retained as historical evidence and are not the
current denominators. The ranked table retains its original pre-calibration counts;
use the current package sections for amended counts. The final package hashes are RPI `b2c9cfcae5b8e8b91ac115af518f90c092b7fbd245d253d70dea0bb001879136`
and PRR `08696557c2de2d8d2e521b7e9fed8c05f365c058df43bf5813910ad6a4645278`.

The original control-selection bands remain part of the record: all authorized partial attempts were outside
0.3–0.7, PRR's mutant attempts were outside 0.3–0.8, and RPI mutant-01 was inside its original band. All 12
attempts are retained in `/home/ollie/sc-evidence/preparation/task3/manifest.json`; no new control construction
occurred. After seeing those fractions and before any judge input, selection changed to the first existing
semantically adequate candidate per role. Fractions and failed-node IDs are descriptive only. The reviewed proof
is `/home/ollie/sc-evidence/preparation/task3/semantic-proof.json` (SHA-256
`eae7669a73755809e3e096b44ab8ed82008e364d98645a1716a26aa5714345d5`); `/home/ollie/sc-evidence/preparation/task3/semantic-review.json`
approves offline package integration only, not predicted judge scores, calibration, or live spend. Both new
anchors enter future `anchor_checks` spread under the frozen `phase2.json`.

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
| 3 | `adopted-attempt-lineage` | `db210752` | `1eb06773` | 3214 | 5 | 0 (0) | 3 | 43 | 0 | **52** (61 qualify, 9 dropped) | Retirement tooling: lineage incident contracts, adopted-attempt disposition v2, restart authority (`orchestrator/retirement/`). |
| 4 | `pure-result-replay` | `f80e551a` | `76427bde` | 4161 | 14 | 5 (1061) | 13 | 94 | 14 (0.3%) | **134** (828 qualify, 694 dropped) | Pure-result replay feasibility (dependency index, atomic witnesses, runtime) and its activation. |
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
- **Current files.** `task.txt`, `intent.txt`, `base_commit`, `hidden/`, `hidden_tests.txt` (111 remaining ids,
  `LC_ALL=C` sorted), `seed/dev-check.json`, and `seed/tests/` with the promoted test and its support helper.
  The package has four anchors: upstream, stub, partial and mutant.
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
  - The amended four-control set also includes `anchors/resume-projection-integrity-partial.diff` and
    `anchors/resume-projection-integrity-mutant.diff` (hashes below).
- **Original hidden qualification scan (historical).** `hidden/` holds every test file the range adds or changes (18 test files, the helper
  `workflow_bundle_helpers.py` and 7 golden fixtures). Their 1130 node ids were each run alone, with TMPDIR under the
  scratch directory:
  - At the base, 951 pass and 179 fail.
  - At the solution, 1126 pass. The 4 that fail there (`test_workflow_lisp_key_migrations.py` tracked-plan
    evidence) fail at the base too.
  - Qualifying: 175.
- The following drop/keep/verification detail preserves the original qualification scan and does not describe the
  current 111-node denominator. Task 3 promoted eight of the former hidden nodes:
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
- **Original verification (historical).** Each of the 169 node ids was run alone:
  - Upstream anchor applied at the base: 169 of 169 pass.
  - Stub applied at the base: 50 of 169 pass. These failed at the base only because a new name was missing, or
    they pass with an auditor that accepts everything:
    - 38 in `test_workflow_state_projection.py`, including 13 that exercise only the test file's own
      architecture-guard helper;
    - 5 lexical-restore resumes, 5 guard-ordering or no-load audit checks in `test_subworkflow_calls.py`, and the
      2 auditor-module source guards.

  So a single call that only adds the entry points scores 50/169 = 0.30.
- **Promoted node ids:**
  - `tests/test_runtime_step_lifecycle.py::test_projection_error_bypasses_failure_success_always_and_on_error_continue[always]`
  - `tests/test_runtime_step_lifecycle.py::test_projection_error_bypasses_failure_success_always_and_on_error_continue[failure]`
  - `tests/test_runtime_step_lifecycle.py::test_projection_error_bypasses_failure_success_always_and_on_error_continue[success]`
  - `tests/test_runtime_step_lifecycle.py::test_projection_error_exits_for_each_and_repeat_until_without_next_iteration[for_each]`
  - `tests/test_runtime_step_lifecycle.py::test_projection_error_exits_for_each_and_repeat_until_without_next_iteration[repeat_until]`
  - `tests/test_runtime_step_lifecycle.py::test_projection_error_finalization_failure_is_supplemental`
  - `tests/test_runtime_step_lifecycle.py::test_projection_error_finalization_sticky_failure_is_supplemental`
  - `tests/test_runtime_step_lifecycle.py::test_projection_error_in_finalization_promotes_without_prior_sticky_error`
- **Promoted check.** `seed/dev-check.json` runs `seed/tests/test_runtime_step_lifecycle.py` first; that file's SHA-256 is
  `6c0ffb91970adc7eaeeef8a2362d81ee57e290775821e78f48c9a6ca32a61506`. The verbatim
  `seed/tests/workflow_bundle_helpers.py` support file has SHA-256
  `6cc53929e568b3f4f827d948d43fab72619cefd6d1566df4b9f67816b16ab773`; the config hash is
  `a52074d9d1733d24f353dfdf35c3581386cb442a5d5f83387ab9be871e98c96e`. Controller tests on a tiny task fixture
  cover an empty/base failure and an upstream-anchor pass. Root's post-commit integration run will check the real
  package's base, upstream and stub controls.
- **Semantic controls.** Partial anchor SHA-256 `759242bdc3dade91afaa7fc642e207b0b868065e3cb4b458b44120e9ea3d249b`
  omits `orchestrator/workflow/calls.py`: the root-executor resume audit remains,
  but a reached child call does not audit its local projection. The retained-behavior test is
  `test_projection_resume_root_direct_executor_rechecks_checksum_and_audit_before_prologue`; the functional
  counterexample is `test_reached_call_checksum_precedes_local_projection_failure`, which fails with
  `call_failed` instead of `resume_projection_integrity_error`. The partial passes the promoted visible check;
  its 96/111 fraction (0.8649) is descriptive only. Full failing-node evidence is
  `/home/ollie/sc-evidence/preparation/task3/reports/hidden/resume-projection-integrity-partial-01-no-calls.json`.
  Mutant anchor SHA-256 `79570b62aba0f82708c3fc9e29d878cd5040d84e1f154a60ea3b40c91cd28cd8` adds one early return
  that skips `audit_scope`; it retains 2,499/2,499 upstream added lines
  and fails `test_projection_resume_root_direct_executor_rechecks_checksum_and_audit_before_prologue` at the
  functional assertion `root guard must reject before prologue`; the promoted visible check passes and its 73/111
  fraction is descriptive only. Full failing-node evidence is
  `/home/ollie/sc-evidence/preparation/task3/reports/hidden/resume-projection-integrity-mutant-01-skip-audit.json`.
- **Evidence** in `/home/ollie/Documents/agent-orchestration-compare-evidence/calibration/`:
  `resume-projection-integrity-hidden-base.txt` and `resume-projection-integrity-hidden-solution.txt` give
  per-node results for all 1130 nodes; `resume-projection-integrity-anchor-upstream.txt` and
  `resume-projection-integrity-anchor-stub.txt` cover the 169.
- **Rung 2's scan solution hash:** `db9889937a895d67810dee1ea0b1b53552d30eca`. Final package-tree SHA-256:
  `b2c9cfcae5b8e8b91ac115af518f90c092b7fbd245d253d70dea0bb001879136`.

## Rung 3 package: `adopted-attempt-lineage`

- **Base check.** The base's `.gitignore` ignores `.orchestrate/` and `artifacts/` (lines 10 and 11, confirmed with
  `git check-ignore`).
- **Files.** `task.txt`, `intent.txt`, `base_commit`, `hidden/` (4 files) and `hidden_tests.txt` (52 node ids,
  `LC_ALL=C` sorted). Anchors:
  - `anchors/adopted-attempt-lineage-upstream.diff` is `base..solution` restricted to `orchestrator/`, `specs/` and
    `workflows/` (R48). It has 5 files, all under `orchestrator/retirement/`, and there are no merges in the range.
  - `anchors/adopted-attempt-lineage-stub.diff` registers the entry points and does nothing useful:
    - `build_attempt_migration_incident`, `validate_attempt_migration_incident` and `capture_invalidated_adopted`
      raise `AttemptMigrationError`;
    - a `capture-invalidated-adopted` CLI subcommand calls the stub;
    - `derive_committed_predecessor_lineage` raises;
    - the new keywords `bound_file_bytes` and `require_committed_fallback` are accepted by `validate_generation`
      and `validate_bound_record` and ignored;
    - the two exports are added to `orchestrator.retirement.__all__`.

    Both anchors pass `git apply --check` at the base.
  - There is no `seed/`.
- **Hidden set.** `hidden/` holds the range's three changed test files and the new helper
  `retirement_broad_evidence_support.py`. Their 855 node ids were each run alone, with TMPDIR under the scratch
  directory:
  - At the base, 790 pass and 65 fail.
  - At the solution, 851 pass. The 4 that fail there (`test_retirement_broad_evidence.py` repository-fixture and
    temp-root probe tests) fail at the base too.
  - Qualifying: 61.
- **Dropped (9).**
  - R49, the 7 node ids the stub passes:
    - `test_retirement_attempt_migration.py::`
      - `test_incident_v1_rejects_current_head_outside_predecessor_ancestry`
      - `test_incident_v1_rejects_failure_baseline_candidate_head_mismatch`
      - `test_incident_v1_rejects_non_owner_confirmed_lifecycle[identity_mismatch]` and `[pending]`
      - `test_incident_v1_requires_an_uncovered_predecessor_path`
      - `test_invalidated_adopted_incident_only_recovery_rejects_unrelated_status_drift`
    - `test_retirement_broad_evidence.py::test_retirement_public_surface_is_cold_lazy_and_cli_sets_are_exact`

    These are rejection tests that a stub which raises satisfies, plus the export and CLI-set registration check.
  - R44 extension, fault injection through a private helper the base defines unchanged. Each test passes only if
    the implementation routes that step through the helper:
    - `test_retirement_source_bindings.py::test_committed_predecessor_lineage_rejects_duplicate_path_projection`
      patches `source_bindings._git` and duplicates `diff-tree` output.
    - `test_retirement_attempt_migration.py::test_invalidated_adopted_recovers_only_after_incident_publication`
      patches `attempt_migration._publish_exclusive` to crash at its second publication.
  - No test checks documentation wording.
- **Kept on base definitions.**
  - Tests compute expectations with base helpers whose call shape is unchanged: `attempt_migration._repository_state`,
    `materialization._evidence_root_from_request_path`, `_request_path`, `_snapshot_path` and `_json_output`.
  - They also use `_input_binding(repository_root, role, path)`, which the solution extends only with keyword-only
    arguments that have defaults.
  - task.txt describes the resulting data, not the helpers.
- **Verification.** Each node id was run alone, on all 61 qualifying ids:
  - Upstream anchor applied at the base: 61 of 61 pass, so 52 of the 52 kept.
  - Stub applied at the base: 7 of 61 pass (the R49 drops), so 0 of the 52 kept.
- **Evidence** in `/home/ollie/Documents/agent-orchestration-compare-evidence/calibration/`:
  `adopted-attempt-lineage-hidden-base.txt` and `adopted-attempt-lineage-hidden-solution.txt` give per-node
  results for all 855 nodes; `adopted-attempt-lineage-anchor-upstream.txt` and
  `adopted-attempt-lineage-anchor-stub.txt` cover the 61.
- **Rung 3's scan solution hash:** `1eb06773029df5c62d81c10e0d60ea6f72c81ab7`.

## Rung 4 package: `pure-result-replay`

- **Base check.** The base's `.gitignore` ignores `.orchestrate/` and `artifacts/` (lines 10 and 11, confirmed with
  `git check-ignore`).
- **Current files.** `task.txt`, `intent.txt`, `base_commit`, `hidden/`, `hidden_tests.txt` (129 remaining ids,
  `LC_ALL=C` sorted), `seed/dev-check.json`, and `seed/tests/test_runtime_step_lifecycle.py`. The package has four
  anchors: upstream, stub, partial and mutant.
  - `anchors/pure-result-replay-upstream.diff` is `base..solution` restricted to `orchestrator/`, `specs/` and
    `workflows/` (R48). It has 15 files; there are no merges in the range. It includes `ce02cd17` (14 lines),
    earlier listed as foreign.
  - `anchors/pure-result-replay-stub.diff` registers the entry points and does nothing useful:
    - a `pure_result_replay` module with the constants, the error and witness types and an empty
      `PureReplayRuntime`, whose functions (including `_propagate_pure_ineligibility`) raise;
    - the four `StateManager` pure-visit methods, which raise;
    - `load_existing_call_frame_read_only`, which raises;
    - the new keywords `result_persistence_profile` (`initialize`), `eligible_pure_settlement`
      (`persist_step_result`) and `restart_node_id` (`determine_default_resume_decision`), accepted and ignored.

    Both anchors pass `git apply --check` at the base.
- **Original hidden qualification scan (historical).**
  - Verification ran with **TMPDIR unset**, so pytest uses the default `/tmp`, as `summarize` does.
  - The 13 test files hold 971 node ids, each run alone. At the base, 141 pass and 830 fail; almost all fail
    because nine of the files import the new module at collection. At the solution, 969 pass; the 2 that fail
    there (documentation-routing tests) fail at the base too.
  - Qualifying: 828.
- **Original dropped-node accounting (historical, 694).**
  - R49: 643 node ids the stub passes. They failed at the base only because the new module or a new name was
    missing. The list is in the evidence file `pure-result-replay-drops-r49.txt`.
  - R44: 37 tests that call, patch or read private functions or attributes the solution added or changed:
    `_configure_pure_replay_runtime`, `_pure_replay_runtime`, `_evaluate_pure_replay_node`,
    `_audit_existing_pure_replay_call_frame`, `_replay_runtime`, `_walk_typed_binding_ref_documents`,
    `_walk_value_document_refs`, `_propagate_pure_ineligibility`, `_determine_resume_default_resume_decision`
    (new `restart_node_id` keyword), `_execute_step_loop` (new keywords), and `_CallFrameStateManager` called with
    the new `result_persistence_profile` keyword:
      - `test_resume_command.py::test_executor_defers_provider_observation_until_profile_audit_with_unloaded_state`
      - `test_resume_command.py::test_fail_closed_resume_audits_leaves_without_replaying_or_masking_checkpoint_error`
      - `test_runtime_step_lifecycle.py::test_call_frame_persistence_profile_cannot_backfill_existing_frame`
      - `test_runtime_step_lifecycle.py::test_call_frame_persistence_profile_is_explicit_on_fresh_frame`
      - `test_runtime_step_lifecycle.py::test_call_frame_same_visit_reuse_is_read_only`
      - `test_subworkflow_calls.py::test_existing_absent_replay_profile_workflow_lisp_frame_is_unchanged_before_execution`
      - `test_subworkflow_calls.py::test_existing_reached_call_frame_audit_hook_is_read_only_and_precedes_constructor`
      - `test_subworkflow_calls.py::test_existing_replay_profile_call_frame_audit_rejects_mixed_surfaces[private-lineage]`
      - `test_subworkflow_calls.py::test_existing_replay_profile_call_frame_audit_rejects_mixed_surfaces[pure-bundle]`
      - `test_subworkflow_calls.py::test_existing_replay_profile_call_frame_audit_rejects_mixed_surfaces[restore-binding]`
      - `test_subworkflow_calls.py::test_existing_replay_profile_call_frame_audit_rejects_mixed_surfaces[same-frame-pure-checkpoint]`
      - `test_subworkflow_calls.py::test_existing_replay_profile_call_frame_audit_rejects_mixed_surfaces[value-row]`
      - `test_subworkflow_calls.py::test_failed_workflow_lisp_child_retry_still_allocates_fresh_frame`
      - `test_subworkflow_calls.py::test_resumed_parent_starts_never_entered_child_call_fresh`
      - `test_subworkflow_calls.py::test_resumed_parent_still_fails_closed_for_persisted_child_without_prior_boundary`
      - `test_workflow_lisp_lexical_checkpoint_default_resume.py::test_replay_profile_filtered_nearest_failure_never_scans_older_point[ambiguous]`
      - `test_workflow_lisp_lexical_checkpoint_default_resume.py::test_replay_profile_filtered_nearest_failure_never_scans_older_point[unusable]`
      - `test_workflow_lisp_lexical_checkpoint_restore.py::test_replay_profile_restore_payload_omits_derivable_pure_bindings`
      - `test_workflow_lisp_lexical_checkpoints.py::test_replay_profile_eligible_pure_point_emits_no_checkpoint_record`
      - `test_workflow_lisp_lexical_checkpoints.py::test_replay_profile_pure_evaluation_failure_keeps_full_row_and_checkpoint_authority`
      - `test_workflow_lisp_lexical_checkpoints.py::test_replay_profile_routed_skipped_pure_keeps_ordinary_checkpoint_authority`
      - `test_workflow_lisp_phased_delivery_runtime.py::test_two_completed_phased_boundaries_reuse_and_skip_execution`
      - `test_workflow_lisp_pure_result_replay.py::test_interrupted_pure_current_reuses_visit_and_evaluates_once[a-before-first-durable-boundary]`
      - `test_workflow_lisp_pure_result_replay.py::test_interrupted_pure_current_reuses_visit_and_evaluates_once[b-after-e1]`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_dependency_index_propagates_reasons_deterministically`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_e1_boundary_reconstructs_only_required_a_before_dispatch`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_finalization_seeds_only_exact_typed_predicate_closure`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_resume_never_evaluates_inactive_route_projection`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_settlement_seeds_only_exact_typed_output_closure`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_typed_binding_walker_accepts_typed_inactive_union_literal`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_typed_binding_walker_accepts_variant_case_discriminant_ref`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_typed_binding_walker_rejects_nested_wrong_inactive_union_literal`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_typed_binding_walker_rejects_wrong_inactive_union_literal[literal-active-field]`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_typed_binding_walker_rejects_wrong_inactive_union_literal[ref-active-field]`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_typed_binding_walker_rejects_wrong_nested_union_in_inactive_field`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_typed_binding_walker_validates_mixed_json_literals`
      - `test_workflow_lisp_pure_result_replay.py::test_pure_replay_value_document_ref_walker_ignores_typed_literals`
  - R50: 12 tests that crash `StateManager._write_state` (unchanged at the base) before or after the write. They
    pass only if the new pure-visit methods persist through that helper:
      - `test_runtime_step_lifecycle.py::test_call_frame_atomic_pure_begin_never_splits_visit_and_cursor[after]`
      - `test_runtime_step_lifecycle.py::test_call_frame_atomic_pure_begin_never_splits_visit_and_cursor[before]`
      - `test_runtime_step_lifecycle.py::test_call_frame_atomic_pure_settlement_is_cursor_or_terminal_row[failure-after]`
      - `test_runtime_step_lifecycle.py::test_call_frame_atomic_pure_settlement_is_cursor_or_terminal_row[failure-before]`
      - `test_runtime_step_lifecycle.py::test_call_frame_atomic_pure_settlement_is_cursor_or_terminal_row[success-after]`
      - `test_runtime_step_lifecycle.py::test_call_frame_atomic_pure_settlement_is_cursor_or_terminal_row[success-before]`
      - `test_state_manager.py::TestStateManager::test_atomic_pure_begin_exposes_only_unstarted_or_matching_cursor[after]`
      - `test_state_manager.py::TestStateManager::test_atomic_pure_begin_exposes_only_unstarted_or_matching_cursor[before]`
      - `test_state_manager.py::TestStateManager::test_atomic_pure_settlement_exposes_only_cursor_or_settled_row[after-failure]`
      - `test_state_manager.py::TestStateManager::test_atomic_pure_settlement_exposes_only_cursor_or_settled_row[after-success]`
      - `test_state_manager.py::TestStateManager::test_atomic_pure_settlement_exposes_only_cursor_or_settled_row[before-failure]`
      - `test_state_manager.py::TestStateManager::test_atomic_pure_settlement_exposes_only_cursor_or_settled_row[before-success]`
  - Documentation wording: 2 tests that check routing text in `docs/` (outside the anchor's paths):
      - `test_workflow_lisp_drain_roadmap_routing.py::test_m1_estate_shrink_routes_the_completed_m0_boundary_and_bounded_deletion_plan`
      - `test_workflow_lisp_drain_roadmap_routing.py::test_ml0_selects_at_least_once_recovery_with_reviewable_component_bounds`
- **Kept on base definitions.**
  - Spies or interruptions on unchanged private executor paths, used to set up interruptions or count effects:
    `_execute_command`, `_execute_pure_projection`, `_step_id`, `_execute_prologue` (as must-not-run),
    `_resolve_pure_projection_bindings`, `_public_runtime_plan_payload` and `_write_state` (as must-not-write).
  - `_CallFrameStateManager` called with base-compatible arguments.
  - The test file `test_workflow_lisp_pure_result_replay.py` imports the private name
    `_propagate_pure_ineligibility` at module level. Its 104 kept nodes therefore need that name to exist, so
    task.txt names it as an importable callable whose behaviour is not checked.
- **Verification.** Each node id was run alone, on all 828 qualifying ids:
  - Upstream anchor applied at the base: 826 of 828 pass (the 2 documentation tests fail), so 134 of the 134 kept.
  - Stub applied at the base: 643 of 828 pass (the R49 drops), so 0 of the 134 kept.
- **Original evidence** in `/home/ollie/Documents/agent-orchestration-compare-evidence/calibration/`:
  `pure-result-replay-hidden-base.txt` and `pure-result-replay-hidden-solution.txt` give per-node results for all
  971 nodes; `pure-result-replay-anchor-upstream.txt` and `pure-result-replay-anchor-stub.txt` cover the original 828; the
  drop lists are `pure-result-replay-drops-r49.txt`, `-r44.txt` and `-r50.txt`.
- **Promoted check.** `seed/dev-check.json` runs `seed/tests/test_runtime_step_lifecycle.py` first. The test file's
  SHA-256 is `ab179a6abd29333d0a67dabc3e1d70c74848d7753df8b9977fe28fb11dddf32a`; the config hash is
  `db2cd149712cb964df6611eccfb801feb4ca09c3992cf4b7d9fdbe2895407145`. Five former hidden nodes moved to this
  check:
  - `tests/test_runtime_step_lifecycle.py::test_call_frame_persistence_profile_rejects_malformed_existing_state_before_write[missing]`
  - `tests/test_runtime_step_lifecycle.py::test_call_frame_persistence_profile_rejects_malformed_existing_state_before_write[non-mapping]`
  - `tests/test_runtime_step_lifecycle.py::test_outcome_recorder_atomic_pure_failure_or_skip_uses_full_row[failed]`
  - `tests/test_runtime_step_lifecycle.py::test_outcome_recorder_atomic_pure_failure_or_skip_uses_full_row[skipped]`
  - `tests/test_runtime_step_lifecycle.py::test_outcome_recorder_atomic_pure_success_uses_exact_shell`
- **Semantic controls.** Partial anchor SHA-256 `5fc14a94fccea40a55e5601a9593070f21f23489332ddee0bd1017a5cbf0c755`
  omits `orchestrator/workflow/executor.py`: exact shell settlement in state
  remains, but public workflow execution does not activate the replay profile. Its counterexample,
  `test_public_run_activates_replay_profile_with_value_free_pure_results`, fails at runtime because
  `WorkflowExecutor._pure_replay_profile_enabled_for_step` is absent; the retained behavior test
  `test_atomic_pure_success_returns_and_persists_exact_shell` passes. Its 101/129 fraction (0.7829) is descriptive
  only, and its promoted visible check fails at the same absent executor API. Mutant anchor SHA-256
  `62583c797165847aa06ce3001e63ff200537e0032e011d25e0923427ee4f8739`; its one early return makes
  `required_node_ids_for_boundary` return an empty closure; it retains 4,170/4,170 upstream added lines and fails
  `test_pure_replay_boundary_indexes_list_root_value_documents` because the required pure-node ID is missing. Its
  116/129 fraction (0.8992) is descriptive only.
- **Final package-tree SHA-256:**
  `08696557c2de2d8d2e521b7e9fed8c05f365c058df43bf5813910ad6a4645278`.
- **Rung 4's scan solution hash:** `76427bdedbbac300bbd82d45db7fa6e24a770f84`.

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

**R49 (2026-10-14, before any rung-2 run):** rung 2's hidden set drops the 50 node ids its stub anchor passes (they measure imports or the test file's own helpers), leaving 119; the dropped ids are the PASS rows of the evidence file `resume-projection-integrity-anchor-stub.txt`.
