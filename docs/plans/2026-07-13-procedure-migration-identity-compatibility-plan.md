# Procedure-Migration Identity Compatibility Prerequisites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the generic lowering-identity, inline checkpoint/provenance, retirement-evidence, and checksum-rejection prerequisites required before the tracked-plan procedure-first pilot source may change.

**Architecture:** Resolve every monomorphic procedure's module-level lowering decision once in the compiler after specialization/effect recomputation, store the resolved tuple on Stage 3, and make classic and WCC lowering consume that exact mapping. Repair WCC inline checkpoint and source-map behavior at the generic inline boundary, add a standalone evidence-only retirement-record validator, characterize existing root/callee checksum rejection, amend only the remaining source-map/spec/acceptance and pilot gates, then hand execution back to the existing pilot plan without editing its `.orc` source in this plan.

**Tech Stack:** Python 3.11, frozen dataclasses and JSON validation, Workflow Lisp typed AST/WCC/classic lowering, build artifacts and source maps, orchestrator resume/runtime, pytest and pytest-xdist.

---

## Scope, authority, and handoff

- Governing target: `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`.
- Baseline contract: `docs/design/workflow_lisp_procedure_first_reuse_contract.md`.
- Handoff plan: `docs/plans/2026-07-13-procedure-first-pilot-plan.md`.
- This plan implements generic prerequisites A-D and contract/gate amendments only. It must not edit `workflows/examples/design_plan_impl_review_stack_v2_call.orc`, regenerate `tests/baselines/procedure_first/tracked_plan_phase.json`, or claim that an old run resumes across changed source.
- The future general atomic upgrader owns supported cross-source old-run resume. The separate checksum-compatible scoped projection audit is owned by `docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md`; it is out of scope here and must land before production migration waves, not before this internal pilot.
- Do not add a migration CLI, runtime alias/remap table, effective-call-site lowering carrier, recursive projection audit, family allowlist, or code keyed to tracked-plan names.
- Approach tradeoff: compiler-owned resolved tuples make direct low-level lowering calls more explicit; future tests or libraries that bypass Stage 3 must now resolve procedures deliberately before calling a lowerer. The evidence-only validator also makes record producers spell out every store, owner, attestation, digest, and identity row rather than inferring eligibility from route labels.

## Protected working-tree and staging guard

These seven user-owned paths remain outside every task:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Before the first edit, save `git status --short` as guard evidence. Before every commit, run both commands below:

```bash
git diff --cached --name-only
git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md'
```

The second command must print nothing. The full staged list must be a subset of the active task's `Files` list. Never stage by directory, never use `git add -A`/`git add .`, and never restore, rewrite, or clean a protected path.

## File responsibility map

- `tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.orc`: generic explicit-inline, explicit-private, and auto fixture, with a WCC-M4-capable loop elsewhere in the retained workflow so the pilot-shaped inline call is outside the classic iteration override.
- `tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.{providers,prompts,commands}.json`: deterministic compile/build extern manifests for that fixture.
- `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json`: compact accepted pre-edit projection for the exact eight broad-suite failures, their categories, normalized signatures/digests, command, date, and starting commit; its accepted content is pinned to commit `50f78791320c540181946fb3a29dce355b19fed3`.
- `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json`: provenance authority for the original `d5eb0043` values, normalization defects, corrected algorithm/digests, and content addresses of the retained raw pre-implementation logs; its accepted content is pinned to correction commit `b7212487764bda8ff93dc995c4ca8e1a6eec54ee`.
- `tests/baselines/procedure_first/procedure_lowering_identity_modes.{legacy,wcc_m4}.json`: normalized pre-refactor executable, Semantic IR, runtime/checkpoint, presentation, source-map, and generated-private-workflow observables.
- `tests/workflow_lisp_procedure_identity.py`: reusable normalization and content-digest helpers; strips workspace roots and excludes unrelated nondeterministic fields.
- `orchestrator/workflow_lisp/compiler.py`: sole owner of module-level resolution after specialization/effect recomputation and before route dispatch.
- `orchestrator/workflow_lisp/lowering/core.py`, `orchestrator/workflow_lisp/lowering/procedures.py`: classic consumer and the shared resolution algorithm; retain the explicitly labeled schema-1 call-local iteration override only on the legacy path.
- `orchestrator/workflow_lisp/wcc/lower.py`, `orchestrator/workflow_lisp/wcc/defunctionalize.py`: WCC consumers, inline checkpoint policy, and inline origin-note propagation.
- `orchestrator/workflow_lisp/procedure_identity_retirement.py`: evidence-only v1 record model, parser, known-store scan facts, and validator. It is not imported by resume/executor code.
- `tests/test_workflow_lisp_procedure_identity_retirement.py`: record schema, eligibility, multiset/order, digest, and runtime-isolation tests.
- `tests/test_resume_command.py`: root checksum and existing callee checksum negative characterization.
- `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md` and `docs/design/workflow_lisp_procedure_first_reuse_contract.md`: already accepted authorities, inspected by default and changed only if post-implementation symbol/path references genuinely require a status/evidence correction.
- `docs/design/workflow_lisp_source_map.md`, `specs/state.md`, `specs/acceptance/index.md`: remaining durable source-map/checksum/acceptance amendments where current text is insufficient.
- `docs/plans/2026-07-13-procedure-first-pilot-plan.md`: revised stop conditions, retirement-record production/approval gates, and handback instructions; it continues to own the family edit.

