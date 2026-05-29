# ProcRef Authoring Docs Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the current Workflow Lisp authoring docs with the ProcRef and `bind-proc` behavior already implemented in the checkout, without reopening compiler or runtime scope.

**Architecture:** Treat accepted design docs plus current code/test evidence as the authority for "supported now", then update only the stale author-facing ProcRef guidance in `docs/lisp_workflow_drafting_guide.md`. Keep compile-time-only ProcRef boundaries explicit, verify adjacent discoverability surfaces before touching them, and use targeted ProcRef tests plus content checks as completion evidence.

**Tech Stack:** Markdown docs, `rg`, targeted `pytest` selectors, and current `orchestrator.workflow_lisp` implementation/test modules as verification evidence.

---

## Fixed Inputs

Treat these as authoritative for execution:

- `docs/index.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md`
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-authoring-docs-alignment/implementation_architecture.md`
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-static-surface-and-resolution/implementation_architecture.md`
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-bind-proc-specialization-lowering/implementation_architecture.md`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/2/design-gap-architect/work_item_context.md`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/2/design-gap-architect/check_commands.json`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/progress_ledger.json`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain/run_state-20260528T215013Z.json`

Reference current evidence before editing:

- `docs/lisp_workflow_drafting_guide.md`
- `orchestrator/workflow_lisp/README.md`
- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_lowering.py`

## Current Checkout Baseline

Assume this exact starting state:

- `docs/lisp_workflow_drafting_guide.md` still contains stale current-state ProcRef wording in two places:
  - the status section around lines 184-198 says only static `ProcRef[...]` and `(proc-ref ...)` are supported and explicitly defers `bind-proc`, residual specialization, and ProcRef call-through;
  - the usage guidance around lines 1141-1145 repeats the same deferral.
- `orchestrator/workflow_lisp/README.md` already describes `procedure_refs.py` as supporting compile-time `ProcRef[...]`, `bind-proc` partial application, specialization naming, and residual-signature validation while keeping ProcRef compile-time-only.
- `docs/index.md` already describes the ProcRef delta and work instructions as the active `ProcRef` / `bind-proc` partial-application tranche.
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain/run_state-20260528T215013Z.json` records `procref-static-surface-and-resolution` and `procref-bind-proc-specialization-lowering` as completed design gaps.
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/progress_ledger.json` is still empty; do not treat that as a missing implementation signal.

## Hard Scope Limits

Implement only this bounded slice:

- update the stale ProcRef implementation-status wording in `docs/lisp_workflow_drafting_guide.md`;
- update the later ProcRef usage guidance in that same guide so it reflects implemented `bind-proc`, residual specialization, and lexical ProcRef call-through;
- verify whether `orchestrator/workflow_lisp/README.md` and `docs/index.md` need narrow wording sync, and edit them only if a real wording conflict is found;
- preserve the compile-time-only ProcRef boundary and runtime-transport rejection in all author-facing wording.

Explicit non-goals:

- no compiler, lowering, runtime, fixture, or test changes;
- no new ProcRef semantics, diagnostics, or examples beyond the accepted design;
- no edits to historical implementation architectures or prior execution plans;
- no workflow YAML, prompts, provisioning, adapter, or smoke-run changes;
- no progress-ledger or run-state mutation.

## File Map

Modify:

- `docs/lisp_workflow_drafting_guide.md`

Modify only if verification proves actual wording drift:

- `orchestrator/workflow_lisp/README.md`
- `docs/index.md`

Use as read-only evidence:

- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_lowering.py`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain/run_state-20260528T215013Z.json`

## Locked Decisions

- ProcRef support remains compile-time-only. Do not imply runtime first-class procedures, closures, serialized procedure values, or dynamic runtime dispatch.
- Updated authoring guidance must state that the supported surface now includes `ProcRef[...]`, explicit `(proc-ref ...)`, keyword-only `bind-proc`, residual-signature specialization, forwarding via `ProcRef[...]` parameters, and lexical invocation through ProcRef-bound call heads.
- Updated authoring guidance must still forbid ProcRef transport through workflow outputs, records, unions, artifacts, ledgers, provider results, command results, and loop-carried runtime state.
- `README` and `docs/index.md` are verification targets first. Leave them untouched if they are already aligned.
- No orchestrator or demo smoke run is required because this slice is docs-only and does not change workflows, prompts, artifact contracts, or runtime behavior.

