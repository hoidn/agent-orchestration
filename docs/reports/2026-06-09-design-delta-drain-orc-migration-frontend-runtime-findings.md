# Design Delta Drain .orc Migration Frontend/Runtime Findings

Status: findings report
Created: 2026-06-09
Updated: 2026-06-09
Scope: issues uncovered while executing `docs/plans/2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md` through the foundation gate, domain module, feasibility probes, plan phase, implementation phase, selector, design-gap architect, work-item leaves, and parent-drain readiness assessment.

## Summary

Yes. The migration uncovered several issues that require attention to Workflow Lisp frontend and runtime design, not only to the migration plan.

The migration has been useful as a diagnostic because it separated three categories:

- fixed frontend bugs;
- unresolved frontend/runtime composition gaps; and
- migration ergonomics or authority gaps that force `.orc` authors back toward YAML-shaped mechanics.

The highest-priority blocker is nested structured-control composition. The implementation phase naturally wants to branch on `ImplementationAttempt.COMPLETED` and then run the stdlib `review-revise-loop` inside that branch. The current lowering/shared-validation path rejects that generated shape. That prevents the implementation phase, work item, and parent drain from becoming principled parent-callable `.orc` workflows.

The second major blocker is private runtime context. The YAML family exposes many `state/` paths, but high-level `.orc` should not expose generated state roots as normal user inputs. The frontend/runtime needs a private executable context bridge backed by StateLayout/source-map/Semantic IR evidence.

Until those are addressed, the migration should continue as typed leaf candidates plus explicit bridge records. YAML should remain primary.

## Current Evidence

Committed checkpoints from this execution:

- `18d5017 workflow_lisp: complete design delta drain foundation gate`
- `3763367 workflow_lisp: add design delta plan phase candidate`
- `3ba7671 workflow_lisp: add design delta implementation phase leaves`
- `82ff487 workflow_lisp: add design delta selector candidate`
- `699e35a workflow_lisp: add design delta architect candidate`
- `59a070f workflow_lisp: add design delta work item leaves`
- `3d6f1e1 docs: record design delta parent drain blockers`

Focused verification:

- `pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q`
  - 11 tests collected.
- `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q`
  - 11 tests passed.
- Foundation-gate selectors are recorded in `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/foundation_readiness_gate.md`.

Current migration state:

- Leaf candidates compile for plan, implementation, selector, design-gap architect, and work-item pieces.
- The parent drain is intentionally blocked before implementation.
- The blocker record is `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`.

## Findings

| ID | Type | Severity | Status | Owner Surface |
| --- | --- | --- | --- | --- |
| F1 | frontend bug | High | fixed | Workflow Lisp stdlib/typecheck recognition |
| F2 | frontend/runtime design gap | High | unresolved | nested structured control + shared validation |
| F3 | frontend lowering bug/design gap | High | unresolved | union-to-union result normalization |
| F4 | ergonomics/shared-validation issue | Medium | unresolved, mitigated | variant output field identity |
| F5 | frontend/runtime design gap | High | unresolved | private context + StateLayout |
| F6 | runtime/adapter authority gap | High | unresolved for family parity | certified adapters + resource transitions |
| F7 | projection/materialization gap | Medium | unresolved | selector and bundle publication |
| F8 | stdlib composition gap | High | unresolved | `review-revise-loop` as first-class reusable workflow abstraction |
| F9 | workflow-family design gap | High | unresolved | work-item and parent-drain composition |
| F10 | authoring ergonomics issue | Medium | unresolved | command adapter call surface and path plumbing |
| F11 | migration evidence gap | Medium | unresolved | parity target/readiness status |

## F1: Imported `PhaseCtx` Recognition Was Too Name-Local

Type: frontend bug
Status: fixed in `18d5017`

The foundation readiness gate exposed a bug where imported type references were canonicalized to module-qualified binding names while the phase/stdlib checks recognized only short authored names such as `PhaseCtx`.