### Task 1: Freeze Generic Pre-Change Identity Observables

**Files:**
- Create before any source/test edit: `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json`
- Create only as the reviewed correction to the completed capture: `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json`
- Create: `tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.orc`
- Create: `tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.providers.json`
- Create: `tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.prompts.json`
- Create: `tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.commands.json`
- Create: `tests/workflow_lisp_procedure_identity.py`
- Create: `tests/baselines/procedure_first/procedure_lowering_identity_modes.legacy.json`
- Create: `tests/baselines/procedure_first/procedure_lowering_identity_modes.wcc_m4.json`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Test: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Capture the fresh pre-edit broad run in tmux**

Before creating or editing any implementation, fixture, or test file, use the `tmux` skill and run from repo root:

```bash
mkdir -p .orchestrate/tmp/procedure-identity-prereqs-baseline
pytest -q -n 16 --dist=worksteal 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/broad.txt
```

Expected: exactly the eight nodeids enumerated in Step 2 fail and no others. If the nodeid set differs, stop before implementation; a replacement failure cannot be categorized as baseline merely because the count remains eight.

- [ ] **Step 2: Isolate all eight baseline failures**

Run each selector separately and save its complete output under `.orchestrate/tmp/procedure-identity-prereqs-baseline/`:

```bash
pytest -q tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/output-contract.txt
pytest -q tests/test_workflow_semantic_ir.py::test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/semantic-prompt-lineage.txt
pytest -q tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/executable-ir-keys.txt
pytest -q tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/semantic-command-boundary.txt
pytest -q tests/test_provider_role_routing.py::test_design_delta_drain_defaults_route_work_to_codex_gpt54 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/provider-role.txt
pytest -q tests/test_neurips_steered_backlog_runtime.py::test_neurips_steered_backlog_runtime_drafts_gap_item_and_continues_without_relaunch 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/neurips-runtime.txt
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_is_explicit_inline_procedure 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/pilot-definition.txt
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_wrapper_uses_procedure_call 2>&1 | tee .orchestrate/tmp/procedure-identity-prereqs-baseline/pilot-callsite.txt
```

Expected: each selector fails independently with the same failure class/message observed in the broad run.

- [ ] **Step 3: Create and commit the baseline authority before implementation**

Write schema `procedure_migration_identity_compatibility_baseline.v1` with `captured_at` (UTC), `repository_commit` from `git rev-parse HEAD`, the exact broad command, and eight ordered `failures` rows. Each row contains `nodeid`, `category`, `normalized_failure_signature`, and `normalized_failure_sha256`. Normalize the isolated output by replacing the repository root with `$REPO`, pytest temp roots with `$PYTEST_TMP`, elapsed durations with `$TIME`, and Python repr memory addresses matching `at 0x[0-9A-Fa-f]+` with `at $ADDR`; do not normalize arbitrary hexadecimal values, hashes, or compared values. Retain exception/assertion type, compared values, and first substantive failure message before hashing the normalized UTF-8 text. Mark exactly the first six nodeids above `established_unrelated` and exactly the last two `intentional_pilot_red`.

```bash
git add docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json
git commit -m "test: record procedure identity prerequisite baseline"
```

Expected: the commit contains only the baseline JSON. This commit's parent is the pre-implementation checkout recorded in `repository_commit`.

Historical execution note: capture commit `d5eb004309a544bfad56b80439dc106c628f2d63`
correctly froze the eight nodeids, categories, signatures, capture time, and
pre-implementation commit, but its eight digest fields hashed the signature
projections rather than the complete normalized isolated logs. Commit
`5c4d6bdce87e1feb587201677c78b63f49925951` corrected all eight to full-log
digests; `50f78791320c540181946fb3a29dce355b19fed3` normalized the one Python repr
address that remained nondeterministic; and `bfabb614dd927a2c121f1e7220c21aa1ee180f63`
plus `ffd4503de7d40dbbadb388655adce4e140a516a0` bounded the normalizer so it
does not erase evidence. The separate correction artifact was created at
`d2440fe9bb52a478c90af4cd7bee5fcf8748f276`; its accepted review candidate at
`b7212487764bda8ff93dc995c4ca8e1a6eec54ee` adds the explicit correction
history and Task 8 review gate while binding the original and corrected values
to the retained raw logs by byte count and SHA-256. Task 8 selects the compact
baseline and this correction artifact together; it must not infer authority
from the latest commit to touch either path.

- [ ] **Step 4: Add the generic fixture**

Define `inline-plan` with explicit `:lowering inline` and provider/command structured-result steps plus a match, `private-helper` with explicit `:lowering private-workflow`, and `auto-helper` with two lowerable call sites so `auto` resolves private. Keep the `inline-plan` call outside an unrelated `loop/recur` form so both `legacy` and `wcc_m4` compile the same pilot-shaped call without entering the schema-1 iteration override. Add minimal fake provider/prompt/certified-command manifests used identically by tests and smoke commands.

- [ ] **Step 5: Add the normalized observation helper**

