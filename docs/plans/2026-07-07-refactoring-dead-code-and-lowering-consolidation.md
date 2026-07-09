# Refactoring Plan: Dead-Code Removal, Latent-Bug Fixes, Lowering Consolidation (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the ungated portion of the 2026-07-07 refactoring brainstorm — verified dead-code deletions, three latent-bug fixes, the first lowering-fork consolidation increments, and the YAML-estate triage — while leaving every migration-gated surface untouched.

**Architecture:** Pure subtraction plus two ownership moves. No new abstractions. Every task is one commit that compiles and passes its named test selectors. The drain intrinsic lowering (`lowering/phase_drain.py:592-1979`, `lowering/drain_terminal.py`) and the design-delta certification bundle are **frozen** — no task here touches them.

**Tech Stack:** Python 3.13, pytest, pyflakes 3.4.0 (already installed).

**Scope assumption (recorded):** The brainstorm's Tranches 2–5 (typecheck family completion, build.py split, executor decomposition, drain migration/G8/bundle retirement) and YAML-retirement steps 2–6 are follow-on plans, listed in the Roadmap section at the end. This plan is Tranche 0 + Tranche 1 increments 1–2 + the fork dossier + YAML triage.

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- The working tree contains the user's in-flight work. **Stage by explicit path only** (`git add <file> <file>`). Never `git add -A`, `git add -u`, or `git commit -a`.
- Commit messages: short imperative sentence, matching repo style (e.g. `Route selector and gap drafting to stronger models`). **No** conventional-commit prefixes, **no** mention of Claude/Claude Code, **no** Co-Authored-By trailers.
- No worktrees. Never use `--no-verify`.
- Narrowest pytest selectors first; treat fresh command output as the verification evidence. After changing any test module, run `pytest --collect-only <module>` on it.
- Do not touch `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` directories — they are compile-evidence inputs for the certification lane.
- Frozen surfaces (do not modify): `orchestrator/workflow_lisp/lowering/phase_drain.py` lines 592-1979, `orchestrator/workflow_lisp/lowering/drain_terminal.py`, everything gated on the `lisp_frontend_design_delta/drain::drain` entry in `build.py`, `migration_parity.py`.
- If a step's verification fails twice in a row, stop and report instead of forcing it green.

---

## Phase A — Zero-risk deletions and latent-bug fixes

### Task 0: Capture the pre-plan full-suite baseline

The tree may carry pre-existing failures owned by concurrent workstreams. Every later "Expected: PASS" for a broad suite means "no NEW failures versus this baseline". This must complete before Task 1 — the suite must not run concurrently with tree edits.

**Files:** none (evidence only; do not commit the baseline file)

- [ ] **Step 1: Run the full suite in tmux (use the tmux skill)**

```bash
mkdir -p .superpowers/sdd
pytest -q 2>&1 | tee .superpowers/sdd/refactor-baseline-pytest.txt
```

Wait for completion. Record the tail (pass/fail counts and any failing test ids) in the progress ledger.

---

### Task 1: Delete `stage7_metrics.py` and its test suite

**Files:**
- Delete: `orchestrator/workflow_lisp/stage7_metrics.py` (470 lines)
- Delete: `tests/test_workflow_lisp_stage7_metrics.py`

**Interfaces:** Produces nothing; nothing imports this module (verified: only its own test file references it).

- [ ] **Step 1: Re-verify zero importers**

Run:
```bash
grep -rln "stage7_metrics" orchestrator/ tests/ scripts/ workflows/ 2>/dev/null
```
Expected output — exactly these two paths and nothing else:
```
orchestrator/workflow_lisp/stage7_metrics.py
tests/test_workflow_lisp_stage7_metrics.py
```
If anything else appears, STOP and report. (`docs/` is deliberately excluded: several historical plan documents mention the module by name; prose references do not block deletion.)

- [ ] **Step 2: Delete both files**

```bash
git rm orchestrator/workflow_lisp/stage7_metrics.py tests/test_workflow_lisp_stage7_metrics.py
```

- [ ] **Step 3: Verify the package still imports and collection is clean**

Run: `python -c "import orchestrator.workflow_lisp" && pytest tests/ -q --collect-only > /dev/null && echo COLLECT_OK`
Expected: `COLLECT_OK`

- [ ] **Step 4: Commit**

```bash
git commit -m "Delete unused stage7 metrics module and suite"
```

---

### Task 2: Delete `runtime_closure_design_fixtures.py`, its test suite, and its README pointer

**Files:**
- Delete: `orchestrator/workflow_lisp/runtime_closure_design_fixtures.py` (573 lines)
- Delete: `tests/test_workflow_lisp_runtime_closure_fixtures.py`
- Modify: `orchestrator/workflow_lisp/README.md:248-252`

**Interfaces:** Produces nothing; the README keeps the runtime-closure *policy* sentence (that contract is live) while dropping the module pointer.

- [ ] **Step 1: Re-verify zero importers**

Run:
```bash
grep -rln "runtime_closure_design_fixtures" orchestrator/ tests/ scripts/ workflows/ 2>/dev/null
```
Expected — exactly (the module does not self-reference, so it does not appear in its own results):
```
orchestrator/workflow_lisp/README.md
tests/test_workflow_lisp_runtime_closure_fixtures.py
```

- [ ] **Step 2: Delete the module and test**

```bash
git rm orchestrator/workflow_lisp/runtime_closure_design_fixtures.py tests/test_workflow_lisp_runtime_closure_fixtures.py
```

- [ ] **Step 3: Update the README paragraph**

In `orchestrator/workflow_lisp/README.md`, replace:

```markdown
Runtime closures remain deferred. `runtime_closure_design_fixtures.py` is a
test-only rejection harness for disabled/design-fixture closure cases; it must
not participate in ordinary compilation, and normal Workflow Lisp artifacts
must not emit runtime-closure payloads, registries, or invocation nodes.
`let-proc` remains compile-time-only.
```

