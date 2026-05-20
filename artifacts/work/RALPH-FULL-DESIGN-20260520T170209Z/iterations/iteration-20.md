# Iteration 20: Module-Header Diagnostic Node IDs

## Selected Slice
- kind: `BACKLOG_ITEM`
- id: `2026-04-29-workflow-authoring-frontend`
- rationale: The full Lisp frontend design requires source-mapped diagnostics with stable semantic identity. Module-header parse diagnostics still lacked `generated_core_node_id` tagging.

## Implementation
- Extended parser diagnostic emission to accept optional `generated_core_node_id` values.
- Added stable module-header clause node-id mapping for `:language` and `:target-dsl`.
- Tagged duplicate/missing header-clause diagnostics with clause-specific node ids.
- Tagged unsupported language/target version diagnostics with clause-specific node ids.
- Added a focused parser test module that verifies these node ids for duplicate, missing, and unsupported header cases.

## Verification
- `pytest --collect-only -q tests/test_workflow_lisp_parser_header_diagnostics.py`
- `pytest -q tests/test_workflow_lisp_parser_header_diagnostics.py`

All verification commands passed.

## Commit
- pending
