# YAML Retirement Task 3 Broad-Comparison Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Stage-6 broad known-failure gate reproducible across runs
without changing the owner-adopted Task-2 baseline or weakening any local
evidence validation.

**Architecture:** Keep every `broad_failure_payload_normalization.v1` record as
run-local evidence bound to its own pytest preflight. Derive a second,
preflight-independent comparison projection, apply one narrowly bounded Python
repr-address transform, and require a reviewed, personally owner-adopted
correction authority that rederives the effective Task-2 signatures from the
original bound JUnit bytes. Task 3 consumes that authority while retaining its
one-production-commit contract.

**Tech Stack:** Python 3.11, closed JSON evidence schemas, SHA-256 canonical
digests, pytest/JUnit, Git content bindings.

---

## Status and authority

**Status:** execution-ready corrective prerequisite.

**Governing plan:** `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`
at SHA-256
`sha256:20096b44d03017780394a6789c39705912da1909847ab3460a312c65dcb066fb`.

**Scope of supersession:** this plan supersedes only the governing plan clauses
that:

1. require a later run's complete, run-local `failure_normalization` object to
   equal the Task-2 object byte-for-byte; and
2. define the stable comparison transform list without bounded Python
   repr-address normalization; and
3. close the typed materialization record-kind partition without the two
   correction-specific adapters defined below.

Every other Task-2 baseline, ownership, review, owner-adoption, skip,
remediation, workspace, broad-gate, commit, and Task-3 ordering requirement
remains in force.

The following Task-2 artifacts remain byte-for-byte immutable:

- outcome:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-baseline/outcome.json`
  at `sha256:ac83eea250ef4eca38d27ab3cf56bbb86a5173bd4fce4b861744db50d9b23411`;
- known-failure baseline:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-baseline/known-failure-baseline.json`
  at `sha256:5068e5b98365c277715db28e21227290714cb3994b0a2535dddff3cd34c1e961`;
- owner attestation:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/attestations/pre-implementation/broad-failure-baseline.json`
  at `sha256:56c8ffc74b6d730c59be43bb8577357fe4644d984c0d2e8bfe205463b7c7795a`;
- execution-ledger generation 13:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`
  at `sha256:d87ef0599835b87f7cf4c3adac7d676cbc788889f47c91dc652473f2798ad8c6`.

This is a generic evidence-correctness prerequisite. No workflow, family,
module, pilot, or queue name may enter the production mechanism or schema.
Security-only hostile-environment work is outside this correction and is not a
gate.

## Proven defects

The first defect is structural. A local normalization record contains
`pytest_temp_root_preflight_binding`, including the evidence-directory path and
file digest. Task 2 and Task 3 must write distinct preflight files, so the
governing byte-equality check can never pass even when their normalization
semantics are identical.

The second defect is nondeterministic. The adopted failure row
`tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification`
contains a CPython generator repr address. Two unchanged fresh pytest processes
produced different addresses and therefore different payload signatures. The
accepted precedent is
`docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json`,
which preserves the original capture and normalizes only addresses inside
angle-bracket Python object reprs.

## Corrected comparison contract

### Run-local evidence remains authoritative

`broad_failure_payload_normalization.v1`, `broad_outcome.v1`, the Task-2
baseline, and all raw JUnit/log/preflight bytes remain unchanged. Every outcome
must still:

- bind and reopen its own exact preflight bytes;
- validate pytest version, repository root, temp root, session parent, root
  component, prefix rule, and ordered local transforms;
- rederive its local normalized payload and local payload digest from its own
  JUnit bytes; and
- fail closed on missing, unreadable, tampered, mismatched, or changed local
  evidence.

The comparison layer never substitutes for those checks.

### Comparison normalization projection

Add the closed schema `broad_failure_comparison_normalization.v1` with exactly:

```text
schema_version
repository_root
pytest_version
system_temp_root
pytest_root_component
pytest_session_parent
pytest_temp_prefix_rule
ordered_transforms
normalized_contract_sha256
```

It is derived only from a validated local normalization record. It excludes
only `pytest_temp_root_preflight_binding` and the local record's
`normalized_contract_sha256`, then uses this exact transform order:

```json
[
  "crlf_to_lf.v1",
  "strip_ansi_csi.v1",
  "repository_prefix.v1",
  "pytest_managed_run_prefix.v1",
  "python_repr_address.v1"
]
```