with:

```markdown
Runtime closures remain deferred. Normal Workflow Lisp artifacts must not emit
runtime-closure payloads, registries, or invocation nodes. `let-proc` remains
compile-time-only.
```

- [ ] **Step 4: Verify import + collection**

Run: `python -c "import orchestrator.workflow_lisp" && pytest tests/ -q --collect-only > /dev/null && echo COLLECT_OK`
Expected: `COLLECT_OK`

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/README.md
git commit -m "Delete runtime-closure design fixture harness"
```

---

### Task 3: Delete nine orphaned `.orc` test fixtures

**Files (delete all nine; each verified to have zero references in any `.py` file):**
- `tests/fixtures/workflow_lisp/invalid/provider_result_bad_return.orc`
- `tests/fixtures/workflow_lisp/invalid/resource_stdlib_finalize_selected_item_constraint_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/if_variant_proof_missing.orc`
- `tests/fixtures/workflow_lisp/invalid/let_proc_bare_call.orc`
- `tests/fixtures/workflow_lisp/invalid/pointer_effect_lineage_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/command_boundary_effect_promotion_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_result_contract_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/backlog_drain_hidden_compatibility_bridge_reread_invalid.orc`
- `tests/fixtures/workflow_lisp/valid/defun_local.orc`

Note: there is no directory-scan test over these fixture dirs. `tests/test_workflow_lisp_verification_gate.py::_iter_checked_in_orc_fixtures` resolves only fixture filenames *referenced as string constants in source* — unreferenced fixtures are invisible to it.

- [ ] **Step 1: Re-verify zero references (repo-wide, not just tests)**

Run:
```bash
for f in provider_result_bad_return resource_stdlib_finalize_selected_item_constraint_invalid \
         if_variant_proof_missing let_proc_bare_call pointer_effect_lineage_invalid \
         command_boundary_effect_promotion_invalid review_loop_result_contract_invalid \
         backlog_drain_hidden_compatibility_bridge_reread_invalid defun_local; do
  echo "== $f =="; grep -rn "$f\.orc" --include="*.py" --include="*.json" --include="*.md" \
    orchestrator/ tests/ workflows/ scripts/ 2>/dev/null | grep -v "\.orc:"
done
```
Expected: no output under any header. Any hit → drop that fixture from the deletion list and report.

The grep targets `<name>.orc` deliberately: `review_loop_result_contract_invalid` collides with a live **diagnostic code** of the same name (`lowering/phase_stdlib.py:106,141`, `lowering/phase_scope.py:2324`, `stdlib_contracts.py:166`). The verification-gate resolver (`_iter_checked_in_orc_fixtures`) only resolves string constants ending in `.orc`, so bare-name hits on the diagnostic code do not reference — and do not protect — the fixture.

Caution: `backlog_drain_hidden_compatibility_bridge_reread_invalid` must not be confused with `..._public_boundary_invalid.orc`, which is live and currently modified in the working tree.

- [ ] **Step 2: Delete and verify the gate suite still passes**

```bash
git rm tests/fixtures/workflow_lisp/invalid/provider_result_bad_return.orc \
       tests/fixtures/workflow_lisp/invalid/resource_stdlib_finalize_selected_item_constraint_invalid.orc \
       tests/fixtures/workflow_lisp/invalid/if_variant_proof_missing.orc \
       tests/fixtures/workflow_lisp/invalid/let_proc_bare_call.orc \
       tests/fixtures/workflow_lisp/invalid/pointer_effect_lineage_invalid.orc \
       tests/fixtures/workflow_lisp/invalid/command_boundary_effect_promotion_invalid.orc \
       tests/fixtures/workflow_lisp/invalid/review_loop_result_contract_invalid.orc \
       tests/fixtures/workflow_lisp/invalid/backlog_drain_hidden_compatibility_bridge_reread_invalid.orc \
       tests/fixtures/workflow_lisp/valid/defun_local.orc
pytest tests/test_workflow_lisp_verification_gate.py -q
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git commit -m "Delete orphaned workflow lisp fixtures"
```

---

### Task 4: Remove dead/shadowed code in `typecheck_dispatch.py`

Pre-authorized by `docs/design/workflow_lisp_parametric_type_system.md` (deletable "independently of this tranche"). Three independent edits, one commit.

Background: module-level `def` statements bind last, so a local `def _raise_error` at the bottom of the module shadows the `raise_error as _raise_error` import at the top for **all** call sites. The local raise helpers are byte-equivalent to the imported ones (delete the locals, imports take over — zero behavior change). Four typecheck_effects helpers are the opposite case: the locals differ semantically from the family-module versions, so the locals stay and the **import aliases** are the dead code.

**Files:**
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py` (import block ~:111-131; dead helper :3236-3262; local raise helpers :3317-3357)

**Interfaces:** No public-surface change. `_raise_error`/`_raise_required_lint` call sites throughout the module now resolve to `typecheck_context.raise_error`/`raise_required_lint` via the existing import aliases.

- [ ] **Step 1: Prove the raise helpers are equivalent before deleting**

Run:
```python
python - <<'EOF'
import ast
def grab(path, names):
    tree = ast.parse(open(path).read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out[node.name] = ast.dump(node)  # last binding wins, matching runtime
    return out
d = grab('orchestrator/workflow_lisp/typecheck_dispatch.py', {'_raise_error', '_raise_required_lint'})
c = grab('orchestrator/workflow_lisp/typecheck_context.py', {'raise_error', 'raise_required_lint'})
assert d['_raise_error'].replace('_raise_error', 'raise_error') == c['raise_error'], 'raise_error differs'
assert d['_raise_required_lint'].replace('_raise_required_lint', 'raise_required_lint') == c['raise_required_lint'], 'raise_required_lint differs'
print('EQUIVALENT')
EOF
```
Expected: `EQUIVALENT`. If an assert fires, STOP — do not delete; report the diff.

