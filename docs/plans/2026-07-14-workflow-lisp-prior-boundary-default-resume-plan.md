# Workflow Lisp Prior-Boundary Default Resume Implementation Plan

**Status:** Tasks 1-4 are implemented, and Task 5's focused and broad
verification are fresh. Specification-compliance review first rejected a
pilot-plan staging contradiction and then rejected prior-boundary selection
that did not require global checkpoint-ID uniqueness. A subsequent quality
review rejected restore selection that trusted foreign empty-index identities,
noncanonical or symlinked record references, and unbound entry/record
identities. A later specification review rejected record IDs that could
introduce traversal while manufacturing their own helper-derived path. All
corrections are implemented. A later quality review rejected pathname reopen
that could follow a symlinked index parent or a final-record swap after
validation. Descriptor-relative no-follow reads correct both paths. Broad
reverification followed. A later quality review rejected blocking final opens
that could wait indefinitely when a canonical index or record path is replaced
by a FIFO. Required nonblocking final opens plus the existing regular-file
`fstat` gate correct both paths. Both verification tranches are fresh; the
ordered review sequence remains pending, and no approval is retained.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow eligible Workflow Lisp default resume to restore from one
uniquely identified, fully validated prior committed effect boundary when a
process stops after that boundary commits but before the next boundary emits a
checkpoint record, while preserving fail-closed behavior everywhere else.

**Architecture:** Keep node-local restore selection as the primary path. Only
when the restart node has checkpoint metadata and the restore layer positively
reports `record_absent` for that next boundary, derive the nearest preceding
effect-boundary checkpoint points from
the runtime plan's canonical `ordered_node_ids`. Exactly one nearest point whose
checkpoint ID occurs exactly once across all runtime-plan checkpoint points may
be retried by checkpoint ID through the existing restore selector; zero or
multiple nearest points, or any duplicate occurrence of the selected ID, fail
closed. An invalid, unsafe, or non-restorable prior point is never skipped in
favor of an older point. Root/callee checksum
preflight, program identity, source lineage, binding schema, completed-effect,
effect-policy, and authoritative-state validation remain unchanged.

**Tech Stack:** Python, immutable Workflow Lisp runtime plans, private lexical
checkpoint sidecars, pytest, existing default-resume and restore-selection
modules.

---

## Governing Contract

