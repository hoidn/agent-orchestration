# Workflow Lisp Effect Graph

Status: current-checkout component contract
Depends on: `docs/design/workflow_lisp_semantic_workflow_ir.md`,
`docs/design/workflow_command_adapter_contract.md`

Versioned authoring rules are owned by
[effect-ledger simplification](workflow_lisp_effect_ledger_simplification.md)
(inference-default optional restrictions and consumer-led metadata cleanup) and
[pure-call composition](workflow_lisp_pure_call_composition.md)
(implemented resolved-inline semantic-effects versus expression-representation
subset). At definition origins 2.35–2.38, retain exact ordinary declarations
and specialization exceptions. At 2.39, inference-default restrictions and
inspection use the same summaries as caller-owned inline composition. The
[frontend](workflow_lisp_frontend_specification.md#106-procedure-lowering-policy-resolved)
owns source admission and lowering; the pure-call component owns its
admitted expression positions independently of annotation relief.

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

For admitted definition origins 2.35–2.38, declaration validation is narrower
than a universal contract claim: ordinary authored procedures require an exact
declared/inferred match;
specializations and generated names are exempted by the current compiler.
An empty clause on an unresolved generic is therefore not proof that every
selected call is pure. For definitions originating at target 2.39, omission means inference without an
authored restriction, explicit empty requires no inferred effects, and named
clauses are resolved upper bounds checked after concrete specialization and
the final fixed point. Generated helpers without a restriction are unconstrained;
unresolved generic hooks are incomplete, never proven empty. The
[effect-ledger contract](workflow_lisp_effect_ledger_simplification.md) owns
subject identity, origin carriage and inspection. Older imported definitions
retain their regime. The shared summary and runtime effect evidence do not change.

Inline lowering expands the resolved procedure into its owning workflow. The
owner-visible carrier is the enclosing `TypedWorkflowDef.effect_summary`,
which already contains the resolved call summary; there is no separately
authoritative inline `CompositionFragment.effect_summary`. For
admitted 2.35–2.38 `:lowering private-workflow`, the generated private
`TypedWorkflowDef` carries
the procedure's resolved transitive summary directly. These carriers feed
frontend analysis and lowering. Semantic IR reconstructs concrete operation
entries and provenance from lowered operations and source metadata; it is not a
serialization of the typed `EffectSummary`.

These views change compiler bookkeeping only. They do not authorize a workflow
family migration, a new runtime effect kind, or a weaker declared-effect
contract.

<a id="generated-visibility-effects"></a>
<a id="open-questions"></a>

Historical flat generated-effect projections remain useful analysis/read metadata. They do not admit generated projection, view or resource effects to current evaluated execution; the checked site table and inferred typed effects govern that route. See the [preserved record](../reports/documentation-history/workflow_lisp_effect_graph-history.md#generated-visibility-effects).

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

## Macro Boundary

Macros may emit frontend AST, but every effect in their expansion must be
visible in the resulting effect graph. A macro that introduces a hidden command
or provider call is invalid.

## Validation Responsibilities

Effect validation responsibilities (implemented scope follows the procedure
views above and current frontend tests):

- at targets 2.35–2.38, ordinary authored declarations equal inferred effects; the broader coverage
  direction does not override current specialization exceptions or make clauses
  optional
- disallowed effects are rejected in pure contexts
- workflow summaries include nested procedure effects
- resource transitions have required capabilities
- historical resource-transition projections preserve private `resource_state`
  and `transition_audit` lineage without current effect admission
- command and provider effects have output validation
- semantic command behavior is either a typed procedure, a typed call, a
  certified command adapter, or a runtime-native effect

## Required Invariants

- Effects are typed structured analysis data, not comments.
- Runtime execution must be explainable from the effect graph and source map.
- Effect checking preserves retained imported-source validation; historical
  YAML validation does not restore YAML execution.
- Inline command glue that mutates semantic state must not disappear into a
  generic `uses_command` entry; it needs adapter metadata or a stronger typed
  construct.