The first four transforms are already applied by the run-local layer. The last
transform replaces only the hexadecimal address in an angle-bracket Python
object repr of the form `<... at 0x[0-9A-Fa-f]+>` with `$ADDR`. It must preserve
arbitrary hexadecimal values and hashes, text such as `mapped at 0x...`,
malformed or unterminated reprs, and addresses outside an angle-bracket Python
object repr.

Later comparison requires the Task-2 and current-run comparison-normalization
objects to be byte-identical after their independent local records validate.
Any repository root, pytest version, temp-root base, root component, session
parent, prefix rule, transform, order, schema, or digest drift fails closed.

### Reviewed comparison correction

Add `broad_failure_comparison_correction.v1`. Its exact top-level keys are:

```text
schema_version
known_failure_baseline_binding
source_normalization_contract_sha256
comparison_normalization
source_failure_set_sha256
comparison_failures
changed_failure_node_ids
comparison_failure_set_sha256
classification_summary
normalized_correction_sha256
claims_not_made
```

`known_failure_baseline_binding` is the complete existing five-part Task-2
authority graph: outcome, baseline record, specification review, quality
review, and owner attestation. Validation reopens that graph and its original
raw JUnit/preflight evidence.

Each sorted `comparison_failures` row contains exactly:

```text
node_id
outcome_kind
source_failure_payload_sha256
comparison_failure_payload_sha256
ownership_class
ownership_basis
authorized_remediation_scope
```

The builder and validator must rederive every comparison signature from the
bound Task-2 outcome's validated `normalized_payload`, using the canonical tuple
`[node_id, outcome_kind, comparison_normalized_payload]`. Node IDs, outcome
kinds, ownership fields, the six-row count, and the 6-external/0-queue
classification must equal the adopted baseline exactly. Only rows whose source
and comparison payload digests differ appear in
`changed_failure_node_ids`. The original baseline is never overwritten.

The closed claims state that the correction is comparison-only, changes no
failure ownership or remediation authority, grants no source/store/workflow/
run-root/repository mutation authority, and does not attest Task 3 or roadmap
completion.

### Owner attestation and later-run binding

Add `broad_failure_comparison_correction_attestation.v1` with the same closed
pending/owner-confirmed lifecycle discipline as the Task-2 baseline
attestation. It binds the correction bytes, six-row comparison failure-set
digest, comparison-normalization digest, unchanged classification, and ordered
approved specification and quality reviews.

The six fixed owner confirmations cover:

1. the exact corrected six-row table and changed-row set;
2. the complete bounded comparison-normalization contract;
3. the unchanged 6-external/0-queue classification;
4. both ordered approved reviews;
5. comparison-only use; and
6. no external repair or mutation authority.

Personal owner adoption of the exact pending SHA is mandatory. Reviewer
approval, relay, standing delegation, or this plan is not adoption.

Extend a later outcome's `known_failure_baseline_binding` with exactly one
`comparison_correction` member containing the correction record, its
specification review, its quality review, and its owner attestation. The
correction must bind the same five-part Task-2 authority graph carried by the
outer binding. Missing, pending, unreadable, tampered, wrong-baseline,
wrong-review, or multiply supplied correction authority fails closed.

`baseline_comparison.normalization_contract_sha256`,
`baseline_failure_set_sha256`, and `observed_failure_set_sha256` retain their
existing keys but bind the comparison-normalization digest, corrected expected
signature set, and current comparison signature set respectively. The local
outcome continues carrying its separate run-local normalization object and
local payload rows.

## File map

The corrective plan commit contains only:

- this plan;
- `docs/plans/evidence/yaml-retirement/broad-comparison-correction-plan/specification-review.json`;
- `docs/plans/evidence/yaml-retirement/broad-comparison-correction-plan/quality-review.json`.

Task 3's already-authorized state-store paths remain:

- modify `orchestrator/retirement/__init__.py`;
- create `orchestrator/retirement/state_store.py`;
- modify `orchestrator/workflow_lisp/procedure_identity_retirement.py`;
- create `tests/test_retirement_state_store.py`;
- modify `tests/test_workflow_lisp_procedure_identity_retirement.py`;
- modify `tests/test_retirement_broad_evidence.py` for the required public
  surface expectation.

This plan additionally authorizes Task 3 to:

- modify `orchestrator/retirement/broad_evidence.py`;
- modify `orchestrator/retirement/materialization.py`;
- modify `tests/test_retirement_broad_evidence.py`;
- create
  `tests/fixtures/retirement_broad_evidence/broad_failure_comparison_normalization.v1.json`;
