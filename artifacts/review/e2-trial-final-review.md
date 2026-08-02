# E2 `trial` Final Review

Status: `PASS_E2`

Reviewed candidate:

- base commit: `925ce4ac56a5cd099a7b9ccea7cb496779f7454e`;
- base tree: `bebcba4a1bbaab8389ad8993cf1cc356ea235be3`;
- reviewed staged tree: `aafa31c09730544a12e33dbc692847a24726a54f`;
- exact staged binary-diff SHA-256:
  `f07b8a94b131e9121b4f279e95849e85e65c6ac0df594d2b7cef2400f981a961`;
- committed candidate: `8aad035ddc0024f1e5f4b121b5dda98dbaf3b6f4`;
- committed tree: `aafa31c09730544a12e33dbc692847a24726a54f`.

Ordered final verdicts:

1. `E2_FINAL_SPEC_APPROVED`, issued by the independent delegated
   specification reviewer `/root/e2_task10_final_spec` against the exact
   staged tree, binary-diff digest, 12-path manifest, and evidence below.
2. `E2_FINAL_QUALITY_APPROVED`, issued afterward by the distinct independent
   delegated quality reviewer `/root/e2_task10_final_quality` against the
   unchanged candidate and evidence.

The reviewed candidate was committed byte-for-byte as `8aad035d`; its tree is
the reviewed staged tree. The fresh postcommit 77-module focused control passed
3,557 tests, and the postcommit routing/readiness control passed 112 tests.

## Exact candidate manifest

The reviewed and committed candidate contained exactly these 12 paths:

| Path | SHA-256 |
| --- | --- |
| `docs/capability_status_matrix.md` | `4d2712b07bf25d0c8e256d8bc150fa34f858bf82d7f943252fabdc6f10c8625d` |
| `docs/design/README.md` | `3e8a21bd52e13624d75bdb5387c169433738c5fa57f63cc932ffae8c16dc6af9` |
| `docs/index.md` | `e56489ed24ab0725304a6fd9721b6a39966aa0692c069e4e4e07cc9327df93c2` |
| `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md` | `489d6d3fb60074fd709d3857aadb798e10796dd2ac6932837a9e9a7c67c62e4d` |
| `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md` | `ccb866ca1d9b6d36c49169f86aa8b69dd7b901ba38037c8ed1b710f15895c4a2` |
| `docs/plans/2026-08-01-workflow-lisp-e2-trial-component-plan.md` | `c6497b1278c0445b48bb1ccef253251538179feeed5a6c3dc472de7533ad5635` |
| `orchestrator/workflow/trial/packets.py` | `936c5bb3f54133e91ace5c7c3b70468df31ea5984600d4e0313c68eac197cea2` |
| `tests/e2e/test_e2e_workflow_lisp_trial.py` | `c3978383327c3e9485c37463da3a2b03c3dcdb4c327c58350db7f3b5f7c90540` |
| `tests/test_dashboard_compiled_workflow.py` | `aff3440e6b864d5ce4988b010b3872c23fd2a37b93f0a0cc523b9ea01104390d` |
| `tests/test_runtime_observability.py` | `1cd0f374705fb94e2fc9fb5c4d6934a4ce1f2cd635c793614f35771ba7b47814` |
| `tests/test_workflow_lisp_drain_roadmap_routing.py` | `90238a74167d1c2aa25d959fbc4c42ffdcb0725e40715296fea964913259446f` |
| `tests/test_workflow_trial_packet_projection.py` | `49996ea9685653c15b6318a0aed26c84729ea4d6f13a87c4375837a402a30cb6` |

## Implementation lineage

| Task | Reviewed tip | Result |
| --- | --- | --- |
| 0 — census and accepted component plan | `c6046d38` | target-2.25 E2 boundaries and ordered plan gate accepted |
| 1 — feasibility and characterization | `456acc7a` | closed evidence, persistence, and nested-transport gaps characterized |
| 2 — normative target-2.25 contract | `6b431087` | `trial` syntax, types, state, versioning, and routing landed |
| 3 — structural transport | `43ae8d5c` | bounded nested record/union transport generalized without trial-name exceptions |
| 4 — typed syntax and generated contracts | `ba430ed2` | exact authored form, placement rules, and monomorphic result contracts landed |
| 5 — IR and checkpoint carriage | `a7a8a083` | one distinct durable effect crosses compiler, lowering, persistence, and resume views |
| 6 — E1 lifecycle and trial ledgers | `5d28619d` | single-writer event seam, identities, and M2-compatible durable facts landed |
| 7 — concurrent cell runtime | `41e64d14` | bounded authored-order execution, failure values, deadlines, crash reconciliation, and fresh ordinals landed |
| 8 — evaluation and verdict | `ebf8a1a9` | evidence freeze, deterministic checks, blinding, scoring, resumable authority, and verdict production landed |
| 9 — executor, SDK, and CLI | `3560b62e` | public surfaces share the ordinary compiler/runtime path |
| 10 — exact fixed-study exit candidate | `8aad035d` | end-to-end clean/resume proof, platform-owned fixed study, label-exclusion probe, broad gate, ordered final reviews, and postcommit controls passed |

