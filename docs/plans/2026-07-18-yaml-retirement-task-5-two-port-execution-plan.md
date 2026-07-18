# YAML Retirement Task 5 Two-Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by task.
> Use `superpowers:test-driven-development` for every production change. Every
> task requires a specification-compliance review followed by an
> implementation-quality review before the next task starts. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Port and promote exactly the two surviving YAML workflow families,
`verified_iteration_drain` and `generic_run_watchdog`, onto dedicated Workflow
Lisp sources with family-specific parity, artifact-lineage, launch-routing, and
fresh `.orc` execution evidence while retaining their YAML sources for the Task
6 deletion gate.

**Architecture:** Treat each family as an independent vertical migration. The
`.orc` source owns typed public inputs and returns, calls the existing prompt and
command assets through declared extern contracts, and uses the already-landed
generic provider-selection, provider-policy, prompt-dependency, structured-
result, conditional, and loop machinery. Each family first lands a runnable
candidate, then a content-addressed parity/readiness registration and report,
then a route promotion and fresh `.orc` smoke. No compiler or runtime branch may
name either family.

**Tech Stack:** Workflow Lisp language 0.1 targeting DSL 2.15, typed provider and
command extern manifests, existing Python command adapters, migration-parity v2,
route-readiness v1, pytest/xdist, canonical JSON/SHA-256, Git, and tmux.

**Governing roadmap:**
`docs/plans/2026-07-07-yaml-retirement-program.md`, Task 5.

**Execution status:** Planning and review are in progress. Task 5 begins from
provider prompt-dependency completion commit `48d5114b280607f491d5a1f3d6acd24d98e5060d`.
Neither family is currently registered in the parity-target manifest or route-
readiness registry, and neither dedicated `.orc` source currently exists.

---

## Scope, Sequencing, And Deliberate Cost

Execute the families in this order:

1. characterize, implement, prove, and promote `verified_iteration_drain`;
2. freeze the bounded watchdog design;
3. characterize, implement, prove, and promote `generic_run_watchdog`;
4. run the exact Task-5 closure gate and update the roadmap; and
5. hand the two retained YAML files to Task 6 without deleting either one.

The vertical sequence keeps a failed family migration from contaminating the
other family's evidence. It makes shared family-test helpers and manifest edits
slightly more repetitive, and a shared correction discovered by the second
family may require a separately reviewed generic prerequisite task.

Retained functional scope:

- typed public defaults and closed provider choices;
- exact provider model, effort, timeout, and invocation-profile behavior;
- exact required prompt dependency sets, canonical order, and watchdog prepend
  instruction meaning;
- typed provider and command returns, including optional branch data;
- verified-iteration bounded loop, terminal outcomes, per-iteration artifacts,
  Record idempotence, and resume-visible lineage;
- watchdog probe/no-repair/repair/publication behavior;
- parity-target and route-readiness registration;
- candidate parity report, promoted launch routing, fresh `.orc` smoke, and
  ordered independent reviews; and
- an exact handoff to Task 6's generic reference and supported-run deletion
  gates without inventing a Task-5 scanner.

Excluded scope:

- all security, path-hardening, hostile-input, authentication, provenance,
  platform-probe, adversarial, and security-review work;
- any family-named compiler, lowering, executor, migration-parity, or route-
  readiness special case;
- deletion, archive, or mutation of any authored YAML/YML file;
- Task 6 tranche execution or Task 7 parser removal;
- the held `non_progress_step_back_demo` family and its protected files; and
- behavior changes to the existing Python command adapters or prompt meaning
  unless an independently reviewed generic correctness prerequisite is proven
  necessary.

Do not create a worktree. Repository instructions prohibit worktrees.

## Governing Authorities

Read these before implementation, in order:

- `AGENTS.md` and `docs/index.md`;
- `docs/plans/2026-07-07-yaml-retirement-program.md`;
- `docs/workflow_yaml_orc_gap_list.md`;
- `docs/workflow_yaml_estate_triage.md`;
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`;
- `docs/design/verified_iteration_drain.md`;
- `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/design/workflow_lisp_native_transportable_returns.md`;
- `docs/design/workflow_command_adapter_contract.md`;
- `specs/providers.md`, `specs/dependencies.md`, and `specs/state.md`;
- the two retained YAML sources and their existing behavioral tests; and
- `docs/plans/2026-05-18-generic-run-watchdog-workflow-plan.md` as historical
  watchdog behavior context, not current Workflow Lisp implementation authority.

If durable authority and YAML mechanics disagree, preserve the user-visible
family contract and record the internal typed replacement as an accepted parity
difference. Do not reproduce YAML-only indirection such as the verified drain's
summary-pointer helper.

Two baseline choices are settled by this plan and do not require escalation:

- preserve the YAML defaults (both verified providers default to Codex;
  `stall_limit` remains a string-compatible public value); and
- preserve the YAML exhaustion observable: public `drain_status` becomes
  `STALLED` at exhaustion while the last already-written iteration summary may
  still describe its pre-exhaustion `CONTINUE` result. Any later normalization
  is a separate behavior change.

## Protected Working-Tree Contract

Do not edit, restore, stage, or commit these pre-existing user paths:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

The untracked Task-6 plan is a separate concurrent artifact. Do not edit or
stage it during Task 5:

- `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`

Before every commit, stage only exact task paths and verify that neither set is
cached. Never use `git add -A`, `git add .`, or a broad directory add.

## Review And Commit Protocol

For every task:

1. dispatch one fresh implementation subagent with the exact task contract;
2. require RED evidence before production edits and GREEN evidence afterward;
3. run `pytest --collect-only` when tests are added or renamed;
4. run the narrowest relevant tests and at least one compile/dry-run/runtime
   integration check for source, extern, routing, or parity changes;
5. freeze the exact candidate tree, parent, patch digest, governing-plan digest,
   and fresh command results;
6. obtain a fresh specification-compliance review;
7. fix findings and repeat the specification review until PASS;
8. obtain a fresh implementation-quality review over the spec-passing object;
9. fix findings and restart both ordered reviews when the object changes; and
10. commit only the reviewed paths with both review tokens in trailers.

Reviewers must exclude all security-related analysis and claims. They must fail
closed on unproved behavior, family-named generic machinery, missing artifact
lineage, missing parity roles, routing that bypasses the `.orc` candidate, or a
claim that YAML deletion is complete.

Every named migration-parity output root owns exactly these review inputs for
its selected family: `<family>.json`, `<family>.md`, `index.json`,
`gate_evaluation.json`, and `logs/<role>.{stdout,stderr}.log` for all seven
executable roles. Candidate and final roots are never reused across families.
The selected family report, index row, and gate row must agree on manifest SHA,
candidate digest, route identity, report digest, and overall result.

---

## Task 1: Freeze Verified-Iteration And Add Its Adapter/Extern Harness

**Files:**

- Create: `tests/test_workflow_lisp_verified_iteration_drain.py`
- Create: `workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.providers.json`
- Create: `workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.prompts.json`
- Create: `workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.commands.json`
- Modify: `tests/test_verified_iteration_drain.py`
- Modify: `workflows/library/scripts/prepare_verified_iteration.py`
- Modify: `workflows/library/scripts/run_verified_iteration_checks.py`
- Modify: `workflows/library/scripts/record_verified_iteration.py`

**Owned tests:**

- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_yaml_baseline_contract_is_frozen`
- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_port_source_is_absent_at_baseline`
- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_extern_manifests_bind_existing_assets`
- `tests/test_verified_iteration_drain.py::test_verified_command_adapters_write_runtime_and_compatibility_outputs`

- [ ] Add the first three passing characterization tests. Bind the YAML byte
  digest, public inputs/defaults/outputs, three prompts, three commands, provider
  policies, max-40 loop, terminal states, and absent `.orc` path.
- [ ] Add the dual-output adapter test and run it RED; it must fail only because
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is not written.

```bash
pytest -q tests/test_verified_iteration_drain.py::test_verified_command_adapters_write_runtime_and_compatibility_outputs
```

  Expected RED: exit 1 with the runtime bundle absent while compatibility files
  exist.
- [ ] Add the three extern manifests, using the shared unrestricted provider
  profiles, exact prompt assets, and exactly prepare/check/record commands.
- [ ] Make the three scripts write the runtime bundle plus their existing
  semantic/YAML compatibility files. Do not add the summary-pointer helper.
- [ ] Run and require GREEN:

