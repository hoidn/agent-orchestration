# E0 Canonical Direct-Control Final Review

Status: `PASS_E0`

Reviewed candidate:

- base tree: `2d332d5f8b41dbd909a8bd174c365c0c9f2a9c37`;
- exact eight-path binary-diff SHA-256:
  `2cd8a67b3d6456481c81228d709a8b991a18363d27a9b1918321f37945b1f087`;
- committed candidate: `fe7d6f9bca9ec61b9078e4048bb43aee7f4f191b`;
- committed tree: `c20f6fd9197b0d0e12a581e96ebbd898b8d1b3c3`;
- production source SHA-256:
  `def92a00126670948fa8a8980a4aab2bc34fce309008d2773299c61080a0324a`;
- direct-control test SHA-256:
  `b6253d24ec1e068d2a195e9109f52c10557511eee0d1fcaa0ccdd7f6278c2a2e`.

Ordered final verdicts:

1. `E0_FINAL_SPEC_APPROVED`, issued by the independent delegated
   specification reviewer `/root/l6_design_quality` against the exact base
   tree and diff digest above.
2. `E0_FINAL_QUALITY_APPROVED`, issued afterward by the distinct independent
   delegated quality reviewer `/root/l6_design_census` against the unchanged
   candidate.

The reviewed candidate was committed byte-for-byte as `fe7d6f9b`. Its fresh
postcommit direct-control, routing, and route-readiness control passed 115
tests.

## Implementation lineage

| Task | Commit | Tree | Result |
| --- | --- | --- | --- |
| 1 — source and compile contract | `b71bf62aa3cc8640e5ae9df47f1ec09794a5eb5c` | `708547530db34397129cc6216029c1c62c0fc637` | canonical target-2.23 source, direct `Bool`, and one composed provider boundary proven |
| 2 — execution and committed-boundary reuse | `3d41a8bf503af14b5aaaaf29e69bc03dfdbb6d5d` | `ff9f590d506a579536011ac39b35b0206db4c7d2` | fresh invocation, zero-retry terminal failure, and same-run committed-boundary reuse proven |
| 3 — accounting parity | `3b9343732d5e764e6e2ebb8f5d2501536d4701ea` | `c93efdb5c45f14a8f4e309e547fa5a7deda68faf` | runtime-owned accounting ownership matches the ordinary composed one-provider control while result/artifact shapes differ |
| 4 — routing | `46387582d2af0636a3f3041a706ddb0f658c8ce8` | `5dc787b69d3deb2010ed1cd4040444eec1e7c62a` | current status surfaces routed; postcommit direct-routing control passed 74 tests |
| 5 — final candidate | `fe7d6f9bca9ec61b9078e4048bb43aee7f4f191b` | `c20f6fd9197b0d0e12a581e96ebbd898b8d1b3c3` | exact reviewed registry/status candidate committed |

## Verification evidence

- Direct-control collection: 4 tests collected.
- Focused E0/provider/prompt/native-return/replay/observability/phased/routing
  gate: 1,167 passed and 1 skipped.
- Deterministic production-source executor smoke with fake provider and
  `max_retries=0`: 1 passed.
- Initial broad non-security gate: 10,115 passed, 19 skipped, 5 warnings, and
  2 failed. Both failures were the route-readiness validators and exposed the
  missing production-library registry row. The complete log SHA-256 is
  `e35590121533f1e11178c2f5a05c5f172e2cee7c86f25f373d61cd692dcf10d9`.
- Corrected broad non-security gate after adding the exact candidate registry
  row: 10,117 passed, 19 skipped, 5 warnings, and 0 failed/errors in 115.06
  seconds. The complete log SHA-256 is
  `21c8a3a0eee208d354b2d88bdf951f72bc282965f673206af9ccb01928c49123`.
- Precommit direct-control/routing/route-readiness control: 115 passed.
- Postcommit direct-control/routing/route-readiness control: 115 passed.
- `git diff --check`: passed before review and commit.

The broad run preserved the repository's standing exclusions for security,
safety, secrets, and provider-isolation paths. Those exclusions are not
counted as passing E0 evidence.

## Exit decision

`PASS_E0`

The production entry has exactly one canonical direct entry and one provider
invocation per fresh zero-retry arm. It accepts the typed task/model/effort
inputs, returns a direct scalar `Bool`, adds no authored result envelope or
report artifact, reuses a committed provider boundary without another
allocation or invocation, fails after one retryable invocation under the
bound zero-retry policy, and uses the ordinary runtime-owned accounting
surface. No compiler, runtime, state, loader, retry-default, prompt contract,
or DSL target changed.

This verdict completes E0 only. It makes E1 eligible for a separate owner
activation decision; it does not select or implement E1, E2, E3, C1, C2, C3,
or any historical evolution tranche.
