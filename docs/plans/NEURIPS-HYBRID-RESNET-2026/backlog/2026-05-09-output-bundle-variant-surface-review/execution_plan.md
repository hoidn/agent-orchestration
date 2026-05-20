# Output Bundle Variant Surface Review Execution Plan

> For implementation: keep ordinary long-running commands under implementation ownership until terminal success or documented recoverable failure handling is complete.

**Goal:** Decide whether Phase 1 tagged-union provider/command output validation should use a dedicated `variant_output` contract or an `output_bundle.variants` extension, then propagate that decision through the binding v2.14 planning and draft-oracle documents without implementing runtime support.

**Architecture:** This item is a planning and governance tranche, not a runtime tranche. The work should produce one durable decision note, revise the Phase 1 design authority and backlog/roadmap authority to use one selected surface consistently, and update only the Phase 0 draft-oracle wording that names the future surface while preserving current-behavior characterization and all Phase 1/Phase 2 boundaries.

**Tech Stack:** Markdown, repo-local backlog governance scripts, `python -m json.tool`, targeted `rg` consistency checks.

---

## Selected Item Objective

- Decide the authored DSL surface for Phase 1 tagged-union provider/command output validation and remove stale or pending-review wording from the implementation-facing planning artifacts.

## Scope

- Compare exactly two authored-surface options for provider/command-produced tagged-union JSON:
  - a sibling `variant_output` contract;
  - an `output_bundle.variants` extension.
- Preserve the already-required semantics regardless of which surface wins:
  - discriminant enum validation;
  - variant-specific required and forbidden fields;
  - selected-field artifact exposure;
  - branch-safe references through `match` and `requires_variant`;
  - runtime guarding for unavailable variant fields;
  - keeping `select_variant_output` separate unless the review produces a concrete, documented reason to merge.
- Update the design authority, roadmap/backlog authority, and draft oracle/design wording so later implementation sees one consistent contract surface and one rejected alternative.

## Explicit Non-Goals

- Do not implement loader, runtime, contract, prompt, or test support for the selected surface in this item.
- Do not add public `version: "2.14"` workflows or revise public support claims.
- Do not change fixed-shape `output_bundle` behavior.
- Do not broaden into `recover_or_run`, `resource_transition`, `phase_outcome`, `review_loop`, mixed-version calls, general expression-language work, or Phase 2 NeurIPS-stack translation.
- Do not merge `select_variant_output` into the chosen validation surface unless a concrete reason is documented and the change stays strictly within this review item’s scope.

## Constraints And Prerequisite Status

- `docs/steering.md` and `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md` bind this work to the current Phase 1 gate only. Public `version: "2.14"` support remains unavailable, Phase 2 translation remains out of scope, tests and checks remain network-free by default, and existing path-safety/version-gating/output-contract semantics must not be changed here.
- `state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json` still contains no completed items or tranches and retains a stale Phase 0-era note. Treat that as bookkeeping drift, not permission to widen scope or claim tranche completion. This review may still proceed because the item has already been selected for planning, but implementation must not use this item to mutate roadmap completion state.
- The selected backlog item requires a design note plus aligned planning artifacts. The later Phase 1 runtime implementation must be able to rely on this plan and the revised design authority without rereading the raw backlog item.
- The current Phase 1 runtime backlog authority is inconsistent across durable surfaces: the roadmap still lists `docs/backlog/in_progress/2026-05-09-dsl-v214-runtime-semantics.md`, but the extant runtime-semantics backlog authority with the current `plan_path` lives at `docs/backlog/done/2026-05-09-dsl-v214-runtime-semantics.md`. Treat the roadmap entry as a stale duplicate and resolve it in this item by retargeting the roadmap to the `done/` file. Do not create, move, or revive a second runtime-semantics backlog item as part of this review.
- Apply the same semantic checklist to both candidate surfaces. Do not bias the decision merely because `variant_output` already has more prose in the current implementation plan.
- If a normal verification issue occurs, diagnose, narrow-fix, and rerun before considering `BLOCKED`. Reserve `BLOCKED` for a real roadmap conflict, missing external dependency, unavailable required resource, required user decision, or a failure that remains unrecoverable after a documented narrow fix attempt.