Impact:

- Valid imported phase contexts could be rejected.
- The failure was not semantic; the record shape was correct.
- Stdlib forms were depending too much on short local names.

Fix applied:

- Use the authored record definition name while preserving structural validation.
- Updated code paths included `orchestrator/workflow_lisp/phase.py` and `orchestrator/workflow_lisp/typecheck_dispatch.py`.

Design lesson:

- Stdlib forms should recognize capability/shape contracts across module boundaries.
- Any future stdlib form that depends on special record names should prefer structural/capability checks plus source provenance over local-name matching.

## F2: Nested Structured Control Cannot Express the Full Implementation Phase

Type: frontend/runtime design gap
Status: unresolved

The YAML implementation phase has this semantic shape:

```text
ExecuteImplementation -> ImplementationAttempt
  COMPLETED -> RunChecks -> ReviewImplementation/FixImplementation bounded loop
  BLOCKED   -> terminal blocked result with NOT_APPLICABLE review decision
```

The natural `.orc` shape is:

```text
attempt = execute(...)
match attempt:
  COMPLETED -> review-revise-loop(...)
  BLOCKED   -> blocked terminal result
```

That currently fails after lowering/shared validation. The failure mode includes:

- structured `repeat_until` only accepted as top-level;
- structured `match` only accepted as top-level;
- generated branch-local refs pointing at steps not visible to shared validation;
- review-loop generated steps becoming invalid when nested under a match branch.

Impact:

- The implementation phase had to be split into `execute-implementation-attempt` and `review-completed-implementation` leaves.
- Work-item orchestration cannot call one complete implementation phase.
- The parent drain cannot be principled until the phase/work-item surfaces are parent-callable.

Principled fix:

- Add a frontend/lowering/shared-validation route for nested structured control.
- Either lower nested structured forms to validation-compatible top-level step graphs with explicit branch scopes, or introduce an executable IR layer that preserves nesting until rendering.
- Generated step IDs, branch-local visibility, source maps, Semantic IR layout, and StateLayout entries must agree.

Acceptance fixture:

```text
provider-result -> ImplementationAttempt
match ImplementationAttempt:
  COMPLETED -> command-result -> review-revise-loop -> ImplementationPhaseResult
  BLOCKED   -> ImplementationPhaseResult
```

Required evidence:

- compile/typecheck;
- shared validation;
- source-map generated-path entries;
- Semantic IR state-layout entries;
- dry-run or fake-provider smoke.

## F3: Union-to-Union Result Mapping Assumes the Source Case Name

Type: frontend lowering bug/design gap
Status: unresolved

When mapping one union to a different result union, lowering tried to normalize the result using the enclosing matched case name rather than the actual returned variant.

Example shape:

```text
match ReviewLoopResult.APPROVED:
  -> DesignDeltaImplementationPhaseResult.COMPLETED
```

Observed effect:

- lowering raised a `KeyError`;
- authors were pushed toward unnatural variant names;
- intermediate review-loop variants leaked into outer domain result types.

Impact:

- Makes semantic result translation awkward.
- Blocks clean domain modeling where inner control states and outer terminal states intentionally have different names.
- Encourages compatibility-shaped union definitions.

Principled fix:

- In union-return normalization, derive the output variant from the returned `variant` expression, not from the matched source case.
- Add tests for:
  - `ReviewLoopResult.APPROVED -> ImplementationPhaseResult.COMPLETED`;
  - `ReviewLoopResult.EXHAUSTED -> ImplementationPhaseResult.REVIEW_EXHAUSTED`;
  - `ImplementationAttempt.BLOCKED -> ImplementationPhaseResult.BLOCKED`.

## F4: Variant Output Field Names Must Be Globally Unique Across Variants

Type: ergonomics/shared-validation issue
Status: unresolved, mitigated by naming

