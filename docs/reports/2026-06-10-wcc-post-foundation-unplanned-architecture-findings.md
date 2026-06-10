# WCC / Post-Foundation Unplanned Architecture Findings

Status: findings report  
Created: 2026-06-10  
Scope: unexpected gaps, design flaws, and target-design revisions uncovered
during the WCC / post-foundation reconciliation and verification pass.

## Context

This report records issues uncovered while integrating the implemented WCC
middle-end route with the active post-foundation Workflow Lisp composition
target.

Relevant authorities:

- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-06-10-wcc-post-foundation-gap-reconciliation.md`

The reconciliation succeeded in landing WCC as the default schema-2 lowering
route for the migrated subset and preserving legacy schema-1 compatibility.
It also exposed several issues that are broader than ordinary bugs. Some are
missing architectural contracts; others are stale example/discoverability
problems that can cause the active drain to select or validate the wrong work.

This report is not a replacement design. It identifies where existing target
or gap designs should be revised, and where new gap designs are likely needed.

## Executive Summary

The biggest unplanned finding is that "WCC is default" is not just an
implementation flip. It creates a new public routing and discoverability
obligation: checked-in `.orc` examples, tests, and workflow-family migration
evidence now need explicit route/readiness labels. Without that, stale
legacy-only examples look like current default examples, and tests can
accidentally assert legacy behavior against the WCC route or WCC behavior
against the legacy route.

The second major finding is that several bugs fixed during reconciliation
point to missing contracts at the compiler/runtime boundary:

- executable control markers need inherited activation guards;
- terminal values need explicit provenance for union pass-through and
  returned-variant normalization;
- pure input-derived outputs need either a projection step or a stated
  shared-validation limitation;
- resume needs a normalized bundle boundary and sharper reusable-state error
  taxonomy; and
- runtime output resolution must understand active union variants, not only
  frontend variant identity.

The third major finding is that the active post-foundation design is now
correctly WCC-based, but its next compiler-lane gap is more specific than
"nested structured control": `IfExpr` support in the WCC route blocks the
Design Delta Drain work-item route. Future drain selection should target that
gap before attempting parent-drain parity.

## Findings Table

| ID | Finding | Where it appeared | Architectural implication |
| --- | --- | --- | --- |
| UAF-01 | Default WCC route exposes stale or legacy-only `.orc` examples | Representative `.orc` dry-runs after the route flip | Add route/readiness labels or a CLI route override/deprecation policy |
| UAF-02 | Tests and examples need explicit lowering-route classification | Reconciliation required many tests to pin `LoweringRoute.LEGACY` | Add fixture/example readiness taxonomy to docs and test helpers |
| UAF-03 | Legacy union pass-through metadata was under-specified | Cross-union passthrough and let-bound call tests failed | Define terminal provenance / returned-union metadata as a compiler contract |
| UAF-04 | Match case markers need inherited activation guards | WCC implementation-phase blocked route evaluated inactive loop selectors | Update executable IR/control docs with guard inheritance semantics |
| UAF-05 | WCC `IfExpr` is the immediate work-item blocker | Work-item route now reaches `wcc_lowering_route_unsupported` for `IfExpr` | Draft a focused WCC `IfExpr` gap before work-item or parent-drain parity |
| UAF-06 | Stdlib provider effects are no longer necessarily inline in parent loops | Review/revise stdlib tests had stale ownership assumptions | Clarify generated callable workflow ownership for stdlib effects |
| UAF-07 | Pure input-derived outputs do not fit current shared-validation output model | Generic loop-state seed/update pure projection fixtures | Decide whether pure projection gets an explicit step or remains validation-limited |
| UAF-08 | Reusable-state diagnostics lost specific failure causes | Resume-state tests returned generic contract errors | Add reusable-state diagnostic taxonomy if actionable errors are a design goal |
| UAF-09 | Resume has two bundle shapes in practice | `resume_workflow` path accepted patched raw `LoadedWorkflowBundle` in tests | Normalize resume bundle API and public/private input filtering contract |
| UAF-10 | Typed projection needs a WCC value class, not ad hoc opaque values | Selector bundle projection required `ProviderBundlePathExpr` support | Revise typed projection tranche around explicit projection/reference values |
| UAF-11 | Active union variant resolution is a runtime output concern too | Workflow output finalization needed inactive variant skipping | Extend variant-scoped output design into runtime signature/output resolution |
| UAF-12 | Context recognition must be structural/capability-based | `PhaseCtx`-like records across modules needed basename/field compatibility | Keep private context bridge structural, not nominal/local-name based |

## Detailed Findings

### UAF-01: Default WCC Route Exposes Stale Or Legacy-Only `.orc` Examples

Context:

After WCC became the default route for new Workflow Lisp compiles in the
migrated subset, representative `.orc` dry-runs were run as an end-to-end
smoke check:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc --dry-run
python -m orchestrator run workflows/examples/review_revise_parametric_design_docs.orc --dry-run
```

