# YAML-Retirement Task 2 Commit-Lineage Restart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the exact owner-adopted but uncommitted Task 2 attempt, restore its live ledger, restart Task 2 from a commit-aligned workspace baseline, and land the controlled owner-confirmed boundary without weakening existing evidence contracts.

**Architecture:** Add a read-only generic predecessor-lineage projection and two additive evidence schemas: `attempt_migration_incident.v1` and `attempt_migration_disposition.v2`. Reuse the existing reviewed archive/replay/restoration engine through strict schema dispatch, leave `attempt_migration_disposition.v1` unchanged, and execute the same three-stage authority pattern used by the prior repair: reviewed implementation authority, reviewed exact disposition, then reviewed post-move evidence. For post-archive v2 validation, derive a transient original-logical-path byte overlay from the exact disposition rows so the full nested evidence graph is revalidated without adding a proof artifact or changing either schema.

**Tech Stack:** Python 3.11, Git plumbing, canonical JSON/SHA-256 evidence, pytest 8.4.1, pytest-xdist, tmux, existing `orchestrator.retirement` source-binding/review/migration helpers.

---

## Governing Inputs And Fixed Coordinates

- Accepted design:
  `docs/plans/2026-07-22-yaml-retirement-task-2-commit-lineage-restart-design.md`
- Governing execution plan:
  `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`
- Prior lifecycle-repair plan:
  `docs/plans/2026-07-22-yaml-retirement-task-2-attestation-lifecycle-repair-plan.md`
- Failed-attempt source root:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate`
- Corrective evidence root:
  `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart`
- Archive root:
  `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/failed-attempt`
- Recorded workspace-baseline HEAD:
  `4020f31a87ac216c01c211c751bbbd230cec5fc2`
- Ledger-restoration commit/tree:
  `4020f31a87ac216c01c211c751bbbd230cec5fc2` /
  `356e03e74608f10bfc49e8b418da1426ac4dd98a`
- Intended Task 2 commit predecessor at incident detection:
  `db2107526a7000c6ea9e8e4041e8d786ff624e79`
- Intended predecessor tree:
  `5103b9a21086917b8f64c2e114c4fbecc71f40f2`
- Intervening ordinary commit/path:
  `db2107526a7000c6ea9e8e4041e8d786ff624e79` / `README.md`
- Owner-confirmed live attestation before archive:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/attestations/pre-implementation/broad-failure-baseline.json`
- Original pending attestation snapshot SHA-256:
  `b5c446870bf6a82ee947698dc9537ddc0feeb71d4faa5b1dbf30695c66e1d0d6`
- Owner-confirmed attestation SHA-256:
  `40be14ce3f86584708030cfcf4ed5c393f7ee0ef60dc8417ddd3db587b930aff`
- Generation-5 restoration request:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/materialization-inputs/64244bcaccf8eda9910c5f0687530e84195269a15a2f86601adb21b5a9f8a7ac/00000005-fe7fcf17ad8016517ef53db5acd458b5520aa11274c049e33253ea6230f3ad53.json`
- Generation-5 restoration snapshot:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/immutable-outputs/64244bcaccf8eda9910c5f0687530e84195269a15a2f86601adb21b5a9f8a7ac/00000005-19ed4c66ec8d5ae08583325c2e4acc416b3b3b9bc8b465957835599287f76e4a.json`
- Failed generation-11 request:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/materialization-inputs/64244bcaccf8eda9910c5f0687530e84195269a15a2f86601adb21b5a9f8a7ac/00000011-7661806388f7e9ee6d7fc8d783a754fb767e5df13782f5777a1c17c20fd753d9.json`
- Failed generation-11 snapshot:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/immutable-outputs/64244bcaccf8eda9910c5f0687530e84195269a15a2f86601adb21b5a9f8a7ac/00000011-56ff869dfdc207026b51938cab00c33a7bbc990eed17da6dcbf6e39778ca4fe1.json`
- Additional ambient protected path observed before Task 5:
  `docs/reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md`

The seven protected paths named by the governing Task 2 Step 1 and the exact
additional ambient report above remain immutable through every task. Together
they are the eight protected paths for this plan. Run all Git commands with
`--no-optional-locks` where Git supports it. Do not create a worktree. Do not
add security-only tests or work.

### Task 1: Freeze Detection Authority And Write RED Lineage Tests

