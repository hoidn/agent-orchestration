# Workflow Lisp Pure-Call Expression Composition

## Metadata

- **Status:** implemented for the resolved-inline subset at target 2.30
- **Kind:** companion architecture decision; implemented contract incorporated
  into [frontend baseline §8.6](workflow_lisp_frontend_specification.md#86-defun)
- **Owner:** Workflow Lisp typechecking, pure-expression lowering, and WCC
- **Created:** 2026-09-08
- **Implementation target:** 2.30, Package C in the owner-requested composition
  implementation plan. Forty-eight focused checks include selected hooks,
  strict rechecking, once-only evaluation and public committed-boundary resume;
  Astra approved the shared-owner correction and old-target compatibility proof.
  This does not select a research allocation or establish superior reuse utility.
- **Roadmap:** [EC-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#ec-1--pure-call-expression-composition-pending-unselected)
- **Companion:** [effect-ledger simplification](workflow_lisp_effect_ledger_simplification.md)
- **Evidence:** [effect-tracking audit](../reports/2026-09-08-workflow-lisp-effect-tracking-audit.md)
- **Drafting record:** [design plan](../plans/2026-09-08-effect-contract-and-composition-design-plan.md)
- **Incremental integration:** [value and continuation composition](workflow_lisp_value_and_continuation_composition.md); its Increment 3 consumes this contract without making rendering, loop, context, or human-input work prerequisites.

## Summary And Current Fallback

An effect-free procedure call should compose as an ordinary expression wherever
its resolved implementation can be represented without changing the enclosing
contract. Distinguish semantic effects, expression representability, and
sequencing requirements. A procedure-call edge alone is not impurity.

The initial target is resolved inline helpers reducible to the supported
pure-expression language, including nested calls and imported specializations.
Record/union fields, list elements, `list/map` bodies, and pure `defun` callers
must not reject such a helper merely because it was declared with `defproc`.
This is not general permission to place effectful work anywhere.

Today, use `defun` where it suffices, or an explicit `let*` binding where
ordinary procedure lowering is supported. Those are current workarounds, not
proof of unrestricted composition. Optional annotations are a separate design;
this proposal can retain current `:effects` clauses throughout.

## Context And Authority

The [frontend baseline](workflow_lisp_frontend_specification.md) owns procedures,
pure expressions, and collection contracts. Relevant component authorities:

- [Effect graph](workflow_lisp_effect_graph.md): inferred effects and visibility.
- [WCC](workflow_lisp_core_calculus_middle_end.md), especially normalization,
  scope/proof analysis, and identity/resume: the maintained lowering foundation.
- [Strict Boolean control flow](workflow_lisp_strict_boolean_control_flow.md):
  target-2.26 conditional normalization, order, and short circuit.
- [Pure list traversal](workflow_lisp_pure_list_traversal.md): pure map evaluation,
  collection eligibility, and pure-payload schema boundaries.
- [Procedure-first reuse](workflow_lisp_procedure_first_reuse_contract.md):
  inline versus private-workflow identity obligations.
- [Pure-result replay](workflow_lisp_pure_result_replay.md),
  [state layout](workflow_lisp_state_layout.md), and
  [source maps](workflow_lisp_source_map.md): generated value ownership and replay.

The audit reproduces a constant-returning inline `defproc` rejected in record,
list, map, and `defun` positions while an equivalent `defun` passes. Binding
the procedure first permits record/list construction; a target-2.26 condition
also passes. This proves an inconsistent composition boundary, not that every
pure procedure already has a valid expression lowering.

Current record/list checks compare the entire `EffectSummary` with empty,
including call edges. `functions.py::_find_purity_violation` rejects procedure
calls structurally. Merely changing those guards does not supply the necessary
resolved-call conversion, evaluation, or identity behavior.

## Decision And Alternatives

Reuse existing resolved-call, pure-expression, and WCC mechanisms. Normalize
eligible calls at the shared semantic boundary; do not add separate record,
list, and provider-context helper APIs or a runtime procedure interpreter.

Alternatives:

- **Keep manual pre-binding:** smallest implementation cost, but it does not
  solve pure-map or pure-function reuse and makes expression composition depend
  on the spelling of the helper.
- **Require duplicate `defun`/`defproc` wrappers:** preserves existing compiler
  paths but splits one behavior between expression reuse and `ProcRef` reuse.
  Keep it as a fallback, not the target architecture.
- **Merge all callable kinds or build general effect polymorphism now:** much
  broader than the demonstrated need. Retain meaningful workflow/identity
  boundaries; reconsider them when an actual consumer requires more.

What this approach makes harder: pure helpers needing runtime control or private
frames are not automatically expression-compatible. The supported subset needs
honest diagnostics and subsequent expansion decisions, not a universal purity
claim.

## Language Contract And Examples

Three questions govern a call independently:

1. What tracked effects does its resolved body and its arguments have?
2. Can its value be represented in the enclosing expression/payload contract?
3. Does preserving evaluation and identity require bindings or execution control?

The initial admission requires resolved, effect-free arguments/body and an inline
lowering that can reduce to supported pure expressions while retaining existing
scope, type, error, and provenance semantics. Empty tracked effects alone do not
prove termination, totality, or absence of a meaningful private boundary.

Target examples below retain today's annotations to isolate the composition
change. They are not current runnable source:

```lisp
(defrecord Result (value Int))

(defproc seven () -> Int
  :effects ()
  :lowering inline
  7)

(defworkflow example () -> Result
  (record Result :value (seven)))

(defproc increment ((x Int)) -> Int
  :effects ()
  :lowering inline
  (+ x 1))

(defun twice ((x Int)) -> Int
  (increment (increment x)))
```

In an enclosing workflow with `values : List[Int]`, the same helper must work:

```lisp
(list/map ((value values)) (increment value))
```

Existing list eligibility still applies: this does not introduce arbitrary
record/union collections, implicit casts, or a runtime `ProcRef` value.
An eligible selected compile-time hook may reduce through the same mechanism;
the binder itself does not become a higher-order runtime map.

Admission is structural after resolution, never based on a helper's name,
module, or presence of `:effects ()`. Under current semantics an empty generic
clause is not proof of purity; always use authoritative resolved inference.

An effectful helper remains rejected in a pure field/map/function position with
its actual effect identified. An effect-free helper whose representation needs
unsupported control or a private frame receives a source-mapped representation
diagnostic, not a false provider/effect diagnosis. Suggested target diagnostic:
`pure_call_representation_unsupported`, with callee, lowering requirement, and
supported alternative. Existing targets retain their diagnostics.

## Normalization And Architecture

The intended flow is existing resolution/specialization → typed expression
normalization → existing pure payload or WCC sequencing → shared validation
and runtime. The precise placement must be demonstrated against current
`defun` checking and WCC phase order before an implementation plan is complete.
Do not infer that a late WCC pass can repair an earlier source rejection.

Responsibilities remain with existing owners:

- Definition/linker/specialization owners resolve the body in its defining
  environment, bind types/hooks, and retain source/contract origin.
- Inference determines actual effects after specialization has settled.
  Intermediate unresolved summaries do not authorize expression admission.
- Pure-expression conversion admits only representable bodies. WCC supplies
  sequencing/control where the enclosing workflow permits it. A pure evaluator
  is not asked to launch a procedure or interpret arbitrary workflow AST.
- Source-map and identity owners preserve the authored call and callee expansion;
  generated bindings are compiler-owned, not new source annotations.

Reuse existing traversal/conversion logic. If a shared resolved-call path is
missing, name it as a feasibility gap; do not implement per-form exceptions or
duplicate a general normalizer behind an apparently small API.

### Selected Phase Placement

For the new EC-1 target, reuse the existing function inliner before procedure
and workflow body typechecking. This exposes procedure calls inside functions
to the existing procedure effect fixed point; it does not require a second
function-effect graph or a new effect atom. Historical targets retain their
existing pipeline. Apply the same ordering in single-module and linked builds:

1. Build catalogs and provisionally type function bodies. Preserve candidate
   procedure-call edges and actual effects; defer only the placement verdict
   that requires final resolution. Keep existing function-cycle detection.
2. Expand function calls at the existing elaborated-body/typecheck seam for
   procedures and workflows, including imported and specialized typed bodies.
   Leave procedure calls visible to inference; do not assume they are pure.
   During inference, defer candidate placement checks in procedure/workflow
   containers as well as function bodies, retaining every call edge and effect.
   Final strict rechecking enforces placement on the normalized result.
3. Run existing procedure/workflow effect inference and specialization to
   completion, then select final procedure lowering modes. Cross-kind recursion
   exposed by function expansion must still fail existing cycle checks.
   Seed existing specialization discovery/materialization from every function
   body, including uncalled functions. Preserve requests across the inference
   entry reset; final rechecking is too late to discover a specialization whose
   effects and lowering have not been resolved.
4. Use one resolved-call normalizer with the visible typed function and resolved
   procedure bodies. Reduce only final-inline, transitively effect-free,
   representable calls, rerun existing strict-Boolean
   `normalize_expanded_conditions`, then strictly recheck before lowering.
   No provisional purity exemption or stale call-edge summary survives admission.

Resolved-call normalization must retain the selected callable's binding context.
An authored hook name is not a global callee name, and a generic template's
empty effect summary does not establish the selected hook's purity. Reuse the
existing exact materialized-specialization selection owner; consume settled
rows rather than discovering new specializations after inference. Normalize a
selected body under its own compile-time hook bindings and defining-module
environment before transplanting it into the caller. Runtime actual arguments
are still evaluated in the caller's environment through ordered hygienic
bindings. Missing or ambiguous concrete selection rejects; a same-named caller
procedure must not capture a callee-local hook.

Keep final strict retyping of every normalized procedure, including generic
bases, and workflows in both compiler paths. The existing retyping owner
preserves signatures, specialization metadata and type environments; skipping
generic bases would hide a normalization defect. Preserve call/definition and
specialization provenance. Astra identified this shared-owner correction after
a selected-hook probe escaped its specialization as an unknown `hook` call.

The final condition normalization keeps inserted bindings inside the selected
`and`/`or` operand by using the existing conditional representation. The pure
evaluator's ordinary operation arguments are eager; an inserted `let` alone does
not establish short-circuiting. Procedure expansion must retain its actual
call/definition provenance in a compiler-owned frame recognized by that pass's
generated-helper predicate; the existing function-only predicate is insufficient.
Do not broaden this into rewriting unrelated authored value-position operators.
Test false-`and` and true-`or` with a failing
skipped call, including inside map bodies.

The linked path must supply actual defining-module bodies and specialized callee
identities, not infer purity or expansion from imported signatures. Replace the
late-only function expansion sites; do not maintain divergent inliners for each
consumer. An uncalled function is still validated, not exempt from its contract.

### Ordered Pure-Payload Binding

The current pure-projection lowering substitutes `LetStarExpr` bindings: unused
arguments can disappear and repeated uses can duplicate evaluation. EC-1 therefore
requires an ordered lexical `let` node in version 3 of the existing pure-expression
payload, rather than relying on substitution or hoisting work outside a map/branch.
Its shape is `kind: let`, ordered `bindings` entries containing `name`, normalized
`type`, and expression `value`, followed by a `body`. Validate, typecheck, and
evaluate each binding in order in the preceding lexical environment; evaluate
the body with all resulting bindings. Reuse the evaluator's existing lexical
environment used by `list_map`. This adds no procedure interpreter or result store.
Match existing authored `let*` scope semantics: initializers see preceding
bindings, inner scopes may shadow outer names, duplicate names in one binding
list reject, and local bindings do not escape the body. The separate list-map
binder collision restriction does not require banning normal lexical shadowing
in `let`. Hygienic argument temporaries are still required before introducing
formal names, so a later actual argument cannot accidentally refer to an earlier
formal instead of its caller binding.

Preserve these bindings at the existing WCC binding/projection owner, not only
when the remaining workflow is a pure terminal suffix. An expanded `defun` or
procedure before a provider, private call, or control continuation still evaluates
every actual argument once. Keep nested lexical scopes (including legal shadowing)
and binding types; flattening their names into one payload binding list is invalid.
Carry binding/call origins through the existing source-map owner, rather than
assigning a reconstructed chain only its terminal reference's origin. Astra review
rejected the terminal-suffix-only reconstruction on these concrete grounds.
Use executable evaluation counts, an unused fallible argument before an effect,
shadowing, and multiple call origins to prove the shared correction.

Call normalization must first evaluate arguments in the caller's environment,
using hygienic temporary bindings before introducing formal parameter names.
For example, `f(x, y) = y` called as `f(2, x)` with caller `x = 9` returns 9,
not 2. Body cloning retains lexical shadowing and call/definition provenance.

Preparation fixtures under
`tests/fixtures/workflow_lisp/pure_call_composition_preparation/` demonstrated
two existing function-expansion defects, not merely risks of the new
procedure-call surface: caller-name capture changed returned values, and an
unused fallible argument disappears. Caller-name capture is corrected at every
target, including the `defun` expansion below 2.30, which now evaluates its
arguments in the caller's scope (`specs/versioning.md`, exceptions to target
stability). The unused fallible argument still disappears. An equivalent
`defun` is therefore not automatically a valid semantic control. Verify
explicit-binding controls independently and repair the shared
normalization/payload owners under the selected target.

Only payloads needing the new node use schema 3, under the selected EC-1 target.
Existing schema-1/2 payloads and old-target lowering remain unchanged; validators
reject a `let` in those older payload schemas. The payload and its lexical
structure participate in the existing deterministic identity/resume contract.

### Evaluation And Proof Invariants

- Evaluate arguments in source order, once per call occurrence. Reusing a formal
  parameter must not duplicate evaluation of its argument; unused parameters
  must not silently suppress observable argument failures.
- Keep calls inside the selected conditional branch or short-circuit operand.
  Do not evaluate untaken work by hoisting it outside its control scope.
- Evaluate a map's source once and its body once per element in input order.
  Keep binder-dependent calls inside the element scope; preserve empty-map and
  failing-element behavior.
- Preserve lexical capture, defining-module lookup, exact result types,
  transport contracts, and branch-local variant proof. A helper returning
  `Bool` does not acquire arbitrary proof-producing authority.
- Preserve the existing compile-time-folding versus runtime-error contract.
  Do not claim semantic equivalence merely because successful scalar results
  match; overflow, path rejection, and skipped-work cases are evidence too.

The first proof may handle the constant helper, but closure of the advertised
subset requires dynamic arguments, nested/imported helpers, and maps. Textual
substitution is insufficient if it changes evaluation or proof semantics.

### Identity, State, And Replay

An inline helper's work remains owned by the enclosing workflow and its
source/call expansion. If a projection is generated, use the existing private
value, payload validation, and replay owners. Do not add a new durable helper
result store.

An explicitly private-workflow procedure keeps its private state/checkpoint
boundary even when its body has no tracked operation atoms. Initial expression
support may refuse it; it must not silently inline it. An `auto` helper is
eligible only when its selected lowering meets the same inline representation
contract, not merely because its effects are empty.

WCC identity includes lexical ownership, node kind, and role. Adding normalized
bindings/scopes can change identity even if values match. Preserve existing
program identity for unaffected same-target programs. Newly admitted syntax
requires deterministic identities and clean run/resume proof; converting
authored workarounds or changing lowering does not promise reuse of old
checkpoints. Preserve historical frames and reject incompatible reuse under
the existing version/identity contract.

The ordered binding extension above changes the existing pure-expression
payload, not the runtime workflow node or durable-state families. Its evaluator,
payload validation, lowering, and version contracts must land together before
expression support is advertised.

## Dependencies, Scope, And Reconsideration

This work is independent of optional `:effects` and a compact effect
representation. Target 2.30 follows the independently selected union-input 2.28
and rich-loop 2.29 increments. The reviewed phase order and schema-3 contract are
implemented for the bounded subset; practical benefit remains unestablished. Historical
targets keep their existing pipeline, diagnostics and schema-1/2 bytes, including
characterized function-expansion limitations rather than rewriting checkpoints,
except for the capture corrections that apply to every target; programs without
a shadowed name keep their bytes.

The first supported subset excludes effectful expression composition, public
workflow calls, private execution frames inside pure payloads, runtime-selected
callables, arbitrary workflow loops in pure functions, and unbounded recursion.
These exclusions bound the first proof; they are not permanent design axioms.

When a useful pure helper still fails, identify whether the cause is actual
effects, type/transport, expression representation, or identity/control needs.
Then consider broader shared normalization, pure-evaluator capability, callable
roles, or a language/type-system redesign in proportion to the benefit. Do not
automatically give up, force wrappers, or add a one-consumer escape hatch.
Unbounded recursion would require revisiting analysis/lowering and termination
semantics, not simply deleting cycle checks.

[Provider-context values](workflow_lisp_provider_context_values.md) are a relevant
consumer, not proof of feasibility: transforming materialized immutable context
can be pure; loading stored history and provider-assisted summaries are not.
This design does not solve context transport, native capture, or record-valued
collections. A PC-1 spike should identify its actual prerequisite instead of
requiring all effect work or pretending a global artifact is first-class data.

## Verification And Acceptance Scenarios

Use the public compile/validation path and an actual executable workflow for
integration. No fixture-only lowering path or literal prompt assertions.

1. **Basic composition:** a constant inline procedure in a record/union field
   and list element compiles and returns the declared value. Compare with the
   existing `defun` and explicit-binding forms; claim value equivalence, not
   identical historical state identity.
2. **Nonconstant reuse:** an imported helper with dynamic arguments is reused
   directly, nested, through an eligible resolved hook, and from a `defun`.
   Correct types/values and defining-module lookup survive specialization.
3. **Traversal/control:** empty and nonempty maps, nested conditionals, and
   short-circuit operands preserve ordering, element scope, and skipped-work
   behavior. Include an error-producing argument/body to detect duplicated,
   suppressed, or eager evaluation under the existing folding contract.
4. **Honest refusals:** effectful selected hooks fail pure-context checks;
   effect-free but unrepresentable/private-boundary calls fail representation
   checks. Invalid type, proof, collection, and old-target uses still reject.
5. **Run/resume and provenance:** use runtime input so the example cannot
   entirely constant-fold. Execute a workflow with an eligible helper around an
   existing committed operation boundary, interrupt downstream, and resume.
   Verify values, payload/call-source attribution, and no repeated completed
   provider operation. A deterministic fixture provider proves mechanics,
   not provider quality; standalone pure compile/run remains required.
6. **Regression:** unchanged same-target workflows retain route, output,
   source/call identity, and checkpoint behavior. The accepted target-2.26
   conditional and target-2.18 list contracts remain intact.

Narrow type/procedure/expression/list/function tests precede WCC, build-artifact,
and checkpoint controls. Collect added/renamed modules, then use the repository's
parallel pytest convention for broad suites and a public-entry smoke check.
Do not rewrite old rejection tests as if the feature had always existed.

## Utility, Consequent Actions, And Deletion

Measure the same five axes independently: construction/composition failures,
duplicate helpers and coupled reuse edits, diagnosis from inferred effects and
source provenance, agent revision/repair effort, and useful search candidates
plus whole-task quality/cost. Compiler acceptance alone proves none of the last
four advantages.

A successful minimum should lead to a documented supported subset and tests of
representative repeated use. Improve common unresolved cases through shared
mechanisms where justified. If the type system or callable split is the recurring
obstacle, consider revising it instead of treating failure as task infeasibility.
If normalization or expansion costs outweigh the benefit, narrow or retire the
proposal and remove its speculative scaffolding; retain independently useful
inference/annotation improvements. Compare with a `defun`, explicit binding,
or ordinary Python/skill control appropriate to the same task.

Delete the displaced edge-only guards and duplicated call-conversion paths
only for the newly supported regime; retain real effect checks and old-target
compatibility. Remove temporary comparison machinery after its decision.
Do not require callers to maintain both a pure and procedure copy merely to
exercise the claimed improvement.

## Documentation And Implementation Handoff

Before implementation, resolve phase ordering, once-only pure expression
representation, source/call identity, and the version boundary with executable
evidence or an explicitly selected feasibility spike. These are prerequisites,
not details an implementer should silently choose.

On acceptance, amend frontend pure/procedure rules, effect-graph pure contexts,
WCC/pure-payload contracts where needed, list/function guidance, and the
procedure-first identity clarification. Keep current snippets current until the
new route is implemented. The draft adds no runtime evaluator, provider executor,
roadmap allocation, or mandatory dependency on all of EL-1.