```bash
pytest --collect-only -q tests/test_workflow_lisp_verified_iteration_drain.py tests/test_verified_iteration_drain.py
pytest -q tests/test_workflow_lisp_verified_iteration_drain.py tests/test_verified_iteration_drain.py -k 'baseline_contract or source_is_absent or extern_manifests or runtime_and_compatibility_outputs'
pytest -q tests/test_verified_iteration_drain.py
```

- [ ] Complete ordered reviews and commit only the eight listed paths.

## Task 2: Implement The Verified-Iteration `.orc` Candidate

**Files:**

- Create: `workflows/library/verified_iteration_drain/drain.orc`
- Modify: `tests/test_workflow_lisp_verified_iteration_drain.py`
- Modify: `tests/test_verified_iteration_drain.py`
- Modify: `workflows/library/scripts/run_verified_iteration_checks.py`
- Modify: `workflows/library/scripts/record_verified_iteration.py`
- Modify: `workflows/library/prompts/verified_iteration_drain/work.md`
- Modify: `workflows/library/prompts/verified_iteration_drain/review_iteration.md`
- Modify: `workflows/library/prompts/verified_iteration_drain/review_done.md`

**Owned tests:**

- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_compiles_with_exact_public_contract`
- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_binds_provider_policy_and_prompt_dependencies`
- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_lowers_prepare_check_record_and_direct_summary_return`
- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_projects_terminal_and_exhaustion_states`
- `tests/test_verified_iteration_drain.py::test_record_typed_provider_values_are_authoritative_over_compatibility_files`
- `tests/test_verified_iteration_drain.py::test_record_typed_skipped_review_preserves_no_change`
- `tests/test_verified_iteration_drain.py::test_verified_command_adapters_write_runtime_and_compatibility_outputs`

- [ ] Replace only the Task-1 absence assertion with the four Workflow Lisp
  compile/contract tests and run them RED because `drain.orc` is absent.

```bash
pytest -q tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_compiles_with_exact_public_contract tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_binds_provider_policy_and_prompt_dependencies tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_lowers_prepare_check_record_and_direct_summary_return tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_projects_terminal_and_exhaustion_states
```

  Expected RED: exit 1 with only the candidate source absence reported.
- [ ] Author module `verified_iteration_drain/drain`, entry
  `verified_iteration_drain/drain::drain`, targeting DSL 2.15.
- [ ] Preserve YAML defaults, closed provider branches, 7200/1800/3600-second
  calls, max-40 loop, review guards, terminal states, and exhaustion behavior.
- [ ] Use exact prompt-dependency sets and runtime-owned typed provider returns.
  Pass the typed verdict/review values to Record as its authoritative control
  inputs. Keep the matching token files, worker notes, findings, and blocked
  notes as semantic/YAML compatibility files; update prompt output instructions
  without testing literal prose. Represent a guard-skipped iteration review as
  an orchestration-only typed `SKIPPED` outcome while keeping the provider's
  accepted return values closed to `APPROVE|FINDINGS`.
- [ ] Add the Record authority test and run it RED before adding direct typed
  value flags; contradictory compatibility tokens must not override typed
  provider values.

```bash
pytest -q tests/test_verified_iteration_drain.py::test_record_typed_provider_values_are_authoritative_over_compatibility_files
```

- [ ] Add the skipped-review parity test and run it RED before introducing the
  typed `SKIPPED` orchestration outcome.

```bash
pytest -q tests/test_verified_iteration_drain.py::test_record_typed_skipped_review_preserves_no_change
```

- [ ] Change the dual-output adapter expectation to a Boolean runtime
  `commits_landed` value and run it RED before changing the Check adapter.

```bash
pytest -q tests/test_verified_iteration_drain.py::test_verified_command_adapters_write_runtime_and_compatibility_outputs
```

- [ ] Use typed command results for prepare/check/record and return Record's
  summary relpath directly. The Check runtime bundle exposes `commits_landed`
  as `Bool` while its YAML compatibility artifact retains the legacy lowercase
  string token.
- [ ] Run and require GREEN:

```bash
pytest -q tests/test_workflow_lisp_verified_iteration_drain.py -k 'compiles_with_exact_public_contract or binds_provider_policy or lowers_prepare or projects_terminal'
pytest -q tests/test_verified_iteration_drain.py::test_record_typed_provider_values_are_authoritative_over_compatibility_files tests/test_verified_iteration_drain.py::test_record_typed_skipped_review_preserves_no_change tests/test_verified_iteration_drain.py::test_verified_command_adapters_write_runtime_and_compatibility_outputs
pytest -q tests/test_verified_iteration_drain.py
python -m orchestrator compile workflows/library/verified_iteration_drain/drain.orc --entry-workflow verified_iteration_drain/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.commands.json
python -m orchestrator run workflows/library/verified_iteration_drain/drain.orc --entry-workflow verified_iteration_drain/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.commands.json --input target_design_path=docs/design/workflow_lisp_frontend_specification.md --input check_commands_path=workflows/examples/inputs/verified_iteration_drain/workflow_lisp_runtime_native_drain_authoring.checks.json --dry-run
```

- [ ] Complete ordered reviews and commit only the eight implementation paths
  listed above; commit this correctness amendment separately before refreezing
  the implementation review object.

## Task 3: Register And Prove The Verified Candidate

**Files:**

- Modify: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify: `docs/workflow_lisp_route_readiness_registry.json`
- Modify: `tests/test_workflow_lisp_verified_iteration_drain.py`
- Modify: `tests/test_workflow_lisp_migration_parity.py`
- Modify: `tests/test_workflow_lisp_route_readiness.py`
- Generate, ignored: `artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-candidate/`

**Owned tests:**

- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_one_continue_then_done_preserves_artifact_lineage`
- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_blocked_stalled_and_exhausted_paths`
- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_retry_refreshes_dependencies_and_resume_is_idempotent`
- `tests/test_workflow_lisp_migration_parity.py::test_checked_in_verified_parity_target_has_complete_candidate_contract`

- [ ] Add the four tests and run RED before registration/runtime harness edits.

```bash
pytest -q tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_one_continue_then_done_preserves_artifact_lineage tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_blocked_stalled_and_exhausted_paths tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_orc_retry_refreshes_dependencies_and_resume_is_idempotent tests/test_workflow_lisp_migration_parity.py::test_checked_in_verified_parity_target_has_complete_candidate_contract
```

  Expected RED: exit 1 because runtime parity harness/registration is absent;
  candidate compile tests from Task 2 remain green.
- [ ] Execute the isolated mocked-provider scenarios. Prove iteration uniqueness,
  exact prompt snapshots, all verdict/review/check/ledger/status/summary lineage,
  Record idempotence, and same-ID retry/resume behavior.
- [ ] Register all nine evidence roles: seven executable command roles plus
  shared-validation and baseline-characterization report roles.
- [ ] Register the parity target with
  `promotion_eligibility.eligible_for_primary_surface=false` and blocked reason
  `candidate evidence only until the promotion task passes`. Register the exact
  route tuple `route_label=migration_candidate`,
  `readiness_label=leaf_runtime_candidate`, `lowering_route=wcc_m4`,
  `lowering_schema_version=2`, `copy_safety=migration_evidence_only`, and
  `parity_constrained=true`. Do not use the final tuple yet.
- [ ] Run and require GREEN:

```bash
pytest -q tests/test_workflow_lisp_verified_iteration_drain.py
pytest -q tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_route_readiness.py -k 'verified_iteration_drain or current_parity_targets_and_checked_in_registry_agree'
python -m orchestrator workflow-lisp-route-readiness --check
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-candidate --target verified_iteration_drain --require-non-regressive
```

  The advisory report must be non-regressive and must still identify the YAML
  source as primary.
- [ ] Complete ordered reviews and commit only the five tracked files.

## Task 4: Promote Verified-Iteration And Rebuild Final Evidence

**Files:**

- Modify: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify: `docs/workflow_lisp_route_readiness_registry.json`
- Modify: `tests/test_workflow_lisp_route_readiness.py`
- Modify: `tests/test_workflow_lisp_verified_iteration_drain.py`
- Modify: `workflows/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/design/verified_iteration_drain.md`
- Modify: `docs/design/README.md`
- Modify: `docs/index.md`
- Modify: `docs/workflow_yaml_orc_gap_list.md`
- Modify: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Modify: `tests/test_workflow_yaml_orc_gap_list.py`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: `tests/test_yaml_deprecation_surface.py`
- Generate, ignored: `artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/`

**Owned tests:**

- `tests/test_workflow_lisp_route_readiness.py::test_verified_route_is_promotion_eligible_and_parity_constrained`
- `tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_post_promotion_orc_smoke_is_fresh`
- `tests/test_yaml_deprecation_surface.py::test_verified_catalog_routes_new_launches_to_orc_and_retains_yaml_compatibility`

- [ ] Add the three tests and run RED against candidate readiness/catalog state.

```bash
pytest -q tests/test_workflow_lisp_route_readiness.py::test_verified_route_is_promotion_eligible_and_parity_constrained tests/test_workflow_lisp_verified_iteration_drain.py::test_verified_post_promotion_orc_smoke_is_fresh tests/test_yaml_deprecation_surface.py::test_verified_catalog_routes_new_launches_to_orc_and_retains_yaml_compatibility
```

  Expected RED: exit 1 because candidate readiness/catalog still retain YAML as
  primary; Task-3 candidate parity remains green.
- [ ] Flip the target to
  `promotion_eligibility.eligible_for_primary_surface=true` and remove the
  obsolete blocked reason. Set the exact registry tuple to
  `route_label=wcc_default`, `readiness_label=promotion_eligible`,
  `lowering_route=wcc_m4`, `lowering_schema_version=2`,
  `copy_safety=preferred_current_guidance`, and `parity_constrained=true`.
  Validate target/registry agreement before report generation.
- [ ] Generate the final report only after that bound identity is final:

```bash
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final --target verified_iteration_drain --require-promotable
```

- [ ] Route the catalog/documented CLI to `.orc`, close only the verified family
  gates, retain the YAML file, and record the report path in its roadmap row.
- [ ] Run and require GREEN:

```bash
pytest -q tests/test_workflow_lisp_verified_iteration_drain.py tests/test_workflow_lisp_route_readiness.py -k 'verified or current_parity_targets_and_checked_in_registry_agree'
pytest -q tests/test_workflow_yaml_orc_gap_list.py tests/test_workflow_lisp_drain_roadmap_routing.py tests/test_yaml_deprecation_surface.py -k 'verified or task_5 or author_routing'
python -m orchestrator workflow-lisp-route-readiness --check
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final --target verified_iteration_drain --require-promotable
```

  Any later manifest/registry edit invalidates this report and requires the last
  command again. The fresh smoke is the named pytest runtime test, not a live
  external provider call.
- [ ] Complete ordered reviews and commit only the fourteen tracked files.

## Task 5: Freeze The Bounded Watchdog Port Design

**Files:**

- Create: `docs/plans/2026-07-18-generic-run-watchdog-orc-port-design.md`
- Create: `tests/test_workflow_lisp_generic_run_watchdog.py`

**Owned tests:**

- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_yaml_baseline_contract_is_frozen`
- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_port_source_is_absent_at_design_boundary`
- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_port_design_closes_both_typed_branches`

