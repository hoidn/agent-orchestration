# Backlog Item: A/B Test Major-Project Prompt Boundary Changes

- Status: active
- Created on: 2026-04-15
- Plan: none yet

## Scope
Evaluate whether the major-project and generic design-plan-implement prompt changes in commit `446146664a5b7b86a86640265d18aaf6347dc268` improve workflow behavior compared with the previous prompt set at `e46c017796b70041c20067dee174b36b8afa38fa`.

The prompt changes added or refined guidance for:

- roadmap-level layout and ownership conventions
- big-design component ownership and stable location decisions
- the boundary between design-level layout decisions and plan-level file/command details
- plan and implementation preservation of design layout decisions
- review checks for layout drift, collapsed boundaries, and authored versus derived artifacts

## Desired Outcome
Produce an evidence-backed recommendation:

- keep the prompt changes as-is
- keep the direction but simplify or rebalance selected lines
- split some guidance between roadmap, big-design, plan, and review prompts differently
- or revert specific wording that makes agents too rigid, noisy, or project-specific

## Experiment Design
Run comparable before/after workflow trials using the same project brief or backlog item inputs, provider settings, and max-iteration budgets.

At minimum, include:

- one broad multi-tranche project where layout and component ownership matter
- one tranche that creates or changes production source code
- one tranche that creates durable artifacts, reports, generated files, or curated data
- one smaller tranche where excessive architecture guidance could create noise

For each before/after pair, record:

- roadmap tranche structure and whether prerequisite phases are preserved
- whether project layout conventions are concrete enough for later tranches
- whether big designs define stable component ownership without over-specifying plan-level mechanics
- whether plans preserve design boundaries and translate them into executable tasks
- whether implementation/review phases catch boundary drift without blocking on harmless deviations
- number of design, plan, and implementation review iterations
- decision quality, finding quality, and false-positive or false-negative review behavior
- whether generated code, source code, artifacts, docs, and tests land in coherent locations

## Non-Goals
Do not add prompt-text snapshot tests.
Do not judge the change from a single EasySpin run.
Do not hard-code EasySpin, PyTorch, MATLAB, or PtychoPINN terminology back into generic prompts.
Do not require the after prompt to produce identical tranche names or file paths; compare behavioral quality and traceability.

## Suggested Method
Use isolated checkouts or recorded refs so each trial uses the intended prompt version:

- before: `e46c017796b70041c20067dee174b36b8afa38fa`
- after: `446146664a5b7b86a86640265d18aaf6347dc268`

Capture run IDs, debug prompt logs, generated roadmap/design/plan artifacts, review reports, implementation reports, and final git diffs for each trial. Prefer structured comparison notes over prompt wording assertions.

## Success Criteria
This item is complete when a follow-on report compares before/after runs on at least the cases above and recommends whether to keep, revise, or partially revert the prompt-boundary changes.