The plan-phase candidate initially used natural field names across variants, such as `plan_path`, `plan_review_report_path`, and `findings`. Shared validation rejected the lowered `variant_output` because artifact names and JSON pointers duplicated across variants.

Impact:

- Authors have to write verbose variant-specific fields:
  - `approved_plan_path`;
  - `blocked_plan_path`;
  - `exhausted_plan_path`;
  - `approved_plan_review_report_path`;
  - `blocked_plan_review_report_path`.
- Domain types become shaped by output-bundle implementation details.
- This makes tagged unions feel less first-class.

Recommendation:

- Prefer variant-scoped field identity.
- `APPROVED.plan_path` and `BLOCKED.plan_path` should be distinct lowered artifact identities even when the logical field name is the same.

If this is not fixed soon:

- document the restriction in `docs/lisp_workflow_drafting_guide.md`;
- add examples showing variant-specific field naming as current required style.

## F5: Public High-Level `.orc` Boundaries Need a Private Runtime Context Bridge

Type: frontend/runtime design gap
Status: unresolved

The YAML family exposes many low-level `state/` paths:

- `state_root`;
- `manifest_path`;
- `progress_ledger_path`;
- `run_state_path`;
- phase state roots;
- selection bundle paths.

When analogous paths are exposed directly in `.orc`, required lints reject high-level workflows that expose low-level state paths. The lint is directionally correct: generated state should not become ordinary author input.

Impact:

- Plan, selector, architect, and work-item candidates avoid raw `state/` path inputs.
- That keeps `.orc` boundaries cleaner but is not YAML parity.
- Parent/work-item composition needs a private bridge for legacy state paths and runtime-owned context.

Principled fix:

- Define private executable context values for Workflow Lisp:
  - public authored `.orc` boundary excludes generated state roots;
  - compiler/runtime injects run/state/artifact roots and phase roots internally;
  - source maps and Semantic IR expose provenance;
  - shared validation sees executable/runtime contracts without treating them as public inputs;
  - YAML interop can bridge legacy `state/` values into private context during migration.

Acceptance:

- public input inspection proves generated write roots and phase roots are hidden;
- resume reconstructs the same private paths;
- source-map/Semantic IR entries identify generated context values;
- a YAML-compatible migration wrapper can pass legacy paths privately without making them normal `.orc` inputs.

## F6: Stateful Scripts Need Certified Adapters or Native Runtime Effects

Type: runtime/adapter authority gap
Status: unresolved for family parity

The candidates can compile `command-result`, but the YAML family still relies on helpers that encode real workflow semantics:

- `publish_lisp_frontend_selection_bundle.py`;
- `build_lisp_frontend_architecture_index.py`;
- `validate_lisp_frontend_design_gap_architecture.py`;
- `materialize_lisp_frontend_work_item_inputs.py`;
- `classify_lisp_frontend_work_item_terminal.py`;
- `select_lisp_frontend_blocked_recovery_route.py`;
- `update_lisp_frontend_run_state.py`;
- `record_lisp_frontend_blocked_recovery_outcome.py`;
- prerequisite/recovery reconciliation helpers.

These helpers are not equivalent. Some are deterministic projections. Some mutate run state. Some decide routing or recovery semantics.

Impact:

- A compileable `command-result` is not enough for migration parity.
- Parent/work-item `.orc` would hide semantics if it simply wrapped these scripts without certified boundaries.
- Run-state mutation and recovery reconciliation remain the largest runtime authority gap after structured-control composition.

Principled fix:

- Classify retained helpers as:
  - pure typed projection;
  - certified adapter;
  - resource-transition/state-transition primitive;
  - migration debt to replace.
- Certified adapters need stable command prefix, typed input/output contract, declared effects, path-safety rules, exit taxonomy, fixtures, negative fixtures, and source-map behavior.
- Resource/run-state mutation should move toward first-class runtime effects where practical.