- [ ] Add the first two passing characterizations and the design-contract test
  RED because the bounded design is absent.

```bash
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_port_design_closes_both_typed_branches
```

  Expected RED: exit 1 because the bounded design document is absent; both
  characterization nodes pass.
- [ ] Specify exact module/entry, six public inputs, four outputs, branch-local
  provider policies, probe/no-action/repair/publication flow, compatibility
  mirror, prompt dependency, retry/resume behavior, and parity cases.
- [ ] Explicitly defer the unrelated watchdog recovery-status backlog proposal.
- [ ] Run and require GREEN:

```bash
pytest --collect-only -q tests/test_workflow_lisp_generic_run_watchdog.py tests/test_generic_run_watchdog.py
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py -k 'baseline_contract or source_is_absent or port_design'
```

- [ ] Complete ordered design reviews and commit only the two listed paths.

## Task 6: Add The Watchdog Adapter And Extern Harness

**Files:**

- Create: `workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.providers.json`
- Create: `workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.prompts.json`
- Create: `workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.commands.json`
- Modify: `tests/test_workflow_lisp_generic_run_watchdog.py`
- Modify: `tests/test_generic_run_watchdog.py`
- Modify: `workflows/library/scripts/probe_orchestrator_run.py`
- Modify: `workflows/library/scripts/publish_run_watchdog_result.py`

**Owned tests:**

- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_extern_manifests_bind_existing_assets`
- `tests/test_generic_run_watchdog.py::test_watchdog_commands_write_runtime_and_compatibility_outputs`
- `tests/test_generic_run_watchdog.py::test_watchdog_publisher_accepts_typed_repair_fields_without_parsing_control_state`

- [ ] Add the tests and run RED only on missing manifests/runtime bundle support.

```bash
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_extern_manifests_bind_existing_assets tests/test_generic_run_watchdog.py::test_watchdog_commands_write_runtime_and_compatibility_outputs tests/test_generic_run_watchdog.py::test_watchdog_publisher_accepts_typed_repair_fields_without_parsing_control_state
```

  Expected RED: exit 1 with missing manifests/bundle API only; existing YAML
  clean and repair tests remain green.
- [ ] Add exactly two command externs (probe/publish), one prompt extern, and two
  compiler-known provider branches with branch-local model/effort literals.
- [ ] Make probe/publish honor `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` while preserving
  YAML files. Add typed publisher inputs; do not derive control state from prose
  or compatibility JSON.
- [ ] Run and require GREEN:

```bash
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py -k 'extern_manifests or commands_write_runtime or publisher_accepts_typed'
pytest -q tests/test_generic_run_watchdog.py
```

- [ ] Complete ordered reviews and commit only the seven listed paths.

## Task 7: Implement The Watchdog `.orc` Candidate

**Files:**

- Create: `workflows/library/generic_run_watchdog/watchdog.orc`
- Modify: `tests/test_workflow_lisp_generic_run_watchdog.py`
- Modify: `tests/test_generic_run_watchdog.py`
- Modify: `workflows/library/prompts/generic_run_watchdog/repair_run_failure.md`

**Owned tests:**

- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_compiles_with_exact_six_input_four_output_contract`
- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_clean_path_skips_provider_and_publishes_no_action`
- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_repair_path_selects_exact_provider_policy`
- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_prompt_dependency_retry_and_resume_contract`

- [ ] Replace the Task-5 source-absence assertion with these tests and run RED
  because `watchdog.orc` is absent.

```bash
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_compiles_with_exact_six_input_four_output_contract tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_clean_path_skips_provider_and_publishes_no_action tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_repair_path_selects_exact_provider_policy tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_prompt_dependency_retry_and_resume_contract
```

  Expected RED: exit 1 with only the candidate source absence reported.
- [ ] Implement module `generic_run_watchdog/watchdog`, entry
  `generic_run_watchdog/watchdog::watchdog`, targeting DSL 2.15.
- [ ] Preserve exactly six public inputs and four outputs. Keep Codex
  `gpt-5.4/high` and Claude `opus/high` branch-local with timeout 7200.
- [ ] Use typed probe, no-action/repair union, provider return, publisher input,
  and final result. Preserve the repair-result target as compatibility mirror.
- [ ] Update prompt output instructions to the typed runtime return without
  literal-prose assertions.
- [ ] Run and require GREEN:

```bash
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py -k 'compiles_with_exact or clean_path or repair_path or prompt_dependency'
python -m orchestrator compile workflows/library/generic_run_watchdog/watchdog.orc --entry-workflow generic_run_watchdog/watchdog::watchdog --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.commands.json
python -m orchestrator run workflows/library/generic_run_watchdog/watchdog.orc --entry-workflow generic_run_watchdog/watchdog::watchdog --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.commands.json --input target_run_id=task5-watchdog-dry-run --dry-run
```

- [ ] Complete ordered reviews and commit only the four listed paths.

## Task 8: Register And Prove The Watchdog Candidate

**Files:**

- Modify: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify: `docs/workflow_lisp_route_readiness_registry.json`
- Modify: `tests/test_workflow_lisp_generic_run_watchdog.py`
- Modify: `tests/test_workflow_lisp_migration_parity.py`
- Modify: `tests/test_workflow_lisp_route_readiness.py`
- Generate, ignored: `artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-candidate/`

**Owned tests:**

- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_both_branches_preserve_artifact_lineage`
- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_resume_reuses_provider_and_publishes_once`
- `tests/test_workflow_lisp_migration_parity.py::test_checked_in_watchdog_parity_target_has_complete_candidate_contract`

- [ ] Add the tests and run RED before runtime harness/registration edits.

```bash
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_both_branches_preserve_artifact_lineage tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_orc_resume_reuses_provider_and_publishes_once tests/test_workflow_lisp_migration_parity.py::test_checked_in_watchdog_parity_target_has_complete_candidate_contract
```

  Expected RED: exit 1 because runtime parity harness/registration is absent;
  Task-7 candidate compile and branch tests remain green.
- [ ] Exercise isolated NO and YES paths, both provider choices, retry snapshot
  refresh, completed-provider reuse, and publication-once resume.
- [ ] Register the seven executable roles plus shared-validation and baseline-
  characterization evidence. Set target eligibility false with blocked reason
  `candidate evidence only until the promotion task passes`, and register exact
  candidate tuple `route_label=migration_candidate`,
  `readiness_label=leaf_runtime_candidate`, `lowering_route=wcc_m4`,
  `lowering_schema_version=2`, `copy_safety=migration_evidence_only`, and
  `parity_constrained=true`.
- [ ] Run and require GREEN:

```bash
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py
pytest -q tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_route_readiness.py -k 'generic_run_watchdog or current_parity_targets_and_checked_in_registry_agree'
python -m orchestrator workflow-lisp-route-readiness --check
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-candidate --target generic_run_watchdog --require-non-regressive
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final --target verified_iteration_drain --require-promotable
```

  The watchdog advisory report must be non-regressive and keep YAML primary.
  The second parity command regenerates and validates verified-final against the
  changed shared manifest/registry before commit; an older verified report is
  not admissible.
- [ ] Complete ordered reviews and commit only the five tracked files.

## Task 9: Promote Watchdog And Rebuild Final Evidence

**Files:**

- Modify: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify: `docs/workflow_lisp_route_readiness_registry.json`
- Modify: `tests/test_workflow_lisp_route_readiness.py`
- Modify: `tests/test_workflow_lisp_generic_run_watchdog.py`
- Modify: `workflows/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `docs/workflow_yaml_orc_gap_list.md`
- Modify: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Modify: `tests/test_workflow_yaml_orc_gap_list.py`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: `tests/test_yaml_deprecation_surface.py`
- Generate, ignored: `artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final/`

