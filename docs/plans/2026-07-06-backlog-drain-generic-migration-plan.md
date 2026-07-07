# Backlog-Drain Generic Migration Plan (Phase B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author the backlog-drain loop as a generic `defproc` in `std/drain.orc`, re-target the `backlog-drain` macro onto it behind the frozen keyword surface, prove checkpoint identity and consumer parity, and retire the intrinsic lowering/typecheck/monomorphization paths.

**Architecture:** This is Phase B of the parametric type-system direction — Tranche 2 prerequisites 3–6 of `docs/design/workflow_lisp_parametric_type_system.md` (the owning design). The loop body becomes an inline-lowered generic procedure (modeled on the shipped `std/phase` `review-revise-loop-proc` precedent) whose hooks arrive as `ProcRef` parameters; the macro keyword surface stays byte-stable; identity and parity gates run **before** any deletion; retirement then removes the ~2,000-line intrinsic region, leaving registry/contract residue on the order of the review-loop precedent.

**Tech Stack:** Workflow Lisp frontend (`orchestrator/workflow_lisp/`), generic `defproc` with `:forall`/`:where`, `loop/recur`, `ProcRef`, the Task-9 `checkpoint_identity_map` harness, pytest.

**Drafted:** 2026-07-06, against commit `5a8e0fc` with the verified-iteration drain workstream's uncommitted changes present in `lowering/phase_drain.py`, `typecheck_calls.py`, `wcc/defunctionalize.py`, and `tests/test_lisp_frontend_autonomous_drain_runtime.py`. Drafted **before** the parametric plan's Tasks 4–10 completed (at the user's direction; the parametric plan's own gate asks for Tasks 2, 3, 7, 9 green before drafting — 2 and 3 were green at drafting time). Every anchor in this plan is therefore provisional until Task 1 re-verifies it.

## Execution Preconditions (hard gate — do not dispatch Task 2+ until all hold)

1. `docs/plans/2026-07-06-parametric-type-system-capability-plan.md` is complete
   through its final whole-branch review. In particular Task 9's
   `tests/test_workflow_lisp_checkpoint_identity_comparison.py::checkpoint_identity_map`
   exists and passes, and Task 7's diagnostics-anatomy regression tests exist.
2. The verified-iteration drain workstream targeting
   `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (run family
   `LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21`) has either completed or been
   deliberately paused, and its in-flight edits to `lowering/phase_drain.py`,
   `typecheck_calls.py`, and `wcc/defunctionalize.py` are committed or reverted.
   This plan rewrites the same region; interleaving with live uncommitted edits
   is not survivable.
3. Task 1 (re-baseline) has run and its findings are recorded in this file.

## Global Constraints

- **Ground truth:** `docs/design/workflow_lisp_parametric_type_system.md` owns
  the flagship signature and constraint vocabulary.
  `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (with
  `workflow_lisp_shared_owner_lane_prerequisites.md`) owns the concrete
  selector/run-item/gap-drafter hook shape contracts and drain runtime
  behavior. On conflict, **the signature adapts, not the shapes** (parametric
  design, Relationship To Other Docs). Raise conflicts; do not improvise.
- **Frozen caller surface:** the macro keyword surface
  `(backlog-drain <name> :ctx … :selector … :run-item … :gap-drafter …
  :max-iterations …)` is frozen; existing call sites remain **byte-stable**
  across the migration. Hook *definitions* in caller modules may change kind
  (workflow → proc) — only the call-site form is frozen.
- **Consumer-name blindness:** no surviving code under
  `orchestrator/workflow_lisp/` may branch on literal names `std/drain`,
  `backlog-drain`, `backlog-drain-callable-boundary`, or `phase_drain`
  (drain-authoring design §12.1). Registry entries and stdlib contracts are the
  allowed residue.
- **Checkpoint identity is a gate, not a hope** (parametric design,
  Specialization Pipeline): the route swap must demonstrate identity
  preservation by compiled-artifact comparison against a pre-swap baseline, or
  land an explicit reviewed identity-migration remap. A mismatch is a BLOCKED
  condition for the executing agent — the human chooses between reproducing
  identities and a reviewed remap.
- **Residue budget:** expected residue is on the order of the review-loop
  precedent (registry entry, stdlib contract, output-contract shaping).
  Residue materially above that is a **stop-and-reassess** signal against the
  per-form migration test (design, Form Classification) — do not push through.
- **No verification weakening:** intrinsic-era validations may move to the
  generic constraint system or shared validation surfaces, and diagnostic codes
  may change as reviewed contract deltas; no check may be silently dropped.
  Census/boundary/provider-metadata obligations move to shared validation
  surfaces, **not** into the generic body (design, Tranche 2 prerequisite 5).
- **Diagnostics anatomy:** every surviving failure path renders caller span,
  diagnostic code, failing clause or signature delta, concrete types, and a
  definition-side note. Tests assert code + substrings + span/note facts, never
  full literal message text.
- **Concurrent workstream hazard:** re-run each task's named suites for a fresh
  baseline before starting it; stage commits **by explicit path only** (never
  `git add -A`, `git add .`, or `git stash`); no worktrees.
- **Repo rules:** run from repo root; narrowest pytest selectors first;
  `pytest --collect-only` on new/renamed test modules; commit working code
  incrementally; no AI attribution in commit messages; workflow-touching
  changes rerun an orchestrator smoke check (Task 8).
