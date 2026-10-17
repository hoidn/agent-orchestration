# Workflow Lisp Debug YAML Renderer

Status: Implemented

`orchestrator/workflow_lisp/debug_yaml.py` renders non-authoritative YAML views
of compiled workflows for inspection and debugging; they are never compiler
input or execution authority. See the
[Core Workflow AST](workflow_lisp_core_workflow_ast.md) and
[source map](workflow_lisp_source_map.md) designs.

## Purpose

`DebugYamlRenderer` emits non-authoritative YAML views of compiled workflows for
inspection, migration comparison, golden fixtures, and debugging.

It is not the compiler target.

## Inputs

Allowed inputs:

- Core Workflow AST
- Semantic Workflow IR
- Source Map

The renderer must not read `.orc` source directly to infer semantics.

## Outputs

Possible outputs:

- `expanded.debug.yaml`
- YAML plus source-map comments
- YAML plus sidecar source-map JSON
- migration comparison bundles

## Required Metadata

The rendered YAML must identify itself as non-authoritative:

```yaml
# Debug projection generated from CoreWorkflowAST.
# Do not edit as source of truth.
```

## Validation Responsibilities

Renderer validation checks:

- rendered YAML can be parsed by the YAML loader if the projection claims that
  property
- source-map references are preserved or sidecar-linked
- generated YAML does not omit semantic constraints that would make it
  misleading as an audit artifact

## Required Invariants

- Debug YAML must not be used as the execution input unless explicitly accepted
  as a migration artifact in a separate workflow.
- Differences between debug YAML and source `.orc` are explained by source maps
  and lowering rules.
- The renderer may not bypass shared validation.

## Open Questions

- Whether debug YAML should be emitted from Core AST or Semantic IR by default.
- Whether renderer output should be stable enough for golden tests or only for
  human inspection.