The durable contract belongs in the current Track R authority chain:
`docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
and its detailed source note
`docs/design/workflow_lisp_lexical_execution_checkpoints.md`. The normative
runtime statement belongs in `specs/state.md`. The active pilot recovery
sequence belongs in `docs/plans/2026-07-13-procedure-first-pilot-plan.md`.
`docs/design/workflow_lisp_lexical_checkpoint_resumability.md` remains a
predecessor draft and is not authority for this change. This implementation
plan owns only the generic prerequisite and its no-run verification.

The approved behavior is:

1. The node-local candidate remains authoritative when it restores, is
   invalid, or reports any unsafe/non-restorable diagnostic.
2. Prior-boundary selection is eligible only when the restart node has lexical
   checkpoint metadata and the restore layer positively establishes that no
   checkpoint record was emitted. A missing canonical index or a valid empty
   canonical index whose program-point and allocation identities match the
   runtime-plan point is `record_absent`; present but unreadable, malformed,
   incomplete, foreign, stale, or invalid indexes/records are not absence and
   fail closed.
3. Candidate ordering comes only from `runtime_plan.ordered_node_ids`; the
   nearest earlier execution index containing eligible effect-boundary points
   is the complete candidate set.
4. Exactly one candidate is required, and its checkpoint ID must occur exactly
   once across all `runtime_plan.lexical_checkpoint_points`, including older,
   later, and non-effect points. Missing, unordered, duplicated, or ambiguous
   candidates and globally duplicated selected IDs produce `FAIL_CLOSED`
   before checkpoint-ID restore selection.
5. The globally ID-unique point is passed back through
   `select_restore_candidate` by its checkpoint ID. The fallback does not
   duplicate or weaken any checkpoint,
   checksum, effect-policy, completed-effect, source-lineage, or authoritative-
   state validation.
   Index entries must reference the exact canonical workspace-relative record
   path derived from their record ID, point, and storage scope. A record ID is
   one safe filename component and cannot introduce path structure. The
   lexical path and normalized resolved path must remain direct children of the
   canonical and resolved record families respectively, below the resolved
   workspace; absolute, escaping, or symlinked references fail closed before
   record I/O. Entry identities must match the point and loaded record, and the
   loaded record plus restore payload must pass the existing complete
   validators.
   Both index and record JSON must be read from already-open descriptors beneath
   a trusted workspace directory descriptor. Parent and final opens are
   descriptor-relative and no-follow. The final open is also nonblocking, and
   `fstat` must identify a regular file so a FIFO or other nonregular target
   fails closed without waiting for a peer. Missing canonical index state is
   absence only on `FileNotFoundError`, while unavailable
   descriptor/no-follow/nonblocking support, invalid or symlinked parents,
   permissions, nonregular targets, and read-time mutation fail closed as
   present-unusable.
6. `RESTORED` continues from the original restart node while activating the
   validated prior restore payload. `INVALID` and `NOT_RESTORABLE` remain
   fail-closed. The implementation never searches farther back after the
   nearest point fails validation.
7. The mechanism and its tests contain no pilot, workflow-family, module, or
   procedure names.
8. The broader Track R phrase "previous consistent checkpoint or coarse
   boundary" does not authorize automatic best-effort scanning past a corrupt
   or invalid nearest checkpoint. This tranche automatically selects only the
   unique nearest point after positive next-record absence. Any older/coarser
   recovery remains an explicit future/operator path and is not silently
   selected by default resume.

## Frozen Evidence Constraint

Until both independent reviews approve and the prerequisite commit is bound by
an owner-adopted recovery authorization:

- do not write, delete, move, resume, or recreate anything below either
  `.orchestrate/runs` root;
- do not run the pilot live selector;
- do not create `clean_run.json` or `interruption_resume.json`;
- use compile-only, unit, no-run harness, collection, and retained read-only
  checks only.

### Task 1: Specify The Fail-Closed Prior-Boundary Contract

**Files:**

- Modify: `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- Modify: `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- Modify: `docs/design/README.md`
- Modify: `docs/index.md`
- Modify: `specs/state.md`
- Modify: `docs/plans/2026-07-13-procedure-first-pilot-plan.md`

- [x] **Step 1: Add the durable design rule**

Document node-local primacy, positive record-absence proof, unique-nearest
prior-boundary selection, canonical runtime-plan ordering, reuse of the full
existing validator, original restart-node continuation, and the prohibition on
automatically searching past an invalid or ambiguous candidate. Reconcile the
existing "previous consistent checkpoint or coarse boundary" prose so it
clearly describes an explicit/operator recovery tier rather than silent
default-resume best effort.

- [x] **Step 2: Add the normative state rule**

State that eligible default resume may use exactly one uniquely ordered prior
committed boundary only when the restore layer positively establishes that the
next boundary has no checkpoint record. It must fail closed for no candidate,
ambiguity, present-but-unreadable/malformed/incomplete state, validation
failure, or unsafe effect evidence.

- [x] **Step 3: Record the pilot recovery sequence**

Amend Task 3 without changing its strict post-plan-draft interruption point.
Record that the failed interrupted run remains unacceptable evidence, both
roots stay frozen through implementation and reviews, and only a later owner-
adopted authorization may delete and recreate exactly that interrupted ID.

### Task 2: Add Failing Generic Resume Tests

**Files:**

- Modify: `tests/test_workflow_lisp_lexical_checkpoint_restore.py`
- Modify: `tests/test_resume_command.py`

- [x] **Step 1: Write the valid-prior-boundary test**

Materialize a generic Workflow Lisp checkpoint fixture with a validated
completed effect-boundary record. Choose the following runtime node as the
restart node without creating its checkpoint record. Assert default resume
selects the prior checkpoint, reports `RESTORED`, retains the original restart
node, and exposes a prior-boundary selection reason.

- [x] **Step 2: Run the valid test and verify RED**

Run the exact new node ID with `pytest -q`. Expected: failure because default
resume currently evaluates only checkpoint points attached to the restart
node.

- [x] **Step 3: Write both-direction fail-closed tests**

Cover:

- no preceding eligible checkpoint point;
- multiple nearest preceding points at the same execution index;
- a unique prior point whose record is absent;
- a restart-node index or record that is present but unreadable, malformed, or
  incomplete, proving it is not treated as absence and the prior selector is
  never called;
- a unique prior point whose ordinary program/checkpoint validation fails;
- a node-local pending/unsafe record, proving fallback is not attempted; and
- a unique invalid nearest prior point with an older valid point, proving the
  implementation never searches past it;
- a selected unique-nearest point whose checkpoint ID is duplicated by an older
  point; and
- a selected unique-nearest point whose checkpoint ID is duplicated by a later
  non-effect point, proving both duplicates fail closed before checkpoint-ID
  restore selection;
- a valid empty canonical index versus empty indexes with foreign program-point
  or allocation identity, proving only the canonical index establishes
  `record_absent` and foreign identity blocks prior fallback;
- a canonical record reference versus absolute, parent-escaping, record-path
  symlink, and symlinked-parent references; and
- index-entry `record_id`, `program_point_id`, `point_kind`, and
  `frame_identity` mismatch against the point or loaded record; and
- a traversal-bearing record ID paired with the exact helper-derived traversal
  path and a valid crafted record, proving rejection occurs before crafted
  record I/O while a legitimate single-component non-derived ID remains valid;
- a canonical index reached through a symlinked parent, proving it is
  present-unusable rather than restored or absent; and
- a canonical record swapped to a symlink immediately before final open,
  proving no-follow descriptor open rejects the race rather than restoring;
- a canonical index path replaced by a FIFO, proving the selector returns
  present-unusable/index-unreadable without blocking; and
- a canonical record path replaced by a FIFO, proving the selector returns
  present-unusable/reference-invalid-or-unreadable without blocking.

Assert `FAIL_CLOSED`, stable typed diagnostics, and zero provider/command
execution where integration coverage reaches the resume entrypoint.

- [x] **Step 4: Run the negative tests and verify RED**

Run only the new selectors. Expected: at least the valid fallback and new
typed-diagnostic assertions fail for the missing behavior, while existing
node-local safety behavior stays green.

### Task 3: Implement The Minimal Generic Selector

**Files:**

- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`

