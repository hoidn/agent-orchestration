# Workflow Lisp Stdlib Review-Loop Ownership Bridge Retirement Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-stdlib-review-loop-ownership-bridge-retirement`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected residual Stage 10 and Stage 12
convergence gap from the target design:

- preserve and stabilize the already-landed direct `std/phase` ownership move
  for the promoted review-loop body;
- make `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` the only
  promoted owner of:
  `ReviewReportPath`,
  `ReviewFindingsJsonPath`,
  `ReviewFindings`,
  `ReviewDecision`,
  `ReviewLoopResult`,
  the hidden seed route,
  and the review-loop body itself;
- keep the retired support-module hop through
  `orchestrator/workflow_lisp/stdlib_modules/std/phase_review_loop_support.orc`
  absent from the promoted route;
- finish the bounded ordinary-frontend support work that the direct `std/phase`
  route exposed across same-module and imported procedure boundaries:
  local-versus-qualified type canonicalization for review-loop signatures,
  imported procedure signatures, proc-ref callback/result typing, loop-state
  carriers, generated seeds, and command-result return typing;
- retire the remaining compiler compatibility owners that still model
  `review-revise-loop` as a legacy bridge:
  `StdlibSpecializationExpr`,
  `__stdlib-specialization__`,
  `phase-review-loop`,
  the legacy allow/deny policy,
  and review-loop-specific typecheck/lowering helpers;
- refresh the focused fixtures, tests, and architecture assertions so they
  prove ordinary imported stdlib ownership instead of bridge survival.

Out of scope for this slice:

- new generic imported `.orc` expansion substrate, new `ProcRef`
  specialization semantics, structural-constraint vocabulary, or authored
  loop-state surface work beyond consuming the already-landed slices;
- redesign of `loop/recur`, `resume-or-start`, `resource-transition`,
  `finalize-selected-item`, or `backlog-drain`;
- runtime changes under `orchestrator/workflow/`, new command adapters,
  new runtime-native effects, report parsing, or pointer-as-authority changes;
- broader cleanup unrelated to the selected review-loop ownership and bridge
  retirement path;
- promotion bookkeeping beyond the focused parity and integration evidence
  needed to prove the direct `std/phase` route.

This is a bounded implementation architecture for one selected residual gap
only. It does not replace the parent Workflow Lisp specification or reopen the
already-proven prerequisites.

## Problem Statement

The selected target design assumes two facts at once:

1. Stage 10 should be implemented as an ordinary imported stdlib route owned by
   `std/phase`.
2. Stage 12 should remove promoted-path dependency on compiler-special
   review-loop behavior.

Current checkout evidence shows that the repository is now between those two
states.

What is already true:

- `std/phase.orc` already owns the exact first-tranche public types
  `ReviewReportPath`,
  `ReviewFindingsJsonPath`,
  `ReviewFindings`,
  `ReviewDecision`,
  and `ReviewLoopResult`.
- `std/phase.orc` already exposes the target public syntax shape:
  `:ctx`,
  `:completed`,
  `:inputs`,
  `:review`,
  `:fix`,
  and `:max`.
- `std/phase.orc` already owns the inlined single-body review-loop
  implementation, and
  `orchestrator/workflow_lisp/stdlib_modules/std/phase_review_loop_support.orc`
  is already gone from the checkout.
- `tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_consumer_specializes_without_runtime_leaks`
  already proves the Section 12.3 single-body imported future-consumer route.
- `tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_specializes_to_ordinary_typed_forms`
  already asserts that ordinary review-loop compilation leaves no surviving
  `StdlibSpecializationExpr` nodes in typed workflow or procedure bodies.

What is still inconsistent:

- `phase_stdlib.py`, `phase_stdlib_typecheck.py`,
  `typecheck_dispatch.py`, `lowering/phase_stdlib.py`,
  `expressions.py`, `functions.py`, and `form_registry.py` still carry
  bridge-only policy, request-kind, AST, or lowering code for
  `phase-review-loop`.
- the direct same-module route now compiles far enough to expose an ordinary
  frontend seam where authored local names such as `ReviewReportPath` drift
  from qualified identities such as `std/phase::ReviewReportPath` during
  procedure-signature compatibility checks, imported procedure signatures,
  proc-ref callback/result typing, generated-seed typing, and command-result
  return typing.
- some focused tests still assert the older bridge contract directly, including
  legacy allow/deny policy behavior and the presence of
  `(__stdlib-specialization__ phase-review-loop ...)` in `std/phase.orc`,
  even though the current `std/phase.orc` no longer contains that text.
