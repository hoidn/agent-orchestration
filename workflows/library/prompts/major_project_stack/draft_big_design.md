Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `tranche_brief`, `project_brief`, `project_roadmap`, and `tranche_manifest` artifacts before acting.

Create a design document for the selected tranche.

This is a design-only step. Do not implement the tranche, edit source files, edit tests, or write the implementation plan. Treat the project brief, project roadmap, and tranche manifest as context and provenance; do not mutate them.

If `docs/index.md` is present, read it first, then use it to select relevant specs, architecture docs, workflow guides, and findings docs for the design decisions.

The design must decide the right implementation shape for this tranche. Include heavier sections only where they are relevant, but do not omit them when the tranche affects architecture, APIs, data contracts, stable modules, or long-lived project structure.

The design must be self-contained for the downstream generic plan and implementation phases. Those phases will consume the design document, not the whole project context. Include a compact "tranche context snapshot" that records:
- selected tranche brief path and objective
- relevant manifest fields, including prerequisites, target artifacts, design depth, and completion gate
- roadmap constraints and sequencing dependencies that the plan and implementation must preserve
- project-level decisions from the roadmap that govern this tranche

Address where relevant:
- tranche objective, scope, non-goals, and relationship to the project roadmap
- ADR or architecture decision section
- type-driven interfaces and public contracts
- data flow, ownership, source-of-truth, oracle, and provenance contracts
- module, package, and integration boundaries
- migration, compatibility, and rollback strategy
- performance, batching, device, or parallelization implications
- spec and documentation updates required by the tranche
- risks, pivots, blockers, and deferred decisions
- verification strategy with visible checks and reviewable artifacts

Justify every semantically material choice. Identify unnecessary or counterproductive transformations, adapters, defaults, or inherited conventions instead of carrying them forward automatically.

For the output contract's `design_path`, read the path recorded in that pointer file and write the design document there. Leave the pointer file as a path-only file.
