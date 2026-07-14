# Workflow Lisp Effect Graph

Status: current-checkout component contract
Depends on: `docs/design/workflow_lisp_semantic_workflow_ir.md`,
`docs/design/workflow_command_adapter_contract.md`

## Purpose

`EffectGraph` records the side effects of workflow procedures, macros, and
statements so frontend abstractions cannot hide provider calls, command calls,
state mutation, resource movement, or artifact publication.

## Effect Kinds

Required effects:

- `reads`
- `writes`
- `publishes`
- `uses_provider`
- `uses_command`
- `calls_workflow`
- `updates_state`
- `moves_resource`
- `updates_ledger`
- `captures_snapshot`
- `materializes_pointer`

## Effect Entries

```python
EffectEntry(
    owner: NodeId,
    kind: EffectKind,
    target: EffectTarget,
    capability: Capability | None,
    source_map: SourceMapRef,
)
```

## Procedure Effect Views

`EffectSummary` is the shared effect algebra for both lexical procedure bodies
and caller-visible closure; the compiler does not maintain a second procedure
effect hierarchy.

- `TypedProcedureDef.direct_effect_summary` contains effect atoms emitted by
  the procedure body itself plus its procedure-call edges. A procedure call
  contributes an edge, but does not copy the callee's atoms into this
  body-local direct view.
- `TypedProcedureDef.transitive_effect_summary` is the caller-visible closure
  of the body-local effects and all reachable callee effects. Generic and
  `ProcRef` bodies are authoritatively re-typechecked after their compile-time
  bindings resolve, and this view is recomputed over the materialized
  monomorphic call graph before lowering and declared-effect validation.
- An unresolved compile-time `ProcRef` contributes no guessed runtime effect.
  Its selected monomorphic specialization contributes the chosen hook's
  effects after resolution.

Inline lowering expands the resolved procedure into its owning workflow. The
owner-visible carrier is the enclosing `TypedWorkflowDef.effect_summary`,
which already contains the resolved call summary; there is no separately
authoritative inline `CompositionFragment.effect_summary`. For
`:lowering private-workflow`, the generated private `TypedWorkflowDef` carries
the procedure's resolved transitive summary directly. Semantic IR derives the
selected effect entries and source provenance from those workflow carriers.

These views change compiler bookkeeping only. They do not authorize a workflow
family migration, a new runtime effect kind, or a weaker declared-effect
contract.

## Generated Visibility Effects

The current checkout also promotes a small set of generated visibility effects
into Semantic IR so runtime-visible generated structure is inspectable without
inventing fake authored statements:

- `snapshot_capture`
- `pointer_materialization`
- `pure_projection`
- `materialize_view`

`pure_projection` is visibility for one generated runtime projection boundary,
not evidence that the authored expression gained provider, command, IO, or
state-mutation effects. The underlying pure-expression tree remains effect-free.

Declared runtime-native `resource-transition` is a real state-mutation effect,
not just visibility metadata. The generated step must therefore emit explicit
`resource_transition` effect entries with backend/resource identity, while any
still-live compatibility adapter route may additionally surface
`resource_transition` / `ledger_update` through command-boundary metadata.

## Pure Forms

Pure helpers may compute names, paths, records, constants, and schemas. They
must not create any effect entry.

The compiler rejects pure forms that:

- read files
- write files
- call providers
- call commands
- call workflows
- inspect wall-clock time
- generate random values
- mutate workflow state

When lowering emits a runtime-visible `pure_projection` step, Semantic IR may
carry a generated `pure_projection` effect with payload digest, schema version,
and private bundle lineage. That effect is observational metadata for the
generated boundary, not permission to treat the expression body as effectful.

When lowering emits a runtime-visible `materialize_view` step, Semantic IR may
carry a generated `materialize_view` effect with renderer identity, renderer
schema version, target/allocation lineage, and authority class. The effect is
real file-rendering visibility, but the rendered file remains a representation
only; it must not become semantic authority for bridge-backed state or resume.

## Macro Boundary

Macros may emit frontend AST, but every effect in their expansion must be
visible in the resulting effect graph. A macro that introduces a hidden command
or provider call is invalid.

## Validation Responsibilities

Effect validation checks:

- declared effects cover inferred effects
- disallowed effects are rejected in pure contexts
- workflow summaries include nested procedure effects
- resource transitions have required capabilities
- runtime-native resource transitions expose private `resource_state` and
  `transition_audit` lineage
- command and provider effects have output validation
- semantic command behavior is either a typed procedure, a typed call, a
  certified command adapter, or a runtime-native effect

## Required Invariants

- Effects are semantic IR data, not comments.
- Runtime execution must be explainable from the effect graph and source map.
- Effect checking must not weaken existing YAML validation.
- Inline command glue that mutates semantic state must not disappear into a
  generic `uses_command` entry; it needs adapter metadata or a stronger typed
  construct.

## Open Questions

- Whether YAML workflows receive inferred effect graphs in the first tranche or
  only frontend-generated workflows do.
- How to model undeclared filesystem writes from arbitrary command processes
  without pretending the runtime can fully sandbox them.