- [ ] **Step 2: Delete the two local raise-helper defs**

Delete the entire `def _raise_required_lint(...)` and `def _raise_error(...)` functions at the bottom of `typecheck_dispatch.py` (currently :3317-3357 — both take `message, *, code, span, form_path, expansion_stack=()` and raise `LispFrontendCompileError`). Keep the `raise_error as _raise_error, raise_required_lint as _raise_required_lint` aliases in the `from .typecheck_context import (...)` block — they now serve every call site.

- [ ] **Step 3: Delete the confirmed-dead helper**

Delete `def _require_union_variant_record_field(...)` (currently :3236-3262 — its only reference repo-wide is its own definition; the live twin is `typecheck_calls.py:425-450`).

- [ ] **Step 4: Remove the four shadowed import aliases**

In the `from .typecheck_effects import (...)` block, delete exactly these four lines (their local shadowing defs at :2821, :2986, :3070, :3298 are the live owners and stay):

```python
    is_macro_introduced_effect as _is_macro_introduced_effect,
    typecheck_expected_extern_operand as _typecheck_expected_extern_operand,
    validate_command_argv as _validate_command_argv,
    validate_semantic_command_adapter_usage as _validate_semantic_command_adapter_usage,
```

Keep `typecheck_command_result_expr`, `typecheck_provider_bundle_path_expr`, `typecheck_provider_result_expr` aliases — they are not shadowed.

- [ ] **Step 5: Verify**

Run:
```bash
pyflakes orchestrator/workflow_lisp/typecheck_dispatch.py
pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_structured_results.py -q
```
Expected: pyflakes reports no `imported but unused` / `redefinition` lines for the six names touched; all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/typecheck_dispatch.py
git commit -m "Remove shadowed and dead typecheck dispatch helpers"
```

---

### Task 5: Delete `head_has_feature_tag` and three dead package re-exports

**Files:**
- Modify: `orchestrator/workflow_lisp/form_registry.py:671-674`
- Modify: `orchestrator/workflow_lisp/__init__.py` (imports ~:9-17; `__all__` entries at ~:118, :124, :145)

- [ ] **Step 1: Re-verify no callers/importers**

Run:
```bash
grep -rn "head_has_feature_tag" orchestrator/ tests/ | grep -v "def head_has_feature_tag"
grep -rn "from orchestrator.workflow_lisp import" orchestrator/ tests/ scripts/ | grep -E "CertifiedAdapterInvocationProtocol|BoolRefCondition|LiteralBoolCondition"
grep -rn "workflow_lisp\.(CertifiedAdapterInvocationProtocol|BoolRefCondition|LiteralBoolCondition)" -E orchestrator/ tests/
```
Expected: no output from any command.

- [ ] **Step 2: Delete the function**

In `form_registry.py`, delete:
```python
def head_has_feature_tag(name: str, tag: str) -> bool:
```
and its body (currently :671-674).

- [ ] **Step 3: Trim `__init__.py`**

- In `from .command_boundaries import (...)`: delete the `CertifiedAdapterInvocationProtocol,` line (keep `CertifiedAdapterInputField`). If the block then has one name, collapse to a single-line import.
- In `from .conditionals import (...)`: delete `BoolRefCondition,` and `LiteralBoolCondition,` (keep `ConditionShape`, `classify_condition_expr`).
- In `__all__`: delete the `"CertifiedAdapterInvocationProtocol",`, `"BoolRefCondition",`, `"LiteralBoolCondition",` entries.

The three names remain defined and used inside their home modules — only the package-level re-export is dead.

- [ ] **Step 4: Verify**

Run: `python -c "import orchestrator.workflow_lisp" && pyflakes orchestrator/workflow_lisp/__init__.py && pytest tests/ -q --collect-only > /dev/null && echo OK`
Expected: `OK` (pyflakes silent for the touched lines).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/__init__.py
git commit -m "Drop dead form registry helper and package re-exports"
```

---

### Task 6: Give `WorkflowExecutor.resume_mode` an `__init__` default

Latent-attribute bug: `self.resume_mode` is assigned only inside `execute()` (executor.py:2968); `calls.py:807` reads it as a direct attribute and would `AttributeError` on any pre-`execute()` path. Six other sites read it defensively via `getattr`. Fix: initialize in `__init__`. Leave the existing `getattr` reads unchanged — 9 tests construct via `WorkflowExecutor.__new__` (bypassing `__init__`) and rely on the `getattr` default, so converting reads to direct access is out of scope here.

**Files:**
- Modify: `orchestrator/workflow/executor.py` (`__init__`, anchor line at :702)

- [ ] **Step 1: Add the default**

In `WorkflowExecutor.__init__`, directly after:
```python
        self._lexical_restore_overlay: Optional[Dict[str, Any]] = None
```
add:
```python
        self.resume_mode = False
```

- [ ] **Step 2: Verify**

Run: `pytest tests/test_workflow_executor_characterization.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/workflow/executor.py
git commit -m "Initialize executor resume mode in constructor"
```

---

### Task 7: Fix the duplicate `_iter_surface_steps` in `build.py` (real traversal bug)

`build.py` defines `_iter_surface_steps` twice. The first (:3132) is the correct typed traversal — it recurses into `repeat_until.steps`, `then_branch.steps`, `else_branch.steps`, `match_cases[*].steps`, and `for_each_steps`. The second (:4227) shadows it for **all** callers and traverses attribute names that do not exist on `SurfaceStep` (`then_steps`, `else_steps`, `repeat_until_steps`, `match`), so both call sites — `_collect_provider_input_shape_observations` (:3251) and `_collect_entry_publication_lowerings` (:4118) — currently miss every step nested under repeat-until, if-branches, and match cases. Fix: delete the second definition.

