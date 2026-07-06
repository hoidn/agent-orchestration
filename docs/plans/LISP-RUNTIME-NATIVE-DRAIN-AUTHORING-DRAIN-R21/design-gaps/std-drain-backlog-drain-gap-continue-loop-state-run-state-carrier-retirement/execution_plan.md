# Std Drain Gap-Continue Loop-State Run-State Carrier Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Retire the `run-state` compatibility carrier from the shared `std/drain::backlog-drain` `GapResult.CONTINUE` and `DrainLoopState` construction path so the dependent compatibility-carrier retirement slice can rerun its parent-drain compile proof without stopping in the deferred shared lane.

**Architecture:** Verify-first. Fresh working-tree inspection shows the carrier retirement largely landed as uncommitted work (carrier-free `GapResult`/`DrainLoopState`, no `run-state` plumbing in `drain_stdlib.py`, focused guards present), so Task 1 proves the current state with fresh command output before any edit. Only if a lane is red does Task 2 implement the bounded retirement. What this makes harder later: durable drain outcome state now lives exclusively in the `drain-run-state` resource transition lane, so any future consumer that wants drain state at the child-call boundary must add a typed field to the declared result unions rather than reviving a carrier.

**Tech Stack:** Workflow Lisp `.orc`, shared compile/shared-validation route, `python -m orchestrator compile`, `pytest`, `rg`

---

## Fixed Inputs And Authority

- `docs/index.md`
- `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` (Sections 2.4, 3.4 — deciding authority for carrier retirement)
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 6.1, 12.1, 12.2)
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/std-drain-backlog-drain-gap-continue-loop-state-run-state-carrier-retirement/implementation_architecture.md`

Acceptance authority, highest first: the implementation architecture's
required capability, ownership, allowed/forbidden shapes, and acceptance
conditions; then owner-lane Sections 3.4/2.4; then target design Section 12.1.

## Current Causal State

Plan from the recorded failure chain, not from the assumption that the lane is
still red:

1. The dependent slice `workflow-lisp-design-delta-compatibility-carrier-retirement`
   was blocked `PREREQUISITE_GAP_REQUIRED` on this gap: its parent-drain
   direct compile failed closed with `[record_field_unknown] unknown field
   'run-state'` at the `continued.run-state` read inside `DrainLoopState`
   construction in `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`,
   and its approved plan forbade touching that deferred shared lane.
2. The working tree has since accumulated uncommitted shared-lane work: the
   `GapResult` union is `(CONTINUE)` with no fields, `DrainLoopState` carries
   only `items-processed` and `progress-report-path`, and
   `orchestrator/workflow_lisp/drain_stdlib.py` has no `run-state` plumbing.
3. Therefore the likely remaining work is fresh verification evidence, guard
   alignment if any focused selector is red, and confirmation that the
   `record_field_unknown` failure class is gone from the parent-drain compile.

## Scope Guards

- Do not touch the selector-`BLOCKED` lane (retired sibling gap) beyond keeping
  its guards green.
- Do not edit Design Delta family `.orc` sources or the Design Delta checked
  manifests (`transition_authoring.json`, `boundary_authority.json`,
  `value_flow_census.json`, `consumer_rendering_census.json`,
  `reference_family_*`); those lanes are owned by sibling gaps.
- Do not weaken `record_field_unknown`, `workflow_call_signature_erased`, or
  any fail-closed validation.
- Do not reintroduce `run-state` / `run_state_path` on any public stdlib drain
  shape or the `gap-drafter` boundary.
- Do not add compiler branches naming `std/drain`, `backlog-drain`, or drain
  concepts.
- Completion requires fresh command output; inspection alone is insufficient.

## File Map

Owned (modify only if Task 1 proves a lane red):

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- `tests/test_workflow_lisp_drain_stdlib.py`

Guard suites (read/run):

- `tests/test_workflow_lisp_resume_plumbing_retirement.py`
- `tests/test_workflow_lisp_value_flow_census.py`

Read-only dependent-route fixtures:

- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`

## Task 1: Prove The Current Carrier State With Fresh Evidence

- [ ] **Step 1: Run the focused gap-continue carrier-rejection guard**