- the originally drafted combined verification sweep can be blocked by unrelated
  dirty-checkout failures in reusable-phase-state relpath-contract validation
  under `orchestrator/contracts/output_contract.py`, which is outside the
  review-loop concept footprint unless the failure is reproduced from touched
  review-loop surfaces.

Those inconsistencies are not a reason to re-run prerequisites. They are the
selected design gap itself: the ownership move has landed, but the bounded
supporting cleanup and verification contract have not been updated to that new
state.

This slice therefore treats the current mismatch as:

- `stale_duplicate` for tests and helper modules that still restate the bridge
  as active authority; and
- `routing_mismatch` for active Python owners and verification instructions that
  still assume the pre-inline bridge/support-module route; and
- `implementation_architecture_under_scoped` for the too-narrow same-module
  framing of the type-identity and verification-boundary work actually needed
  to finish the direct route without widening into unrelated reusable-phase-
  state regressions.

The missing architecture is the bounded convergence step that makes the direct
`std/phase` route fully authoritative, normalizes its ordinary type identity at
the review-loop boundaries, and removes the now-redundant bridge surfaces
instead of continuing to guard them.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
  - empty in this checkout; it adds no extra local scope
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `12.3 Imported Generic Loop-State Consumer Proof Dependency`
  - `14.1.1 Authoritative First-Tranche Schema`
  - `15. Review/Revise Semantic Contract`
  - `18. Loop Exhaustion Projection`
  - `19. Evidence Authority`
  - `20. Effects Contract`
  - `21. Source Maps And State Layout`
  - `24. Incremental Implementation Plan`
    - `Stage 10 - Implement std/phase.orc review-revise-loop`
    - `Stage 12 - Remove Promoted Dependency On Compiler-Special Review Loop`
  - `25. Diagnostics`
  - `27. Acceptance Checks`
  - `30. Summary Recommendation`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `8.8 defproc`
  - `8.9 defworkflow`
  - `11. Pattern Matching`
  - `13. Loops`
  - `16. Effect System`
  - `17. Artifact Authority`
  - `18. Reports Are Views, Not State`
  - `23. Command Result`
  - `27. review-revise-loop`
  - `51. defproc Lowering`
  - `57. review-revise-loop Lowering Contract`
  - `63. Variant Proof Validation`
  - `66. Report-Authority Validation`
  - `74. Source Map Requirements`
  - `95. Lowering Tests`
  - `103. Stage 5: Phase And Context Library`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must preserve these guardrails:

- keep the promoted review loop on ordinary imported `.orc` composition, not a
  compiler-owned request kind;
- keep the public review-loop protocol exact and stdlib-owned, with any richer
  workflow-specific terminal projection outside the loop under ordinary
  proof-gated `match`;
- keep reports as views, typed findings/state as authority, and pointer files
  as representations;
- keep `validate_review_findings_v1` or any equivalent findings validator on an
  explicit `command-result` / certified command-adapter boundary governed by
  `docs/design/workflow_command_adapter_contract.md`;
- keep runtime execution Lisp-agnostic: the runtime executes shared
  `repeat_until`, `match`, `provider-result`, `command-result`,
  materialization, and projection surfaces only;
- keep source maps and effect visibility intact for generated seed values,
  selected `ProcRef` hooks, the loop frame, and the findings-validation command
  boundary;
- do not use the empty `docs/steering.md` file as permission to widen scope.

The baseline frontend specification remains a compatibility boundary, not the
active work queue. This slice may consume later landed deltas such as
parametric specialization, authored loop-state, and authored
`loop/recur :on-exhausted`, while preserving the baseline invariants:

- no second execution engine;
- no YAML-as-authority fallback;
- no report parsing as semantic state;
- no unproved variant-field access;
- lowering still terminates in shared Core Workflow AST plus shared validation.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-revise-loop-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-generic-loop-state-consumer-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-track-a-denylist-architecture-tests/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`

### Decisions Reused

- Reuse the single-body imported generic consumer pattern as the accepted
  review-loop-shaped implementation substrate. This slice does not reopen
  helper decomposition or alternate consumer shapes.
- Reuse compile-time `ProcRef` specialization and runtime-erasure rules:
  review/fix hooks must resolve to concrete procedures before lowering and must
  not leak into runtime state, Semantic IR, Executable IR, or persisted loop
  frames.
- Reuse authored loop-state and typed `:on-exhausted` projection rather than
  any Python-owned exhaustion injection or hidden loop-frame synthesis.
- Reuse the findings/report path split contract:
  `ReviewFindings.items_path` remains strict under `artifacts/work`, while
  review-report paths remain under `artifacts/review`.
- Reuse the imported review-loop checkpoint identity contract: generated helper
  names do not become resume authority.
- Reuse the Track A denylist intent: once this slice lands, promoted review
  loop behavior must not depend on bridge-only AST nodes, request kinds,
  policy toggles, or lowerers.
- Reuse the command-adapter contract for the findings-validation command
  boundary; explicit validator commands remain acceptable, hidden command glue
  does not.

### New Decisions In This Slice

- `std/phase.orc` becomes the only promoted semantic owner of the review-loop
  body. The extra `std/phase_review_loop_support.orc` hop is retired.
- The public promoted surface is the exact stdlib contract in `std/phase`:
  exported types plus the thin `review-revise-loop` macro. Any helper proc used
  by that macro is same-module implementation detail, not a second stdlib owner.
- The repository no longer keeps a live promoted-mode review-loop bridge
  policy. Once this slice lands, the correct state is direct ownership, not
  “bridge allowed by default but denylisted in some tests.”
- Because `__stdlib-specialization__` and `StdlibSpecializationExpr` are only
  serving the retired review-loop bridge in this checkout, this slice may
  remove them entirely rather than leaving them as dead general-purpose
  extension scaffolding.
- Test authority shifts from “prove the bridge is denylisted” to “prove the
  direct stdlib route is the only surviving route.” Any compatibility fixture
  still checking for bridge presence is stale and should be rewritten or removed.

### Conflicts Or Revisions

This slice intentionally narrows and revises the earlier
`workflow-lisp-stdlib-review-revise-loop-implementation` architecture.

That earlier slice assumed the main remaining work was to replace a still-live
bridge with a wholly ordinary stdlib implementation. Current checkout evidence
shows that this has already partially happened:

- the public protocol is already in `std/phase`;
- the public syntax already uses `:review` / `:fix` `ProcRef` hooks;
- the single-body imported consumer proof already exists.

The remaining gap is therefore narrower than the earlier architecture's broad
Stage 10/12 scope: direct ownership convergence and bridge retirement.

This slice also explicitly resolves the current source/test mismatch in favor
of the target design and current direct `std/phase` route. Tests or helper
modules that still treat `__stdlib-specialization__` as active authority are
stale duplicates, not counter-authority.

## Ownership Boundaries

This slice owns:

- preservation of direct review-loop body ownership inside
  `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`;
- continued retirement of
  `orchestrator/workflow_lisp/stdlib_modules/std/phase_review_loop_support.orc`
  from the promoted route, including test and source-map updates that stop
  referring to it as current authority;
- removal or legacy quarantine of review-loop-only bridge artifacts in:
  `orchestrator/workflow_lisp/expressions.py`,
  `orchestrator/workflow_lisp/form_registry.py`,
  `orchestrator/workflow_lisp/phase_stdlib.py`,
  `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`,
  `orchestrator/workflow_lisp/typecheck_dispatch.py`,
  `orchestrator/workflow_lisp/lowering/phase_stdlib.py`,
  `orchestrator/workflow_lisp/functions.py`,
  `orchestrator/workflow_lisp/compiler.py`,
  and any traversal/walker owners that still mention `StdlibSpecializationExpr`;
- the bounded ordinary-frontend support changes needed because the promoted
  loop now lives in one same-module `.orc` file but compiles through ordinary
  imported procedure boundaries:
  `orchestrator/workflow_lisp/modules.py`,
  `orchestrator/workflow_lisp/type_env.py`,
  `orchestrator/workflow_lisp/compiler.py`,
  `orchestrator/workflow_lisp/typecheck_effects.py`,
  and, if focused failures prove the need, the existing ordinary procedure
  owners such as `orchestrator/workflow_lisp/procedure_typecheck.py`,
  `orchestrator/workflow_lisp/workflows.py`, and
  `orchestrator/workflow_lisp/typecheck_context.py`, but only for canonical
  local-versus-qualified type identity and explicit validator-binding
  visibility needed by the direct review-loop route;
- focused fixtures and tests that still assert bridge presence or policy
  behavior;
- updated architecture assertions proving the ordinary stdlib route is the only
  remaining route.

This slice intentionally does not own:

- new imported `.orc` expansion machinery, new generic type-system surfaces, or
  new loop-state authoring rules;
- runtime `repeat_until` behavior, resume storage, or shared validation
  semantics under `orchestrator/workflow/`;
- redesign of the findings validator itself or any new adapter/runtime-native
  promotion decision;
- unrelated stdlib forms or broad frontend cleanup outside the review-loop
  bridge retirement footprint.

## Current Checkout Facts

The current checkout already contains the substrate this slice should reuse:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` defines the exact
  first-tranche review-loop public types, the inlined single-body helper proc,
  and a thin macro that expands to a same-surface helper call with generated
  seed values.
