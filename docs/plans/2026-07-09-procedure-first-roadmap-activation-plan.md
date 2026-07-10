# Procedure-First Roadmap Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the approved procedure-first roadmap executable by reconciling the existing component plans with landed commits, tracking and routing the governing plan set, re-anchoring stale ownership paths, and establishing a verified component-plan handoff.

**Architecture:** This plan changes planning and routing artifacts only; it does not replay landed refactors or implement the drain migration. Each component plan keeps ownership of its detailed tasks and verification. The activation pass records evidence-backed status and updates symbol/path anchors after module extraction. Its original Task 9 executor handoff and the later lowering-fork closeout are historical; current routing is paused at the boundary-report Task 5 case 5 production design gate.

**Tech Stack:** Markdown, Git, `rg`, pytest, pyflakes.

---

## Governing Sequence

Follow `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`.
Semantic authority remains with the Workflow Lisp frontend specification and
the parametric type-system design. These activation edits may change status,
paths, ordering pointers, and check commands; they must not change semantic
acceptance requirements.

## Working-Tree Safety

- Run from `/home/ollie/Documents/agent-orchestration`.
- Do not create a worktree.
- Preserve all unrelated modified and untracked files.
- Stage only the exact plan/index paths named by each task.
- A checkbox is not completion evidence. Use the current symbol, commit, and
  fresh-check evidence named below.
- If the checkout advances during this plan, re-run Task 1 and update the
  status snapshot before committing.

### Task 1: Capture the live component-plan execution boundary

**Files:**
- Modify: `docs/plans/2026-07-07-build-module-split.md`
- Modify: `docs/plans/2026-07-07-executor-decomposition.md`
- Modify: `docs/plans/2026-07-07-typecheck-family-completion.md`
- Reference: `docs/plans/2026-07-07-lowering-fork-migration.md`

- [ ] **Step 1: Record the current commit and dirty paths**

Run:

```bash
git log -1 --date=iso-strict --format='%H %ad %s'
git status --short
```

Record the commit in each new execution-status note. Do not copy unrelated
dirty paths into the plan prose; state only that unrelated user work exists and
must be preserved.

Make the in-scope untracked plans visible to ordinary diff review without
staging their content yet:

```bash
for f in \
  docs/plans/2026-07-07-build-module-split.md \
  docs/plans/2026-07-07-drain-migration-g8-retirement.md \
  docs/plans/2026-07-07-executor-decomposition.md \
  docs/plans/2026-07-07-typecheck-family-completion.md \
  docs/plans/2026-07-08-boundary-report-followups.md \
  docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md; do
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 || git add -N -- "$f"
done
```

`git add -N` records intent-to-add only; it does not stage file content. After
this step, `git diff -- <exact path>` must show each untracked file as a full
addition, making its complete contents reviewable before the final commit.

- [ ] **Step 2: Verify the landed build-split boundary**

Run:

```bash
git log --format='%h %s' -- \
  orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_manifest_io.py \
  orchestrator/workflow_lisp/build_design_delta.py \
  orchestrator/workflow_lisp/build_artifacts.py | head -12
test -f orchestrator/workflow_lisp/build_manifest_io.py
test -f orchestrator/workflow_lisp/build_design_delta.py
test -f orchestrator/workflow_lisp/build_artifacts.py
rg -n 'def (_compile_entry|_select_and_reattach|_emit)' orchestrator/workflow_lisp/build.py
```

Expected: Tasks 1-5 are represented by committed module moves, evidence
threading, and stage slicing. Add an `Execution status (verified 2026-07-09)`
note after the plan header: Tasks 1-5 landed; Task 6 final gate remains. Cite
commit subjects or hashes, not line numbers.

- [ ] **Step 3: Verify the landed typecheck-family boundary**

Run:

```bash
test -f orchestrator/workflow_lisp/typecheck_resume.py
test -f orchestrator/workflow_lisp/typecheck_drain_phase.py
test -f orchestrator/workflow_lisp/typecheck_resource_view.py
rg -n 'compat\._raise|compat\._type|from \. import typecheck as compat' \
  orchestrator/workflow_lisp/typecheck_*.py
git log --format='%h %s' -- \
  orchestrator/workflow_lisp/typecheck_context.py \
  orchestrator/workflow_lisp/typecheck_resume.py \
  orchestrator/workflow_lisp/typecheck_drain_phase.py \
  orchestrator/workflow_lisp/typecheck_resource_view.py | head -12
```