- [x] **Step 1: Add pure candidate derivation**

First extend `RestoreDecision` with a typed selection observation sufficient to
distinguish `record_absent` from `record_present_unusable`. Return
`record_absent` only for a missing checkpoint index or a valid index with no
record entries. A present unreadable/malformed index, or a referenced record
that is unreadable/malformed/incomplete, must return `INVALID` with a stable
diagnostic.

Then add one private helper that maps checkpoint points to the canonical execution
indexes in `runtime_plan.ordered_node_ids`, selects the complete nearest prior
effect-boundary set, requires the selected checkpoint ID to occur exactly once
across all runtime-plan checkpoint points, and returns a typed
missing/ambiguous/duplicate result. Do not inspect workflow names, source paths,
presentation labels, or family metadata.

- [x] **Step 2: Integrate after node-local selection**

Invoke the helper only for node-local `NOT_RESTORABLE` whose typed selection
observation is exactly `record_absent`, at a restart node that owns checkpoint
metadata. For exactly one candidate, call the same restore selector again with
`checkpoint_id=<unique prior id>`. Preserve the original `restart_node_id`;
record the prior-boundary selection reason.

- [x] **Step 3: Preserve validation and fail-closed outcomes**

Return `FAIL_CLOSED` for missing/ambiguous candidates and for every non-
`RESTORED` result from the selected prior point. Propagate existing validator
diagnostics. Never try an older candidate.

- [x] **Step 4: Run the new narrow suite and verify GREEN**

Run the exact Task 2 selectors with `pytest -q`. Expected: all pass.

- [x] **Step 5: Run existing restore/default-resume regression modules**

```bash
pytest -q tests/test_workflow_lisp_lexical_checkpoint_restore.py tests/test_resume_command.py
```

Expected: pass with no new failure or warning.

### Task 4: Correct The Pilot Harness Without Executing It

**Files:**

- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `docs/workflow_lisp_route_readiness_registry.json`

- [x] **Step 1: Replace provider failure with abrupt post-commit interruption**

Keep the interruption immediately after the successful `plan.draft` provider
boundary. Wrap the executor's post-persist checkpoint hook so it first invokes
the production hook, verifies the committed draft record and completed-effect
reference exist, then raises a test-only `BaseException` that is not converted
into a failed provider result. Do not move the interruption to `plan.review`.

