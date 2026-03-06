# Development Guidelines

## Scope

Make the smallest set of changes that completes the Rust port and its visible checks.

## Verification

- Prefer behavioral checks over style-only checks.
- Do not claim completion without running local Rust checks when available.
- Treat fresh command output as required evidence for verification claims.
- Prefer targeted `pytest` selectors before broader suites.
- If you add or rename tests, run `pytest --collect-only` on those modules.
- If verification is incomplete, say exactly what remains unverified.

## Hygiene

- Avoid external Python dependencies, FFI, async runtimes, and unrelated refactors.
- Keep boundary and padding behavior explicit and documented.
- Preserve deterministic stride progression and validation rules.