**Files:**
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/pre-relocation/expected-attempt-paths.txt`
- Modify: `tests/test_retirement_source_bindings.py`
- Modify: `tests/test_retirement_attempt_migration.py`

- [ ] **Step 1: Record the exact failed-attempt path manifest**

Create the LF-terminated sorted manifest from the current NUL-safe porcelain
projection beneath the failed-attempt source root. Require exactly 34 regular
files: one modified tracked live ledger and 33 untracked files. Compare the
result in both directions to Git status before saving it. The new plan/design
paths and all eight protected paths are outside this manifest.

- [ ] **Step 2: Write RED predecessor-lineage projection tests**

Add tests for a public read-only helper with this contract:

```python
projection = derive_committed_predecessor_lineage(
    repository_root,
    baseline_head=baseline_head,
    intended_predecessor_head=predecessor_head,
)
```

The positive fixture has one ordinary intervening commit and returns canonical
first-parent commit rows, exact changed paths, trailer coordinates where
present, `controlled_paths`, and a nonempty `uncovered_paths`. Add failures for
non-ancestor heads, merge/ambiguous lineage, malformed control trailers,
duplicate path projection, missing Git object, and an empty uncovered set when
the caller requires an invalidating gap.

- [ ] **Step 3: Write RED incident-schema tests**

Add tests for `attempt_migration_incident.v1` covering:

- owner-confirmed attestation accepted;
- pending attestation rejected;
- owner/adoption identity mismatch rejected;
- workspace baseline and intended predecessor mismatch captured exactly;
- candidate HEAD in the bound failure baseline equals the intended predecessor;
- path manifest and owner-attestation byte digests reopened;
- pre-publication repository state captured in the incident for deterministic
  incident-only crash recovery;
- uncovered predecessor paths required;
- fully controlled predecessor range rejected;
- incident digest, commit row, path set, raw-message digest, and nested type
  tamper rejected; and
- corrective commits after the intended predecessor allowed only when that
  predecessor remains an ancestor and attempt bytes remain unchanged.

- [ ] **Step 4: Collect and run the RED selectors**

```bash
pytest --collect-only -q \
  tests/test_retirement_source_bindings.py \
  tests/test_retirement_attempt_migration.py
pytest -q tests/test_retirement_source_bindings.py \
  -k 'committed_predecessor_lineage'
pytest -q tests/test_retirement_attempt_migration.py \
  -k 'incident_v1 or invalidated_adopted'
```

Expected: collection succeeds; the new selectors fail because the helper,
schema, and capture operation do not exist.

### Task 2: Implement The Generic Incident Projection And Record

**Files:**
- Modify: `orchestrator/retirement/source_bindings.py`
- Modify: `orchestrator/retirement/attempt_migration.py`
- Modify: `orchestrator/retirement/__init__.py`
- Test: `tests/test_retirement_source_bindings.py`
- Test: `tests/test_retirement_attempt_migration.py`

- [ ] **Step 1: Implement the read-only predecessor projection**

Add `derive_committed_predecessor_lineage` to `source_bindings.py`. Reuse the
existing raw commit-message/trailer parser and NUL-safe Git path decoding. The
helper must not write a control, index, worktree file, or repository record.
Return one closed canonical mapping with:

```text
baseline_head
intended_predecessor_head
intended_predecessor_tree
first_parent_commits
commit_count
changed_paths
changed_path_count
changed_path_set_sha256
controlled_paths
controlled_path_set_sha256
uncovered_paths
uncovered_path_set_sha256
normalized_projection_sha256
```

Each commit row binds commit, parent, tree, raw-message SHA-256, sorted changed
paths, path-set digest, and either null control coordinates or the exact parsed
transaction/control digest. Reject merge topology rather than guessing which
parent supplied the workspace state.

- [ ] **Step 2: Implement the closed incident builder and validator**

In `attempt_migration.py`, add version-specific constants and pure builder /
validator functions for `attempt_migration_incident.v1`. The builder receives
paths and the intended predecessor as data, derives adoption and lineage facts,
and returns canonical data. The publisher uses existing exclusive no-follow
publication. No caller may supply adoption booleans, path counts, or lineage
digests.

The incident must bind the accepted design, this implementation plan, workspace
baseline, owner-confirmed attestation, its pending snapshot, known-failure
baseline, expected path manifest, and derived predecessor projection. Its
claims state only why the uncommitted attempt cannot be sealed. It also binds
the exact repository state observed before publication. The general incident
validator treats that state as historical so later corrective descendants
remain valid; the capture replay path consumes it as the frozen comparison
source for the incident-only crash prefix.

- [ ] **Step 3: Export only the stable read/validate surface**

Export the public lineage projection and incident validator from
`orchestrator.retirement` only if current package conventions export comparable
evidence helpers. Keep capture/apply policy in `attempt_migration.py`.

- [ ] **Step 4: Run the Task 1 selectors GREEN**

Run the three commands from Task 1 Step 4. Expected: all selected tests pass.

- [ ] **Step 5: Run adjacent source-binding regression tests**

```bash
pytest -q tests/test_retirement_source_bindings.py \
  -k 'precommit or workspace_baseline or committed_predecessor_lineage'
