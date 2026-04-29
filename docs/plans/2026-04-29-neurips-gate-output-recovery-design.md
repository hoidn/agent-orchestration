# NeurIPS Gate Output Recovery Design

## Purpose

When a NeurIPS backlog-drain run resumes an item that already passed an earlier gate, the workflow should not redo that gate unless its durable evidence is missing or invalid. The immediate failure mode is an in-progress item that had already passed planning, then failed during implementation; a fresh run recovered the item but reran planning because the selected-item workflow always calls the plan phase.

The fix is not a new lifecycle state such as `IMPLEMENTATION_READY`. The general model is **gate output recovery**: every resumable gate has an output contract, and recovery either reconstructs that contract from durable evidence or routes through the normal gate.

## Invariants

- Workflows own deterministic control and routing.
- Provider prompts should not decide whether a previous gate can be reused.
- Downstream phases should consume normalized gate outputs and not care whether those outputs came from a fresh gate run or recovery.
- Recovery must be conservative: missing, unsafe, or unverifiable evidence falls back to rerunning the gate.
- The first implementation is scoped to the NeurIPS plan gate only. The naming and structure should still be suitable for later roadmap, implementation, or review gate recovery.

## Gate Output Recovery Pattern

A resumable gate has:

- A durable evidence source, usually queue frontmatter, run state, or stable pointer files.
- A recovery command that validates that evidence.
- A recovered output contract that matches the fresh gate's downstream contract.
- A YAML branch that chooses recovered outputs when valid, otherwise executes the fresh gate.
- A normalization point that publishes one authoritative output surface for downstream steps.

For the NeurIPS plan gate, the fresh gate's relevant downstream contract is:

- `plan_path`
- `plan_review_decision`
- `plan_review_report_path`

The implementation phase should consume a single normalized `plan_path` artifact, not a direct reference to `RunFreshPlanPhase`.

## Plan Gate Evidence

The plan gate may be recovered only for a recovered in-progress item. Durable evidence is valid when:

- The selected item path is under `docs/backlog/in_progress/`.
- The item frontmatter contains a non-empty `plan_path`.
- `plan_path` is a safe repo-relative path under `docs/plans/`.
- The plan file exists.

If the old plan review report can be found, recovery should preserve its path. If no report is available, recovery may write a small recovery report under the current selected-item state root that states the plan was recovered from durable item frontmatter. That report is evidence of the recovery check, not a replacement for the original review.

Longer term, the stronger form is to record an explicit approved-plan marker in durable run state when the plan gate passes. This design does not require that migration before fixing the current bug, because current in-progress backlog items already carry the plan path as the durable authority used by the workflow.

## YAML Shape

The selected-item workflow should add a deterministic plan recovery step before planning:

- It emits `plan_gate_status` with values `RECOVERED` or `MISSING`.
- On `RECOVERED`, a structured branch exposes recovered plan artifacts.
- On `MISSING`, the workflow runs `RunFreshPlanPhase`, asserts approval, rewrites the selected item plan path, and exposes fresh plan artifacts.
- Both branches publish the same branch outputs.
- `RunImplementationPhase` consumes the branch output `plan_path`.

This keeps the branch condition factual and general: "did we recover the gate's output contract?" It avoids item-specific lifecycle states and avoids leaking recovery mechanics into prompts.

## Out Of Scope

- Recovering roadmap sync, implementation, or review gates.
- Changing provider prompts.
- Changing long-running job ownership semantics.
- Adding a generic runtime-level checkpoint engine.
- Treating an arbitrary existing `plan_path` as sufficient for active, newly selected items. New active items should still run the plan gate.

## Verification

The change should be covered by tests that prove:

- A recovered in-progress item with valid `plan_path` does not call `RunFreshPlanPhase`.
- A recovered in-progress item without valid `plan_path` still runs `RunFreshPlanPhase`.
- `RunImplementationPhase` depends on the normalized plan gate output, not directly on the fresh plan step.
- Existing active-item behavior still runs planning.

An orchestrator dry-run should also pass for `workflows/examples/neurips_steered_backlog_drain.yaml`.