**Files:**
- Modify: `orchestrator/workflow_lisp/build.py` (delete def at :4227 through its `return tuple(collected)`)
- Test: `tests/test_workflow_lisp_build_artifacts.py` (append new test)

**Interfaces:** Produces: the single surviving `_iter_surface_steps(steps) -> list[SurfaceStep]` used by both call sites.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_workflow_lisp_build_artifacts.py`:

```python
def test_iter_surface_steps_traverses_repeat_until_and_match_children():
    from orchestrator.workflow.surface_ast import (
        SurfaceMatchCaseBlock,
        SurfaceRepeatUntilBlock,
        SurfaceStep,
        SurfaceStepKind,
    )
    from orchestrator.workflow_lisp.build import _iter_surface_steps

    nested_provider = SurfaceStep(
        name="inner-provider", step_id="inner-provider", kind=SurfaceStepKind.PROVIDER
    )
    loop_step = SurfaceStep(
        name="loop-step",
        step_id="loop-step",
        kind=SurfaceStepKind.REPEAT_UNTIL,
        repeat_until=SurfaceRepeatUntilBlock(
            token="loop-1",
            step_id="loop-1",
            steps=(nested_provider,),
            outputs={},
            condition=None,
            max_iterations=3,
        ),
    )
    case_child = SurfaceStep(
        name="case-child", step_id="case-child", kind=SurfaceStepKind.COMMAND
    )
    match_step = SurfaceStep(
        name="match-step",
        step_id="match-step",
        kind=SurfaceStepKind.MATCH,
        match_cases={
            "DONE": SurfaceMatchCaseBlock(
                case_name="DONE", token="m-1", step_id="m-1", steps=(case_child,)
            )
        },
    )
    names = [step.name for step in _iter_surface_steps((loop_step, match_step))]
    assert names == ["loop-step", "inner-provider", "match-step", "case-child"]
```

- [ ] **Step 2: Run it — must fail against the shadowing definition**

Run: `pytest tests/test_workflow_lisp_build_artifacts.py::test_iter_surface_steps_traverses_repeat_until_and_match_children -v`
Expected: FAIL with `assert ['loop-step', 'match-step'] == ['loop-step', 'inner-provider', 'match-step', 'case-child']` (the broken def collects only top-level steps here).

- [ ] **Step 3: Delete the second definition**

In `build.py`, delete this entire function (currently :4227-4252, immediately before `def _serialize_design_delta_adapter_census`):

```python
def _iter_surface_steps(steps: Any) -> tuple[Any, ...]:
    collected: list[Any] = []
    if not isinstance(steps, tuple):
        steps = tuple(steps)
    for step in steps:
        collected.append(step)
        match_block = getattr(step, "match", None)
        if isinstance(match_block, Mapping):
            cases = match_block.get("cases", {})
            if isinstance(cases, Mapping):
                for case in cases.values():
                    nested_steps = getattr(case, "steps", None)
                    if nested_steps:
                        collected.extend(_iter_surface_steps(nested_steps))
        for attr_name in ("then_steps", "else_steps", "repeat_until_steps", "for_each_steps"):
            nested_steps = getattr(step, attr_name, None)
            if nested_steps:
                collected.extend(_iter_surface_steps(nested_steps))
    return tuple(collected)
