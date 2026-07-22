# YAML Retirement Task 2 Attestation Lifecycle Repair Plan

**Status:** execution-ready corrective prerequisite

**Governing plan:** `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`
at SHA-256
`20096b44d03017780394a6789c39705912da1909847ab3460a312c65dcb066fb`.

**Scope of supersession:** this plan supersedes only the Task-1
`broad_failure_baseline_attestation.v1` claim boundary and the failed,
pre-adoption Task-2 attempt described below. Every other ordering, authority,
owner, verification, and evidence requirement in the governing plan remains in
force.

## Reason for the repair

The Task-2 pending materializer emitted this non-owner field:

```json
{
  "claims_not_made": [
    "This pending record is not an owner adoption or mutation authorization."
  ]
}
```

The governing plan requires an owner-confirmed replacement to preserve every
non-owner byte. After adoption, the present-tense description “This pending
record” would be false. The closed validator accepted the contradiction because
it checked only that `claims_not_made` was a nonempty string list. The pending
record therefore must not be presented for owner adoption.

This is a generic lifecycle-contract defect. It is not an owner decision,
evidence-standard change, queue exception, or authorization to weaken any gate.

## Exact generic contract correction

For `broad_failure_baseline_attestation.v1`, both pending and owner-confirmed
states must use exactly this lifecycle-invariant list:

```json
{
  "claims_not_made": [
    "Pending status alone is not owner adoption; this attestation does not authorize source, store, workflow, run-root, or repository mutation or out-of-scope remediation."
  ]
}
```

The production builder and validator must share one constant for those bytes.
The validator must reject the former lifecycle-specific sentence, any additional
claim, any missing claim, reordering, or any other drift. The pending and
confirmed canonical fixtures must carry identical claim bytes.

Test-driven coverage must prove both directions:

1. a pending record can be converted to owner-confirmed form by changing only
   `evidence_status`, `owner`, `owner_confirmations`, and `owner_adoption`, while
   preserving every other value, and both forms validate;
2. the old pending-only sentence and arbitrary claim drift fail closed.

Update every transitively bound fixture digest and the closed fixture manifest.
No queue, workflow family, module, or pilot name may enter the production
mechanism.

## Failed-attempt disposition

The first Task-2 attempt was captured at source commit
`c376faabd3e23d1ee5914c87ed42a620994ec7cb`. It reached ledger generation 11,
produced a six-failure baseline and two approved reviews, then materialized the
contradictory pending attestation at SHA-256
`abbbde1c99e24ca50e4bdbb775fcde29603ef771fd8611c9e75c232d046bca5e`.
No owner adopted it and no Task-2 completion commit exists.

No relocation is permitted merely because this plan describes it. First land a
pre-relocation authority commit containing this exact plan, the generic
capture/validate/apply implementation and tests below, the attestation claim
repair and tests, fresh test evidence, one frozen authority subject, and ordered
approving specification then code-quality reviews over the same subject bytes.
The authority subject and reviews live at:

- `docs/plans/evidence/yaml-retirement/task-2-attestation-lifecycle-repair/pre-relocation/subject.json`
- `docs/plans/evidence/yaml-retirement/task-2-attestation-lifecycle-repair/pre-relocation/specification-review.json`
- `docs/plans/evidence/yaml-retirement/task-2-attestation-lifecycle-repair/pre-relocation/quality-review.json`
- `docs/plans/evidence/yaml-retirement/task-2-attestation-lifecycle-repair/pre-relocation/expected-attempt-paths.txt`

The subject binds the governing and corrective plan bytes, the complete
candidate path/mode/size/digest manifest, exact diff, focused and broad test
evidence, protected-path equality, and the unchanged 34-path failed-attempt set.
The expected-path file contains exactly the sorted 34 repository-relative UTF-8
paths, each followed by LF, and the subject binds its byte digest and row count.
Those reviews authorize only use of the reviewed generic mover under a later
committed exact disposition; they do not themselves authorize an unenumerated
move.