## Implementation Architecture

- **Decision note:** one durable note that records the selected surface, comparison rubric, tradeoffs, and rejected alternative.
- **Planning authority alignment:** the implementation plan, roadmap, and sole Phase 1 runtime backlog authority at `docs/backlog/done/2026-05-09-dsl-v214-runtime-semantics.md` must all name the same selected surface and keep `select_variant_output` handling, scope boundaries, and non-goals consistent.
- **Draft oracle wording alignment:** Phase 0 draft references should only be updated where they name the future surface; they must not change scenario meaning, current-behavior claims, or public-support boundaries.

## File And Artifact Targets

Mandatory contract outputs:

- `docs/design/dsl_v214_variant_surface_decision.md`
- `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`
- `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md`
- `docs/backlog/done/2026-05-09-dsl-v214-runtime-semantics.md`
- `docs/design/dsl_v214_materialization_variants_draft.md`

Preferred packaging and conditional targets:

- `docs/design/neurips_v214_behavior_matrix.md` only if the chosen surface changes future-surface terminology there; leave it untouched if its current wording stays accurate.
- `docs/index.md` if the new decision note is added or if existing descriptions need to point readers to the decision authority.
- `docs/backlog/in_progress/2026-05-09-output-bundle-variant-surface-review.md` only if implementation needs to add a narrowly scoped completion note for local consistency; do not rewrite the selected item’s scope or provenance.

## Execution Checklist

### Task 1: Establish The Comparison Rubric And Select One Surface

- [ ] Review the current Phase 1 design authority and draft references where `variant_output`, `output_bundle`, and `select_variant_output` are named.
- [ ] Compare both candidate surfaces against the same criteria:
  - discoverability and DSL surface area;
  - preservation of existing fixed-shape `output_bundle` semantics;
  - fit for provider, command, and adjudicated-provider outputs;
  - prompt-injection implications;
  - selected-field exposure and variant-proof ergonomics;
  - atomic-commit and validation responsibilities;
  - downstream wording impact on the Phase 0 oracle and Phase 1 runtime plan.
- [ ] Choose one surface and explicitly reject the other with concrete reasons.
- [ ] Decide whether the selected surface leaves `select_variant_output` separate. The default is yes; a merge requires a concrete, written justification and must not broaden scope beyond this review item.

Verification:

- Supporting: use targeted `rg` searches before editing to enumerate all current references to `variant_output`, `output_bundle.variants`, `pending review`, and `select_variant_output` across the planned edit set.
- Supporting: confirm the decision rubric covers every semantic requirement already named in the current implementation plan before committing to a winner.

### Task 2: Write The Durable Decision Note And Update The Design Authority

- [ ] Create `docs/design/dsl_v214_variant_surface_decision.md` as the durable design note for this review. It must record:
  - the selected authored surface;
  - the semantic requirements that remain unchanged;
  - tradeoffs for both options;
  - the rejected option and why it was rejected;
  - whether `select_variant_output` remains separate and why.
- [ ] Update `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md` so it no longer presents stale or ambiguous surface guidance. Replace pending-review language with the selected surface, preserve the Phase 1/Phase 2 boundaries, and keep the non-goals intact.
- [ ] Update any mutual-exclusion, prompt-injection, or test-planning text in the implementation plan so it names the selected surface consistently and preserves the same underlying runtime obligations.

Verification:

- Blocking: run a targeted post-edit consistency grep across `docs/design/dsl_v214_variant_surface_decision.md`, `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`, and `docs/design/dsl_v214_materialization_variants_draft.md` to confirm the selected surface is the normative one and the rejected surface appears only in explicit tradeoff or historical context.
- Supporting: reread the updated implementation-plan sections that describe contract validation, prompt delivery, runtime lowering, tests, and completion criteria to confirm they still preserve the same Phase 1 semantics apart from the authored surface name.