**Owned tests:**

- `tests/test_workflow_lisp_route_readiness.py::test_watchdog_route_is_promotion_eligible_and_parity_constrained`
- `tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_post_promotion_both_branch_smoke_is_fresh`
- `tests/test_yaml_deprecation_surface.py::test_watchdog_catalog_routes_new_launches_to_orc_and_retains_yaml_compatibility`

- [ ] Add the tests and run RED against candidate readiness/catalog state.

```bash
pytest -q tests/test_workflow_lisp_route_readiness.py::test_watchdog_route_is_promotion_eligible_and_parity_constrained tests/test_workflow_lisp_generic_run_watchdog.py::test_watchdog_post_promotion_both_branch_smoke_is_fresh tests/test_yaml_deprecation_surface.py::test_watchdog_catalog_routes_new_launches_to_orc_and_retains_yaml_compatibility
```

  Expected RED: exit 1 because candidate readiness/catalog still retain YAML as
  primary; Task-8 candidate parity remains green.
- [ ] Flip target eligibility true and remove its blocked reason. Set exact final
  registry tuple `route_label=wcc_default`,
  `readiness_label=promotion_eligible`, `lowering_route=wcc_m4`,
  `lowering_schema_version=2`, `copy_safety=preferred_current_guidance`, and
  `parity_constrained=true`; validate agreement, generate the strict final
  report, then change only catalog/docs routing:

```bash
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final --target generic_run_watchdog --require-promotable
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final --target verified_iteration_drain --require-promotable
```

- [ ] Close only watchdog family gates and retain its YAML source.
- [ ] Run and require GREEN:

```bash
pytest -q tests/test_workflow_lisp_generic_run_watchdog.py tests/test_workflow_lisp_route_readiness.py -k 'watchdog or current_parity_targets_and_checked_in_registry_agree'
pytest -q tests/test_workflow_yaml_orc_gap_list.py tests/test_workflow_lisp_drain_roadmap_routing.py tests/test_yaml_deprecation_surface.py -k 'watchdog or task_5 or author_routing'
python -m orchestrator workflow-lisp-route-readiness --check
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final --target generic_run_watchdog --require-promotable
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final --target verified_iteration_drain --require-promotable
```

  Rerun both strict parity commands after any bound manifest/registry edit.
  Both are mandatory because the shared edit invalidates the prior verified
  report as well as the watchdog candidate report.
- [ ] Complete ordered reviews and commit only the twelve tracked files.

## Task 10: Close Roadmap Task 5 And Hand Off Both Deletion Gates