Implement `build_procedure_identity_observation(path, route, workspace, ...)` returning sorted JSON for: resolved typed procedures `(name, requested_mode, resolved_mode, generated_workflow_name)`; lowered authored mappings; executable projection node/step IDs and presentation keys; Semantic IR workflow/effect/node identities; runtime-plan checkpoint/program-point IDs and policies; source-map origin keys (provenance note content is tested separately in Task 4); generated path allocations; and the content bytes/digest of each generated private workflow. Normalize `repo_root`/`workspace` paths to `$REPO`/`$WORKSPACE`; omit timestamps, temp roots, object reprs, and debug-only WCC node IDs.

- [ ] **Step 6: Capture both pre-change baselines**

Run a one-off Python snippet that imports the helper, builds the fixture through `legacy` and `wcc_m4`, and writes the two sorted/indented JSON files. Review the diff and verify each baseline contains `inline`, `private-workflow`, and `auto` requested modes plus resolved names.

- [ ] **Step 7: Add characterization assertions**

Add `test_procedure_identity_modes_match_frozen_legacy_observables`, `test_procedure_identity_modes_match_frozen_wcc_m4_observables`, and `test_explicit_inline_pilot_shape_does_not_use_schema1_iteration_override`. The last test must spy on the legacy override predicate and assert zero override decisions for `inline-plan`, while both routes retain inline resolved mode and no generated inline workflow.

- [ ] **Step 8: Run collection and characterization tests**

Run: `pytest --collect-only -q tests/test_workflow_lisp_procedures.py`

Expected: collection succeeds with all three new test names.

Run: `pytest -q tests/test_workflow_lisp_procedures.py -k 'procedure_identity_modes or explicit_inline_pilot_shape'`

Expected: PASS against the pre-change compiler.

- [ ] **Step 9: Commit the characterization seam**

```bash
git add tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.orc tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.providers.json tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.prompts.json tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.commands.json tests/workflow_lisp_procedure_identity.py tests/baselines/procedure_first/procedure_lowering_identity_modes.legacy.json tests/baselines/procedure_first/procedure_lowering_identity_modes.wcc_m4.json tests/test_workflow_lisp_procedures.py
git commit -m "test: freeze procedure lowering identity observables"
```

### Task 2: Resolve Once in Stage 3 and Pass the Exact Mapping to Every Lowerer

**Files:**
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify: `orchestrator/workflow_lisp/wcc/lower.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Modify: `tests/workflow_lisp_procedure_identity.py`
- Test: `tests/test_workflow_lisp_procedures.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Test: `tests/test_workflow_lisp_lowering.py`
- Test: `tests/test_workflow_lisp_workflow_refs.py`

- [ ] **Step 1: Write RED Stage-3 ownership tests**

Add `test_stage3_returns_module_resolved_procedure_modes_and_names` and `test_stage3_resolves_lowering_once_after_specialization_and_effects`. Patch `_resolve_procedure_lowering` with a counting wrapper and assert one call per compiled module; assert every `result.typed_procedures` row has non-`None` `resolved_lowering_mode`, and every resolved-private row has its deterministic `%<source-stem>.<procedure>.v1` name.

- [ ] **Step 2: Write the RED typed-AST artifact test**

Build the generic fixture and assert `typed_frontend_ast.json` contains the same requested/resolved mode and generated name as `entry_result.typed_procedures` for all three procedures.

- [ ] **Step 3: Write RED no-recomputation tests**

Add `test_legacy_lowerer_uses_supplied_resolved_procedure_tuple` and `test_wcc_m4_lowerer_uses_supplied_resolved_procedure_tuple`. Supply a deliberately resolved private name such as `%test.resolved.helper`, patch `_resolve_procedure_lowering` to raise, and assert each low-level lowerer emits that exact generated workflow name.

- [ ] **Step 4: Verify the combined RED state**

```bash
pytest -q tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py -k 'stage3_returns_module_resolved or stage3_resolves_lowering_once or typed_frontend_ast_records_resolved_procedure_lowering or lowerer_uses_supplied_resolved'
```

Expected: FAIL because the Stage-3 tuple precedes authoritative resolution and classic/WCC still recompute. There is deliberately no intermediate GREEN or commit until both route-owned resolver calls are removed.

- [ ] **Step 5: Add the compiler-owned resolution pass and stored tuple**

In `compiler.py`, add `_resolve_stage3_procedure_lowering(state, *, workflow_path)` immediately after function normalization and post-specialization direct/transitive effect validation. It calls `_resolve_procedure_lowering(...)` once, preserves original order, and replaces `state.typed_procedures` with the resolved local tuple. Preserve specialization objects and procedure type environments exactly. Do not add a call-site carrier: `TypedProcedureDef.resolved_lowering_mode` and `generated_workflow_name` remain the Stage-3 carriers.

- [ ] **Step 6: Build one immutable mapping before route dispatch**

In `_lower_workflows_for_route`, create `resolved_procedures_by_name = MappingProxyType({p.definition.name: p for p in typed_procedures})` once from that stored tuple. Pass this exact mapping object to the selected classic or WCC lowerer and through source-map/Semantic/build consumers; do not reconstruct it inside a route.

