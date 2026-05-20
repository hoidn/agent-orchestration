# DSL v2.14 Pointer Authority Clarification Execution Plan

> For implementation: keep ordinary long-running commands under implementation ownership until terminal success or documented recoverable failure handling is complete.

**Goal:** Audit current pointer-file usage, decide the authoritative Phase 1 pointer model for relpath artifacts, and tighten the v2.14 planning/design authority without changing runtime behavior or public DSL support.

**Architecture:** This item is a documentation-and-governance tranche with four units: inventory current pointer surfaces, derive one explicit authority rule set for Phase 1, propagate that rule into the binding implementation plan and any necessary durable docs, and capture any follow-up oracle/documentation gaps without implementing them here. The execution must distinguish authoritative contract outputs from read-only audit inputs so later Phase 1 runtime work can rely on one pointer model without rereading the backlog item or inferring intent from scattered workflow examples.

**Tech Stack:** Markdown, repo-local YAML/workflow inventory, Python helper scripts, targeted `rg` searches, `python -m json.tool`.

---

## Selected Item Objective

- Clarify the role of pointer files in the current DSL and the v2.14 materialization plan, then produce a durable Phase 1 decision for which pointer surfaces are authoritative and which are compatibility-only or deferred.

## Scope

- Inventory pointer-file usage across the binding audit set named by the selected backlog item:
  - `specs/dsl.md`
  - `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`
  - `workflows/library/*.yaml`
  - `workflows/examples/*.yaml`
  - `workflows/library/scripts/*.py`
  - tests that read or write `state/*_path.txt`
- Classify each observed pointer use as one of:
  - canonical top-level artifact pointer
  - local step materialization pointer
  - prompt/script compatibility input
  - stale compatibility shim
  - ambiguous authority surface
- Identify where artifact value, pointer-file contents, pointer-file path, and published artifact lineage can drift.
- Produce a durable decision note and tighten the Phase 1 implementation plan so the later runtime tranche inherits one explicit rule for published relpath artifacts.
- Record any needed Phase 0 oracle follow-up as documentation or a narrow note only if the audit exposes missing evidence expectations that should be captured before or alongside Phase 1 work.

## Explicit Non-Goals

- Do not remove existing pointer files.
- Do not change runtime behavior, loader behavior, or public DSL version support.
- Do not implement `materialize_artifacts`, pointer enforcement, or any other v2.14 runtime semantics in this item.
- Do not translate NeurIPS workflows to `.v214.yaml`.
- Do not introduce new sidecar-pointer semantics beyond documenting whether they are allowed, rejected, or deferred for Phase 1.
- Do not silently broaden into other Phase 1 backlog items, the v2.14 release tranche, or Phase 2 workflow translation.

## Constraints And Prerequisite Status

- `docs/steering.md` and `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md` keep this work inside the current Phase 1 gate only. Public `version: "2.14"` remains unavailable, Phase 2 translation remains blocked, tests stay network-free by default, and existing path-safety/version-gating/output-contract semantics are not to be changed here.
- `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md` is the binding design authority. Its current pointer model already distinguishes artifact value, pointer file, and published artifact, and it leans toward canonical published-pointer authority. This item may tighten or clarify that model, but it must not reopen unrelated Phase 1 decisions.
- `state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json` shows no completed items or tranches and still carries a stale Phase 0-era note. Treat that as bookkeeping drift rather than a scope override. The selected item is already the planning authority for this work, but implementation must not mark roadmap progress complete or mutate the ledger based on planning alone.
- `docs/backlog/roadmap_gate.json` currently allows `phase-1-dsl-v214-runtime` and blocks `phase-2-dsl-v214-neurips-stack`; keep that exact boundary intact.
- The selected backlog item’s deliverables are documentation and plan-authority outputs. Inventory sources such as specs, workflows, scripts, and tests are primarily audit inputs, not automatic edit targets.
- If a routine verification problem occurs, diagnose, narrow-fix, and rerun before considering `BLOCKED`. Reserve `BLOCKED` for missing resources, roadmap conflict, external dependency outside current authority, required user decision, unavailable hardware, or a failure that remains unrecoverable after a documented narrow fix attempt.

## Implementation Architecture

