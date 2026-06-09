# Workflow Lisp Imported Generic Loop-State Consumer Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; `AGENTS.md` forbids worktrees for this repo. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove one supported imported generic future-consumer composition pattern for the Stage 10 review-loop route by hardening the existing imported `.orc` proof fixture and making only the narrow frontend repairs needed for that exact fixture to typecheck, specialize, lower, preserve strict `ReviewFindings.v1` contracts, preserve source provenance, and erase compile-time-only values from runtime-visible artifacts.

**Architecture:** Treat this as a bounded proof slice, not stdlib implementation work. Reuse the current proof owners in `tests/test_workflow_lisp_procedures.py`, `tests/test_workflow_lisp_structured_results.py`, and `tests/test_workflow_lisp_phase_stdlib.py`; only touch frontend owner modules if the hardened proof exposes a real specialization, loop-state, lowering, output-contract, provenance, or proc-ref handoff bug. Keep the supported pattern exactly to one imported generic consumer `defproc` body, keep the proof outside `std/phase.orc`, keep the bridge-owned public review-loop route unchanged, and treat shared-validation failures as evidence that the frontend lowered shape is still wrong unless a separate stop condition proves otherwise.

**Tech Stack:** Python 3, pytest, Workflow Lisp frontend modules under `orchestrator/workflow_lisp/`, shared validation/runtime reuse under `orchestrator/workflow/`, and repo-root verification commands.

---

## Governing Inputs

Use these artifacts as authority for scope and correctness:

- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections `7`, `8.8`, `10`, `11`, `13`, `16`, `44`, `51`, `57`, `63`, `74`, `95`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - Sections `12.3`, `14.1.1`, `15`, `16`, `18`, `19`, `20`, `21`, `24` Stage `9A`, `27`, `30`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-generic-loop-state-consumer-proof/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`
- `artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN/workflow-lisp-imported-generic-loop-state-consumer-proof-plan-review.json`

Current ledger fact:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is still `{"ledger_version":1,"events":[]}`.
- There is no ledger-side implementation history to reconcile; this plan should rely on the consumed design and work-item artifacts rather than implied prior execution state.

Current execution baseline:

- preserve the selected gap, target design, and baseline design authority; do not widen into stdlib implementation or runtime/shared-validation redesign
- refresh execution routing from the current review evidence rather than older blocker wording in stale duplicate plan text
- treat the current live blocker as a lowering/output-contract seam exposed by shared validation:
  - `workflow_boundary_type_invalid: structured ref ... targets unknown step ...__review-report`
  - `workflow_boundary_type_invalid: repeat_until.on_exhausted.outputs.result__findings__schema_version must be a scalar literal`
- keep the exact first-tranche exhausted-result and `ReviewFindings.v1` contract while repairing the frontend-owned lowering/output shape that shared validation is rejecting

## Fixed Scope

In scope:

- one supported imported generic consumer pattern:
  one imported generic consumer `defproc` body
- one focused imported `.orc` proof fixture that combines:
  - caller-owned `CompletedT`
  - caller-owned `InputsT`
  - compile-time `ProcRef` review/fix hooks
  - authored `loop-state`
  - ordinary `loop/recur :state`
  - ordinary `match`
  - typed `:on-exhausted`
- the exact first-tranche protocol from target-design Sections `14.1.1` and `15`:
  - `ReviewDecision` variants `APPROVE`, `REVISE`, `BLOCKED`
  - `ReviewLoopResult` variants `APPROVED`, `BLOCKED`, `EXHAUSTED`
  - `ReviewFindings.schema_version == "ReviewFindings.v1"`
  - strict `ReviewFindings.items_path` relpath contract under `artifacts/work`
- source-map/origin assertions for both the entry module and the imported consumer module
- runtime-erasure assertions proving no leaked `TypeParamRef`, `ProcRef`, provider refs, prompt refs, or generated `%loop-state` carrier names
- only the smallest owner-module repairs needed if the proof still fails with:
  - `procedure_call_unknown`
  - `type_unknown`
  - `loop_recur_state_type_invalid`
  - unresolved `TypeParamRef`
  - `workflow_boundary_type_invalid` on the ordinary lowered route, including:
    - unknown structured-ref targets for the lowered review report/findings path
    - non-literal `repeat_until.on_exhausted.outputs.result__findings__schema_version`

Out of scope:

- same-module helper `defproc` decomposition inside the imported consumer
- edits to `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- edits to `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- ordinary stdlib `review-revise-loop` implementation
- bridge retirement or public review-loop API changes
- new loop-state syntax, new `:forall` semantics, or new structural-constraint vocabulary
- edits to shared validation or runtime modules under `orchestrator/workflow/`
- new command adapters, hidden shell/Python glue, report parsing, or pointer-as-authority behavior
- redesign of shared Core Workflow AST, Semantic IR, Executable IR, SourceMap, or checkpoint identity

Stop conditions:

- if the proof only works by introducing same-module helper resolution, stop and route that as a separate prerequisite
- if the only plausible fix is in `std/phase.orc`, `phase_stdlib_typecheck.py`, or shared validation/runtime code under `orchestrator/workflow/`, stop and reopen the downstream stdlib implementation slice or prerequisite design instead
- if the failing seam is actually missing generic specialization or structural-constraint machinery outside this composed proof, stop and hand it back to the relevant prerequisite slice
- if the only way to make the proof pass is to weaken the exact first-tranche exhausted-result or `ReviewFindings.v1` contract, stop and reopen the governing design instead of relaxing this slice

## Locked Decisions

Do not reopen these during implementation:

- the supported pattern is exactly one imported generic consumer `defproc` body
- same-module helper decomposition remains unsupported in this slice
- review/fix hooks remain compile-time-only `ProcRef` values
- the proof fixture remains outside `std/phase.orc`
- `ReviewFindings.items_path` remains a strict relpath contract under `artifacts/work`
- `ReviewFindings.schema_version` remains the exact literal `"ReviewFindings.v1"`
- approved and blocked terminal payload fields come from the current review decision, not carried-state surrogates
- `REVISE` is iteration-local and must not be a terminal `ReviewLoopResult` variant
- typed state and validated artifact values remain authority; reports are views
- `loop/recur` stays on the ordinary shared `repeat_until` lowering path
- typed `:on-exhausted` projects from authored loop-frame outputs, not bridge-owned hidden state
- runtime-visible artifacts must remain free of `TypeParamRef`, `ProcRef`, provider refs, prompt refs, and generated `%loop-state` carrier names

## File Map

Primary proof owners:

- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_structured_results.py`

