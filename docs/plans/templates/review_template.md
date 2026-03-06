# Review Template

This template is an authoring aid for review artifacts such as:
- `plan_review_report`
- `implementation_review_report`

It is not the contract.
Decision artifacts and artifact meanings are defined in `docs/plans/templates/artifact_contracts.md`.

## Suggested Structure

```md
# Review Report

## Decision
- APPROVE or REVISE

## Summary
- One short paragraph describing the overall verdict.

## Blocking Findings
1. Finding title
   - Evidence
   - Why it blocks

## Required Fixes
1. Concrete required fix
2. Concrete required fix

## Notes
- Optional non-blocking observations
```

## Guidance

- Review for blocking correctness issues, not style.
- Cite concrete evidence.
- Make required fixes specific enough to execute.
- If no blocking issues exist, say so directly.
