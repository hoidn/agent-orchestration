# Refusal Diagnosability Fixes Plan

**Status:** queued; not a competing selector. Execute after the YAML-retirement
program's current task completes, or opportunistically as a small independent
fix between capture windows.

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

## Task 2: Replace the name key with the declared-property rule

The exports branch already implements the principled rule: exported workflows
qualify as entry-bootstrap candidates. Replace the name allowlist with that
rule for selected entries (a selected exported entry qualifies; a selected
non-exported entry does not), preserving current behavior for the three
currently allowlisted names via the general rule rather than by spelling.
Tests: positive (arbitrary-named exported entry with omitted RunCtx-rooted
call compiles), negative (non-exported selected entry still denied, with the
Task 1 diagnostic). Run the focused promoted-entry/hidden-context selectors
plus one selection-free and one selected compile of
`workflows/examples/review_revise_design_docs.orc`; then revert that
example's two build-artifact tests and README compile command to the selected
form if desired (optional follow-up, not required by this plan).

**Status: blocked on a design question — not implemented.** Drafted the
literal change (export-based `_entry_bootstrap_name_gate_denial`, reusing a
new `_exported_workflow_names` helper) and both tests, then ran the full
focused selector set before committing. One pre-existing test regressed:
`tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unrelated_exported_sibling_in_item_ctx_proof_module`
(fixture: `item_ctx_child_phase_reuse_leak_probe`, entry_workflow
`unrelated-phase-entry`) went from a required raise to a clean compile.
That fixture explicitly exports an unrelated sibling workflow specifically
to prove that *selecting* it as the compile entrypoint must still be denied
hidden-context bootstrap, even though it is exported — i.e. an existing test
encodes "exported is necessary but not sufficient for a selected entry to
qualify," which directly contradicts this task's literal instruction
("a selected exported entry qualifies," full stop). Both readings have a
textual source (the task's own wording vs. this pre-existing regression
test), so this is a real policy fork, not a mechanical detail — reverted the
draft change (`git restore`) rather than pick a side. Options for whoever
resolves this: (a) implement literally as specified and update/retire the
"unrelated sibling" test's expectation to match the new, intentionally
broader rule; (b) narrow the declared property so export alone is
insufficient — e.g. require the callee's hidden-context requirement to
independently mark `allows_entry_bootstrap`, or require membership in the
route-readiness registry's promoted set, in addition to being exported; (c)
keep the name allowlist for now and only land Task 1's diagnostic naming
(no rule change). Not resolved here.

## Task 3: Verify no identity drift

The gate change must not alter generated hidden-input identities for the
already-promoted routes (`drain`, the retained public entries). Compare
compiled boundary projections for the two promoted `.orc` ports before and
after; byte-identical hidden-input contracts are the acceptance bar.

**Status: done, against Task 1's change** (Task 2 is unimplemented, so
"before/after" here brackets Task 1 only). Compiled
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
rather than inspection alone. Re-run this comparison once Task 2 lands,
since Task 2's rule change is the one that can actually alter which
workflows qualify.

## Non-goals

- No repo-wide silent-denial sweep.
- No change to hidden-context bootstrap semantics, role metadata, or the
  supported context families.
- No prompt or workflow-surface changes.