```

Expected: pass with no change to `precommit_control.v1` construction or
validation behavior.

### Task 3: Add Disposition V2 Without Changing V1

**Files:**
- Modify: `orchestrator/retirement/attempt_migration.py`
- Modify: `tests/test_retirement_attempt_migration.py`

- [ ] **Step 1: Write RED v2 capture and schema-dispatch tests**

Add a synthetic owner-adopted repository fixture and tests for:

- `capture-invalidated-adopted` publishing one incident plus one v2
  disposition;
- exact replay after a crash between incident and disposition publication;
- rejection when an existing incident differs by one byte;
- strict dispatch for v1, v2, and unknown versions;
- v1 constants, claims, artifact roles, canonical bytes, validation, and CLI
  behavior unchanged; and
- cross-version field substitution rejected in both directions.

Run:

```bash
pytest -q tests/test_retirement_attempt_migration.py \
  -k 'disposition_v2 or invalidated_adopted or v1_compatibility'
```

Expected: fail before implementation.

- [ ] **Step 2: Implement the lifecycle-explicit v2 schema**

Add `attempt_migration_disposition.v2` with the v1 common migration fields plus
one exact `attempt_lifecycle` object:

```json
{
  "adoption_state": "owner_adopted",
  "repository_commit_state": "uncommitted",
  "invalidation_reason": "workspace_baseline_predecessor_mismatch",
  "incident_binding": {"path": "...", "size": 0, "sha256": "sha256:..."},
  "workspace_baseline_role": "workspace_baseline",
  "owner_attestation_role": "attestation_record",
  "adoption_transfer": "forbidden"
}
```

Use a versioned artifact-role catalog. V1 retains its original six roles.
V2 requires `baseline`, both baseline reviews, `workspace_baseline`,
`attestation_request`, `attestation_snapshot`, and `attestation_record`.
Require the snapshot to be pending, the record to be owner-confirmed, and the
record's four-field reversal to reproduce the snapshot bytes exactly.

- [ ] **Step 3: Add the distinct capture operation**

Add `capture-invalidated-adopted` to the existing CLI. It accepts exact paths,
the intended predecessor, source/archive roots, authority subject/reviews,
restoration commit/tree, generation-5/generation-11 coordinates, manifest,
protected paths, baseline/reviews, workspace baseline, and attestation
request/snapshot/record. It derives and exclusively publishes the incident,
then the disposition. Capture the pre-move repository state before publishing
either output and bind that same state into both records. On exact replay, an
already-published byte-identical incident is
the sole permitted output-path addition and is excluded from the pre-move
outside-status comparison; it is never reclassified as a protected path.
Exact replay returns the same records; a partial or different replay fails
closed, except for the one explicitly recoverable crash state: the exact
byte-identical incident is present and the disposition is absent. In that state
the operation revalidates the incident and its bound frozen pre-move projection
after removing exactly the proven incident-output addition, then
publishes only the deterministic disposition. Every other partial state, or
any differing existing byte, fails closed. Recomputing a new baseline from the
retry workspace is forbidden.

- [ ] **Step 4: Implement strict version dispatch**

Split `_validate_disposition_structure` into a small dispatcher plus separate
v1 and v2 validators. Do not edit v1 constants or accepted key sets. Make
`_load_disposition`, live-binding validation, review gating, `apply`, and
`postvalidate` consume only the schema-specific validated projection.

- [ ] **Step 5: Run v2 and complete v1 tests GREEN**

```bash
pytest -q tests/test_retirement_attempt_migration.py \
  -k 'disposition_v2 or invalidated_adopted or v1_compatibility'