- that same `std/phase.orc` file now expresses the review loop as the Section
  12.3-approved single-body imported consumer shape:
  `loop/recur`,
  authored loop-state,
  typed `:on-exhausted`,
  `match`,
  `command-result validate_review_findings_v1`,
  and compile-time `ProcRef` review/fix hooks.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase_review_loop_support.orc`
  is already absent, so the remaining work must not depend on recreating it.
- `tests/test_workflow_lisp_procedures.py` already proves the imported generic
  future-consumer route without `TypeParamRef` or runtime `ProcRef` leaks.
- the progress ledger is still empty, so there is no later recorded drain event
  that supersedes the selector rationale.

The same checkout also shows the exact residual debt this slice must remove:

- `phase_stdlib_typecheck.py` still implements review-loop bridge validation
  keyed to `StdlibSpecializationExpr` and `phase-review-loop`;
- `lowering/phase_stdlib.py` still carries bridge-only denylist and
  review-loop result-contract helpers;
- `phase_stdlib.py` still exposes a review-loop legacy-bridge policy even
  though the promoted source surface has moved beyond that bridge;
- `form_registry.py` still retains `phase-review-loop` request-kind metadata;
- ordinary procedure-signature and callback/result typing still treat local and
  qualified references to the same `std/phase` exported type as distinct at
  some direct-route boundaries, with the observed failure shape:
  `ReviewReportPath` versus `std/phase::ReviewReportPath`;
- validator-binding discovery still needs to recognize the ordinary
  `command-result`/`loop-recur` ownership shape used by the inlined same-module
  review loop;
- some tests already assert the direct route (`StdlibSpecializationExpr`
  eliminated), while others still assert the opposite (bridge text/policy).

That combination makes the slice feasible without any new runtime or type-system
capability. The remaining work is bridge cleanup, bounded direct-route type
normalization across ordinary procedure boundaries, validator-binding
visibility, fixture realignment, and a verification contract that distinguishes
review-loop regressions from unrelated dirty-checkout failures.

## Proposed Architecture

### 1. Treat `std/phase.orc` Ownership As Landed And Stabilize The Direct Route

The ownership move is already landed in the checkout. This slice must preserve
that state and finish the bounded ordinary-frontend work that the same-module
route exposed through ordinary procedure compilation so one stdlib module
remains the sole promoted owner of:

- the public review-loop types;
- the hidden initial seed construction;
- the findings-validation command boundary;
- the review/fix `ProcRef` call sites;
- the loop-state carrier;
- the final `ReviewLoopResult` projection.

Required consequences:

- `std/phase.orc` stays free of `std/phase_review_loop_support` imports;
- any helper proc remains same-module implementation detail;
- the exported promoted API is reduced to the exact public contract rather than
  a two-module ownership chain.

Required ordinary-type identity rule for this slice:

- authored local names such as `ReviewReportPath`, `ReviewFindings`,
  `ReviewDecision`, and `ReviewLoopResult` are semantically identical to the
  qualified `std/phase/...` forms that resolve to the same exported types when
  they appear in the same-module helper, imported caller sites, proc-ref
  callback signatures, loop-state carriers, generated relpath seeds, and
  `command-result` return declarations;
- procedure-call compatibility, proc-ref compatibility, record/variant
  construction, and generated-seed typing must compare the canonical resolved
  identity, not authored spelling;
- imported procedure signature compatibility and proc-ref result typing must
  pass through the same canonical resolved identity instead of preserving
  authored local-versus-qualified spelling differences across module seams;
- this normalization remains a bounded ordinary-frontend support change for the
  direct review-loop route, not a new generic language feature or a new
  prerequisite gap.

Implementation order rule:

- finish the focused direct-route canonicalization selectors first;
- only start deleting bridge AST/registry/typecheck/lowering owners after the
  ordinary `std/phase` route compiles and lowers through those selectors;
- if the direct route still fails on canonical resolved-identity drift, treat
  that as unfinished work inside this gap rather than authority to recreate the
  bridge or escalate to a new prerequisite.

Preferred outcome:

- stop exporting `review-revise-loop-proc` unless another landed slice still
  needs it as a supported cross-module API;
- keep `review-revise-loop` as the public authoring entry point and keep the
  helper proc private to `std/phase`.

If current macro/procedure mechanics still require exporting the helper
temporarily, keep that as an implementation detail with an explicit removal note
in code comments or focused tests, not as a second public API surface.

### 2. Keep The Public Surface Exact And Thin

The public promoted authoring surface remains:

```lisp
(review-revise-loop name
  :ctx ctx
  :completed completed
  :inputs inputs
  :review (proc-ref review-once)
  :fix (proc-ref apply-fix)
  :max 5)
