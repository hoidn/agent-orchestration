# Check Plan Schema

This document defines the recommended machine-readable schema for the `check_plan` artifact used by the generic workflow demo.

The goal is to keep workflow execution deterministic without hard-coding a task domain into the workflow YAML.

## Purpose

`check_plan` is the visible verification plan produced during planning and consumed later by:
- plan review
- check execution
- implementation review
- fix steps

It should contain runnable commands derived from the task and current repo state.

## Recommended JSON Shape

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

## Fields

Top-level:
- `checks`: array of check objects

Per check:
- `name`: short stable identifier for logs and reports
- `argv`: command as an argument vector, not a shell string
- `timeout_sec`: positive integer timeout
- `required`: boolean

## Authoring Rules

- Prefer deterministic commands.
- Prefer `argv` over shell fragments.
- Every required check should be runnable in the current repo.
- Do not include placeholder commands for tests that do not exist yet.
- Do not include commands that depend on hidden evaluator internals.
- Keep checks focused on visible verification only.

## Review Rules

A check plan is weak and should typically be revised when:
- it only checks formatting or lint but not behavior
- it contains commands that do not exist in the repo
- it relies on hidden tools or external services not part of the scaffold
- it omits obvious high-signal verification opportunities visible from the task and repo
- it is so broad or slow that it is impractical for iterative review/fix cycles

## Execution Notes

- A generic `RunChecks` step should execute the current `check_plan` exactly as written.
- Results should be persisted in a structured `check_results` artifact.
- Review may still reject despite passing checks if blocking correctness gaps remain.
