# Workflow Lisp Core Workflow Ast: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_core_workflow_ast.md](../../design/workflow_lisp_core_workflow_ast.md).

## Purpose

`CoreWorkflowAST` is the syntax-neutral workflow representation shared by YAML
and frontends such as Workflow Lisp. For YAML it can be the first common
substrate after loading. For Workflow Lisp, the accepted compiler baseline now
passes through WCC/schema 2 first, then defunctionalizes into this flat Core
AST before shared validation.

The Lisp frontend must lower to this AST through the WCC middle-end, not to
YAML text and not through direct per-form lowerers except for explicitly marked
legacy schema 1 compatibility.

## Open Questions

- Whether the existing YAML loader can be refactored to emit Core AST directly
  without changing external behavior.
- Whether Core AST stores provider templates exactly as authored or as resolved
  provider descriptors.
- Whether record-valued Lisp inputs are preserved structurally or flattened at
  this boundary.