pytest -q tests/test_retirement_attempt_migration.py
```

Expected: pass.

### Task 4: Prove Apply, Replay, Postvalidation, And CLI Behavior

**Files:**
- Modify: `orchestrator/retirement/attempt_migration.py`
- Modify: `tests/test_retirement_attempt_migration.py`
- Modify: `docs/index.md`

- [ ] **Step 1: Write RED v2 mutation-boundary tests**

Cover both directions for:

- exact pre-state apply succeeds;
- exact post-state replay succeeds;
- partial source/archive state rejects;
- uncommitted disposition or either uncommitted review rejects;
- wrong review order, reviewer identity reuse, subject kind, path, or SHA
  rejects;
- changed owner attestation, incident, protected path, outside status, ledger,
  archive destination, or restoration commit rejects before mutation;
- a completed post-state revalidates the owner attestation, pending snapshot,
  known-failure baseline, broad outcome and raw evidence, ordered reviews, and
  materialization ancestry through the archived logical bytes;
- an adversarial nested broad-evidence defect still rejects after its file-row,
  incident, and disposition bindings and normalized digests are coherently
  rebound, proving that row integrity does not substitute for graph semantics;
- missing, swapped, duplicated, noncontiguous, or wrong-parent
  materialization request/snapshot slots reject through the same logical view;
- candidate identity, repository-status, and ancestry defects remain live Git
  failures, with only the exact existing historical candidate-drift tolerance;
- only the one enumerated tracked ledger may be restored; and
- postvalidation binds the consumed disposition schema and makes no Task 2
  completion claim.

- [ ] **Step 2: Implement shared apply/postvalidation adapters**

Normalize v1 and v2 only after their separate closed validators succeed. Feed
the common byte/mode rows and restoration binding to the existing move/replay
engine. Retain `attempt_migration_post_report.v1` unchanged: its exact
`disposition_binding` already content-addresses the consumed record, and
postvalidation must reopen that binding and validate its v1 or v2 schema before
publishing the report. Add no optional report fields.

For v2, construct the logical-path overlay only after the disposition row set
and replay state validate. Project each unique `original_path` to the exact
resolved row bytes; mapped originals shadow live or restored bytes and never
fall back, while an unmapped path may use a live read only when it is a regular
file in `HEAD` and its current bytes equal that `HEAD` blob. Thread that same
read-only overlay through bound-file reopening, recursive broad record
validation, review subjects and immutable review bytes, ledger completion
handoffs, and materialization generation/ancestry validation. Keep candidate
and Git-derived checks on the real repository and preserve the existing exact
historical-drift filter without adding new tolerated issue classes. The
overlay is transient: do not persist a proof record, add an artifact role, or
revise either closed schema.

- [ ] **Step 3: Test the public CLI end to end**

Extend the existing subprocess CLI smoke to cover capture-invalidated-adopted,
validate, apply, replay, and postvalidate using real Git commits and review
files. Do not call private helpers in this acceptance test.

- [ ] **Step 4: Update documentation routing**

Add the accepted corrective design and this plan to `docs/index.md` adjacent to
the YAML-retirement plan. State that they correct an owner-adopted uncommitted
Task 2 attempt and do not alter roadmap ordering.

- [ ] **Step 5: Run collection and the complete migration module**

```bash
pytest --collect-only -q \
  tests/test_retirement_attempt_migration.py \
  tests/test_retirement_source_bindings.py
pytest -q tests/test_retirement_attempt_migration.py
pytest -q tests/test_retirement_source_bindings.py \
  -k 'committed_predecessor_lineage or precommit or workspace_baseline'
```

Expected: collection and all selectors pass.

### Task 5: Build And Commit Reviewed Pre-Relocation Authority

**Files:**
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/pre-relocation/candidate-manifest.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/pre-relocation/exact-diff.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/pre-relocation/focused-test-evidence.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/pre-relocation/broad-test-evidence.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/pre-relocation/subject.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/pre-relocation/specification-review.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/pre-relocation/quality-review.json`

- [ ] **Step 1: Run focused verification and persist exact evidence**

Run and bind exact argv, cwd, environment, output, exit, duration, and tested
file digests for:

```bash
pytest --collect-only -q tests/test_retirement_attempt_migration.py tests/test_retirement_source_bindings.py
pytest -q tests/test_retirement_attempt_migration.py
pytest -q tests/test_retirement_source_bindings.py tests/test_retirement_broad_evidence.py
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k yaml_retirement_handoff
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py -k yaml_retirement
```