- create
  `tests/fixtures/retirement_broad_evidence/broad_failure_comparison_correction.v1.json`;
- create
  `tests/fixtures/retirement_broad_evidence/broad_failure_comparison_correction_attestation.pending.v1.json`;
- create
  `tests/fixtures/retirement_broad_evidence/broad_failure_comparison_correction_attestation.confirmed.v1.json`;
- modify
  `tests/fixtures/retirement_broad_evidence/broad_outcome.exact_match.v1.json`;
- modify
  `tests/fixtures/retirement_broad_evidence/broad_outcome.reviewed_subset.v1.json`;
- modify `tests/fixtures/retirement_broad_evidence/manifest.v1.json`;
- create the reviewed correction evidence beneath
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/corrections/broad-comparison-v1/`;
- create the deterministic `materialization-inputs/` request and
  `immutable-outputs/` snapshot artifacts for `correction.json` and the pending
  `attestation.json` beneath the existing
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/` evidence
  root used as `materialize_transaction.evidence_root`;
- create Task-3 focused, broad, subject, review, immutable-review, ledger
  materialization, and commit-control evidence at the deterministic locations
  already required by the governing plan.

Mechanically derived fixture or immutable-review filenames under those exact
roots are part of the same authorized set. No other production, test, fixture,
workflow, or evidence path is authorized by this correction.

### Task 1: Lock the corrective plan

**Files:**

- Create:
  `docs/plans/2026-07-23-yaml-retirement-task-3-broad-comparison-correction-plan.md`
- Create:
  `docs/plans/evidence/yaml-retirement/broad-comparison-correction-plan/specification-review.json`
- Create:
  `docs/plans/evidence/yaml-retirement/broad-comparison-correction-plan/quality-review.json`

- [ ] **Step 1: Obtain an independent specification review**

Review the exact plan bytes against the governing plan, adopted Task-2
authority graph, and the accepted repr-address correction precedent.

- [ ] **Step 2: Obtain an independent quality review**

Check that the plan is generic, minimal, fail-closed, internally consistent,
and executable without modifying Task-2 artifacts.

- [ ] **Step 3: Commit only the reviewed plan and reviews**

Run:

```text
git add -- \
  docs/plans/2026-07-23-yaml-retirement-task-3-broad-comparison-correction-plan.md \
  docs/plans/evidence/yaml-retirement/broad-comparison-correction-plan/specification-review.json \
  docs/plans/evidence/yaml-retirement/broad-comparison-correction-plan/quality-review.json
git commit --only -m "Plan broad comparison evidence correction" -- \
  docs/plans/2026-07-23-yaml-retirement-task-3-broad-comparison-correction-plan.md \
  docs/plans/evidence/yaml-retirement/broad-comparison-correction-plan/specification-review.json \
  docs/plans/evidence/yaml-retirement/broad-comparison-correction-plan/quality-review.json
```

Expected: one documentation-only corrective-plan commit; all Task-3 source
candidate and ambient user paths remain uncommitted and byte-identical.

### Task 2: Implement the comparison projection and bounded transform

**Files:**

- Modify: `orchestrator/retirement/broad_evidence.py`
- Modify: `orchestrator/retirement/__init__.py`
- Modify: `tests/test_retirement_broad_evidence.py`
- Create:
  `tests/fixtures/retirement_broad_evidence/broad_failure_comparison_normalization.v1.json`
- Modify: `tests/fixtures/retirement_broad_evidence/manifest.v1.json`

- [ ] **Step 1: Write failing normalization tests**

Add tests proving:

- committed/local-v1 JUnit replay preserves an angle-bracket Python repr
  address and reproduces its original local digest byte-for-byte;
- two valid local normalizers with different preflight paths/digests derive the
  same comparison projection;
- any retained base/version/rule/order field drift changes or invalidates the
  projection;
- two well-formed repr addresses normalize equally;
- different repr content remains different; and
- bare, mapped, malformed, unterminated, and arbitrary hexadecimal values
  remain byte-significant.

- [ ] **Step 2: Run the exact RED selector**

Run:

```text
pytest -q tests/test_retirement_broad_evidence.py \
  -k 'comparison_normalization or python_repr_address'
```

Expected: failures identify the missing projection/schema/transform, not
unrelated collection errors.

- [ ] **Step 3: Implement the minimal projection and transform**

