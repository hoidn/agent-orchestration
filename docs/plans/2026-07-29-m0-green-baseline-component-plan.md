# M0 Green Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the already-started substrate M0 tranche with a truthful green
baseline, without expanding it into a language feature or beginning M1.

**Architecture:** Preserve the landed M0 behavior fixes, disposition the
unsafe export-only entry-bootstrap rule replacement without changing runtime
eligibility, add the replacement-rule pointer required by design principle 28,
repair the two checked-in metadata drifts exposed by those landed changes, and
run the exact green-baseline gates. M0 owns no new abstraction: the route
registry receives two ordinary fixture rows and the retirement reproduction
test asserts and peels only the exact diagnostic metadata absent from its
frozen historical artifacts.

**Tech Stack:** Python 3.13, pytest, Workflow Lisp Stage-3/WCC M4 compiler,
JSON route-readiness and retirement fixtures, Git.

---

## Authority, selection, and bounds

This component plan executes Phase M0 from
`docs/plans/2026-07-26-substrate-maintenance-track.md`. The owner already
selected and started M0; this plan supplies the component plan that the track
requires before the remaining work proceeds.

The following M0 work is already committed and must be preserved:

| M0 item | Commit(s) | Disposition |
| --- | --- | --- |
| Port three deleted-loader test modules | `e1594634` | landed |
| Adjudicate retained output/IR failures | `b16a49f5` | landed |
| Name the entry-bootstrap refusal | `76452fdc` | landed |
| Extern-operand fork | `6620f186` | landed |
| Dead semantic-adapter local | `ae67ea16` | landed |
| `let-proc` hidden-context equivalence | `6182ae48`, `7dcd177c` | landed |
| Remove local capture-window hook/marker | local paths absent at plan capture | satisfied by absence; do not recreate |

The remaining fresh narrow baseline at plan capture is:

```text
4 failed, 347 passed in 14.72s
```

The four failures are exactly the two route-readiness nodes caused by the two
landed `let-proc` fixtures and the old/new production-artifact reproduction
nodes caused by the newly serialized `WorkflowSignature.entry_bootstrap_gate_denial`.

Hard bounds:

- do not edit Q5, L0–L5, provider-adapter, or provider-isolation behavior;
- do not begin or prepare M1;
- do not add a new Workflow Lisp annotation, registry, type, schema, or
  eligibility mechanism;
- do not weaken the unrelated-exported-sibling negative control;
- do not rewrite the frozen retirement artifacts, their hashes, identity
  tables, queries, scans, source files, or evidence;
- do not perform new security feature work; the already-landed loader-test
  ports are verification inputs only; and
- do not convert an xdist-only shared-repository digest race into an L-series
  behavior change. The M0 contract's authoritative green gate is the bare
  serial `pytest -q` run; the repository-standard xdist run remains an
  additional disclosed control.

## Entry-bootstrap disposition

Three approaches were evaluated:

1. **Export-only eligibility:** rejected. The existing
   `test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unrelated_exported_sibling_in_item_ctx_proof_module`
   control proves that an exported selected sibling is not necessarily an
   authorized hidden-context bootstrap route.
2. **A new authored eligibility annotation:** deferred. It would be a new
   language contract and taxonomy, disproportionate to M0's diagnosability
   objective.
3. **Retain the fail-closed name gate and its coded refusal:** selected. The
   landed diagnostic makes the current rule actionable without widening
   eligibility. M0 adds the stable replacement-rule identifier
   `explicit_entry_bootstrap_eligibility` and a pointer to this disposition,
   as required by design principle 28. A future replacement requires its own
   accepted design naming a property that distinguishes the legitimate
   wrappers from the negative control.

This is a disposition, not a claim that a name allowlist is the desired
long-term model. It closes the unsafe Task 2 instruction in
`docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md` without changing
entry-bootstrap eligibility.

---

### Task 1: Record the reviewed component plan and refusal disposition

**Files:**