### Task 1: Lock The Supported-Now Evidence Before Editing Docs

**Files:**

- Read-only evidence: `docs/design/workflow_lisp_proc_refs_partial_application.md`
- Read-only evidence: `docs/design/workflow_lisp_frontend_specification.md`
- Read-only evidence: `docs/lisp_workflow_drafting_guide.md`
- Read-only evidence: `orchestrator/workflow_lisp/README.md`
- Read-only evidence: `orchestrator/workflow_lisp/procedure_refs.py`
- Read-only evidence: `orchestrator/workflow_lisp/typecheck.py`
- Read-only evidence: `orchestrator/workflow_lisp/compiler.py`
- Read-only evidence: `orchestrator/workflow_lisp/lowering.py`
- Read-only evidence: `tests/test_workflow_lisp_procedures.py`
- Read-only evidence: `tests/test_workflow_lisp_modules.py`
- Read-only evidence: `tests/test_workflow_lisp_lowering.py`
- Read-only evidence: `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain/run_state-20260528T215013Z.json`

- [ ] **Step 1: Confirm the accepted feature surface and the completed prior slices**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path

run_state = json.loads(Path("state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain/run_state-20260528T215013Z.json").read_text())
assert "procref-static-surface-and-resolution" in run_state["completed_design_gaps"]
assert "procref-bind-proc-specialization-lowering" in run_state["completed_design_gaps"]
print("completed prior ProcRef slices confirmed")
PY
```

Expected: prints `completed prior ProcRef slices confirmed`.

- [ ] **Step 2: Capture code-and-test evidence for implemented ProcRef behavior**

Run:

```bash
rg -n "bind-proc|residual|specializ|compile-time-only|proc ref" \
  orchestrator/workflow_lisp/procedure_refs.py \
  orchestrator/workflow_lisp/typecheck.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/lowering.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_lowering.py
```

Expected: matches show `bind-proc` handling, specialization/lowering logic, and dedicated ProcRef test coverage.

- [ ] **Step 3: Confirm the stale wording is limited to the authoring guide and not the adjacent discoverability surfaces**

Run:

```bash
rg -n -F \
  -e 'Do not rely on' \
  -e 'Do not write examples that depend on' \
  docs/lisp_workflow_drafting_guide.md \
  orchestrator/workflow_lisp/README.md \
  docs/index.md
```

Expected: only `docs/lisp_workflow_drafting_guide.md` matches these stale deferral phrases; `README` and `docs/index.md` may mention supported `bind-proc` behavior, but they should not match the stale guidance.

- [ ] **Step 4: Run the existing narrow ProcRef selectors as evidence for current support**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k "proc_ref or bind_proc" -q
pytest tests/test_workflow_lisp_modules.py -k "proc_ref or bind_proc" -q
pytest tests/test_workflow_lisp_lowering.py -k "proc_ref or specialization" -q
```

Expected: all selected ProcRef tests pass and provide fresh evidence that the documentation update describes real implemented behavior.

### Task 2: Rewrite Only The Stale Authoring Guide Surface

**Files:**

- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify only if Step 1.3 proves drift: `orchestrator/workflow_lisp/README.md`
- Modify only if Step 1.3 proves drift: `docs/index.md`

- [ ] **Step 1: Update the current implementation-status paragraph in the drafting guide**

Edit the ProcRef status block in `docs/lisp_workflow_drafting_guide.md` so it no longer says the supported surface stops at static references. The replacement wording must explicitly say that current support includes:

- `ProcRef[...]` type annotations;
- explicit `(proc-ref name)` literals;
- keyword-only `bind-proc` partial application;
- residual-signature specialization before lowering;
- lexical invocation through ProcRef-bound call heads;
- compile-time-only ProcRef transport rules.

