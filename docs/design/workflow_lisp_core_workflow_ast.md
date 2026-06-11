# Workflow Lisp Core Workflow AST

Status: draft internal design  
Depends on: `specs/dsl.md`, `docs/design/workflow_language_design_principles.md`

## Purpose

`CoreWorkflowAST` is the syntax-neutral workflow representation shared by YAML
and frontends such as Workflow Lisp. For YAML it can be the first common
substrate after loading. For Workflow Lisp, the accepted compiler baseline now
passes through WCC/schema 2 first, then defunctionalizes into this flat Core
AST before shared validation.

The Lisp frontend must lower to this AST through the WCC middle-end, not to
YAML text and not through direct per-form lowerers except for explicitly marked
legacy schema 1 compatibility.

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

- Core AST is the only authoritative frontend output accepted by shared
  validation.
- Debug YAML, if emitted, is rendered from Core AST or later IR and is
  non-authoritative.
- Every Core AST node has a source-map path back to YAML or `.orc` source.

## Open Questions

- Whether the existing YAML loader can be refactored to emit Core AST directly
  without changing external behavior.
- Whether Core AST stores provider templates exactly as authored or as resolved
  provider descriptors.
- Whether record-valued Lisp inputs are preserved structurally or flattened at
  this boundary.