- **Suite baselines (2026-07-06 drafting-time counts — re-measure in Task 1):**
  `tests/test_workflow_lisp_drain_stdlib.py` (47 tests),
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` (93),
  `tests/test_workflow_lisp_procedures.py` (126),
  `tests/test_workflow_lisp_generic_stdlib_composition.py` (9),
  `tests/test_workflow_lisp_build_artifacts.py` (183),
  `tests/test_lisp_frontend_autonomous_drain_runtime.py` (148, drain-workstream
  dirty at drafting time).

## Anchor Map (verified 2026-07-06 — Task 1 re-verifies every row)

| Surface | Anchor |
| --- | --- |
| Drain macro (alias to intrinsic) | `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc:280-286` |
| Authored terminal half (keep) | `std/drain.orc:128-279` — `empty/blocked/completed-drain-result-proc`, `finalize-drain-terminal`, `consume-drain-terminal-effects`, `drain-run-state` resource, `record-drain-outcome` transition |
| Form registry entries | `orchestrator/workflow_lisp/form_registry.py:576-599` (`backlog-drain`, `backlog-drain-callable-boundary`, `elaboration_route="backlog_drain"`) |
| Elaboration | `orchestrator/workflow_lisp/expressions.py:982` route entry; `_elaborate_backlog_drain` at `expressions.py:3128`; `BacklogDrainExpr`/`BacklogDrainSpec` (`drain_stdlib.py:12-23`) |
| Typecheck dispatch | `orchestrator/workflow_lisp/typecheck_dispatch.py:1788` (`isinstance(expr, BacklogDrainExpr)`) |
| Name-keyed validators | `orchestrator/workflow_lisp/typecheck_calls.py:464-697` — `validate_selector_workflow_ref`, `validate_run_item_workflow_ref`, `validate_gap_drafter_workflow_ref` |
| Intrinsic lowering | `orchestrator/workflow_lisp/lowering/phase_drain.py:399-1978` (`_phase_stdlib_lower_backlog_drain_impl`) plus helpers to :2455 |
| Form-specific monomorphizer | `phase_drain.py:208-391` (callable-boundary specialization: `_callable_backlog_drain_specialization_key`, `_ensure_callable_backlog_drain_workflow`, generated `std/drain::backlog-drain__<sha1[:12]>` children) |
| Python terminal duplicate | `orchestrator/workflow_lisp/lowering/drain_terminal.py:173+` (`lower_shared_drain_terminal_result`) |
| Schema-1 dispatch | `orchestrator/workflow_lisp/lowering/control_dispatch.py:151-154, 213-214` |
| WCC dispatch | `orchestrator/workflow_lisp/wcc/defunctionalize.py:3100-3108, 3243-3254` |
| Inventory strings | `orchestrator/workflow_lisp/stage7_metrics.py:102`, `stdlib_contracts.py:90,271,273` |
| Production consumer (sole) | `workflows/library/lisp_frontend_design_delta/drain.orc:64`; hooks are `defworkflow`: `stdlib_adapters.orc:26` (selector), `work_item.orc:433` (run-item), `stdlib_adapters.orc:62` (gap-drafter) |
| Blessed exemplar fixture | `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc` (98 lines; hooks are `defworkflow`) |
| Negative fixtures (codes will change) | ~12 under `tests/fixtures/workflow_lisp/invalid/` matching `backlog_drain_*`/`drain_ctx_*` |
| Generic precedent | `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc:82-149` (`review-revise-loop-proc`: `loop/recur`, `done`/`continue`, `:on-exhausted`) and macro at `:150+` |

## Known Feasibility Gaps (front-loaded as probes; do not discover these in Task 5)

- **G1 — hook kind.** The intrinsic validates hooks as *workflow refs*; the
  flagship signature takes `ProcRef` parameters, and `ProcRef` references
  `defproc` definitions. Production and exemplar hooks are `defworkflow`.
  Expected resolution: hooks convert to effectful `defproc` definitions
  (call-site keyword surface unchanged; the macro wraps names in `proc-ref`
  during expansion). Task 2 probes whether an effectful proc hook that invokes
  a child workflow / provider phase and returns a union compiles and
  inline-lowers through `ProcRef` + specialization.
- **G2 — ItemCtx construction.** The generic body must build
  `std/context/ItemCtx` (fields incl. `item-id String`) to call `run-item`,
  but the normative `:where` block gives `SelPayloadT` only `is-record` — the
  body has no proof for `selection.item-id`. Expected resolution: a design
  amendment adding `(SelPayloadT has-field item-id String)` (and, if the
  intrinsic reads it, `item-state-root`). The signature adapts, not the shapes;
  the amendment is a one-clause reviewed doc delta, raised in Task 4.
- **G3 — match exhaustiveness vs subset semantics.** Callers may add union
  variants (subset semantics), but under instantiate-then-typecheck the
  specialized body's `match` is checked against the caller's *concrete* union:
  an extra variant would fail exhaustiveness. Task 2 records what the compiler
  actually does; if extra-variant callers must be supported, that is a design
  question to raise, not a body hack.
- **G4 — selector `BLOCKED (reason String)` → terminal `blocker_class`.** The
  loop terminal's `BLOCKED`/`EXHAUSTED` arms need a `BlockerClass`; the
  selector's `BLOCKED` carries only `reason String`. Task 4 mirrors whatever
  mapping `_phase_stdlib_lower_backlog_drain_impl` performs today (read it;
  record the mapping in the fixture test) rather than inventing one.
- **G5 — inline-bodied proc hooks vs shared/loader validation.** Discovered
  2026-07-07 during the parametric plan's Task 8 review: an inline-bodied
  `defproc` passed as a `ProcRef` argument can fail the shared validation pass
  (`validate_shared=True`) with `source_map_missing` — `elaborate_surface_workflow`
  (`orchestrator/workflow/elaboration.py:123`) requires a non-empty `steps`
  field, a rule shaped for authored YAML workflows, and a trivially-bodied
  lowered proc can violate it (reproduced on
  `tests/fixtures/workflow_lisp/valid/minimal_caller_review_revise_loop.orc`;
  the sibling `minimal_caller_finalize_selected_item.orc` passes). The
  production drain consumer compiles through the full pipeline, so proc hooks
  must clear loader-shape validation, not just the frontend-only path. Task 2's
  probe therefore compiles with `validate_shared=True`; production-shaped
  effectful hooks (which lower to real steps) are expected to pass, but the
  outcome must be recorded, and a `source_map_missing` failure is a STOP.

---

### Task 1: Re-baseline and anchor verification

**Files:**
- Modify: `docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md`
  (append a `## Task 1 Re-baseline Record` section — this plan is the ledger
  for drift found here)

