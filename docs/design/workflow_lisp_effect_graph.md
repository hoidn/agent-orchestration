# Workflow Lisp Effect Graph

Status: draft internal design  
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

## Generated Visibility Effects

The current checkout also promotes a small set of generated visibility effects
into Semantic IR so runtime-visible generated structure is inspectable without
inventing fake authored statements:

- `snapshot_capture`
- `pointer_materialization`
- `pure_projection`

`pure_projection` is visibility for one generated runtime projection boundary,
not evidence that the authored expression gained provider, command, IO, or
state-mutation effects. The underlying pure-expression tree remains effect-free.

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
