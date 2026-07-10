# Lowering Fork Migration and Shim Retirement Plan (Tranche 1 remainder)

> **Execution status (completed 2026-07-09):** Tasks 1-8 are committed through `3ff5492b`; no later committed change touches the plan-owned lowering paths. Task 9 is verified below. The only remaining `lowering_core` imports and attribute references are the explicitly frozen `phase_drain.py` / `drain_terminal.py` residue owned by the drain/G8 retirement plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the phase_scope↔workflow_calls fork (nine diverged helper pairs, with the fix stream stranded on workflow_calls) and then retire the `lowering_core` forwarder-shim pattern (~120 forwarders across 10 modules) by threading recursion through `_LoweringContext` and direct owner imports.

**Architecture:** Consolidation direction is fixed: **workflow_calls owns** (the package facade and `core.py:243-256` already publish its versions; git shows the hidden-phase-context fixes landed only there). All nine pairs are signature-compatible — where signatures differ, workflow_calls only adds defaulted keyword-only parameters. Shim retirement replaces call-time `lowering_core.X` indirection with (a) direct imports from owner modules for owned helpers and (b) callable fields on `_LoweringContext` for genuine core-owned mutual recursion. No new abstractions beyond those context fields.

**Tech Stack:** Python 3.13, pytest.

## Entry gate