**Interfaces:**
- Consumes: the Anchor Map above; the then-current tree.
- Produces: verified (or corrected) anchors and fresh suite counts that every
  later task cites as its baseline.

- [ ] **Step 1: Confirm preconditions.** Verify the parametric plan is
complete (its ledger `.superpowers/sdd/progress.md` and final review), that
`tests/test_workflow_lisp_checkpoint_identity_comparison.py` exists and
passes, and that the drain workstream's edits in the region are committed
(`git status --porcelain orchestrator/workflow_lisp/ tests/` shows no
modifications to the Anchor Map files). If any check fails, STOP — the
execution preconditions are not met.

```bash
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -q
git status --porcelain orchestrator/workflow_lisp/ tests/ workflows/library/
```

- [ ] **Step 2: Re-verify every Anchor Map row.** For each row, confirm the
symbol still exists at (or near) the stated location:

```bash
grep -n "defmacro backlog-drain" orchestrator/workflow_lisp/stdlib_modules/std/drain.orc
grep -n "backlog-drain-proc" -r orchestrator/ tests/   # expect: nothing yet
grep -n '"backlog-drain"' orchestrator/workflow_lisp/form_registry.py
grep -n "_elaborate_backlog_drain" orchestrator/workflow_lisp/expressions.py
grep -n "BacklogDrainExpr" orchestrator/workflow_lisp/typecheck_dispatch.py orchestrator/workflow_lisp/lowering/control_dispatch.py orchestrator/workflow_lisp/wcc/defunctionalize.py
grep -n "validate_selector_workflow_ref\|validate_run_item_workflow_ref\|validate_gap_drafter_workflow_ref" orchestrator/workflow_lisp/typecheck_calls.py
grep -n "_phase_stdlib_lower_backlog_drain_impl\|_ensure_callable_backlog_drain_workflow" orchestrator/workflow_lisp/lowering/phase_drain.py
grep -n "lower_shared_drain_terminal_result" orchestrator/workflow_lisp/lowering/drain_terminal.py
grep -rn "(backlog-drain " workflows/library/ | head
```

Record moved/renamed/deleted anchors in the Re-baseline Record. If the drain
workstream landed an authored proc body or removed the intrinsic itself,
STOP and report — the plan's task structure needs human re-scoping.

- [ ] **Step 3: Fresh suite counts.**

```bash
pytest tests/test_workflow_lisp_drain_stdlib.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
pytest tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -q
pytest tests/test_workflow_lisp_build_artifacts.py -q
```

Record pass counts (and any pre-existing failures with owners) in the
Re-baseline Record.

- [ ] **Step 4: Commit the record.**

```bash
git add docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md
git commit -m "Record drain migration re-baseline"
```

### Task 2: Feasibility probes — ProcRef hook kind and generic-union match

**Files:**
- Create: `tests/fixtures/workflow_lisp/valid/drain_generic_hook_probe.orc`
- Test: `tests/test_workflow_lisp_generic_stdlib_composition.py`

**Interfaces:**
- Consumes: generic `defproc` + `ProcRef` + `loop/recur` machinery; the
  `review-revise-loop-proc` precedent (`std/phase.orc:82-149`).
- Produces: a compiled proof that an **effectful proc hook** — one that (a)
  returns a caller-owned union and (b) contains a `command-result` effect —
  binds through `ProcRef` inference into a generic definition and
  inline-lowers. This is gate G1; Task 4's body shape depends on it.

- [ ] **Step 1: Author the probe fixture.** A miniature of the drain call
shape with **proc** hooks (adapt the module scaffolding from
`drain_stdlib_backlog_drain.orc`, replacing `defworkflow` hooks with
effectful `defproc` hooks):

