# YAML-Retirement Task 2 Commit-Lineage Restart Design

- **Status:** accepted
- **Kind:** operational migration design
- **Owner:** Ollie, owner of the YAML-retirement roadmap
- **Reviewers:** independent specification review, then independent code-quality review
- **Created:** 2026-07-22
- **Last material update:** 2026-07-22
- **Related plans:**
  - `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`
  - `docs/plans/2026-07-22-yaml-retirement-task-2-attestation-lifecycle-repair-plan.md`
- **Implementation target:** a backward-compatible successor disposition in
  `orchestrator/retirement/attempt_migration.py`, its tests, reviewed migration
  evidence, and a fresh Task 2 capture

## Summary

Task 2 produced and received personal owner adoption for a broad-failure
baseline, but that attempt cannot cross its required controlled commit
boundary. Its workspace baseline records one commit while the intended commit
predecessor contains a later ordinary commit whose changed path is not covered
by a retirement-control trailer. The commit controller correctly refuses to
infer authority for that predecessor delta.

The accepted resolution is to preserve the complete owner-adopted attempt as
historical evidence, restore only the tracked live execution ledger to its
committed pre-attempt generation, and restart Task 2 from a workspace baseline
captured at the actual corrective HEAD. The existing pre-adoption migration
schema remains unchanged. A successor schema records the materially different
truth: personal adoption occurred, but no controlled completion commit did.

## Context And Authority

The governing Task 2 plan requires one immutable workspace baseline, exact
non-target bindings, an adopted six-failure baseline, and a controlled commit
whose predecessor and staged path set reconstruct from durable authority. The
existing `precommit_control.v1` implementation intentionally accepts later
committed workspace changes only when their commits carry reconstructable
retirement-control trailers.

The earlier lifecycle-repair plan introduced
`attempt_migration_disposition.v1` for a failed attempt that stopped before
personal owner adoption. Its capture, validation, apply, replay, and
postvalidation paths are implemented and tested in
`orchestrator/retirement/attempt_migration.py` and
`tests/test_retirement_attempt_migration.py`. That is the feasibility proof for
the common byte-preserving relocation and tracked-ledger restoration
mechanics. Its fixed pre-adoption lifecycle claim is also why it cannot be
reused unchanged here.

This design does not change Task 2's six-failure baseline semantics, owner
authority, or commit-control policy. It supplies the missing truthful recovery
class after that policy rejects an adopted but uncommitted attempt.

## Problem

The attempt has four facts that must all remain true:

1. The owner personally adopted the exact broad-failure attestation.
2. The attempt never reached the required controlled commit boundary.
3. The recorded workspace-baseline HEAD does not describe the intended commit
   predecessor, and the intervening ordinary commit is not represented by a
   retirement-control trailer.
4. The live execution ledger and append-only materialization slots prevent a
   silent in-place recapture.

The v1 mover would falsely state that the attempt stopped before adoption.
Overwriting the baseline or ledger would break content-addressed history.
Adding an undocumented second workspace baseline would violate the closed Task
2 layout. Rewriting or reverting the intervening commit would mutate unrelated
history. Bypassing the controller would make the Task 2 completion claim
unreconstructable.

## Goals And Non-Goals

### Goals

- Preserve every attempt byte, including the owner-confirmed attestation.
- Distinguish owner adoption from controlled repository completion.
- Prove the exact predecessor mismatch and uncovered committed-path set.
- Reuse the reviewed relocation, replay, protected-path, and ledger-restoration
  mechanics without changing v1 behavior.
- Require committed, independently reviewed authority before relocation.
- Restart Task 2 from the actual corrective HEAD and require fresh downstream
  evidence and personal adoption.
- Keep the mechanism generic: no queue, workflow-family, pilot, module, or
  repository-specific name may appear in production code or schemas.

### Non-Goals

- Treating owner adoption as repository mutation authority.
- Reusing the archived adoption for a newly captured baseline.
- Relaxing workspace-baseline, commit-predecessor, trailer, index, or protected
  path validation.
