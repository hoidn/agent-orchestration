# User-Facing YAML Retirement Program Plan (Tranche 6, steps 2–6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 4–7 carry explicit gates — check the gate before dispatching.

**Goal:** Retire YAML as a user-facing workflow authoring surface; `.orc` becomes the only authoring format, while the converged executable-IR runtime and the shared surface-validation core remain unchanged.

**Architecture:** Four ungated enabling tasks (language-gap list, dashboard typed-IR migration, loader split, deprecation surface) followed by gated per-family promotion through the existing migration-parity machinery and a final deletion sweep. Nothing in this plan invents new promotion infrastructure — `migration_parity.py`'s kernel, `parity_targets.json`, and the route-readiness registry are the engine.

**Steering decision (user, 2026-07-07):** YAML-surface retirement is a program desideratum. The design-delta family endgame is promote-`.orc`-then-delete-YAML. One recorded sub-decision remains open: whether `verified_iteration_drain` gets its own `.orc` port or is absorbed by the promoted design_delta family — settle it at Task 5, family 2.

## Entry gate

- `docs/workflow_yaml_estate_triage.md` must exist first (produced by `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md` Task 13) — it is this program's work-list. Do not start this plan before that triage doc exists.
- The drain migration plan (`docs/plans/2026-07-07-drain-migration-g8-retirement.md`) exists; its phases gate Task 5's drain-family promotions.

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- The working tree may contain the user's in-flight work. **Stage by explicit path only.** Never `git add -A`, `git add -u`, or `git commit -a`.
- Commit messages: short imperative sentence, repo style. No conventional-commit prefixes, no mention of Claude/Claude Code, no Co-Authored-By trailers.
- No worktrees. Never `--no-verify`.
- Narrowest pytest selectors first; fresh output is the verification evidence. Workflow/prompt/artifact-contract changes additionally rerun one orchestrator/demo smoke.
- Do not touch `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` directories (compile-evidence inputs).
- Out of scope for "user-facing retirement": internal/debug YAML (`emit_debug_yaml` artifacts, persisted run metadata). Those are not authoring surfaces.
- Anchors verified 2026-07-07; re-verify by name before each task.

---

### Task 1: Language-gap list (`.orc` vs YAML feature parity) — UNGATED

The final deletion (Task 7) is gated on this list being empty or explicitly waived. Known member: **native bounded loops** — `cycle_guard_demo` is pinned `eligible_for_primary_surface: false` with reason "demo-only until native bounded-loop parity is intentionally designed later" (see `artifacts/work/review-parity-check/cycle_guard_demo.json` and `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`).

**Files:**
- Create: `docs/workflow_yaml_orc_gap_list.md`

- [ ] **Step 1: Enumerate the YAML feature surface**

The authored YAML surface is what `orchestrator/loader.py` validates/normalizes plus the typed step kinds. Collect:
```bash
grep -n "def _validate_\|def _normalize_" orchestrator/loader.py
python -c "from orchestrator.workflow.surface_ast import SurfaceStepKind; print([k.value for k in SurfaceStepKind])"
```

- [ ] **Step 2: Enumerate the `.orc` form surface**