- [x] **Step 2: Update lifecycle and projection contracts**

The interrupted state must show successful provider roles through
`plan.draft`, no `plan.review` attempt, and a nonterminal process-interruption
state suitable for same-ID resume. The resumed attempt counts must show the
first three roles reused and the remaining roles executed once. Remove the old
`fail_once_role`/failed-provider assertions and vocabulary.

- [x] **Step 3: Add no-run guard tests for the interruption mechanism**

Exercise lifecycle validation and the hook wrapper without constructing a live
run root. Assert the hook delegates to production checkpoint persistence before
raising, triggers only once at the compiler-derived draft step identity, and
cannot target another boundary.

- [x] **Step 4: Run only no-run pilot selectors**

Run collection and the default/no-run selectors in
`tests/test_workflow_lisp_key_migrations.py`. Do not set
`ORCHESTRATOR_RUN_LIVE_TRACKED_PLAN_PILOT_EVIDENCE` and do not invoke the live
selector. Every command must explicitly remove a possibly inherited gate with
`env -u ORCHESTRATOR_RUN_LIVE_TRACKED_PLAN_PILOT_EVIDENCE`.

- [x] **Step 5: Reconcile temporary route readiness conservatively**

Retirement of the ordinary one-pass runtime selector was required to preserve
Task 3's exact-two-run protocol. The affected
`workflows.examples.design_plan_impl_review_stack_v2_call` registry entry is
therefore temporarily `leaf_compile_candidate` and retains only its existing
compile selector. Task 5 of
`docs/plans/2026-07-13-procedure-first-pilot-plan.md` owns replacement of stale
parity-target commands, addition of procedure-comparison evidence, and
restoration to `leaf_runtime_candidate` after run-bearing evidence passes.

### Task 5: Verify And Review Before Evidence Recovery

**Files:**

- Review all Task 1-4 files.

- [x] **Step 1: Prove root immutability**

Capture and compare full-tree digests and entry sets for both exact roots before
and after every verification tranche:

- `/home/ollie/Documents/agent-orchestration/.orchestrate/runs`
- `/home/ollie/Documents/agent-orchestration/.orchestrate/procedure-first-pilot-evidence/tracked-plan-phase/workspace/.orchestrate/runs`

Also bind the clean and interrupted `state.json` hashes. Require no legacy-root
change, no dedicated-root change, no third dedicated ID, and no temporary
orchestrator run root.

Fresh before/after bindings were unchanged:

- legacy root: 418108 entries,
  `sha256:0a4f6e4ce63731c7a219201356f78c1f1e015770e553a465531e7816f2cd40e8`;
- dedicated root: 68 entries,
  `sha256:89b9b47034b994be2a67e3fd151da4b2ae08d08671284ffd826eb5c6ac77957d`;
- clean `state.json`:
  `sha256:729ebd7b4670ee73b0f18fbd3566e2ea73e5e8f488ddf729212cbec77e34a73b`;
  and
- interrupted `state.json`:
  `sha256:938df00488f5b82e38bad867fc047e7bfa111b5c6c06816e050f9d5b3e6582cc`.

The same root entry sets, root digests, and clean/interrupted `state.json`
hashes remained unchanged after the final warning-clean FIFO broad rerun, and
no temporary orchestrator run root was created.

- [x] **Step 2: Run collection and focused suites**

```bash
env -u ORCHESTRATOR_RUN_LIVE_TRACKED_PLAN_PILOT_EVIDENCE pytest --collect-only -q tests/test_workflow_lisp_lexical_checkpoint_restore.py tests/test_resume_command.py tests/test_workflow_lisp_key_migrations.py
env -u ORCHESTRATOR_RUN_LIVE_TRACKED_PLAN_PILOT_EVIDENCE pytest -q tests/test_workflow_lisp_lexical_checkpoint_restore.py tests/test_resume_command.py
env -u ORCHESTRATOR_RUN_LIVE_TRACKED_PLAN_PILOT_EVIDENCE pytest -q tests/test_workflow_lisp_key_migrations.py
env -u ORCHESTRATOR_RUN_LIVE_TRACKED_PLAN_PILOT_EVIDENCE pytest -q tests/test_workflow_lisp_route_readiness.py::test_checked_in_registry_loads_and_validates tests/test_workflow_lisp_route_readiness.py::test_cli_route_readiness_check_valid_registry
```