```

Required rules:

- the public surface does not reintroduce `:returns`,
  `:review-provider`,
  `:fix-provider`,
  `:review-prompt`,
  or `:fix-prompt`;
- hidden initial report/findings seeds remain compiler-generated or stdlib
  internal, not public boundary inputs;
- workflow-specific terminal unions are still constructed outside the stdlib
  loop by ordinary `match`.

The macro may stay as a syntax/ergonomics layer, but it must remain syntax-only
and expand to ordinary same-module `.orc` forms. It must not encode another
semantic bridge.

### 3. Remove The Legacy Bridge Instead Of Continuing To Guard It

After direct `std/phase` ownership is complete, the remaining bridge artifacts
stop serving a valid promoted purpose.

Retire:

- `StdlibSpecializationExpr` if review-loop is its only live use;
- `__stdlib-specialization__` if no other stdlib extension request kind exists;
- `phase-review-loop` request-kind metadata and feature tags;
- review-loop legacy allow/deny policy plumbing;
- review-loop-specific typecheck helpers whose only job is to validate the old
  bridge payload or caller-owned `:returns` contract;
- review-loop-specific lowering helpers whose only job is to lower that old
  bridge payload.

If any legacy compatibility coverage must remain for historical fixtures, it
must be quarantined under explicitly legacy names or fixtures and must not be:

- imported by `std/phase`;
- part of promoted compilation;
- represented as normal current stdlib ownership.

This is not a denylist slice anymore. The correct promoted state is bridge
absence, not bridge policy.

### 4. Preserve Semantic Guarantees Through Ordinary `.orc` Composition

Direct `std/phase` ownership must preserve the same semantic guarantees already
proved by the inlined single-body route:

- findings validation stays on an explicit `command-result` boundary whose
  command path, inputs, outputs, and failure behavior remain visible under the
  command-adapter contract;
- typed loop-state remains the authority for exhaustion projection;
- final `EXHAUSTED` output reads from loop-frame state, not from a first review
  step or hidden Python state;
- review-provider output does not replace carried evidence identity;
- source maps identify the public macro call site, same-module helper body,
  generated seed values, and command-validation step origins;
- review/fix `ProcRef` hooks remain compile-time only and do not leak into
  runtime payloads.
- same-module qualified and unqualified spellings of the stdlib-owned review
  loop types do not create distinct runtime or typechecking identities.

This slice therefore changes ownership, not semantics.

### 5. Realign Fixtures Around Direct Ownership

Focused fixtures and tests should prove four things after the slice lands:

1. direct `std/phase` ownership works;
2. no review-loop bridge artifacts survive;
3. findings validation and loop-state semantics still work;
4. stale compatibility tests are gone.

Expected fixture changes:

- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc` continues
  to exercise the public `std/phase` route, but no test may treat
  `__stdlib-specialization__` text as the expected source contract;
- tests that currently assert
  `review_loop_legacy_bridge_policy="allow"` or `"deny"` should be rewritten to
  assert ordinary compilation only, unless an explicitly legacy fixture is kept
  in quarantine;
- typed/lowering tests should assert that any generated helper specialization is
  owned by `std/phase` rather than `std/phase_review_loop_support`;
- architecture tests should assert absence of bridge artifacts in the current
  promoted route, not merely denial when a policy flag is flipped.

### 6. Keep The Command Boundary Honest

This slice touches a command-bearing stdlib loop and must preserve the
authority boundary from `docs/design/workflow_command_adapter_contract.md`.

Required rules:

- keep `validate_review_findings_v1` invoked via `command-result` or an already
  certified adapter boundary;
- do not inline findings validation in macro code, Python typecheck code, or
  lowering glue;
