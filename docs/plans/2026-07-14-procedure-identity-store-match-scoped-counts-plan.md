# Procedure Identity Store Match-Scoped Counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make procedure-identity retirement run-status counts apply only to
distinct runs containing a queried retired identity while retaining complete
store-wide run totals as non-gating evidence.

**Architecture:** `scan_known_state_store` continues to scan and content-address
the complete named store. It records `store_terminal_run_count` and
`store_nonterminal_run_count` for hygiene, then derives the existing
`terminal_run_count` and `nonterminal_run_count` from distinct containing runs
of the normalized query-match set. The validator gates only on the match-scoped
nonterminal count and compares both scoped and store-wide facts against a fresh
scan.

**Tech Stack:** Python dataclasses, deterministic JSON scanning, Workflow Lisp
retirement evidence, pytest, jq, tmux.

---

## Authority and boundaries

- Accepted contract:
  `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`,
  especially its matching-count and queried-identity requirements.
- Accepted architect decision:
  `docs/plans/2026-07-14-tracked-plan-pilot-identity-retirement-decision-request.md`.
- Active consumer:
  `docs/plans/2026-07-13-procedure-first-pilot-plan.md`, Task 1A.
- Root cause: `scan_known_state_store` currently increments run-status counts
  for every top-level `state.json`, independently of `retired_identities`, but
  `validate_retirement_record` consumes `nonterminal_run_count` as supported
  queried state. This is a `semantic_conflict`, not a reason to broaden the
  accepted gate.
- Keep the implementation generic. No workflow-family name or pilot identity
  belongs in `orchestrator/workflow_lisp/procedure_identity_retirement.py`, its
  generic tests, or the fictional generic fixture.
- Preserve `procedure-identity-store-query.v1`: this is a correction to its
  accepted matching-count semantics before the first production retirement
  record, not a new eligibility class. The normalized digest changes because
  corrected facts and new store-wide totals enter the normalized projection.
- `terminal_run_count` and `nonterminal_run_count` remain required schema
  fields and become unambiguously match-scoped. Add required non-gating
  `store_terminal_run_count` and `store_nonterminal_run_count` fields.
- `consumer_count` and `call_frame_count` remain query-match-derived. File,
  checkpoint, manifest, metadata, and scanned-file counts remain whole-store
  observability facts and do not independently select strict compatibility.
- An unreadable supported file remains a scan error. A query match whose
  containing top-level run lacks `state.json` is a stable fail-closed scan
  error. A present top-level state with a missing or unknown status is counted
  as matching nonterminal state and therefore rejected.
- Count each matching run once even if it contains multiple matching rows.
- A nested call-frame/checkpoint/metadata/path match inherits the status of its
  first path component's top-level run.
- Do not edit the pilot `.orc` source or frozen baseline in this repair.

## Protected working-tree guard

Preserve and never stage, restore, or rewrite these user-owned dirty paths:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

The untracked pilot evidence directory is also not part of the generic repair
commit. Regeneration is owned by Task 4 below.

### Task 1: Correct Generic Scanner Run Counts With TDD

**Files:**
- Modify: `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Modify: `orchestrator/workflow_lisp/procedure_identity_retirement.py`

- [ ] **Step 1: Write the unrelated-run RED**

Add a generic test with one unrelated `running` top-level run and a retired
identity that does not occur anywhere. Require:

```python
assert result["terminal_run_count"] == 0
assert result["nonterminal_run_count"] == 0
assert result["store_terminal_run_count"] == 0
assert result["store_nonterminal_run_count"] == 1
assert result["matches"] == ()
```

- [ ] **Step 2: Write remaining scanner REDs**

Add behavioral tests proving:

1. a matching nonterminal top-level run produces matching and store-wide
   nonterminal counts of one;
2. an unrelated terminal run plus a matching nonterminal run produces matching
   counts `0/1` and store totals `1/1`;
3. multiple matching identities in one run count as one matching run;
4. a nested checkpoint/call-frame/metadata match inherits its containing
   top-level run status; and
5. a nested match without a containing top-level `state.json` raises
   `procedure_identity_retirement_matching_run_state_missing`.

Also add matching-run cases whose readable `state.json` omits `status` or uses
an unknown status. Both must count as matching nonterminal state. Retain the
existing malformed/unreadable-file rejection coverage.

Update the existing normalized scan test and scalar-output scan test so their
matching-count expectations follow the accepted semantics while store-wide
totals retain the old observations.

- [ ] **Step 3: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py \
  -k 'match_scoped or matching_run or known_state_store_scan_is_normalized or scalar_json'
```

