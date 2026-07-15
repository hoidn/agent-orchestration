# Retired Identity Query Evidence Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every reviewed procedure-identity retirement record bind its identity delta to a frozen, content-addressed pre-edit `old_identity_query` without recompiling retained source or persisting full per-workflow bundles.

**Architecture:** Add one closed evidence-only binding to the existing v1 retirement record. A read-only validator replays the referenced pre-edit query's raw identity list, domain memberships, baseline/source bindings, and digests, then unions its domain-qualified retired rows with production-derived old identities and requires an exact match to `identity_delta`; any raw retired identity found anywhere in the new production table fails closed.

**Tech Stack:** Python dataclasses and JSON validation, SHA-256 canonical JSON projections, pytest fixtures, existing procedure-identity retirement validator.

---

### Task 1: Add the closed query-evidence model and parser

**Files:**
- Modify: `orchestrator/workflow_lisp/procedure_identity_retirement.py`
- Modify: `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Modify: `tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json`
- Create: `tests/fixtures/workflow_lisp/procedure_identity_retirement/pre_edit_scan.json`
- Create: `tests/fixtures/workflow_lisp/procedure_identity_retirement/old/identity_baseline.json`

- [ ] **Step 1: Write parser RED tests**

Add tests proving that `retired_identity_query_evidence` is required and closed, and that every field has the required type. The binding fields are `evidence_path`, `evidence_sha256`, `query_version`, `query_list_sha256`, `identity_count`, `identities_by_domain_sha256`, `baseline_path`, `baseline_sha256`, `old_source_path`, and `old_source_sha256`.

- [ ] **Step 2: Run the parser RED tests**

Run:

```bash
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py -k 'retired_identity_query_evidence and (required or parser)'
```

Expected: failure because the root schema and frozen model do not yet contain the binding.

- [ ] **Step 3: Implement the minimal frozen model and closed parser**

Add a frozen `RetiredIdentityQueryEvidence` dataclass and require it from `ProcedureIdentityRetirementRecord`. Parse the exact field set above with existing strict object/string/integer helpers. Do not add compiler imports, runtime hooks, mutation directives, module-name switches, or optional family-specific fields.

- [ ] **Step 4: Create the generic fictional fixture evidence**

Create a small pre-edit scan fixture whose `old_identity_query` contains a canonical sorted raw list and an exact `identities_by_domain` mapping, including at least one raw identity validly present in two domains. Bind it to a content-addressed opaque frozen baseline and the existing old source. Update the valid retirement fixture with exact hashes.

- [ ] **Step 5: Run collection and parser GREEN tests**

Run:

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedure_identity_retirement.py
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py -k 'retired_identity_query_evidence and (required or parser)'
```

Expected: collection succeeds and the focused parser tests pass.

### Task 2: Replay the frozen query and strengthen exact identity validation