## Verification evidence

- Exact Task-10 collection: 51 tests collected; complete log SHA-256
  `df0d4a4aa5a59d3a78e44df275b00c93057a36fd6b55469fea0eae4e6ee50f5d`.
- Exact Task-10 slice: 51 passed in 28.54 seconds / 29.12 seconds
  elapsed; complete log SHA-256
  `414d7abc19f3402dad981e73eb8e5b3162521cab8ba9be1cbb317f1fc0485f38`.
- Frozen precommit 77-module focused gate: 3,557 passed in 142.40 seconds /
  142.70 seconds elapsed; complete log SHA-256
  `aa0c6ee49472930d0370cf76aac48487b6f98da6c794c9fa5ceee6ffc729703e`.
- Real-subprocess fixed-study smoke: one passed in 4.71 seconds / 5.34
  seconds elapsed; complete log SHA-256
  `cbd2d70cb4e68682ea8913d42483ebd349645ca9d94ae248c0c99f6c996635d5`.
- Adjacent stale Task-5 v4 schema-fixture repair gate: 249 passed in 35.04
  seconds / 35.61 seconds elapsed; complete log SHA-256
  `a2ff7bc710cc699479828913b8fb839dbe2a5287104c20ae452b98fae3015b1c`.
- Corrected broad non-security gate: 11,403 passed, 19 skipped, 5 warnings,
  and zero failures/errors in 152.01 seconds / 152.63 seconds elapsed;
  complete log SHA-256
  `77bd779cd22acee2fa97ba322bf56a04e1043e7584f2cbfbbee6577fd184d276`.
- Initial pre-review routing/readiness control: 112 passed; complete log
  SHA-256
  `0edf256b2efd3e4a5613e71771c07e36bb0393f8953bae58dba2f6e483098814`.
- Pending-candidate routing/readiness control: 112 passed in 6.22 seconds /
  6.84 seconds elapsed; complete log SHA-256
  `55e4cae63797201447bbbc3ef8b7d7aeccfd1819f901f4112c78e6d8e389f402`.
- Fresh postcommit 77-module focused control: 3,557 passed in 143.41 seconds /
  143.637078763 seconds elapsed; complete log SHA-256
  `253ae8bb6e4f62d8f4f5c6a21ce525675b2bc5b9ac00eb6dcca23f100c83bdc7`.
- Fresh postcommit routing/readiness control: 112 passed in 6.30 seconds /
  6.80 seconds elapsed; complete log SHA-256
  `1ddb875c44c7e01030a4cdc86595127b83a06ae6a79bfe90315436059e0d5eb3`.
- `git diff --check`, exact path-manifest verification, exact staged-tree
  verification, and the unchanged-commit/tree check passed.

The broad run preserved the repository's standing exclusions for security,
safety, secrets, provider isolation, and the provider-launch shim. Those
exclusions are not counted as passing E2 evidence.

## Fixed-study mechanism proof

The platform-owned fixed study holds the exact Git pin, result contract, task
input, setup, checks, scorer, observation contract, and budgets constant. It
executes one actual provider call for DIRECT and two actual provider calls each
for COORDINATOR and ORC. The sealed label map presents the sorted opaque order
ORC/DIRECT/COORDINATOR; the evaluator-visible packet-byte-only classifier
identifies one of three arms; and all 29 forbidden identity fields fail closed
with exact exclusion diagnostics. The success fixture records an explicit
all-zero treatment-failure table. A separate deterministic COORDINATOR launch
failure remains a terminal treatment outcome while its DIRECT and ORC siblings
complete, proving sibling-independent accounting rather than erasing the
failure.

This is a mechanism proof, not effectiveness or output-quality evidence. It
also makes no security, isolation, or sandbox claim. The clone remains an exact
workspace/output boundary, not a sandbox. No production `.orc` registry row was
added, and route-readiness therefore remains unchanged.

## Exit decision

`PASS_E2`

Target 2.25 is normative and backward compatible within the exact accepted
component contract. Static homogeneous arms compile into one distinct durable
trial effect over exact E1 configs. The coordinator is the sole writer;
authored-order results, sibling-independent failure values, bounds, deadlines,
evaluator-attempt ceilings, clean reuse, and incomplete-cell fresh-ordinal
reconciliation are deterministic and proven. Evidence freezes before
evaluation, deterministic authority precedes judgment, and the blinded join,
aggregation, success rule, and digest-bound verdict validate exactly. The SDK,
CLI, and non-evolution wrapper share the ordinary compiler/runtime path and
expose no privileged admission path.

This verdict completes E2 only within that exact target-2.25 contract. It does
not promote a production `.orc` registry row or establish effectiveness,
quality, security, isolation, or sandbox behavior. The post-`PASS_E2` first
effectiveness study (ES) is now the next on-spine plan- and review-gated stage;
Phase ME may proceed in parallel and never blocks an E exit. E3 remains gated
on review of this fixed study, ES results, and a separate reviewed component
plan. C1-C3, E2O, the historical execution-registry/handle substrate, and all
security work remain unselected.