Require the two handoff/triage diffs, cached and unstaged, to remain empty.

- [ ] **Step 2: Run the broad suite in tmux**

Use the tmux skill and session `yaml-retirement-task2-lineage-restart`:

```bash
pytest -q -n 16 --dist=worksteal
```

Persist the log and exit. Compare failures against the personally adopted
six-row baseline by its normalized failure signatures. Accept only the same
six external failures, zero new errors, and zero new queue-owned failures.
Do not repair external failures.

- [ ] **Step 3: Freeze the implementation authority subject**

Build the v1 authority subject using the existing closed schema. Bind the
governing plan, accepted design, this plan, exact 34-path manifest, all eight
protected bindings, changed mechanism/test files, complete candidate manifest,
exact diff, and focused/broad evidence. Require no failed-attempt source byte to
change from the manifest snapshot.

- [ ] **Step 4: Obtain ordered independent reviews**

Dispatch specification review first. After approval, dispatch a different
agent for code-quality review over the identical subject SHA. A correction to
code, tests, evidence, manifest, or subject invalidates both reviews.

- [ ] **Step 5: Commit only pre-relocation authority**

Stage only the design/plan-routing, production code, tests, expected manifest,
test evidence, subject, and both reviews. Require the cached path set to exclude
the failed-attempt root and eight protected paths. Commit with subject:

```text
Add adopted-attempt lineage restart authority
```

Verify the commit's exact path set and byte bindings from HEAD before Task 6.

### Task 6: Capture, Review, And Commit The Exact V2 Disposition

**Files:**
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/incident.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/failed-attempt-disposition.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/failed-attempt-disposition-specification-review.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/failed-attempt-disposition-quality-review.json`

- [ ] **Step 1: Revalidate the unchanged attempt and protected set**

Require current status beneath the failed-attempt root to equal the 34-path
manifest, every byte/mode to match, the owner-confirmed attestation SHA to equal
`40be14ce...`, and every protected path to match its pre-relocation subject.

- [ ] **Step 2: Capture the incident and disposition once**

Invoke `capture-invalidated-adopted` with the fixed coordinates above, the
fixed `4020f31a...` / `356e03e...` generation-5 restoration commit/tree, all
eight protected paths, and the exact review/manifest/evidence paths. The Task 5
authority commit is the required current ancestor containing the reviewed
mechanism, but it intentionally still has the generation-11 live ledger.
Require:

- incident predecessor projection has one uncovered path, `README.md`;
- disposition has 34 sorted rows, one modified tracked row, and 33 untracked
  rows;
- its attestation is owner-confirmed while its immutable snapshot is pending;
- its restoration bytes equal the committed generation-5 snapshot and live
  ledger at the fixed `4020f31a...` restoration commit; and
- validation and exact replay return success without mutation.

- [ ] **Step 3: Obtain ordered disposition reviews**

Review the exact incident and disposition bytes, row/path digests, adoption
lifecycle, predecessor proof, restoration binding, protected bindings, and
authority chain. Specification review precedes code-quality review by a
different agent. Both use subject kind `attempt_migration_disposition` and bind
the exact v2 disposition path/SHA.

- [ ] **Step 4: Commit the disposition authority before applying it**

Commit only the incident, disposition, and two reviews with subject:

```text
Authorize adopted Task 2 attempt archival
```

Reopen each committed blob at HEAD and rerun `validate`. No source/archive
relocation is legal before this commit.

### Task 7: Apply The Reviewed Move And Close Post-Move Evidence

**Files:**
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/failed-attempt/**`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/failed-attempt-post-report.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/post-relocation/exact-diff.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/post-relocation/subject.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/post-relocation/specification-review.json`
- Create: `docs/plans/evidence/yaml-retirement/task-2-commit-lineage-restart/post-relocation/quality-review.json`
- Verify unchanged against HEAD: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`
- Delete: only the 33 untracked failed-attempt paths enumerated by the disposition

- [ ] **Step 1: Apply the exact committed disposition**

Run `apply` with the committed disposition and reviews. Require 34 byte-identical
archive files, absence of all 33 untracked originals, and restoration of the
tracked live ledger to generation-5 SHA
`19ed4c66ec8d5ae08583325c2e4acc416b3b3b9bc8b465957835599287f76e4a`.

- [ ] **Step 2: Prove replay and postvalidate**

