# Design Delta Drain .orc Migration Frontend/Runtime Findings

Status: findings report  
Created: 2026-06-09  
Scope: issues uncovered while executing `docs/plans/2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md` through the foundation gate, plan-phase candidate, implementation-phase candidate, and selector candidate.

## Summary

Yes: the migration has uncovered frontend/runtime issues that deserve explicit attention before this workflow family can become promotion-grade `.orc`.

Some are already-fixed implementation bugs. Others are current frontend limitations or ergonomics/design mismatches that force the migration to split workflows into leaf candidates, avoid public `state/` paths, or rename fields only to satisfy lowering/shared-validation constraints.

The most important unresolved issue is nested structured control composition: the full implementation phase wants to branch on `ImplementationAttempt.COMPLETED` and then run the stdlib `review-revise-loop` inside that branch. The current lowering/shared-validation path cannot represent that shape cleanly. That is a first-class frontend/runtime design gap, not merely a migration inconvenience.

## Current Evidence

Committed checkpoints:

- `18d5017 workflow_lisp: complete design delta drain foundation gate`
- `3763367 workflow_lisp: add design delta plan phase candidate`
- `3ba7671 workflow_lisp: add design delta implementation phase leaves`
- `82ff487 workflow_lisp: add design delta selector candidate`

Focused verification from the migration run:

- `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q`
  - after the selector checkpoint: 9 tests passed.
- Foundation-gate selectors recorded in `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/foundation_readiness_gate.md`.

The current migration state is intentionally not parity-complete. The `.orc` candidates are compileable slices that expose remaining frontend/runtime gaps.

## Findings

| ID | Type | Severity | Status | Owner Surface |
| --- | --- | --- | --- | --- |
| F1 | frontend bug | High | fixed in current branch | Workflow Lisp typecheck/lowering |
| F2 | frontend/runtime design gap | High | unresolved | Workflow Lisp structured control + shared validation |
| F3 | frontend lowering ergonomics/design gap | Medium | unresolved | Workflow Lisp union return lowering |
| F4 | frontend/shared-validation ergonomics | Medium | unresolved/mitigated | Structured result contract derivation |
| F5 | public/private boundary design gap | High | unresolved | Workflow Lisp StateLayout/private executable contracts |
| F6 | command adapter/runtime authority gap | Medium | partially covered, still migration-blocking | command-result + certified adapters |
| F7 | selector/state bundle bridge gap | Medium | unresolved | typed projection / private context bridge |

## F1: Imported `PhaseCtx` Recognition Was Too Name-Local

Type: frontend bug  
Status: fixed in `18d5017`

During the foundation readiness gate, an imported stdlib/phase fixture failed because imported type references were canonicalized to module-qualified binding names while the phase/stdlib checks recognized only the short authored name `PhaseCtx`.

Impact:

- Valid imported phase contexts could be rejected or fail downstream phase/stdlib checks.
- The failure was not semantic: the record shape was correct, but recognition used the wrong identity surface.

Fix already applied:

- Use the authored record definition name while preserving structural validation for imported `PhaseCtx`.
- Updated code paths include `orchestrator/workflow_lisp/phase.py` and `orchestrator/workflow_lisp/typecheck_dispatch.py`.

Why this matters for design:

- Standard-library forms should recognize capability/shape contracts across module boundaries.
- Imported type canonicalization must not accidentally make same-shaped stdlib contracts unusable.

Recommended follow-up:

- Treat this as a pattern: any stdlib form that depends on special record names should prefer explicit structural/capability checks plus source provenance over short-name matching.

## F2: Nested Structured Control Cannot Express the Full Implementation Phase

Type: frontend/runtime design gap  
Status: unresolved

The YAML implementation phase has this semantic shape:

```text
ExecuteImplementation -> ImplementationAttempt
  COMPLETED -> RunChecks -> ReviewImplementation/FixImplementation bounded loop
  BLOCKED   -> terminal blocked result with NOT_APPLICABLE review decision
```

The natural `.orc` expression is:

```text
match ImplementationAttempt
  COMPLETED:
    review-revise-loop(...)
  BLOCKED:
    return blocked terminal result
```