```lisp
(defproc probe-selector
  ((ctx DrainCtx))
  -> SelectionResult
  :effects ((uses-command probe_select))
  :lowering inline
  (command-result probe_select
    :argv ("python" "scripts/select_next_item.py" ctx.manifest)
    :returns SelectionResult))

(defproc probe-generic
  :forall (CtxT SelectionT)
  ((ctx CtxT)
   (selector ProcRef[(CtxT) -> SelectionT]))
  :where ((CtxT is-record)
          (SelectionT is-union)
          (SelectionT has-union-variant EMPTY)
          (SelectionT has-union-variant BLOCKED (reason String)))
  -> String
  :effects ()
  :lowering inline
  (match (selector ctx)
    ((EMPTY e) "empty")
    ((BLOCKED b) b.reason)))
```

The fixture's caller union (`SelectionResult`) deliberately has **more**
variants (SELECTED, GAP) than the generic matches — this is the G3 probe.

- [ ] **Step 2: Compile it and record reality.**

```bash
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -k hook_probe -v
```

The compile test must go through the shared-validated stage-3 entry
(`validate_shared=True`, the composition suite's default) — a frontend-only
compile would leave G5 unprobed.

Four recordable outcomes: (a) compiles — G1, G3, and G5 all clear (the
compiler tolerates unmatched extra variants or requires and accepts a default
arm — record which); (b) fails on exhaustiveness — G3 confirmed: the flagship
signature's constraint set is exact-in-practice for matched unions; record
the diagnostic code and adjust the fixture to a four-variant union matching
the flagship exactly, and note in this plan that extra-variant callers are
unsupported pending a design decision; (c) fails on the effectful proc hook
or `ProcRef` binding — **STOP (BLOCKED)**: G1 has no landed resolution and
the human must adjudicate (extend `ProcRef` vs. a different hook contract)
before any body authoring; (d) fails in shared/loader validation with
`source_map_missing` — **STOP (BLOCKED)**: G5 reproduces even for
production-shaped effectful hooks, and the loader-shape gap must be fixed or
design-adjudicated before the migration can proceed.

- [ ] **Step 3: Add the compile test** (assert compile success for whichever
fixture shape Step 2 validated), run the suite, and commit.

```bash
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -q
git add tests/fixtures/workflow_lisp/valid/drain_generic_hook_probe.orc \
  tests/test_workflow_lisp_generic_stdlib_composition.py
git commit -m "Probe ProcRef hook feasibility for drain migration"
```

- [ ] **Step 4: Append probe outcomes (G1/G3 resolutions) to this plan's
Re-baseline Record and commit that edit by explicit path.**

### Task 3: Intrinsic-route checkpoint-identity baselines

**Files:**
- Create: `tests/baselines/drain_checkpoint_identity/exemplar.json`
- Create: `tests/baselines/drain_checkpoint_identity/design_delta_drain.json`
- Test: `tests/test_workflow_lisp_checkpoint_identity_comparison.py`

**Interfaces:**
- Consumes: `checkpoint_identity_map(executor)` from the parametric plan's
  Task 9 (`tests/test_workflow_lisp_checkpoint_identity_comparison.py`);
  the `compile_stage3_entrypoint` + `WorkflowExecutor` pattern from
  `tests/test_workflow_lisp_lexical_checkpoints.py:30-51`.
- Produces: checked-in JSON snapshots of the **intrinsic-route** checkpoint
  identity maps for (a) the blessed exemplar fixture and (b) the production
  consumer `workflows/library/lisp_frontend_design_delta/drain.orc`, plus
  freshness tests proving the live compile still matches the snapshots. Task 5
  diffs the generic route against these files.

- [ ] **Step 1: Write the snapshot helper + freshness tests.**

```python
def _identity_map_for(source_path: Path, tmp_path: Path) -> dict[str, str]:
    executor = _executor_for_source(source_path, tmp_path)
    return {
        f"{wf}::{origin}": checkpoint_id
        for (wf, origin), checkpoint_id in checkpoint_identity_map(executor).items()
    }


def test_exemplar_intrinsic_route_matches_baseline(tmp_path: Path) -> None:
    live = _identity_map_for(FIXTURES / "valid" / "drain_stdlib_backlog_drain.orc", tmp_path)
    recorded = json.loads(BASELINES / "exemplar.json").read_text())
    assert live == recorded


def test_design_delta_drain_intrinsic_route_matches_baseline(tmp_path: Path) -> None:
    live = _identity_map_for(REPO_ROOT / "workflows/library/lisp_frontend_design_delta/drain.orc", tmp_path)
    recorded = json.loads((BASELINES / "design_delta_drain.json").read_text())
    assert live == recorded
```

`_executor_for_source` follows the Task 9 `_executor_for_fixture` pattern; if
the production module needs its sibling imports, compile via the same
multi-module entry the feasibility suite uses for
`lisp_frontend_design_delta` (copy its loader helper — do not invent one).

- [ ] **Step 2: Generate the two JSON files** by running the helper once and
writing sorted-key JSON (a small `python - <<'PY'` using the same helpers, or
a `--snapshot` conftest flag — match how existing baselines under `tests/`
are generated if a convention exists; otherwise inline script is fine).

- [ ] **Step 3: Run + collect-only; commit.**

```bash
pytest --collect-only tests/test_workflow_lisp_checkpoint_identity_comparison.py -q
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v
git add tests/baselines/drain_checkpoint_identity/ \
  tests/test_workflow_lisp_checkpoint_identity_comparison.py
git commit -m "Snapshot intrinsic-route drain checkpoint identities"
```

### Task 4: Author `backlog-drain-proc` and `settle-drain-terminal` in `std/drain.orc` (dormant — macro untouched)

**Files:**
- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- Create: `tests/fixtures/workflow_lisp/valid/minimal_caller_backlog_drain.orc`
- Test: `tests/test_workflow_lisp_generic_stdlib_composition.py`

**Interfaces:**
- Consumes: the normative flagship signature (parametric design, Tranche 2 —
  copy the `:forall`/`:where` block **verbatim** from
  `docs/design/workflow_lisp_parametric_type_system.md:512-539`, plus any
  G2 amendment); `loop/recur` per `review-revise-loop-proc`; the existing
  terminal helpers `finalize-drain-terminal` and
  `consume-drain-terminal-effects` (`std/drain.orc:153-279`).
- Produces: `backlog-drain-proc` returning `std/drain/DrainLoopTerminal`
  (exported); monomorphic `settle-drain-terminal
  ((terminal DrainLoopTerminal)) -> DrainResult` that sequences
  `consume-drain-terminal-effects` then `finalize-drain-terminal` (exported);
  a minimal-caller fixture (design Acceptance Checks: every stdlib generic
  gets one). Task 5's macro expansion targets exactly these two procs.

- [ ] **Step 1: Raise the G2 design amendment first.** Read
`_phase_stdlib_lower_backlog_drain_impl` to confirm which `SelPayloadT`
fields the intrinsic actually reads when building the item context (expected:
`item-id`; possibly `item-state-root`). Add the corresponding
`(SelPayloadT has-field … …)` clause(s) to the design doc's flagship
signature (one-clause delta, cite this plan) and mirror them in the proc.
Commit the doc delta separately:

```bash
git add docs/design/workflow_lisp_parametric_type_system.md
git commit -m "Declare selection payload fields the drain body projects"
```

- [ ] **Step 2: Write the failing compile test** (minimal-caller fixture
does not exist yet):

```python
def test_minimal_caller_satisfies_backlog_drain_proc_declared_constraints(tmp_path: Path) -> None:
    assert _compile_module_fixture(
        FIXTURES / "valid" / "minimal_caller_backlog_drain.orc", tmp_path=tmp_path
    ) is not None
```

- [ ] **Step 3: Author the proc.** Body skeleton (normative shape; field
spellings must match `std/drain.orc:51-68` exactly — note the terminal union
uses underscore field names):

```lisp
(defproc backlog-drain-proc
  :forall (CtxT SelectionT SelPayloadT GapPayloadT RunResultT GapResultT)
  ((ctx CtxT)
   (selector    ProcRef[(CtxT) -> SelectionT])
   (run-item    ProcRef[(std/context/ItemCtx SelPayloadT) -> RunResultT])
   (gap-drafter ProcRef[(CtxT GapPayloadT) -> GapResultT])
   (max-iterations Int)
   (initial-progress-report WorkReport))
  :where (…verbatim from the design, plus the Step-1 G2 clause(s)…)
  -> std/drain/DrainLoopTerminal
  :effects ()
  :lowering inline
  (loop/recur
    :max max-iterations
    :state (loop-state
             (items-processed Int 0)
             (progress-report-path WorkReport initial-progress-report))
    :on-exhausted (variant std/drain/DrainLoopTerminal EXHAUSTED
                    :items_processed state.items-processed
                    :progress_report_path state.progress-report-path
                    :blocker_class <the intrinsic's exhaustion class — read it>)
    (fn (state)
      (match (selector ctx)
        ((EMPTY e)
         (done (variant std/drain/DrainLoopTerminal EMPTY
                 :items_processed state.items-processed
                 :progress_report_path state.progress-report-path)))
        ((SELECTED s)
         (let* ((item-ctx (record std/context/ItemCtx
                            :run ctx.run
                            :item-id s.selection.item-id
                            :state-root ctx.state-root
                            :artifact-root ctx.run.artifact-root
                            :ledger ctx.ledger)))
           (match (run-item item-ctx s.selection)
             ((CONTINUE c)
              (continue (loop-state :like state
                          :items-processed (+ state.items-processed 1)
                          :progress-report-path c.summary-path)))
             ((BLOCKED b)
              (done (variant std/drain/DrainLoopTerminal BLOCKED
                      :items_processed state.items-processed
                      :progress_report_path b.summary-path
                      :blocker_class b.blocker-class))))))
        ((GAP g)
         (match (gap-drafter ctx g.gap)
           ((CONTINUE c) (continue (loop-state :like state)))
           ((BLOCKED b)
            (done (variant std/drain/DrainLoopTerminal BLOCKED
                    :items_processed state.items-processed
                    :progress_report_path b.progress-report-path
                    :blocker_class b.blocker-class)))))
        ((BLOCKED r)
         (done (variant std/drain/DrainLoopTerminal BLOCKED
                 :items_processed state.items-processed
                 :progress_report_path state.progress-report-path
                 :blocker_class <the intrinsic's reason→class mapping — G4, read it>))))))

(defproc settle-drain-terminal
  ((terminal std/drain/DrainLoopTerminal))
  -> std/drain/DrainResult
  :effects ((uses-command apply_resource_transition))
  :lowering inline
  (let* ((report (consume-drain-terminal-effects terminal)))
    (finalize-drain-terminal terminal)))
```

Reality anchors, each resolved **inside this task** by reading the intrinsic
(`phase_drain.py:399-1978`) and recorded in the fixture test, not invented:
the `:on-exhausted` blocker class; the G4 `reason → BlockerClass` mapping
(if the intrinsic routes selector-BLOCKED through a different terminal shape,
mirror that instead); the `initial-progress-report` parameter (the intrinsic
seeds a progress-report path — Task 5's macro supplies it via the
`__generated-relpath-seed__` pattern from the `review-revise-loop` macro,
`std/phase.orc:150+`; if the intrinsic derives it differently, mirror that).
ItemCtx field spellings must match `std/context` — read the module, don't
trust this skeleton. Both procs go in the module export list. Add the two
procs' IDL-style contract lines to the module header comment block if the
module keeps one.

- [ ] **Step 4: Author the minimal-caller fixture.** Types provide exactly
the declared constraints and nothing more (minimality is the enforcement
mechanism); hooks are effectful `defproc` definitions in the shape Task 2
validated; the call is a **direct** `(backlog-drain-proc …)` call wrapped in
`(settle-drain-terminal …)` — the macro is not exercised here.

- [ ] **Step 5: Run.** The dormant-proc bar: new tests pass, and the stdlib
edit breaks nothing that consumed `std/drain` before.

```bash
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -q
pytest tests/test_workflow_lisp_drain_stdlib.py -q
pytest tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_build_artifacts.py -q
```

- [ ] **Step 6: Commit.**

```bash
git add orchestrator/workflow_lisp/stdlib_modules/std/drain.orc \
  tests/fixtures/workflow_lisp/valid/minimal_caller_backlog_drain.orc \
  tests/test_workflow_lisp_generic_stdlib_composition.py
git commit -m "Author generic backlog-drain loop body in std/drain"
```

### Task 5: Macro re-target + checkpoint-identity gate

**Files:**
- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc:280-286`
  (the `defmacro backlog-drain` only)
- Modify: `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`,
  `workflows/library/lisp_frontend_design_delta/work_item.orc` (hook
  `defworkflow` → effectful `defproc`, per the Task 2 G1 resolution; call
  site in `drain.orc:64` stays byte-identical)
- Test: `tests/test_workflow_lisp_checkpoint_identity_comparison.py`,
  `tests/test_workflow_lisp_drain_stdlib.py`

**Interfaces:**
- Consumes: `backlog-drain-proc` + `settle-drain-terminal` (Task 4); the
  Task 3 baselines; the `review-revise-loop` macro precedent (seed injection,
  `proc-ref` wrapping).
- Produces: `backlog-drain` expanding to
  `(settle-drain-terminal (backlog-drain-proc ctx (proc-ref selector) … ))`
  with the generated progress-report seed; the intrinsic no longer reachable
  from the macro (but `backlog-drain-callable-boundary` remains live for its
  direct fixtures until Task 7).

- [ ] **Step 1: Re-target the macro.** Keyword surface and argument order
unchanged; expansion becomes shaping-only composition (macros must not own
control flow — both calls are proc calls, matching the review-revise-loop
precedent):

```lisp
(defmacro backlog-drain (name ctx-key ctx selector-key selector run-item-key run-item gap-drafter-key gap-drafter max-key max)
  (std/drain/settle-drain-terminal
    (std/drain/backlog-drain-proc
      ctx
      (proc-ref selector)
      (proc-ref run-item)
      (proc-ref gap-drafter)
      max
      (__generated-relpath-seed__
        std/drain/WorkReport
        "artifacts/work/drain-progress-report.md"
        "backlog_drain_progress_report_seed"))))
```

Match the seed-path spelling to what the intrinsic seeds today (read
`_phase_stdlib_lower_backlog_drain_impl`; identity preservation may depend on
it). Adjust `proc-ref` placement to however Task 2 showed hook names bind.

- [ ] **Step 2: Convert the production hooks** (`select-next-work-stdlib`,
`run-selected-item-stdlib`, `draft-design-gap-stdlib`) from `defworkflow` to
effectful `defproc` per the Task 2-validated shape, bodies unchanged.
`workflows/library/lisp_frontend_design_delta/drain.orc` itself must show an
empty diff (`git diff workflows/library/lisp_frontend_design_delta/drain.orc`
— byte-stable call site is a review gate).

- [ ] **Step 3: Compile gates.**

```bash
pytest tests/test_workflow_lisp_drain_stdlib.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
```

Failures here are expected to be diagnostic-code shifts (old
`backlog_drain_contract_invalid` paths now taking generic constraint paths) —
inventory them; they are Task 6's contract-delta work. Do not chase them here
unless the valid-path compiles themselves break.

- [ ] **Step 4: THE GATE — checkpoint identity.** Re-run the Task 3
freshness tests. They now compare the **generic route** against the recorded
intrinsic-route baselines:

```bash
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v
```

If identical: record that in the plan and proceed. If different: **BLOCKED —
stop the task, do not commit the re-target.** Produce the diff (which
`(workflow, origin_key)` rows changed/appeared/vanished), attach it to the
report, and present the human the design's two sanctioned options:
(a) make the generic route reproduce the intrinsic's generated-step
identities; (b) an explicit reviewed identity-migration remap of persisted
records. Neither is chosen unilaterally.

- [ ] **Step 5: Commit (only if the gate passed).**

```bash
git add orchestrator/workflow_lisp/stdlib_modules/std/drain.orc \
  workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc \
  workflows/library/lisp_frontend_design_delta/work_item.orc
git commit -m "Re-target backlog-drain macro onto the generic proc"
```

### Task 6: Parity gates, obligation census, and diagnostic contract deltas

**Files:**
- Modify: `tests/fixtures/workflow_lisp/invalid/backlog_drain_*.orc`,
  `tests/fixtures/workflow_lisp/invalid/drain_ctx_*.orc` (expected-code
  updates only where the route swap changed the code)
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`,
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Create: `docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md`
  → append `## Task 6 Obligation Census` section

**Interfaces:**
- Consumes: the intrinsic's validation inventory
  (`typecheck_calls.py:464-697`; `phase_drain.py` —
  `_require_backlog_drain_public_params:472-497`,
  `_validate_backlog_drain_provider_metadata:2003`, hidden-context
  eligibility checks); `parent_drain_census_alignment.py` and
  `phase_family_boundary.py` gates (these are name-blind already — verify,
  don't assume).
- Produces: every intrinsic-era obligation mapped to exactly one of:
  (1) subsumed by the generic `:where` constraint system, (2) relocated to a
  shared validation surface, (3) reviewed retirement with rationale. Plus
  green parity suites with documented diagnostic-code deltas.

- [ ] **Step 1: Obligation census.** Enumerate every check the intrinsic
path performs beyond loop semantics (read the three validators and the
lowering impl; list each with its diagnostic code). For each, record its
new home in the census section. Known population at drafting time: selector
arity + ctx type (`ensure_drain_context_type` — becomes the ctx `:where`
clauses via rule-4 refinement tolerance); the three hook return-shape checks
(become `RunResultT`/`GapResultT`/`SelectionT` clauses + `ProcRef` signature
matching); `workflow_signature_mismatch` extra-public-bindings; provider
metadata validation; hidden-context/private-context bootstrap eligibility;
`:max-iterations` literal-Int check. Any obligation whose only home would be
inside the generic body is a design conflict — raise it (prerequisite 5
forbids that home).

- [ ] **Step 2: Relocate what needs relocating.** Expected concrete work:
provider-metadata validation moving from `phase_drain.py` to the shared
surface that validates ordinary specialized proc calls (find where
`review-revise-loop` consumers get theirs — mirror that route). Write or
re-point a test per relocated obligation proving the failure still fires on
the generic route (behavioral assertion, not message text).

- [ ] **Step 3: Diagnostic contract deltas.** For each invalid fixture whose
code changed, update the expected code and record the delta
(`old code → new code, fixture, why`) in the census section. Deleting a
negative fixture outright requires showing its scenario is now impossible to
author, not merely differently reported.

- [ ] **Step 4: Full parity run.**

```bash
pytest tests/test_workflow_lisp_drain_stdlib.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
pytest tests/test_workflow_lisp_parent_drain_census_alignment.py -q
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: at Task-1 baselines. The autonomous-drain runtime suite is the
end-to-end consumer evidence; failures there are real parity breaks, not
contract deltas.

- [ ] **Step 5: Commit.**

```bash
git add tests/fixtures/workflow_lisp/invalid/ \
  tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  orchestrator/workflow_lisp/ \
  docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md
git commit -m "Move drain obligations to shared surfaces with parity evidence"
```

(Stage the specific `orchestrator/workflow_lisp/` files actually touched —
enumerate them; the glob above is a placeholder for the reviewer to check.)

### Task 7: Intrinsic retirement

**Files (delete/narrow — re-verify each against Task 1's record):**
- Modify: `orchestrator/workflow_lisp/lowering/phase_drain.py` (delete
  `_phase_stdlib_lower_backlog_drain_impl` + callable-boundary monomorphizer
  `:208-391` + drain-only helpers; keep any genuinely shared
  provider-metadata helpers that Task 6 relocated callers onto)
- Modify: `orchestrator/workflow_lisp/lowering/drain_terminal.py` (delete
  `lower_shared_drain_terminal_result` intrinsic path; delete the module if
  nothing remains)
- Modify: `orchestrator/workflow_lisp/typecheck_calls.py` (delete the three
  validators `:464-697` and `_backlog_drain_blocker_class_type`)
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py` (delete the
  `BacklogDrainExpr` block `:1788+`)
- Modify: `orchestrator/workflow_lisp/expressions.py` (delete
  `_elaborate_backlog_drain`, the `"backlog_drain"` route entry `:982`, and
  `BacklogDrainExpr`), `orchestrator/workflow_lisp/expression_traversal.py`,
  `orchestrator/workflow_lisp/drain_stdlib.py` (delete `BacklogDrainSpec`;
  delete the module if empty)
- Modify: `orchestrator/workflow_lisp/lowering/control_dispatch.py`
  (`:151-154, 213-214`), `orchestrator/workflow_lisp/wcc/defunctionalize.py`
  (`:3100-3108, 3243-3254`),
  `orchestrator/workflow_lisp/procedure_specialization.py` (`:246-251`
  `BacklogDrainExpr` result-type special case)
- Modify: `orchestrator/workflow_lisp/form_registry.py:576-599` (reclassify:
  `backlog-drain` becomes a stdlib-macro registry record — mirror how the
  migrated `review-revise-loop` is recorded; delete
  `backlog-drain-callable-boundary`)
- Modify: `orchestrator/workflow_lisp/stage7_metrics.py:102`,
  `orchestrator/workflow_lisp/stdlib_contracts.py:90,271,273`,
  `orchestrator/workflow_lisp/README.md:131` (inventory updates)
- Modify/Delete: `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_callable_boundary*.orc`
  and their tests (the boundary form retires; convert each to the macro form
  if it guards distinct behavior, else delete with a one-line rationale per
  fixture in the commit message body)

**Interfaces:**
- Consumes: green Tasks 5–6 gates.
- Produces: no compiler branch keyed to drain names (drain-authoring design
  §12.1); residue = registry record + stdlib contract entries + this plan's
  census.

- [ ] **Step 1: Delete in dependency order** (dispatch sites → elaboration →
AST node → validators → lowering impl → monomorphizer → spec dataclass),
compiling between clusters (`python -c "import orchestrator.workflow_lisp"`
or the fastest compile-touching test) so each commit is working code.
`backlog-drain-callable-boundary` retirement is a **reviewed contract
delta**: it is exported from `std/drain.orc:7-20` — remove the export and the
macro-alias plumbing; any fixture that invoked it directly follows the
disposition rule above.

- [ ] **Step 2: Name-blindness check.**

```bash
grep -rn "backlog.drain\|backlog_drain\|BacklogDrain" orchestrator/workflow_lisp/ \
  | grep -v stdlib_modules | grep -v README
```

Expected: form-registry residue entry only (plus stdlib-contract inventory
rows). Anything else is unfinished retirement.

- [ ] **Step 3: Residue audit.** Count what remains vs. the review-loop
precedent's residue (registry entry, stdlib contract, output-contract
shaping). Materially more → STOP and reassess against the per-form migration
test with the human; record the comparison in this plan either way.

- [ ] **Step 4: Full verification.**

```bash
pytest tests/test_workflow_lisp_drain_stdlib.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
pytest tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -q
pytest tests/test_workflow_lisp_build_artifacts.py -q
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v
```

The checkpoint-identity freshness tests must still pass post-retirement
(retirement must not perturb the generic route's identities).

- [ ] **Step 5: Commit** (multiple incremental commits are expected across
Step 1; each stages its explicit file list; final message for the last:)

```bash
git commit -m "Retire the backlog-drain intrinsic lowering paths"
```

### Task 8: Documentation sync and integration evidence

**Files:**
- Modify: `docs/design/workflow_lisp_parametric_type_system.md` (Tranche 2
  status: prerequisites 3–6 landed; flagship migrated)
- Modify: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
  (§12.1/12.2 status note: conversion path executed for `backlog-drain`)
- Modify: `docs/capability_status_matrix.md` (backlog-drain: library-provided
  via `std/drain` generic; intrinsic: retired)
- Modify: `docs/workflow_lisp_g6_verification_gate.json` (only if it tracks
  `std/drain` route status — read it first)
- Modify: `docs/index.md` (only if any doc description above changed meaning)

**Interfaces:**
- Consumes: everything landed in Tasks 4–7.
- Produces: docs matching implementation (repo rule: contradictions are
  implementation blockers), plus end-to-end run evidence.

- [ ] **Step 1: Doc updates.** Status/record edits only — no normative
rewrites; the design docs' contracts were satisfied, not changed (except the
G2 clause already committed in Task 4).

- [ ] **Step 2: Integration evidence (repo rule for DSL/frontend changes).**
Compile-and-dry-run the sole production consumer end to end:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
```

(If the drain family's launch wrapper is named differently at execution time,
use the wrapper the verified-iteration workstream's runs used — check
`.orchestrate/runs/` history; record which command served as evidence.)

- [ ] **Step 3: Commit.**

```bash
git add docs/design/workflow_lisp_parametric_type_system.md \
  docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  docs/capability_status_matrix.md docs/index.md \
  docs/workflow_lisp_g6_verification_gate.json
git commit -m "Record backlog-drain generic migration in design docs"
```

---

## Self-Review Notes (drafting time)

- **Spec coverage:** prerequisite 3 → Task 4; prerequisite 4 → Tasks 3+5;
  prerequisite 5 → Task 6; prerequisite 6 → Task 7; per-form migration test
  points 1–4 → Tasks 4/7 (smaller+clearer, retirement), 6 (parity), 3+5
  (checkpoint identity); form-registry reclassification → Task 7; acceptance
  check "minimal-caller fixture per stdlib generic" → Task 4.
- **Known unknowns are named** (G1–G5) with owning tasks and STOP protocols,
  because this plan is deliberately drafted against a moving tree; Task 1 is
  the drift net, Task 2 the feasibility net.
- **Not in scope:** `with-phase`/`phase-scope` migration (the other
  migration-destined family); extending subset semantics for extra-variant
  callers (G3 raises it if hit); any change to the `std/drain` terminal
  helpers' semantics; YAML-side drain workflows.
