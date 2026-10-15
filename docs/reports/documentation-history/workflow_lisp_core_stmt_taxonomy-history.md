# Workflow Lisp Core Stmt Taxonomy: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_core_stmt_taxonomy.md](../../design/workflow_lisp_core_stmt_taxonomy.md).

## Drift From Older Draft

The earlier one-row-per-family draft no longer matches the current checkout
literally. The current contract is:

- `CoreForEach` is a real shared base family and belongs in the inventory.
- `CorePureProjectionStep` is now a real shared generated base family used for
  runtime-visible pure computation and private projection-bundle transport.
- `publish`, `consume_bundle`, `variant_output`, and `pre_snapshot` are current
  attached facets, not standalone `CoreStmt` dataclasses.
- `CoreResourceTransitionStep` is now a real shared generated base family for
  declared runtime-native transitions, while certified-adapter
  `resource_transition` / `ledger_update` compatibility routes still travel
  through `CoreCommandStep`.
- `snapshot_capture` and `pointer_materialization` are still promoted generated
  effects with source-map lineage, not statement families.
- Source maps, runtime-plan summaries, build artifacts, and observability views
  remain derived projections. They must not become semantic authority.

The practical rule is: update this document only when the shared implementation
changes, and describe new behavior in terms of real shared dataclasses plus real
attached facets rather than reviving obsolete standalone-family names.