- This plan is not executable until `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md` Tasks 9–12 have landed: phase_scope's four same-file dead shims deleted; `_managed_inputs_from_mapping`/`_record_call_binding_label` consolidated; `_compile_error` lives in `lowering/context.py`; and the fork dossier exists at `docs/plans/2026-07-07-lowering-fork-dossier.md`.
- **Coordination gate with the drain migration** (`docs/plans/2026-07-07-drain-migration-g8-retirement.md`): Tasks 1–3 of this plan may change drain lowering output (they adopt fixes on paths `phase_drain.py`/`phase_flow.py` consume). They must land **before** the drain migration captures its checkpoint-identity baseline, or be deferred until that migration completes. Do not interleave.

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- The working tree may contain the user's in-flight work. **Stage by explicit path only.** Never `git add -A`, `git add -u`, or `git commit -a`.
- Commit messages: short imperative sentence, repo style. No conventional-commit prefixes, no mention of Claude/Claude Code, no Co-Authored-By trailers.
- No worktrees. Never `--no-verify`.
- Narrowest pytest selectors first; fresh output is the verification evidence.
- Do not touch `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` directories.
- Frozen surfaces: `orchestrator/workflow_lisp/lowering/phase_drain.py` lines 592-1979 (post-Phase-1 line numbers may shift — the frozen region is the body of the backlog-drain inline lowering, from `_phase_stdlib_lower_backlog_drain_impl`'s inline branch onward), `orchestrator/workflow_lisp/lowering/drain_terminal.py` (entire file), design-delta gated code in `build.py`, `migration_parity.py`. In `phase_drain.py`, import lines and forwarder defs above the frozen region may be edited; `lowering_core.*` attribute calls **inside** the frozen region stay.
- Line numbers in this plan were verified 2026-07-07 pre-Phase-1; re-anchor by function name (`grep -n "def <name>" <file>`) before each task.
- If a step's verification fails twice, stop and report.

## Baseline rule (applies to Tasks 1–3)

Before each migration task, run and record:
```bash
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_phase_stdlib.py -q 2>&1 | tail -3
```
After the task's edit, rerun. A test that fails because lowered output changed on a phase/drain path is **expected signal** (the stranded fix landing) — inspect the diff: if the new behavior matches the workflow_calls semantics (e.g. hidden phase-context bindings now emitted where the stale copy omitted them), update the test expectation and say so in the commit message. Any failure that does not trace to the migrated helper → revert the pair and report.

---

### Task 1: Migrate the four render-family pairs onto workflow_calls

Pairs (same signatures, small behavioral diffs; phase_scope copy deleted, name re-imported):

| Name | phase_scope def | workflow_calls def | diff size |
|---|---|---|---|
| `_render_argv_tail` | :677 | :430 | 7L vs 4L |
| `_render_boolean_predicate` | :718 | :450 | 30L vs 29L |
| `_render_call_binding_ref` | :750 | :1511 | 16L vs 12L |
| `_render_record_call_bindings` | :768 | :1525 | 30L vs 30L |

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`

**Interfaces:** After this task, `from .phase_scope import <name>` still resolves for existing consumers (re-binding through the import); the single definition lives in `workflow_calls.py`.

- [ ] **Step 1: Read the four diffs in the dossier**

Open `docs/plans/2026-07-07-lowering-fork-dossier.md` sections for these four names. Confirm each classification is `superset-merge onto workflow_calls` (or equivalent). If a section says `needs careful read` and the diff shows phase-path-only behavior with no workflow_calls counterpart, STOP for that pair and report.

- [ ] **Step 2: Delete the four phase_scope defs; extend the import**

Delete each `def` body from `phase_scope.py` and add the four names to the existing `from .workflow_calls import (...)` block (created by Phase-1 Task 10).

- [ ] **Step 3: Verify**

```bash
python -c "from orchestrator.workflow_lisp.lowering import phase_scope, workflow_calls, core"
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_lowering.py -q
```
Apply the Baseline rule above to any diff.

- [ ] **Step 4: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/phase_scope.py
git commit -m "Migrate render helpers onto workflow calls owner"
```

---

### Task 2: Migrate the three managed/runtime-context pairs

Pairs: `_managed_inputs_from_bundle` (ps:546 / wc:404, 1-line diff), `_managed_write_root_requirements_for_callable` (ps:554 / wc:798, same signature), `_runtime_context_default_value` (ps:481 / wc:179, same signature).

Consumers of the stale copies via `from .phase_scope import`: `phase_drain.py:91` and `phase_flow.py:67` both import `_managed_write_root_requirements_for_callable` — they re-bind automatically once phase_scope imports from workflow_calls.

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`

- [ ] **Step 1: Dossier check** (as Task 1 Step 1, for these three names).

- [ ] **Step 2: Delete the three phase_scope defs; extend the `from .workflow_calls import (...)` block.**

- [ ] **Step 3: Verify** — same commands as Task 1 Step 3, plus:

```bash
pytest tests/test_workflow_lisp_wcc_m4.py -q
```
Apply the Baseline rule.

- [ ] **Step 4: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/phase_scope.py
git commit -m "Migrate managed input helpers onto workflow calls owner"
```

---

### Task 3: Migrate the two superset pairs (highest care)

Pairs where workflow_calls extends the signature with defaulted keyword-only params:

- `_managed_write_root_bindings` — ps:582 (5 kwargs) vs wc:824 (adds `context`, `source_expr`, defaulted). Imported from phase_scope by `phase_drain.py:91` and `phase_flow.py:67`.
- `_declare_runtime_context_hidden_inputs` — ps:505 (39 lines, 5 kwargs) vs wc:210 (192 lines, adds 7 defaulted kwonly params: `source_param_name`, `bridge_class`, `binding_id`, `generated_name`, `carried_input_sources`, `carried_source_expr`, `local_values`). This carries the hidden-phase-context fixes (commits a42ae109, 8a311818).

- [ ] **Step 1: Careful read of the wc bodies with old-argument patterns**

For each pair, read the workflow_calls body and confirm: with the new parameters left at their defaults, the code path either (a) reduces to the phase_scope behavior, or (b) differs only by the known fixes (hidden-context binding emission/omission handling). Record the conclusion in one sentence each in the commit message. If neither holds, STOP and report — do not migrate that pair.

- [ ] **Step 2: Enumerate phase_scope-internal call sites**

```bash
grep -n "_managed_write_root_bindings(\|_declare_runtime_context_hidden_inputs(" orchestrator/workflow_lisp/lowering/phase_scope.py orchestrator/workflow_lisp/lowering/phase_drain.py orchestrator/workflow_lisp/lowering/phase_flow.py
```
Confirm all call sites pass keyword arguments compatible with the wc signature (they will, since ps params are a subset). Any call site inside phase_drain's frozen region is read-only context — the call keeps working unchanged.

- [ ] **Step 3: Delete the two phase_scope defs; extend the workflow_calls import.**

- [ ] **Step 4: Verify — full phase/drain surface plus certification smoke**

```bash
python -c "from orchestrator.workflow_lisp.lowering import phase_scope, phase_drain, phase_flow, workflow_calls, core"
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_wcc_m4.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"
```
Apply the Baseline rule; for this task additionally treat **any change in generated step identity** (step ids/checkpoint tokens in lowered output) as a STOP-and-report — that interacts with the drain migration's identity baseline (see Entry gate).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/phase_scope.py
git commit -m "Adopt fixed hidden context and write root helpers from workflow calls"
```

---

### Task 4: Remove the workflow_calls self-round-trips through core

`workflow_calls.py` calls two functions it defines itself via the core back-reference: `lowering_core._declare_runtime_context_hidden_inputs` (2 sites) and `lowering_core._render_call_binding_leaf_ref` (3 sites). Since core imports those names *from* workflow_calls (core.py:243-256), these are identity round-trips.

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`

- [ ] **Step 1: Replace the five attribute calls with bare local calls**

```bash
grep -n "lowering_core\._declare_runtime_context_hidden_inputs\|lowering_core\._render_call_binding_leaf_ref" orchestrator/workflow_lisp/lowering/workflow_calls.py
```
Edit each to drop the `lowering_core.` prefix.

- [ ] **Step 2: Verify** — `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_drain_stdlib.py -q` → PASS (identity change only).

- [ ] **Step 3: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/workflow_calls.py
git commit -m "Call locally owned helpers directly in workflow calls lowering"
```

---

### Task 5: Classify remaining core attribute uses; extend `_LoweringContext` with recursion entry points

Current inventory (2026-07-07; regenerate at execution time): 12 modules hold `from . import core as lowering_core`; ~120 forwarder defs; forwarder counts — control_dispatch 17, phase_drain 20, phase_flow 20, phase_resource 20, phase_scope 20, control_match 9, control_loops 4, values 4, drain_terminal 4 (frozen), materialize_view 2; non-forwarder attribute uses concentrate in effects.py (15 distinct) and workflow_calls.py.

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/context.py` (add callable fields)
- Modify: `orchestrator/workflow_lisp/lowering/core.py` (populate the fields where `_LoweringContext` is constructed)
- Create: none

**Interfaces:** Produces `_LoweringContext` fields (names final at execution time, pattern fixed here):

```python
    # recursion entry points, set by core at construction; break the
    # leaf -> core back-import cycle for mutual recursion only
    lower_expression: Callable[..., Any] | None = None
    lower_call_expr: Callable[..., Any] | None = None
    record_step_origin: Callable[..., Any] | None = None
    normalize_generated_step_id: Callable[..., Any] | None = None
```

- [ ] **Step 1: Regenerate the classification table**

```bash
python - <<'EOF'
import re, pathlib, collections, json
root = pathlib.Path('orchestrator/workflow_lisp/lowering')
report = {}
for p in sorted(root.glob('*.py')):
    src = p.read_text()
    names = sorted(set(re.findall(r'lowering_core\.(\w+)', src)))
    if names:
        report[p.name] = names
print(json.dumps(report, indent=1))
EOF
```

Classify every name into exactly one bucket:
- **owner-import**: defined in a leaf/owner module (workflow_calls, phase_impl, values, context, diagnostics…) and merely re-exported by core → replace with a direct `from .<owner> import name`. Find the owner with `grep -rn "^def <name>" orchestrator/workflow_lisp/lowering/*.py`.
- **context-callable**: defined in core and mutually recursive with leaf modules (`_lower_expression`, `_lower_call_expr`, `_record_step_origin`, `_normalize_generated_step_id`, and any other core-owned name the classification surfaces) → route through the new `_LoweringContext` fields.
- **frozen**: any use inside phase_drain's frozen region or anywhere in drain_terminal.py → leave untouched.

Commit the table as an appendix section appended to `docs/plans/2026-07-07-lowering-fork-dossier.md`.

- [ ] **Step 2: Add the context fields and populate them in core**

Add the callable fields to `_LoweringContext` (context.py:176 region, matching the dataclass style there). In core.py, at every `_LoweringContext(` construction site (`grep -n "_LoweringContext(" orchestrator/workflow_lisp/lowering/core.py`), pass the core functions. Field must default to `None` so unrelated constructions elsewhere keep working; call sites in leaf modules use `context.lower_expression(...)` only where a context is in scope — where no context is in scope, the name stays an owner-import or (if core-owned and context-free) a deferred function-body import, mirroring `procedures.py:132`.

- [ ] **Step 3: Verify** — `python -c "from orchestrator.workflow_lisp.lowering import core, context" && pytest tests/test_workflow_lisp_lowering.py -q` → PASS (fields unused so far).

- [ ] **Step 4: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/context.py orchestrator/workflow_lisp/lowering/core.py docs/plans/2026-07-07-lowering-fork-dossier.md
git commit -m "Add lowering context recursion entry points"
```

---

### Task 6: De-shim the small modules (materialize_view, values, control_loops, control_match)

35 forwarders + assorted attribute uses; smallest blast radius first.

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/materialize_view.py`, `values.py`, `control_loops.py`, `control_match.py`

- [ ] **Step 1 (per module, one commit each):** Using the Task-5 table: delete each forwarder def, add the owner-import or switch calls to `context.<field>` per its bucket; replace non-forwarder `lowering_core.X` uses the same way; finally delete the module's `from . import core as lowering_core` line once `grep -c "lowering_core\." <file>` is 0.

- [ ] **Step 2 (per module):** Verify:

```bash
python -c "from orchestrator.workflow_lisp.lowering import <module>, core"
pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_wcc_m4.py -q
```
For control_loops also run `pytest tests/test_workflow_lisp_wcc_m4.py -q -k loop`; tests/test_workflow_lisp_wcc_m4.py:790 binds control_loops internals — if a moved name is bound there, keep a module-level alias.

- [ ] **Step 3 (per module):** Commit: `git add <file>` / `git commit -m "Retire core forwarder shims in <module>"`.

---

### Task 7: De-shim the phase family (phase_resource, phase_scope, phase_flow) and effects

60 forwarders + effects.py's 15 attribute-use names. Same procedure as Task 6, one module per commit, order: phase_resource → phase_scope → phase_flow → effects. Suites per commit:

```bash
pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_drain_stdlib.py -q
```

- [ ] phase_resource converted, verified, committed
- [ ] phase_scope converted, verified, committed
- [ ] phase_flow converted, verified, committed
- [ ] effects converted, verified, committed

---

### Task 8: De-shim control_dispatch and (partially) phase_drain

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/control_dispatch.py`, `phase_drain.py`

- [ ] **Step 1: control_dispatch** — full conversion per the Task-5 table (17 forwarders + 5 attribute names incl. `_lower_backlog_drain`, `_lower_finalize_selected_item`, `_lower_with_phase` — these are core-owned dispatch targets: route via owner-import from their defining module per the table, or context-callable if core-owned). Verify with `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_wcc_m4.py -q`; note `_control_lower_expression_impl` (control_dispatch.py:185-260) is schema-1-only — do not delete it here (that retirement belongs to the drain/G8 plan's optional LEGACY phase). Commit.

- [ ] **Step 2: phase_drain, frozen-aware partial conversion** — convert ONLY the forwarder defs above the frozen region (delete forwarder, add owner-import; bare call sites inside the frozen region keep resolving to the imported name — zero text change inside the region). Leave every `lowering_core.*` attribute call inside the frozen region and leave `drain_terminal.py` entirely. Afterward `grep -n "lowering_core\." orchestrator/workflow_lisp/lowering/phase_drain.py` must list only frozen-region lines; record them in the commit message. Verify: `pytest tests/test_workflow_lisp_drain_stdlib.py -q` and `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"`. Commit.

---

### Task 9: Final sweep and gate

- [x] **Step 1:** `grep -rln "import core as lowering_core" orchestrator/workflow_lisp/lowering/` → expected: only `phase_drain.py` and `drain_terminal.py` (frozen residue, retired by the drain/G8 plan).
- [x] **Step 2:** Full lowering surface: `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_wcc_m1.py tests/test_workflow_lisp_wcc_m2.py tests/test_workflow_lisp_wcc_m4.py -q` → PASS.
- [x] **Step 3:** Full suite in tmux: `pytest -q` → same pass set as before this plan.
- [x] **Step 4:** Report lines deleted, remaining frozen residue, and any expectation updates made under the Baseline rule.

#### Task 9 closeout evidence (2026-07-09)

- The residue grep returned exactly `phase_drain.py` and `drain_terminal.py`.
- The exact six-module lowering selector passed: **386 passed in 25.86s**.
- Full suite at `78deb6759710` completed with **6 failed, 4073 passed, 11 skipped in 947.91s**. All six failure identities match both the executor closeout baseline and direct execution of those selectors at pre-plan revision `93a34adf`; they are not lowering-fork regressions.
- The exact plan commit set deleted 768 code lines and inserted 277, for **491 net code lines removed**. Including the 116-line dossier appendix, the tranche removed 375 net lines.
- No test file changed in the plan commits, so Baseline-rule expectation updates were **zero**.
- Thirteen `lowering_core.` references remain: nine in `phase_drain.py` (one documented import-cycle-required `_normalize_generated_step_id` forwarder and eight frozen-body references) and four frozen forwarders in `drain_terminal.py`. Their retirement remains owned by the drain/G8 plan.
