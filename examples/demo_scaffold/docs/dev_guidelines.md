# Development Guidelines

## Scope

Make the smallest set of changes that satisfies the task.

## Verification

- Prefer behavioral checks over style-only checks.
- Do not claim completion without running visible checks when available.
- Treat fresh command output as required evidence for verification claims.
- Prefer targeted `pytest` selectors before broader suites.
- If you add or rename tests, run `pytest --collect-only` on those modules.
- If you touch workflow execution, prompting, contracts, provisioning, or trial logic, rerun at least one orchestrator/demo smoke check.
- If verification is incomplete, say exactly what remains unverified.

## Hygiene

- Avoid renames, broad refactors, and formatting-only edits unless required.
- Keep new files minimal and purposeful.
- Write short reports that cite concrete evidence.
