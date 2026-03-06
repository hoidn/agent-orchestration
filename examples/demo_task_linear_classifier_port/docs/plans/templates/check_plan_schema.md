# Check Strategy and Check Plan Guidance

This document defines the recommended contract split between the plan-time `check_strategy` artifact and the implementation-time `check_plan` artifact used by the generic workflow demo.

The goal is to keep workflow execution deterministic without forcing the plan loop to pretend that future tests already exist.

## Purpose

`check_strategy` is produced during planning and consumed later by:
- plan review
- execution
- implementation review
- fix steps

It explains:
- which visible behaviors need verification
- which checks are expected to exist after implementation
- which checks are already runnable now, if any
- why the proposed verification is high-signal for the task

`check_plan` is produced during execution or fix steps and consumed by:
- check execution
- implementation review
- later fix steps

It contains only the runnable commands that `RunChecks` should execute now.

## Recommended `check_plan` JSON Shape

```json
{
  "checks": [
    {
      "name": "unit-tests",
      "argv": ["cargo", "test", "--quiet"],
      "timeout_sec": 900,
      "required": true
    }
  ]
}
```

## `check_plan` Fields

Top-level:
- `checks`: array of check objects

Per check:
- `name`: short stable identifier for logs and reports
- `argv`: command as an argument vector, not a shell string
- `timeout_sec`: positive integer timeout
- `required`: boolean

## `check_strategy` Authoring Rules

- Describe intended visible verification, not hidden-evaluator assumptions.
- Call out which checks already exist and which are expected to be created during execution.
- Prefer high-signal behavioral checks over formatting-only checks.
- If current repo verification is weak, say so explicitly rather than fabricating commands that do not exist yet.

## `check_plan` Authoring Rules

- Prefer deterministic commands.
- Prefer `argv` over shell fragments.
- Every required check should be runnable in the current repo at the time the artifact is written.
- Do not include placeholder commands for tests that do not exist yet.
- Do not include commands that depend on hidden evaluator internals.
- Keep checks focused on visible verification only.

## Review Rules

A plan-time verification strategy is weak and should typically be revised when:
- it only checks formatting or lint but not behavior
- it does not explain how visible verification will become runnable
- it omits obvious high-signal verification opportunities visible from the task and repo
- it depends on hidden tools or external services not part of the scaffold

A runnable `check_plan` is weak and should typically trigger implementation revision when:
- it contains commands that do not exist in the repo
- it is stale relative to tests/checks created during execution
- it is too narrow for the stated task
- it is so broad or slow that it is impractical for iterative review/fix cycles

## Execution Notes

- A generic `RunChecks` step should execute the current runnable `check_plan` exactly as written.
- Invalid or stale `check_plan` entries should normally be recorded in structured `check_results`, not crash the workflow.
- Review may still reject despite passing checks if blocking correctness gaps remain.
