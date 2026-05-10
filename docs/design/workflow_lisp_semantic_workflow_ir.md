# Workflow Lisp Semantic Workflow IR

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_core_workflow_ast.md`

## Purpose

`SemanticWorkflowIR` is the validated, type-rich representation between Core
AST and executable IR. It records the meaning of a workflow after contracts,
references, effects, proofs, and state layout are resolved.

## Ownership Boundary

Semantic IR owns:

- resolved workflow graph
- type catalog
- contract catalog
- reference catalog
- effect graph
- proof graph
- state layout
- artifact availability table
- source map references

Semantic IR does not own:

- frontend syntax
- macro expansion
- provider process execution
- persisted `state.json`
- debug YAML rendering

## Required Shape

```python
SemanticWorkflowIR(
    workflows: dict[QualifiedName, SemanticWorkflow],
    types: TypeCatalog,
    contracts: ContractCatalog,
    refs: ReferenceCatalog,
    effects: EffectGraph,
    proofs: ProofGraph,
    state_layout: StateLayout,
    source_map: SourceMap,
)
```

Each `SemanticWorkflow` records:

- typed inputs and outputs
- executable statements before scheduling
- call graph edges
- provider prompt-contract surfaces
- command validation surfaces
- artifact publication plan

## Validation Responsibilities

Semantic IR construction must fail if:

- references are unresolved
- contracts are weakened
- variant-specific fields lack proof
- snapshot refs are used outside allowed evidence positions
- pointer authority conflicts are detected
- effects are hidden or undeclared
- source-map coverage is incomplete

## Required Invariants

- Semantic IR is the authoritative meaning of a compiled frontend workflow.
- Executable IR must be derivable from Semantic IR without reinterpreting
  frontend syntax.
- Any runtime error emitted from executable IR must be able to point back to
  Semantic IR and source-map origin.

## Open Questions

- Whether Semantic IR should be serialized as a stable debug artifact in every
  run or only under debug flags.
- Whether effect checking is mandatory for YAML workflows or initially only for
  Lisp frontend workflows.