Both failed, but for different reasons.

`review_revise_design_docs.orc` failed under the WCC default with a collection
transport boundary error:

```text
workflow_boundary_collection_unsupported
```

Resolution note, 2026-06-10: default WCC now accepts lowerable
collection-typed workflow inputs, so `review_revise_design_docs.orc` no longer
requires legacy schema 1 for its `context_docs` input. Collection returns and
collection-bearing workflow refs remain outside the supported runtime boundary.

`review_revise_parametric_design_docs.orc` failed with a stale macro shape:

```text
macro_arity_error macro review-revise-loop expected 13 args but got 19
```

The CLI did not expose an obvious `--lowering-route` selector in `python -m
orchestrator run --help`, so a user copying one of these examples would hit
the WCC default even when the example still requires a legacy route or should
be treated as historical.

Root cause interpretation:

The repository now has at least three `.orc` example classes:

- WCC-default examples in the migrated subset;
- legacy schema-1 compatibility examples; and
- stale historical examples that are discoverable but not runnable as current
  guidance.

The docs and CLI do not yet make that classification durable enough.

Implication:

This is not just a broken example. It can corrupt migration evidence because a
workflow may appear to fail WCC architecture when it is actually a legacy-only
or stale fixture. It can also cause users and drains to copy the wrong model.

Recommended design or gap action:

- Add a route/readiness label taxonomy for `.orc` examples and fixtures:
  `wcc_default`, `legacy_schema1_compat`, `historical_negative`,
  `migration_candidate`, and `stale_needs_update` are sufficient starting
  labels.
- Update `workflows/README.md`, `docs/lisp_workflow_drafting_guide.md`, and
  the post-foundation plan/gap selector guidance so current examples are not
  inferred from filename recency.
- Decide whether the CLI needs an explicit route override for compatibility
  runs, or whether legacy examples should be invoked only through tests and
  migration harnesses.

### UAF-02: Tests And Examples Need Explicit Lowering-Route Classification

Context:

During reconciliation, several tests that inspect legacy/private-boundary
behavior had to be explicitly pinned to `LoweringRoute.LEGACY`. Without that,
the new default WCC route changed what the test was actually asserting.

This affected tests around build artifacts, workflow references, phase
stdlib behavior, procedures, and lowering. The fix was mostly mechanical, but
the need for the fix was architectural.

Root cause interpretation:

The lowering route is now a semantic dimension of a fixture. The test suite
previously treated route choice as an implementation detail or global default.
That assumption no longer holds.

Implication:

Unlabeled tests can give false confidence:

- a legacy compatibility test can accidentally fail under WCC for the wrong
  reason;
- a WCC regression can be hidden because the test silently ran legacy; or
- docs can cite a passing test without saying which compiler route it proves.

Recommended design or gap action:

- Add a test helper convention that requires route choice to be explicit in
  compiler/lowering tests unless the test is intentionally checking the
  default route.
- Add readiness labels to migration evidence and report indexes so
  `leaf_compile_candidate` includes the route used.
- Update post-foundation parity language to say that route identity is part of
  evidence freshness.

### UAF-03: Terminal Provenance And Union Pass-Through Metadata Were Under-Specified

