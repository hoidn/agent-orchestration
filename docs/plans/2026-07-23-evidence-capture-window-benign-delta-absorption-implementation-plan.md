# Evidence-Capture Window And Benign Delta Absorption Implementation Plan

> **Execution:** Use subagent-driven development. Use test-driven development
> for every production change. Obtain specification review before code-quality
> review. Do not generate or mutate roadmap evidence until both reviews
> approve.

**Goal:** Implement the generic prospective controller extension in
`2026-07-23-evidence-capture-window-benign-delta-absorption-design.md`, use it
for the active YAML-retirement Task 3 capture, and leave completed Task 2 bytes
and meaning unchanged.

**Architecture:** Preserve `precommit_control.v1`. Add a closed
`evidence_capture_windows.v1` marker, an always-present closed
`evidence_capture_window_boundary.v1` authority, and a separate conditional
`committed_predecessor_delta_absorption.v1` authority. Reconstruct prior
controlled boundaries to retain occurrence-level absorption coverage; allow
current coverage only for the exact still-uncovered occurrence set when every
path is disjoint from the selected window's scope.

**Tradeoff:** The implementation intentionally makes overlapping edits,
incomplete scopes, ambiguous authorities, and unreconstructable prior controls
require a restart. It does not attempt a semantic merge or infer intent from a
commit subject.

## Governing Inputs

- `docs/plans/2026-07-23-evidence-capture-window-benign-delta-absorption-design.md`
- `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`
- `docs/plans/2026-07-22-yaml-retirement-task-2-commit-lineage-restart-design.md`
- `docs/plans/2026-07-22-yaml-retirement-task-2-commit-lineage-restart-implementation-plan.md`
- `orchestrator/retirement/source_bindings.py`
- `tests/test_retirement_source_bindings.py`

The Task 6 plan remains immutable. This plan is a prospective controller
prerequisite and does not change its task/queue semantics.

## Authorized Paths

Production implementation:

- Modify `orchestrator/retirement/source_bindings.py`
- Modify `orchestrator/retirement/__init__.py`
- Modify `tests/test_retirement_source_bindings.py`
- Modify `orchestrator/retirement/broad_evidence.py`
- Modify `tests/test_retirement_broad_evidence.py`
- Create
  `tests/fixtures/retirement_broad_evidence/implementation_verification_subject.capture_window.v2.json`
- Modify `tests/fixtures/retirement_broad_evidence/manifest.v1.json`

Reviewed design/plan evidence:

- Create
  `docs/plans/evidence/yaml-retirement/evidence-capture-window-benign-delta-absorption-design/specification-review.json`
- Create
  `docs/plans/evidence/yaml-retirement/evidence-capture-window-benign-delta-absorption-design/quality-review.json`
- Create
  `docs/plans/evidence/yaml-retirement/evidence-capture-window-benign-delta-absorption-implementation/specification-review.json`
- Create
  `docs/plans/evidence/yaml-retirement/evidence-capture-window-benign-delta-absorption-implementation/quality-review.json`
- Create
  `docs/plans/evidence/yaml-retirement/evidence-capture-window-benign-delta-absorption-design/provisional-window-disposition.json`

Live state and current Task 3 authority:

- Maintain ignored local state at `state/evidence-capture-windows.json`; never
  stage or force-add it
- Create the exact Task 3 window-boundary authority at
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-commits/task-03/evidence-capture-window-boundary.json`
- Create the exact Task 3 absorption authority beneath
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-commits/task-03/committed-predecessor-delta-absorption.json`

No completed Task 2 evidence/control path may change. Every pre-existing
fixture payload file remains byte-identical. The shared fixture manifest may
receive only the one additive v2 row plus mechanically recomputed count,
path-set, and row-set digests; this does not regenerate or reinterpret Task 2.

## Task 1: Review And Land The Design Contract

- [ ] Validate the bootstrap disposition, require its old row closed and its
  complete replacement uniquely open, and require the marker to use the exact
  compact sorted UTF-8-plus-LF byte grammar.
- [ ] Compute and record the exact SHA-256 of both proposed documents and the
  bootstrap disposition.
- [ ] Obtain an independent specification review of the design against the
  owner directive, existing source-binding controller, and immutable Task 6
  plan.
- [ ] Resolve every valid finding and repeat the complete specification review.
- [ ] Obtain an independent code/contract-quality review of the revised design
  and implementation plan.
- [ ] Resolve every valid finding and repeat both reviews in order if governing
  bytes change.