Run `apply` a second time and require exact no-op success. Run `postvalidate`
and persist its canonical report. Verify archive/source coverage in both
directions, unchanged v1 archive bytes, exact index classification, protected
path equality, and unchanged outside-status projection.

- [ ] **Step 3: Freeze the post-move subject**

Bind the exact disposition/reviews, post-report, archive inventory, restoration
equivalence, replay result, exact diff, protected bindings, outside-status
equality, and result manifest. State explicitly that this closes only the
relocation and does not complete Task 2.

- [ ] **Step 4: Obtain the third ordered review pair**

Obtain specification review followed by code-quality review over identical
post-move subject bytes. Any archive, ledger, report, diff, or subject change
invalidates both.

- [ ] **Step 5: Commit only the reviewed post-move result**

Commit the archive, post-report, subject, diff, and both reviews with subject:

```text
Archive invalidated adopted Task 2 attempt
```

Verify exact committed path reconstruction, 34 archive files, generation-5
live ledger byte-identical to the already-committed HEAD blob (therefore absent
from the commit delta), zero failed-attempt originals other than Task-1
committed files, and all protected bytes unchanged.

### Task 8: Restart Task 2 And Land Its Controlled Boundary

**Files:**
- Recreate only the Task 2 paths named in
  `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

Execution disposition for the final fresh capture:

- The exact owner-adopted attempt captured at
  `1c3d4fc4a2ab0d083ca63f152ac1f89324ab609b` is preserved by the immutable
  archive ref
  `refs/archive/yaml-retirement/task2-attempt-20260722T233938`, which resolves
  to reconstructable sibling commit
  `9effc8cba699c4864294a5dd2c9b82e5407e811f`. The later ordinary documentation
  commit `61de28ccfd75b2c374c948ae753298edf67060a0` invalidated that attempt's
  main-line predecessor before it could land. The archived adoption is
  historical and non-transferable; it does not satisfy the replacement
  capture's owner boundary.
- Land the generic workspace-baseline transition prerequisite as its own
  reviewed commit on top of the real main-line HEAD, restore the live ledger
  to the committed generation-5 snapshot, and delete only the replacement
  attempt's already-archived untracked source files before recapture. The
  compact disposition under
  `task-2-commit-lineage-restart/post-1c3-concurrent-attempt/` records why no
  additional recovery implementation or review class was built.
- The eight protected paths remain byte-bound without adding a redundant
  eighth `protected_paths` row. The seven paths named by the governing capture
  command retain their explicit protected-row duplicates; all eight paths,
  including the later-observed untracked report, are already exact
  `dirty_entries` and broad-candidate rows. The ambient report is therefore
  protected by the same live byte/mode/status checks and remains outside the
  allowed commit set.
- The unique bootstrap-to-workspace transition adopts the selected baseline's
  exact HEAD/index while preserving every inherited dirty/protected row
  semantically. Only a newly observed exact `??` untracked dirty row may extend
  that set; tracked drift, inherited-row drift, and later workspace-baseline
  replacement still fail closed.
- The complete first-boundary durable authority is the two immutable ordered
  `review.v1` records plus the immutable generation-13
  `workflow_retirement_execution_ledger.v1` snapshot. The ledger already binds
  the reviewed `broad_known_failure_baseline.v1` subject, so the v1 durable
  schema catalog is not expanded and historical bootstrap-control
  reconstruction remains byte-compatible.
- The broad baseline inside the archived attempt remains only the historical
  comparison boundary it claims to be. Its normalized six-row failure set may
  be used to detect deviation, but neither its owner adoption nor its
  completion state transfers to the replacement capture. The prerequisite
  patch below changes only repository commit-control machinery and its tests;
  it does not change workflow, provider, runtime, or queue behavior. Later
  broad totals may therefore include the added controller tests while the
  replacement attempt still recaptures and independently adopts its own exact
  baseline.

- [ ] **Step 1: Recapture Task 2 Steps 1–5 at the real HEAD**

Run the governing plan's exact `capture-workspace-baseline`,
`validate-workspace-baseline`, `build-non-target-sources`,
`validate-non-target-sources`, and `materialize-query` commands. Require the new
workspace baseline's `head` to equal current HEAD, the same eight protected
paths represented as described above, ten non-target sources, 100 sorted query
paths, and path-list digest
`sha256:2b4cdaf11ce8570c35cde84987ef73a0a51e985d1d8e3588443a16b8ebac2b63`.
Run both exact handoff selectors and cached/unstaged diff checks.

- [ ] **Step 2: Advance the restored generation-5 ledger through Step 6**

Use the existing materialization transaction API. Do not reuse archived
generation-6-through-11 requests or snapshots. Bind the new workspace/non-target
bytes and retain the governing plan's immutable Task table.

- [ ] **Step 3: Recapture the complete broad baseline in tmux**

Use session `yaml-retirement-impl-baseline` and the governing Generic
Production Broad Gate. Persist collection, preflight, log, exit, JUnit, outcome,
and known-failure baseline. Require exact comparison to the six personally
classified external failure signatures unless fresh output proves an actual
repository change; any deviation follows the governing remediation boundary
and is not silently normalized.

- [ ] **Step 4: Obtain fresh ordered baseline reviews**

Obtain specification review then code-quality review over the new exact
known-failure baseline. Archived reviews are inadmissible.

- [ ] **Step 5: Materialize and pause at the personal-owner boundary**

Materialize the closed pending broad-failure-baseline attestation. Verify its
pending immutable snapshot and live bytes, then pause for Ollie to personally
review and adopt that exact SHA. Prior adoption does not transfer.

- [ ] **Step 6: Apply the owner fields and materialize the final ledger generations**

After personal adoption, change only `evidence_status`, `owner`,
`owner_confirmations`, and `owner_adoption`. Reverse those four fields and
require byte-for-byte equality with the pending snapshot. Run both production
attestation validators. Then materialize contiguous generations 12 and 13:
generation 12 closes Step 7 with the already-existing owner-confirmed
attestation/review evidence, and generation 13 closes Step 8, marks Task 2
`complete`, and makes Task 3 the sole `in_progress` task. The generation-13
live ledger and both new immutable request/snapshot pairs are part of the
controlled Task 2 commit. No task-complete claim exists unless those exact
bytes land unchanged in that commit.

Do not invent a review pair over generation 13. The closed review lifecycle has
exactly one Task 2 pair: the implementation-failure-baseline reviews bind the
generation-11 baseline subject, and the owner attestation consumes that exact
approved pair. Generations 12 and 13 are the acyclic closing transitions that
bind those already-existing approvals and owner-confirmed bytes, matching the
Task 1 closure sequence exercised by
`test_task1_ledger_generations_are_contiguous_and_historical_after_future_reviews`.
Before commit, reopen and validate generations 11, 12, and 13; require the
generation-12 transition evidence to contain the exact attestation and review
digests and the generation-13 transition to preserve them in Task 2's sorted
evidence bindings. A new review kind, subject, or live review path is forbidden
by the governing closed table.

- [ ] **Step 7: Build and validate the external commit control**

Stage only the Task 2 boundary paths. Rerun `validate-non-target-sources`, the
eight-path cached guard, and complete protected-byte comparison. Build
`precommit_control.v1` with the new workspace baseline, exact allowed path set,
complete durable authority, and subject:

```text
Adopt YAML retirement implementation baseline
```

Require precommit validation success.

- [ ] **Step 8: Commit and reconstruct the boundary**

Commit only through the bound NUL pathspec and final-message file. Run
post-commit validation, repeat non-target/protected checks, remove the external
control directory, and reconstruct the control from HEAD. Require the commit
parent to equal the new workspace-baseline HEAD and the committed path set to
equal the control exactly.

- [ ] **Step 9: Resume the governing roadmap**

Reopen the committed generation-13 ledger, require Task 2 `complete` and Task 3
the sole `in_progress` task. Reopen generations 11 and 12 from generation 13's
validated ancestry and require the committed owner attestation to consume the
same two approved baseline reviews bound at generation 11. Then begin `Extract
Stable Generic State-Store Traversal` without another discretionary
confirmation pause.

## Completion Conditions

- The accepted design and this plan are committed and discoverable.
- `attempt_migration_disposition.v1` behavior and committed evidence remain
  unchanged.
- The incident and v2 disposition validate from committed authority.
- Three ordered independent review pairs approve implementation, disposition,
  and post-move subjects.
- The original owner-adopted attempt is archived byte-for-byte and never reused
  as new adoption/completion authority.
- The live ledger is restored to committed generation 5 before restart.
- All eight protected paths and the intervening `README.md` commit remain
  unchanged.
- Fresh Task 2 evidence is captured at its real HEAD, personally adopted, and
  committed through reconstructable `precommit_control.v1` authority.
- Task 3 begins only after that controlled commit exists.