Context:

Legacy route regressions appeared in cross-union translation and pass-through
tests. The failures showed that terminal expressions crossing workflow calls,
procedure calls, and let-bound local values could lose the returned union type.

The underlying bug was not a single missing branch. Several lowering paths
were independently losing or ignoring union pass-through metadata:

- match case terminal normalization ignored pass-through union type;
- workflow/procedure call terminals did not always preserve callee union type;
- let-bound terminal conversion dropped returned-union metadata.

Root cause interpretation:

The architecture said returned variants must drive outer union normalization,
but the implementation did not have a durable internal contract for terminal
provenance. Metadata was carried ad hoc by local lowerers rather than through
a typed terminal-value model.

Implication:

Even with WCC as the default, legacy compatibility remains important for
historical resume and dual-route evidence. More importantly, this bug class
shows that the general compiler architecture should make terminal provenance
first-class:

- actual returned expression;
- expected target union;
- returned union type, if known;
- active variant proof used for field access; and
- whether the terminal is a pass-through or a projection.

Recommended design or gap action:

- Add terminal provenance / returned-union metadata to the WCC and
  post-foundation design vocabulary.
- Ensure any future gap designs for union normalization include let-bound
  values, workflow calls, procedure calls, and branch projections, not just
  direct `match` arms.
- Keep legacy-route tests for this behavior until schema-1 is retired.

### UAF-04: Executable Control Markers Need Inherited Activation Guards

Context:

The WCC implementation-phase fixture exposed a runtime/control bug in the
`BLOCKED` route. The completed-arm review loop was correctly skipped, but a
match case marker still attempted to evaluate a selector belonging to the
inactive completed-arm loop.

The fix introduced an inherited/bound predicate for match case markers and
combined it with the local case selector in executable guard evaluation.

Root cause interpretation:

The compiler and executable IR treated the match join as guarded, but not all
generated child/control marker statements inherited the parent activation
condition. In a flat executable graph, this is unsafe: inactive branch
markers can still be visited unless their activation predicate is explicit.

Implication:

This is a compiler/runtime boundary design issue. WCC can model scopes and
proofs correctly, but defunctionalized executable control nodes still need
durable activation semantics:

```text
active(match parent) AND active(case selector)
```

not merely:

```text
active(case selector)
```

Recommended design or gap action:

- Update `workflow_lisp_executable_ir.md` or the WCC design to define guard
  inheritance for defunctionalized control markers.
- Add negative tests where inactive branches contain loops, joins, or
  selectors that would crash if evaluated.
- Treat guard inheritance as part of WCC defunctionalization acceptance, not
  an executor implementation detail.

### UAF-05: WCC `IfExpr` Is The Immediate Work-Item Blocker

Context:

After the WCC merge, the Design Delta Drain work-item route progressed past
the old private-workflow and phase-family boundary blockers. The next failure
is now explicit:

```text
wcc_lowering_route_unsupported
```

for `IfExpr` in:

```text
lisp_frontend_design_delta/work_item::run-work-item
```

Root cause interpretation:

The post-foundation target still describes the compiler lane in broad
"nested structured control" terms. That was correct before WCC landed. After
the reconciliation, the next compiler blocker is narrower: WCC needs
`IfExpr` support in the same composition model as `match`, calls, loops, and
projections.

Implication:

If the drain keeps selecting generic nested-control or helper-hoisting gaps,
it will either duplicate WCC work or fix the wrong route. The active gap
index should keep pointing compiler-lane work to WCC `IfExpr` until that gap
is resolved.

Recommended design or gap action:

- Draft a focused WCC `IfExpr` gap design.
- The gap should define elaboration, ANF normalization, scope/proof/effect
  propagation, defunctionalized branch routing, source maps, and shared
  validation behavior.
- Acceptance should include the current work-item route that triggered the
  failure.

### UAF-06: Stdlib Provider Effects Are Owned By Generated Callable Workflows

Context:

Some phase-stdlib and example tests assumed that review/fix provider steps
would appear inline under the parent loop body. After the WCC/std route, the
parent loop owns repeat/call/validation control, while generated callable
workflows own provider effects such as review and fix procedures.