- [ ] **Step 7: Remove classic route-owned recomputation**

Change `lower_workflow_definitions(..., typed_procedures=..., resolved_procedures_by_name=...)` to require the compiler-owned immutable mapping whenever procedures are present and fail with `procedure_lowering_unresolved` if any tuple/mapping row differs or lacks a mode. Keep the schema-1 iteration-scope recheck confined to `_lower_procedure_call`; add an explicit boolean/diagnostic observation hook for characterization, not a new semantic carrier.

- [ ] **Step 8: Remove WCC route-owned recomputation**

Delete the resolver import/call from `wcc/defunctionalize.py`; accept and pass the same compiler-owned `resolved_procedures_by_name` mapping through all M1-M4 entrypoints, including `wcc/lower.py`'s M1 legacy adapter. `_lower_workflows_for_route` creates this mapping once from the Stage-3 stored tuple and passes that exact mapping object to the selected lowerer. WCC must never run the schema-1 iteration override.

- [ ] **Step 9: Update direct low-level callers**

In `tests/test_workflow_lisp_lowering.py`, `tests/test_workflow_lisp_procedures.py`, and `tests/test_workflow_lisp_workflow_refs.py`, resolve the typed tuple explicitly with the shared resolver before calling a lowerer. Do not add an implicit fallback inside the lowerers.

- [ ] **Step 10: Run the first GREEN only after all consumers are converted**

```bash
pytest -q tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflow_refs.py -k 'stage3_returns_module_resolved or stage3_resolves_lowering_once or typed_frontend_ast_records_resolved_procedure_lowering or lowerer_uses_supplied_resolved or procedure_identity_modes or explicit_inline_pilot_shape or procedure or wcc_m4'
```

Expected: PASS. Both frozen JSON files remain byte-identical after root normalization, covering executable/Semantic/runtime/checkpoint/presentation/source-map/generated-workflow observables.

- [ ] **Step 11: Commit compiler ownership and all route conversions together**

```bash
git add orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/lowering/core.py orchestrator/workflow_lisp/lowering/procedures.py orchestrator/workflow_lisp/wcc/lower.py orchestrator/workflow_lisp/wcc/defunctionalize.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflow_refs.py tests/workflow_lisp_procedure_identity.py
git commit -m "refactor: resolve procedure lowering once in stage three"
```

### Task 3: Make WCC Inline Checkpoints Effect-Owned

**Files:**
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/workflow_lisp_procedure_identity.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Test: `tests/test_workflow_lisp_lexical_checkpoints.py`

- [ ] **Step 1: Write RED inline-policy tests and positive controls**

Add `test_wcc_inline_procedure_has_no_synthetic_workflow_call_checkpoint`, `test_wcc_inline_procedure_keeps_inner_provider_and_command_policies`, and `test_wcc_real_workflow_and_private_procedure_calls_keep_workflow_call_policy`. Inspect `runtime_plan.lexical_checkpoint_points`: no point may identify the inline `WccCall` as `step_kind=call`/`reuse_validated_workflow_call`; the body provider/command points must retain their normal policies; true workflow/private calls must retain the call policy.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_workflow_lisp_lexical_checkpoints.py -k 'wcc_inline_procedure or real_workflow_and_private'`

Expected: FAIL because `_effect_boundary_checkpoint_point_payload` currently treats every `WccCall` as a workflow call.

- [ ] **Step 3: Implement the minimal WCC fix**

In `_defunctionalize_body`, do not append a checkpoint for an inline procedure's outer `WccCall`. Let `_lower_wcc_procedure_call` pass the same checkpoint list into its child body so actual provider, command, view, transition, and nested workflow-call effects append their ordinary points. Keep private-workflow procedures on the true call path.

- [ ] **Step 4: Preserve the frozen baseline with one reviewed delta**

Keep both pre-change JSON files unchanged. Update the comparison helper to remove only the baseline's synthetic inline-call checkpoint row before equality comparison, then require every remaining executable/Semantic/runtime/checkpoint/presentation/generated-workflow field to match exactly. A missing inner-effect point or any other delta remains a failure.

- [ ] **Step 5: Run checkpoint tests GREEN**

Run the Step 2 selector, then `pytest -q tests/test_workflow_lisp_lexical_checkpoints.py`.

Expected: PASS; no synthetic inline call/frame policy and all positive controls remain.

- [ ] **Step 6: Commit checkpoint ownership**

```bash
git add tests/test_workflow_lisp_lexical_checkpoints.py tests/test_workflow_lisp_procedures.py tests/workflow_lisp_procedure_identity.py orchestrator/workflow_lisp/wcc/defunctionalize.py
git commit -m "fix: keep inline checkpoints owned by inner effects"
```

### Task 4: Persist WCC Inline Definition and Call-Site Provenance

**Files:**
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Test: `tests/test_workflow_lisp_source_map.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Write RED source-map and build tests**