```bash
python -c "
from orchestrator.workflow_lisp import form_registry
import inspect
src = inspect.getsource(form_registry)
" 2>/dev/null || grep -n "FormKind\|register_form\|\"remove_by\"" orchestrator/workflow_lisp/form_registry.py | head -40
```
Cross-check with `docs/capability_status_matrix.md` (the repo's implemented/partial/designed ledger) — do not re-derive what it already records.

- [ ] **Step 3: Write the gap list**

For each YAML-expressible feature with no `.orc` equivalent, one entry: feature, evidence (workflow file using it, from the triage table), and a decision field with exactly one of: `design` (link the design doc that must own it — native bounded loops goes here), `drop` (feature retired with its last YAML user), `wait` (blocked on a named gate). No entry may read "TBD" — `wait` with a named gate is the honest unknown.

- [ ] **Step 4: Commit**

```bash
git add docs/workflow_yaml_orc_gap_list.md
git commit -m "Add yaml to orc language gap list"
```

---

### Task 2: Move the dashboard off raw-YAML structure reads — UNGATED

`dashboard/server.py` re-reads workflow YAML and re-classifies steps with an untyped parallel classifier: `_read_workflow_yaml_for_structure` (:1898-1924) and `_workflow_step_kind` (:2036-2051), duplicating `SurfaceStepKind`/`ExecutableNodeKind` logic. `dashboard/projection.py:19,150` already reaches `WorkflowLoader` — the typed path exists.

**Files:**
- Modify: `dashboard/server.py` (or the dashboard module root discovered in Step 1)

- [ ] **Step 1: Verify anchors and find the callers**

```bash
grep -rn "_read_workflow_yaml_for_structure\|_workflow_step_kind" dashboard/ | grep -v test
grep -rn "WorkflowLoader" dashboard/
ls tests/ | grep -i dashboard
```

- [ ] **Step 2: Replace the raw reads**

Route the structure/step-kind needs through the loaded bundle (`WorkflowLoader.load_bundle` → surface AST → `SurfaceStepKind`), mirroring how `projection.py` does it. Delete `_workflow_step_kind`'s string-matching classifier; the surface AST already knows the kind. Keep the function names as thin wrappers if dashboard tests bind them (check with the Step-1 grep of tests).

- [ ] **Step 3: Verify**

Run the dashboard test files found in Step 1 (`pytest <files> -q`) plus an import smoke: `python -c "import dashboard.server"`. If the dashboard has a runnable smoke (check `grep -rn "if __name__" dashboard/server.py`), start it against a sample state dir and confirm the workflow-structure endpoint renders (document the exact command used and its output in the task report).

- [ ] **Step 4: Commit**

```bash
git add <touched dashboard files>
git commit -m "Read workflow structure from typed surface in dashboard"
```

---

### Task 3: Split the YAML parse frontend from the shared validation core in `loader.py` — UNGATED

Every Lisp workflow also flows through loader validators: `lowering/core.py:2345-2419` (`_validate_one_lowered_workflow`) calls loader `_validate_*` / `_normalize_v214_ergonomics`. The split makes Task 7's YAML-frontend deletion a file-scoped change instead of a surgical one.

**Files:**
- Create: `orchestrator/workflow_surface_validation.py`
- Modify: `orchestrator/loader.py`, `orchestrator/workflow_lisp/lowering/core.py`

**Interfaces:** Produces `workflow_surface_validation.py` exporting the shared `_validate_*` / `_normalize_*` functions under their current names; `loader.py` keeps `WorkflowLoader` (YAML read/parse/bundle) and re-exports nothing new.

- [ ] **Step 1: Measure exactly which loader names the Lisp path uses**

```bash
grep -n "loader\.\|from orchestrator.loader import\|from ..loader import\|from orchestrator import loader" orchestrator/workflow_lisp/lowering/core.py orchestrator/workflow_lisp/*.py orchestrator/workflow/*.py | grep -v "\.pyc"
```
The moved set = the union of names used outside `loader.py` itself, plus their private helpers (trace with `grep -n "def <name>" orchestrator/loader.py` and read each body for intra-module calls).

- [ ] **Step 2: Move the shared set to `workflow_surface_validation.py`**

Mechanical move; `loader.py` imports the moved names from the new module (keeping `from orchestrator.loader import X` working for any existing importer — verify importers with `grep -rn "from orchestrator.loader import\|from orchestrator import loader" orchestrator/ tests/ dashboard/`). `lowering/core.py` switches its imports to the new module.

- [ ] **Step 3: Verify**

```bash
python -c "import orchestrator.loader, orchestrator.workflow_surface_validation"
pytest tests/test_workflow_lisp_lowering.py -q
pytest tests/ -q --collect-only > /dev/null && echo COLLECT_OK
```
Plus one YAML-route smoke: `pytest tests/test_workflow_executor_characterization.py -q` (loads YAML workflows end to end).

- [ ] **Step 4: Commit**

```bash
git add orchestrator/loader.py orchestrator/workflow_surface_validation.py orchestrator/workflow_lisp/lowering/core.py
git commit -m "Split shared surface validation out of yaml loader"
```

---

### Task 4: Deprecation surface — GATED on first family promotion (Task 5 family 1)

Users need a real `.orc` target before the warning fires. Do not land this before at least one production family is `.orc`-primary.

**Files:**
- Modify: `orchestrator/cli/commands/run.py` (the non-`.orc` branch at :329's `else`), `orchestrator/cli/commands/resume.py` (equivalent branch), `docs/index.md`, `workflows/templates/` (1 file per triage)

- [ ] **Step 1:** In the YAML branch of `run.py` (after `loader = WorkflowLoader(workspace)` succeeds), emit once: `logger.warning("YAML workflow authoring is deprecated; author new workflows in .orc (see docs/index.md).")`. Mirror in `resume.py` for fresh YAML loads only — resumes of existing runs stay silent.
- [ ] **Step 2:** Update `docs/index.md` routing (currently routes YAML drains as production workflows around :537-546) to point authors at `.orc` and the promoted family; replace the `workflows/templates/` YAML template with an `.orc` equivalent per the triage table.
- [ ] **Step 3:** Verify: `pytest tests/test_cli_safety.py -q` plus a manual `python -m orchestrator run <any triage 'example' yaml> --dry-run` showing the warning once. No test may assert the literal warning text (repo rule) — if a test is needed, assert a warning of category/логger name, not phrasing.
- [ ] **Step 4:** Commit: `git add <files>` / `git commit -m "Deprecate yaml workflow authoring surface"`.

---

### Task 5: Per-family `.orc` promotion — GATED per family

Uniform checklist, one family at a time, using the promotion machinery. Family order and gates:

| # | Family (YAML primary or retained twin) | Gate |
|---|---|---|
| 1 | `lisp_frontend_design_delta_drain.yaml` (+ 6 `v214` library imports) | Promotion handoff recorded; `.orc` is primary and YAML/`v214` archive remains deferred to Stage 6 pending Gate P3 closure |
| 2 | `verified_iteration_drain.yaml` | Record the port-vs-absorb decision first (one paragraph in the triage doc); if port: after family 1 |
| 3 | `lisp_frontend_autonomous_drain.yaml` | After family 1 (shares the drain stdlib surface) |
| 4 | `neurips_steered_backlog_drain.yaml` | After family 1; `.legacy.yaml` twin is deleted, not ported (triage class `delete`) |
| 5 | `major_project_tranche_drain_from_manifest_v2_call.yaml`, `major_project_tranche_drain_stack_v2_call.yaml` | After family 3 |
| 6 | `lisp_frontend_proc_refs_partial_application_drain.yaml` | After the ProcRef tranche it exercises is stable (check `docs/design/workflow_lisp_proc_refs_partial_application.md` status) |

Per-family checklist (each bullet = one commit-sized step):

- [ ] Author/complete the `.orc` port under `workflows/library/<family>/` or `workflows/examples/`, reusing existing candidates where the triage table shows an `.orc` twin.
- [ ] Register the family in `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` (schema `workflow_lisp_migration_parity_targets.v1` — copy an existing target block) with smoke/parity evidence commands.
- [ ] Run the parity gate: `python -m orchestrator migration-parity ...` (exact subcommand per `orchestrator/cli/main.py:491-515`) until the report is `non_regressive: true` with all evidence roles passing.
- [ ] Flip primary surface: update the launch entry points (docs/index.md routing, any scripts referencing the YAML path), set the registry/readiness labels, keep the YAML twin in place for one verification cycle.
- [ ] Run one real (or dry-run, for expensive families) drain/workflow launch on the `.orc` primary; treat fresh run output as the promotion evidence.
- [ ] Archive the YAML twin (git rm; the `v214` library files retire only when their last importer flips).

---

### Task 6: Estate deletion sweeps by triage class — class `delete`/`example-archive` UNGATED, class `library` per family, class `production` after Task 5

- [ ] **Step 1 (ungated):** Delete triage-class `delete` files (e.g. `neurips_steered_backlog_drain.legacy.yaml`) and archive-class examples with no importers (`yaml importers == 0` in the triage table). Verify: `pytest tests/test_workflow_lisp_examples.py -q` and `grep -rn "<deleted basename>" orchestrator/ tests/ docs/ workflows/` per file → no hits. One commit per batch of ≤15 files.
- [ ] **Step 2 (per family):** With each Task-5 family archival, delete its `v214`/library YAML imports once `grep -rln "<library file basename>" workflows/` shows no remaining importer.
- [ ] **Step 3:** Keep the triage doc updated (re-run the Phase-1 Task-13 generator script and commit the refreshed table alongside each sweep).

---

### Task 7: Delete the user-facing YAML frontend — GATED on: gap list empty/waived AND all production families promoted AND triage table shows zero `production` YAML rows

**Files:**
- Modify: `orchestrator/cli/commands/run.py`, `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/loader.py`
- Delete: remaining `workflows/**/*.yaml` per triage; the YAML template

- [ ] **Step 1:** Remove the non-`.orc` branch in `run.py` (the `else` after the `.orc` suffix check at :329) — replace with a hard error naming the `.orc` requirement. Same in `resume.py` for fresh loads; decide (and record) the policy for resuming pre-retirement YAML runs — the conservative default is: keep resume working for existing persisted runs for one release, delete later.
- [ ] **Step 2:** Delete the YAML read/parse path from `loader.py` (now isolated by Task 3); `WorkflowLoader` either shrinks to the persisted-bundle loader the runtime still needs or is deleted — decide by `grep -rn "WorkflowLoader" orchestrator/ dashboard/ tests/` at execution time.
- [ ] **Step 3:** Delete remaining YAML files per triage; `find workflows -name "*.yaml"` → empty (or exactly the recorded resume-compat exceptions).
- [ ] **Step 4:** Full suite in tmux (`pytest -q`) + one `.orc` production workflow smoke launch. Update `docs/index.md` and `docs/capability_status_matrix.md` (YAML surface → legacy/removed).
- [ ] **Step 5:** Commit in reviewable slices (CLI, loader, estate) with explicit paths.

---

## Program-level verification strategy

- Tasks 1–3 are ordinary refactors: targeted suites + collect-only + one YAML-route characterization run each.
- Tasks 4–7 change user-facing behavior: each requires a fresh workflow launch (dry-run acceptable where the family is expensive) as evidence, per the repo rule that workflow-touching changes rerun an orchestrator smoke.
- The promotion machinery is the admissibility contract for every family flip: no family's YAML twin is deleted while its parity report is anything but `non_regressive: true`.