- [ ] Validate review bindings, JSON shape, document hashes, and the active
  marker.
- [ ] Commit only the two documents, bootstrap disposition, and their four
  review records using
  `ORC_CAPTURE_WINDOW_ACK=1`. Do not stage the marker or any Task 3 candidate.
- [ ] Record this consciously acknowledged planning commit as an uncovered
  predecessor delta to be consumed by the active Task 3 absorption authority.

## Task 2: Add Marker Lifecycle With TDD

### Step 1: Write RED tests

Cover:

- the exact closed top-level and row key sets;
- timezone-aware timestamps, lowercase commit IDs, normalized relative paths,
  row ordering, unique window IDs, and nonredundant scopes;
- explicit selection with zero, one, or several open windows;
- new-baseline and reusable-baseline opening;
- status-only close;
- wrong baseline/timestamp, duplicate IDs, closed selection, scope
  normalization failures, symlink/nonregular parents or targets, and
  concurrent-publish changes;
- CLI success/nonzero rejection for validate, open, and close.
- close rejection before a successful reconstructed postcommit boundary, for a
  non-HEAD/wrong-subject boundary, and for a missing, changed, nonintersecting,
  or wrong-window archive disposition.
- two open rows sharing one baseline with zero uncovered occurrences, proving
  a boundary for one row cannot close the other.
- a scope-intersecting lineage can be dispositioned and closed through exact
  ignored local archival state without granting coverage or making a successor
  attempt eligible.

Run:

```bash
pytest --collect-only -q tests/test_retirement_source_bindings.py
pytest -q tests/test_retirement_source_bindings.py \
  -k 'evidence_capture_window'
```

Require collection success and behavioral RED failures before production code.

### Step 2: Implement the minimum lifecycle

Add the closed validator, exact byte-grammar check, no-follow builders,
compare-before-publish writes, mechanically boundary-bound close operation,
always-present closed window-boundary builder, closed generic archive
disposition, public exports, and CLI operations. Do not add task, queue,
family, repository, owner, or evidence-kind branches.

The archive-disposition builder publishes only to a deterministic immutable
content-addressed generation beneath the ignored
`state/evidence-capture-window-dispositions/<window-id-sha256>/` directory,
rederives the exact intersecting lineage, and grants no successor baseline or
occurrence coverage. Test a HEAD race after publication: stale close rejects, a
new digest generation publishes without overwriting the old one, and fresh
close passes.

### Step 3: Turn the selector GREEN

Rerun the exact RED selector. Then run:

```bash
pytest -q tests/test_retirement_source_bindings.py \
  -k 'workspace_baseline or evidence_capture_window'
```

## Task 3: Add Occurrence-Level Absorption With TDD

### Step 1: Write RED builder/validator tests

Cover exact schema shape and canonical digest plus:

- one disjoint untrailed commit;
- multiple disjoint commits and paths;
- file deletion and file/gitlink transition;
- exact-scope, descendant-scope, and ancestor-scope rejection;
- missing authority with outstanding occurrences;
- stale authority with no outstanding occurrences;
- missing, extra, duplicate, reordered, or redigested occurrence rows;
- wrong marker binding/window/baseline/predecessor/tree/commit/path/digest;
- malformed lineage and control trailers;
- syntactically valid trailers with forged/unreconstructable coordinates;
- changed marker between build and validation.
- valid boundary derivation with zero uncovered commits and exact rejection of
  wrong window, baseline, predecessor, tree, scope digest, or commit subject.

Run:

```bash
pytest -q tests/test_retirement_source_bindings.py \
  -k 'committed_predecessor and absorption'
```

Require behavioral RED failures.

### Step 2: Implement the closed record

Add:

- the closed always-present `evidence_capture_window_boundary.v1` builder and
  validator;
- occurrence derivation from `lineage_projection.first_parent_commits`;
- symmetric normalized scope-intersection logic;
- closed record builder and issue-returning validator;
- public export and explicit CLI build operation; and
- both `evidence_capture_window_boundary.v1` and
  `committed_predecessor_delta_absorption.v1`, plus
  `implementation_verification_subject.v2`, in the durable-authority schema
  set.

The absorption builder derives every row. Its callers supply only repository
root, marker, window ID, intended predecessor, and output path. The boundary
builder additionally receives the exact prospective commit subject.

### Step 3: Add persistent prior coverage

Write RED tests for:

- a valid prior controlled absorption remaining covered;
- an authority present in a tree but absent from the reconstructed control;
- tampered or unreconstructable prior authority;
- a later untrailed change to the same path requiring a new occurrence; and
- mixed controlled, previously absorbed, and newly uncovered occurrences.

Implement private reconstruction of occurrence coverage only from exact prior
controlled durable-authority sets. Keep
`derive_committed_predecessor_lineage` output and completed Task 2 fixtures
payload files byte-compatible.

### Step 4: Turn the selector GREEN

Run:

```bash
pytest -q tests/test_retirement_source_bindings.py \
  -k 'committed_predecessor or absorption'
```

## Task 4: Integrate Without Changing `precommit_control.v1`

### Step 1: Write both-direction RED integration tests

Cover:

- an explicit matching window-boundary authority is required for every
  prospective control, including zero-uncovered lineage;
- disjoint outstanding occurrences plus one explicit absorption authority pass
  precommit validation;
- an intersection, missing authority, extra authority, or ambiguous authority
  fails;
- controlled-only lineage retains old behavior;
- semantic-index reconstruction uses exactly controlled plus absorbed paths;
- precommit, postcommit, and reconstruction produce the same control;
- reconstructed authorities rederive the embedded marker snapshot and binding
  without requiring ignored live state;
- valid-looking but unreconstructable prior control coordinates fail before
  path partitioning;
- prior coverage persists at the next controlled boundary;
- an uncommitted or staged path is never absorbed;
- historical Task 2 controls and fixtures still validate unchanged;
- v1 implementation subjects build and validate byte-for-byte unchanged;
- pure no-boundary v1 construction, validation, and review reopening remains
  compatible, but explicit capture-mode precommit rejects a v1-only
  subject/review set for prospective Tasks 3–6;
- explicit boundary plus nonempty absorption builds a v2 subject whose exact
  authority bindings are required in both the new field and candidate
  manifest;
- a zero-uncovered v2 subject requires boundary plus null absorption; and
- missing, extra, wrong-schema, wrong-window, tampered, or manifest-omitted v2
  authority bindings reject, including review-subject reopening;
- every v2 manifest row must be equal to or descended from the selected scope;
  one outside-scope candidate/evidence row rejects, an in-scope descendant
  passes, and an unused conservative scope row is permitted;
- every prospective allowed path is covered by the selected boundary scope at
  build, precommit, postcommit, and reconstruction; an outside-scope allowed
  path rejects even when staged and reviewed; and
- v2 subjects are discovered as durable authorities during commit
  reconstruction, while omission of v2 from the durable schema set rejects;
- capture mode requires exactly one v2 subject plus its ordered approved
  reviews and deep-joins its boundary/nullable-absorption bindings to the
  explicit controller authorities; missing, multiple, v1-only, or mismatched
  authority sets reject in the applicable live or committed-blob mode;
- live build/precommit runs the existing full candidate-state review-pair
  validation, while postcommit/fresh reconstruction validates the exact
  committed subject/review blobs, closed schemas and digests, review
  identity/result/order/subject-pointer contract, and v2 authority joins
  without requiring the former live index or dirty worktree; and
- fresh-clone committed-blob reconstruction succeeds, while tampered committed
  subject, review, review order/result/subject pointer, or authority binding
  rejects.

### Step 2: Add the explicit controller input

Add explicit prospective `capture_window_boundary` plus optional
`predecessor_delta_absorption` inputs to `build_precommit_control` and matching
CLI flags. Infer nothing from arbitrary files. Revalidate the selected
authorities at build, precommit validation, postcommit validation, and
reconstruction. Historical calls without a boundary retain their old behavior
but cannot close a prospective window.

Do not add a field to `precommit_control.v1`.

Add `implementation_verification_subject.v2` as the closed additive
capture-bearing review subject. Keep the v1 builder/validator output unchanged
when no boundary path is supplied. Extend generic `implementation_candidate`
review reopening to accept either schema. In explicit capture mode, require
Task 3 to supply exactly one v2 subject and ordered review pair whose authority
bindings equal its exact boundary and absorption paths. Apply the same
controller discriminator to every prospective capture-bearing Task 4–6
implementation candidate even though the immutable plan's v1-only wording
remains unchanged.