Shared regression owners to touch only if needed:

- `tests/test_workflow_lisp_loop_recur.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

Frontend owner modules to edit only if the hardened proof exposes a real bug:

- `orchestrator/workflow_lisp/procedure_typecheck.py`
- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/loop_state.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/lowering/procedures.py`
- `orchestrator/workflow_lisp/lowering/control_loops.py`
- `orchestrator/workflow_lisp/lowering/values.py`
- `orchestrator/workflow_lisp/source_map.py`

Do not modify for this slice:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- shared runtime modules under `orchestrator/workflow/`
- `specs/`

## Acceptance Target

This slice is complete only when all of the following are true:

- one imported generic future-consumer fixture models the chosen Stage 10 control shape
- the supported composition pattern is explicit and covered:
  one imported generic consumer `defproc` body
- the fixture matches the exact first-tranche protocol from Sections `14.1.1` and `15`:
  - `ReviewDecision` is a union with `APPROVE`, `REVISE`, `BLOCKED`
  - `ReviewLoopResult` is a union with `APPROVED`, `BLOCKED`, `EXHAUSTED`
  - `ReviewDecision.APPROVE` carries `review_report` and `findings`
  - `ReviewDecision.REVISE` carries `review_report` and `findings`
  - `ReviewDecision.BLOCKED` carries `review_report`, `blocker_class`, and `findings`
  - `ReviewLoopResult.APPROVED` carries `review_report` and `findings`
  - `ReviewLoopResult.BLOCKED` carries `review_report`, `blocker_class`, and `findings`
  - `ReviewLoopResult.EXHAUSTED` carries `last_review_report`, `findings`, and `reason`
- the fixture compiles and lowers without:
  - `procedure_call_unknown`
  - `type_unknown`
  - `loop_recur_state_type_invalid`
  - unresolved `TypeParamRef`
  - `workflow_boundary_type_invalid`
- the composed route preserves the exact first-tranche `ReviewFindings.v1` contract:
  - `schema_version == "ReviewFindings.v1"`
  - `items_path` remains a strict relpath under `artifacts/work`
  - the items payload still routes through the validated findings envelope rather than an unvalidated pointer/path placeholder
  - the exact exhausted result remains representable on the ordinary lowered `repeat_until.on_exhausted` route without weakening scalar-literal or structured-ref rules