Root cause interpretation:

The architecture correctly says stdlib forms should compile through ordinary
import/specialization/lowering routes, but tests and some mental models still
expected inline ownership. That assumption does not hold once stdlib
procedures are ordinary generated callables.

Implication:

Source-map, Semantic IR, and review/revise parity expectations need to look
across workflow boundaries:

- the parent owns loop/control identity;
- generated callables own provider/command effects; and
- evidence must prove the call relationship and source provenance, not merely
  look for inline provider steps in the parent.

Recommended design or gap action:

- Revise stdlib/review-loop gap designs to state provider-effect ownership
  explicitly.
- Add source-map acceptance checks for caller frame, imported stdlib body,
  generated callable workflow, and provider effect.
- Avoid tests that require provider steps to be physically inline when the
  semantic ownership is a generated call boundary.

### UAF-07: Pure Input-Derived Outputs Need A Projection Contract Or A Stated Limitation

Context:

Imported generic loop-state seed/update fixtures that returned records
derived only from inputs failed shared validation because they produced no
steps. Shared validation expected workflow outputs to reference
`root.steps.*`.

The reconciliation adjusted tests so pure projection fixtures were not
treated as shared-validation workflow bundles.

Root cause interpretation:

Workflow Lisp can express pure computations, but the current workflow bundle
validation model assumes public workflow outputs are step-backed. There is
not yet a clean architectural contract for "this workflow output is a pure
projection of inputs" in the executable/shared-validation layer.

Implication:

This can recur in stdlib helpers, context constructors, default projections,
and typed bundle materialization. If pure input-derived outputs are intended
to be parent-callable workflow outputs, they need an explicit projection node
or accepted validation rule.

Recommended design or gap action:

- Decide whether pure input-derived outputs must lower to a visible
  projection step.
- If yes, add `pure_projection` or equivalent to WCC/post-foundation typed
  projection work.
- If no, document that shared-validation workflow outputs must be step-backed
  and keep pure helpers below workflow-boundary validation.

### UAF-08: Reusable-State Diagnostics Need A Taxonomy Decision

Context:

Some resume/reusable-state tests previously expected specific errors such as:

```text
resume_state_pointer_authority_forbidden
resume_state_path_unsafe
```

After reconciliation, the current fail-closed behavior reported a more
generic:

```text
resume_state_contract_invalid
```

Root cause interpretation:

The runtime is preserving safety by failing closed, but the diagnostic layer
does not consistently preserve the specific cause. That may be acceptable for
runtime safety, but it is weaker for migration debugging and operator repair.

Implication:

If the post-foundation target expects reusable-state validation to guide
recovery, a single generic error is likely too coarse. It makes stale state,
path escape, pointer-as-authority, schema mismatch, and missing artifact
harder to distinguish.

Recommended design or gap action:

- Add a reusable-state diagnostic taxonomy to the resume/reuse tranche.
- Keep the outer failure class fail-closed, but preserve inner cause codes.
- Add tests that assert specific causes where the cause is part of recovery
  behavior, and generic failure only where the caller should not branch.

### UAF-09: Resume Needs A Normalized Bundle Boundary

Context:

The resume command path had to tolerate tests that patch the loader to return
a raw `LoadedWorkflowBundle`, while the normal path expects a
`ResumeWorkflowBundle`. The force-restart rebind path also needed to filter
runtime context inputs separately from ordinary public inputs.

Root cause interpretation:

There are two bundle shapes in practice:

- a raw loaded workflow bundle; and
- a resume-aware bundle with runtime context and resume metadata.

The boundary between those shapes was implicit.

Implication:

Resume, force-restart, public/private boundary checks, and future private
context bootstrap work can drift if each path normalizes bundle data
differently.

Recommended design or gap action:

- Define a normalized resume bundle boundary in runtime/state docs.
- Specify how public inputs, private runtime context inputs, generated write
  roots, and force-restart rebinding are filtered.
- Treat tests that patch raw bundles as compatibility inputs to this
  normalization layer, not as a separate resume API.