- Rewriting, reverting, amending, or otherwise normalizing unrelated commits.
- Adding a second Task 2 workspace-baseline authority.
- Changing the accepted six-failure normalization or ownership partition.
- Expanding into deferred hostile-environment or other security-only work.

## Decision

Add `attempt_migration_disposition.v2` as a lifecycle-specific successor while
retaining v1 byte-for-byte and behavior-for-behavior. Expose the new capture
through a distinct generic CLI operation rather than adding ambiguous defaults
to the v1 command.

The v2 disposition is valid only when all of the following are proven:

- its bound attestation is closed, owner-confirmed, and personally adopted;
- the attempt has no completion commit;
- the workspace-baseline recorded HEAD is an ancestor of the incident HEAD;
- the complete first-parent intervening commit/path projection is bound;
- at least one intervening path is not covered by a valid retirement-control
  trailer; and
- the existing commit-control selection rejects the recorded workspace
  baseline for the intended predecessor without changing any repository state.

After ordered reviews and a commit of the exact disposition, the shared mover
archives the enumerated attempt and restores the one tracked live ledger. A
post-move subject and ordered reviews then close the relocation. Task 2 starts
again from Step 1; none of the archived baseline, reviews, adoption, ledger
generations, or raw test results may satisfy the new attempt.

Alternatives rejected:

- **Broaden v1 in place:** changes the meaning of already committed historical
  evidence and makes its fixed claims unreliable.
- **One-off manual relocation:** duplicates replay and restoration logic and
  provides a weaker review surface.
- **Second workspace baseline or history rewrite:** violates the closed plan or
  mutates unrelated history.
- **Commit without the controller:** produces a boundary that cannot pass the
  roadmap's clone-reconstruction requirement.

The accepted tradeoff is two additional evidence schemas, one additional CLI
operation, and one further personal-adoption boundary in exchange for
preserving both historical truth and deterministic reconstruction.

## Design Details

### Frozen incident record

Before any failed-attempt file is relocated or restored, materialize a
canonical incident record outside the failed attempt root. The implementation
plan freezes the detection coordinates first, so the production builder can
reopen the historical Git objects even after corrective commits advance HEAD.
The incident binds:

- the governing and corrective-plan bytes;
- the recorded workspace-baseline bytes and its internal HEAD;
- the intended predecessor HEAD/tree at detection time;
- the complete first-parent intervening commit list;
- each intervening commit's exact changed-path projection and raw commit
  message digest;
- the subset covered by valid retirement-control trailers;
- the nonempty uncovered path set;
- the owner-confirmed attestation bytes;
- the exact current attempt-path projection; and
- the exact repository state captured before either incident or disposition
  publication, used as the frozen comparison source for incident-only crash
  recovery; and
- a claim that the incident proves only why the uncommitted attempt cannot be
  sealed.

Later corrective commits may advance HEAD, so the disposition binds this
frozen incident record rather than reinterpreting the original detection
coordinates. Ordinary incident validation continues to permit corrective
descendants. The stricter pre-publication repository-state equality is applied
only by capture replay after the exact incident exists and the disposition is
absent; that comparison removes exactly the proven incident-output addition
and never recaptures a replacement baseline.

### Successor disposition

`attempt_migration_disposition.v2` retains the v1 file, authority-review,
repository-state, protected-path, row-set, archive-set, ledger-lineage, and
normalized-digest contracts. It replaces the fixed pre-adoption policy with a
closed `attempt_lifecycle` object containing:

- `adoption_state = owner_adopted`;
- `repository_commit_state = uncommitted`;
- `invalidation_reason = workspace_baseline_predecessor_mismatch`;
- the incident-record binding;
- `workspace_baseline` and `attestation_record` artifact-role bindings; and
- a fixed statement that adoption is historical and non-transferable.

The artifact-role catalog is versioned. V1 continues to require its original
six roles, including `pending_record`. V2 requires the baseline and review
roles plus `workspace_baseline`, `attestation_request`,
`attestation_snapshot`, and `attestation_record`. The v2 validator requires
the record role to be owner-confirmed and requires its immutable snapshot role
to remain the original pending bytes; those two different lifecycle states are
expected and both remain content-addressed.

