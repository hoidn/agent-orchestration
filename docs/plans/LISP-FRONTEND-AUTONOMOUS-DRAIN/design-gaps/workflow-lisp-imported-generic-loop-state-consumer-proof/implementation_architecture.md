# Workflow Lisp Imported Generic Loop-State Consumer Proof Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-imported-generic-loop-state-consumer-proof`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected Section 12.3 prerequisite gap from the
target design:

- prove one explicit imported generic future-consumer composition pattern for
  the Stage 10 review-loop-shaped route;
- keep that pattern to one imported generic consumer `defproc` body that
  combines:
  - caller-owned `CompletedT` and `InputsT`,
  - compile-time `ProcRef` review/fix hooks,
  - authored `loop-state`,
  - ordinary `loop/recur :state`,
  - ordinary `match`,
  - typed `:on-exhausted` projection;
- add one focused proof fixture and only the narrow substrate repairs required
  if that exact composition still fails with `procedure_call_unknown`,
  `type_unknown`,
  `loop_recur_state_type_invalid`,
  or leaked `TypeParamRef` evidence, including the compile-time `ProcRef`
  binding handoff from a specialized imported consumer body into ordinary
  procedure lowering when typing has already preserved the selected hook
  metadata;
- prove that strict `ReviewFindings.items_path` contracts, source maps, effect
  visibility, and runtime-erasure rules survive the composed imported route.

Out of scope for this slice:

- same-module helper `defproc` decomposition inside the imported generic
  consumer;
- implementing ordinary stdlib `review-revise-loop` in `std/phase.orc`;
- review-loop bridge retirement, public API changes, or Stage 10 parity work;
- new loop-state syntax, new `:forall` semantics, or new structural-constraint
  vocabulary beyond consuming already-landed surfaces;
- runtime changes under `orchestrator/workflow/`, new command adapters,
  runtime-native effects, report parsing, or pointer-as-authority behavior;
- redesign of shared Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, proof rules, or resume checkpoint identity.

This is a bounded implementation architecture for the selected future-consumer
proof only. It does not replace the umbrella Workflow Lisp specification or
the downstream stdlib review-loop implementation architecture.

## Problem Statement

The current checkout already proves the prerequisite pieces in isolation, but
not the exact future-consumer shape that Section 12.3 requires before Stage 10
can resume.

Fresh checkout evidence shows the gap is now narrowly compositional:

1. `orchestrator/workflow_lisp/loop_state.py` and
   `tests/test_workflow_lisp_loop_state.py` already establish one frontend-owned
   authored loop-state carrier surface.
2. `tests/test_workflow_lisp_procedures.py` already proves imported generic
   loop-state seed/update specializations such as
   `test_compile_stage3_imported_generic_loop_state_seed_specializes_without_runtime_leaks`
   and
   `test_compile_stage3_imported_generic_loop_state_update_reuses_specialized_carrier`.
3. `tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts`
   already proves strict `ReviewFindings.items_path` relpath contracts survive
   ordinary authored loop-state carriage.