### UAF-10: Typed Projection Needs A WCC Value Class

Context:

Selector bundle projection work needed WCC support for
`ProviderBundlePathExpr`. The implementation treated it as an opaque value
and carried projected path metadata through elaboration/defunctionalization.

Root cause interpretation:

Typed projection is becoming a first-class semantic operation, but the WCC
value model does not yet have a fully specified projection/reference value
class. Provider bundle paths, selection bundle views, compatibility pointer
views, and materialized value views are related but not identical.

Implication:

Without a typed projection value model, each new projection-like surface will
be added as a special opaque expression. That repeats the pre-WCC failure
mode at a smaller scale.

Recommended design or gap action:

- Revise post-foundation Tranche 5 to define WCC projection/reference values.
- Include authority class: semantic state, public artifact, materialized
  view, compatibility view, or provider bundle reference.
- Add source-map and StateLayout requirements for each projection/reference
  value.

### UAF-11: Active Union Variant Resolution Is Also Runtime Output Behavior

Context:

Union workflow output finalization required runtime/signature changes so
inactive variants are skipped and active variant output metadata is resolved
correctly.

Root cause interpretation:

Variant-scoped output identity is not purely a frontend lowering problem.
The runtime output resolver and workflow signature projection must understand
that only the active variant's required fields are meaningful.

Implication:

Post-foundation Tranche 2 should not stop at generated artifact names or JSON
pointers. It should include runtime workflow output resolution and final
signature behavior.

Recommended design or gap action:

- Extend variant-scoped output identity acceptance to runtime output
  finalization.
- Add tests where inactive variants reuse field names, omit required inactive
  fields, and still resolve the active variant successfully.
- Ensure parity reports compare active variant outputs, not all variant
  fields as though every branch ran.

### UAF-12: Private Context Compatibility Must Be Structural

Context:

Imported context records such as `PhaseCtx` required structural compatibility
across module boundaries. A local-name or nominal-only check was too brittle;
the implementation needed compatibility based on basename and field shape.

Root cause interpretation:

Private runtime context will cross imported stdlib, generated callables, and
workflow-family modules. Nominal local names are not stable enough across
those boundaries.

Implication:

The private executable context bridge should be specified as structural or
capability-based. That includes `RunCtx`, `PhaseCtx`, `ItemCtx`, `DrainCtx`,
`SelectionCtx`, and `RecoveryCtx`.

Recommended design or gap action:

- Keep the post-foundation context bridge language structural/capability
  based.
- Add negative tests for shape mismatch and positive tests for
  module-qualified equivalent context records.
- Avoid new gap designs that require local short-name recognition for context
  authority.

## Recommended Design Revisions

### WCC Design

Revise `docs/design/workflow_lisp_core_calculus_middle_end.md` or follow-on
gap designs to cover:

- inherited activation guards for defunctionalized control markers;
- terminal provenance / returned-union metadata through calls, let-bound
  values, and branch projections;
- WCC `IfExpr` support as the next compiler-lane gap;
- projection/reference value classes instead of ad hoc opaque path values;
- the migrated-subset boundary for WCC default behavior; and
- explicit route/readiness labels for examples and tests.

### Post-Foundation Target

