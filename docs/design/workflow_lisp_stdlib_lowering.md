# Workflow Lisp Frontend Standard Library Lowering

Status: current stdlib composition/invariant contract with historical flat projections
Depends on: `docs/design/workflow_lisp_core_stmt_taxonomy.md`,
`docs/design/workflow_lisp_semantic_workflow_ir.md`,
`docs/design/workflow_command_adapter_contract.md`

## Purpose

High-level Lisp library forms use ordinary typed `.orc` composition, shared
elaboration and checked-program construction. They must not hide unresolved
semantics. Core/Semantic/Executable IR projection shapes are historical;
[evaluated execution](workflow_lisp_evaluated_execution.md) owns current admission.

The default implementation path is ordinary `.orc` stdlib code compiled through
the shared typed and evaluated composition model. A form should receive bespoke
compiler lowering only when it is explicitly accepted as a primitive rather
than as a library abstraction. Schema-1 and direct per-form flat lowerers are
retired; historical compatibility descriptions do not retain those routes.

Each standard-library form needs an exact typed/effect/identity contract and
public execution evidence before claiming an admitted evaluated route.

For the key-workflow migration tranche, `review-revise-loop` is not accepted as
a compiler-special primitive. Its implemented route is ordinary imported stdlib
composition over typed loops, structured provider results and `match`, with
source provenance and memo-safe effect identity. The historical flat projection
used `repeat_until` and generated materialization steps. If later work proves that a review-loop-specific
compiler branch is necessary for another workflow family, the migration
architecture must be revised before primary promotion.

For review/fix loops, consumed evidence artifacts such as `checks_report` are
loop inputs/consumes, not review-provider output fields. Generated review
provider contracts should omit evidence identity fields unless the provider
actually produces that artifact. Route and final projection steps carry evidence
refs from loop inputs/state, and negative validation should catch a lowering
where provider output can replace consumed evidence identity.

`review-revise-loop` compiles through the ordinary imported stdlib route in
`orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`. That route uses
compile-time `ProcRef` review/fix hooks, generic `loop/recur` exhaustion
projection, and explicit `command-result` validation through the certified
`validate_review_findings_v1` adapter boundary. Promotion is still gated by
workflow-family parity evidence rather than by a separate review-loop-specific
compiler branch.

Current stdlib status: `phase-scope`, `finalize-selected-item`, and
`backlog-drain` lower through ordinary imported stdlib composition on the
typed route. `std/resource` and `std/drain` are builtin modules. Their old
per-form flat lowerers are retired; retained modules do not retain that backend.
Builtin module/type availability does not admit every reachable effect.
`resource-transition`, generated materialized views and old reusable-state
execution remain excluded unless their evaluated owner explicitly admits them.
Historical dedicated flat runtime-proof lanes do not establish current admission;
frontend-only proof is non-executable.

Historical note: earlier bridge-era feasibility work used
`ReviewReviseLoopExpr` as a shape reference while proving the route. That
historical expression is not current-checkout acceptance evidence or a live
owner seam for ordinary stdlib composition.

## Form Status

| Form | Authoring status | Primary-migration status | Lowering status |
| --- | --- | --- | --- |
| `provider-result` | implemented authoring surface | pending parity evidence per workflow family | structured provider bundle contract |
| `command-result` | implemented authoring surface | pending union/proof and bundle-path parity | `output_bundle` for fixed records; union results require a variant-proof surface or validator/projection |
| `review-revise-loop` | implemented authoring surface for current fixtures/examples | pending parity evidence per workflow family | ordinary imported stdlib composition over compile-time `ProcRef` review/fix hooks, generic `loop/recur`, and the explicit `validate_review_findings_v1` command boundary; no review-loop-specific compiler branch |
| `resume-or-start` | library/adapter-backed or pending by usage | pending | requires canonical reusable-state validation |
| `resource-transition` | versioned typed/library surface | no current evaluated effect admission | historical native/adapter backends; a separate accepted port is required |

## Required Forms

Initial forms:

- `provider-result`
- `command-result`
- `produce-one-of`
- `run-provider-phase`
- `review-revise-loop`
- `resume-or-start`
- `resource-transition`
- `finalize-selected-item`
- `backlog-drain`

## Lowering Contract Template

Each form must specify:

- inputs and return type
- effects
- checked-program representation and effect-site identity
- retained catalog/proof facts; historical Core/Semantic projections where read
- state layout use
- reference catalog entries
- proof graph entries
- source-map behavior
- runtime backend requirements
- negative validation cases

<a id="example-produce-one-of"></a>

Historical flat snapshot/selection projection. Current library import/type support does not admit excluded evaluated effects. See the [preserved record](../reports/documentation-history/workflow_lisp_stdlib_lowering-history.md#example-produce-one-of).

## Example: `backlog-drain`

Expected lowering:

```text
bounded loop
call selector
match selection result
call selected-item runner or gap drafter
normalize terminal DrainResult
```

Semantic requirements:

- workflow refs are signature-checked
- selected item results are typed unions
- gap handling cannot hide an empty active queue as success unless the
  `DrainResult` variant says so
- loop state is explicit and bounded
- runtime-native terminal state and summary effects remain visible on the
  imported stdlib route
- the dedicated executable-boundary proof lane stays distinct from
  frontend-only compile proof

## Adapter Backends

Some standard-library forms may initially lower to certified command adapters
when the runtime does not yet expose a native effect.

Allowed examples:

- `resource-transition` lowering to a queue-move adapter with typed outputs;
- `command-result` invoking a deterministic validator;
- temporary `resume-or-start` validation behind an adapter while canonical
  reusable-state validation is being specified.

Adapter-backed lowering must still expose:

- typed inputs and outputs;
- declared effects;
- source-map links from the high-level form to the adapter invocation;
- fixture and negative-test obligations;
- validate-before-publication behavior for structured outputs.

Inline command text is not an acceptable lowering target for standard-library
forms.

## Runtime-Native Promotion

Do not promote every adapter into a runtime primitive. Promote only when the
form needs runtime-level properties that an adapter cannot provide well:

- atomic multi-file/resource transition semantics;
- resumability tied to runtime state checkpoints;
- source-map and observability fidelity beyond command logs;
- path-safety guarantees that must be enforced before command launch;
- proof, effect, or reference information needed by Semantic IR.

`resume-or-start` also requires a canonical reusable-state validation contract:
the prior-state schema, reusable terminal variants, artifact-existence checks,
failure modes, and normalization between resumed and fresh branches must be
specified before the form can claim runtime-integrated semantics.

## Required Invariants

- A stdlib form must reduce a recurring correctness burden, not only reduce
  punctuation.
- Every generated effect is visible in the effect graph.
- Every generated statement is source-mapped.
- Command-backed forms use certified command adapters, not hidden inline glue.
- Provider decisions become structured state, with reports as views.
- If no faithful lowering exists, the form is not implementation-ready.

## Remaining Open Questions

- The exact authoring syntax for additional generic `loop/recur` exhaustion
  projection conveniences.
- Whether `resume-or-start` needs a new canonical-state validation primitive.

The historical transition ownership rule remains a constraint on any later port:
durable mutation needs explicit runtime authority and typed adapter contracts.
It supplies no current evaluated transition admission.
