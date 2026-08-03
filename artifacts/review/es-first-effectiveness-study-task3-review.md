# ES First Effectiveness Study Task 3 Review

Status: approved; ES Tasks 0–3 are complete and Task 4 is selected. Live
provider allocation remains gated on the exact Task-6 scientific-lock owner
adoption.

Reviewed implementation:

- base commit:
  `01ca930c329cb24a1555c9427a2fd86428a429ca`, tree
  `c806995cce4c549eda7d63ff1ccb1e840467bcf0`
- implementation commit:
  `0d16ca364c0aeff641232dc0c0c33e445d443623`, tree
  `ee6d60eb18ce03721898d163ad214b12f2c4098f`
- reviewed binary-diff SHA-256:
  `3826adaa36d91313705f2b60ddd5cddbfa02b8fc15a9352c90fbd4a39a5dfaf9`

Frozen implementation bindings:

- decision-lock schema:
  `sha256:25fac73eeea4b91cda003366517f8207945e0ca36980f2874b736fcf137e84bb`
- randomization-manifest schema:
  `sha256:cb6928ae210cbcf6074ecd8d6cdce38eea71d8bca68b33893dadad79a3962a30`
- usage-receipt schema:
  `sha256:178642595bfe61699ab5b125c8f650a58254a6d83e1e89b37345ef216f977c78`
- CLI facade:
  `sha256:22b35e261ea8716d41b0bf9d86a543a1461feef806e867e1760582b539c43c26`
- decision-lock implementation:
  `sha256:2b701ce388ce49fc76d167d23cce150a0158294c53457285a0e0acbbaaba4f0a`
- metering implementation:
  `sha256:c5ebc1c4b406c4e6bdb5b5a43f0244780e72b190d6d30eb1e9d007d13bd693d0`
- pinned success JSONL fixture:
  `sha256:9d5bbbd7eff4ea00a0cda50295d2e5b3a74657f592385139bfaeeb8fb4d880d8`
- fake provider CLI:
  `sha256:b00ec6217441f91d9a3b9d6ade62e7d99e8866bd19fd145e7cb10ef24a0020d1`
- CLI tests:
  `sha256:60111dd9973f04c901c2d4fb4b8207a38543ba982886d2ed5d1cb51fb4ca8cd5`
- decision-lock tests:
  `sha256:06bc728fac18033b47879a7caa21b59d0765e2f4c2944e2ded12e6c709690e1e`
- metering tests:
  `sha256:374d2c03269749179328bf5e9ce4327efe8aaab4cc395a65e2da952ad669b8d6`

Ordered final-byte verdicts:

1. `ES_TASK3_SPEC_APPROVED`
2. `ES_TASK3_QUALITY_APPROVED`

## Findings resolved before approval

The first quality review rejected the candidate because strict resolution of
the evidence root and a receipt-bound raw JSONL occurred outside the intended
exception boundary. A missing path therefore leaked `FileNotFoundError`, and
the CLI returned 1 with a traceback instead of a stable fail-closed diagnostic.

The corrected candidate reports `receipt_evidence_root_unreadable` for an
unreadable root and `receipt_raw_unreadable` for an unreadable bound raw path.
Library tests execute a valid control before each missing-path case. The CLI
test likewise proves a valid join first, then requires exit 2, empty stdout,
the exact diagnostic, and no traceback for both failures. Specification review
approved the corrected frozen bytes before the distinct quality replay.

## Evidence and boundary

The final Task-3 suite collected 92 tests and passed all 92 in 7.97 seconds.
Pyright reported zero errors, warnings, or informational diagnostics; the
syntax-tree guard confirmed no Task-3 production module imports the retired
`orchestrator.experiments` package. The fresh postcommit Task-3 control passed
92 tests in 8.03 seconds.

The implementation derives rather than restates the exact `N=2`, `k=2`,
`M=3`, `1/4`, `81/100`, and `27/32` vector, with its minimality witnesses and
the alpha-`0.05` regression vector. It binds the 22 terminal-route/receipt-slot
rows, all aggregate call ranges, the four-attempt permutation manifest, the
pinned provider executable chain, one terminal usage event per attempt, and
canonical receipts reopened against immutable raw bytes. Tests fail closed on
noncanonical data, derived-field and schedule tampering, malformed or
conflicting usage, cross-attempt data, identity reuse, and receipt mismatch.

This approval closes only provider-free ES metering and decision-lock
validation. It does not adopt the proposed scientific lock, authorize a
provider-bearing ES attempt, implement E3, or make whole-repository,
effectiveness, security, isolation, or sandbox claims.