Revise `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
or its gap index to cover:

- WCC `IfExpr` as the immediate blocker for work-item parent-callability;
- active union variant output resolution as a runtime/signature obligation;
- stdlib provider-effect ownership across generated callable workflows;
- pure projection/output boundary rules;
- typed projection value/reference classes; and
- route/readiness identity as part of migration evidence.

### Runtime / State / Resume Docs

Revise runtime/state or resume-oriented docs to cover:

- normalized resume bundle shape;
- force-restart public/private input filtering;
- reusable-state diagnostic taxonomy;
- guard inheritance in executable control nodes, if owned there rather than
  by the WCC design; and
- structural/capability compatibility for private runtime context records.

### Authoring And Discoverability Docs

Revise `docs/lisp_workflow_drafting_guide.md`, `workflows/README.md`, and
active drain work instructions to cover:

- which `.orc` examples are WCC-default copy-safe;
- which are legacy compatibility fixtures;
- which are stale or historical negative examples;
- whether and how a user can intentionally run a legacy route; and
- the rule that current target examples are selected by evidence labels, not
  by recency or filename.

## Candidate Follow-Up Gap Designs

1. **WCC `IfExpr` Composition Gap**
   - Owner: WCC compiler lane.
   - Acceptance: current Design Delta Drain work-item route compiles through
     WCC and reaches the next non-compiler blocker.

2. **Route/Readiness Labeling And CLI Route Policy**
   - Owner: Workflow Lisp authoring/discoverability.
   - Acceptance: checked-in `.orc` examples and tests declare WCC-default,
     legacy-compat, historical-negative, or stale status; CLI behavior is
     documented.

3. **Executable Guard Inheritance**
   - Owner: WCC/executable IR boundary.
   - Acceptance: inactive match arms containing loops or selectors cannot be
     evaluated.

4. **Pure Projection Boundary**
   - Owner: WCC/post-foundation typed projection.
   - Acceptance: pure input-derived workflow outputs either lower to visible
     projection steps or are explicitly rejected at workflow boundaries.

5. **Reusable-State Diagnostic Taxonomy**
   - Owner: resume/reuse tranche.
   - Acceptance: stale, missing, incompatible, unsafe path, pointer-authority,
     and unsupported-version cases fail closed while preserving actionable
     cause codes.

6. **Runtime Active-Variant Output Resolution**
   - Owner: runtime/signature plus post-foundation variant identity.
   - Acceptance: inactive variant fields are not required or published, active
     variant fields resolve deterministically, and parity compares active
     terminal state.

## Verification Evidence From Reconciliation

The following checks passed after reconciliation fixes:

```bash
pytest tests/test_workflow_lisp_wcc_characterization.py \
  tests/test_workflow_lisp_wcc_m1.py \
  tests/test_workflow_lisp_wcc_m2.py \
  tests/test_workflow_lisp_wcc_m3.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_wcc_m5.py -q
```

Result: `164 passed`.

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
```

Result: `27 passed`.

```bash
pytest tests/test_resume_command.py -q
```

Result: `47 passed`.

```bash
pytest tests/test_workflow_lisp_workflow_refs.py \
  tests/test_output_contract_collections.py -q
```

Result: `19 passed`.

```bash
pytest tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py -q
```

Result: `437 passed`.

The Design Delta Drain dry-run with the post-foundation target also passed
workflow validation. The representative `.orc` dry-runs listed in UAF-01 did
not pass; that failure is part of the findings, not acceptance evidence.

## Non-Findings

The split between the WCC design and the post-foundation target remains sound.
The WCC document owns how lowering works; the post-foundation document owns
what migration surfaces must become parent-callable and promotable. The
unexpected issue was not the document split. It was the lack of a durable
coordination rule before WCC became accepted and implemented.

The WCC route does not by itself complete the post-foundation migration. It
removes the old nested-control implementation blocker for the migrated subset,
but private context, typed projection, certified adapters, resource
transitions, resume/reuse parity, and parent-drain evidence remain active
post-foundation work.

Legacy schema-1 is not wrong merely because WCC is now default. It remains a
compatibility route for historical behavior and dual-route evidence until the
legacy lowerers are retired by evidence-backed gaps.

## Bottom Line

The reconciliation uncovered six concrete architectural follow-ups that were
not fully covered by the existing target/gap designs:

1. route/readiness labeling for examples, tests, and migration evidence;
2. explicit terminal provenance and union pass-through metadata;
3. inherited activation guards for defunctionalized executable control;
4. WCC `IfExpr` as the next compiler-lane blocker;
5. pure projection/output boundary semantics; and
6. resume bundle normalization with reusable-state diagnostic taxonomy.

These should be handled before using the post-foundation drain to claim
parent-callable or promotable `.orc` family parity. They do not invalidate the
current WCC or post-foundation direction; they sharpen the next gap designs
and reduce the risk of the drain implementing more legacy-route work by
accident.