Add closed schema validation, canonical digest derivation, the bounded regex,
and comparison signature derivation. Do not change local normalization or the
committed Task-2 fixtures/artifacts.

- [ ] **Step 4: Run the exact GREEN selector**

Run the Step-2 command. Expected: all selected tests pass.

### Task 3: Implement the reviewed correction authority

**Files:**

- Modify: `orchestrator/retirement/broad_evidence.py`
- Modify: `orchestrator/retirement/materialization.py`
- Modify: `orchestrator/retirement/__init__.py`
- Modify: `tests/test_retirement_broad_evidence.py`
- Create:
  `tests/fixtures/retirement_broad_evidence/broad_failure_comparison_correction.v1.json`
- Create:
  `tests/fixtures/retirement_broad_evidence/broad_failure_comparison_correction_attestation.pending.v1.json`
- Create:
  `tests/fixtures/retirement_broad_evidence/broad_failure_comparison_correction_attestation.confirmed.v1.json`
- Modify: `tests/fixtures/retirement_broad_evidence/manifest.v1.json`

- [ ] **Step 1: Write failing correction and attestation tests**

Cover a valid rederivation plus missing/tampered raw evidence, wrong Task-2
authority, changed classification, changed row, wrong changed-row set, pending
attestation, owner-field drift, review mismatch, and digest mismatch.

- [ ] **Step 2: Run the exact RED selector**

Run:

```text
pytest -q tests/test_retirement_broad_evidence.py \
  -k 'comparison_correction'
```

Expected: failures identify the missing schemas/builders/validators.

- [ ] **Step 3: Implement the smallest closed builders and validators**

Reopen and validate the existing authority graph, rederive from its raw JUnit
and local payloads, enforce the exact row/classification relationship, validate
ordered reviews, and close both attestation lifecycle states. Extend the closed
materialization registry with:

- non-pending kind `broad-failure-comparison-correction`, whose exact five
  inputs are the Task-2 outcome, baseline record, specification review, quality
  review, and owner attestation and whose output slot is the deterministic
  `correction.json`; and
- pending-only kind
  `broad-failure-comparison-correction-attestation`, whose exact inputs are the
  correction plus its specification and quality reviews, whose only parameters
  are `prepared_by` and `prepared_at`, and whose output slot is the
  deterministic `attestation.json`.

Both use `materialize_transaction`; unknown, repeated, missing, or extra
roles/parameters remain rejected. Confirmed owner adoption is validate-only and
never a materializer mode.

- [ ] **Step 4: Run the exact GREEN selector**

Run the Step-2 command. Expected: all selected tests pass.

### Task 4: Route later broad comparisons through the correction

**Files:**

- Modify: `orchestrator/retirement/broad_evidence.py`
- Modify: `orchestrator/retirement/__init__.py`
- Modify: `tests/test_retirement_broad_evidence.py`
- Modify:
  `tests/fixtures/retirement_broad_evidence/broad_outcome.exact_match.v1.json`
- Modify:
  `tests/fixtures/retirement_broad_evidence/broad_outcome.reviewed_subset.v1.json`
- Modify: `tests/fixtures/retirement_broad_evidence/manifest.v1.json`

- [ ] **Step 1: Write both-direction integration tests**

Prove that distinct valid preflight bindings with equal comparison projections
pass and that missing/pending/tampered/wrong-baseline correction authority
fails. Also prove new, missing, semantically changed, or externally removed
failures still fail exactly as before.

- [ ] **Step 2: Run the exact RED selector**

Run:

```text
pytest -q tests/test_retirement_broad_evidence.py \
  -k 'baseline_comparison and comparison_correction'
```

Expected: the valid cross-run case fails under the old byte-equality check.

- [ ] **Step 3: Replace only the contradictory comparison logic**

Require the reviewed correction authority, compare derived projection objects,
and compare corrected signature rows. Preserve all local evidence, remediation,
skip, lifecycle, and external-removal gates.

- [ ] **Step 4: Run the exact GREEN selector and owning module**

Run:

```text
pytest -q tests/test_retirement_broad_evidence.py \
  -k 'baseline_comparison or comparison_correction or comparison_normalization or python_repr_address'
pytest -q tests/test_retirement_broad_evidence.py
```

Expected: both commands pass.

### Task 5: Review and adopt the correction evidence

**Files:**