## F7: Selector and Bundle Publication Need Typed Projection

Type: projection/materialization gap
Status: unresolved

The YAML selector returns `selection_status` from provider output, then runs a script to publish `selection_bundle_path`. The first `.orc` selector candidate models the provider decision only.

Impact:

- The selector candidate is useful but not parity-ready.
- Downstream workflow calls still need an authoritative selection bundle path.
- The parent drain cannot route work without this bridge.

Principled fix options:

1. Native typed projection:
   - derive `selection_bundle_path` from runtime-known provider output bundle identity;
   - make selection bundle publication a typed projection over structured provider state.

2. Certified adapter:
   - keep `publish_lisp_frontend_selection_bundle.py`;
   - certify it explicitly as deterministic projection, not hidden semantic routing.

3. Private context bridge:
   - keep selection bundle path private to runtime/StateLayout and expose typed selection values to `.orc`.

Recommendation:

- Use native typed projection if feasible.
- Use certification only as a migration bridge.

## F8: `review-revise-loop` Is Not Yet First-Class Enough for Rich Composition

Type: stdlib composition gap
Status: unresolved

`review-revise-loop` works for leaf/top-level patterns, including the plan phase. It does not yet compose cleanly inside richer typed branches, especially inside the completed branch of an implementation attempt.

Impact:

- The stdlib abstraction is real but not yet fully first-class.
- Complex workflows must split leaves or avoid natural composition.
- This weakens the case for `.orc` as a reusable workflow language until the composition path is fixed.

Principled fix:

- Treat stdlib review loops as ordinary effectful procedures that can appear wherever typed effectful procedures are valid.
- Preserve branch proof, effects, generated paths, source maps, loop state, and resume identity under nested calls.
- Add fixtures for imported stdlib review loops inside:
  - `match` cases;
  - reusable workflow calls;
  - parent workflow modules;
  - nested phase contexts.

## F9: Work-Item and Parent-Drain Composition Need a Real `backlog-drain`/Resource Model

Type: workflow-family design gap
Status: unresolved

The parent drain is not just a loop over work items. It includes:

- normal selection;
- prerequisite selection;
- design-gap drafting;
- selected work-item execution;
- blocked implementation recovery;
- recovered-gap retry;
- run-state/resource updates;
- bounded exhaustion;
- resume/recovery reconciliation.

The current `.orc` candidates cover leaves, not the full orchestration.

Impact:

- Writing a parent `.orc` now would either call incomplete surfaces or hide semantics in adapters.
- That would recreate YAML-shaped Lisp.
- The migration correctly stopped before Task 9.

Principled fix:

- Implement the missing typed/private context bridges and certified adapters so the leaf modules become parent-callable.
- Then introduce or harden a `backlog-drain`-like typed abstraction that owns selection, running, gap drafting, recovery, retry, terminal block, and bounded exhaustion.
- Parent drain should be a typed loop with accumulator and explicit terminal result, not a wrapper around YAML state files.

## F10: Command Adapter Calling Ergonomics Are Too Low-Level

Type: authoring ergonomics issue
Status: unresolved

Current `.orc` authors must hand-author argv details for adapters:

```lisp
(command-result run_neurips_backlog_checks
  :argv ("python" "workflows/library/scripts/run_neurips_backlog_checks.py" ...))
```

Impact:

- Too much script/path plumbing leaks into high-level workflow code.
- It obscures whether the command is a pure projection, a certified adapter, or hidden workflow semantics.
- It increases copy/paste risk.

Principled fix:

- Add an importable certified-adapter surface or stdlib adapter declaration.
- Let `.orc` call named adapters with typed fields rather than raw argv assembly.
- Keep source-map and command-boundary evidence.

## F11: Migration Evidence Must Distinguish Leaf Compile Success From Parent-Callable Parity

Type: migration evidence gap
Status: unresolved

The migration now has several compileable leaves. That is useful, but it is not parity.