Also remove `bind-proc` and residual specialization from the "Still deferred or future" bullet list while leaving the real remaining restrictions in place.

- [ ] **Step 2: Update the later usage guidance so examples can use the implemented ProcRef surface**

Edit the later ProcRef guidance block in `docs/lisp_workflow_drafting_guide.md` so it no longer forbids `bind-proc`, residual signatures, or call-through. The revised guidance should recommend `ProcRef[...]` for compile-time procedure composition while still warning that ProcRef values cannot cross runtime transport seams.

- [ ] **Step 3: Keep remaining unsupported boundaries explicit**

During the same edit, make sure the guide still clearly forbids:

- runtime first-class procedures or closures;
- provider-selected or command-produced procedure values;
- procedure values stored in workflow outputs, records, unions, artifacts, ledgers, provider results, command results, or loop-carried runtime state;
- dynamic runtime dispatch.

Do not add forward-looking claims beyond what the accepted delta and current implementation already support.

- [ ] **Step 4: Touch `README` or `docs/index.md` only if the earlier verification found a real mismatch**

If Task 1 showed that either adjacent surface contradicts the accepted delta or the updated guide wording, make the smallest wording-only sync edit needed. Otherwise, leave both files unchanged.

### Task 3: Prove The Updated Docs Match Implemented Behavior

**Files:**

- Modify: `docs/lisp_workflow_drafting_guide.md`
- Optional verify-only surfaces: `orchestrator/workflow_lisp/README.md`, `docs/index.md`

- [ ] **Step 1: Verify the stale deferral wording is gone from the current guide**

Run:

```bash
rg -n "Do not rely on|Do not write examples that depend on|residual signature specialization" \
  docs/lisp_workflow_drafting_guide.md
```

Expected: no matches for the stale ProcRef deferral wording.

- [ ] **Step 2: Verify the updated guide still exposes the compile-time-only restrictions**

Run:

```bash
rg -n "compile-time-only|runtime.*transport|dynamic runtime dispatch|provider-selected|command-produced" \
  docs/lisp_workflow_drafting_guide.md \
  orchestrator/workflow_lisp/README.md
```

Expected: matches remain visible for the compile-time-only boundary and the unsupported runtime ProcRef cases.

- [ ] **Step 3: Re-run the narrow ProcRef selectors after the doc change**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k "proc_ref or bind_proc" -q
pytest tests/test_workflow_lisp_modules.py -k "proc_ref or bind_proc" -q
pytest tests/test_workflow_lisp_lowering.py -k "proc_ref or specialization" -q
```

Expected: same passing selectors as Task 1. This confirms the documentation still matches current checked-in behavior.

- [ ] **Step 4: Check the final diff for bounded scope**

Run:

```bash
git diff -- docs/lisp_workflow_drafting_guide.md orchestrator/workflow_lisp/README.md docs/index.md
```

Expected: the diff is wording-only and limited to the planned doc surfaces; if `README` and `docs/index.md` were already aligned, only `docs/lisp_workflow_drafting_guide.md` should appear.

- [ ] **Step 5: Commit the bounded docs-alignment slice**

Run:

```bash
git add docs/lisp_workflow_drafting_guide.md orchestrator/workflow_lisp/README.md docs/index.md
git commit -m "docs: align ProcRef authoring guidance with implemented support"
```

Expected: one docs-only commit capturing the authoring-guide correction and any truly necessary sync edits.

## Acceptance Checklist

- [ ] `docs/lisp_workflow_drafting_guide.md` no longer claims `bind-proc`, residual specialization, or ProcRef call-through are unimplemented.
- [ ] The guide still states that ProcRef is compile-time-only and cannot cross runtime transport seams.
- [ ] `orchestrator/workflow_lisp/README.md` and `docs/index.md` were either verified as already aligned or received narrow wording-only sync edits.
- [ ] Targeted ProcRef pytest selectors passed before and after the doc change.
- [ ] Final diff stayed bounded to the selected docs-alignment gap.