- the deterministic verification bundle explicitly proves the findings-envelope rule through `validate_review_findings_v1`:
  - valid non-pointer object with a top-level `items` member succeeds
  - pointer payloads fail
  - missing top-level `items` fails
- source-map/origin assertions cover both the entry module and the imported consumer module
- the specialized consumer still reports the visible provider effect from the selected proc-ref hook
- compile-time-selected `review` and `fix` hooks survive specialization into lowering without unresolved symbolic callee names
- shared validation accepts the lowered exhausted-result shape without either of the currently reproduced blockers:
  - structured-ref target resolution to an unknown generated `...__review-report` step
  - non-literal `result__findings__schema_version` under `repeat_until.on_exhausted.outputs`
- runtime-visible artifacts contain no leaked `TypeParamRef`, `ProcRef`, provider refs, prompt refs, or generated `%loop-state` carrier names
- the lowered workflow uses ordinary `repeat_until`, `match`, and projection surfaces instead of a review-loop-specific route
- `std/phase.orc` and the bridge-owned public review-loop path remain unchanged

## Task 0: Sync The Verification Bundle

**Files:**

- Review: `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`
- Modify if needed: `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`

- [ ] **Step 1: Audit the recorded bundle against this plan**

Confirm `check_commands.json` includes all selectors this slice requires:

```bash
pytest --collect-only tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_procedures.py -k 'imported_generic_loop_state_consumer' -q
pytest tests/test_workflow_lisp_structured_results.py -k 'review_findings_certified_adapter' -q
pytest tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts -q
pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_review_loop_bridge_still_compiles_after_structural_constraints -q
git diff --check
```

If any selector is missing, add it before using the artifact. If the bundle already matches, leave it unchanged.

- [ ] **Step 2: Validate the artifact format immediately**

Run:

```bash
python -c "import json, pathlib; path=pathlib.Path('state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json'); data=json.loads(path.read_text(encoding='utf-8')); assert isinstance(data, list) and data; assert all(isinstance(item, str) and item for item in data)"
```

Expected: valid JSON list, non-empty, every entry a non-empty shell command string.

- [ ] **Step 3: Respect the dirty-worktree guard before any commit**

Before staging anything in this task, run:

```bash
git status --short --untracked-files=no -- \
  state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json
```

If the file already has unrelated edits, do not commit it as part of this slice. Record the guard firing in the final handoff.

## Task 1: Harden The Existing Proof To The Exact First-Tranche Contract

**Files:**

- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify if needed: `tests/test_workflow_lisp_structured_results.py`
- Modify if needed: `tests/test_workflow_lisp_phase_stdlib.py`
- Review only: `tests/test_workflow_lisp_loop_recur.py`

- [ ] **Step 1: Reuse the existing proof owners instead of adding new files**

Anchor the work on these current tests:

- `tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_consumer_specializes_without_runtime_leaks`
- `tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_seed_specializes_completed_field`
- `tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_update_reuses_specialized_carrier`
- `tests/test_workflow_lisp_procedures.py::test_stage3_materializes_proc_ref_specializations_before_lowering_and_preserves_effects`
- `tests/test_workflow_lisp_loop_recur.py::test_compile_stage3_imported_loop_recur_on_exhausted_helper_validates`
- `tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts`
- the `review_findings_certified_adapter_*` tests in `tests/test_workflow_lisp_structured_results.py`

Do not add a second proof file or a second imported-consumer proof.

- [ ] **Step 2: Update the imported-consumer fixture in place**

Patch `test_compile_stage3_imported_generic_loop_state_consumer_specializes_without_runtime_leaks` so the fixture now models the exact Section `14.1.1` and Section `15` protocol:

- `ReviewDecision` variants:
  - `APPROVE(review_report, findings)`
  - `REVISE(review_report, findings)`
  - `BLOCKED(review_report, blocker_class, findings)`
- `ReviewLoopResult` variants:
  - `APPROVED(review_report, findings)`
  - `BLOCKED(review_report, blocker_class, findings)`
  - `EXHAUSTED(last_review_report, findings, reason)`