Add `test_wcc_inline_generated_provider_and_match_entries_keep_definition_and_callsite_notes` and `test_build_persists_wcc_inline_procedure_notes`. Compile/build the generic fixture through WCC M4, inspect structured `SourceMapEntry.notes` for each inline provider and match step, and require one note starting `procedure definition at` and one starting `procedure call site at`. Do not parse those notes for spans or identity.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_build_artifacts.py -k 'wcc_inline_generated or persists_wcc_inline_procedure_notes'`

Expected: FAIL because the WCC inline child context drops the merged notes.

- [ ] **Step 3: Propagate existing notes into the WCC child context**

In `_lower_wcc_procedure_call`, compute:

```python
procedure_notes = _merge_origin_notes(
    context.origin_notes,
    _procedure_provenance_notes(call_source, procedure, typed_procedures=context.typed_procedures),
)
child_context = replace(context, ..., origin_notes=procedure_notes)
```

Use the existing helper/note carrier; do not change `workflow_lisp_source_map.v1` or add a second provenance structure.

- [ ] **Step 4: Prove provider, match, and checkpoint lineage persists**

Run the Step 2 selector plus `pytest -q tests/test_workflow_lisp_procedures.py -k 'procedure_identity_modes'`.

Expected: PASS; persisted `source_map.json` provider/match entries and checkpoint source-lineage origins resolve to entries containing both labels.

- [ ] **Step 5: Commit provenance propagation**

```bash
git add orchestrator/workflow_lisp/wcc/defunctionalize.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_procedures.py
git commit -m "fix: persist wcc inline procedure provenance notes"
```

### Task 5: Add the Evidence-Only Retirement Record Model and Validator

**Files:**
- Create: `orchestrator/workflow_lisp/procedure_identity_retirement.py`
- Create: `tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json`
- Create: `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Test: `tests/test_workflow_lisp_procedure_identity_retirement.py`

- [ ] **Step 1: Write RED valid-record and parser tests**

Define schema `workflow_lisp_procedure_identity_retirement.v1`. The valid fixture must contain migration/repository/compiler metadata; retained public entry; callee eligibility facts (`exported=false`, `registered_public_entry=false`, `public=false`, `route_promoted=false`, `route_live=false`); retained-wrapper evidence; supporting labels; known stores with root, owner, query version/time, normalized scan digest, terminal/nonterminal/call-frame/consumer counts, and explicit owner attestation; `external_store_absence: "not_asserted"`; old/new content-addressed source and production artifacts; complete identity-delta rows; artifact keyed-multiset rows with counts; separate execution order; lineage notes; new-ID clean/resume evidence; root/callee checksum evidence; and `runtime_directives: []`. Any owner/attestation in this JSON is explicitly fictional test data and must never be copied into pilot evidence.

- [ ] **Step 2: Write RED fail-closed eligibility tests**

Parameterize mutations that set exported/registered/public/promoted/live true; remove a store owner or attestation; claim external absence; set a supported nonterminal/call-frame consumer count; or replace substantive facts with a route label. Expect stable issue codes such as `procedure_identity_retirement_public_boundary`, `..._known_store_unowned`, `..._attestation_missing`, and `..._external_absence_asserted`.

- [ ] **Step 3: Write RED ambiguity and no-remap tests**

Reject duplicate `(identity_kind, old_identity)` or `(identity_kind, new_identity)` rows, identities marked both preserved/retired or preserved/new, incomplete identity domains, duplicate ambiguous artifact keys without an explicit `count`, mismatched artifact multisets/order evidence, and any nested key named `runtime_remap`, `remap_directive`, `identity_aliases`, or `old_to_new_map`. Assert the library is not imported by `orchestrator.cli.commands.resume`, `orchestrator.workflow.executor`, or `orchestrator.workflow.calls`.

- [ ] **Step 4: Verify RED**

Run: `pytest --collect-only -q tests/test_workflow_lisp_procedure_identity_retirement.py && pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py`

Expected: collection succeeds, then FAIL with `ModuleNotFoundError` for the new production module.

- [ ] **Step 5: Implement frozen record types and strict parsing**

Create focused frozen dataclasses (`ContentAddressedArtifact`, `KnownStateStoreEvidence`, `IdentityDeltaRow`, `ArtifactContractKey`, `ArtifactMultisetRow`, `ExecutionOrderEntry`, `ProcedureIdentityRetirementRecord`, `RetirementIssue`, `RetirementValidationResult`) plus `load_retirement_record(path)` and `validate_retirement_record(record, *, repo_root)`. Parsing must reject unknown/mistyped structural fields and preserve all substantive facts; validation returns issues and never mutates state.

- [ ] **Step 6: Implement content and store-evidence validation**

Require `sha256:` digests to match retained files; require old and new typed AST, Semantic IR, executable IR, runtime plan, lexical checkpoint points, and source-map artifacts; require all identity domains (`workflow`, `call_frame`, `executable_node`, `step`, `presentation_key`, `program_point`, `checkpoint`, `state_allocation`, `source_map_origin`); compare artifact contracts as keyed multisets independently from ordered execution; require new-ID run/resume and both checksum evidence blocks. Treat labels as supporting evidence only.

- [ ] **Step 7: Add a generic known-store scan function without a CLI**

Implement `scan_known_state_store(root, *, retired_identities, query_version)` to enumerate top-level state, nested call frames, checkpoint indexes/records, retained manifests, and supported identity-addressing metadata; return normalized sorted counts and a SHA-256 digest. It must not invent an owner/attestation or claim anything about external stores.

