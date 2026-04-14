Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `project_brief` before acting.

Create a project roadmap and tranche manifest from the broad project brief.

This is a project-decomposition step. Do not implement source changes, edit the broad brief, draft full designs for every tranche, or write implementation plans.

If `docs/index.md` is present, read it first, then use it to select relevant specs, architecture docs, workflow guides, and findings docs for the roadmap decisions.

Before defining tranches, extract the conceptually distinct sequential phases required by the project brief. Preserve those phases as the controlling roadmap structure unless the roadmap explicitly justifies a different ordering.

Do not collapse prerequisite phases into each production implementation tranche when the brief presents them as ordered project phases. Examples of prerequisite phases include repository or documentation setup, architecture discovery, interface or API classification, test or validation coverage expansion, reference-data or oracle generation, data-contract design, migration planning, and implementation architecture.

A tranche may produce documentation, specs, tests, validation assets, inventories, architecture decisions, data contracts, or migration plans without producing production feature code. Production implementation tranches should depend on the relevant prerequisite evidence, coverage, validation, contract, and architecture tranches.

The roadmap must:
- state the high-level project shape and sequencing rationale
- divide the project into sequential tranches that can each be designed, planned, implemented, and reviewed independently
- record prerequisites and blocker conditions for each tranche
- identify architecture, API, data-flow, oracle, compatibility, migration, and verification decisions that must be resolved before or inside specific tranches
- keep tranche boundaries practical: not so broad that a tranche cannot be reviewed, and not so small that it produces no verifiable project progress
- explain which work is deferred, blocked, or intentionally out of scope

The tranche manifest must be JSON with:
- `project_id`
- `project_brief_path`
- `project_roadmap_path`
- `tranches`, an ordered array

Each tranche object must include:
- `tranche_id`
- `title`
- `brief_path`
- `design_target_path`
- `design_review_report_target_path`
- `plan_target_path`
- `plan_review_report_target_path`
- `execution_report_target_path`
- `implementation_review_report_target_path`
- `item_summary_target_path`
- `prerequisites`
- `status`
- `design_depth`
- `completion_gate`

Use `status: "pending"` for tranches ready to be selected once prerequisites are met. Use `status: "blocked"` only when the roadmap identifies a concrete unresolved prerequisite outside the tranche.
Use `design_depth: "big"` for tranches that require the big-design phase. Use `completion_gate: "implementation_approved"` for first-driver tranches.

When tranche brief paths are included in the manifest, write concise standalone tranche brief files at those paths. Each brief should be enough for a later design phase to understand the tranche objective, scope, required context, expected outputs, and verification concerns. Do not turn those briefs into full designs or implementation plans.

For output contract relpath artifacts, read each recorded path from the pointer file and write the rich content to that target path. Leave pointer files as path-only files.