- `REVISE` must trigger `fix` plus `continue`
- `APPROVE` and `BLOCKED` must be terminal
- typed `:on-exhausted` must project `EXHAUSTED`
- the terminal fields for `APPROVED` and `BLOCKED` must come from the current review decision
- the `fix` call must consume findings from the current `REVISE` decision
- keep this exact exhausted-result shape even if the current checkout rejects it initially; this slice repairs the frontend-owned lowering/output contract rather than loosening the protocol to fit stale lowering behavior

Hard-code the findings carrier shape in the fixture:

- `ReviewFindings.schema_version` must be the exact literal `"ReviewFindings.v1"`
- `ReviewFindings.items_path` must be a relpath under `artifacts/work`
- the findings payload must still represent the validated `ReviewFindings.v1` envelope at `items_path`

- [ ] **Step 3: Preserve visible effects and runtime erasure in the same proof**

Thread at least one provider-backed hook through the imported consumer:

- keep `review` or `fix` on an existing `provider-result` pattern
- keep the hook compile-time-selected via `proc-ref`
- reuse the effect-inspection style from `test_stage3_materializes_proc_ref_specializations_before_lowering_and_preserves_effects`

The hardened proof must simultaneously show:

- the selected provider effect is still visible in the specialized consumer
- provider refs and prompt refs do not leak into runtime-visible artifacts

- [ ] **Step 4: Expand assertions to lock the exact contract**

The hardened proof must assert at least:

- the imported generic consumer specialization exists in typed procedure results
- the specialized signature contains no `TypeParamRef`
- serialized Semantic IR and Executable IR contain no:
  - `TypeParamRef`
  - `ProcRef[`
  - provider-ref markers
  - prompt-ref markers
  - generated `%loop-state` carrier names
- the lowered specialized body contains no unresolved symbolic `review` or `fix` callee names
- the lowered workflow contains an ordinary `repeat_until` step
- the strict findings contract survives:
  - `schema_version == "ReviewFindings.v1"`
  - the lowered/generated findings path still points under `artifacts/work`
  - the carried findings surface remains a typed schema-plus-path pair
  - the lowered `repeat_until.on_exhausted` result preserves a scalar-literal `schema_version`
  - the lowered `repeat_until.on_exhausted` result resolves review-report/findings references to declared step outputs instead of dangling generated names
- the exact terminal protocol survives:
  - no terminal `REVISE` variant exists in `ReviewLoopResult`
  - `APPROVED`, `BLOCKED`, and `EXHAUSTED` have the exact fields listed above
  - `APPROVED` terminal payload fields are sourced from the approving decision
  - `BLOCKED` terminal payload fields are sourced from the blocking decision
  - `fix` consumes the `REVISE` findings
- origin/source-map data mentions both:
  - the entry module path
  - the imported consumer module path
- none of the target failure diagnostics appear:
  - `procedure_call_unknown`
  - `type_unknown`
  - `loop_recur_state_type_invalid`
  - `workflow_boundary_type_invalid`

- [ ] **Step 5: Keep the shared regressions narrow**

Update `tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts` only if the hardened proof exposes a missing assertion. At minimum it must keep proving:

- `state__latest_findings__schema_version` is the exact literal `"ReviewFindings.v1"`
- `state__latest_findings__items_path` remains `must_exist_target=True` under `artifacts/work`
- the carried loop-state findings surface remains a `ReviewFindings`-shaped schema-plus-path pair
- generated-path provenance for the carried findings path remains present

- [ ] **Step 6: Keep the adapter proof responsible for the validated envelope**

Use `tests/test_workflow_lisp_structured_results.py` to prove the minimum validated findings envelope:

- keep the positive test that accepts a non-pointer JSON object with a top-level `items` member
- keep the negative test that rejects pointer-authority payloads
- keep the negative test that rejects unsafe paths
- ensure there is a focused negative regression for a non-pointer object missing top-level `items`

Do not move this coverage into `std/phase.orc`, `phase_stdlib_typecheck.py`, or runtime code.