- [ ] **Step 8: Run validator tests GREEN**

Run: `pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py`

Expected: PASS for the valid evidence fixture and PASS for every negative rejection. Confirm no CLI or runtime import was added.

- [ ] **Step 9: Commit the evidence library**

```bash
git add orchestrator/workflow_lisp/procedure_identity_retirement.py tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json tests/test_workflow_lisp_procedure_identity_retirement.py
git commit -m "feat: validate procedure identity retirement evidence"
```

### Task 6: Characterize Root and Callee Checksum Rejection

**Files:**
- Modify: `tests/test_resume_command.py`
- Test: `tests/test_resume_command.py`

- [ ] **Step 1: Write the root-checksum negative test**

Add `test_default_resume_root_checksum_mismatch_is_pre_executor_and_byte_immutable`. Create an old `.orc` run tree containing state, call frame, checkpoint, artifact, ledger, and sidecar files; hash the entire run-root relative-path/byte multiset; change only root source; invoke `resume_workflow(run_id, repair=False, force_restart=False)` with default observability and no override flags. Patch `WorkflowExecutor` and provider/command entrypoints to fail if called.

- [ ] **Step 2: Run the root test before changing production code**

Run: `pytest -q tests/test_resume_command.py::test_default_resume_root_checksum_mismatch_is_pre_executor_and_byte_immutable`

Expected: PASS on existing behavior: exit 1, checksum error on stderr, no executor/provider/command call, and identical before/after tree digest. If it fails, stop and diagnose; do not move the guard or add retirement-record awareness.

- [ ] **Step 3: Strengthen the existing callee-checksum characterization**

Extend `test_call_subworkflow_resume_rejects_imported_workflow_checksum_mismatch` (or add `..._before_child_execution_without_remap`) with spies proving no child `WorkflowExecutor`, provider, or command execution and no child identity remap. Snapshot/classify allowed parent state deltas rather than demanding whole-tree byte identity or pre-parent-executor rejection.

- [ ] **Step 4: Run root and callee selectors**

Run: `pytest -q tests/test_resume_command.py -k 'root_checksum_mismatch_is_pre_executor or imported_workflow_checksum_mismatch or before_child_execution_without_remap'`

Expected: PASS; root is byte-immutable/pre-executor, callee fails at the child boundary with ordinary parent metadata allowed.

- [ ] **Step 5: Commit checksum evidence**

```bash
git add tests/test_resume_command.py
git commit -m "test: characterize procedure retirement checksum rejection"
```

### Task 7: Amend Remaining Contracts and the Pilot Handoff

