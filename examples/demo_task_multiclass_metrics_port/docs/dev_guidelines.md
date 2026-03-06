# Development Guidelines

## Scope

Make the smallest set of changes that completes the Rust port and its visible checks.

## Verification

- Prefer behavioral checks over style-only checks.
- Do not claim completion without running local Rust checks when available.
- If verification is incomplete, say exactly what remains unverified.

## Hygiene

- Avoid external Python dependencies, FFI, async runtimes, and unrelated refactors.
- Keep numeric behavior explicit and documented.
- Preserve deterministic tie-breaking and validation rules.
