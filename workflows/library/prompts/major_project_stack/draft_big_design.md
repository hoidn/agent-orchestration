Major-project escalation additions:
- Read the consumed `upstream_escalation_context` artifact. If it is active, treat it as required downstream evidence about why lower phases failed to converge.
- Even when the context is inactive, assess whether the tranche appears too broad or wrongly partitioned to execute as one implementation phase.

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

Keep the phase boundary explicit. The design should settle durable architecture, ownership, behavior claims, source-of-truth contracts, compatibility boundaries, and acceptance standards. Leave task sequence, exact edit lists, command lists, validator implementation mechanics, generated report inventories, and test migration order to the plan unless those details define the contract being designed.

If the consumed escalation context says planning failed to converge, treat that as evidence that the approved design may be too broad, under-specified, wrongly scoped, or missing a planning-critical architectural decision. Revise design-owned decisions only; do not write the plan.

If the project roadmap defines layout or ownership conventions, apply the relevant parts in this tranche design. Do not leave later phases to invent file locations, ownership boundaries, maintained-input locations, generated output locations, or internal component boundaries when the roadmap already made or requires those decisions.

If the roadmap identifies this tranche as part of a cross-tranche family, or repo inspection shows that this tranche has a repeated work shape already used by an earlier tranche, include a `Cross-Tranche Reuse And Family Fit` section. A repeated work shape may involve solving a similar kind of problem, creating or changing similar components, exposing similar interfaces or entrypoints, maintaining similar data or assets, following similar implementation or review steps, or serving similar later consumers.

In that section, classify the tranche as one of:
- first pilot
- second instance needing a reuse/consolidation decision
- later family member expected to consume shared machinery
- intentionally separate local fork

State the evidence for the classification, the closest prior tranche or comparable result, which parts should be reused or refactored into shared helpers, which parts remain tranche-specific, and which prior interfaces, entrypoints, artifacts, or behavior must remain compatible.

A tranche may refactor prior tranche-local work into shared helpers when that refactor is needed for the current tranche. Keep the refactor limited to parts the current tranche will consume, preserve prior tranche behavior and interfaces, and require regression checks for the prior tranche.

Freeze the long-lived ownership boundaries for the tranche: decide what extends an existing subsystem versus introducing a new local component, and decide where the lasting source of truth for changed behavior, stable interfaces, and maintained data or contracts will live.

For any tranche that creates or materially changes production code, stable APIs, maintained data or contracts, or externally consumed persistent artifacts, identify the stable locations, interfaces, provenance assumptions, and checks that belong in the tranche contract. Distinguish authored from derived outputs when both exist. Generated reports, projections, summaries, and review evidence are derived by default, not tranche-contract surfaces, unless a downstream consumer, external user, or stable gate depends on them directly. Define layout at the level needed to fix component ownership and stable locations; leave complete file lists, function-level structure, exact commands, and incidental generated outputs to the plan unless they are part of the contract. Justify any large hand-curated data stored inside executable code.

If the tranche introduces or changes a nontrivial subsystem, process, integration surface, automation, or stable consumed contract, include an `Implementation Architecture` section that defines:
- component boundaries and what each component owns
- owned components and stable location roots for the durable things being created or changed; name exact files, modules, or artifact paths only when they are themselves a stable API, source of truth, provenance boundary, or required handoff
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
- cross-tranche reuse and family fit: whether this tranche is a pilot, consolidation point, later family member, or justified local fork; what prior work is reused or refactored; and what compatibility checks protect earlier tranches
- migration, compatibility, and rollback strategy
- performance, batching, device, or parallelization implications
- discoverability, spec, and documentation impact: when the tranche changes behavioral specs, public or internal APIs, architectural conventions, development processes, test conventions, data or oracle contracts, creates important docs, or changes other durable project knowledge, identify the authoritative docs, specs, documentation indexes such as `docs/index.md`, templates, or guides that should be updated by the implementation plan; state when no durable documentation update is needed
- risks, pivots, blockers, and deferred decisions
- acceptance strategy: the evidence classes and risk-oriented checks needed to support the tranche claim; exact commands, generated-output inventories, and test migration sequence belong in the plan unless they define the acceptance contract

Justify every semantically material choice. Identify unnecessary or counterproductive transformations, adapters, defaults, or inherited conventions instead of carrying them forward automatically.

For the output contract's `design_path`, read the path recorded in that pointer file and write the design document there. Leave the pointer file as a path-only file.