- [ ] **Step 7: Run the narrow failing selectors before touching owner modules**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_procedures.py -k 'imported_generic_loop_state_consumer' -q
pytest tests/test_workflow_lisp_structured_results.py -k 'review_findings_certified_adapter' -q
pytest tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts -q
```

Expected:

- collect-only succeeds
- the imported-consumer selector either passes immediately or fails on a bounded typing, lowering, output-contract, or shared-validation seam that this slice owns
- the adapter selector passes once the missing top-level-`items` regression is present
- the strict findings regression still passes or only fails on a bounded contract-preservation seam

## Task 2: Repair Only The Exposed Typing Or Specialization Seam

**Files:**

- Modify if needed: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify if needed: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify if needed: `orchestrator/workflow_lisp/loop_state.py`
- Modify if needed: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Test: `tests/test_workflow_lisp_procedures.py`
- Test if needed: `tests/test_workflow_lisp_phase_stdlib.py`
- Test if needed: `tests/test_workflow_lisp_structured_results.py`

- [ ] **Step 1: Route by diagnostic instead of patching broadly**

Use the first failing proof run to pick the owner:

- `procedure_call_unknown`
  - if it happens before the specialized consumer preserves compile-time proc-ref metadata, inspect imported generic call resolution in `procedure_typecheck.py` and specialization materialization in `procedure_specialization.py`
  - if typing and specialization are already monomorphic and the failure comes from lowering, stop Task 2 and move to Task 3
- `type_unknown`
  - inspect loop-state field-type resolution in `loop_state.py`
  - inspect generic substitution and local type-environment usage in `procedure_typecheck.py` and `typecheck_dispatch.py`
- unresolved `TypeParamRef`
  - inspect when loop-state carrier types are resolved relative to specialized-helper typechecking
- `workflow_boundary_type_invalid`
  - if typing/specialization already produced a monomorphic helper and the failure comes from the lowered `repeat_until` output contract or structured-ref target shape, stop Task 2 and move to Task 3 immediately

Do not touch lowering modules in this task.

- [ ] **Step 2: Keep the supported pattern to one imported body**

Any typing/specialization repair must preserve this route:

```text
resolve concrete types
-> specialize one imported generic consumer
-> typecheck the specialized helper
-> lower ordinary workflow surfaces
```

Do not add same-module helper resolution, a second expansion path, or bridge-only behavior.

- [ ] **Step 3: Re-run the proof selector after each narrow repair**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k 'imported_generic_loop_state_consumer' -q
```

Stop this task once the proof is past typing/specialization failures.

- [ ] **Step 4: Re-run shared findings regressions when the repair could affect them**

Run when changes can affect findings typing, substitution, or carried record materialization:

```bash
pytest tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts -q
pytest tests/test_workflow_lisp_structured_results.py -k 'review_findings_certified_adapter' -q
```

- [ ] **Step 5: Re-run the existing isolated imported loop-state proofs**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_seed_specializes_completed_field -q
pytest tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_update_reuses_specialized_carrier -q
```

Expected: the new proof does not regress the already-landed carrier substrate.

## Task 3: Repair Only The Exposed Lowering, Output-Contract, Proc-Ref Handoff, Or Provenance Seam

**Files:**

- Modify if needed: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify if needed: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify if needed: `orchestrator/workflow_lisp/lowering/values.py`
- Modify if needed: `orchestrator/workflow_lisp/source_map.py`
- Test: `tests/test_workflow_lisp_procedures.py`
- Test if needed: `tests/test_workflow_lisp_loop_recur.py`
- Test if needed: `tests/test_workflow_lisp_phase_stdlib.py`
- Test if needed: `tests/test_workflow_lisp_structured_results.py`

- [ ] **Step 1: Enter this task only after typing/specialization passes**

Use this task when the hardened proof now exposes one of these remaining gaps:

- `procedure_call_unknown` during lowering after the specialized consumer already preserves compile-time proc-ref metadata
- `workflow_boundary_type_invalid` because a lowered structured ref targets an unknown generated `...__review-report` step/output
- `workflow_boundary_type_invalid` because `repeat_until.on_exhausted.outputs.result__findings__schema_version` is not emitted as the required scalar literal
- runtime-visible leaks in serialized IR
- provider-ref or prompt-ref leakage on the selected provider-backed hook path
- `loop_recur_state_type_invalid` at the loop boundary after specialization
- missing `repeat_until.on_exhausted` projection behavior on the composed route
- missing imported-module provenance or origin-map coverage
- lost exact `ReviewFindings.v1` carrier contract on generated loop outputs or projections

- [ ] **Step 2: Repair in the smallest existing owner**

Route repairs as follows:

- loop boundary, typed exhaustion projection, or `repeat_until.on_exhausted` output-shape repair:
  - `orchestrator/workflow_lisp/lowering/control_loops.py`
- loop-state value projection, findings-carrier reconstruction, literal-field materialization, or carried contract preservation:
  - `orchestrator/workflow_lisp/lowering/values.py`
- proc-call runtime erasure, generated step/output naming, generated private-workflow provenance, or lowering-boundary proc-ref binding handoff:
  - `orchestrator/workflow_lisp/lowering/procedures.py`
- imported source lineage and generated-path provenance:
  - `orchestrator/workflow_lisp/source_map.py`

Do not repair by adding bridge-only state synthesis, weakening the first-tranche contract, or changing shared validation/runtime semantics under `orchestrator/workflow/`.

- [ ] **Step 3: Re-run the imported-consumer proof until it passes**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k 'imported_generic_loop_state_consumer' -q
```

