# Workflow Lisp Effect Ledger Simplification

## Metadata

- **Status:** accepted target-2.39 contract; implementation and consumer evidence are tracked by the linked plan and capability matrix
- **Kind:** language contract and subtractive architecture decision
- **Owner:** Workflow Lisp frontend
- **Created:** 2026-08-15
- **Last material update:** 2026-10-15
- **Implementation target:** 2.39; selection and bounded steps belong to
  [roadmap EL-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#el-1--effect-contracts-and-analysis-cleanup-selected-239)
- **Evidence:** [effect-tracking audit](../reports/2026-09-08-workflow-lisp-effect-tracking-audit.md)
- **Drafting record:** [design plan](../plans/2026-09-08-effect-contract-and-composition-design-plan.md)

## Summary

Infer procedure effects by default. An authored `:effects` clause is an
optional, identity-aware upper bound, not a mandatory exact restatement.
Explicit empty means no tracked effects, including after specialization.
Preserve inferred inspection and runtime evidence.

Three decisions are deliberately independent:

1. This design owns authored contracts, inference visibility, and migration.
2. [Pure-call composition](workflow_lisp_pure_call_composition.md) owns admitting
   effect-free procedures in expression positions through proven normalization.
3. This design defines the requirements for optional internal metadata cleanup,
   but mandates neither a new analysis record nor a fixed compact footprint.

Annotation relief does not depend on a wholesale representation rewrite.
Internal cleanup does not claim to repair expression composition. Execution
safety is not the rationale; tool use remains provider/agent-owned.

## Context And Authority

Current authoring follows the [drafting guide](../lisp_workflow_drafting_guide.md),
[frontend baseline](workflow_lisp_frontend_specification.md), and
[effect graph](workflow_lisp_effect_graph.md). The latter's general coverage
wording does not supersede the mandatory/exact ordinary-procedure rule at
admitted definition origins 2.35–2.38 or its specialization exceptions. Target 2.39 changes that contract;
it does not claim merely to fix an implementation exceeding the baseline.

Other authorities:

- [Language principles](workflow_language_design_principles.md): effects visible
  to validation/IR, procedural composition, and deterministic work ownership.
- [WCC](workflow_lisp_core_calculus_middle_end.md): resolved calls, normalization,
  scope/proof analysis, and checked closed-program construction.
- [Semantic IR](workflow_lisp_semantic_workflow_ir.md) and
  [lexical checkpoints](workflow_lisp_lexical_execution_checkpoints.md):
  operation explanations and execution evidence, respectively.
- [Versioning](../../specs/versioning.md): explicit validation/version boundaries.
- [Roadmap](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md):
  selection and allocation, not language semantics.

The audit establishes annotation ripple, edge-only positional rejection, and
specialization exemptions. Its 42 declarations include migration/legacy source;
14 empty clauses do not establish 14 pure procedures. It measures neither
author-time savings nor compiler performance. Exact annotations can express
intentional dependency restrictions; their value is not zero.

## Decision And Alternatives

Choose inference-default optional restrictions using the existing named atom
vocabulary first. Retain the existing inference machinery until a particular
consumer-backed simplification is justified.

- **Keep mandatory exactness:** preserves an exhaustive change alarm but couples
  wrappers to deterministically derivable implementation details.
- **Remove declarations entirely:** simpler syntax, but loses useful intentional
  library constraints. Optional restrictions preserve that choice.
- **Kind-only ceilings plus an immediate representation rewrite:** removes
  precision and increases migration scope unnecessarily. A provider name must
  not become unchecked decoration. Coarse contracts, if later useful, need
  unmistakably coarse syntax and a demonstrated consumer.

No new effect keyword, handler language, runtime permission model, general
effect-row system, or mandatory annotation style for exported libraries follows.

## Authored Contract

For a fully resolved procedure specialization, let `I` be its inferred
transitive effect atoms and `D` its optional declared atoms.

| Source | Target meaning |
| --- | --- |
| Clause absent | Infer `I`; no additional authored restriction. |
| `:effects ()` | Require `I = ∅`. |
| `:effects (...)` | Require `I ⊆ D`, preserving atom kind and subject identity. |

Procedure-call edges are not members of `I`. Calling a procedure contributes
its inferred effects, not impurity merely because it is a call. This does not
automatically make the expression representable by the pure evaluator.
Workflow calls remain tracked dependencies even when their returned value is
constant; this proposal does not erase workflow/checkpoint boundaries.

Examples below require target 2.39 and its implemented route:

```lisp
(defproc seven () -> Int
  7)

(defproc checked-seven () -> Int
  :effects ()
  (seven))
```

An intentionally restricted boundary may retain:

```lisp
:effects ((uses-provider providers.review))
```

Invoking only that provider fits the restriction; invoking another does not.
Using fewer declared effects is permitted. Membership describes possible work,
not proof of execution, order, count, termination, or task quality. Required
execution belongs in behavioral checks. An exact dependency-removal alarm may
be supplied by reviewing inferred differences; no second authored exact mode
is introduced without a real consumer.

### Subjects And Coverage

Retain distinctions among reads, writes, publication, provider/command/workflow
use, state updates, child runs, and trials. Do not collapse reads into purity
or all stateful operations into an unchecked write category.

Symbol-bearing subjects resolve in the definition's environment using existing
module/linker identity rules, including aliases and specialization bindings.
Preserve previously valid canonical spellings. An unused permitted symbol
still must resolve to an appropriate declaration; an unresolved name is an
error, not a wildcard. Canonical identities in the linked transitive dependency
closure do not require a wrapper to duplicate the callee's imports merely to
name a restriction. Ordinary caller shadowing must not change an imported
restriction.

Path, artifact, state, and adapter-label subjects retain their existing domain
semantics. They are not all provider capabilities or globally resolvable
symbols, and this design adds neither resource alias analysis nor claims about
all tools an opaque provider might execute. Distinct atom kinds remain distinct.

Resolution uses the existing catalogs and specialization bindings; it does not
change `EffectAtom` or create an external-capability registry:

- `calls-workflow` resolves the defining module's aliases to the existing
  canonical workflow identity. Canonical subjects already in the linked
  transitive closure remain usable. A formal WorkflowRef subject substitutes
  its selected `workflow_ref_bindings` before comparison; unresolved formals
  remain incomplete.
- `uses-provider` names the existing provider extern key in the source graph's
  compiler-owned extern environment, not a provider-id string or configuration
  digest. An unused named permission must still resolve to a provider binding.
- `uses-command` preserves the current operation/adapter **step label** domain;
  an adapter's label is not its boundary binding name. Path, artifact, state,
  child-run and other domain labels likewise keep their existing equality
  semantics, rather than acquiring invented declaration lookups.
- Separately compiled workflow capsules keep their existing callable alias and
  producer configuration ownership. Their private provider/command names do
  not become caller-environment permissions. Ordinary source imports and
  opaque workflow imports retain their current effect-summary boundary;
  this contract introduces neither cross-capsule inference nor a second effect
  graph.

Unused workflow/provider symbols must resolve even when the procedure body is
pure. Wrong-kind and unknown names are declaration errors. Domain labels are
not symbols and are not rejected merely for lacking an extern declaration.

Some compiler-inferred atoms have no authored grammar. Initially preserve
their inference and equality identities: an explicit restriction that cannot
cover such an atom must diagnose that fact, while an unconstrained procedure
may use the operation if otherwise valid. Never silently discard an atom to
make a ceiling pass. Extending coverage through a documented operation-to-atom
projection requires its own examples and review; omission is not evidence
that every desired restriction is already expressible.

### Specialization, Imports, And Generated Procedures

The restriction is attached to its authored definition, not to whichever name
the compiler generates for it. Carry clause presence, source location, and
defining contract/version origin through parsing, linking, signature copying,
and specialization. Use a compiler-only origin target on `ProcedureDef` and optional declared
atoms on the existing definition/signature; qualification and specialization
copy those facts. Do not persist the origin in executable identity/JSON or
invent a parallel registry. A definition produced by a macro uses the target
of the receiving expanded module; importing an already defined procedure
preserves that procedure's origin, including when specialized in a newer module.

```lisp
(defproc forward ((runner ProcRef[() -> Result])) -> Result
  (runner))
```

This target helper infers the selected hook's effects. Adding `:effects ()`
asserts that every materialized use is effect-free; an effectful selected hook
must fail at its use with the definition's restriction and responsible call
path identified. Generic summaries with unresolved hooks are incomplete,
not proof of purity. An uninstantiated generic can be checked only to the
extent its bindings are known; report that boundary honestly.

Resolve each call in its owner's lexical WorkflowRef environment and use the
existing materialized callee row when bindings are concrete, before joining
effects. Never substitute caller bindings into inherited callee atoms; a
visible workflow with the same spelling does not resolve a lexical formal.
An unresolved dependency and any known workflow boundary remain represented
through their existing owning call/edge. An empty restriction, or one allowing
no workflow calls, cannot accept that known boundary; a named restriction
defers only the unresolved identity comparison until materialization. Other
known effects remain checked. Reconstruct own call facts consistently for
procedures and workflows through the existing discovery traversal, preserving
workflow-summary closure without a second graph or persisted call metadata.

Validate authored restrictions after the existing inference fixed point has
settled, not during intermediate passes that intentionally suppress declared
validation. This ordering applies to every resolved specialization inheriting
the restriction, including nested generated and imported definitions. The
final check includes helpers or specializations materialized by the final
workflow re-typecheck, not only those present at the first validation call.

Generated `let-proc` helpers currently receive synthetic empty declarations.
Under target 2.39, every temporary and final generated helper without an
authored restriction uses omission and caller-owned inline semantics; it must
not synthesize `:effects ()` or `:lowering` source clauses. A specialization of an explicitly restricted definition retains
and checks that restriction. Neither blanket generated-name exemptions nor
synthetic purity promises are permitted.

The definition's contract regime governs imports. A new-target caller must not
reinterpret an old library's empty clause, and old targets must not admit new
syntax accidentally. Existing module-version compatibility checks still apply;
a target-2.39 module may import 2.35–2.38 definitions with their original exactness,
exemptions and lowering policy. A module below 2.39 must refuse a dependency
defined at 2.39, including the otherwise compatible 2.37/2.38 route. This
check precedes existing evaluated-import shortcuts. The separate source-floor migration retargets the six maintained stdlib modules
to 2.35, preserving their old-contract behavior. They are not retargeted to 2.39
or stripped of intentional clauses merely because a new caller imports them.
Pre-2.35 definitions are rejected, not preserved through an origin exemption.

## Frontend And Inspection Contract

Ordinary syntax errors and unknown kinds remain errors. Target-2.39
diagnostics distinguish malformed/unresolved declarations from
`procedure_effect_ceiling_exceeded`. A ceiling violation reports the authored
restriction, uncovered kind/subject, resolved specialization, and a relevant
source-mapped call path. Existing-target diagnostic codes remain unchanged.

The parser must distinguish omitted from explicit empty; an empty set alone
cannot represent both. Absence is not an inference-disable switch. Inference
must still cross wrappers, macros, selected hooks, and imports.

Existing compiler/editor projections should expose:

- authored restriction, or its absence;
- inferred possible effects at a resolved call;
- contributing calls and unresolved generic dependencies;
- actual execution evidence only when inspecting a particular run.

LSP procedure-completion detail projects compiler-derived restriction and
inference facts; `signature.declared_effects` alone cannot represent optional
clauses or specialization. Use compiler facts, not hover text or reports as semantic authority.
Definition inspection may show unresolved requirements; call-site inspection
must show the resolved result or a clear unavailable/incomplete state.
Use existing REPL `:info` for definition restriction/inferred status and
`:type` for a resolved expression's inferred summary; retain no-effect execution
rules. LSP procedure-completion detail projects the same compiler facts for
the declaration and marks unresolved generic dependencies incomplete. No new
hover request, span-to-type service, dashboard or runtime inspection API is
selected. Early pure-function/child-run/trial consumers must consult inferred
or unresolved facts; an absent clause is never evidence of purity.

## Internal Architecture And Subtraction

Keep the existing path: frontend resolution/typechecking → executable WCC →
checked closed program → evaluated runtime. The following are separate facts, not a
requirement for separate modules or persisted records:

| Fact | Owner and consumers |
| --- | --- |
| Possible effects and authored restrictions | Frontend inference and definition contracts; validation, diagnostics, inspection. |
| Located calls and specialization | Existing callable/catalog/WCC ownership; callee resolution, closure, cycles, source maps. |
| Expression representability and sequencing | Type/lowering/WCC owners; pure-expression conversion and normalization. |
| Concrete operation identity and actual evidence | Lowered operation contracts, Semantic IR projections, runtime state/checkpoints. |

`EffectSummary` may remain for the first contract change. A later cleanup may
relocate located calls and shrink node-local summaries only where consumers
need less. Identity-aware restrictions require subject facts somewhere before
validation; a single effect bit cannot replace them.

Consumer review must include positional checks, child-run/trial placement,
workflow-only boundary classification, resolved call selection, cycle
diagnostics, and path-admission serialization—not just summary constructors.
The audit identifies owners in `typecheck_*.py`, `functions.py`,
`phase_family_boundary.py`, `wcc/elaborate.py`, and
`workflow/run_ref/path_compile.py`. Strict-Boolean normalization in
`conditionals.py` currently decides from expression classes, not by consulting
an effect-summary predicate; do not mechanically rewrite the wrong dependency.

No reachable producer of inferred `ReadEffect` was found in the audit, but
synthetic read summaries affect current checks. Removal therefore needs a
reachable-language argument and consumer tests, not a claim of equivalence on
every possible summary. A future stored-context load is not pure.

Delete displaced propagation, redundant decision paths, and any temporary
comparison harness with the completed cleanup. Do not keep two analysis
authorities, add a predicate per caller without common semantics, or create a
permanent compatibility service. Profile before promising memory or speed gains;
retaining the simpler existing representation is an acceptable outcome.

## Persistence And Compatibility

Target 2.39 is the version boundary. Admitted targets 2.35–2.38 retain mandatory
exact ordinary-procedure checks and their existing specialization behavior.
Current authoring examples and their copy limits belong to the
[drafting guide](../lisp_workflow_drafting_guide.md#procedure-contracts-at-target-239)
and [library reference](../lisp_library_reference.md#target-239-local-hooks).

Migration reviews actual definitions, including stdlib/imported hooks:

- Omitted clauses become the normal unconstrained form on the new target.
- Retain explicit empty only when purity is intended and verified after binding.
- Replace old forwarding/synthetic empties with omission, not exemptions.
- Retain named ceilings where the constraint is intentional; do not automatically
  strip them from every library or infer intent from clause size.
- Reject unknown or unrepresentable restrictions honestly.

Semantic IR remains derived from concrete lowered operations. Checkpoint
policies, completed-result reuse, resource transitions, and artifact lineage
do not derive from the authored ledger and remain unchanged.

The annotation change needs no new persisted effect-facts format. Current
path admission serializes direct/transitive atoms and call edges, so an internal
representation change must preserve that projection or explicitly version its
owning admission contract and readers. Full frontend construction precedes that
serialization; Semantic IR is available there if a proven projection uses it.
Do not preselect a new `v2` schema merely to rename an internal record.

Preserve historical admitted facts, hashes, and frozen evidence without
backfill. Source edits, a new target, or changed lowering may change program
identity; no cross-version checkpoint reuse or identical fingerprint is
promised. Same-input, same-target internal cleanup must demonstrate unchanged
durable identity unless a separately reviewed version change is necessary.

## Verification And Feasibility

Separate evidence lanes; no requirement can simultaneously preserve every old
rejection and accept the deliberately new source forms.

| Lane | Required evidence |
| --- | --- |
| Authored contracts | Omission accepted only in the new regime; subset/empty/named restrictions checked; malformed and uncovered effects rejected. |
| Resolution and specialization | Imported aliases, unused allowed subjects, shadowing, pure/effectful selected hooks, generated helpers, and old/new definition origins behave as specified. |
| Inspection | Restrictions and inferred possible effects remain distinct; resolved calls expose selected hooks; unknown generic effects are not displayed as empty. |
| Representation-only cleanup | Same-target decisions, diagnostics, call/source identities, classification, admission facts, and executable behavior unchanged over actual consumers. |
| Runtime integration | Public-entry compile/run/resume of representative wrappers retains values, validated completed-result reuse, and operation lineage. |

Use the audit's add/remove dependency and pure/effectful forwarding examples as
small starting fixtures, then imported stdlib/library consumers. Existing-target
regressions retain their contract; add target-specific cases instead of rewriting
old expected failures into purported historical successes. Compare internal
representations temporarily only if both actually exist.

Run narrow owning tests first, collect changed test modules, then relevant
broader suites with the repository's prescribed parallel pytest invocation.
Implementation needs a public-entry usage/integration check and proportionate
checkpoint/path-admission controls, not inspection alone. Design-only drafting
does not establish those capabilities.

The selected plan identifies the existing owner catalogs, definition copying,
final inference pass and inspection projections used by this contract. Their
new-target integration still requires the finite resolution/origin/inspection
fixtures above before completion. Internal representation and persisted-format
cleanup are not part of the selected implementation.

## Five-Axis Utility And Consequent Decisions

| Axis | Measure | Improvement or simplification consequence |
| --- | --- | --- |
| Programmability/composition | Source edits and failed compile rounds when wrapping, substituting hooks, or composing helpers. | Repair normalization separately; reconsider callable/type boundaries if useful cases remain obstructed. |
| Reuse | Coupled edits across imported definitions and callers. | Improve inferred propagation/resolution; retain intentional constraints, not compulsory mirrors. |
| Introspection | Ability to identify which selected dependency introduced an operation and distinguish possible from executed work. | Improve existing projections; remove redundant displays or metadata that do not help diagnosis. |
| Self-programmability | Agent effort to author and revise behavior under intended constraints. | Eliminate deterministic annotation repair; retain checks that express the task's actual requirements. |
| Search/optimization | Invalid-candidate repair effort and whole-task outcome/cost under equivalent constraints. | Search behavior rather than derived ledgers; retain only useful restrictions/features and compare simpler skill/Python controls. |

No new benchmark platform is needed initially. A minimum fixture establishes a
capability, not superiority. Expand supported composition and improve weak
ergonomics where justified; abandon the proposed cleanup or simplify restrictions
when measured benefit does not justify their cost. Negative evidence on one
axis does not cancel unrelated useful inference.

Cycle rejection is a current finite-specialization/lowering boundary, not proof
that effects require an acyclic language. If real adaptive programs require
runtime-selected callables or unbounded recursion, revisit language assumptions,
analysis and lowering. Recursive inference may require a fixed point; termination
is a separate property. Do not add that machinery without a consumer or dismiss
a useful consumer solely because the present type system cannot express it.

## Documentation And Implementation Handoff

The effect-graph and frontend contracts carry the target-2.39 version
semantics; WCC continues consuming inferred rows rather than authored ceilings.
Inference-default restrictions, origin-aware specialization/import checks and
inspection use the existing summary. The frontend selects caller-owned inline
composition and enforces finite private-form admission; these source contracts
do not change runtime effect identity, memo reuse or transport policy.

The [drafting guide](../lisp_workflow_drafting_guide.md#procedure-contracts-at-target-239)
explains omission, checked empty/named restrictions and explicit workflow
boundaries. Its maintained proposal and compact-search examples are the two
selected consumer migrations; the [capability matrix](../capability_status_matrix.md)
and [implementation plan](../plans/2026-10-15-orc-simplification-roadmap-extension.md#target-239-selected-implementation)
own supported scope, acceptance evidence and remaining gates. The
[pure-call design](workflow_lisp_pure_call_composition.md) is independently
reviewable and can retain current annotations. Consumer-led representation
cleanup follows demonstrated need, not a compulsory phase before either benefit.
If a selected consumer exposes a shared prerequisite, record the narrow
dependency instead of making all EL-1 work a gate.

Roadmap EL-1 owns scheduling and existing entry conditions. This revision
supersedes the earlier proposal's unchecked subjects, blanket compatibility,
fixed footprint/call-bit architecture, mandatory path-facts v2, and global
decision-equivalence gate. The selected implementation is recorded in the roadmap and simplification
plan; it does not amend frozen research packages.