Keep the validation modes explicit. Build/live-precommit mode runs the full
live candidate review-pair validator before the v2 authority joins.
Postcommit/fresh-reconstruction mode reopens only the exact committed durable
subject and review blobs, validates their closed bindings and ordered approved
review relationship, validates the v2 authority joins, and relies on the
existing reconstructed parent/tree/allowed-delta/control checks for candidate
truth. It must not call a validator that requires the precommit index or dirty
worktree after the commit has landed.

### Step 3: Run focused and compatibility checks

```bash
pytest -q tests/test_retirement_source_bindings.py \
  -k 'precommit or workspace_baseline or committed_predecessor or absorption or evidence_capture_window'
pytest --collect-only -q tests/test_retirement_broad_evidence.py
pytest -q tests/test_retirement_broad_evidence.py \
  -k 'implementation_verification_subject and capture_window'
pytest -q -n 16 --dist=worksteal tests/test_retirement_broad_evidence.py
```

## Task 5: Independent Implementation Reviews

- [ ] Freeze the exact candidate path set and diff.
- [ ] Run `python -m compileall -q orchestrator tests`.
- [ ] Run the complete owning module:

```bash
pytest -q -n 16 --dist=worksteal tests/test_retirement_source_bindings.py
pytest -q -n 16 --dist=worksteal tests/test_retirement_broad_evidence.py
```

- [ ] Obtain independent specification review against the approved design and
  this plan.
- [ ] Resolve valid findings using TDD and repeat the full specification review.
- [ ] Obtain independent code-quality review.
- [ ] Resolve valid findings using TDD and repeat both reviews in order after
  any production/test change.
- [ ] Confirm the implementation contains no workflow-family, queue,
  repository, batch, owner, or Task 3 branch.
- [ ] Confirm completed Task 2 evidence/control bytes and every pre-existing
  fixture payload are unchanged; require the manifest delta to be exactly the
  additive v2 row and mechanically derived aggregate fields.

No roadmap evidence generation is allowed before both reviews approve.

## Task 6: Consume The Mechanism In The Active Task 3 Attempt

- [ ] Revalidate `state/evidence-capture-windows.json` and require the selected
  replacement Task 3 row to be uniquely open, complete for every authorized
  controller/Task 3 candidate path, and bound to the live workspace baseline.
- [ ] Derive the current predecessor lineage and materialize exactly one
  Task 3 absorption authority for the still-uncovered disjoint occurrences.
- [ ] Materialize exactly one
  `implementation-commits/task-03/evidence-capture-window-boundary.json`
  matching the selected replacement row, current predecessor/tree, scope, and
  final Task 3 commit subject.
- [ ] Require all current planning/concurrent paths to be disjoint from the
  selected scope. If any intersects, disposition/restart Task 3; do not weaken
  the scope.
- [ ] Include exactly
  `implementation-commits/task-03/evidence-capture-window-boundary.json` and
  `implementation-commits/task-03/committed-predecessor-delta-absorption.json`,
  but not the ignored open marker, in Task 3's fixed evidence manifest,
  subject, exact allowed candidate, and durable-authority sets. Extend the
  candidate manifest by exactly the generic controller implementation and
  owning-test paths authorized above.
- [ ] Build Task 3's implementation review subject as
  `implementation_verification_subject.v2`; require its explicit authority
  field and candidate manifest to bind the same exact boundary and absorption
  bytes before either ordered implementation review.
- [ ] Resume Task 3 focused/broad evidence, correction adoption, subject,
  ordered reviews, ledger advance, and controlled commit under its governing
  plan.
- [ ] Run postcommit validation and fresh reconstruction before changing the
  live marker.
- [ ] Invoke the boundary-bound close command; close only the selected
  replacement row after it independently reconstructs and passes the complete
  Task 3 postcommit boundary.

## Task 7: Broad Verification

Use the tmux skill and run:

```bash
pytest -q -n 16 --dist=worksteal
```

Compare the result through the adopted broad-failure comparison contract. A
new, changed, or unexplained missing failure is not absorbed by this controller
design.

## Completion Contract

This plan is complete only when:

1. both documents and both ordered document-review pairs are committed;
2. marker lifecycle and absorption behavior pass both-direction tests;
3. `precommit_control.v1` shape and historical Task 2 evidence remain
   unchanged;
4. the complete controller-and-v2-subject implementation, fixtures, tests, and
   diff pass ordered specification and quality reviews;
5. the active Task 3 predecessor delta is represented by one exact disjoint
   occurrence-level authority;
6. Task 3's controlled boundary validates before and after commit and
   reconstructs without local control bytes; and
7. the selected marker row is closed only after that success.