Expected: the proof passes with ordinary `repeat_until` lowering, preserved first-tranche findings and terminal contracts, no unresolved symbolic `review` or `fix` callee names during lowering, no unknown generated `...__review-report` structured-ref targets, no non-literal exhausted `schema_version`, and no runtime-visible leaks.

- [ ] **Step 4: Re-run the focused shared regressions**

Run:

```bash
pytest tests/test_workflow_lisp_loop_recur.py::test_compile_stage3_imported_loop_recur_on_exhausted_helper_validates -q
pytest tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts -q
pytest tests/test_workflow_lisp_structured_results.py -k 'review_findings_certified_adapter' -q
pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_review_loop_bridge_still_compiles_after_structural_constraints -q
```

Expected: the proof fix preserves the adjacent exhaustion, strict-findings, adapter, and bridge-compatibility contracts.

## Task 4: Final Verification And Handoff Evidence

**Files:**

- Verify: `tests/test_workflow_lisp_procedures.py`
- Verify: `tests/test_workflow_lisp_loop_recur.py`
- Verify: `tests/test_workflow_lisp_phase_stdlib.py`
- Verify: `tests/test_workflow_lisp_structured_results.py`
- Verify: any touched owner modules under `orchestrator/workflow_lisp/`

- [ ] **Step 1: Re-run collect-only on any module with new or renamed tests**

Run at minimum:

```bash
pytest --collect-only tests/test_workflow_lisp_procedures.py -q
```

If this slice adds or renames tests in any other module, run collect-only on those modules too.

- [ ] **Step 2: Run the focused proof bundle recorded in `check_commands.json`**

At minimum that bundle must include:

```bash
pytest tests/test_workflow_lisp_procedures.py -k 'imported_generic_loop_state_consumer' -q
pytest tests/test_workflow_lisp_structured_results.py -k 'review_findings_certified_adapter' -q
pytest tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts -q
pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_review_loop_bridge_still_compiles_after_structural_constraints -q
git diff --check
```

- [ ] **Step 3: Run the adjacent prerequisite regressions**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_seed_specializes_completed_field -q
pytest tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_update_reuses_specialized_carrier -q
pytest tests/test_workflow_lisp_loop_recur.py::test_compile_stage3_imported_loop_recur_on_exhausted_helper_validates -q
```

These are required to prove the new composed route did not regress the already-landed carrier and exhaustion prerequisites.

- [ ] **Step 4: Record exact verification evidence in the final handoff**

The execution summary for this slice must explicitly record:

- which owner modules changed
- whether `check_commands.json` changed or was already aligned
- which selectors were run
- the exact passing result for the hardened imported future-consumer proof
- the exact passing result that clears the current shared-validation blockers on unknown `...__review-report` refs and non-literal exhausted `schema_version`
- the exact passing result for the `ReviewFindings.v1` adapter selector, including top-level-`items` validation
- the exact passing result for the shared strict-findings regression
- the exact passing result for the bridge smoke selector
- confirmation that the passing imported proof exercised the required provider-backed hook and showed no provider/prompt ref leaks
- confirmation that the passing imported proof matched the exact first-tranche terminal protocol rather than a weaker local enum/union surrogate
- confirmation that the passing imported proof carried the caller-selected `review` and `fix` proc-ref bindings through lowering without unresolved symbolic callee names
- confirmation that `std/phase.orc` and `phase_stdlib_typecheck.py` were left unchanged

## Execution Notes

- Run all commands from the repo root.
- Prefer the narrowest pytest selectors first.
- If any test names are added or renamed, `pytest --collect-only` is mandatory on those modules.
- Do not relax specs or approved design contracts to make the proof pass.
- Do not claim completion from inspection alone; completion requires fresh command output from the verification bundle above.
