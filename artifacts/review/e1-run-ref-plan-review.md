# E1 `run-ref` Component Plan Review

Status: approved for E1 execution

Reviewed candidate:

- commit: `0c392ac93e2e7a0304dbda48549d8113904ab90c`
- tree: `3a55ac5f3e7dfcd9d9000d4ac3ca22474df31cb2`
- plan:
  `docs/plans/2026-07-31-workflow-lisp-e1-run-ref-component-plan.md`
- plan SHA-256:
  `524e7a76afd23f8dbcbd7e5b9a33514efbaf347a7a2041bc2d1a8847be899389`
- hermeticity fixture SHA-256:
  `bb7bc47ccdee6e3e3e7e5847e2d4c1b5a3d75194bc6d47014bb6804e0c97382a`
- accepted trial-runs design SHA-256:
  `ed4b4090b71f4310e09aa59d3f347245c640c0727eceec8baf1344a14c53cf53`
- adopted program-search boundaries SHA-256:
  `a42a1db72b887eb94cfa7c3fe93fe6e7269e99daa2867ccd484d16bbe0f0d41b`
- language design principles SHA-256:
  `36a4b4d5626e0d6f7c3444c49f74856a7d4d11cb3bad745e2c475b8b80fe0951`
- E1-E3 owner-selection SHA-256:
  `a3ec1dcdd0d307f4ddfb3eecca7643c175b47d2173f3ba00fc99b7aa9b243e9d`

Ordered verdicts:

1. `E1_PLAN_SPEC_APPROVED`
2. `E1_PLAN_QUALITY_APPROVED`

Review closed at `2026-07-31T23:06:17-07:00`.

## Findings resolved before approval

The proposal at `3f4581d3` widened `RepositoryRevisionId` beyond the accepted
design and scheduled the hermetic full-compiler proof after plan acceptance.
Commit `78b48ae0` restored the exact repository-identity inputs, separated Git
tree/compiler/baseline evidence, and added the five-test preacceptance fixture.
That fixture proves same-path entry and dependency rereads, distinct-root
normalized equivalence, exact source/config read vectors, and structured
ordinary-compiler rejection. It also names the still-required independent
compiler/runtime implementation identity and excludes the path-bound frontend
fingerprint from E1 identity.

Quality review then found two dependency inversions and one under-specified
proof assertion. Commit `0c392ac9` orders the typed compiler/IR before capsule
emission, orders mode-2 compile/admission before parent runtime integration,
and compares exact module-name-to-source-digest vectors. The parent state
transition is the sole settlement point; an adjacent ledger transition is
reconciled only from a fully validated settled result.

Material corrections replayed the specification review before the distinct
quality review. Both approved the same candidate above. No unchanged E0, ML,
M2, C-series, L-series, or successor surface was re-reviewed.

## Approved boundary

The plan selects target-2.24 E1 only: the durable `run-ref` effect, exact
pinned-revision materialization, compiled-bundle and clone-path modes, all
existing transportable input/result shapes, deterministic workspace/accounting
evidence, fresh discard/rerun of incomplete attempts, and validated committed
reuse. Tasks 1–9 must retain their TDD and ordered-review gates.

E2 remains selected pending `PASS_E1`; E3 remains selected pending `PASS_E2`
and first-study review. C1-C3 and all security/isolation work remain outside
this plan. Approval does not claim target 2.24 or `run-ref` is implemented.