4. The public `review-revise-loop` surface is still the bridge-owned
   provider/prompt route in `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
   and `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`, so this
   prerequisite must not widen into Stage 10 implementation.
5. No existing fixture combines all of the following in one imported generic
   future-consumer definition:
   caller-owned `CompletedT` / `InputsT`,
   compile-time `ProcRef` hooks,
   loop-state carriage,
   `loop/recur`,
   `match`,
   and typed `:on-exhausted` projection.

That missing combined proof is exactly the target-design trigger:

- the standalone loop-state carrier surface may pass its own fixtures;
- imported generic seed/update helpers may pass their own fixtures;
- the Stage 10-shaped imported consumer can still fail when those surfaces meet
  inside one generic control-flow body.

The selected gap is therefore not "add another generic feature." It is:

- choose one supported imported future-consumer composition pattern;
- prove that exact pattern compiles and lowers through ordinary frontend paths;
- keep the proof narrow enough that a failure clearly routes either to a small
  owner-module repair or back to a different prerequisite, instead of widening
  into stdlib review-loop implementation.

Fresh blocked-run evidence narrows the remaining unknown further. After the
proof-first fixture and bounded typing/specialization repairs landed, the
composed route still fails during lowering with
`procedure_call_unknown: unknown procedure callee review` from the imported
consumer body. The specialized typed helper already preserves compile-time
`ProcRef` metadata, so the open seam is no longer generic type binding. The
open seam is the specialization-to-lowering handoff that must carry those
selected `ProcRef` bindings far enough for ordinary procedure lowering to
resolve `review` and `fix` as concrete compile-time callees.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
  - empty in this checkout; no additional local steering text is present
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `12.3 Imported Generic Loop-State Consumer Proof Dependency`
  - `14.1.1 Authoritative First-Tranche Schema`
  - `15. Review/Revise Semantic Contract`
  - `16. Loop State Model`
  - `18. Loop Exhaustion Projection`
  - `19. Evidence Authority`
  - `20. Effects Contract`
  - `21. Source Maps And State Layout`
  - `24. Incremental Implementation Plan`
    - `Stage 9A - Imported Generic Loop-State Consumer Proof`
  - `27. Acceptance Checks`
  - `30. Summary Recommendation`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `7. Types`
  - `8.8 defproc`
  - `10. Sequential Binding: let*`
  - `11. Pattern Matching`
  - `13. Loops`
  - `16. Effect System`
  - `22. Provider Result`
  - `23. Command Result`
  - `27. review-revise-loop`
  - `44. Typed Frontend AST`
  - `51. defproc Lowering`
  - `57. review-revise-loop Lowering Contract`
  - `63. Variant Proof Validation`
  - `74. Source Map Requirements`
  - `95. Lowering Tests`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must preserve these guardrails:

- keep the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  constraint check -> instantiate monomorphic helper -> typecheck instantiated
  helper -> lowering -> shared validation;
- keep imported future-consumer behavior on ordinary frontend surfaces rather
  than a bridge-only or review-loop-specific compiler branch;
- keep the chosen proof pattern compile-time-only with respect to type
  parameters, `ProcRef`, provider refs, and prompt refs;
- keep typed state and validated artifact values authoritative, with reports as
  views and pointer files as representations;
- keep `ReviewFindings.items_path` as a strict relpath contract rooted under
  `artifacts/work`;
- keep command-boundary semantics visible under
  `docs/design/workflow_command_adapter_contract.md` when review/fix hooks use
  `command-result` or certified adapters;
- do not use the empty `docs/steering.md` file as permission to broaden scope.

The baseline frontend specification is a compatibility boundary here, not the
active queue. This slice may consume later accepted deltas such as parametric
specialization, structural constraints, authored `loop-state`, and authored
`loop/recur :on-exhausted`, while preserving the baseline invariants:

- no second execution engine;
- no YAML-as-authority fallback;
- no report parsing for semantic state;
- variant-specific fields remain proof-gated;
- lowering still terminates in shared Core Workflow AST plus shared validation.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-loop-recur-on-exhausted-projection/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-structural-parametric-constraints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-revise-loop-implementation/implementation_architecture.md`

### Decisions Reused

- Reuse the compile-time specialization rule:
  resolve concrete types -> check constraints -> instantiate monomorphic helper
  -> typecheck instantiated helper -> lower.
- Reuse the `loop-state` surface as the only authored carrier route for this
  proof; do not introduce a second loop-frame representation.
- Reuse authored `loop/recur :on-exhausted` rather than review-loop-specific
  hidden exhaustion injection.
- Reuse compile-time `ProcRef` invocation and runtime-erasure rules; review/fix
  hooks must remain concrete before lowering and must not leak to runtime
  state, Semantic IR, Executable IR, or persisted artifacts.
- Reuse the review-loop report/findings path split so strict
  `ReviewFindings.items_path` rules remain active through the composed route.
- Reuse the source-map/runtime-lineage substrate:
  `SourcePosition`,
  `SourceSpan`,
  macro expansion stacks,
  `LispFrontendDiagnostic`,
  `LoweringOrigin`,
  and `LoweringOriginMap`.
- Reuse the rule that runtime checkpoint identity belongs to the shared
  executable/runtime bridge, not to generated helper or carrier names.

### New Decisions In This Slice

- Choose one supported composition pattern for the prerequisite proof:
  one imported generic consumer `defproc` body, not same-module helper
  decomposition.
- Keep the proof fixture outside `std/phase.orc`; the selected route is a
  synthetic imported generic consumer that models Stage 10 control shape
  without prematurely implementing the actual stdlib loop.
- Require that the proof fixture uses the exact first-tranche
  `ReviewFindings` carrier shape from the target design
  (`schema_version` plus strict `items_path`) rather than a looser placeholder.
- Treat `tests/test_workflow_lisp_procedures.py` as the primary proof owner for
  the composed imported route, with at most one narrow regression/smoke check
  in `tests/test_workflow_lisp_phase_stdlib.py` if strict findings-path or
  bridge non-regression needs confirmation.