After that authority commit, create a closed disposition record at:

`docs/plans/evidence/yaml-retirement/task-2-attestation-lifecycle-repair/failed-attempt-disposition.json`

It must enumerate every changed or untracked file from that attempt in sorted
original-path order, with original path, archive path, byte size, and SHA-256.
It must also bind the governing-plan digest, corrective-plan digest and the two
committed pre-relocation authority reviews, source commit/tree, ledger
generation-11 request/snapshot/live bytes, baseline, both reviews, pending
materialization request/snapshot/live bytes, and state explicitly:

- the attempt stopped before personal owner adoption;
- none of its baseline, reviews, or pending form may be consumed by a later
  attestation, index, or completion claim;
- archival relocation preserves bytes but grants no mutation or completion
  authority;
- the current ledger must return to its committed generation-5 bytes before a
  fresh Task-2 attempt begins.

The exact top-level disposition keys are `schema_version`, `disposition`,
`governing_plan_binding`, `migration_plan_binding`,
`authority_review_bindings`, `attempt_binding`,
`pre_move_repository_state`, `protected_path_bindings`, `ledger_lineage`,
`attempt_rows`, `attempt_path_count`, `attempt_path_set_sha256`,
`archive_path_set_sha256`, `normalized_row_set_sha256`,
`normalized_disposition_sha256`, and `claims_not_made`.
`schema_version` is `attempt_migration_disposition.v1`; `disposition` is
`archive_failed_pre_adoption_attempt_and_restore_tracked_files`.

Every `attempt_rows` entry contains exactly `original_path`, `archive_path`,
`tracked_state` (`modified | untracked`), `file_type` (`regular`),
`lstat_mode`, `size`, and `sha256`. The path counts and canonical digests cover
the sorted rows and both path projections in both directions.
`pre_move_repository_state` binds current HEAD/tree/index plus the SHA-256 and
row count of a NUL-safe complete status projection captured before the
disposition output exists. `attempt_binding` separately freezes source commit
`c376faabd3e23d1ee5914c87ed42a620994ec7cb`, tree
`a1cc4afd66aa9f6a1024be3b3280793d3f832400`, source root, archive root, and the
exact 34-row expectation. `protected_path_bindings` contains all seven
pre-existing protected paths with type/mode/size/digest and must remain equal
before and after application.

`ledger_lineage` binds the generation-11 request, immutable snapshot, and live
ledger plus the exact committed generation-5 request, immutable snapshot, and
restoration bytes. The restoration bytes must equal both the generation-5
snapshot and `c376faab:<live-ledger-path>`.

Materialize ordered disposition specification and code-quality reviews beside
the disposition. Both bind its exact path and SHA-256 and the already committed
authority review chain. Commit the disposition and both reviews before applying
it. A review, disposition, or tool that exists only in the worktree is not
migration authority.

After the disposition record and its path/digest inventory have been checked,
relocate the exact enumerated attempt files byte-for-byte beneath:

`docs/plans/evidence/yaml-retirement/task-2-attestation-lifecycle-repair/failed-attempt/`

The archive path must append the complete original repository-relative path.
For the tracked live ledger, archive its generation-11 bytes and restore the
original live path to the exact committed generation-5 bytes. Reject a missing,
extra, non-regular, changed, duplicated, or digest-mismatched source or archive
row. Check every source and destination component without following symlinks;
this is ordinary evidence-identity correctness, not a separate hostile-
environment security tranche. The Task-1 committed evidence that was unchanged
by the attempt is not relocated.

This section is the explicit migration contract required by the governing
plan’s immutable-ledger rule. It permits only the enumerated pre-adoption
relocation and generation-5 live-ledger restoration; it does not permit
overwriting or silently discarding evidence.

## Generic migration mechanism

Create `orchestrator/retirement/attempt_migration.py` and
`tests/test_retirement_attempt_migration.py`. Its CLI has four exact modes:
`capture`, `validate`, `apply`, and `postvalidate`.

