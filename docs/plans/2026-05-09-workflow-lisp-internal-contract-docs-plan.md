# Workflow Lisp Internal Contract Docs Plan

Goal: make `docs/design/workflow_lisp_frontend_specification.md` implementation-gated by explicit internal contracts instead of implicit assumptions.

Scope:

- Add draft design docs for the internal components that the Lisp frontend depends on.
- Update the frontend specification with prerequisites, component boundaries, and links to every new design doc.
- Keep the docs non-normative. They define implementation prerequisites and design contracts, not released runtime behavior.

Files to create:

- `docs/design/workflow_lisp_core_workflow_ast.md`
- `docs/design/workflow_lisp_core_stmt_taxonomy.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_reference_catalog.md`
- `docs/design/workflow_lisp_type_catalog.md`
- `docs/design/workflow_lisp_effect_graph.md`
- `docs/design/workflow_lisp_proof_graph.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_legacy_adapter.md`
- `docs/design/workflow_lisp_debug_yaml_renderer.md`

Files to modify:

- `docs/design/workflow_lisp_frontend_specification.md`

Verification:

- Check every new document is linked from the Lisp frontend specification.
- Run a local markdown-link existence check over the touched docs.
- Inspect the resulting diff for stale or misleading normative wording.