Expected: failures show current store-wide counts leaking into match-scoped
fields and missing `store_*` fields/error behavior.

- [ ] **Step 4: Implement minimal scanner correction**

In `scan_known_state_store`:

- retain a map from each top-level run path component to its terminal versus
  nonterminal classification while scanning top-level `state.json` files;
- increment the new `store_*` counts for every top-level run;
- normalize and deduplicate query matches as today;
- derive distinct matching run keys from match-row paths;
- fail closed if a matching run has no top-level state;
- derive existing terminal/nonterminal counts from the distinct matching run
  keys; and
- include both scoped and store-wide counts in the normalized digest.

Do not special-case workflow names, query values, or the pilot root.

- [ ] **Step 5: Run GREEN and focused regression tests**

```bash
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py \
  -k 'match_scoped or matching_run or known_state_store_scan_is_normalized or scalar_json or store_scan'
```

Expected: all selected scanner tests pass.

- [ ] **Step 6: Commit the scanner behavior**

```bash
git add orchestrator/workflow_lisp/procedure_identity_retirement.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py
git diff --cached --check
git commit -m "fix: scope procedure retirement run counts to matches"
```

- [ ] **Step 7: Run the two-stage Task 1 review**

Require a fresh specification reviewer to check the implementation against
the accepted match-scoped semantics, then a different fresh quality reviewer
to check maintainability, failure behavior, and test strength. Resolve every
material finding and repeat the affected review before Task 2.

### Task 2: Carry Store Totals Through Record Parsing And Validation

**Files:**
- Modify: `orchestrator/workflow_lisp/procedure_identity_retirement.py`
- Modify: `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Modify: `tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json`

- [ ] **Step 1: Write validator REDs in both directions**

Add a test that builds a fresh known store containing only an unrelated running
run. Copy all fresh scanner fields into the record and require the validator to
accept it: matching nonterminal is zero while store-wide nonterminal is one.

Add a second test whose running run contains a recognized retired identity and
require `procedure_identity_retirement_supported_state_present`.

Add parser/count-mismatch coverage for both required `store_*` fields. Retain
the existing rejection tests for matching nonterminal, call-frame, and consumer
counts.

- [ ] **Step 2: Run validator REDs**

```bash
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py \
  -k 'unrelated_nonterminal or matching_nonterminal or store_terminal_run_count or store_nonterminal_run_count'
```

Expected: missing schema fields and current record semantics fail.

- [ ] **Step 3: Extend the generic record model**

Add required integer fields to `KnownStateStoreEvidence`:

```python
store_terminal_run_count: int
store_nonterminal_run_count: int
```

Permit, require, parse, validate as non-negative, and fresh-compare both fields.
Do not add either to the eligibility predicate. Change the supported-state
diagnostic text to say `matching supported nonterminal state`.

- [ ] **Step 4: Regenerate fictional fixture scan facts**

Run the corrected scanner over the fixture store using the fixture record's
retired identities. Update the fixture's matching counts, store totals, and
normalized digest from that exact result. Do not copy owner or attestation text
into any pilot evidence.

- [ ] **Step 5: Run the complete retirement suite**

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedure_identity_retirement.py
pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_procedure_identity_retirement.py
```

Expected: collection succeeds and the complete module passes.

- [ ] **Step 6: Commit schema and validator support**

```bash
git add orchestrator/workflow_lisp/procedure_identity_retirement.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json
git diff --cached --check
git commit -m "fix: retain non-gating procedure store totals"
```

- [ ] **Step 7: Run the two-stage Task 2 review**

Require specification review first and quality review second. Resolve and
re-review material findings before updating durable documentation.

### Task 3: Merge The Accepted Count Semantics Into Durable Docs