- `capture` accepts repository root, source root, archive root, corrected plan,
  both authority reviews, source commit/tree, the expected 34-path LF manifest,
  the seven protected paths, and the g5/g11 coordinates. It writes one canonical
  closed disposition and refuses any source-set mismatch.
- `validate` reopens all bound authority, plan, review, Git, protected, ledger,
  and attempt bytes without mutation.
- `apply` first requires the disposition and both disposition reviews to be
  byte-identical committed blobs at HEAD. It permits only reviewed rows. It
  publishes each archive file exclusively, verifies byte/mode equality, then
  removes an untracked source or atomically restores the one tracked source.
  Replay accepts only an identical already-published archive and a source still
  in its exact pre-state or exact reviewed post-state; ambiguous or partial
  state fails closed.
- `postvalidate` requires exact archive coverage, absence of every untracked
  original, the tracked live file equal to its reviewed restoration binding,
  unchanged protected and outside-set projections, and emits a closed
  `attempt_migration_post_report.v1` binding the disposition and both review
  pairs.

Unit tests cover success plus extra/missing input, byte/mode drift, destination
conflict, wrong or uncommitted review authority, incorrect restoration bytes,
and both valid replay states. They do not add security-only hostile Git or
environment injection work.

## Implementation and review sequence

1. Implement the generic disposition mechanism and shared lifecycle-invariant
   claim test first; update fixtures and transitive digests mechanically.
2. Run collection for the changed test modules, the narrow attestation and
   materialization selectors, all retirement broad-evidence tests, and the
   relevant routing selectors.
3. Run the repository broad suite with
   `pytest -q -n 16 --dist=worksteal` in tmux. The same known six external
   failures may be observed, but this repair does not adopt or baseline them.
4. Freeze the pre-relocation authority subject. Obtain specification review
   first, then an independent code-quality review over the same bytes. Commit
   the reviewed plan, generic mover, attestation repair, tests/fixtures, test
   evidence, subject, and reviews without touching the failed-attempt files.
5. From that authority commit, capture and validate the exact failed-attempt
   disposition. Obtain ordered independent reviews over those exact bytes and
   commit the disposition and reviews without relocating anything.
6. Apply only the committed reviewed disposition. Prove original/archive
   coverage in both directions, restore the live ledger to committed generation
   5, and emit the post-move report.
7. Freeze a post-move subject binding the disposition, archive, report, exact
   diff, protected/outside-set equality, and restored generation-5 ledger.
   Obtain ordered specification then code-quality reviews and commit only that
   reviewed archive/result set.
8. Validate each commit and reconstruct its exact allowed path set from durable
   history.

Security-only hostile-environment work remains deferred by the governing plan
and is not added as a gate here.

## Task-2 restart

After the corrective commit, restart Task 2 at Step 1 in the original evidence
root. Freshly capture the workspace baseline and non-target sources, materialize
a new query generation 1, prove the handoff unchanged, then advance a fresh
generation-5 ledger through Steps 1–6. Recapture the complete broad gate against
the corrective HEAD, rebuild the six-failure baseline, and obtain new ordered
specification and quality reviews. Historical archived bytes and reviews are
inadmissible inputs.

Materialize the corrected pending attestation from the fresh baseline/reviews.
Only then pause for the mandatory personal owner adoption. Task 3 remains
forbidden until the corrected owner-confirmed Task-2 boundary is committed.

## Completion conditions

The repair is complete only when:

- the failed-attempt disposition and archive validate byte-for-byte;
- the pre-relocation plan/mover authority and exact disposition were each
  reviewed and committed before relocation;
- the live execution ledger equals committed generation 5 before restart;
- the old pending-only claim rejects and the shared lifecycle-invariant claim
  passes in both lifecycle states;
- focused and broad verification has fresh output;
- two independent ordered reviews approve the exact corrective subject;
- the repair commit contains no protected-path mutation; and
- a fresh Task-2 attempt, not the archived attempt, reaches the personal-owner
  boundary.