Fresh results after the nonblocking final-open correction: 199 selectors were
collected; the generic restore/resume suites passed 151 tests; the key-migration
module passed 46 tests with 2 expected skips; and the two route-readiness
selectors passed. The live selector remained skipped.

- [x] **Step 3: Re-run the broad suite in tmux**

```bash
env -u ORCHESTRATOR_RUN_LIVE_TRACKED_PLAN_PILOT_EVIDENCE pytest -q -n 16 --dist=worksteal
```

Repository policy requires PASS except established unrelated failures that are
independently reproduced on an isolated clean `HEAD` and receive explicit
disposition; it does not require misreporting an attributed baseline failure as
a regression in this tranche. The final warning-clean FIFO broad output was 6
failed, 4352 passed, 13 skipped, and 0 warnings in 53.35 seconds. The same exact
six failures reproduced independently on isolated clean `HEAD` `54744aa5`, and
no route regression was present. This satisfies the attribution gate, not an
all-green claim.

The immediately preceding xdist broad run reported 8 failed, 4350 passed, and
13 skipped because two additional adjudicated-provider deadline selectors
failed. Both additional selectors passed in a fresh narrow rerun (2 passed in
0.42 seconds) and then passed again in the final broad run. They are classified
as transient xdist timing failures, not accepted baseline failures; only the
six independently reproduced failures receive baseline attribution.

- [ ] **Step 4: Obtain two independent reviews in order**

Record one deterministic hash of the complete intended code/doc/test diff.
First obtain a specification-compliance review against that hash, the approved
contract, and this plan. After approval, obtain a separate code-quality review
against the same hash. Any code, doc, or test change invalidates both approvals:
rerun affected verification, record a new hash, and restart both reviews in
order. Only the exact tree approved by both reviewers may proceed.

Review evidence: the first specification-compliance review rejected the prior
tree because Task 4 required the temporary compile-only registry downgrade but
Task 4 Step 5 permitted only the optional no-run test at its staging boundary.
After that contradiction was corrected, specification-compliance review also
rejected a selector that required uniqueness only within the nearest
effect-boundary set, because the selected checkpoint ID could be duplicated by
an older, later, or non-effect runtime-plan point. The selector, tests, normative
spec, and durable design wording now require that ID to occur exactly once
across all runtime-plan checkpoint points. After focused and broad
reverification, quality review then rejected index absence and record-reference
validation that trusted noncanonical identities and paths. The selector now
requires canonical index identity, canonical non-symlink record allocation,
bound entry/record identity, and the existing full validators. Focused and
broad reverification followed. A later specification review rejected the
remaining traversal gap where a record ID could introduce path structure and
make the helper return the authored escaping path. Record IDs are now safe
single components, and both lexical and normalized containment are enforced
before record I/O. Focused and broad reverification followed. A later quality
review rejected the remaining pathname check/open gap for index parents and
final record components. Both reads now walk from a trusted workspace
descriptor with descriptor-relative no-follow opens and decode from the
already-open final descriptor. Focused and broad reverification followed. A
later quality review rejected the remaining FIFO blocker: a blocking final open
could wait indefinitely before the regular-file check. Final opens now require
nonblocking support, and `fstat` rejects FIFOs and other nonregular targets
without waiting for a peer. Exact FIFO and full focused reverification are
fresh, and final warning-clean broad reverification is fresh. A new
deterministic hash and fresh ordered reviews remain pending. Both reviews remain
pending.

- [ ] **Step 5: Commit only reviewed prerequisite paths**

Use exact-file staging. Do not stage unrelated user changes, either run root,
or pilot evidence projections. Commit the generic runtime prerequisite,
contract docs, recovery-plan amendment, and corrected no-run harness.

- [ ] **Step 6: Stop at owner recovery authorization**

After the reviewed commit, create the bound machine-fact incident record at:

`docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/incidents/task-3-default-resume-not-restorable.json`

Then publish the exact owner-adoption form at:

`docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/task-3/interrupted-run-recovery-authorization.json`

Do not delete or recreate the interrupted run until that record exists with
matching hashes and genuine owner adoption. The authorization may permit one
deletion and recreation of only
`tracked-plan-phase-interrupted-new-id`, followed by exactly one same-ID resume;
it must preserve the clean run byte-for-byte and forbid a third run.
