# Reference-Family Parity Evidence Binding Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Make the Design Delta reference-family conformance profile's parity lane validate cleanly against the live checkout so the direct parent-drain compile no longer fails with `reference_family_conformance_invalid: reference_family_parity_report_invalid`, without hand-editing runtime-owned `artifacts/work/**` evidence or weakening the conformance gate.

**Architecture:** Verify-first. Fresh read-only probes show the parity report set was regenerated today by its owning harness and both fail-closed sub-validations (`validate_report_for_target`, `parse_parity_markdown_metadata`) accept the current checked reports, while the bound evidence root has advanced to a newer drain run — so Task 1 proves the full profile end to end with fresh command output before any edit. Only if a lane is red does Task 2 repair, ordered by ownership: regenerate checked parity reports through the harness first, then reconcile the `parity_targets.json` contract, then (last resort, generic only) evidence routing. What this makes harder later: the conformance profile binds to the newest finished drain run's evidence, so every future run that finishes with new gap outcomes must leave summary/inventory evidence the profile can reconcile, or the next compile fails closed.

**Tech Stack:** reference-family conformance profile, migration-parity harness, `python -m orchestrator compile`, `pytest`, `rg`

---

## Fixed Inputs And Authority

- `docs/index.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 8.4, 12.1, 13.4)
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_command_adapter_contract.md` (fail-closed checked-evidence discipline)
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-runtime-native-drain-reference-family-parity-evidence-binding-repair/implementation_architecture.md`

Acceptance authority, highest first: the implementation architecture's
evidence-binding mechanism, ownership, allowed/forbidden shapes, and
acceptance conditions; then target design Sections 8.4/12.1/13.4; then the
command-adapter contract.

## Current Causal State

1. The dependent slice
   `workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`
   cleared its checked-manifest trio; the direct compile then advanced to
   `[reference_family_conformance_invalid] ... reference_family_parity_report_invalid`,
   reported against the then-latest versioned drain root's runtime-owned
   drain-summary evidence — outside that slice's editable surface.
2. The conformance profile binds evidence to the newest versioned drain root
   with a finished drain-summary and validates the checked parity report set
   under `artifacts/work/review-parity-check/` fail-closed.
3. The parity report set was regenerated today by its owning harness, and
   read-only probes show the JSON gate validation and markdown metadata both
   accept the current reports (valid non-promotable row,
   `primary_surface: yaml`).
4. The bound evidence root has advanced since the blocked attempt, so the
   remaining risk is profile lanes that reconcile against the newly bound
   root (completed-gap inventory, per-gap summaries, architecture-index
   coverage), not the parity sub-validations themselves.
5. Therefore the likely remaining work is fresh end-to-end verification and,
   only if a lane is red, the bounded ownership-ordered repair in Task 2.

## Scope Guards

- Do not hand-edit anything under `artifacts/work/**`; runtime-owned evidence
  is regenerated through its owning harness only.
- Do not weaken, bypass, or downgrade `reference_family_conformance_invalid`,
  `reference_family_parity_report_invalid`, or
  `reference_family_parity_report_missing`.
- Do not author gate-owned primary-surface fields into parity reports, and do
  not manufacture promotion eligibility for the legitimately non-promotable
  `design_delta_parent_drain` row.
- Do not edit sibling-owned checked manifests (`boundary_authority.json`,
  `value_flow_census.json`, `consumer_rendering_census.json`,
  `transition_authoring.json`, `resume_plumbing_retirement.json`).
- Do not add Design Delta-specific branches to shared conformance/build
  surfaces.
- Completion requires fresh command output; inspection alone is insufficient.

## File Map

Owned (modify only if Task 1 proves a lane red):

- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
  (the `design_delta_parent_drain` target row only)
- `orchestrator/workflow_lisp/reference_family_conformance.py` (generic
  defect repair only, last resort)
- `orchestrator/workflow_lisp/build.py` (evidence-path resolution only,
  generic defect repair only, last resort)
- `tests/test_workflow_lisp_reference_family_conformance.py`
- `tests/test_workflow_lisp_build_artifacts.py` (focused reference-family
  guards only)

Regenerated through their owning harness (never edited in place):

- `artifacts/work/review-parity-check/design_delta_parent_drain.json`
- `artifacts/work/review-parity-check/design_delta_parent_drain.md`
- `artifacts/work/review-parity-check/index.json`

Read-only evidence and gate surfaces:

- `orchestrator/workflow_lisp/migration_parity.py`
- the newest versioned drain root's `drain/run_state.json` and
  `drain-summary.json` plus its per-gap summary artifacts (bound
  automatically by the resolver)

## Task 1: Prove The Current Conformance State With Fresh Evidence

- [ ] **Step 1: Run the dedicated conformance suite**

```bash
pytest tests/test_workflow_lisp_reference_family_conformance.py -q
```

Expected: green (fixture-level contracts, including the parity rejection
lanes).

- [ ] **Step 2: Run the focused build-artifact reference-family selectors**

```bash
pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_reference_family_conformance_profile \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_reference_family_invalid_parity_report \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_reference_family_malformed_parity_markdown \
  -q
```

Expected: 3 passed — the live-evidence profile passes and the fail-closed
rejection contracts hold.

- [ ] **Step 3: Prove the compile gate progression**

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: the compile must not fail with
`[reference_family_conformance_invalid]`. Success, or a fail-closed stop on a
different sibling-owned gate, both satisfy this gap; record the observed
first failure verbatim either way.

- [ ] **Step 4: Route on the evidence**

If Steps 1-3 all meet expectations, skip Task 2 and complete via Task 3. If a
reference-family lane is red, classify which evidence input the diagnostic
names (parity JSON, parity markdown, parity index, drain-summary binding,
per-gap summaries, architecture-index coverage) and proceed to Task 2 for
that input only. If the failure is a different gate class, stop and record
the new first failing causal defect instead of expanding this slice.

## Task 2: Repair By Ownership Order (Only For Lanes Task 1 Proved Red)

- [ ] **Step 1: Regenerate the checked parity report set first**

If the diagnostic names the parity JSON/markdown/index: regenerate the report
set through the migration-parity harness (the `run_migration_parity` runner
surface in `orchestrator/workflow_lisp/migration_parity.py`, selecting the
`design_delta_parent_drain` target) so the checked reports describe the live
checkout. Do not edit report files by hand.

- [ ] **Step 2: Reconcile the checked parity-targets contract**

If validation still rejects the regenerated report: correct only the
`design_delta_parent_drain` target row in
`workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
where its declared evidence contract (evidence commands, required artifacts,
accepted differences) provably drifted from the live route.

- [ ] **Step 3: Repair evidence routing only as a generic last resort**

If the diagnostic shows the profile binding to the wrong evidence root or
mis-loading a valid input: repair the resolver
(`_resolve_reference_family_evidence_paths` in
`orchestrator/workflow_lisp/build.py`) or the evidence loading in
`orchestrator/workflow_lisp/reference_family_conformance.py` generically,
with a behavioral test in
`tests/test_workflow_lisp_reference_family_conformance.py` or the focused
build-artifact suite proving the rule. No Design Delta-specific branches.

- [ ] **Step 4: Re-run the Task 1 ladder from the top**

All Task 1 steps must now meet expectations.

## Task 3: Record Completion Evidence

- [ ] **Step 1: Re-run the full acceptance set and capture output**

Run every command in the architecture's Acceptance Conditions section and
capture fresh output. If tests were added or renamed, also run:

```bash
pytest --collect-only tests/test_workflow_lisp_reference_family_conformance.py tests/test_workflow_lisp_build_artifacts.py -q
```

- [ ] **Step 2: Confirm scope hygiene**

```bash
git status --porcelain
git diff --check
```

Expected: only owned files changed (none, if Task 2 was skipped); no
whitespace errors; no in-place edits under `artifacts/work/**` other than
harness-regenerated parity outputs; sibling-lane checked manifests untouched.

## Completion Criteria

- Every acceptance condition in the implementation architecture holds with
  fresh command output on the execution checkout.
- The parent-drain direct compile's first failure (if any) is not the
  reference-family parity lane.
- The fail-closed contract is intact: invalid parity reports and malformed
  parity markdown still fail, and no gate was weakened or bypassed.
