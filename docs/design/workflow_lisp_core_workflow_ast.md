# Workflow Lisp Core Workflow AST

`orchestrator/workflow/core_ast.py` retains shared dataclasses and validation for
analysis/imports and read contracts. Current `.orc` entries elaborate through the
shared typed frontend into a [checked closed program](workflow_lisp_evaluated_execution.md#4-the-closed-program).
Old-header typed imports do not select a flat executor. The shape below is an
internal model sketch; executable scheduling/persistence belong to the evaluated
contract and [State](../../specs/state.md).

Status: current retained analysis/data-model contract; historical executable projection
Depends on: `specs/dsl.md`, `docs/design/workflow_language_design_principles.md`

<a id="purpose"></a>

The original WCC-to-flat-Core execution requirement is historical; it does not govern current checked-program execution. See the [preserved record](../reports/documentation-history/workflow_lisp_core_workflow_ast-history.md#purpose).

## Ownership Boundary

Owned by the shared compiler/loader layer:

- workflow identity and version
- typed inputs and outputs
- imported workflow references
- statement list
- artifact declarations
- provider template declarations
- source map anchors

Not owned by this AST:

- frontend syntax objects
- macro expansion logic
- executable step scheduling
- provider execution
- persisted runtime state

## Required Shape

The minimum shape is:

```python
CoreWorkflow(
    name: QualifiedName,
    version: DslVersion,
    source: SourceOrigin,
    inputs: list[CoreInput],
    outputs: list[CoreOutput],
    imports: dict[str, CoreImport],
    artifacts: dict[str, CoreArtifact],
    providers: dict[str, CoreProviderTemplate],
    statements: list[CoreStmt],
    source_map: SourceMapRef,
)
```

The AST must preserve authored stable identities where they exist and must carry
generated identities where the frontend elaborates higher-level forms.

## Validation Responsibilities

Core validation begins after construction:

- DSL version support
- unknown-field rejection after frontend lowering
- execution-form mutual exclusion
- workflow input/output contract validity
- import resolution and same-version call rules
- artifact contract validity
- statement-local reference scope
- source-map coverage for generated nodes

## Required Invariants

- Retained Core dataclasses and shared validation serve typed analysis/imports
  and historical readers; they are not the executable output of current Lisp.
- Checked closed programs are executable authority; debug YAML emission is retired.
  Reports and source maps remain views of structured authority.
- Every Core AST node has a source-map path back to YAML or `.orc` source.

<a id="open-questions"></a>

The old YAML-loading/flattening questions are historical; current input contracts are owned by checked-program construction. See the [preserved record](../reports/documentation-history/workflow_lisp_core_workflow_ast-history.md#open-questions).