- Create under:
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/corrections/broad-comparison-v1/`

- [ ] **Step 1: Materialize the correction from committed Task-2 bytes**

Call the already-landed `materialize_transaction` library API directly with
`record_kind="broad-failure-comparison-correction"` and `pending=False` to write
canonical `correction.json` plus its immutable request/output snapshots. Verify
the six-row comparison table, changed-row set, normalization digest, 6/0
classification, complete original authority binding, and transaction replay.
The transaction uses
`docs/plans/evidence/yaml-retirement/delete-non-survivor-estate` as
`evidence_root` and
`docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/corrections/broad-comparison-v1/correction.json`
as `output_path`; its derived `materialization-inputs/` and
`immutable-outputs/` therefore live beneath that same evidence root.

- [ ] **Step 2: Obtain ordered independent reviews**

Publish `specification-review.json` first, then `quality-review.json`, both over
the same correction bytes, and preserve their immutable review bindings.

- [ ] **Step 3: Materialize the pending owner attestation**

Call `materialize_transaction` directly with
`record_kind="broad-failure-comparison-correction-attestation"` and
`pending=True` to write canonical `attestation.json` and its immutable
request/output snapshots. Require no owner values, bind both reviews, and
validate it as pending. No tool may materialize the later confirmed form. The
governing Task-6 CLI extension remains deferred to Task 6.
Use the same evidence root as Step 1 and the deterministic output path
`docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/corrections/broad-comparison-v1/attestation.json`.

- [ ] **Step 4: Stop only at the non-delegable adoption boundary**

The owner must personally review and adopt the exact pending SHA, six-row table,
bounded transform, unchanged classification, comparison-only use, and
no-repair/no-mutation claim. Apply only the enumerated owner fields and validate
the closed owner-confirmed record.

### Task 6: Resume and complete Task 3

**Files:**

- All Task-3 state-store, correction, fixture, evidence, review, ledger, and
  commit-control paths authorized above.

- [ ] **Step 1: Re-run Task-3 focused evidence**

Use ledger generation 18 and the exact three focused roles from the governing
plan. Bind only the focused contract's exact `LC_ALL=C.UTF-8` and
`PYTHONHASHSEED=0` environment. Collection and all focused commands must pass.

- [ ] **Step 2: Run the full broad gate in tmux**

Use session `yaml-retirement-impl-task-03`, Task-3-local preflight/raw paths,
and bind `LC_ALL=C.UTF-8`, `PYTHONHASHSEED=0`, and
`PYTEST_DEBUG_TEMPROOT=/home/ollie/.cache/pytest-yaml-retirement-task2` for the
preflight, full collection, and broad run exactly as Task 2 did. Run:

```text
LC_ALL=C.UTF-8 \
PYTHONHASHSEED=0 \
PYTEST_DEBUG_TEMPROOT=/home/ollie/.cache/pytest-yaml-retirement-task2 \
pytest -q -rs -n 16 --dist=worksteal \
  --junitxml=docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-commits/task-03/pytest.junit.xml
```

The result must be `known_failures_matched` or an independently authorized
subset. It may not rely on Task-2 local preflight bytes.

- [ ] **Step 3: Freeze and review the exact Task-3 subject**

Build the implementation subject over the combined state-store and correction
candidate, focused evidence, broad evidence, owner-confirmed correction
authority, and ledger generation 18. Obtain ordered independent specification
then quality approval.

- [ ] **Step 4: Advance the ledger and make Task 3's one production commit**

Materialize generation 19 with Task 3 complete and Task 4 solely in progress.
Build and validate the exact precommit control, commit only its allowed path set
with subject `Extract generic retirement state-store traversal`, then perform
postcommit and reconstruction validation.

- [ ] **Step 5: Continue the governing roadmap**

Proceed immediately to Task 4 and the remaining Stage-6 tasks in order. This
correction adds no roadmap task, queue exception, or later owner boundary.

## Completion conditions

This correction is complete only when:

- all four frozen Task-2 artifacts above remain byte-identical;
- every local broad outcome validates its own preflight and raw evidence;
- the comparison projection excludes only the run-local preflight binding and
  local full-object digest;
- the bounded repr transform preserves every non-repr address and arbitrary
  hexadecimal value;
- correction bytes are rederived from the original Task-2 JUnit authority;
- the correction has ordered independent reviews and personal owner adoption;
- missing, pending, tampered, ambiguous, or wrong-baseline correction authority
  fails closed;
- new, missing, changed, or unauthorized externally removed failures still
  fail closed;
- Task 3 passes focused and broad evidence plus ordered independent reviews; and
- Task 3 lands as exactly one controlled production commit.
