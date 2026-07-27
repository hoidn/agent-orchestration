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

## Task 3: Verify no identity drift

The gate change must not alter generated hidden-input identities for the
already-promoted routes (`drain`, the retained public entries). Compare
compiled boundary projections for the two promoted `.orc` ports before and
after; byte-identical hidden-input contracts are the acceptance bar.

## Non-goals

- No repo-wide silent-denial sweep.
- No change to hidden-context bootstrap semantics, role metadata, or the
  supported context families.
- No prompt or workflow-surface changes.
