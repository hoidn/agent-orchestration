# Workflow Lisp Core Statement Taxonomy

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_core_workflow_ast.md`

## Purpose

`CoreStmt` is the closed set of statement forms accepted by shared validation.
It is the contract that prevents frontends from inventing runtime behavior that
the executor cannot validate or explain.

## Statement Families

Initial statement families:

- `CoreProviderStep`
- `CoreAdjudicatedProviderStep`
- `CoreCommandStep`
- `CoreAssertStep`
- `CoreWaitForStep`
- `CoreSetScalarStep`
- `CoreIncrementScalarStep`
- `CoreCallStep`
- `CoreIf`
- `CoreMatch`
- `CoreRepeatUntil`
- `CoreFinally`
- `CoreMaterializeArtifacts`
- `CorePreSnapshot`
- `CoreVariantOutput`
- `CoreSelectVariantOutput`
- `CoreConsumeBundle`
- `CorePublish`
- `CoreResourceTransitionCandidate`, only if runtime-native resource transition
  support exists

## Execution Forms

Execution forms remain mutually exclusive where the YAML DSL requires that
today. Higher-level Lisp procedures lower into one or more Core statements,
not into new hidden execution forms.

## Statement Metadata

Every statement carries:

```python
CoreStmtMeta(
    id: StableId,
    display_name: str | None,
    source_map: SourceMapRef,
    lexical_scope: ScopeId,
    generated_by: GeneratedBy | None,
)
```

## Validation Responsibilities

The taxonomy must define:

- which statements produce artifacts
- which statements consume references
- which statements create lexical scopes
- which statements create proof contexts
- which statements may publish top-level artifacts
- which statements may inject provider prompt contracts
- which statements are runtime-only and never prompt-injected

## Required Invariants

- Frontend forms may elaborate into Core statements, but may not bypass the
  taxonomy.
- New statement families require explicit validation, lowering, runtime, and
  observability rules.
- A statement that cannot be source-mapped is invalid.

## Open Questions

- Whether `pre_snapshot` is represented as its own statement or as a producer
  step modifier in Core AST.
- Whether `variant_output` is statement metadata on a producer or a separate
  validation node.
- Whether `publish` remains step-local metadata or becomes an explicit Core
  statement.