### Capture and validation

The new CLI operation accepts paths and bindings as data. It derives lifecycle
facts from the files and Git history; callers cannot supply booleans asserting
adoption, mismatch, or trailer coverage. Capture fails before publication on
any extra/missing attempt path, malformed owner record, changed incident
coordinate, ambiguous ancestry, covered-only predecessor delta, protected-path
drift, or ledger-restoration mismatch.

Validation dispatches strictly by schema version. V1 continues through the
unchanged v1 validator. V2 reopens the incident, attestation, workspace
baseline, reviews, Git objects, attempt rows, protected paths, and ledger
lineage. Unknown versions fail closed.

### Apply, replay, and postvalidation

Apply remains gated on an exact disposition and distinct ordered reviews that
are committed at HEAD. The common mover publishes each archive file
exclusively, verifies byte and mode equality, removes only enumerated untracked
sources, and atomically restores only the enumerated tracked ledger. Replay
accepts only the exact pre-state or exact completed post-state.

Postvalidation proves source/archive coverage in both directions, exact ledger
restoration, unchanged protected and outside-set projections, and the committed
review chain. Its versioned report records the disposition schema it consumed;
it does not claim that Task 2 is complete.

## Contracts And Interfaces

The implementation adds, without altering v1:

- schema `attempt_migration_incident.v1`;
- schema `attempt_migration_disposition.v2`;
- one distinct generic capture CLI operation for an owner-adopted,
  uncommitted, predecessor-invalidated attempt;
- schema-aware validation/apply/postvalidation dispatch; and
- fixtures for both valid lifecycle classes and invalid cross-class records.

No runtime, workflow, YAML, Workflow Lisp, provider, or public orchestrator
execution contract changes. These records are repository evidence and
operational migration authority only.

## Dependencies And Sequencing

1. Freeze the incident's detection coordinates and exact expected attempt path
   set in reviewed planning authority; do not relocate attempt files.
2. Implement v2 with TDD while preserving all v1 fixtures and behavior.
3. Run focused and broad verification.
4. Freeze a pre-relocation subject and obtain specification review followed by
   code-quality review over identical bytes.
5. Commit the design, implementation, tests, frozen detection-coordinate/path
   manifest, subject, and reviews without relocating the attempt.
6. From that landed implementation, capture the incident and exact v2
   disposition, obtain the same ordered review pair, and commit that authority
   before relocation.
7. Apply, postvalidate, review, and commit the archived result.
8. Restart Task 2 at Step 1 and continue the governing roadmap.

The seven pre-existing protected paths remain outside every allowed mutation
set. The intervening ordinary commit remains intact.

## Invariants And Failure Modes

- Owner adoption and controlled completion are separate state dimensions.
- An archived adoption never applies to different baseline bytes.
- V1 records retain their exact schema, claims, validation, and replay behavior.
- V2 accepts only an owner-confirmed attestation; pending or delegated-only
  forms fail closed.
- Incident ancestry and path coverage are derived from Git objects, not prose.
- A fully trailer-covered predecessor range is not eligible for this recovery;
  normal commit-control reconstruction must be used instead.
- Missing, extra, changed, non-regular, duplicated, or ambiguously placed files
  stop capture or apply.
- No move occurs before the exact disposition and both reviews are committed.
- Partial application is replayable only from exact recognized states.
- The restored ledger equals its committed generation-5 binding before a new
  attempt begins.
- Any protected or outside-set drift stops the operation.

## Operations And Performance

The operation is a one-time repository-local evidence migration. Work is
linear in the enumerated attempt files and intervening commits. It launches no
workflow and touches no run root. Storage temporarily retains both the archive
and the committed corrective evidence, which is intentional provenance.

## Evidence And Implementation Boundaries

The production path is the schema-dispatched capture/validate/apply/
postvalidate module, not a fixture, shell mover, or hand-authored JSON record.
The incident and disposition are evidence-only; neither changes runtime
behavior. Reviews must bind complete subject bytes, not prose summaries.

