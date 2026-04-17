Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `project_brief` before acting.

Create a project roadmap and tranche manifest from the broad project brief.

This is a project-decomposition step. Do not implement source changes, edit the broad brief, draft full designs for every tranche, or write implementation plans.

If `docs/index.md` is present, read it first, then use it to select relevant specs, architecture docs, development docs, and findings docs for the roadmap decisions.

Before defining tranches, extract the conceptually distinct sequential phases required by the project brief. Preserve those phases as the controlling roadmap structure unless the roadmap explicitly justifies a different ordering.

Do not collapse prerequisite phases into each production implementation tranche when the brief presents them as ordered project phases. Examples of prerequisite phases include repository or documentation setup, architecture discovery, interface or API classification, test or validation coverage expansion, reference-data or oracle generation, data-contract design, migration planning, and implementation architecture.

A tranche may produce documentation, specs, tests, validation assets, inventories, architecture decisions, data contracts, or migration plans without producing production feature code. Production implementation tranches should depend on the relevant prerequisite evidence, coverage, validation, contract, and architecture tranches.

Do not let evidence, prior artifacts, status labels, or review decisions unlock broader downstream work than they actually support. Narrow or pilot-scoped evidence may justify a correspondingly narrow follow-on tranche, but broader work needs explicit remaining-work gates.

Before finalizing tranches, define the project's completion boundary: what outcome the brief asks for, which users or consumers must be served, which behaviors, artifacts, interfaces, data, workflows, quality constraints, and compatibility promises are in scope, and what evidence would show the project is complete.

If the roadmap covers only a subset, pilot, representative path, or intermediate milestone, state that explicitly. Name the remaining in-scope work at the same semantic level as the brief, and assign it to later tranches, blockers, explicit non-goals, or follow-up owners. Do not let terms like "selected", "practical", "representative", "initial", or "workhorse" become the final definition of done unless the brief itself sets that narrower goal.

When the completion boundary includes users, workflows, integrations, downstream systems, operational paths, or data/artifact consumers, include representative end-to-end tasks, examples, conformance scenarios, or consumer paths as acceptance targets. The acceptance targets should exercise the requested outcome unless the brief explicitly limits success to narrower intermediate milestones.

For broad multi-tranche projects, look for repeated work shapes before finalizing the tranche list. A repeated work shape is a set of tranches that appear to solve a similar kind of problem, create or change similar components, expose similar interfaces or entrypoints, maintain similar data or assets, follow similar implementation or review steps, or serve similar later consumers, even if each member has different domain content.

Record likely cross-tranche family relationships as hypotheses, not as final abstractions. For each likely family, state:
- candidate member tranches
- the repeated work shape
- which tranche is the likely pilot
- when a later tranche should run a consolidation checkpoint before copying the pilot shape
- which parts are expected to remain domain-specific

Do not hardcode shared helpers before there is evidence. It is acceptable for the first pilot tranche to build local work. The roadmap should, however, prevent the second or later family member from blindly copying the pilot by requiring an explicit reuse/consolidation decision.

For broad multi-tranche projects, include a `Project Organization Conventions` section. Base it on the project brief, existing repository layout, existing docs/specs/architecture notes, and the roadmap's planned work.

Define where each relevant kind of work belongs and how to subdivide it when several components exist. Do not stop at top-level roots if later tranches would still need to invent internal ownership.

Include a concrete layout sketch using the target repo's real paths and naming style. Replace the example placeholders with the target repository's actual source roots, tooling roots, artifact roots, test layout, and documentation conventions. Omit irrelevant categories and add project-specific ones when needed.

Example shape:

```text
src/<package>/
  <component_a>/              # production code for one coherent domain/component
    __init__.py
    public_api.py             # stable API surface, if applicable
    internal_logic.py         # reusable implementation logic
  <component_b>/
    ...

tools/<project_or_domain>/
  <command_name>.py           # thin CLI entrypoint
  <component_a>/              # reusable tooling logic for component_a
    generate.py
    validate.py
    render.py

docs/specs/
  <contract_or_catalog>.md    # source-of-truth contracts
  <contract_or_catalog>.json  # machine-readable source of truth, when needed

artifacts/work/<project>/<tranche_or_run>/
  ...                         # generated candidates, reports, logs, temporary outputs

artifacts/<durable_kind>/<owner>/<case_or_dataset>/
  ...                         # promoted/persistent artifacts with provenance

tests/
  <component_or_suite>/        # tests mirror source/tooling component boundaries
```

After the sketch, state which locations reuse existing conventions, which are new roadmap decisions, how each root is subdivided, which entries are thin entrypoints versus reusable modules, and which outputs are maintained, generated, temporary, or promoted.

The roadmap must:
- state the high-level project shape and sequencing rationale
- divide the project into sequential tranches that can each be designed, planned, implemented, and reviewed independently
- include layout and ownership conventions when the project is broad enough that later tranches would otherwise invent file or component locations
- identify cross-tranche family hypotheses and reuse/consolidation checkpoints when several tranches have repeated work shapes
- define the project's completion boundary, including the requested outcome, in-scope promises, omitted in-scope work, and evidence for completion
- define end-to-end acceptance gates when success depends on users, workflows, downstream systems, integrations, operations, or data/artifact consumers
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

When a tranche belongs to a likely cross-tranche family, its brief should mention the family relationship, prior or future related tranches, and whether the tranche is expected to be a pilot, consolidation point, later family member, or intentionally separate despite superficial similarity.

For output contract relpath artifacts, read each recorded path from the pointer file and write the rich content to that target path. Leave pointer files as path-only files.