- Create: `docs/plans/2026-07-29-m0-green-baseline-component-plan.md`
- Modify: `docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] **Step 1: Obtain ordered plan reviews**

Review this exact plan candidate first for specification compliance and then
for execution quality. Required verdicts:

1. `M0_PLAN_SPEC_APPROVED`
2. `M0_PLAN_QUALITY_APPROVED`

If either review changes a byte, restart both reviews against the corrected
candidate. Do not re-review unchanged Q5 or L-series surfaces.

- [x] **Step 2: Record the Task 2 disposition**

Change the refusal plan's overall status to active with only the
replacement-rule diagnostic pointer pending. Replace Task 2's blocked status
with an accepted disposition that records:

- export-only replacement rejected by the named negative control;
- a new explicit property is deferred to a separate accepted design;
- the fail-closed name gate and `entry_bootstrap_name_gate_denied` note remain;
- the diagnostic points to stable rule ID
  `explicit_entry_bootstrap_eligibility` and this disposition;
- no eligibility change occurs; and
- Task 3's already-recorded non-drift comparison remains applicable because
  the gate logic is unchanged.

Do not delete the incident history or the rejected alternatives.

- [x] **Step 3: Route M0 as selected and bounded**

Update the substrate track and `docs/index.md` to point to this component plan,
record M0 as selected/in progress, and keep M1 ineligible until M0's green gate
closes. Add routing assertions that:

- the component plan is routed;
- M0 is selected;
- M1 still requires completed M0 and its own component plan; and
- the refusal disposition does not claim an export-only rule shipped.

- [x] **Step 4: Run routing and refusal controls**

Run:

```bash
pytest -q \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_names_the_denied_gate_for_unexported_non_magic_name_entry_workflow \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unrelated_exported_sibling_in_item_ctx_proof_module \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_promoted_entry_emits_hidden_context_call_bindings \
  tests/test_workflow_lisp_build_artifacts.py::test_promoted_entry_runtime_context_inputs_stay_internal_and_appear_in_projection \
  tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context
```

Expected: all selected tests pass.

- [x] **Step 5: Commit the accepted plan and disposition**

Stage only the five files named in this task.

Suggested subject:

```text
Select M0 green baseline closure
```

---

### Task 2: Add the required replacement-rule pointer

**Files:**

- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Test: `tests/test_workflow_lisp_key_migrations.py`
- Test: `tests/test_resume_command.py`

- [ ] **Step 1: Write the two RED assertions**

Extend
`test_compile_stage3_entrypoint_names_the_denied_gate_for_unexported_non_magic_name_entry_workflow`
to require its secondary note to contain:

```text
entry_bootstrap_name_gate_denied
unexported-custom-entry
explicit_entry_bootstrap_eligibility
docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md
```

Extend
`test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unrelated_exported_sibling_in_item_ctx_proof_module`
to assert that the same coded note and replacement-rule ID accompany the
existing `workflow_signature_mismatch`. Do not alter its rejection
expectation.

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```bash
pytest -q \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_names_the_denied_gate_for_unexported_non_magic_name_entry_workflow \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unrelated_exported_sibling_in_item_ctx_proof_module
```

Expected before implementation: both fail because the replacement-rule
identifier/pointer is absent.

- [ ] **Step 3: Change only the diagnostic**

Keep `_selected_entry_hidden_context_omission_callees` byte-for-byte unchanged.
Extend `_entry_bootstrap_name_gate_denial` so its existing note ends with:

```text
replacement rule `explicit_entry_bootstrap_eligibility` is deferred to
docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md
```

The exact punctuation may be adjusted for one-line readability, but both the
stable identifier and path must be literal and behavior must remain
fail-closed.

- [ ] **Step 4: Run the eight-control bootstrap gate**

Run:

```bash
pytest -q \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_names_the_denied_gate_for_unexported_non_magic_name_entry_workflow \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unrelated_exported_sibling_in_item_ctx_proof_module \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_transitive_proof_wrapper \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_promoted_entry_emits_hidden_context_call_bindings \
  tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_runctx_only_entry_constructs_drainctx_in_language \
  tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context \
  tests/test_workflow_lisp_build_artifacts.py::test_promoted_entry_runtime_context_inputs_stay_internal_and_appear_in_projection \
  tests/test_resume_command.py::test_resume_force_restart_rebinds_only_public_inputs_for_promoted_entry_hidden_context