Expected: owner modules exist and the legacy `compat` patterns print no hits.
Add an execution-status note: Tasks 1-6 landed; the end-of-plan verification
gate remains to be rerun. Do not rewrite the historical task instructions.

- [ ] **Step 4: Verify the landed executor boundary**

Run:

```bash
test -f orchestrator/workflow/call_frame_state.py
test -f orchestrator/workflow/frontend_origins.py
test -f orchestrator/workflow/step_results.py
test -f orchestrator/workflow/steps/runtime.py
test -f orchestrator/workflow/steps/resource_transition.py
test -f orchestrator/workflow/steps/pure_projection.py
test -f orchestrator/workflow/steps/scalars.py
test -f orchestrator/workflow/steps/materialize_view.py
git cat-file -e HEAD:orchestrator/workflow/adjudication_runner.py
if git cat-file -e HEAD:orchestrator/workflow/executor_runtime.py 2>/dev/null; then
  git show HEAD:orchestrator/workflow/executor_runtime.py | \
    rg -n 'class (ExecutorRuntime|LoopRuntime|CallRuntime)'
else
  echo TASK7_UNLANDED
fi
git show HEAD:orchestrator/workflow/executor.py | \
  rg -n '^    def (_execute_prologue|_execute_step_loop|_execute_epilogue)'
git log --format='%h %s' -- \
  orchestrator/workflow/executor.py \
  orchestrator/workflow/adjudication_runner.py \
  orchestrator/workflow/executor_runtime.py \
  orchestrator/workflow/steps | head -16
```

Expected at the activation boundary recorded by this task: Tasks 2-4, 5a-5e,
6, 7, and 8 are landed; Task 9 was next. Task 7 followed its plan-authorized low-overlap branch:
committed `executor_runtime.py` exists with `LoopRuntime` and `CallRuntime`
rather than one literal `ExecutorRuntime`. Task 8's three `execute()` helpers
are committed. If Task 9 is now complete in `HEAD`, inspect the newest commits
and advance the note to the real first
unlanded task rather than recording stale status. Uncommitted or staged work
does not count as landed. Add an execution-status note after the header with
the verified boundary.

- [ ] **Step 5: Review the status-only diff**

Run:

```bash
git diff --check -- \
  docs/plans/2026-07-07-build-module-split.md \
  docs/plans/2026-07-07-executor-decomposition.md \
  docs/plans/2026-07-07-typecheck-family-completion.md
git diff -- \
  docs/plans/2026-07-07-build-module-split.md \
  docs/plans/2026-07-07-executor-decomposition.md \
  docs/plans/2026-07-07-typecheck-family-completion.md
```

Expected: status notes only; no semantic task or check weakening.
Because these files began untracked, the diff shows their complete contents.
Review the added status notes in context and confirm the rest matches the
previously reviewed plan content.

### Task 2: Re-anchor the drain retirement plan to current owners

**Files:**
- Modify: `docs/plans/2026-07-07-drain-migration-g8-retirement.md`
- Reference: `docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md`
- Reference: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`

- [ ] **Step 1: Locate every moved build/typecheck symbol**

Run:

```bash
rg -n 'def _serialize_design_delta_g8_deletion_evidence|DESIGN_DELTA_G8_|def _maybe_load_design_delta|class DesignDeltaEvidence|class DesignDeltaReportPayloads' \
  orchestrator/workflow_lisp/build*.py orchestrator/workflow_lisp/migration_parity.py