```

The definition at :3132 (which already handles `repeat_until`, `then_branch`, `else_branch`, `match_cases`, `for_each_steps`) now serves both call sites.

- [ ] **Step 4: Run the new test and the affected report suites**

Run:
```bash
pytest tests/test_workflow_lisp_build_artifacts.py::test_iter_surface_steps_traverses_repeat_until_and_match_children -v
pytest tests/test_workflow_lisp_build_artifacts.py -q
pytest tests/test_workflow_lisp_rendering_ergonomics.py tests/test_workflow_lisp_entry_publication.py -q
```
Expected: new test PASS; the full build-artifacts suite (which pins report payloads) passes with no new failures versus the Task 0 baseline. The two report suites exercise the enriched traversal (`provider_input_shapes`, entry-publication lowerings). If a test there fails because it pinned the previously incomplete observation set, inspect: an expectation that gains rows for genuinely nested provider/materialize_view steps is the bug fix landing — update that expectation and note it in the commit message. Any other failure → STOP and report.

- [ ] **Step 5: Smoke the certification compile (this file feeds design-delta reports)**

Run: `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"`
Expected: PASS (these are the parity target's smoke evidence commands).

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/build.py tests/test_workflow_lisp_build_artifacts.py
git commit -m "Fix shadowed surface step traversal in build reports"
```

---

### Task 8: Guarded unused-import sweep over `orchestrator/`

pyflakes reports ~472 unused imports. Blind removal is unsafe: several lowering/typecheck modules import names **purely to re-export** them (the compatibility-shim pattern), and pyflakes flags those too. Consumers reach re-exports two ways, and the guard must cover both:

1. `from flagging_module import name` — caught by a from-import grep.
2. **Attribute-style facade consumption** — `from . import flagging_module as alias` then `alias.name`. Confirmed live instance: pyflakes flags `typecheck.py`'s re-exports (e.g. `_hidden_context_omission_allowed`) as unused, while `typecheck_effects.py:59,145,204` consumes them via `from . import typecheck as compat` + `compat._name`. A from-import-only guard would delete these and break runtime paths the spot-check suites do not cover.

**Files:**
- Modify: multiple modules under `orchestrator/` (one commit per top-level package: `orchestrator/workflow_lisp/`, `orchestrator/workflow/`, `orchestrator/cli/`, remainder)
- Exclude entirely: any `__init__.py`, `orchestrator/workflow_lisp/typecheck.py` (the compat facade — every import there is a deliberate re-export), plus files already handled in Tasks 4–5.

- [ ] **Step 1: Generate the guarded candidate list**

```bash
mkdir -p /tmp/refactor-sweep
python - <<'EOF'
import re, subprocess, pathlib
out = subprocess.run(["pyflakes", "orchestrator/"], capture_output=True, text=True).stdout
candidates = []
for line in out.splitlines():
    m = re.match(r"(.+?):(\d+):\d+:? '(.+?)' imported but unused", line)
    if not m:
        continue
    path, lineno, name = m.group(1), int(m.group(2)), m.group(3)
    if path.endswith("__init__.py") or path.endswith("workflow_lisp/typecheck.py"):
        continue
    short = name.split(" as ")[-1].split(".")[-1]
    mod = pathlib.Path(path).stem
    # guard 1: is `short` imported FROM this module elsewhere?
    g = subprocess.run(
        ["grep", "-rlE", rf"from .*\b{mod}\b import (\(|.*\b{short}\b)", "orchestrator/", "tests/"],
        capture_output=True, text=True).stdout.strip().splitlines()
    consumers = [c for c in g if c != path]
    if consumers:
        continue  # potential re-export; skip
    # guard 2: attribute-style consumption anywhere else (`alias.short` facade pattern).
    # Over-excludes on name coincidences — acceptable: a skipped candidate is merely not cleaned.
    g2 = subprocess.run(
        ["grep", "-rlE", rf"\.{re.escape(short)}\b", "orchestrator/", "tests/"],
        capture_output=True, text=True).stdout.strip().splitlines()
    attr_consumers = [c for c in g2 if c != path]
    if attr_consumers:
        continue  # potential facade re-export; skip
    candidates.append(f"{path}:{lineno}: {name}")
open("/tmp/refactor-sweep/unused_imports.txt", "w").write("\n".join(candidates) + "\n")
print(len(candidates), "safe candidates")
EOF
```
Expected: a count (will be < 472 because re-export candidates are excluded) and `/tmp/refactor-sweep/unused_imports.txt`.

- [ ] **Step 2: Apply removals package by package**

For each package in order — `orchestrator/workflow_lisp/`, `orchestrator/workflow/`, `orchestrator/cli/`, remaining `orchestrator/*` — edit each file listed in `unused_imports.txt`, removing only the named import (drop the name from a parenthesized list, or the whole statement if it becomes empty). After each package:

```bash
pyflakes <package> | grep "imported but unused" | wc -l   # should shrink accordingly
python -c "import orchestrator; import orchestrator.workflow_lisp; import orchestrator.workflow; import orchestrator.cli.main"
pytest tests/ -q --collect-only > /dev/null && echo COLLECT_OK
```

- [ ] **Step 3: Targeted behavioral spot-check per package**

Run after workflow_lisp batch: `pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_lowering.py -q`
Run after workflow batch: `pytest tests/test_workflow_executor_characterization.py -q`
Run after cli batch: `pytest tests/test_cli_safety.py -q`
Expected: no new failures versus the Task 0 baseline (these suites may carry pre-existing failures owned by concurrent workstreams).

- [ ] **Step 4: One commit per package batch**

```bash
git add <explicit files touched in this batch>
git commit -m "Remove unused imports in <package>"
```

---

## Phase B — Lowering consolidation (increments 1–2 + dossier)

Background for all Phase B tasks: `lowering/phase_scope.py` and `lowering/workflow_calls.py` share 15 top-level function names, forked from the same split commit (d7bf3865). Since then the fix stream (e.g. a42ae109, 8a311818 — hidden phase-context fixes) landed only on `workflow_calls.py`. The package facade and `core.py:243-256` already publish the workflow_calls versions; `phase_flow.py:67` and `phase_drain.py:91` still import the stale phase_scope copies of `_managed_write_root_bindings` / `_managed_write_root_requirements_for_callable`. Consolidation direction: **workflow_calls owns**.

### Task 9: Delete four dead same-file shims in `phase_scope.py`

These forwarders near the top of the module are shadowed by later real `def`s in the same file (last binding wins for both internal calls and `from .phase_scope import X`), so they are unreachable:

| Shim (dead) | Shadowed by real def |
|---|---|
| `_render_boolean_predicate` :103 | :718 |
| `_render_call_binding_ref` :121 | :750 |
| `_render_record_call_bindings` :125 | :768 |
| `_join_ref_path` :149 | :2344 |

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`

- [ ] **Step 1: Confirm the shadow list mechanically**

```bash
python - <<'EOF'
import ast
tree = ast.parse(open('orchestrator/workflow_lisp/lowering/phase_scope.py').read())
seen = {}
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        if node.name in seen:
            print(f"{node.name}: dead def at :{seen[node.name]} shadowed by :{node.lineno}")
        seen[node.name] = node.lineno
EOF
```
Expected — exactly four lines for `_render_boolean_predicate`, `_render_call_binding_ref`, `_render_record_call_bindings`, `_join_ref_path`. Delete only what this prints.

- [ ] **Step 2: Delete the four dead shim defs**

Each is a two-line forwarder of the form:
```python
def _render_boolean_predicate(*args, **kwargs):
    return lowering_core._render_boolean_predicate(*args, **kwargs)
```
Delete all four (first/earlier occurrence only, per the Step-1 output).

- [ ] **Step 3: Verify**

Run:
```bash
python -c "from orchestrator.workflow_lisp.lowering import phase_scope"
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_phase_stdlib.py -q
```
Expected: PASS. (Zero behavior change — these defs were unreachable.)

- [ ] **Step 4: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/phase_scope.py
git commit -m "Delete shadowed forwarder shims in phase scope lowering"
```

---

### Task 10: Consolidate the two AST-identical duplicated functions onto `workflow_calls.py`

`_managed_inputs_from_mapping` (phase_scope:470 / workflow_calls:99) and `_record_call_binding_label` (phase_scope:800 / workflow_calls:481) are AST-identical. `workflow_calls.py` does not import `phase_scope` at module scope (verified), so the import direction is safe.

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`

**Interfaces:** Consumers importing these names *from phase_scope* keep working — the import re-binds the same names at module scope.

- [ ] **Step 1: Re-confirm AST identity**

```bash
python - <<'EOF'
import ast
def last_defs(path):
    return {n.name: ast.dump(n) for n in ast.parse(open(path).read()).body if isinstance(n, ast.FunctionDef)}
ps = last_defs('orchestrator/workflow_lisp/lowering/phase_scope.py')
wc = last_defs('orchestrator/workflow_lisp/lowering/workflow_calls.py')
for name in ('_managed_inputs_from_mapping', '_record_call_binding_label'):
    assert ps[name] == wc[name], f'{name} DIVERGED — stop'
print('IDENTICAL')
EOF
```
Expected: `IDENTICAL`. Otherwise STOP.

- [ ] **Step 2: Replace the defs with an import**

In `phase_scope.py`: delete the full bodies of `_managed_inputs_from_mapping` (:470) and `_record_call_binding_label` (:800), and add near the other relative imports at the top:

```python
from .workflow_calls import (
    _managed_inputs_from_mapping,
    _record_call_binding_label,
)
```

- [ ] **Step 3: Verify (cycle check + suites)**

Run:
```bash
python -c "from orchestrator.workflow_lisp.lowering import phase_scope, workflow_calls, core"
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_phase_stdlib.py -q
```
Expected: PASS. Contingency: if the import smoke raises `ImportError` (circular import via a transitive module-scope chain), instead move both function bodies to `lowering/context.py` (a verified leaf — it imports no lowering sibling except `origins`) and import them from `.context` in **both** files; re-run the same verification.

- [ ] **Step 4: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/phase_scope.py
git commit -m "Consolidate duplicated call-binding helpers onto workflow calls owner"
```

---

### Task 11: Move `_compile_error` to `lowering/context.py`; retire its forwarders; merge the three now-identical pairs

`_compile_error` (core.py:2459) is a pure constructor for a lowering-phase `LispFrontendCompileError`. It is reached today through 34 `lowering_core._compile_error(...)` call sites across 11 lowering modules, several per-module forwarder defs, and one deferred import (`procedures.py:132`). Moving it to the leaf `context.py` removes the most common reason for `lowering_core` back-references, and makes three phase_scope/workflow_calls pairs — `_render_call_binding_leaf_ref`, `_render_repeat_until_max_iterations`, `_render_scalar_expr` — byte-identical (they currently differ only by `_compile_error` vs `lowering_core._compile_error` spelling), so they consolidate like Task 10.

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/context.py` (add the function)
- Modify: `orchestrator/workflow_lisp/lowering/core.py` (delete def, import from context)
- Modify: `orchestrator/workflow_lisp/lowering/procedures.py:132` (retarget deferred import)
- Modify: the 11 modules using `lowering_core._compile_error` or defining forwarders: `control_match.py`, `values.py`, `effects.py`, `control_dispatch.py`, `workflow_calls.py`, `phase_flow.py`, `control_loops.py`, `materialize_view.py`, `phase_scope.py`, `phase_drain.py`, `phase_resource.py`

**Interfaces:** Produces: `from .context import _compile_error` — signature unchanged: `_compile_error(*, code: str, message: str, span: SourceSpan, form_path: tuple[str, ...]) -> LispFrontendCompileError`.

Frozen-surface rule for `phase_drain.py`: only the forwarder def (:106-107, outside the frozen range) may be replaced. The three `lowering_core._compile_error(` attribute calls **inside** the frozen range (:867, :878, :924) stay exactly as they are — they keep working because Step 2 re-exports `_compile_error` from core, and they retire with the drain migration.

- [ ] **Step 1: Add the function to `context.py`**

Copy the exact def from `core.py`:

```python
def _compile_error(*, code: str, message: str, span: SourceSpan, form_path: tuple[str, ...]) -> LispFrontendCompileError:
    """Create a single lowering-phase frontend compile error."""

    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                phase="lowering",
            ),
        )
    )
```

Add the imports `context.py` needs for it, copied from `core.py`'s own import lines for `LispFrontendCompileError`, `LispFrontendDiagnostic`, and `SourceSpan` (find them with `grep -n "LispFrontendCompileError\|LispFrontendDiagnostic\|SourceSpan" orchestrator/workflow_lisp/lowering/core.py | head -5` — they come from the `..diagnostics` / source-span modules; use the same module paths).

- [ ] **Step 2: Retire the def in `core.py`**

Delete the `_compile_error` def at core.py:2459 and add `_compile_error` to core's existing `from .context import (...)` block (core already imports from `.context`). This keeps `lowering_core._compile_error` working during the transition and preserves any `from .core import _compile_error` importers.

Run: `python -c "from orchestrator.workflow_lisp.lowering import core" && pytest tests/test_workflow_lisp_lowering.py -q`
Expected: PASS.

- [ ] **Step 3: Replace forwarders and attribute calls module by module**

For each of the 11 modules:
- If it defines `def _compile_error(*args, **kwargs): return lowering_core._compile_error(*args, **kwargs)` (e.g. phase_flow ~:81, phase_drain ~:106), delete that forwarder and add `from .context import _compile_error` to its imports. Bare `_compile_error(...)` call sites need no edit.
- Replace remaining `lowering_core._compile_error(` occurrences with `_compile_error(` (adding the context import if not present).

Check completeness: `grep -rn "lowering_core\._compile_error" orchestrator/workflow_lisp/` → expected: exactly the three phase_drain.py frozen-range sites (:867, :878, :924) and nothing else.
Retarget the deferred import at `procedures.py:132` from `.core` to `.context`.

- [ ] **Step 4: Merge the three now-identical pairs**

Re-run the Task 10 Step-1 AST script extended to `('_render_call_binding_leaf_ref', '_render_repeat_until_max_iterations', '_render_scalar_expr')`. Expected: `IDENTICAL` for all three. Then, as in Task 10: delete the three defs from `phase_scope.py` (:808, :704, :686) and extend phase_scope's `from .workflow_calls import (...)` block with the three names. (`phase_drain.py:95` imports `_render_repeat_until_max_iterations` from phase_scope — that import keeps working through the re-binding.)

- [ ] **Step 5: Verify the full lowering surface**

Run:
```bash
python -c "from orchestrator.workflow_lisp.lowering import core, phase_scope, phase_drain, phase_flow, workflow_calls, control_dispatch, control_match, control_loops, values, effects, materialize_view, phase_resource, procedures"
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_wcc_m4.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/context.py orchestrator/workflow_lisp/lowering/core.py \
        orchestrator/workflow_lisp/lowering/procedures.py <other touched lowering files>
git commit -m "Move compile error constructor to lowering context leaf"
```

---

### Task 12: Produce the diverged-pair dossier (analysis only, no behavior change)

Nine shared names remain genuinely diverged between `phase_scope.py` and `workflow_calls.py` after Tasks 10–11: `_declare_runtime_context_hidden_inputs` (ps ~3,985 chars vs wc ~21,145 — wc carries the hidden-context fixes), `_managed_inputs_from_bundle`, `_managed_write_root_bindings`, `_managed_write_root_requirements_for_callable`, `_render_argv_tail`, `_render_boolean_predicate`, `_render_call_binding_ref`, `_render_record_call_bindings`, `_runtime_context_default_value`. (`_lower_call_expr` in phase_scope is a forwarding shim, not a fork — exclude it.) Their migration is judgment work and gets its own follow-on plan; this task produces the evidence that plan needs.

**Files:**
- Create: `docs/plans/2026-07-07-lowering-fork-dossier.md`

- [ ] **Step 1: Generate the dossier**

```bash
python - <<'EOF'
import ast, difflib, subprocess
PS = 'orchestrator/workflow_lisp/lowering/phase_scope.py'
WC = 'orchestrator/workflow_lisp/lowering/workflow_calls.py'
NAMES = ['_declare_runtime_context_hidden_inputs', '_managed_inputs_from_bundle',
         '_managed_write_root_bindings', '_managed_write_root_requirements_for_callable',
         '_render_argv_tail', '_render_boolean_predicate', '_render_call_binding_ref',
         '_render_record_call_bindings', '_runtime_context_default_value']
def last_defs(path):
    src = open(path).read()
    tree = ast.parse(src)
    return {n.name: (n, src) for n in tree.body if isinstance(n, ast.FunctionDef)}, src
ps, ps_src = last_defs(PS)
wc, wc_src = last_defs(WC)
out = ["# Lowering Fork Dossier (phase_scope vs workflow_calls)", "",
       "Generated for the diverged-pair migration follow-on plan.",
       "Consolidation direction: workflow_calls owns (facade + fix-stream evidence).", ""]
for name in NAMES:
    a = ast.get_source_segment(ps_src, ps[name][0]).splitlines(keepends=True)
    b = ast.get_source_segment(wc_src, wc[name][0]).splitlines(keepends=True)
    log_ps = subprocess.run(['git', 'log', '-L', f':{name}:{PS}', '--format=%h %as %s', '-s'],
                            capture_output=True, text=True).stdout.strip().splitlines()[:5]
    log_wc = subprocess.run(['git', 'log', '-L', f':{name}:{WC}', '--format=%h %as %s', '-s'],
                            capture_output=True, text=True).stdout.strip().splitlines()[:5]
    out += [f"## {name}", "",
            f"- phase_scope def at :{ps[name][0].lineno}; recent history: {log_ps}",
            f"- workflow_calls def at :{wc[name][0].lineno}; recent history: {log_wc}",
            "- Classification: DRAFT — superset-merge candidate unless the diff shows deliberate per-family behavior.",
            "", "```diff"]
    out += [l.rstrip('\n') for l in difflib.unified_diff(a, b, 'phase_scope', 'workflow_calls', n=2)]
    out += ["```", ""]
open('docs/plans/2026-07-07-lowering-fork-dossier.md', 'w').write('\n'.join(out) + '\n')
print('dossier written')
EOF
```
Expected: `dossier written`; the file contains nine sections each with per-copy git history and a unified diff.

- [ ] **Step 2: Review and finalize classifications**

Read the dossier. For each pair set `Classification:` to either `superset-merge onto workflow_calls` (wc adds defaulted params/branches while preserving the ps behavior) or `needs careful read` (control-flow restructured; expected at least for `_declare_runtime_context_hidden_inputs`). Do not migrate anything in this task.

- [ ] **Step 3: Commit**

```bash
git add docs/plans/2026-07-07-lowering-fork-dossier.md
git commit -m "Add lowering fork dossier for diverged helper migration"
```

---

## Phase C — YAML estate triage (Tranche 6 step 1)

### Task 13: Inventory and draft-classify the user-facing YAML workflow estate

Steering desideratum (user, 2026-07-07): retire user-facing YAML support; `.orc` becomes the only authoring surface. First step is a machine-generated inventory with a human-reviewable draft classification.

**Files:**
- Create: `docs/workflow_yaml_estate_triage.md`

- [ ] **Step 1: Generate the inventory**

```bash
python - <<'EOF'
import pathlib, subprocess
rows = []
yamls = sorted(pathlib.Path('workflows').rglob('*.yaml'))
orc_stems = {p.stem for p in pathlib.Path('workflows').rglob('*.orc')}
for p in yamls:
    last = subprocess.run(['git', 'log', '-1', '--format=%as', '--', str(p)],
                          capture_output=True, text=True).stdout.strip() or 'untracked'
    importers = subprocess.run(['grep', '-rl', p.name, 'workflows/', '--include=*.yaml'],
                               capture_output=True, text=True).stdout.strip().splitlines()
    importers = [i for i in importers if i != str(p)]
    in_docs = subprocess.run(['grep', '-l', p.name, 'docs/index.md'],
                             capture_output=True, text=True).stdout.strip()
    run_evidence = subprocess.run(['grep', '-rl', p.name, 'state/', '--include=*.json', '-m', '1'],
                                  capture_output=True, text=True).stdout.strip().splitlines()[:1]
    if 'legacy' in p.name:
        draft = 'delete'
    elif run_evidence or in_docs:
        draft = 'production — needs .orc port + promotion evidence'
    elif importers:
        draft = 'library — retires with its importing family'
    else:
        draft = 'example — port one exemplar or archive'
    rows.append((str(p), last, len(importers), 'yes' if p.stem in orc_stems else 'no',
                 'yes' if (run_evidence or in_docs) else 'no', draft))
out = ["# YAML Workflow Estate Triage (DRAFT)", "",
       "Generated 2026-07-07 for the user-facing YAML retirement sweep.",
       "Classification column is a DRAFT heuristic — review before acting.",
       "Machine-readable migration state should graduate into the route-readiness registry pattern.", "",
       "| path | last commit | yaml importers | .orc twin | run/docs evidence | draft class |",
       "|---|---|---|---|---|---|"]
for r in rows:
    out.append("| " + " | ".join(str(x) for x in r) + " |")
counts = {}
for r in rows:
    counts[r[5]] = counts.get(r[5], 0) + 1
out += ["", "## Draft class counts", ""] + [f"- {k}: {v}" for k, v in sorted(counts.items())]
open('docs/workflow_yaml_estate_triage.md', 'w').write('\n'.join(out) + '\n')
print(len(rows), 'yaml workflows inventoried')
EOF
```
Expected: `109 yaml workflows inventoried` (±the user's in-flight additions) and the triage doc.

- [ ] **Step 2: Sanity-check the known production set**

Verify the table classifies at least these as production: `workflows/examples/lisp_frontend_design_delta_drain.yaml`, `workflows/examples/lisp_frontend_autonomous_drain.yaml`, `workflows/examples/verified_iteration_drain.yaml`. If not, fix the doc by hand (the heuristic is a draft, the doc is the deliverable).

- [ ] **Step 3: Register the doc**

Add a one-line pointer to `docs/workflow_yaml_estate_triage.md` in the appropriate inventory/status section of `docs/index.md` (follow the surrounding entry format).

- [ ] **Step 4: Commit**

```bash
git add docs/workflow_yaml_estate_triage.md docs/index.md
git commit -m "Add draft triage inventory for yaml workflow estate"
```

---

## Final gate: full-suite verification

### Task 14: Full test suite + smoke evidence

- [ ] **Step 1: Full suite (long-running — use the tmux skill)**

Run in tmux: `pytest -q 2>&1 | tee .superpowers/sdd/refactor-final-pytest.txt`
Expected: no new failures versus the Task 0 baseline (`.superpowers/sdd/refactor-baseline-pytest.txt`); diff the failing-test id sets, not just the counts.

- [ ] **Step 2: Orchestrator smoke**

Run: `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"`
Expected: PASS.

- [ ] **Step 3: Report**

Summarize: lines deleted per task, test counts before/after, any expectation updates made in Task 7 Step 4, and the dossier/triage deliverables. Do not push; leave commits local for review.

---

## Roadmap (follow-on plans, in recommended order — NOT part of this plan)

Current cross-plan execution order is governed by
`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`. The
numbered list below is the original follow-on decomposition and remains useful
for scope ownership; use the newer sequence for gates, closeout-versus-replay
decisions, the Design Delta promotion handoff, and the broader procedure-first
initiative.

1. **Diverged-pair migration** — consumes `docs/plans/2026-07-07-lowering-fork-dossier.md`; migrates the nine forks onto workflow_calls one function per commit, phase-consumers first (`phase_flow.py:67`, `phase_drain.py:91` import the stale `_managed_write_root_*` copies today); drain/phase test diffs there are stranded fixes landing, not noise. Then thread recursion entry points through `_LoweringContext` and delete the ~115 remaining forwarder shims + 13 `lowering_core` back-imports.
2. **typecheck_dispatch family completion** — replace `compat._raise_*` with module-scope `typecheck_context` imports (~58 sites); move `_typed`/`_type_label`/`_type_refs_compatible` into `typecheck_context`; per-pair semantic diffs of the four legacy/owner duplicates (:2821, :2986, :3070, :3298); extract resume → drain/phase → resource/view family modules. Structure-lock tests need one assertion edit per move.
3. **build.py split** — isolate the design-delta cluster (:2646-4844) behind `load_design_delta_evidence`/`serialize_design_delta_reports` so its retirement becomes a file deletion; then manifest-io and artifact-writer siblings.
4. **executor.py decomposition** — extract `call_frame_state`, `step_results`, step-kind interpreters, `adjudication_runner` behind kept delegators; `ExecutorRuntime` protocol only after the back-reference surface shrinks.
5. **Drain migration (parametric Tranche 2) → G8 deletion → certification-bundle retirement** — per `docs/design/workflow_lisp_parametric_type_system.md:515-613`; keep `phase_drain.py`/`drain_terminal.py` frozen until the generic route replaces them wholesale; G8 evidence machinery already passes and needs no changes to land the deletion.
6. **YAML retirement steps 2–6** — language-gap list (native bounded loops is the known blocker), port production families through the promotion machinery (design_delta first; decide whether `verified_iteration_drain` gets its own port), split loader.py's YAML parse frontend from the shared validation core, move the dashboard off raw-YAML reads, deprecate the CLI YAML branch, delete per triage.