```

Expected: eight pass. Re-run the exact prior Task 3 boundary-projection
non-drift controls with:

```bash
pytest -q \
  tests/test_workflow_lisp_build_artifacts.py::test_promoted_entry_runtime_context_inputs_stay_internal_and_appear_in_projection \
  tests/test_workflow_lisp_build_artifacts.py::test_promoted_entry_private_exec_context_binding_metadata_drives_boundary_projection \
  tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_runctx_only_entry_constructs_drainctx_in_language \
  tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context
```

These selectors compile the production promoted routes and assert their
hidden-input boundary projections. Expected: four pass. Also inspect the exact
Task 2 source delta with:

```bash
git diff --unified=0 HEAD -- orchestrator/workflow_lisp/workflows.py
```

Expected before the Task 2 commit: the only production-code delta from the
accepted Task 1 head is the diagnostic-note text inside
`_entry_bootstrap_name_gate_denial`; the eligibility helper and accept/deny
branches are unchanged.

- [ ] **Step 5: Close the bounded refusal-plan status**

Before review, mark the refusal plan complete for its bounded diagnosability
objective: Task 1 named the denial, the amended Task 2 records the rejected
unsafe widening and points to its deferred replacement rule, and Task 3 proves
no promoted-route identity drift. This status change is part of the exact
candidate reviewed in Step 6.

- [ ] **Step 6: Obtain ordered task reviews and commit**

Required verdicts:

1. `M0_DIAGNOSTIC_POINTER_SPEC_APPROVED`
2. `M0_DIAGNOSTIC_POINTER_QUALITY_APPROVED`

The reviews bind the complete candidate, including the completed refusal-plan
status from Step 5. After both approve, commit those exact bytes.

Suggested subject:

```text
Point M0 entry refusal to its replacement rule
```

---

### Task 3: Register the two landed `let-proc` fixtures

**Files:**

- Modify: `docs/workflow_lisp_route_readiness_registry.json`
- Test: `tests/test_workflow_lisp_route_readiness.py`
- Test: `tests/test_workflow_lisp_design_delta_smoke.py`

- [ ] **Step 1: Preserve the RED baseline**

Run:

```bash
pytest -q \
  tests/test_workflow_lisp_route_readiness.py::test_checked_in_registry_loads_and_validates \
  tests/test_workflow_lisp_route_readiness.py::test_cli_route_readiness_check_valid_registry
```

Expected before the edit: two failures naming only:

```text
tests/fixtures/workflow_lisp/valid/design_delta_item_ctx_child_phase_reuse_let_proc.orc
tests/fixtures/workflow_lisp/valid/design_delta_item_ctx_child_phase_reuse_let_proc_in_proc.orc
```

- [ ] **Step 2: Append two ordinary registry rows**

Use the existing adjacent proc/proc-ref rows as the schema template. Add:

```json
{
  "copy_safety": "test_evidence_only",
  "evidence": [
    "tests/test_workflow_lisp_design_delta_smoke.py::test_registered_design_delta_fixture_compiles_directly[item-ctx-let-proc]"
  ],
  "lowering_route": "wcc_m4",
  "lowering_schema_version": 2,
  "path": "tests/fixtures/workflow_lisp/valid/design_delta_item_ctx_child_phase_reuse_let_proc.orc",
  "readiness_label": "leaf_compile_candidate",
  "route_label": "wcc_default",
  "surface_id": "tests.fixtures.workflow_lisp.valid.design_delta_item_ctx_child_phase_reuse_let_proc",
  "surface_kind": "test_fixture"
}
```

and the identical shape for
`design_delta_item_ctx_child_phase_reuse_let_proc_in_proc.orc` with evidence
ID `[item-ctx-let-proc-in-proc]` and the corresponding surface ID. Refresh
only the registry's `updated` date.

- [ ] **Step 3: Run the exact GREEN controls**

Run:

```bash
pytest -q \
  tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_design_delta_smoke.py::test_registered_design_delta_fixture_compiles_directly
