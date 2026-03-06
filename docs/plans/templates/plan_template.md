# Plan Template

This template is an authoring aid for the `plan` artifact.

It is not the contract.
The artifact contract is defined in `docs/plans/templates/artifact_contracts.md`.

## Suggested Structure

```md
# Current Plan

## Task Restatement
- Restate the task in concrete engineering terms.

## Scope
- In scope
- Out of scope

## Assumptions and Risks
- Assumptions
- Known risks or uncertainty

## Proposed Design
- Describe the architecture before listing execution steps.
- Call out module or function boundaries.
- Note important interfaces, data shapes, or state transitions.

## Key Invariants
- List the semantic properties that must remain true after implementation.
- Call out the correctness-sensitive areas the checks must protect.

## Implementation Steps
1. First concrete step
2. Second concrete step
3. Remaining execution steps

## Verification Strategy
- Explain what visible verification should exist by the end of execution.
- Call out which checks exist already and which should be created during implementation.

## Completion Criteria
- List the conditions that would justify calling the task complete.
```

## Guidance

- Keep the plan executable, not aspirational.
- Make scope boundaries explicit.
- Call out risky assumptions.
- Align the verification strategy with the separate `check_strategy` artifact.
- Avoid embedding hidden-evaluator assumptions into the plan.