**Files:**

- Modify: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/workflow_yaml_estate_triage.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: this plan
- Generate, ignored: `artifacts/work/YAML-RETIREMENT-TASK5/final/collect.log`
- Generate, ignored: `artifacts/work/YAML-RETIREMENT-TASK5/final/broad.log`
- Generate, ignored: `artifacts/work/YAML-RETIREMENT-TASK5/final/broad.exit`

**Owned tests:**

- `tests/test_workflow_lisp_procedure_first_migrations.py::test_yaml_retirement_handoff_names_both_promoted_port_replacements`
- `tests/test_workflow_lisp_drain_roadmap_routing.py::test_yaml_task_5_is_complete_and_routes_next_to_task_6`
- `tests/test_workflow_lisp_procedure_first_migrations.py::test_yaml_task_5_keeps_both_old_sources_pending_their_deletion_gates`

- [ ] Add the tests and run exact RED:

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py::test_yaml_retirement_handoff_names_both_promoted_port_replacements tests/test_workflow_lisp_drain_roadmap_routing.py::test_yaml_task_5_is_complete_and_routes_next_to_task_6 tests/test_workflow_lisp_procedure_first_migrations.py::test_yaml_task_5_keeps_both_old_sources_pending_their_deletion_gates
```

  Expected RED: exit 1 because the handoff/program still describe Task 5 as
  current. Then update the handoff evidence/replacement fields and regenerate
  the triage projection without removing either YAML queue path.
- [ ] Mark roadmap Task 5 complete and current selector Task 6. State that
  reference/run-consumer evidence remains a Task-6 pre-deletion gate governed by
  `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`; Task 5 does
  not invent an ad hoc scanner or queue either source for deletion.
- [ ] Run exact collection/focused gates:

```bash
mkdir -p artifacts/work/YAML-RETIREMENT-TASK5/final
pytest --collect-only -q tests/test_workflow_lisp_verified_iteration_drain.py tests/test_workflow_lisp_generic_run_watchdog.py > artifacts/work/YAML-RETIREMENT-TASK5/final/collect.log
pytest -q tests/test_verified_iteration_drain.py tests/test_generic_run_watchdog.py tests/test_workflow_lisp_verified_iteration_drain.py tests/test_workflow_lisp_generic_run_watchdog.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_route_readiness.py tests/test_workflow_yaml_orc_gap_list.py tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_drain_roadmap_routing.py tests/test_yaml_deprecation_surface.py
python -m orchestrator workflow-lisp-route-readiness --check
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final --target verified_iteration_drain --require-promotable
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final --target generic_run_watchdog --require-promotable
```

- [ ] Create the final ignored directory, then run the broad suite with these
  exact commands:

```bash
tmux new-session -d -s yaml-task5-broad "cd /home/ollie/Documents/agent-orchestration && pytest -q -n 16 --dist=worksteal > artifacts/work/YAML-RETIREMENT-TASK5/final/broad.log 2>&1; status=\$?; printf '%s\n' \"\$status\" > artifacts/work/YAML-RETIREMENT-TASK5/final/broad.exit; exit \"\$status\""
```

  Compare exact failed IDs/signatures and skipped IDs with the Task-13 baseline;
  passing-test growth is expected, any failed/skipped delta is not.
- [ ] Audit all ten task commits and both review trailers per commit. Verify both
  retained YAML byte digests equal their Task-1/Task-5 baselines.
- [ ] Complete final holistic specification and quality reviews, then commit
  only the seven tracked files.

## Completion Contract

Task 5 is complete only when all of the following are true:

- exactly the two named dedicated `.orc` sources exist;
- both families preserve their public functional behavior through typed
  contracts and the accepted private-mechanics differences;
- both parity targets and readiness entries validate;
- both typed parity reports pass with complete role and artifact lineage;
- launch routing selects `.orc` for both families;
- fresh `.orc` executions pass after promotion;
- each family has passed ordered independent reviews;
- the handoff leaves both reference and supported-run gates explicitly pending
  for Task 6's reviewed generic scanner;
- both old YAML sources remain present and unchanged; and
- roadmap/status docs claim Task 5 completion only, with Task 6 deletion and
  Task 7 parser retirement still open.

After the reviewed Task-5 closure commit, proceed directly to the existing Task-6
execution plan without asking for confirmation. Continue excluding all
security-related work.