The old owner-confirmed attestation remains evidence that the owner adopted
that exact attempt. It is not evidence that the attempt passed its commit
boundary and is forbidden as an input to the restarted Task 2 attestation.

## Compatibility And Migration

Existing v1 callers, fixtures, committed dispositions, and archives remain
valid without regeneration. V2 is additive and selected only by its distinct
capture operation or explicit schema dispatch. There is no automatic v1-to-v2
conversion.

The restarted Task 2 uses the original evidence root only after v2 relocation
has removed the enumerated failed-attempt files and restored the live ledger.
It creates new immutable generations and reviews under the governing plan.

## Verification Strategy

- Collect changed test modules before execution.
- Prove all existing v1 tests and fixtures remain byte-compatible.
- Add positive v2 capture, validate, apply, replay, and postvalidate tests.
- Add negative lifecycle tests for pending attestation, owner/adoption mismatch,
  false completion-commit claim, incident tamper, ancestry mismatch, extra or
  missing intervening commit/path, fully covered predecessor paths, and
  cross-version field substitution.
- Retain both-direction source/archive coverage and ledger restoration tests.
- Run the retirement evidence/source-binding suites and the repository broad
  suite with the accepted known external failures compared, not repaired.
- Obtain ordered independent reviews over the exact implementation subject,
  again over the exact disposition, and a third time over the exact post-move
  subject.

No test may assert literal prompt prose.

## Declarative Acceptance Scenarios

### Owner-adopted attempt with an uncovered predecessor delta

Given an owner-confirmed attestation, an uncommitted attempt, a workspace
baseline whose HEAD is an ancestor of the intended predecessor, and at least
one intervening changed path not covered by a retirement-control trailer, the
v2 capture operation publishes one canonical disposition. After its committed
ordered reviews, apply archives every enumerated byte, restores only the live
ledger, and postvalidation proves exact coverage and protected-path equality.

### Invalid lifecycle substitution

Given the same repository state but a pending attestation, a v1 record relabeled
as v2, or a v2 record claiming pre-adoption, validation fails before any archive
or ledger mutation.

### Ordinary controlled predecessor chain

Given a workspace-baseline delta fully covered by valid retirement-control
trailers, v2 capture rejects the recovery. The normal commit-control path
remains authoritative.

## Success Criteria

- The frozen incident is canonical and independently reproducible.
- V1 behavior and committed historical evidence remain unchanged.
- V2 accepts the exact incident class and rejects both lifecycle directions.
- Focused and broad verification has fresh persisted output.
- Three ordered review pairs approve the implementation subject, exact
  disposition, and exact post-move subject respectively.
- Relocation and replay validate byte-for-byte.
- The live ledger equals committed generation 5 and all seven protected paths
  remain unchanged.
- A fresh Task 2 attempt begins from a workspace baseline captured at its real
  HEAD and uses none of the archived attempt as adoption or completion proof.

## Stop / Revise Criteria

Revise the design if implementation would require changing v1 semantics,
rewriting unrelated history, accepting a second Task 2 baseline, weakening the
commit controller, moving an unenumerated path, or reusing the archived owner
adoption. Stop if the exact incident cannot be reconstructed from repository
objects and content-addressed files.

## Documentation Impact

The implementation plan and evidence index must reference this corrective
design. The governing roadmap order does not change: Task 2 remains current
until the restarted controlled boundary commits, then Task 3 follows. No
machine selector or workflow-routing artifact changes.

## Implementation Handoff

Start with schema-dispatch and lifecycle RED tests in
`tests/test_retirement_attempt_migration.py`. Then implement the incident
builder/validator and v2 adapter using the existing no-follow capture, review,
move, replay, and restoration primitives. Keep family-specific coordinates in
the execution plan and evidence records, never in production code. Freeze and
review authority before applying any relocation.

## Open Questions

None. The owner approved the lifecycle-explicit successor, exact historical
preservation, ledger-only restoration, and fresh Task 2 restart on 2026-07-22.
