# Workflow Lisp Source Map

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_core_workflow_ast.md`

## Purpose

`SourceMap` connects frontend source forms to Core AST nodes, Semantic IR nodes,
Executable IR steps, runtime logs, and validation errors.

No frontend abstraction is acceptable if failures become harder to explain.

## Source Map Entry

```python
SourceMapEntry(
    node_id: NodeId,
    source_file: str,
    span: SourceSpan,
    form_path: list[int | str],
    module: QualifiedName,
    expansion_stack: list[ExpansionFrame],
    generated_name_origin: str | None,
)
```

## Expansion Frames

Expansion frames record:

- macro name, if any
- procedure name, if any
- standard-library form, if any
- source span that triggered expansion
- generated Core node ids

## Required Coverage

Source maps must cover:

- frontend syntax nodes
- macro-generated nodes
- procedure-generated Core statements
- Core AST nodes
- Semantic IR nodes
- Executable IR steps
- runtime validation and execution errors

## Diagnostics

Diagnostics should show:

```text
error: variant_ref_unproved
generated step: %implementation.publish_execution_report
source: neurips/implementation.orc:84:5
form: (match implementation ...)
expansion stack: review-revise-loop -> publish-result
```

## Validation Responsibilities

Source-map validation checks:

- every generated Core statement has a source-map entry
- every Semantic IR error can identify an origin
- macro expansion frames are deterministic
- generated names can be explained

## Required Invariants

- Debug YAML must preserve source-map comments or sidecar references if emitted.
- Runtime logs should display both executable step names and high-level source
  forms where available.

## Open Questions

- Whether source maps are persisted for every run or only when compiled from a
  non-YAML frontend.
- Whether source maps should be embedded in state or stored as run-root
  sidecars.
