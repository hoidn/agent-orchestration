# Refusal Diagnosability Fixes Plan

**Status:** complete for its bounded diagnosability objective; not a competing
selector. Task 1 names the denial, Task 2 rejects unsafe export-only widening
while pointing to its deferred replacement rule, and Task 3 records no
promoted-route identity drift.

**Goal:** Apply design principle 28 ("Refusals Must Name Their Rule",
`docs/design/workflow_language_design_principles.md`) to the one known
violating gate, so the 2026-07-23 debugging class cannot recur there.

**Motivating incident:** entry-bootstrap context omission is gated on the
literal workflow-name allowlist
`{"entry", "drain", "promoted-entry-resume-plan-gate-wrapper"}`
(`orchestrator/workflow_lisp/workflows.py`, promoted-entry candidate
selection). The gate denies with a bare `return {}`; the surface error is a
misleading downstream `workflow_signature_mismatch` ("call is missing
required binding"). Diagnosis took a ninety-minute bisect. Selection-free
compiles take the exports branch and are unaffected.

**Scope guard:** three tasks below, nothing else. No registry, no recurring
audit, no new process artifacts. Other silent denial paths are fixed when
touched or when they cost a debugging session (principle 28's adoption rule),
not swept here.

## Task 1: Name the refusal

When the selected entry's local name causes the candidate-selection gate to
return no allowances, emit a coded diagnostic (suggested code:
`entry_bootstrap_name_gate_denied`) naming the rejected workflow name and the
accepted set, attached as a secondary note to any resulting
`workflow_signature_mismatch` on an omitted context binding. Add one negative
test asserting the note appears for a non-allowlisted entry name.

**Status: done.** `orchestrator/workflow_lisp/workflows.py`'s gate (function
renamed in code churn to `_selected_entry_hidden_context_omission_callees`,
still the same three-name literal set at the same behavior) now routes its
accept/deny decision through `_entry_bootstrap_name_gate_denial`, and
`build_workflow_catalog` stamps the resulting note onto the denied
workflow's `WorkflowSignature.entry_bootstrap_gate_denial` (new field). The
diagnostic actually surfaces from the typecheck-phase call-binding check
(`orchestrator/workflow_lisp/typecheck_calls.py`, the `missing_bindings`
raise, not the lowering-phase raise the plan's file pointer implied) via
`raise_error`'s new `notes` parameter — both `raise_error`
(`typecheck_context.py`) and lowering's `_compile_error`
(`orchestrator/workflow_lisp/lowering/context.py`) gained a `notes` kwarg for
this. New test:
`tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_names_the_denied_gate_for_unexported_non_magic_name_entry_workflow`.

## Task 2: Disposition the declared-property rule

**Accepted disposition (2026-07-29; implemented): no eligibility change.**
Export-only eligibility is rejected by
`tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unrelated_exported_sibling_in_item_ctx_proof_module`.
That control proves that an exported selected sibling is not necessarily
authorized for hidden-context bootstrap. A new explicit authored property is
deferred to a separate accepted design that must distinguish legitimate
wrappers from that negative control. The current fail-closed name gate remains,
as does its `entry_bootstrap_name_gate_denied` note. The completed
diagnostic-only change points that note to the stable replacement-rule ID
`explicit_entry_bootstrap_eligibility` and this disposition at
`docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md`. The gate logic is
unchanged, so Task 3's recorded non-drift comparison remains applicable.

**Original proposal (rejected):** The exports branch already implements the
broader candidate source used by selection-free compilation. The original Task
2 instruction proposed replacing the selected-entry name allowlist with that
rule (a selected exported entry qualifies; a selected non-exported entry does
not), preserving behavior for the three currently allowlisted names through a
general rule rather than by spelling. Its proposed tests were a positive
arbitrary-named exported entry with an omitted RunCtx-rooted call and a
negative non-exported selected entry retaining the Task 1 diagnostic. It also
called for the focused promoted-entry/hidden-context selectors plus one
selection-free and one selected compile of
`workflows/examples/review_revise_design_docs.orc`.

**Incident history and rejected alternatives (preserved):** The literal change
(export-based `_entry_bootstrap_name_gate_denial`, reusing a new
`_exported_workflow_names` helper) and both tests were drafted, then the full
focused selector set ran before commit. One pre-existing test regressed: the
named unrelated-exported-sibling control (fixture
`item_ctx_child_phase_reuse_leak_probe`, entry workflow
`unrelated-phase-entry`) went from a required raise to a clean compile. That
fixture explicitly exports an unrelated sibling workflow to prove that
selecting it as the compile entrypoint must still be denied hidden-context
bootstrap. In other words, the existing test encodes "exported is necessary
but not sufficient for a selected entry to qualify," directly contradicting
the original instruction. Both readings had a textual source, so the draft
change was reverted (`git restore`) rather than silently choosing policy.
Considered alternatives were: (a) implement the original instruction and
retire the unrelated-sibling expectation; (b) narrow a new property so export
alone is insufficient, for example through an independently declared
`allows_entry_bootstrap` property or promoted-route membership; or (c) retain
the name allowlist and land only its named diagnostic. The accepted
disposition selects (c) for this bounded plan and defers (b) to a separate
accepted design; (a) is rejected.

## Task 3: Verify no identity drift

The gate change must not alter generated hidden-input identities for the
already-promoted routes (`drain`, the retained public entries). Compare
compiled boundary projections for the two promoted `.orc` ports before and
after; byte-identical hidden-input contracts are the acceptance bar.

**Status: done, against Task 1's change.** The comparison brackets Task 1's
diagnostic-only change. It compiled
`workflows/library/verified_iteration_drain/drain.orc`
(`verified_iteration_drain/drain::drain`) and
`workflows/library/lisp_frontend_design_delta/drain.orc`
(`lisp_frontend_design_delta/drain::drain`) with `validate_shared=True`,
pulled each `workflow_boundary_projection` from `validated_bundles_by_name`,
and serialized both deterministically (`PYTHONHASHSEED=0`, sorted sets) once
against the current tree and once with
`orchestrator/workflow_lisp/{workflows.py,typecheck_calls.py,typecheck_context.py,lowering/context.py,lowering/workflow_calls.py}`
checked out to their pre-Task-1 commit (`ad5474c7`, immediately restored
afterward). The two dumps are byte-identical (matching MD5). Expected: Task 1
only threads a diagnostic note through the existing accept/deny decision and
does not change the gate's logic, so both `drain` routes' hidden-input
contracts were never at risk; this closes the loop with a runnable check
rather than inspection alone. This comparison remains applicable because the
gate logic is unchanged by Task 2's accepted disposition. Re-run it only if a
separate accepted design later changes entry-bootstrap eligibility.

## Non-goals

- No repo-wide silent-denial sweep.
- No change to hidden-context bootstrap semantics, role metadata, or the
  supported context families.
- No prompt or workflow-surface changes.
