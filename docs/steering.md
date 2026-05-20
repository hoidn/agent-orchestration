# Local Workflow Steering: DSL v2.14 Materialization And Variants

This steering document records the current local backlog-drain scope for the
DSL v2.14 materialization and variant-output roadmap.

## Current Gate

- Gate id: `dsl-v214-phase2-neurips-stack`
- Selectable phase prefix: `phase-2-dsl-v214-neurips-stack`
- Blocked future prefixes: none

Phase 1 runtime semantics and public `version: "2.14"` support have landed.
The local drain may select Phase 2 workflow-translation and YAML ergonomics
items while preserving the Phase 0 oracle evidence and Phase 1 runtime
contracts.

## Constraints

- Do not reopen the public v2.14 release decision without a new design record.
- Do not delete the legacy workflow stack.
- Preserve old-stack versus v2.14 behavioral equivalence.
- Keep same-version v2.14 workflow call stacks.
- Do not add mixed-version reusable workflow calls.
- Keep tests network-free by default and use fake providers for workflow
  behavior checks.

## Selection Guidance

- Select Phase 2 items related to NeurIPS stack translation, YAML ergonomics,
  and LOC reduction while the roadmap gate allows
  `phase-2-dsl-v214-neurips-stack`.
- Treat pointer authority, runtime semantics, and public v2.14 support as
  completed prerequisites unless new evidence shows a contract gap.
- If a selected item reveals a mismatch between roadmap, backlog item, and
  implementation plan, update the durable roadmap narrowly before broadening
  the backlog item.