- Treat compile-time `ProcRef` binding handoff from a specialized imported body
  into lowering as a first-class seam of this prerequisite. If symbolic
  `review` or `fix` names survive into lowering after specialization, repair
  that seam inside the existing lowering ownership rather than routing to a new
  prerequisite or widening bridge semantics.
- If the proof exposes a bug, repair only the smallest existing owner module
  already responsible for that seam; do not widen the slice into new helper
  owners or bridge replacement.

### Conflicts Or Revisions

The parametric loop-state authoring slice intentionally stopped after proving:

- authored loop-state carriers exist;
- simple imported generic seed/update helpers specialize cleanly; and
- strict findings-path contracts survive authored local carriage.

This slice revises none of those semantics. It extends the evidence boundary:

- from isolated carrier proof
- to one imported future-consumer composition proof.

The target design explicitly allows either one generic consumer body or a
same-module helper `defproc` boundary. This slice narrows that choice
deliberately:

- same-module helper decomposition is not supported by this prerequisite;
- Stage 10 should be written in the chosen single-body pattern unless a later
  bounded prerequisite explicitly proves the helper route.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, command
adapter policy, or variant proof.

## Ownership Boundaries

This slice owns:

- one focused imported future-consumer proof fixture that combines imported
  generic specialization, `ProcRef` hooks, `loop-state`, `loop/recur`,
  `match`, and typed `:on-exhausted`;
- the assertions that the composed route:
  - compiles and lowers,
  - preserves compile-time `ProcRef` binding handoff through lowering,
  - preserves strict findings-path contracts,
  - preserves source-map provenance,
  - preserves effect visibility,
  - leaks no `TypeParamRef` or runtime ref values;
- any narrow repairs in existing owner modules if that exact proof exposes a
  composition bug, most likely under:
  - `orchestrator/workflow_lisp/procedure_typecheck.py`
  - `orchestrator/workflow_lisp/procedure_specialization.py`
  - `orchestrator/workflow_lisp/loop_state.py`
  - `orchestrator/workflow_lisp/typecheck_dispatch.py`
  - `orchestrator/workflow_lisp/lowering/procedures.py`
  - `orchestrator/workflow_lisp/lowering/control_loops.py`
  - `orchestrator/workflow_lisp/lowering/values.py`
  - `orchestrator/workflow_lisp/source_map.py`

This slice intentionally does not own:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- bridge retirement or public `review-revise-loop` API changes
- same-module helper resolution after imported generic specialization
- runtime execution/state modules under `orchestrator/workflow/`
- new command adapters, scripts, runtime-native effects, or pointer/report
  authority policy

## Current Checkout Facts

The current checkout is already beyond the earlier prerequisites and should be
treated as such:

- `orchestrator/workflow_lisp/form_registry.py` already admits `loop-state` as
  a compiler-known authored surface.
- `orchestrator/workflow_lisp/expressions.py` already defines
  `LoopStateField`,
  `LoopStateSeedExpr`,
  `LoopStateUpdateExpr`,
  and authored `loop/recur :on-exhausted`.
- `orchestrator/workflow_lisp/loop_state.py` already owns loop-state typing and
  generated carrier metadata.
- `tests/test_workflow_lisp_procedures.py` already proves imported generic
  loop-state seed and update helpers specialize without runtime leaks.
- `tests/test_workflow_lisp_phase_stdlib.py` already proves strict
  `ReviewFindings.items_path` relpath behavior survives authored loop-state
  carriage.
- the blocked implementation attempt already landed bounded pre-lowering fixes
  in `orchestrator/workflow_lisp/procedure_specialization.py` and
  `orchestrator/workflow_lisp/procedure_typecheck.py` so inherited
  specialization metadata and bound `ProcRef` parameters survive typing.
- the remaining reproduced blocker is
  `procedure_call_unknown: unknown procedure callee review` during lowering of
  the imported consumer body, so the unresolved seam is now the
  specialization-to-lowering binding handoff rather than generic caller-side
  type resolution.
- the checkout still exposes the old bridge-style public
  `review-revise-loop` route using provider/prompt operands and caller-owned
  `:returns`, so this proof slice must not edit that route as a shortcut.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is still empty,
  so there is no competing in-progress ledger authority to reconcile here.

The missing proof is therefore specific:

- imported generic carrier helpers are already proven;
- local loop-state findings-path carriage is already proven;
- the composed imported future-consumer route is not yet proven.