rg -n 'backlog_drain|BacklogDrain|_backlog_drain_blocker_class_type' \
  orchestrator/workflow_lisp/typecheck*.py orchestrator/workflow_lisp/lowering/*.py
```

Build a symbol-to-current-owner map in a new `Execution re-anchor
(2026-07-09)` subsection near the plan's relationship section. Prefer symbol
names and owning module paths; retain old line numbers only as historical
drafting context.

- [ ] **Step 2: Update task file ownership without changing deletion scope**

Update Phase 2-4 `Files` and deletion-inventory references so that:

- moved design-delta serializers/loaders point to
  `orchestrator/workflow_lisp/build_design_delta.py`;
- moved artifact writers point to
  `orchestrator/workflow_lisp/build_artifacts.py` when applicable;
- the public build orchestration/stage call sites remain attributed to
  `orchestrator/workflow_lisp/build.py`;
- drain/phase typecheck ownership points to
  `orchestrator/workflow_lisp/typecheck_drain_phase.py` when the live symbol
  moved there;
- the plan still deletes only family-specific certification/G8 logic and
  preserves the generic build and parity kernels.

Do not guess ownership. Every replacement must be supported by Task 2 Step 1
output.

- [ ] **Step 3: Add the Design Delta promotion handoff**

In the Gate P3 / Phase 3 transition, point to
`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md` Stage 3:

- execute YAML-retirement Task 5 family 1 only through `.orc` primary flip,
  fresh parity, and end-to-end evidence;
- stop before its archive bullet;
- retain the YAML twin until the later YAML-retirement stage;
- do not recreate the retired parity target after Phase 3.

This is sequencing clarification only; do not weaken Gate P3.

- [ ] **Step 4: Verify the re-anchor**

Run:

```bash
rg -n 'build\.py:[0-9]|typecheck_calls\.py:[0-9]|typecheck_dispatch\.py:[0-9]' \
  docs/plans/2026-07-07-drain-migration-g8-retirement.md
git diff --check -- docs/plans/2026-07-07-drain-migration-g8-retirement.md
```

Classify every remaining old anchor as either still-current or explicitly
historical. The diff must change paths/ordering notes only, never expected
behavior or pass criteria.

### Task 3: Reconcile the boundary follow-up plan with already-landed fixture deletion

**Files:**
- Modify: `docs/plans/2026-07-08-boundary-report-followups.md`
- Reference only: `docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md`
- Reference: `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md`

- [ ] **Step 1: Verify whether the originally orphaned fixtures still exist**

Run:

```bash
for f in \
  tests/fixtures/workflow_lisp/invalid/if_variant_proof_missing.orc \
  tests/fixtures/workflow_lisp/invalid/review_loop_result_contract_invalid.orc \
  tests/fixtures/workflow_lisp/invalid/backlog_drain_hidden_compatibility_bridge_reread_invalid.orc; do
  test -e "$f" && echo "present $f" || echo "absent $f"
done
git log --format='%h %s' -- tests/fixtures/workflow_lisp/invalid | head -12
```

- [ ] **Step 2: Update coordination and recovery wording**

If the fixture-deletion task already landed, add an execution note stating
that Task 5 must recreate only a minimal fixture for a genuine uncovered case;
it must not attempt to reuse an absent file. Keep the audit valid and keep
Task 6 as a historical reconciliation/status update rather than replaying the
deletion plan.

Do not edit the report in this task; it contains unrelated user changes and is
the output of later boundary-follow-up execution.

- [ ] **Step 3: Verify**

Run:

```bash
git diff --check -- docs/plans/2026-07-08-boundary-report-followups.md
```

Expected: coordination/recovery clarification only.

### Task 4: Track and route the component plan set

**Files:**
- Modify: `docs/index.md`
- Add: `docs/plans/2026-07-07-build-module-split.md`
- Add: `docs/plans/2026-07-07-drain-migration-g8-retirement.md`
- Add: `docs/plans/2026-07-07-executor-decomposition.md`
- Add: `docs/plans/2026-07-07-typecheck-family-completion.md`
- Add: `docs/plans/2026-07-08-boundary-report-followups.md`
- Add: `docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md`

- [ ] **Step 1: Add concise routing entries**

Under the procedure-first roadmap entry in `docs/index.md`, add a compact
component-plan list or paragraph that identifies:

- closeout plans: lowering, typecheck family, build split;
- activation-time next plan: executor decomposition (now completed; use current `docs/index.md` routing);
- semantic migration plan: drain migration/G8 retirement;
- prerequisite evidence plan: boundary-report follow-ups.

Do not copy task details into the index.

- [ ] **Step 2: Validate paths and Markdown**

Run:

```bash
for f in \
  docs/plans/2026-07-07-lowering-fork-migration.md \
  docs/plans/2026-07-07-typecheck-family-completion.md \
  docs/plans/2026-07-07-build-module-split.md \
  docs/plans/2026-07-07-executor-decomposition.md \
  docs/plans/2026-07-07-drain-migration-g8-retirement.md \
  docs/plans/2026-07-08-boundary-report-followups.md; do
  test -f "$f" || exit 1
done
git diff --check -- \
  docs/index.md \
  docs/plans/2026-07-07-build-module-split.md \
  docs/plans/2026-07-07-drain-migration-g8-retirement.md \
  docs/plans/2026-07-07-executor-decomposition.md \
  docs/plans/2026-07-07-typecheck-family-completion.md \
  docs/plans/2026-07-08-boundary-report-followups.md \
  docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md
```

- [ ] **Step 3: Review the complete unstaged plan set**

Run:

```bash
git diff --stat -- \
  docs/index.md \
  docs/plans/2026-07-07-build-module-split.md \
  docs/plans/2026-07-07-drain-migration-g8-retirement.md \
  docs/plans/2026-07-07-executor-decomposition.md \
  docs/plans/2026-07-07-typecheck-family-completion.md \
  docs/plans/2026-07-08-boundary-report-followups.md \
  docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md
```

Inspect `git diff -- <path>` for each of the seven paths. The five component
plans and activation plan are full additions because they began untracked;
their complete contents, not only status-note snippets, must be accepted before
Task 5 stages them. Do not use a wildcard that includes unrelated modified
plans.

### Task 5: Run the activation gate and hand off to the first unlanded executor task

**Files:**
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md`
  (activation evidence record)
- Modify only if evidence requires correction: the component plan containing
  the incorrect status note.

- [ ] **Step 1: Run closeout-focused checks**

Use the tmux skill for the long build suite or any command expected to exceed
the normal foreground window.

Run:

```bash
pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_drain_stdlib.py -q
pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_drain_stdlib.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
pytest tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: PASS. If a current branch has a documented pre-existing failure,
record the exact before/after evidence and do not label that component closed.

Append an `Activation evidence (2026-07-09)` section to this plan containing:

- tested commit hash;
- each exact command;
- exit code and pass/fail count;
- any accepted pre-existing failure with its before/after source;
- the closeout disposition for lowering, typecheck, and build.

- [ ] **Step 2: Verify the first unlanded executor task**

Run:

```bash
git cat-file -e HEAD:orchestrator/workflow/adjudication_runner.py && echo TASK6_LANDED
git cat-file -e HEAD:orchestrator/workflow/executor_runtime.py && echo TASK7_MODULE_LANDED
git show HEAD:orchestrator/workflow/executor_runtime.py | \
  rg -n 'class (ExecutorRuntime|LoopRuntime|CallRuntime)'
git grep -n 'ExecutorRuntime|LoopRuntime|CallRuntime' HEAD -- \
  orchestrator/workflow/loops.py orchestrator/workflow/calls.py
git show HEAD:orchestrator/workflow/executor.py | \
  rg -n '^    def (_execute_prologue|_execute_step_loop|_execute_epilogue)'
git log -5 --format='%h %s'
```

Treat either one `ExecutorRuntime` or the Task-7-authorized narrower
`LoopRuntime` and `CallRuntime` pair as landed when the committed consumers use
the contract. Treat Task 8 as landed when its three committed `execute()`
helpers exist. Advance to the first unlanded task by committed symbol and
commit evidence. Do not execute an already-landed extraction, and do not count
uncommitted or staged work as landed.

- [ ] **Step 3: Record the handoff in the evidence section**

Record the newest committed executor boundary; whether committed
`executor_runtime.py` and a literal `ExecutorRuntime` exist; whether the
authorized narrower protocols exist instead; whether Task 8's helpers exist;
and the first unlanded executor task. Update the executor plan's
execution-status note if Step 2 changed the boundary.

- [ ] **Step 4: Stage, review, and commit the activated plan set**

Stage only:

```bash
git add \
  docs/index.md \
  docs/plans/2026-07-07-build-module-split.md \
  docs/plans/2026-07-07-drain-migration-g8-retirement.md \
  docs/plans/2026-07-07-executor-decomposition.md \
  docs/plans/2026-07-07-typecheck-family-completion.md \
  docs/plans/2026-07-08-boundary-report-followups.md \
  docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md
git diff --cached --name-only
git diff --cached --check
git diff --cached --stat
git diff --cached -- \
  docs/index.md \
  docs/plans/2026-07-07-build-module-split.md \
  docs/plans/2026-07-07-drain-migration-g8-retirement.md \
  docs/plans/2026-07-07-executor-decomposition.md \
  docs/plans/2026-07-07-typecheck-family-completion.md \
  docs/plans/2026-07-08-boundary-report-followups.md \
  docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md
git commit -m "Activate procedure-first component plan set"
```

The cached name list must contain exactly those seven paths. Inspect the full
cached diff before committing; a names-only check is insufficient for files
that began untracked. The activation evidence must already be present in the
cached activation plan, so the commit itself satisfies Gate S0's recorded
baseline requirement.

Final activation result:

- the plan set is tracked and discoverable;
- closeout status is evidence-backed;
- drain anchors point to current owners;
- no unrelated working-tree changes were staged;
- the next executor task is unambiguous.

## Activation evidence (2026-07-09)

Tested committed boundary:
`1600fd7ed6c920c1bd9f3a6890ff10f6d7ee25b0`
(`Slice executor run method into prologue and epilogue helpers`). All four
commands ran sequentially from the repository root in a private tmux session.
Before and after every command, the following exact checks ran from the
repository root:

```bash
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all -- orchestrator tests
find orchestrator tests -type f \
  \( -name '*.py' -o -name '*.orc' -o -name '*.yaml' -o -name '*.yml' -o -name '*.json' \) \
  -print0 | sort -z | xargs -0 sha256sum | sha256sum
```

Both `git rev-parse HEAD` calls printed
`1600fd7ed6c920c1bd9f3a6890ff10f6d7ee25b0` for every suite. Both status
checks printed only the same pre-existing unrelated modification to
`tests/test_workflow_non_progress_step_back_demo.py`. The content command,
whose path set is exactly the matching `*.py`, `*.orc`, `*.yaml`, `*.yml`, and
`*.json` files below `orchestrator/` and `tests/`, printed
`fbcedec80761386e764d620a0b37513f745b78ac854611ec08941f1064a0f6c0  -`
before and after every suite. No pre-existing test failure was accepted.

1. `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_drain_stdlib.py -q`
   — exit `0`; `320 passed`, `0 failed`, `0 skipped` in `26.26s`.
2. `pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_drain_stdlib.py -q`
   — exit `0`; `398 passed`, `0 failed`, `0 skipped` in `17.11s`.
3. `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q`
   — exit `0`; `93 passed`, `0 failed`, `0 skipped` in `157.26s`.
4. `pytest tests/test_workflow_lisp_build_artifacts.py -q`
   — exit `0`; `190 passed`, `0 failed`, `0 skipped` in `279.43s`.

Closeout dispositions:

- **Lowering:** completed 2026-07-09. Its Task 9 residue audit, 386-test lowering
  selector, full-suite baseline comparison, and report are recorded in the
  component plan. Only drain-frozen `lowering_core` residue remains.
- **Typecheck family:** completed 2026-07-09 through its bounded Task 7
  closeout amendment. Structural/static checks, 398 behavioral tests, the
  Design Delta smoke, and the full-suite baseline comparison are recorded in
  the component plan.
- **Build split:** completed 2026-07-09. Task 6's module-size/static audit,
  exact certification selectors, compatibility review, and full-suite baseline
  comparison are recorded in the component plan.

Executor handoff (superseded by the 2026-07-09 Task 9 closeout): the committed executor code boundary is
`1600fd7ed6c920c1bd9f3a6890ff10f6d7ee25b0`. Committed
`orchestrator/workflow/executor_runtime.py` exists. A literal
`ExecutorRuntime` does not; the plan-authorized narrower `LoopRuntime` and
`CallRuntime` protocols are committed and used by their consumers. Task 8's
`_execute_prologue`, `_execute_step_loop`, and `_execute_epilogue` helpers are
committed. Task 9 subsequently passed its corrected executor-surface and
orchestrator smoke gates; its six full-suite failure identities were also
present on the pre-Task-2 revision. That lowering-fork handoff is now
historical. Current routing is paused at the boundary-report Task 5 case 5
production design gate, as recorded by `docs/index.md` and the governing
execution sequence; drain migration must not begin until that gate clears.
