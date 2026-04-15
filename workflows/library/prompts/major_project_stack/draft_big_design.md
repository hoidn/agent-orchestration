Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `tranche_brief`, `project_brief`, `project_roadmap`, and `tranche_manifest` artifacts before acting.

Create a design document for the selected tranche.

This is a design-only step. Do not implement the tranche, edit source files, edit tests, or write the implementation plan. Treat the project brief, project roadmap, and tranche manifest as context and provenance; do not mutate them.

If `docs/templates/design_template.md` is present, read it and use it for document structure. Omit irrelevant optional sections rather than padding the design. Preserve the tranche-specific requirements below even when you shorten or combine template sections.

If `docs/index.md` is present, read it first, then use it to select relevant specs, architecture docs, development docs, and findings docs for the design decisions.

The design must decide the right implementation shape for this tranche. Include heavier sections only where they are relevant, but do not omit them when the tranche affects architecture, APIs, data contracts, stable modules, or long-lived project structure.

The design must be self-contained for the downstream generic plan and implementation phases. Those phases will consume the design document, not the whole project context. Include a compact "tranche context snapshot" that records:
- selected tranche brief path and objective
- relevant manifest fields, including prerequisites, target artifacts, design depth, and completion gate
- roadmap constraints and sequencing dependencies that the plan and implementation must preserve
- project-level decisions from the roadmap that govern this tranche

If the project roadmap defines layout or ownership conventions, apply the relevant parts in this tranche design. Do not leave later phases to invent file locations, ownership boundaries, maintained-input locations, generated output locations, or internal component boundaries when the roadmap already made or requires those decisions.

For any tranche that creates source code, tools, durable artifacts, or curated data, identify stable locations, stable interfaces, provenance assumptions, and required checks that are part of the tranche contract. Distinguish authored from derived files when both exist. Define layout at the level needed to fix component ownership and stable locations; leave complete file lists, function-level structure, and exact commands to the plan unless they are part of the contract. For example, the design might place a new package under `src/<package>/<component>/` and its command entrypoint under `tools/<project>/`, while leaving exact module names and command flags to the plan. Or it might decide that promoted reference data lives under `artifacts/<kind>/<owner>/` and run reports live under `artifacts/work/<project>/`, while leaving exact filenames to the plan. Justify any large hand-curated data stored inside executable code.

If the tranche introduces or changes a nontrivial subsystem, process, integration surface, automation, or durable artifact contract, include an `Implementation Architecture` section that defines:
- component boundaries and what each component owns
- owned files, directories, modules, or artifact roots for each concrete thing being created or changed
- data, control-flow, API, or artifact interfaces between components
- invariants and failure modes the design relies on
- stable decisions, contracts, and invariants downstream work may rely on, without over-specifying plan-level mechanics
- test or review boundaries for the component contracts and invariants

When the tranche creates or changes concrete things that should change or be reviewed independently, keep them separate unless the design explains why they belong together.

Address where relevant:
- tranche objective, scope, non-goals, and relationship to the project roadmap
- ADR or architecture decision section
- type-driven interfaces and public contracts
- data flow, ownership, source-of-truth, oracle, and provenance contracts
- module, package, and integration boundaries
- migration, compatibility, and rollback strategy
- performance, batching, device, or parallelization implications
- discoverability, spec, and documentation impact: when the tranche changes behavioral specs, public or internal APIs, architectural conventions, development processes, test conventions, data or oracle contracts, creates important docs, or changes other durable project knowledge, identify the authoritative docs, specs, documentation indexes such as `docs/index.md`, templates, or guides that should be updated by the implementation plan; state when no durable documentation update is needed
- risks, pivots, blockers, and deferred decisions
- verification strategy with visible checks and reviewable artifacts

Justify every semantically material choice. Identify unnecessary or counterproductive transformations, adapters, defaults, or inherited conventions instead of carrying them forward automatically.

For the output contract's `design_path`, read the path recorded in that pointer file and write the design document there. Leave the pointer file as a path-only file.