- do not replace the validator with hidden stdout parsing or direct JSON rewrites
  that bypass declared command outputs;
- keep command inputs/output contracts, source maps, and negative fixtures
  visible in ordinary Workflow Lisp compilation and lowering.

## Verification

Implementation of this slice should prove:

- compile-time ownership:
  no surviving `StdlibSpecializationExpr`,
  no `phase-review-loop` request kind,
  no live `std/phase_review_loop_support` dependency in promoted fixtures;
- direct-route typing continuity:
  procedure signatures, imported procedure signatures, proc-ref
  callbacks/results, loop-state carriers, generated seeds, and
  `command-result` returns treat `ReviewReportPath` and
  `std/phase::ReviewReportPath` as the same resolved type identity where they
  refer to the same `std/phase` export;
- behavioral continuity:
  `APPROVE`,
  `REVISE -> APPROVE`,
  `BLOCKED`,
  and `EXHAUSTED` still compile and lower through the ordinary stdlib route;
- command-boundary continuity:
  findings validation remains explicit and typed;
- lineage continuity:
  source maps and checkpoint identity still point back to the authored review
  loop site rather than to a retired support-module or bridge abstraction;
- public-surface cleanup:
  no tests still claim the bridge is current authority.

Minimum verification set:

- narrow `pytest --collect-only` over affected Workflow Lisp review-loop suites;
- focused `pytest` over:
  `tests/test_workflow_lisp_phase_stdlib.py`,
  `tests/test_workflow_lisp_procedures.py`,
  `tests/test_workflow_lisp_expressions.py`,
  `tests/test_workflow_lisp_macros.py`,
  `tests/test_workflow_lisp_modules.py`,
  `tests/test_workflow_lisp_lowering.py`,
  `tests/test_workflow_lisp_build_artifacts.py`,
  and `tests/test_workflow_lisp_key_migrations.py`;
- at least one compile/integration-style review-loop smoke check, not just
  isolated type or lowering tests, because this slice changes a reusable stdlib
  route and its ownership chain;
- if a broader compatibility sweep fails only in reusable-phase-state or
  relpath-contract paths rooted in `validate_reusable_phase_state` or
  `orchestrator/contracts/output_contract.py`, and the failing stack does not
  traverse a touched review-loop footprint file, record that exact evidence as
  an unrelated dirty-checkout blocker instead of widening this slice or
  relabeling it as a missing prerequisite;
- `pytest --collect-only` on any renamed test modules if test names or files
  move;
- `git diff --check`.

## Risks And Non-Goals

Primary risk:

- accidentally treating stale tests or stale pre-inline architecture wording as
  authority and reintroducing a hidden compatibility branch instead of removing
  it.

Secondary risk:

- weakening direct-route typing by papering over `ReviewReportPath` versus
  `std/phase::ReviewReportPath` mismatches instead of normalizing one canonical
  resolved identity;
- deleting bridge owners before the direct `std/phase` route has passed the
  focused canonicalization selectors, which would trade a clear typing blocker
  for a noisier mixed failure surface;
- removing bridge scaffolding too broadly if any non-review-loop path still
  depends on `StdlibSpecializationExpr`. This slice should verify actual uses
  before deleting shared scaffolding;
- absorbing unrelated reusable-phase-state relpath failures from the dirty
  checkout into this gap instead of recording them as out-of-slice evidence.

Non-goals to hold:

- do not broaden this into generic stdlib cleanup for all forms;
- do not redesign the findings validator boundary;
- do not reopen prerequisite capability debates already resolved by the landed
  imported-consumer proof and loop-state slices.

## Summary

The selected residual gap is not “implement review-revise-loop from scratch.”
The checkout already has the public types, the public syntax, the inlined
single-body imported consumer shape, and the removed support-module hop.

The remaining work is to finish ownership convergence:

- keep the loop body under direct `std/phase` ownership;
- keep the extra support module retired;
- normalize local and qualified type identity at the direct-route boundaries
  the inlined helper now exercises, including ordinary imported procedure
  signatures and proc-ref callback/result typing;
- remove the obsolete bridge AST/policy/typecheck/lowering owners;
- realign tests around the direct route; and
- verify against the focused review-loop footprint while recording unrelated
  dirty-checkout reusable-phase-state failures as separate evidence rather than
  widening the slice.

After this slice, promoted review-loop compilation should have exactly one
story: ordinary `std/phase` ownership over shared Workflow Lisp semantics, with
no bridge surviving as current authority.