python -m orchestrator workflow-lisp-route-readiness \
  --registry docs/workflow_lisp_route_readiness_registry.json \
  --check
```

Expected: tests pass; the CLI returns zero issues and `overall_pass: true`.

- [ ] **Step 4: Commit the registry repair**

Suggested subject:

```text
Register M0 let-proc route fixtures
```

---

### Task 4: Preserve frozen retirement artifacts across diagnostic metadata

**Files:**

- Modify: `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Test: `tests/test_workflow_lisp_procedure_identity_retirement.py`

- [ ] **Step 1: Preserve the RED baseline and semantic census**

Run:

```bash
pytest -q \
  tests/test_workflow_lisp_procedure_identity_retirement.py::test_checked_retirement_artifacts_reproduce_from_production_build
```

Expected before the edit: old and new both fail. Rebuild both sides into an
external temporary directory and compare them through the test's
`_canonical_production_artifact` projection. After Task 2, the complete
semantic delta must remain exactly:

```text
old typed workflow 0: entry_bootstrap_gate_denial = null
old typed workflow 1: entry_bootstrap_gate_denial = coded denial for `orchestrate` with replacement-rule pointer
new typed workflow 0: entry_bootstrap_gate_denial = coded denial for `orchestrate` with replacement-rule pointer
```

All other production artifacts must be canonically equal. Fail closed if the
delta contains any fourth row or any other field.

- [ ] **Step 2: Write an exact diagnostic-only projection**

Add a test-local helper that deep-copies a typed frontend artifact and removes
`signature.entry_bootstrap_gate_denial` only after asserting the complete
observed tuple. Its expected current tuples are:

```python
expected_by_side = {
    "old": (None, EXPECTED_ORCHESTRATE_DENIAL),
    "new": (EXPECTED_ORCHESTRATE_DENIAL,),
}
```

`EXPECTED_ORCHESTRATE_DENIAL` must include the coded rule, rejected
`orchestrate` value, stable `explicit_entry_bootstrap_eligibility` identifier,
and disposition path. Assert that the frozen checked artifacts contain no such
field. Apply this projection only to `typed_frontend_ast`; compare every other
artifact through the existing canonical projection unchanged.

Do not add `entry_bootstrap_gate_denial` to
`_canonical_production_artifact`'s general exclusions. Do not modify any
fixture or hash.

- [ ] **Step 3: Run exact both-direction checks**

Run:

```bash
pytest -q \
  tests/test_workflow_lisp_procedure_identity_retirement.py::test_historical_artifact_projection_excludes_only_persisted_surface_provenance \
  tests/test_workflow_lisp_procedure_identity_retirement.py::test_checked_retirement_artifacts_reproduce_from_production_build \
  tests/test_workflow_lisp_procedure_identity_retirement.py::test_production_artifact_diagnostic_projection_rejects_unexpected_delta
```

The new negative test must pass a wrong diagnostic value and an additional
unexpected signature field through the helper and assert both fail closed.
Expected: four pass (one historical projection, two reproduction parameters,
one negative).

- [ ] **Step 4: Run the retirement module**

Run:

```bash
pytest -q tests/test_workflow_lisp_procedure_identity_retirement.py
```

Expected: the complete module passes, including literal-hash validation,
production reproduction, identity-table coverage, tamper negatives, and
root-independent reproduction.

- [ ] **Step 5: Commit the exact reproduction projection**

Suggested subject:

```text
Preserve retirement fixtures across M0 diagnostics
```

---

### Task 5: Close M0 on fresh green evidence

**Files:**

- Modify: `docs/plans/2026-07-29-m0-green-baseline-component-plan.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: `docs/reports/2026-07-26-m0-decision-brief.md`
- Modify: `docs/index.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Create externally: `/home/ollie/.tmp/m0-green-baseline-20260729/`

- [ ] **Step 1: Run focused M0 ownership checks**

Run:

```bash
pytest --collect-only -q \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
pytest -q \
  tests/test_at61_at62_wait_for_path_safety.py \
  tests/test_cli_safety.py \
  tests/test_secrets.py \
  tests/test_workflow_output_contract_integration.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_design_delta_smoke.py \
  tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Expected: collection succeeds and the exact focused set passes with no
M0-owned failure. The safety/secrets modules are unchanged verification inputs
for the already-landed loader-test ports, not new security feature work.

- [ ] **Step 2: Run the repository-standard broad control in tmux**

Run from the repository root:

```bash
pytest -q -n 16 --dist=worksteal
```

Store the complete log and exit status under the external M0 evidence
directory. Any failure must be classified from fresh output. An xdist-only
repository-read-only digest race may be checked isolated, but it is not
silently removed, skipped, or reclassified as a product pass.

- [ ] **Step 3: Run the authoritative bare M0 gate in tmux**

Run:

```bash
pytest -q
```

The completion requirement is zero collection errors, zero failures, and no
known-failure-set comparison. Store the complete log, exit status, totals,
HEAD/tree, and SHA-256 under the external M0 evidence directory.

- [ ] **Step 4: Update durable status**

Only after the bare gate is green:

- mark M0 as an **implemented closure candidate with final reviews,
  exact-byte commit, and post-commit control pending** in the substrate track
  and this plan;
- replace the substrate track's stale M0 owner-decision list with the recorded
  rulings/dispositions;
- record the exact focused, xdist, and serial results without claiming an
  xdist failure passed;
- record L4 and Q4 external closure as already completed context without
  reopening their gates;
- keep M1 **ineligible and unselected** until the exact reviewed M0 candidate
  is committed and its post-commit control passes; and
- update routing tests to lock those statements.

- [ ] **Step 5: Obtain ordered final reviews**

Bind the exact candidate diff and external evidence hashes. Required verdicts:

1. `M0_FINAL_SPEC_APPROVED`
2. `M0_FINAL_QUALITY_APPROVED`

One ordered pass is sufficient absent a material finding. If a review requires
a byte change, apply it, rerun affected checks, and restart the ordered pair.

- [ ] **Step 6: Commit and run the post-commit control**

Suggested subject:

```text
Close M0 green baseline
```

After commit, run:

```bash
pytest -q \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py
```

Record the commit/tree and post-commit result in:

```text
/home/ollie/.tmp/m0-green-baseline-20260729/closure-verdicts.md
```

The external record must bind the ordered review verdicts and hashes, exact
commit/tree, broad-log hashes and exit statuses, and post-commit result. Only
that exact-tree record declares M0 complete and M1 eligible but unselected
pending its own reviewed component plan. Do not create a follow-up metadata
commit and do not start M1 inside this task.

---

## Completion gate

M0 is complete only when:

- all previously landed M0 commits remain present;
- the refusal gate is coded and fail-closed, while export-only widening remains
  rejected;
- the route-readiness registry validates with both `let-proc` fixtures;
- retirement production artifacts reproduce after an exact assertion of the
  three-row serialized diagnostic delta, while frozen artifacts remain
  unchanged;
- the bare full suite collects and passes with no retained-failure set;
- the xdist broad result is disclosed exactly;
- ordered final specification then quality reviews approve the exact closure
  candidate;
- the exact reviewed bytes are committed and the post-commit focused control
  passes;
- the external closure record binds those facts and declares M0 complete; and
- M1 is described as eligible but unselected pending its own component plan.
