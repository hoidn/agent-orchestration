# Local Workflow Steering: DSL v2.14 Materialization And Variants

This steering document scopes the local NeurIPS-style backlog drain for the
DSL v2.14 materialization and variant-output work.

## Intent

- Advance the v2.14 semantics only through the ordered roadmap in
  `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md`.
- Use the completed Phase 0 oracle as the safety net for Phase 1 runtime
  implementation.
- Keep public DSL support capped at the existing supported versions until the
  runtime, loader, docs, and tests for v2.14 land together.
- Treat the implementation plan in
  `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`
  as the design authority.

## Constraints

- Do not expose runnable public `version: "2.14"` workflows until the runtime,
  loader, docs, and tests for Phase 1 land together.
- Do not translate public v2.14 workflow stacks before Phase 1 is complete.
- Do not start Phase 2 workflow translation until the public v2.14 release gate
  has landed.
- Keep tests network-free by default and use fake providers for workflow
  behavior checks.
- Preserve existing DSL version gating, path-safety rules, same-version call
  restrictions, and output-contract validation semantics.

## Selection Guidance

- Select the Phase 1 runtime-semantics backlog item while the roadmap gate
  allows `phase-1-dsl-v214-runtime`.
- Treat Phase 2 work as future roadmap scope until Phase 1 is complete and the
  gate advances.
- If the selected item reveals a real mismatch between the roadmap, backlog
  item, and implementation plan, update the roadmap narrowly rather than
  broadening the backlog item.