### Task 3: Propagate The Decision Into Backlog, Roadmap, And Draft Oracle Docs

- [ ] Update `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md` so Phase 1 no longer says the contract surface is pending review and so its backlog-authority list explicitly points to `docs/backlog/done/2026-05-09-dsl-v214-runtime-semantics.md` instead of the stale nonexistent `in_progress` path. Keep the gate id, allowed/disallowed prefixes, and Phase 2 boundary unchanged.
- [ ] Treat `docs/backlog/done/2026-05-09-dsl-v214-runtime-semantics.md` as the sole authoritative Phase 1 runtime backlog item for this review because it is the durable runtime-semantics backlog document that already carries the current `plan_path`. Do not create or reintroduce `docs/backlog/in_progress/2026-05-09-dsl-v214-runtime-semantics.md`.
- [ ] Update `docs/backlog/done/2026-05-09-dsl-v214-runtime-semantics.md` so its scope names the selected surface explicitly and keeps all existing prerequisites, non-goals, and required evidence aligned with the revised implementation plan.
- [ ] Update `docs/design/dsl_v214_materialization_variants_draft.md` anywhere it names the future tagged-union validation surface so the Phase 0 characterization references the selected Phase 1 surface accurately without changing scenario behavior or public-support status.
- [ ] Update `docs/design/neurips_v214_behavior_matrix.md` only if terminology there becomes stale after the decision.
- [ ] Update `docs/index.md` if a new durable decision note is added or if readers need a new reference entry to find the decision authority quickly.

Verification:

- Blocking: run a final cross-document grep over the touched planning/design files for `pending review`, `variant_output`, and `output_bundle\\.variants`, then confirm any remaining mentions of the rejected surface are deliberate historical or rejected-option references rather than stale normative guidance.
- Supporting: verify the roadmap still names only `phase-1-dsl-v214-runtime` as current work, does not accidentally advertise public `2.14` support or Phase 2 translation readiness, and no touched planning authority still points Phase 1 runtime work at `docs/backlog/in_progress/2026-05-09-dsl-v214-runtime-semantics.md`.

### Task 4: Run Required Deterministic Governance Checks And Record Evidence

- [ ] Run the selected backlog item’s required deterministic checks exactly as recorded in the selected-item context after the doc updates are complete.
- [ ] If any required check fails because of a narrow consistency issue introduced by this review item, fix the issue and rerun the same command set.
- [ ] Record what changed and how it was verified so later implementation can cite the decision authority and consistency evidence directly.
- [ ] Do not add an orchestrator dry-run smoke by default for this item, because this tranche is scoped to planning/design/backlog documents rather than workflow, prompt, or runtime behavior. If implementation unexpectedly touches workflow YAML or backlog-drain scripts while resolving a failing required check, add a blocking dry-run smoke before completion.

Verification:

- Blocking:

```bash
python -m json.tool docs/backlog/roadmap_gate.json
python workflows/library/scripts/build_neurips_backlog_manifest.py --backlog-root docs/backlog/active --output state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json
python workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py --manifest-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json --gate-policy-path docs/backlog/roadmap_gate.json --progress-ledger-path state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --run-state-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --output state/DSL-V214-MATERIALIZATION-VARIANTS/roadmap_gate_check.json
```

## Completion Criteria

- A durable decision note exists and explicitly records the selected surface, rejected surface, unchanged semantic requirements, and `select_variant_output` relationship.
- The v2.14 implementation plan, Phase 1 roadmap, the sole durable Phase 1 runtime backlog item at `docs/backlog/done/2026-05-09-dsl-v214-runtime-semantics.md`, and relevant Phase 0 draft references all name one selected tagged-union validation surface consistently.
- No stale pending-review wording remains in the touched planning/design authority except in explicit historical or rejected-option context.
- The required deterministic manifest and roadmap-gate checks pass.
- No runtime implementation, public `version: "2.14"` exposure, Phase 2 translation work, or deferred DSL features are added or implied.
