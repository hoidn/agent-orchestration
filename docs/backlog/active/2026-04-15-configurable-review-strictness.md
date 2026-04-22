# Backlog Item: Add Configurable Review Strictness

- Status: active
- Created on: 2026-04-15
- Plan: none yet

## Scope
Add an explicit, configurable review strictness setting for reusable review phases and design-plan-implementation stacks.

The goal is to make review behavior intentionally tunable without relying on ad hoc prompt edits such as "be more picky" or "be less picky." Some runs need a normal execution gate; others need a skeptical audit because they touch durable contracts, architecture, scientific claims, generated artifacts, workflow behavior, or broad implementation plans. The current prompts can be made stricter by editing prose, but that couples local run intent to prompt-source churn.

## Proposed Direction
Use a small typed review standard, not a free-form prompt knob.

Candidate enum:

- `standard`: default behavior; preserve current review expectations.
- `strict`: lower tolerance for vague scope, missing evidence, weak verification, unresolved architecture, or hidden downstream risk.
- `audit`: highest scrutiny for cases where the review is being used to intentionally search for design, plan, claim, artifact-contract, or workflow-quality problems before execution proceeds.

If a lighter mode is considered, it must not disable core contract, safety, artifact-lineage, path-safety, or correctness checks. A "lenient" setting should not be able to approve work that violates the workflow's non-negotiable gates.

## Required Work
- Inventory current review prompts in the generic design-plan-implementation stack, major-project stack, revision-study stack, and any downstream synced copies.
- Decide whether strictness should be a workflow input, phase input, consumed scalar artifact, or prompt asset. Prefer the smallest existing DSL surface that keeps the value typed and visible in debug-logged prompts.
- Add a default `standard` strictness for existing workflows so current callers do not need to change.
- Update review prompts to interpret the configured strictness as a review standard, not as a personality instruction.
- Ensure review reports echo the strictness level used, so later comparisons can distinguish prompt behavior from run configuration.
- Document when to use `standard`, `strict`, and `audit` in `docs/workflow_drafting_guide.md` or an adjacent workflow-authoring guide.
- Add focused tests or smoke checks that verify strictness is propagated to review steps and reports without asserting literal prompt wording.

## Non-Goals
- Do not add a broad DSL feature if typed workflow inputs or existing artifacts are sufficient.
- Do not make strictness a free-form string that callers can use to smuggle arbitrary prompt instructions.
- Do not let strictness override deterministic workflow gates, output contracts, path-safety rules, or required artifact validation.
- Do not create prompt snapshot tests that assert exact review wording.
- Do not retune every review prompt by hand before defining the shared convention.

## Open Questions
- Should `audit` be allowed to block execution, or should it produce findings without changing the normal `APPROVE` / `REVISE` gate semantics?
- Should strictness be configured per workflow run, per phase, or per review step?
- Should implementation review use the same enum as design and plan review, or does it need a smaller surface because it already has concrete execution evidence?

## Success Criteria
- A caller can request stricter review behavior without editing prompt files.
- Existing workflows default to current behavior.
- Review reports record the strictness level used.
- The strictness mechanism is typed, documented, and narrow enough to avoid prompt-injection-style misuse.
- At least one mocked-provider or dry-run smoke check demonstrates that the setting reaches design, plan, and implementation review prompts where applicable.