```bash
pytest "tests/test_workflow_lisp_drain_stdlib.py::test_workflow_ref_resolution_rejects_custom_union_run_state_carriers[gap_continue_run_state]" -q
```

Expected: pass — a fixture that re-adds `(run-state StateExisting)` to
`GapResult.CONTINUE` fails closed with `workflow_call_signature_erased`.

- [ ] **Step 2: Run the target-contract source guard**

```bash
pytest tests/test_workflow_lisp_drain_stdlib.py::test_backlog_drain_target_contract_removes_run_state_from_public_stdlib_shapes -q
```

Expected: pass — no `run-state` field in `DrainResult`, `DrainLoopTerminal`,
`DrainLoopState`, or the drain-result helper procs.

- [ ] **Step 3: Run the deterministic plumbing scans**

```bash
rg -n "acc__run-state|terminal__run-state|return__run-state|drain-run-state\.json" orchestrator/workflow_lisp/
rg -n "run-state" orchestrator/workflow_lisp/stdlib_modules/std/drain.orc
```

Expected: the first scan returns nothing; the second matches only the
`drain-run-state` resource declaration and its `:resource drain-run-state`
transition references — no `(run-state ...)` record/union field and no
`continued.run-state` read.

- [ ] **Step 4: Run the shared stdlib and retirement guard suites**

```bash
pytest tests/test_workflow_lisp_drain_stdlib.py -q
pytest tests/test_workflow_lisp_resume_plumbing_retirement.py -q
```

Expected: green.

- [ ] **Step 5: Prove the dependent compile failure class is gone**

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: the compile must not fail with `[record_field_unknown] unknown field
'run-state'` in `std/drain.orc`. Success, or a fail-closed stop on a later
checked-input gate owned by a sibling slice (for example boundary authority or
reference-family conformance), both satisfy this gap; record the observed
first failure verbatim either way.

- [ ] **Step 6: Route on the evidence**

If Steps 1-5 all meet expectations, skip Task 2 and complete via Task 3. If
any step is red, classify the first red lane and proceed to Task 2 for that
lane only.

## Task 2: Implement The Bounded Retirement (Only For Lanes Task 1 Proved Red)

- [ ] **Step 1: Remove the carrier from the typed contracts**

In `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`: drop any
`run-state` field from `GapResult` variants and `DrainLoopState`, rewrite
gap/continue loop-state construction to loop-owned accumulator fields only
(`items-processed`, `progress-report-path`), and keep durable outcome
recording on the declared `record-drain-outcome` transition against the
`drain-run-state` resource.

- [ ] **Step 2: Remove the lowering plumbing**

In `orchestrator/workflow_lisp/drain_stdlib.py`: delete `acc__run-state`,
`terminal__run-state`, `return__run-state` plumbing and the
`state/drain-run-state.json` seed literal; preserve typed value return,
variant proof, and source-map lineage for the imported route.

- [ ] **Step 3: Align the focused guards**

Update `tests/test_workflow_lisp_drain_stdlib.py` so the carrier-rejection
parametrization and the target-contract source guard assert the carrier-free
contract. Do not delete or skip guards; align expectations to the live
contract only where the old expectation encoded the carrier.

- [ ] **Step 4: Re-run the Task 1 ladder from the top**

All Task 1 steps must now meet expectations.

## Task 3: Record Completion Evidence

- [ ] **Step 1: Re-run the full acceptance set and capture output**

Run every command in the architecture's Acceptance Conditions section and
capture fresh output. If a command's collection surface changed (added or
renamed tests), also run:

```bash
pytest --collect-only tests/test_workflow_lisp_drain_stdlib.py -q
```

- [ ] **Step 2: Confirm scope hygiene**

```bash
git status --porcelain
git diff --check
```

Expected: only owned files changed (none, if Task 2 was skipped); no
whitespace errors.

## Completion Criteria

- Every acceptance condition in the implementation architecture holds with
  fresh command output on the execution checkout.
- The parent-drain direct compile's first failure (if any) is not the
  `std/drain` run-state lane.
- No forbidden shape was introduced: no carrier revival, no gate weakening, no
  sibling-lane edits, no drain-named compiler branches.