**Files:**
- Inspect by default; modify only for genuine post-implementation status/evidence references: `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
- Inspect by default; modify only for genuine post-implementation status/evidence references: `docs/design/workflow_lisp_procedure_first_reuse_contract.md`
- Modify: `docs/design/workflow_lisp_source_map.md`
- Modify only if current wording is insufficient: `specs/state.md`
- Modify only if current wording is insufficient: `specs/acceptance/index.md`
- Modify: `docs/plans/2026-07-13-procedure-first-pilot-plan.md`

- [ ] **Step 1: Confirm the already accepted target and reuse contract**

Inspect the accepted status and strict-default/narrow-retirement amendment already landed by routing commit `61c79cb4`. Do not re-accept, reword, or re-amend either authority. Modify only an implementation-status, symbol, test, or evidence reference if the completed Tasks 1-6 prove the checked-in reference factually stale; keep the projection-integrity follow-up out of scope.

- [ ] **Step 2: Amend the remaining source-map contract**

Document that WCC inline child contexts merge `_procedure_provenance_notes` through `_merge_origin_notes`, and persisted provider/match/checkpoint lineage contains definition and consuming-call-site notes. State explicitly that `workflow_lisp_source_map.v1` is unchanged.

- [ ] **Step 3: Clarify normative checksum/upgrader text only where missing**

If `specs/state.md`/`specs/acceptance/index.md` do not already say it, add: root changed-source default resume rejects before executor construction and mutation; callee mismatch rejects before child execution/remap while parent metadata may exist; identity equality alone is not cross-source resume evidence; a future tested atomic upgrader must own checksum/program identity. Do not specify recursive projection auditing here.

- [ ] **Step 4: Rewrite the pilot prerequisites and stop conditions**

Make this plan's focused selectors and reviews prerequisites to the pilot source edit. Preserve the frozen old baseline. Qualify the old “any identity change stops” rule: unreviewed or ineligible changes stop, while reviewed retired internal identities may differ only after validator approval, substantive eligibility, checksum negatives, and artifact/order review.

- [ ] **Step 5: Put known-store scans before the pilot source edit**

Before the pilot may edit `.orc`, require it to enumerate the repository workspace `.orchestrate/runs` root and every other intentionally used workspace/run root as separate prospective record entries. Run `scan_known_state_store` for each root against the old identities and retain the normalized digest/count facts. State `external_store_absence: not_asserted`; never infer absence in EasySpin, PtychoPINN, the paper repo, CI, backups, or copied workspaces unless each location is individually enumerated.

- [ ] **Step 6: Require genuine named owner attestations before editing source**

For every scanned entry, require a genuine named human owner to supply the timestamped attestation that no supported live/nonterminal run or consumer remains in that named store. An agent must never synthesize, guess, default, paraphrase, or sign an owner name or attestation. If any owner/attestation is missing, ambiguous, or cannot be independently attributed, the pilot records `STOP: missing known-store owner attestation`, keeps strict compatibility selected, and ends without asking, retrying, editing source, or fabricating evidence under the standing unattended/“do not ask” instruction.

- [ ] **Step 7: Keep full record assembly after the pilot source edit**

Only after Steps 5-6 pass may the amended pilot make its one `.orc` edit. It then builds content-addressed new artifacts, combines them with retained old source/build artifacts and the pre-edit genuine store evidence, generates the full identity delta/artifact multiset/execution order/new-ID run-resume evidence, validates the complete record, obtains independent specification/runtime-state approval, and only then accepts reviewed retired identities. The record is evidence, never an input to run/resume. Make no cross-source old-run resume claim.

- [ ] **Step 8: Verify contract consistency**

Run:

```bash
rg -n "strict.compat|reviewed_internal_identity_retirement|external_store_absence|atomic.*upgrader|procedure definition|call site|call-site|projection-integrity" docs/design/workflow_lisp_procedure_migration_identity_compatibility.md docs/design/workflow_lisp_procedure_first_reuse_contract.md docs/design/workflow_lisp_source_map.md specs/state.md specs/acceptance/index.md docs/plans/2026-07-13-procedure-first-pilot-plan.md
rg -n "preserve.*checkpoint.*exact|any persisted checkpoint|old.*resume.*new|external.*absent" docs/design/workflow_lisp_procedure_first_reuse_contract.md docs/plans/2026-07-13-procedure-first-pilot-plan.md
```

Expected: the first search finds the new rule at each owning surface; the second finds no stale unconditional stop or unsupported cross-source/external-absence claim except explicitly labeled historical wording.

- [ ] **Step 9: Commit the remaining contract and handoff amendments**

```bash
git add docs/design/workflow_lisp_source_map.md docs/plans/2026-07-13-procedure-first-pilot-plan.md
git add specs/state.md specs/acceptance/index.md  # only files actually changed after the insufficiency check
git add docs/design/workflow_lisp_procedure_migration_identity_compatibility.md docs/design/workflow_lisp_procedure_first_reuse_contract.md  # only if Step 1 found a genuine post-implementation reference correction
git commit -m "docs: land procedure identity compatibility references"
```

### Task 8: Run Full Gates, Independent Reviews, and Hand Back to the Pilot

**Files:**
- Inspect without modifying: `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json`
- Inspect without modifying: `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json`
- Modify in Step 8 only: `docs/plans/2026-07-13-procedure-first-pilot-plan.md`
- If a review finds a defect, return to the owning Task 1-7, change only that task's exact `Files` list, rerun its RED/GREEN cycle, and commit there.
- Never modify the family source or frozen pilot baseline.

- [ ] **Step 1: Run focused collection**

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_lexical_checkpoints.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_procedure_identity_retirement.py tests/test_resume_command.py
```

Expected: collection succeeds.

- [ ] **Step 2: Run focused prerequisites**

```bash
pytest -q tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_lexical_checkpoints.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_procedure_identity_retirement.py tests/test_resume_command.py -k 'procedure or lowering or inline or checkpoint or source_map or retirement or checksum'
```

Expected: PASS for every prerequisite selector. The two already-checked-in pilot source-shape RED tests remain the existing pilot handoff signal until its source task executes; do not weaken or baseline-refresh them.

- [ ] **Step 3: Run a production compile/build smoke**

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.orc --entry-workflow orchestrate --provider-externs-file tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.providers.json --prompt-externs-file tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.prompts.json --command-boundaries-file tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.commands.json --emit-executable-ir .orchestrate/tmp/procedure-identity-prereqs/executable_ir.json --emit-runtime-plan .orchestrate/tmp/procedure-identity-prereqs/runtime_plan.json --emit-semantic-ir .orchestrate/tmp/procedure-identity-prereqs/semantic_ir.json --emit-source-map .orchestrate/tmp/procedure-identity-prereqs/source_map.json
pytest -q tests/test_workflow_lisp_build_artifacts.py -k 'persists_wcc_inline_procedure_notes or typed_frontend_ast_records_resolved_procedure_lowering'
```

Expected: the CLI compile exits 0 through the default WCC route and the production build-artifact smoke passes; typed AST has resolved modes/names, inline provider/match source-map notes contain both provenance labels, and checkpoint artifacts contain no synthetic inline workflow-call policy.

- [ ] **Step 4: Run the broad suite in tmux**

Use the `tmux` skill and run from repo root:

```bash
pytest -q -n 16 --dist=worksteal
```

Expected: exactly the eight nodeids selected by the accepted baseline/correction pair: the compact baseline's six `established_unrelated` rows plus its two `intentional_pilot_red` rows and no others. First verify that both files still match their pinned commits, that every correction row's nodeid/category/signature and `corrected_normalized_failure_sha256` equal the compact baseline row, and that each retained raw log still matches the correction artifact's byte count and SHA-256. Compare broad-run nodeids as an exact set, not by count. Rerun every baseline row in isolation, apply `tests.workflow_lisp_procedure_identity.normalize_procedure_prerequisite_failure_log`, and require exact equality of both `normalized_failure_signature` and the selected corrected digest; a replacement failure cannot hide behind the same nodeid or category. The two pilot rows must be:

- `tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_is_explicit_inline_procedure`
- `tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_wrapper_uses_procedure_call`

Record an isolated-rerun disposition for each of the six unrelated rows and confirm none is in a file touched by Tasks 1-7. Rerun the two named pilot tests together and require exactly their pre-source-edit assertions. A missing/replacement/new nodeid, changed normalized signature/digest, changed category/count, any regression in a touched path, or any additional pilot failure fails this gate. Do not edit the baseline JSON or pilot source merely to make the comparison pass.

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_is_explicit_inline_procedure tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_wrapper_uses_procedure_call
```