**Files:**
- Modify: `orchestrator/workflow_lisp/procedure_identity_retirement.py`
- Modify: `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Modify: `tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json`

- [ ] **Step 1: Write both-direction RED tests**

Add one positive test for the valid content-addressed query, including the same
raw identity occurring validly in two domains. Add negative tests for:
evidence-byte tamper, query-version mismatch, canonical raw-list digest
mismatch, identity-count mismatch, a duplicate within one domain, missing
domain membership, extra domain membership, domain-map digest mismatch,
frozen-baseline digest mismatch, old-source digest mismatch, an extra or
missing domain-qualified retired row in `identity_delta`, and a retired raw
identity appearing anywhere in the new production identity table. Assertions
target stable issue codes and paths, not message phrasing.

Use a helper that copies the generic fixture tree beneath a temporary
repository root. The outer-byte-tamper test mutates `pre_edit_scan.json` and
leaves `evidence_sha256` stale. For version/list/count/map/baseline/source
tests, mutate the retained query or referenced bytes, recompute the outer
evidence digest in the record, and deliberately leave only the targeted
duplicated binding or semantic invariant stale. Each test must reach and
assert its specific issue code and path rather than passing through the outer
digest failure.

- [ ] **Step 2: Run the validator RED tests**

Run:

```bash
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py -k 'retired_query or query_evidence or leaked_retired'
```

Expected: the new validation tests fail for the missing replay/union logic.

- [ ] **Step 3: Implement retained-byte replay**

Load the referenced evidence, baseline, and old source relative to `repo_root`
with duplicate-key rejection, traversal/symlink rejection, readable-file
checks, and exact SHA-256 verification. Require the frozen evidence's
`old_identity_query` to agree with every binding field.

Require `old_identity_query.identities` to be a string-only, sorted,
duplicate-free array. Require `identities_by_domain` to be a closed object
with exactly `REQUIRED_IDENTITY_DOMAINS` as its keys. Require each domain value
to be a string-only, sorted, duplicate-free array while permitting the same
raw identity in multiple domains. Require the sorted unique flattening to
equal the raw list. Recompute the canonical raw-list and exact domain-map
digests using UTF-8 JSON with `sort_keys=True`, separators `(',', ':')`, and
`ensure_ascii=False`; the exact map, not only its membership count, must match
the record binding.

- [ ] **Step 4: Implement exact domain-qualified union and leak rejection**

Expand the frozen domain map into unique `(identity_kind, identity)` retired rows. Union those rows with production-derived old identities, assigning `preserved` only when the same domain-qualified identity exists in the new production table and otherwise `retired`. Because the frozen query is authoritative retired evidence, reject any of its raw identities found in any new production domain. Require old and new actual tables from `identity_delta` to equal the resulting production/query tables exactly.

- [ ] **Step 5: Run focused and full validator GREEN tests**

Run:

```bash
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py -k 'retired_query or query_evidence or leaked_retired'
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py
```

Expected: all focused and module tests pass.

- [ ] **Step 6: Verify genericity and read-only boundaries**

Run:

```bash
git diff --check
rg -n 'tracked-plan|procedure-first-pilot|design_plan_impl' orchestrator/workflow_lisp/procedure_identity_retirement.py tests/fixtures/workflow_lisp/procedure_identity_retirement tests/test_workflow_lisp_procedure_identity_retirement.py
```

Expected: no new family/pilot/module-specific mechanism or fictional fixture coupling. Verify no workflow run/resume command and no store mutation occurred.

### Task 3: Complete ordered implementation reviews and land the generic fix

**Files:**
- Review: `orchestrator/workflow_lisp/procedure_identity_retirement.py`
- Review: `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Review: `tests/fixtures/workflow_lisp/procedure_identity_retirement/`
- Review: `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
- Review: `docs/plans/2026-07-15-retired-identity-query-evidence-binding-plan.md`

- [ ] **Step 1: Dispatch specification review**

Require confirmation that the implementation matches the approved content-addressed query contract, preserves the distinct raw-ID and domain-membership views, never recompiles, and rejects every mismatch and leak listed above.

- [ ] **Step 2: Resolve all Critical and Important specification findings**

Re-run the focused and full validator module after any correction.

- [ ] **Step 3: Dispatch quality/safety review**

Require confirmation of closed parsing, duplicate-key/path/symlink defenses, deterministic canonicalization, stable issue codes, generic naming, zero runtime authority, and zero store/workflow mutation.

- [ ] **Step 4: Resolve all Critical and Important quality findings**

Re-run the focused and full validator module after any correction.

- [ ] **Step 5: Run broad verification in tmux**

Run the complete generic validator module under the repository-required
parallel form. Do not run the pilot migration module yet because its record
does not gain the newly required binding until Task 4:

```bash
pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_procedure_identity_retirement.py
```

Expected: all generic validator tests pass. Keep the command in tmux and
verify protected run roots before and after.

- [ ] **Step 6: Commit only the generic fix and its reviewed docs**

The authoritative design amendment and this reviewed plan land before
implementation. Stage only the validator and generic tests/fixtures with this
exact allowlist:

```bash
git add \
  orchestrator/workflow_lisp/procedure_identity_retirement.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json \
  tests/fixtures/workflow_lisp/procedure_identity_retirement/pre_edit_scan.json \
  tests/fixtures/workflow_lisp/procedure_identity_retirement/old/identity_baseline.json
expected="$({ printf '%s\n' \
  orchestrator/workflow_lisp/procedure_identity_retirement.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json \
  tests/fixtures/workflow_lisp/procedure_identity_retirement/pre_edit_scan.json \
  tests/fixtures/workflow_lisp/procedure_identity_retirement/old/identity_baseline.json; } | LC_ALL=C sort)"
test "$(git diff --cached --name-only | LC_ALL=C sort)" = "$expected"
```

Inspect the cached diff, then commit. Do not stage pilot evidence, owner
records, run roots, or unrelated dirty paths.

### Task 4: Resume Task 4A evidence assembly without a live scan

**Files:**
- Modify: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/retirement_record.json`
- Modify: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/identity_delta.json`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Later modify after validation: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json`

- [ ] **Step 1: Add the pilot binding from immutable bytes**

Bind the record to `pre_edit_known_store_scans.json.old_identity_query`, its file digest, 64-entry canonical query digest/count, exact 72-membership domain-map digest, frozen baseline path/digest, and old source path/digest. Do not rewrite any frozen evidence.

- [ ] **Step 2: Regenerate the full domain-qualified identity delta**

Require the retired query plus production-derived identities to match the complete old/new table exactly. Preserve all production-derived preserved/new rows and all reviewed retired domain memberships.

- [ ] **Step 3: Run deterministic replay only**

Require the live environment switch to be absent, then run the exact migration
replay selector with its scanner stub and the focused generic validator module:

```bash
test -z "${ORCHESTRATOR_RUN_LIVE_PROCEDURE_RETIREMENT_VALIDATION+x}"
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_retirement_record_replays_final_scan_evidence
```

Verify exact two retained completed run IDs, unchanged protected roots,
unchanged final owner record and scan digests, empty scratch, and no live
environment variable before and after.

- [ ] **Step 4: Complete both independent pre-live reviews**

Obtain ordered specification and quality/safety approval for the assembled record and replay. Do not invoke the live selector until both approve.

- [ ] **Step 5: Continue the parent Task 4A plan**

After both reviews, execute the one authorized scanner-only live validator, produce its retained result, complete the independent retirement-record review, and then publish the exact pending hold-release record. Pause at that owner boundary; do not release the hold or perform later workflow/store mutations.