- **Inventory and classification:** build one cross-surface matrix of pointer uses, their authority role, and their drift risk. The matrix should be durable enough that later runtime work can cite it directly.
- **Decision authority:** write one design note that states the Phase 1 rule for published relpath artifacts, the status of noncanonical local sidecars, and the migration/deprecation guidance for new v2.14-authored workflows.
- **Planning alignment:** update the binding implementation plan so its pointer-authority language, error expectations, and compatibility framing match the decision note exactly.
- **Follow-up capture:** if the audit exposes missing Phase 0 oracle assertions or stale discoverability, capture that narrowly in the proper durable doc or index without implementing runtime/test behavior here.

## File And Artifact Targets

Mandatory contract outputs:

- `docs/design/dsl_v214_pointer_authority.md`
- `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`

Preferred packaging and conditional outputs:

- `docs/index.md` if the new design note needs a durable index entry.
- `docs/design/dsl_v214_materialization_variants_draft.md` only if the audit finds stale pointer-authority wording there that would mislead later Phase 1 implementation.
- A narrow follow-up note or backlog-facing documentation update only if the audit proves that current Phase 0 oracle docs are missing a pointer-authority evidence expectation. Prefer updating an existing durable doc over creating a new surface.

Primary audit inputs that must be covered even if they are not edited:

- `specs/dsl.md`
- `workflows/library/revision_study_design_phase.yaml`
- `workflows/library/major_project_roadmap_revision_phase.yaml`
- `workflows/library/neurips_backlog_seeded_plan_phase.yaml`
- `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml`
- `workflows/library/scripts/materialize_neurips_selected_item_inputs.py`
- `workflows/library/scripts/build_neurips_backlog_manifest.py`
- `workflows/library/scripts/reconcile_neurips_selected_item.py`
- tests and fixtures that read or write `state/*_path.txt`, including at minimum `tests/test_neurips_plan_gate_recovery.py` and the NeurIPS fixture trees surfaced by the audit grep

## Execution Checklist

### Task 1: Build The Pointer-Surface Inventory

- [ ] Enumerate pointer-related references across the required scope using targeted searches for `pointer:`, `state/*_path.txt`, `plan_path`, `publishes.from`, `outputs.from`, and workflow/script reads or writes of pointer files.
- [ ] For each relevant occurrence, record:
  - the artifact or workflow surface involved
  - whether the pointer represents a canonical published artifact pointer, a local materialization pointer, a compatibility input, a stale shim, or an ambiguous authority surface
  - whether artifact value, pointer contents, pointer path, and published artifact lineage can drift there
- [ ] Make the inventory explicit about the current DSL distinction between top-level relpath artifacts, same-step local outputs, and workflow-visible pointer files.
- [ ] Keep the inventory self-contained inside `docs/design/dsl_v214_pointer_authority.md` or an appendix embedded there; do not scatter the matrix across ad hoc notes.

Verification:

- Supporting: run targeted `rg` coverage checks before drafting the inventory and again before finalizing it to confirm every required scope bucket has at least one reviewed result or an explicit “no relevant pointer surface found” note.
- Supporting: spot-check the inventory against representative current surfaces in `specs/dsl.md`, one workflow file, one helper script, and one test/fixture path to confirm the classifications match actual usage rather than grep-only assumptions.

### Task 2: Decide The Phase 1 Authority Model

- [ ] Use the inventory plus the existing design authority to decide exactly which surfaces are authoritative in Phase 1.
- [ ] The decision note must state, without ambiguity:
  - published artifact lineage stores artifact values, not pointer-file paths
  - canonical pointer contents equal the relpath artifact value when a canonical published pointer exists
  - for published relpath artifacts, a same-step local pointer is either omitted or exactly equal to the canonical top-level pointer
  - whether noncanonical sidecar pointers are rejected for published relpath artifacts, allowed only for unpublished local artifacts as compatibility materializations, or deferred pending an explicitly named future contract
  - migration/deprecation guidance for new v2.14-authored workflows and scripts, including preference for direct structured refs where available
- [ ] Treat the current implementation-plan direction as the default unless the audit proves it is internally inconsistent. Do not reopen the broader artifact dataflow model.
- [ ] Record any intentional deferrals explicitly so later runtime implementation does not infer permission to invent new sidecar semantics.

Verification:

- Blocking: post-draft grep and reread must show that the decision note names one authority model consistently and does not leave multiple live interpretations of published relpath pointer behavior.
- Supporting: compare the final recommendation against the selected backlog acceptance criteria to confirm it distinguishes authoritative artifact values from pointer-file paths and states allowed, rejected, and deferred patterns explicitly.

### Task 3: Tighten The Binding Phase 1 Design Authority

- [ ] Update `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md` only where its pointer-authority language remains ambiguous, duplicated, or incomplete after Task 2.
- [ ] Keep the implementation plan aligned with the decision note on:
  - artifact value versus pointer file versus published artifact lineage
  - canonical-pointer requirements for published relpath artifacts
  - handling of local sidecar pointers
  - migration framing for compatibility-only pointer surfaces
- [ ] Do not edit unrelated Phase 1 sections or broaden the plan into runtime work, release gating, or Phase 2 translation.
- [ ] Update `docs/design/dsl_v214_materialization_variants_draft.md` only if it contains stale descriptive wording that would mislead future implementers about the chosen pointer-authority rule.
- [ ] Add an index entry in `docs/index.md` if the new design note would otherwise be hard to discover from the standard repo documentation hub.

Verification:

- Blocking: run a targeted consistency grep across `docs/design/dsl_v214_pointer_authority.md`, `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`, and any other touched durable docs to confirm there is one consistent pointer-authority rule and that stale contradictory wording has been removed.
- Supporting: reread only the touched sections of the implementation plan to verify Phase 1 scope boundaries, non-goals, and error-taxonomy references remain unchanged apart from the pointer clarification.

### Task 4: Capture Any Oracle Or Discoverability Follow-Up Narrowly

- [ ] If the audit shows current Phase 0 oracle docs are missing a pointer-authority evidence expectation, record that as a narrow documentation follow-up in the most appropriate existing durable surface.
- [ ] Prefer a note in an existing design/plan doc over new standalone documentation unless a new file is clearly needed for durable discoverability.
- [ ] Do not modify oracle fixtures, runtime behavior, or tests in this item. This task is only for documenting follow-up evidence needs or clarifying existing Phase 0 claims.
- [ ] If the audit finds no follow-up gap, say so explicitly in the decision note and leave this task with no extra file changes.

Verification:

- Supporting: ensure any follow-up wording is framed as a future evidence or implementation obligation, not as a claim that the behavior has already been enforced.
- Supporting: if `docs/index.md` is touched, verify the new or updated entry points to the actual authority document and does not advertise public `2.14` support.

### Task 5: Run Required Deterministic Checks And Record Evidence

- [ ] Run the selected backlog item’s required deterministic checks exactly as recorded in the selected-item context after documentation changes are complete.
- [ ] If a required check fails because of a narrow consistency issue introduced while updating docs or inventory-linked metadata, fix that issue and rerun the same command set.
- [ ] Record what changed, which surfaces were inventoried, the final pointer-authority recommendation, and how verification passed so later implementation can cite the resulting docs directly.
- [ ] Do not add an orchestrator smoke check by default for this item, because the intended change surface is documentation and plan authority only. If implementation unexpectedly edits workflow YAML or helper scripts to repair a failing required check, add the narrowest relevant smoke or parser check before completion and document why it became necessary.

Verification:

- Blocking:

```bash
python -m json.tool docs/backlog/roadmap_gate.json
python workflows/library/scripts/build_neurips_backlog_manifest.py --backlog-root docs/backlog/active --output state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json
python workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py --manifest-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json --gate-policy-path docs/backlog/roadmap_gate.json --progress-ledger-path state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --run-state-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --output state/DSL-V214-MATERIALIZATION-VARIANTS/roadmap_gate_check.json
```

## Completion Criteria

- `docs/design/dsl_v214_pointer_authority.md` exists and contains a usable pointer-use inventory plus one explicit Phase 1 authority recommendation.
- The resulting decision distinguishes artifact values from pointer-file paths and published artifact lineage, and it states which published and local pointer patterns are allowed, rejected, or deferred.
- `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md` matches the decision note on pointer authority without changing unrelated Phase 1 scope.
- Any discoverability or oracle-follow-up wording added by this item is narrow, accurate, and clearly framed as documentation or future evidence work rather than implemented behavior.
- The selected backlog item’s required deterministic checks pass.
- No runtime behavior, public DSL support, workflow translation, or unrelated backlog scope is changed or implied.
