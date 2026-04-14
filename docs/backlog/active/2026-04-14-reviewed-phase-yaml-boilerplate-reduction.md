# Backlog Item: Reduce Reviewed Phase YAML Boilerplate

- Status: active
- Created on: 2026-04-14
- Plan: none yet

## Scope
Reduce repeated YAML scaffolding in workflows that implement draft/review/revise phases with explicit `APPROVE`, `REVISE`, and `BLOCK` routing.

The major-project tranche workflow exposed how much boilerplate is needed to express a reviewed phase: provider setup, artifacts, path pointer initialization, expected outputs, review output bundles, decision routing, revise loops, block/finalize behavior, and caller-visible outputs. The explicit mechanics are useful for resumability and auditability, but the same shape is now repeated across tracked design, big design, roadmap, plan, and implementation-style phases.

This item should improve authoring conventions and reuse without introducing a broad new phase abstraction prematurely.

## Required Work
- Inventory existing reviewed-phase workflows and identify repeated YAML structures.
- Define a small canonical reviewed-phase interface in documentation, including common artifact names such as input document, candidate output document, review report, decision, and open findings.
- Add a reusable authoring template or exemplar for reviewed draft/review/revise phases with `APPROVE`, `REVISE`, and immediate `BLOCK` behavior.
- Clarify when a workflow should reuse an existing library phase versus create a new reviewed-phase variant.
- Update the workflow drafting guide to point authors at the reviewed-phase convention/template before they copy and modify a large workflow.
- Keep prompt-specific judgment and deterministic workflow control separate; do not move loop mechanics into prompts to reduce YAML.

## Non-Goals
- Do not redesign the DSL or add a generic phase primitive as the first step.
- Do not collapse artifact lineage or output contracts just to reduce line count.
- Do not make one universal interface that forces unrelated phases into the wrong shape.
- Do not add tests that assert literal prompt phrasing.

## Success Criteria
- New reviewed-phase workflows can be drafted from a compact, documented skeleton instead of copying hundreds of lines from a previous workflow.
- Existing examples clearly show the standard reviewed-phase surfaces and route behavior.
- The major-project roadmap and big-design phases can be compared against the convention without hidden one-off mechanics.
- Workflow YAML remains explicit about artifacts, outputs, and routing, but repeated authoring decisions are documented once.