**Files:**
- Modify: `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
- Modify: `docs/index.md`
- Modify: `docs/plans/2026-07-13-procedure-first-pilot-plan.md`
- Modify: `docs/plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md`

- [ ] **Step 1: Clarify the authoritative evidence schema**

State durably that terminal/nonterminal counts are counts of distinct runs
containing at least one queried-identity match; multiple matches do not multiply
the count; nested matches inherit the containing run status; missing/unreadable
status fails closed; and separate `store_*` totals are disclosed but non-gating.

- [ ] **Step 2: Align the pilot gate**

Require the corrected matching counts and disclosed store totals in pre-edit
and final scans. Replace any plan wording that could make unrelated
nonterminal runs select strict compatibility. Preserve the owner-attestation,
quiescence, unknown-store, checksum, source-edit, and old-consumer gates.

Update `docs/index.md` so its Task 1A route reflects the architect-approved
selection, this generic corrective prerequisite, and the current
owner-attestation boundary instead of describing the task as unselected.

- [ ] **Step 3: Record repair completion in this plan**

Check completed implementation steps only after their commits and reviews are
real. Do not mark pilot scan regeneration or owner attestations complete here.

- [ ] **Step 4: Verify and commit docs**

```bash
rg -n "matching.*nonterminal|store_nonterminal_run_count|queried old identities" \
  docs/design/workflow_lisp_procedure_migration_identity_compatibility.md \
  docs/plans/2026-07-13-procedure-first-pilot-plan.md
git diff --check -- docs/design/workflow_lisp_procedure_migration_identity_compatibility.md \
  docs/index.md \
  docs/plans/2026-07-13-procedure-first-pilot-plan.md \
  docs/plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md
git add docs/design/workflow_lisp_procedure_migration_identity_compatibility.md \
  docs/index.md \
  docs/plans/2026-07-13-procedure-first-pilot-plan.md \
  docs/plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md
git commit -m "docs: clarify procedure retirement store counts"
```

- [ ] **Step 5: Run the two-stage Task 3 review**

Require specification review first and quality review second. Resolve and
re-review material findings before broad verification.

### Task 4: Run Broad Generic Verification

**Files:**
- Verify only; modify nothing unless a real regression requires a scoped fix.

- [ ] **Step 1: Run focused related suites**

```bash
pytest -q -n 16 --dist=worksteal \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_resume_command.py
```

- [ ] **Step 2: Run the broad suite in tmux**

```bash
pytest -q -n 16 --dist=worksteal
```

Compare failures by exact node ID and normalized signature against the accepted
prerequisite baseline/correction artifacts. Do not weaken or delete tests to
make unrelated failures disappear.

- [ ] **Step 3: Independent holistic review**

After the per-task two-stage reviews, require a fresh holistic reviewer to
check the integrated Tasks 1-3 result and fresh verification evidence before
regenerating pilot evidence.

### Task 5: Regenerate The Pilot Pre-Edit Scan

**Files:**
- Regenerate:
  `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/pre_edit_known_store_scans.json`
- Preserve owner-supplied:
  `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/pre-edit/scratch-provenance-confirmation.json`

- [ ] **Step 1: Reconfirm immutable inputs and empty dedicated root**

Require the pilot source and frozen baseline to remain unchanged, scratch count
to remain zero, and the dedicated evidence root to remain empty and isolated.
Reuse the reviewed 64-identity query only after recomputing its baseline/source
and query digests.

- [ ] **Step 2: Rerun both store scans in tmux**

Use the corrected `scan_known_state_store` against the same two roots and exact
query. Regenerate the complete evidence file from scratch at the new repair
commit. Retain the store-wide `4,074/90` facts under `store_*`; never edit the
old normalized digest in place.

- [ ] **Step 3: Apply the corrected gate**

Proceed only if both roots have zero matching nonterminal, call-frame, and
consumer counts. Store-wide totals do not select strict compatibility. Any
actual query match, scan race, root mutation, or dedicated-root contamination
stops the pilot.

- [ ] **Step 4: Independently review regenerated evidence**

Require exact query, digest, count, isolation, and claim-boundary review. Do not
create owner attestations or begin quiescence during regeneration/review.

### Task 6: Pause At The Owner-Attestation Boundary

**Files:**
- Owner-supplied or explicitly owner-adopted:
  `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/pre-edit/<sha256-of-canonical-root>.json`
- Create only after receiving owner records:
  `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/index.json`

- [ ] **Step 1: Publish exact owner record forms and deterministic paths**

For each scanned root, provide the exact scan digest, query time, matching
counts, store-wide totals, canonical-root digest filename, required adoption
provenance, and quiescence statement. Do not write, paraphrase, or sign the
owner confirmations.

If the owner explicitly directs a mechanical write after reviewing and
adopting the complete record, preserve accurate mechanical-writer attribution
and the owner's verbatim adoption provenance.

- [ ] **Step 2: Pause**

The standing owner direction permits mechanical writes only after Ollie reviews
and adopts the complete record. Stop here until both owner records exist and
quiescence has explicitly started. Task 2 of the pilot remains prohibited.
