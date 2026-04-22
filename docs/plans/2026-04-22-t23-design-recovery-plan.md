# T23 Design Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover the EasySpin major-project drain by fixing the big-design open-findings carry-forward bug, rewriting the stalled T23 design into a convergent form, and rerunning T23 design review before resuming the drain.

**Architecture:** Keep workflow control deterministic and local to the tracked big-design phase. Patch only the carry-forward logic in `tracked_big_design_phase.yaml` and cover it with a narrow runtime regression. Treat the EasySpin T23 rewrite as a fresh design artifact driven by the tranche brief and updated roadmap, not as another incremental patch on the previous monolith.

**Tech Stack:** Agent-orchestration DSL v2.7 workflows, pytest, EasySpin project docs/specs, tmux-launched orchestrator runs in `ptycho311`.

---

### Task 1: Patch big-design finding carry-forward semantics

**Files:**
- Modify: `workflows/library/tracked_big_design_phase.yaml`
- Test: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add a failing regression that models lowercase review statuses**

Add a focused runtime test under `tests/test_major_project_workflows.py` that runs `tracked_big_design_phase.yaml` with mocked providers:
- first `ReviewBigDesign` writes a `REVISE` report whose findings include one lowercase `open` status and one resolved finding
- `ReviseBigDesign` rewrites the design
- second `ReviewBigDesign` receives the carried `open_findings` artifact and can assert that the unresolved finding was preserved

The test should fail against current workflow behavior because `open_findings` stays empty.

- [ ] **Step 2: Run the narrow test to confirm the failure**

Run:

```bash
pytest tests/test_major_project_workflows.py -k open_findings -q
```

Expected: FAIL because lowercase `open` findings are not carried.

- [ ] **Step 3: Patch the workflow extractor minimally**

In `workflows/library/tracked_big_design_phase.yaml`, update `ExtractOpenBigDesignFindings` so it preserves unresolved findings when `status` is one of:
- `STILL_OPEN`
- `NEW`
- `SPLIT`
- `open`

Keep the change narrow; do not redesign the loop contract in this pass.

- [ ] **Step 4: Re-run the narrow test**

Run:

```bash
pytest tests/test_major_project_workflows.py -k open_findings -q
```

Expected: PASS.

- [ ] **Step 5: Run the broader major-project workflow selectors**

Run:

```bash
pytest tests/test_major_project_workflows.py -q
```

Expected: PASS.


### Task 2: Rewrite the stalled EasySpin T23 design cleanly

**Files:**
- Modify: `/home/ollie/Documents/EasySpin/docs/plans/pytorch-port-roadmap/T23-full-resonance-helper-expansion-design.md`
- Read: `/home/ollie/Documents/EasySpin/docs/plans/pytorch-port-roadmap/tranches/T23-full-resonance-helper-expansion-brief.md`
- Read: `/home/ollie/Documents/EasySpin/docs/plans/pytorch-port-roadmap.md`
- Read: `/home/ollie/Documents/EasySpin/docs/specs/t21-full-spice-parity-ledger.json`
- Read: `/home/ollie/Documents/EasySpin/docs/specs/pytorch-cw-epr.md`
- Read: `/home/ollie/Documents/EasySpin/docs/specs/pytorch-remaining-api.md`

- [ ] **Step 1: Read the controlling T23 inputs and current failure**

Re-read:
- the T23 tranche brief
- the current roadmap sections that govern T23/T24/T26 handoff
- the latest T23 review report

Capture the exact public-contract decisions that must be fixed:
- `resfields_eig` excitation contract
- helper parser/default semantics

- [ ] **Step 2: Replace the design with a clean draft, not another incremental patch**

Rewrite `T23-full-resonance-helper-expansion-design.md` so it has one authoritative contract section for each of:
- accepted helper interfaces
- source-backed defaults vs truly required inputs
- output arity / shaping
- helper taxonomy / runtime identifiers
- downstream handoff constraints

Avoid repeating the same normative decisions across multiple sections unless one section references the authoritative one directly.

- [ ] **Step 3: Run local document hygiene**

Run:

```bash
git -C /home/ollie/Documents/EasySpin diff --check -- docs/plans/pytorch-port-roadmap/T23-full-resonance-helper-expansion-design.md
```

Expected: no diff-hygiene errors.


### Task 3: Rerun T23 big-design review as a standalone recovery step

**Files:**
- Use existing workflow: `workflows/library/tracked_big_design_phase.yaml`
- Use existing EasySpin state root: `/home/ollie/Documents/EasySpin/state/easyspin-pytorch-port/tranche-drain/items/easyspin-pytorch-port/T23-full-resonance-helper-expansion/big-design-phase`

- [ ] **Step 1: Launch a standalone T23 big-design-phase run in tmux under `ptycho311`**

Use a tmux-launched command from `/home/ollie/Documents/EasySpin` with:
- `source /home/ollie/miniconda3/etc/profile.d/conda.sh`
- `conda activate ptycho311`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration`
- `python -m orchestrator run ... --debug`

Pass the explicit inputs needed by `tracked_big_design_phase.yaml`:
- `state_root`
- `brief_path`
- `project_brief_path`
- `project_roadmap_path`
- `tranche_manifest_path`
- `design_target_path`
- `design_review_report_target_path`

- [ ] **Step 2: Monitor until T23 design review returns a decision**

Use tmux pane capture and the run `state.json`. If the decision is `REVISE`, inspect the report, revise the T23 design directly, and rerun the standalone big-design phase again. Do not relaunch the full drain yet.

- [ ] **Step 3: Stop only when the standalone T23 design phase approves**

Success condition:
- `design_review_decision.txt` is `APPROVE`
- `artifacts/review/...T23...design-review.json` has no unresolved high findings


### Task 4: Resume the major-project drain from the recovered T23 state

**Files:**
- Reuse run inputs from EasySpin manifest/state

- [ ] **Step 1: Relaunch the drain from manifest after T23 design approval**

Preferred path:
- start a fresh `major_project_tranche_drain_from_manifest_v2_call.yaml` run from the existing manifest, since T37A and T38 are already recorded completed in the manifest

Do not restart from roadmap generation.

- [ ] **Step 2: Confirm the selector still chooses T23 next**

Verify the first selected tranche is still `T23-full-resonance-helper-expansion`.

- [ ] **Step 3: Verify the drain enters plan phase instead of re-failing in big design**

Expected:
- `RunBigDesignPhase` completes
- `AssertBigDesignApproved` passes
- the workflow advances into `RunPlanPhase`


### Task 5: Final verification and recording

**Files:**
- Modify if needed: `docs/index.md`

- [ ] **Step 1: Re-run targeted orchestration verification in this repo**

Run:

```bash
pytest tests/test_major_project_workflows.py -q
```

- [ ] **Step 2: Record what changed and the recovery evidence**

Be ready to report:
- the workflow bug and exact fix
- the T23 standalone approval result
- the drain run id and resumed phase

- [ ] **Step 3: Stage only scoped files**

Stage only:
- the workflow/test fix in `agent-orchestration`
- the rewritten T23 design in `EasySpin`
- any directly relevant generated review artifacts if they are meant to be tracked