## Chosen Future-Consumer Pattern

This slice chooses the narrower of the two target-design options:

- supported pattern:
  one imported generic consumer `defproc` body
- unsupported in this slice:
  same-module helper `defproc` decomposition inside that imported generic
  consumer

### Rationale

The selector bundle asks for one bounded prerequisite proof, not a second
procedural-substrate expansion. A single imported generic consumer body is the
smallest pattern that still exercises the Stage 10 semantic joints:

- imported generic specialization;
- compile-time `ProcRef` review/fix parameters;
- caller-owned `CompletedT` and `InputsT`;
- structural constraints on those caller-owned records;
- authored loop-state carriage with fixed stdlib-owned fields;
- ordinary `loop/recur`, `match`, `continue`, `done`, and `:on-exhausted`;
- source maps, effect visibility, and runtime erasure.

Choosing same-module helper decomposition here would reopen a second seam:
post-specialization same-module procedure resolution inside imported generic
definitions. That is a valid future gap if needed, but it is broader than this
selector's proof-only scope.

### Required Fixture Shape

The proof fixture should live in test-owned temporary `.orc` modules and model
the future Stage 10 route without editing `std/phase.orc`.

Representative shape:

```lisp
(defproc review-loop-consumer
  :forall (CompletedT InputsT)
  ((completed CompletedT)
   (inputs InputsT)
   (initial_review_report ReviewReportPath)
   (initial_findings ReviewFindings)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
   (max_iterations Int))
  :where ((CompletedT is-record)
          (InputsT is-record))
  -> ReviewLoopResult

  (loop/recur
    :max max_iterations
    :state (loop-state
             (completed CompletedT completed)
             (latest_review_report ReviewReportPath initial_review_report)
             (latest_findings ReviewFindings initial_findings)
             (status ReviewDecisionStatus REVISE))
    :on-exhausted
      (variant ReviewLoopResult EXHAUSTED
        :last_review_report state.latest_review_report
        :findings state.latest_findings
        :reason "max_iterations_exhausted")
    (fn (state)
      (let* ((decision (review state.completed inputs)))
        (match decision
          ((APPROVE approved)
           (done
             (variant ReviewLoopResult APPROVED
               :review_report approved.review_report
               :findings approved.findings)))

          ((REVISE revise)
           (let* ((next_completed
                    (fix state.completed inputs revise.findings)))
             (continue
               (loop-state :like state
                 :completed next_completed
                 :latest_review_report revise.review_report
                 :latest_findings revise.findings))))

          ((BLOCKED blocked)
           (done
             (variant ReviewLoopResult BLOCKED
               :review_report blocked.review_report
               :blocker_class blocked.blocker_class
               :findings blocked.findings))))))))
```

The exact names may differ, but the proof must preserve these properties:

- the consumer itself is imported generic `.orc`, not local-only code;
- review and fix are compile-time `ProcRef` parameters invoked inside the
  generic consumer body;
- the loop-state carrier contains both caller-specialized and fixed stdlib-like
  fields;
- `:on-exhausted` constructs a typed exhausted result from carried loop-state
  outputs;
- no hidden bridge-owned state or helper route is involved.

### Deliberately Excluded Pattern

This slice does not support:

- an imported generic consumer that calls a same-module helper `defproc`
  defined in the same imported module after specialization;
- local type aliases or helper-owned intermediate surfaces that would require
  a second proof of post-specialization name resolution.

If Stage 10 later needs that shape, it must reopen a separate bounded
prerequisite instead of silently widening this proof slice.

## Implementation Approach

### Primary Proof Owner

Use `tests/test_workflow_lisp_procedures.py` as the primary proof owner because
the selected gap is about imported generic procedure composition, not about the
current public review-loop bridge.

The proof should:

- create temporary imported modules under a test-owned source root;
- define the exact first-tranche `ReviewFindings` carrier shape there;
- define test-owned `ReviewDecision` and `ReviewLoopResult` unions mirroring
  the target-design terminal protocol closely enough to exercise the route;
- define one imported generic consumer `defproc` body following the supported
  pattern above;
- define local concrete `review` and `fix` procedures in the entry module and
  pass them as `proc-ref` arguments;
- demonstrate that those selected `proc-ref` arguments become concrete
  lowering-time bindings inside the specialized imported consumer body rather
  than surviving as free symbolic `review` / `fix` callees;
- compile with `validate_shared=True`.

### Proof Assertions

The proof fixture must assert at least:

- the imported generic consumer specializes successfully;
- the specialized procedure signature contains no `TypeParamRef`;
- serialized Semantic IR and Executable IR contain no leaked
  `TypeParamRef`,
  `ProcRef`,
  provider refs,
  prompt refs,
  or generated `%loop-state` carrier names;
- lowering resolves `review` and `fix` through the preserved compile-time
  binding environment, with no unresolved symbolic consumer-local callee name
  left after specialization;
- the lowered workflow contains an ordinary `repeat_until` step rather than a
  review-loop-specific bridge construct;
- the carried `ReviewFindings.items_path` field preserves the strict relpath
  contract through the generated loop outputs/projections;
- source-map or origin data shows both the entry module and the imported
  generic consumer module;
- no `procedure_call_unknown`,
  `type_unknown`,
  or `loop_recur_state_type_invalid`
  diagnostic appears for the supported pattern.

### Narrow Repair Rule

If the proof fails, repair only the seam it exposes:

- imported generic call-site specialization or type binding:
  `procedure_typecheck.py` / `procedure_specialization.py`
- lowering-boundary `ProcRef` binding handoff, compile-time callee resolution,
  or procedure-lowering runtime erasure after specialization:
  `lowering/procedures.py`
- loop-state carrier type propagation:
  `loop_state.py` / `typecheck_dispatch.py`
- lowered loop/projection/output contracts:
  `lowering/control_loops.py` / `lowering/values.py`
- imported provenance:
  `source_map.py` / lowering origin helpers

Do not repair failures by:

- editing `std/phase.orc`;
- widening the bridge;
- adding a new helper-only expansion path;
- changing runtime loop execution semantics.

## Verification Strategy

The verification surface for this slice is intentionally small and deterministic:

1. collect the targeted test module if new tests are added or renamed;
2. run the narrow imported generic procedures selector that owns the new
   future-consumer proof;
3. run the strict findings-path regression if the proof relies on that contract
   continuing to hold;
4. optionally run one bridge smoke selector only to confirm the proof slice did
   not destabilize the current bridge while it remains in place.

Representative command families for the later execution plan:

- `pytest --collect-only` on `tests/test_workflow_lisp_procedures.py`
- focused `tests/test_workflow_lisp_procedures.py -k 'loop_state and imported and consumer'`
- focused `tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts`
- focused bridge smoke only if a touched owner module is shared with the bridge

This slice does not require orchestrator/demo smoke runs because it drafts one
implementation architecture only and does not modify workflow execution code.

## Acceptance Conditions

This prerequisite is complete when all of the following are true:

- one imported generic future-consumer fixture models the chosen Stage 10
  control shape with caller-owned `CompletedT` / `InputsT`, compile-time
  `ProcRef` hooks, authored `loop-state`, ordinary `loop/recur`, and typed
  `:on-exhausted`;
- the supported composition pattern is explicit:
  one imported generic consumer `defproc` body;
- the fixture compiles and lowers without
  `procedure_call_unknown`,
  `type_unknown`,
  `loop_recur_state_type_invalid`,
  or unresolved `TypeParamRef`;
- compile-time `ProcRef` selections supplied by the caller survive
  specialization into lowering so the imported consumer resolves `review` and
  `fix` without unresolved symbolic callee names or runtime `ProcRef` leakage;
- strict `ReviewFindings.items_path` contracts survive the composed imported
  route;
- runtime-visible artifacts contain no leaked `TypeParamRef`,
  `ProcRef`,
  provider refs,
  prompt refs,
  or generated `%loop-state` carrier names;
- source maps or equivalent origin assertions cover both the authored entry
  module and the imported generic consumer definition;
- the slice leaves `std/phase.orc` and the bridge-owned public
  `review-revise-loop` route unchanged;
- same-module helper decomposition is either still unsupported or explicitly
  proven in a separate future slice, but is not implicitly claimed by this one.

## Non-Goals And Stop Conditions

Stop and hand the work back to a different prerequisite if:

- the only path to passing the proof requires same-module helper decomposition
  support inside imported generic consumers;
- the failure is actually missing `:forall`, structural-constraint, or
  loop-state authoring substrate that contradicts the already-landed
  prerequisites;
- the only apparent fix is to modify `std/phase.orc` or the bridge-owned
  `review-revise-loop` route;
- the route requires runtime changes under `orchestrator/workflow/`.

That stop condition is part of the architecture. This slice is a proof
boundary, not a fallback bucket for downstream Stage 10 work.
