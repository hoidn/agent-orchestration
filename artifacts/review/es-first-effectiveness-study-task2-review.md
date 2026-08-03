# ES First Effectiveness Study Task 2 Review

Status: approved; ES Tasks 0–2 are complete and Task 3 is selected. Live
provider allocation remains gated on the exact Task-6 scientific-lock owner
adoption.

Reviewed implementation:

- base commit:
  `f0c8739a3c9e8844245419a866a4c669f954072c`, tree
  `ac5deee2a25583de007581bf38da6e2607153194`
- implementation commit:
  `d24c1818d586ee5e082a117f4cf46d85a4fc208e`, tree
  `5e8f84cbc688a6f56090c546bb177ed4496afc17`
- reviewed binary-diff SHA-256:
  `40f646230cb730c707edb56a9fdfcc0a82975ae1c5023d9e0cbe299f8df368bb`

Frozen task/evaluator bindings:

- task profile: `sha256:22981a717e1d9593f962afab2c783ce95e4a8ed049655d7641ce10e00492a2ec`
- task-seed manifest: `sha256:c110edbb79665d48953ce4f107976aa13b90c3084984c823c397cb342226ca51`
- fixture manifest: `sha256:bc2917db0aa41c72dc52f31a609e4a009628c304a7b1c8ea584c40abf34b6f3a`
- reviewer perspectives: `sha256:2f5419f430568b3dc83ea2b4541d027d29b33d6b66760121910a8441a3d9f997`
- visible task contract: `sha256:f4cbdd147018b9ab91ed493d8ee8ea58fec2f15c9c34b77860216303b05323fc`
- visible-check manifest: `sha256:ee2f4e9e4c3795543043cb5599cfa8df0f40ca73a26b670e464aae5d4bfb9edb`
- calibration cases: `sha256:de322e15caa1b73566846592579c7e2f30128946a8dc030fc0254dc76974c3cc`
- evaluator: `sha256:a2068233ce05909c75a760e3d6520cf2d731e233a2c89a0e0f839e0f16332028`
- evaluator tests: `sha256:43149cd99ef38046a9bb73cc829ea541dc24c75b390e2ad48d1543c9f9c81a3f`

Ordered final-byte verdicts:

1. `ES_TASK2_SPEC_APPROVED`
2. `ES_TASK2_QUALITY_APPROVED`

## Findings resolved before approval

The reviewed candidate was corrected before the final ordered approvals so
visible checks execute against fresh scratch materializations while a
continuous audit rejects mutation of either protected root, including
swap-and-restore, rename, link, and `dir_fd` paths. The projection, adapter,
and nested child audit bootstrap now precedes candidate-resolvable imports,
and the sole controlled child is bound by executable, argv, working directory,
protected-root pair, bootstrap digest, and explicit environment.

The lifecycle evaluator was also made representation-neutral: it observes
public construction and persisted rebuild behavior instead of prescribing a
private `ModelSpec` layout. Structural fields may be witness-only, may live in
separate consistent containers, and may use architecture-local tagged payloads;
absent or conflicting architecture identity and unknown-architecture routes
still fail closed. The specification reviewer approved these corrected exact
bytes, followed by a distinct quality reviewer against the same bytes.

## Evidence and boundary

The frozen Task-2 suite collected 211 tests. Its precommit gate passed all 211
tests in 322.73 seconds; the final focused evaluator replay passed 61 tests,
the quality replay passed 40 tests, Pyright was clean, and deterministic
task-seed closure passed. The fresh postcommit Task-2 control passed 211 tests
in 282.83 seconds (`0:04:42`).

The resulting package binds one neutral task surface, the complete ten-clause
hard contract and five dispositions, two distinct reviewer perspectives, the
history-free task seed, supported artifact eras, full public lifecycle and
fresh-process reload/inference, compatibility and ownership checks, and
calibration over conforming and defective fixtures. This approval closes only
the provider-free F1 task/evaluator package. It does not adopt the proposed
scientific lock, authorize a provider-bearing ES attempt, implement E3, or
make whole-repository, effectiveness, security, isolation, or sandbox claims.