That shape currently fails shared validation after lowering. The failure reported structured-control constraints such as:

- structured `repeat_until` is only supported on top-level steps;
- structured `match` is only supported on top-level steps;
- generated structured references inside the branch pointed at steps not visible where shared validation expected them.

Impact:

- The migration cannot yet express the implementation phase as one principled `.orc` workflow without splitting it into leaf workflows or falling back to an adapter.
- This blocks a faithful `.orc` parent/work-item composition because the parent wants to call one implementation phase and route on its terminal result.
- It also weakens the stdlib story: `review-revise-loop` is useful at top level, but not composable enough inside ordinary typed branches.

Current mitigation:

- `workflows/library/lisp_frontend_design_delta/implementation_phase.orc` was split into:
  - `execute-implementation-attempt`
  - `review-completed-implementation`
- The migration record explicitly says full phase composition and output parity remain open.

Principled fix:

- Lower structured `match` and structured `repeat_until` so they are valid inside generated branch scopes, or introduce an internal executable IR representation that can carry nested structured control before rendering to a validation-compatible executable workflow.
- Ensure generated step IDs, branch-local step visibility, source maps, Semantic IR entries, and state layout all agree for nested structures.
- Add a minimal regression fixture with exactly this shape:

```text
provider-result -> union
match union:
  A -> command-result -> review-revise-loop -> union terminal
  B -> union terminal
```

Acceptance should include shared validation, source-map emission, Semantic IR state-layout entries, and a dry-run or fake-provider smoke.

## F3: Union Match Lowering Assumes Matched Variant Names When Returning Another Union

Type: frontend lowering bug/design gap  
Status: unresolved

While trying to express the full implementation phase directly, a `match` over one union returned a different union whose variant names did not match the source case names. For example:

```text
match ReviewLoopResult.APPROVED -> DesignDeltaImplementationPhaseResult.COMPLETED
```

The lowerer raised a `KeyError` while normalizing the union result because it attempted to look up fields under the source/matched variant name rather than the returned variant name.

Impact:

- Authors are pushed toward unnatural variant names just to satisfy lowering internals.
- It makes semantically clean mappings awkward, especially when one domain uses `APPROVED` and another uses `COMPLETED`.
- It encourages leaking intermediate control states into exported workflow result types.

Current mitigation:

- Avoided the full nested shape.
- Where needed, candidates use terminal variant names that line up with stdlib review-loop names or split the workflow before this mapping is needed.

Principled fix:

- In union-return normalization, derive the output variant from the returned `variant` expression, not from the enclosing `match` case name.
- Add tests for mapping one union to another with different variant names:

```text
ReviewLoopResult.APPROVED -> ImplementationPhaseResult.COMPLETED
ReviewLoopResult.EXHAUSTED -> ImplementationPhaseResult.REVIEW_EXHAUSTED
ImplementationAttempt.BLOCKED -> ImplementationPhaseResult.BLOCKED
```

## F4: Variant Output Field Names Must Be Globally Unique Across Variants

Type: ergonomics/shared-validation issue  
Status: unresolved, mitigated by naming

The plan-phase candidate originally used the same logical field names across variants, such as `plan_path`, `plan_review_report_path`, and `findings`. Shared validation rejected the lowered `variant_output` because artifact names and JSON pointers duplicated across discriminant/shared/variant fields.

Impact:

- Authors have to write verbose variant-specific names:
  - `approved_plan_path`
  - `blocked_plan_path`
  - `exhausted_plan_path`
  - `approved_plan_review_report_path`
  - `blocked_plan_review_report_path`
- This is noisy and semantically worse than saying each variant carries a `plan_path`.
- It makes domain types less natural and more shaped by current output-bundle implementation constraints.

Current mitigation:

- `plan_phase.orc` uses variant-specific field names so shared validation passes.
- The migration plan records that output parity is not complete.

Principled fix:

- Decide whether `variant_output` should support same logical field names in different variants when the JSON pointer is variant-scoped.
- If yes, update structured result contract derivation and artifact naming to include variant scope, for example:

```text
APPROVED.plan_path
BLOCKED.plan_path
EXHAUSTED.plan_path
```