Expected: exactly two failures with the frozen pre-edit messages that `tracked-plan-phase` remains a `defworkflow` and its wrapper still uses `(call tracked-plan-phase ...)`.

- [ ] **Step 5: Obtain an independent specification/runtime-state review**

Use `@superpowers:requesting-code-review`. The reviewer must compare the implementation and docs against every prerequisite/eligibility/checksum clause in `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`, confirm no cross-source old-run claim, and confirm the record is not a runtime input. Resolve findings and rerun the whole review.

- [ ] **Step 6: Obtain an independent quality review**

Use `@superpowers:requesting-code-review` with a fresh reviewer. Require checks for one-time resolution, exact mapping propagation, normalized-observable non-tautology, real WCC positive controls, fail-closed schema validation, no family special case/CLI/remap, and protected-path scope. Resolve findings and rerun the whole review.

- [ ] **Step 7: Run final scope and staging guards**

```bash
git diff --check
git status --short
git diff --name-only -- workflows/examples/design_plan_impl_review_stack_v2_call.orc tests/baselines/procedure_first/tracked_plan_phase.json
git diff --cached --name-only
```

Expected: `git diff --check` is clean; the family source/frozen pilot baseline command prints nothing; the seven protected paths remain exactly as the initial guard recorded and are unstaged; no unrelated path is staged.

- [ ] **Step 8: Hand back to the existing pilot plan**

Modify `docs/plans/2026-07-13-procedure-first-pilot-plan.md` execution notes to record: the Task 1-7 prerequisite commit range; the checked-in compact baseline and correction-artifact paths; original capture commit/date, accepted baseline commit, and accepted correction commit; focused/compile/build/broad commands and outcomes; exact eight-nodeid/signature/digest comparison against the accepted pair; six isolated unrelated dispositions; the two exact pilot REDs; both review approvals; and the known-store scan API location. The pilot must complete its pre-edit scans and obtain genuine named-owner attestations before its source-edit task becomes selectable. Missing attestation records the explicit unattended stop and does not trigger a question or retry. Do not update `docs/index.md`, the wider roadmap selector, capability status, route-readiness registry, or migration-wave routing in this prerequisite plan.

- [ ] **Step 9: Commit the narrow handoff evidence update**

Run the protected staging guard, then:

```bash
git add docs/plans/2026-07-13-procedure-first-pilot-plan.md
git diff --cached --name-only
git commit -m "docs: hand procedure identity prerequisites to pilot"
```

Expected: the staged list contains only the pilot plan, and the commit records evidence/routing within that plan without editing the pilot source or frozen baseline.

- [ ] **Step 10: Re-run the final diff and protected-path checks**

```bash
git diff --check
git diff --exit-code 50f78791320c540181946fb3a29dce355b19fed3..HEAD -- docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json
git diff --exit-code b7212487764bda8ff93dc995c4ca8e1a6eec54ee..HEAD -- docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json
git diff --name-only "$(python -c 'import json; print(json.load(open("docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json"))["repository_commit"])')"..HEAD -- workflows/examples/design_plan_impl_review_stack_v2_call.orc tests/baselines/procedure_first/tracked_plan_phase.json
git status --short
```

Expected: diff checks pass against the explicitly accepted baseline and correction commits; the checked-in baseline pair, pilot `.orc` source, and frozen pilot contract baseline are unchanged; all seven protected paths retain their initial user-owned status and are unstaged.

## Completion gate

This plan is complete only when prerequisites A-D are generic and green; normalized legacy/WCC-M4 executable, Semantic, runtime, checkpoint/program-point, presentation, source-map-origin, state-allocation, and generated-workflow observables are unchanged except for exactly the reviewed retirement of the synthetic inline-procedure workflow-call checkpoint; the required additive WCC provenance notes pass their separate contract tests; the evidence validator and checksum characterizations pass; accepted contracts and pilot gates agree; the original pre-edit baseline capture and its separately reviewed correction artifact remain pinned to their accepted commits, with the corrected values bound to content-addressed raw logs, and the final broad/isolated runs match all eight exact nodeids, categories, normalized signatures, and corrected digests; both independent reviews approve; the narrow pilot-plan handoff evidence commit exists; protected paths are untouched/unstaged; and the pilot `.orc` source and frozen old baseline are unchanged. At that point hand off to the existing pilot plan's pre-edit scan/attestation gate; do not continue into the source migration under this plan.
