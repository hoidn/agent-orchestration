# Development Guidelines

## Scope

Make the smallest set of changes that completes the bounded PyTorch port and its visible checks.

## Verification

- Prefer behavioral checks over style-only checks.
- Do not claim completion without running local `pytest` checks when available.
- Treat fresh command output as required evidence for verification claims.
- Prefer targeted `pytest` selectors before broader suites.
- If you add or rename tests, run `pytest --collect-only` on those modules.
- If verification is incomplete, say exactly what remains unverified.

## Hygiene

- Avoid external services, unrelated refactors, and scope creep into the rest of `nanoBragg.c`.
- Do not introduce CUDA, GPU-specific code paths, or performance-only changes as substitutes for correctness.
- Keep tensor shapes, reduction order, and multiplicative factors explicit and documented.
- Favor small helper functions over one monolithic transliteration.