Impact:

- Without explicit labels, future readers could mistake leaf compile success for workflow-family migration success.
- `--require-non-regressive` and `--require-promotable` should not pass on leaf-only evidence.

Current mitigation:

- `migration_record.md` marks each candidate as a first-pass leaf or compile candidate.
- `parent_drain_readiness_blockers.md` says the parent should not be implemented as a wrapper.

Principled fix:

- Keep parity tooling strict:
  - leaf compile evidence is necessary but insufficient;
  - parent-callable behavior must be proven;
  - output, terminal-state, artifact, resume/reuse, and recovery parity must be machine-computed;
  - `--require-promotable` must fail until the full family is callable and non-regressive.

## Priority Work Items

### P0: Nested Structured-Control Composition

Implement or design the lowering/runtime route where structured `match`, structured `repeat_until`, and stdlib `review-revise-loop` can appear inside branch scopes and procedure calls while still passing shared validation.

This is the most important blocker because it prevents the implementation phase and work item from becoming single parent-callable workflows.

### P0: Private Executable Context Bridge

Define how Workflow Lisp carries run roots, state roots, artifact roots, phase roots, generated write roots, selection state, and recovery state internally without exposing them as public high-level workflow inputs.

This is required for parity with YAML workflows that currently expose many `state/` paths.

### P0: Run-State / Resource-Transition Ownership

Move run-state completion, blocked recovery recording, prerequisite edge reconciliation, and terminal drain updates into typed runtime effects or certified adapters.

This is required before the parent drain can be more than a wrapper.

### P1: Union-to-Union Variant Mapping Fix

Fix union return normalization so source match variants and returned target variants are independent.

### P1: Variant-Scoped Field Identity

Allow the same logical field name in different union variants using variant-scoped artifact/json-pointer identity, or document the current limitation clearly.

### P1: Native Typed Projection for Bundle Paths

Replace deterministic publication scripts like `publish_lisp_frontend_selection_bundle.py` with typed projections or certified adapters.

### P1: Certified Adapter Declaration Ergonomics

Provide a cleaner `.orc` surface for certified adapters so authors call typed adapter functions instead of assembling raw argv lists in high-level workflow code.

## Design Documents To Update

These findings should feed into:

- `docs/design/workflow_lisp_runtime_migration_foundation.md`
  - private executable context bridge;
  - StateLayout/private path ownership;
  - typed projection/materialized view authority;
  - adapter/runtime output authority.

- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  - nested structured control as a hard composition prerequisite;
  - stdlib review loops composing under branch scopes;
  - parent-callable workflow-family migration criteria.

- `docs/design/workflow_lisp_state_layout.md`
  - private context identity;
  - run/phase/call/loop generated path ownership;
  - YAML compatibility bridge boundaries.

- `docs/design/workflow_command_adapter_contract.md`
  - certified adapter ergonomics;
  - distinction between typed projections, state transitions, and hidden semantic glue.

- `docs/lisp_workflow_drafting_guide.md`
  - document current limitations if they remain unfixed:
    - nested structured control;
    - variant field naming;
    - low-level `state/` paths at public boundaries.

- `docs/plans/2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md`
  - keep leaf-candidate execution until the P0 blockers are resolved.

## Bottom Line

The migration is not blocked by Lisp syntax. It is blocked by first-class workflow composition.

Workflow Lisp has enough implemented substrate to express useful typed leaves, but the drain family needs more:

- nested structured control that survives shared validation;
- stdlib loops that compose in branches;
- private runtime context instead of public generated state paths;
- typed projections and certified adapters for deterministic bundle/state helpers;
- resource/run-state transition ownership;
- strict parity evidence that distinguishes leaf compile success from parent-callable migration.

Until those land, the right migration shape is exactly what the execution produced: compileable typed leaves, explicit bridge records, and no parent `.orc` wrapper pretending to be a principled migration.