- If no, document the restriction prominently in Workflow Lisp authoring guidance and status matrix examples, because it materially affects type design.

Recommendation:

- Prefer variant-scoped field identity. The current restriction is implementation-shaped and makes `.orc` less ergonomic for ordinary tagged unions.

## F5: Public High-Level `.orc` Boundaries Cannot Yet Represent Private Runtime State Contexts Cleanly

Type: frontend/runtime design gap  
Status: unresolved

The YAML family exposes many `state/` paths at workflow boundaries:

- `state_root`
- `manifest_path`
- `progress_ledger_path`
- `run_state_path`
- phase state roots
- selection bundle paths

When analogous paths were exposed directly in `.orc`, required lint rejected high-level workflows that expose low-level `state/` paths. That lint is directionally right: public `.orc` authoring should not make generated state roots ordinary user inputs.

But the migration still needs a principled way to preserve compatibility with YAML state roots while keeping `.orc` boundaries clean.

Impact:

- Plan phase and selector candidates use `WorkReport` artifacts instead of raw `state/` paths for first-pass compileability.
- This avoids bad public API design, but it is not parity with YAML.
- Parent/work-item composition still needs a private context bridge that can carry runtime state paths without exposing them as public user-authored inputs.

Current mitigation:

- `plan_phase.orc` models work-item context and ledger context as artifact inputs.
- `selector.orc` models manifest, progress ledger, and run state as typed artifact inputs.
- Migration record calls out the public-boundary delta.

Principled fix:

- Define an explicit private executable context mechanism for Workflow Lisp lowered workflows:
  - public authored `.orc` boundary excludes generated state roots;
  - compiler/runtime injects private context values;
  - source maps and Semantic IR expose provenance;
  - shared validation sees executable/runtime contracts without treating them as public inputs.
- This belongs with the StateLayout/private executable contract work in `docs/design/workflow_lisp_runtime_migration_foundation.md`.

Acceptance:

- A workflow can use run/state/artifact roots internally without public input exposure.
- Public input inspection proves generated write roots and phase state roots are hidden.
- Resume reconstructs the same private context paths.
- YAML interop can bridge legacy `state/` paths into private context values during migration.

## F6: Command Adapter Certification Is Still Required for Real Selector/Implementation Parity

Type: runtime/adapter authority gap  
Status: partially covered, unresolved for this family

The `.orc` candidates can compile command-result calls, but several YAML helpers still encode semantic workflow behavior:

- `publish_lisp_frontend_selection_bundle.py`
- `run_neurips_backlog_checks.py`
- design-gap architecture validation scripts
- run-state/recovery recording scripts

These are not all equivalent. Some are deterministic projections; some mutate run state or encode routing semantics.

Impact:

- A compileable `command-result` is not enough to claim migration parity.
- The migration needs certified adapter contracts or native typed procedures for these helpers.
- The implementation-phase leaf candidate calls `run_neurips_backlog_checks` as command-result, but the full runtime output-bundle contract and adapter certification still need parity evidence.

Principled fix:

- For each retained helper, add a certified adapter boundary with:
  - stable command prefix;
  - typed input/output contract;
  - declared effects;
  - path-safety rules;
  - exit-code taxonomy;
  - fixtures and negative fixtures;
  - source-map behavior.
- Promote pure path/status projections into typed `.orc` procedures or runtime-native effects where practical.

Design ownership:

- Policy lives in `docs/design/workflow_command_adapter_contract.md`.
- Runtime command IO behavior lives in `specs/io.md`.
- Migration status should remain in the migration record until adapters are certified.

## F7: Selector Bundle Publication Needs a Typed Projection or Private Bridge

Type: ergonomics/design gap  
Status: unresolved

The YAML selector produces:

- `selection_status` directly from provider output;
- `selection_bundle_path` through a script that validates and republishes the path to the provider's selection JSON.

The first `.orc` selector candidate models only the typed selection decision. It does not yet preserve the public `selection_bundle_path` output contract.

Impact:

- The selector candidate is useful but not parity-ready.
- Downstream workflows currently expect a state-root selection bundle path.
- Without a typed projection or bridge, parent drain composition cannot route work-item/materialization paths equivalently.

Principled fix options:

1. Typed projection:
   - Have provider-result return a typed bundle record that includes the bundle path as authoritative structured output.
   - Derive `selection_bundle_path` from runtime-known output bundle path instead of a script.

2. Certified adapter:
   - Keep `publish_lisp_frontend_selection_bundle.py` as a certified adapter with explicit semantics.
   - Treat it as migration debt until native projection exists.

3. Private bridge:
   - Lower the selection bundle as private runtime state and expose only typed selection values to public `.orc` code.

Recommendation:

- Prefer typed projection for selector bundle publication. It is deterministic and should not need a standalone script long term.

## Cross-Cutting Ergonomics Problem

The current frontend makes authors think about too many implementation-shaped constraints:

- whether a structured control step is top-level;
- whether a union-returning branch maps variant names directly;
- whether variant field names duplicate across variants;
- whether a path is public `state/` or private generated state;
- whether a command helper is just a projection or semantic workflow authority.

For `.orc` to be a strong authoring surface, authors should be able to write the semantic program:

```text
attempt = execute(...)
match attempt:
  COMPLETED -> review/revise completed result
  BLOCKED -> blocked terminal result
```

and rely on the compiler/runtime to allocate paths, generate source maps, preserve branch proof, and lower to validation-compatible executable form.

The migration is showing that Workflow Lisp has enough substrate to express useful leaves, but not yet enough compositional smoothness for this drain family without visible seams.

## Recommended Work Items

### P0: Nested Structured Control Composition

Implement or design a lowering/runtime path where structured `match`, `repeat_until`, and stdlib review loops can appear inside branch scopes and procedure calls while still passing shared validation.

Minimal fixture:

```text
provider-result -> ImplementationAttempt
match ImplementationAttempt:
  COMPLETED -> command-result -> review-revise-loop -> ImplementationPhaseResult
  BLOCKED -> ImplementationPhaseResult
```

This is required before the implementation phase can be migrated as one principled `.orc` workflow.

### P0: Private Executable Context Bridge

Define how Workflow Lisp carries run/state/artifact roots, phase roots, generated write roots, and selection/recovery state internally without exposing them as public high-level workflow inputs.

This is required for parity with YAML workflows whose public boundaries currently include many `state/` paths.

### P1: Union-to-Union Variant Mapping Fix

Fix union return normalization so matched source variant names and returned target variant names are independent.

This improves ergonomics and removes a surprising lowering constraint.

### P1: Variant-Scoped Field Identity

Allow the same logical field name in different union variants, with variant-scoped artifact/json-pointer identity, or document the restriction as a hard current limitation.

Recommendation is to support variant-scoped identity.

### P1: Selector Bundle Native Projection

Replace `publish_lisp_frontend_selection_bundle.py` with a typed projection or certified adapter. Native projection is preferable because this script mostly republishes deterministic structured state.

### P1: Adapter Certification Pass for Remaining Helpers

Certify or replace command helpers used by the drain family before claiming parity. Focus first on helpers that decide routing, mutate run state, or publish bundle paths.

## Design Documents To Update

The following docs should absorb these findings:

- `docs/design/workflow_lisp_runtime_migration_foundation.md`
  - private executable context bridge;
  - nested structured control as a foundation or immediate post-foundation prerequisite;
  - selector/value projection as runtime-owned state rather than script-owned pointer publication.

- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  - explicitly include nested `match` plus stdlib `review-revise-loop` composition as a required hardening target;
  - state that imported stdlib review loops are not sufficient until they compose under branch scopes.

- `docs/lisp_workflow_drafting_guide.md`
  - if not fixed soon, document current authoring limitations around nested structured control and variant field naming.

- `docs/plans/2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md`
  - keep the current split-candidate approach until the frontend/runtime gaps above are resolved.

## Bottom Line

The migration is succeeding as a diagnostic: it is converting hidden YAML mechanics into typed `.orc` candidate surfaces and exposing the real composition gaps.

The biggest required fix is not syntax. It is making Workflow Lisp's structured control, private runtime context, variant proof, generated path ownership, and shared validation work together for nested real workflows.

Until then, the design delta drain migration should continue as leaf candidates plus explicit bridges, and YAML should remain primary.
