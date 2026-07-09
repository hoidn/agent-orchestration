# Executor Decomposition: Extraction-Behind-Delegators for `orchestrator/workflow/executor.py`

> **Execution status (verified 2026-07-09):** Verified at `1600fd7ed6c920c1bd9f3a6890ff10f6d7ee25b0` (`Slice executor run method into prologue and epilogue helpers`). Tasks 2-4 are landed in `a5f02e43cd95542a6f0e41b67543dfe0cfc29b44` (`Extract nested call frame state manager into its own module`), `b85066ae83af39c4cf1cd7ebf8fa628524033d24` (`Extract compiled frontend origin index into its own module`), and `9b331b6f66118bbc234f1163efdec482f2627c35` (`Extract pure step result helpers and switch loop and call executors to direct imports`). Tasks 5a-5e are landed in `98e80f0cb28cbaef2843283144fe93b338cffd77` (`Add step runtime protocol and steps package scaffold`), `3f55ff14bdade3df52bc62a583a95e1476bbc595` (`Extract resource transition step interpreter`), `c32106e7d64f8312fa64236f3edea3104566cef2` (`Extract pure projection step interpreter`), `be2ea0af985dc393cc4efd7669d9440559961fb0` (`Extract scalar step interpreter`), and `36aafed448892b2f773b27c8c507db31bccd15fd` (`Extract materialize view step interpreter behind a permanent delegator`). Task 6 is landed in `0da6e4ca46d436eb29b13974517a8931d7002040` (`Extract adjudication runner into its own module`). Task 7 is landed in `b3d7eb91dc57f334b6a0c737e57f21f82b5f3088` (`Type loop and call executors with an executor runtime protocol`): committed `orchestrator/workflow/executor_runtime.py` exists and, following Task 7's low-overlap decision rule, defines the narrower `LoopRuntime` and `CallRuntime` protocols rather than a single literal `ExecutorRuntime`; `loops.py` and `calls.py` use those committed contracts. Task 8 is landed in `1600fd7ed6c920c1bd9f3a6890ff10f6d7ee25b0`; `_execute_prologue`, `_execute_step_loop`, and `_execute_epilogue` are committed helpers on `WorkflowExecutor`. Task 9, the final executor-surface suite and orchestrator smoke gate, is the first unlanded task. Unrelated user work exists in the checkout and must be preserved.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink `orchestrator/workflow/executor.py` (currently 10,956 lines; `WorkflowExecutor` at :523 with 67 `__init__` self-attributes and 299 methods) by extracting five self-contained clusters into sibling modules — **without** splitting the `WorkflowExecutor` class. Every extraction keeps a 2-line delegating method (or a module-level re-export) on the executor so the 77 test files that import `WorkflowExecutor` and the suites that bind private methods keep passing. Dependency direction is strictly `executor → new modules`; no new module imports the executor back. After the back-reference surface of `loops.py`/`calls.py` shrinks, introduce an `ExecutorRuntime` Protocol to type the two whole-object back-references that regressed (`LoopExecutor(executor: Any)`, `CallExecutor(executor: Any)`). Finally, slice the 637-line `execute()` method into private prologue/loop/epilogue helpers in the same class.

**Architecture:** Extraction-behind-delegators, not a class split. A full split is **rejected**: 77 test files import `WorkflowExecutor`; suites bind private methods directly (`executor._runtime_step_for_node_id` x22 in `tests/test_runtime_step_lifecycle.py`, `WorkflowExecutor._execute_materialize_view` x11 in `tests/test_workflow_lisp_materialize_view_runtime.py`, `_summary_kind_for_step` x7, `_step_identity`/`_step_id` bindings in characterization, `WorkflowExecutor.__new__` x9). The repo already models the target collaborator pattern correctly — `ResumePlanner`, `FinalizationController`, `OutcomeRecorder`, `PromptComposer`, `DataflowManager` are real collaborators with explicit constructor deps. `LoopExecutor(self)` and `CallExecutor(self)` are the two that regressed to whole-object back-reference. This plan brings them and the largest interpreter/adjudication clusters back toward explicit dependencies. **No dispatch-registry abstraction:** the ~15-branch `ExecutableNodeKind` if-chain in `_run_top_level_step` (:4641) stays as-is.

**Tech Stack:** Python 3.13, pytest.

**Scope assumption (recorded):** This plan implements Roadmap item 4 ("executor.py decomposition") from `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md`. It touches only `orchestrator/workflow/` runtime execution modules. It does **not** touch the drain lowering, typecheck family, or `build.py` (those are separate follow-on plans).

## Entry gate

This plan's increment (1) — giving `WorkflowExecutor.resume_mode` an `__init__` default — is **Task 6 of the Phase-1 plan** (`docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md`). Before starting Task 2 below, confirm it landed:

```bash
grep -n "self.resume_mode = " orchestrator/workflow/executor.py
```
Expected: two hits — the `__init__` default (`self.resume_mode = False`) **and** the `execute()` assignment (`self.resume_mode = resume` at :2968). If only the `execute()` assignment appears, land Phase-1 Task 6 first (it is a one-line change with its own commit) and do not proceed.

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- The working tree contains the user's in-flight work. **Stage by explicit path only** (`git add <file> <file>`). Never `git add -A`, `git add -u`, or `git commit -a`.
- Commit messages: short imperative sentence, matching repo style (e.g. `Route selector and gap drafting to stronger models`). **No** conventional-commit prefixes, **no** mention of Claude/Claude Code, **no** Co-Authored-By trailers.
- No worktrees. Never use `--no-verify`.
- Narrowest pytest selectors first; treat fresh command output as the verification evidence. After changing any test module, run `pytest --collect-only <module>` on it.
- Keep the repo's structural rules: no module over 500 lines where avoidable, cyclomatic complexity ≤12 per function where practical. New modules must stay under 500 lines; if an extraction would exceed that, split it by the internal phase boundaries named in the task.
- **Delegators are the default.** Every method moved out of `WorkflowExecutor` leaves a 2-line delegating method behind, unless a step's grep proves zero test/caller bindings for that name AND all internal callers are switched to the new import in the same commit. Each task marks which delegators are *permanent* (test-bound) vs *droppable later*.
- Dependency direction is one-way: `executor.py` imports from the new modules; **no new module imports `executor.py`** (module scope). The only permitted back-reference is a typed Protocol parameter (Task 7) or a deferred function-local import that is being *removed* (Task 2).
- If a step's verification fails twice in a row, stop and report instead of forcing it green.

## Measured coupling (verified 2026-07-07, anchor to function names — line numbers may drift)

`loops.py` (`LoopExecutor(executor: Any)`, ctor at :25) touches **28 distinct** `self.executor.*` members:

```
16 _attach_outcome            2 _record_step_error
15 state_manager              2 executable_ir
 7 _step_id                   1 workflow_context_defaults
 5 current_step               1 variables
 3 _when_condition            1 _to_step_result
 3 variable_substitutor       1 _restore_overlay_loop_frame
 3 _structured_guard_condition 1 _resolve_structured_output_artifacts
 3 _json_safe_runtime_value   1 _repeat_until_output_contracts
 3 _execute_nested_loop_step  1 _repeat_until_condition
 3 _evaluate_condition_expression  1 _implicit_typed_transfer_for_result
 3 _enforce_consumes_contract 1 _finalize_consumes
 3 debug                      1 _executable_node_for_step
 2 _runtime_step_for_node_id  1 _emit_lexical_checkpoint_shadow_after_repeat_until_commit
 2 _runtime_context
 2 _resume_entry_is_terminal
```

`calls.py` (`CallExecutor(executor: Any)`, ctor at :35) touches **17 distinct** `self.executor.*` members:

```
9 _contract_violation_result   1 stream_output
6 current_step                 1 step_heartbeat_interval_sec
4 workspace                    1 retry_delay_ms
4 state_manager                1 resume_mode
3 _step_id                     1 _resolve_runtime_value
3 loaded_bundle                1 _private_exec_context_binding_value
3 _json_safe_runtime_value     1 max_retries
2 observability                1 _call_input_bindings
1 debug
```

Task 4 moves `_attach_outcome` / `_json_safe_runtime_value` / `_step_id` / `_contract_violation_result` / `_to_step_result` to a direct-import module. That drops `loops.py` from 28 → ~23 distinct back-referenced members (removes `_attach_outcome`, `_step_id`, `_json_safe_runtime_value`, `_to_step_result`) and `calls.py` from 17 → ~13 (removes `_contract_violation_result`, `_step_id`, `_json_safe_runtime_value`). Task 7's Protocol is sized against the *post-Task-4* residual, re-measured at that point.

---

## Task 2: Extract `_CallFrameStateManager` into `call_frame_state.py`

`_CallFrameStateManager` (class at :225, spanning :225-521, immediately before `class WorkflowExecutor` at :523) plus its four module-level helpers at :165-224 (`_path_safe_frame_scope_token`, `_display_workflow_path`, `_thaw_workflow_value`, `_managed_jobs_config_from_step`). It hand-mirrors ~20 `StateManager` methods for nested call frames. Its **only** consumer is `calls.py` (deferred import at :767, instantiation at :864). `_CallFrameStateManager.__init__` takes only `parent_manager: StateManager`, `workflow`, and frame identity strings — it never references `WorkflowExecutor`, so it moves cleanly to a leaf module.

**Files:**
- Create: `orchestrator/workflow/call_frame_state.py`
- Modify: `orchestrator/workflow/executor.py` (delete the class + 4 helpers; add a re-export line during transition)
- Modify: `orchestrator/workflow/calls.py` (retarget the deferred import)

**Interfaces (verified from :229-338):**

```python
# call_frame_state.py — module-level helpers (moved verbatim from executor.py:165-224)
def _path_safe_frame_scope_token(frame_id: str) -> str: ...
def _display_workflow_path(workspace: Path, workflow_path: Any) -> str: ...
def _thaw_workflow_value(value: Any) -> Any: ...
def _managed_jobs_config_from_step(step: Mapping[str, Any]) -> Optional[ManagedJobsConfig]: ...

class _CallFrameStateManager:
    def __init__(
        self,
        *,
        parent_manager: StateManager,
        workflow: Any,
        frame_id: str,
        call_step_name: str,
        call_step_id: str,
        import_alias: str,
        bound_inputs: Dict[str, Any],
        existing_frame: Optional[Dict[str, Any]] = None,
        observability: Optional[Dict[str, Any]] = None,
    ) -> None: ...
    # + the ~20 StateManager-mirroring methods (update_step, update_loop_step, fail_run,
    #   start_step, heartbeat_step, _snapshot, _persist, _write_state, ...) moved verbatim.
```

- [ ] **Step 1: Identify the exact class + helper span and its imports**

```bash
awk 'NR>=160 && NR<=225 && (/^def / || /^class / || /^logger = /) {print NR": "$0}' orchestrator/workflow/executor.py
awk 'NR>=225 && /^class / {print NR": "$0}' orchestrator/workflow/executor.py | head -2
```
Expected: helpers `_path_safe_frame_scope_token` / `_display_workflow_path` / `_thaw_workflow_value` / `_managed_jobs_config_from_step` in :165-224; `class _CallFrameStateManager` at :225; next `class` is `WorkflowExecutor` at :523. The block to move is **:165-521** (helpers + class), stopping immediately before `class WorkflowExecutor`.

- [ ] **Step 2: Determine the import set the moved code needs**

```bash
sed -n '165,521p' orchestrator/workflow/executor.py | grep -oE "\b(StateManager|RunState|ManagedJobsConfig|workflow_context|workflow_output_contracts|workflow_output_contracts|Path|Mapping|Optional|Dict|Any)\b" | sort -u
```
For each name, find its import origin in executor.py's header (`grep -n "import <name>\|<name>," orchestrator/workflow/executor.py | head`). The new module needs: `from pathlib import Path`; `from typing import Any, Dict, Mapping, Optional`; `from ..state import StateManager, RunState` (verify path — `grep -n "import StateManager\|from .*state import" orchestrator/workflow/executor.py`); the `ManagedJobsConfig`, `workflow_context`, `workflow_output_contracts` origins from their existing executor imports. Copy those exact import lines.

- [ ] **Step 3: Create `call_frame_state.py`**

Create the file with a module docstring cross-referencing the implementation-architecture contract, the copied imports, and the moved helpers + class (cut verbatim from executor.py:165-521):

```python
"""Nested call-frame state manager.

Mirrors a subset of ``orchestrator.state.StateManager`` for child workflow
call frames. Extracted from ``executor.py`` to keep the executor module under
the size budget. Sole consumer: ``orchestrator/workflow/calls.py``.

Contract: see the call-frame state section of the workflow-executor
implementation-architecture doc. Dependency direction: this module imports
from ``orchestrator.state`` only; it never imports ``executor.py``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

# ... copied import lines for StateManager, RunState, ManagedJobsConfig,
#     workflow_context, workflow_output_contracts ...

# ... the four helpers and class _CallFrameStateManager, moved verbatim ...
```

- [ ] **Step 4: Delete the moved block from executor.py and add a transitional re-export**

Delete executor.py:165-521 (the helpers + class). Immediately after executor.py's own imports, add a re-export so any existing `from .executor import _CallFrameStateManager` keeps resolving during the transition:

```python
from .call_frame_state import _CallFrameStateManager  # transitional re-export; dropped in Step 6
```

Also check whether the four module-level helpers are referenced elsewhere in executor.py:
```bash
grep -n "_path_safe_frame_scope_token\|_display_workflow_path\|_thaw_workflow_value\|_managed_jobs_config_from_step" orchestrator/workflow/executor.py
```
If any remain used inside `WorkflowExecutor`, add them to the same re-export import line. Decision rule: re-export exactly the helper names that Step-4 grep shows still referenced in executor.py.

- [ ] **Step 5: Grep tests for direct bindings of the moved names**

```bash
for n in _CallFrameStateManager _path_safe_frame_scope_token _display_workflow_path _thaw_workflow_value _managed_jobs_config_from_step; do
  echo "== $n =="; grep -rn "$n" tests/ | grep -v "\.pyc"
done
```
Decision rule: for any name a test imports **from executor** (`from ...executor import <n>`), keep it on the transitional re-export line permanently (mark it PERMANENT in the import comment) instead of dropping it in Step 6. `_CallFrameStateManager` is expected to have zero direct test imports (only `calls.py` uses it); if that holds, the re-export is fully droppable.

- [ ] **Step 6: Retarget `calls.py` and drop the droppable re-export**

In `calls.py`, change the deferred import at :767 from:
```python
from .executor import WorkflowExecutor, _CallFrameStateManager
```
to:
```python
from .executor import WorkflowExecutor
from .call_frame_state import _CallFrameStateManager
```
Then, if Step-5 showed zero external test imports of `_CallFrameStateManager`, remove that name from the executor.py transitional re-export (keep only helper names that Step 5 flagged PERMANENT, if any).

- [ ] **Step 7: Verify**

```bash
python -c "import orchestrator.workflow.executor, orchestrator.workflow.calls, orchestrator.workflow.call_frame_state"
pytest tests/test_workflow_lisp_call_frames.py tests/test_workflow_executor_characterization.py -q
grep -rn "from .executor import" orchestrator/workflow/calls.py
```
Expected: import smoke clean; suites PASS; `calls.py` no longer imports `_CallFrameStateManager` from `.executor`. If a call-frame suite name differs, discover it: `grep -rln "_CallFrameStateManager\|call_frame" tests/ | head`.

- [ ] **Step 8: Commit**

```bash
git add orchestrator/workflow/call_frame_state.py orchestrator/workflow/executor.py orchestrator/workflow/calls.py
git commit -m "Extract nested call frame state manager into its own module"
```

---

## Task 3: Extract the compiled-frontend origin cluster into `frontend_origins.py`

The compiled-frontend origin/display cluster (:704-918) is provenance-only: it reads a `provenance` object and caches derived origin/boundary maps. Its inputs are the source-trace payload and step/node ids; it does not touch `state_manager`, `workspace`, or execution state. The methods: `_load_compiled_frontend_source_trace_payload` (:704), `_load_compiled_frontend_step_origins` (:732), `_load_compiled_frontend_node_origins` (:754), `_load_compiled_frontend_command_boundaries` (:802), `_compiled_frontend_origin_for_step` (:824), `_compiled_frontend_command_boundary_for_step` (:847), `_emit_compiled_frontend_step_display` (:879). The `__init__` sets four attributes from these at :622-625.

**Files:**
- Create: `orchestrator/workflow/frontend_origins.py`
- Modify: `orchestrator/workflow/executor.py`

**Interfaces (designed from the cluster's actual inputs — the methods read `provenance`, `self._compiled_frontend_kind`, and the cached maps only):**

```python
# frontend_origins.py
class CompiledFrontendIndex:
    """Provenance-only index of compiled-frontend node/step origins and command
    boundaries, plus the step-display emitter. Self-contained: built from a
    provenance object once, then queried by node_id / step identity.

    Contract: workflow-executor implementation-architecture doc, compiled-
    frontend provenance section. Imports no execution state.
    """
    def __init__(self, provenance: Any) -> None:
        self.frontend_kind: Optional[str] = provenance.frontend_kind if provenance is not None else None
        self._payload_cache: Optional[dict] = None
        self._provenance = provenance
        self.node_origins = self._load_node_origins(provenance)
        self.step_origins = self._load_step_origins(provenance)
        self.command_boundaries = self._load_command_boundaries(provenance)

    def origin_for_step(self, step_name: str, step_id: str, *, node_id: Optional[str] = None) -> Optional[Any]: ...
    def command_boundary_for_step(self, step_name: str, step_id: str, *, node_id: Optional[str] = None) -> Optional[Any]: ...
    def emit_step_display(self, step_name: str, step_id: str, *, node_id: Optional[str], stream_output, debug) -> None: ...
    # private: _load_source_trace_payload, _load_step_origins, _load_node_origins, _load_command_boundaries
```

Note: `_emit_compiled_frontend_step_display` writes via `self.stream_output` / `self.debug` in the current code. Verify at authoring time (`sed -n '879,918p'`). If it only needs those two, pass them as `emit_step_display` params (as above). If it reaches further into the executor, keep `_emit_compiled_frontend_step_display` as a **delegator on the executor** and move only the pure origin/boundary lookups; record that decision in the commit.

- [ ] **Step 1: Confirm the cluster span and its executor dependencies**

```bash
grep -n "def _load_compiled_frontend\|def _compiled_frontend\|def _emit_compiled_frontend" orchestrator/workflow/executor.py
sed -n '704,918p' orchestrator/workflow/executor.py | grep -oE "self\.[a-zA-Z_][a-zA-Z0-9_]*" | sort | uniq -c | sort -rn
```
Decision rule: every `self.<member>` in the 704-918 range that is **not** one of the seven cluster methods or the four `_compiled_frontend_*` attributes is an external dependency. Expected external set is small (`stream_output`, `debug`, possibly `_compiled_frontend_source_trace_payload_cache`). Any dependency on `state_manager`/`workspace`/execution state → downgrade that method to a delegator and note it.

- [ ] **Step 2: Create `frontend_origins.py`**

Move the seven methods into `CompiledFrontendIndex`, renaming `self._compiled_frontend_*` cache attributes to unprefixed instance attributes and dropping the `_compiled_frontend_` prefix on method names per the interface above. Copy the imports the bodies need (find them: `sed -n '704,918p' orchestrator/workflow/executor.py | grep -oE "\b[A-Z][a-zA-Z]+\b" | sort -u`, then resolve each against executor's import header).

- [ ] **Step 3: Rewire executor to hold a `CompiledFrontendIndex`**

In `__init__`, replace the four assignments at :622-625:
```python
self._compiled_frontend_kind = provenance.frontend_kind if provenance is not None else None
self._compiled_frontend_node_origins = self._load_compiled_frontend_node_origins(provenance)
self._compiled_frontend_step_origins = self._load_compiled_frontend_step_origins(provenance)
self._compiled_frontend_command_boundaries = self._load_compiled_frontend_command_boundaries(provenance)
```
with:
```python
self._frontend_index = CompiledFrontendIndex(provenance)
```
Add `from .frontend_origins import CompiledFrontendIndex` to executor's imports. Keep **delegating methods** on the executor for any of the seven names that the grep in Step 4 shows a test binds:
```python
def _compiled_frontend_origin_for_step(self, step_name, step_id, *, node_id=None):
    return self._frontend_index.origin_for_step(step_name, step_id, node_id=node_id)
```
Update internal callers (`grep -n "_compiled_frontend_origin_for_step\|_emit_compiled_frontend_step_display\|self._compiled_frontend_node_origins\|self._compiled_frontend_step_origins\|self._compiled_frontend_command_boundaries\|self._compiled_frontend_kind" orchestrator/workflow/executor.py`) to route through `self._frontend_index` (or the delegator).

- [ ] **Step 4: Grep tests for direct bindings**

```bash
for n in _compiled_frontend_origin_for_step _compiled_frontend_command_boundary_for_step _emit_compiled_frontend_step_display _load_compiled_frontend_node_origins _load_compiled_frontend_step_origins _load_compiled_frontend_command_boundaries _compiled_frontend_kind _compiled_frontend_node_origins; do
  echo "== $n =="; grep -rn "$n" tests/ | grep -v "\.pyc"
done
```
Decision rule: any name a test binds on the executor gets a permanent delegator (methods) or a `@property` (attributes, e.g. `_compiled_frontend_kind` → `return self._frontend_index.frontend_kind`). Names with zero test hits need no delegator. Record which delegators are permanent.

- [ ] **Step 5: Verify**

```bash
python -c "import orchestrator.workflow.executor, orchestrator.workflow.frontend_origins"
pytest tests/test_workflow_executor_characterization.py tests/test_observability_summary_runtime.py -q
grep -rln "compiled_frontend\|frontend_origin\|frontend_index" tests/ | head
```
Expected: import clean; suites PASS. If Step-5 grep surfaces a dedicated compiled-frontend test module, add it to the selector and rerun.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow/frontend_origins.py orchestrator/workflow/executor.py
git commit -m "Extract compiled frontend origin index into its own module"
```

---

## Task 4: Extract near-pure step-result helpers into `step_results.py`; switch loops/calls to direct imports

Five near-pure functions on dicts: `_attach_outcome` (:10897), `_json_safe_runtime_value` (:1744), `_step_id` (:919), `_contract_violation_result` (:4030), `_to_step_result` (:5179, already a `@staticmethod`). These are the highest-frequency members `loops.py` and `calls.py` back-reference. Moving them to a direct-import module shrinks the back-reference surface (loops 28→~23, calls 17→~13) and is the prerequisite for the Task 7 Protocol.

**Files:**
- Create: `orchestrator/workflow/step_results.py`
- Modify: `orchestrator/workflow/executor.py` (delete bodies, keep delegators)
- Modify: `orchestrator/workflow/loops.py`, `orchestrator/workflow/calls.py` (switch to direct imports)

**Interfaces (verified signatures):**

```python
# step_results.py
def step_id(step: Dict[str, Any], fallback_index: Optional[int] = None) -> str: ...
def json_safe_runtime_value(value: Any) -> Any: ...
def contract_violation_result(message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...
def attach_outcome(step: Dict[str, Any], result: Dict[str, Any], ...) -> Dict[str, Any]:  # confirm full sig at :10897
    ...
def to_step_result(result: Dict[str, Any], fallback_name: str) -> StepResult: ...
```

Design note: these are currently *methods* (`self` in their signature). Check whether each actually uses `self`:
```bash
for ln in 919 1744 4030 5179 10897; do echo "== :$ln =="; sed -n "${ln},$((ln+30))p" orchestrator/workflow/executor.py | grep -c "self\."; done
```
Decision rule per function:
- **Zero `self.` uses** → move to a bare module function (drop `self`), executor keeps a delegator `def _step_id(self, step, fallback_index=None): return step_id(step, fallback_index)`.
- **Uses `self.` for other executor state** → it is not pure; leave it on the executor and drop it from this task's move list, reporting which one. (`_attach_outcome` and `_contract_violation_result` are the likely candidates to inspect closely — `_attach_outcome` may reference `self._summary_kind_for_step` or provenance.)

- [ ] **Step 1: Classify each of the five by `self.` usage**

Run the loop above. For any function that references `self.<other>`, either (a) pass that dependency as an explicit parameter if it is itself pure/small, or (b) keep the function on the executor and remove it from the move set. Record the classification table in the commit body. Proceed only with the confirmed-pure subset.

- [ ] **Step 2: Create `step_results.py`**

```python
"""Pure step-result helpers.

Near-pure functions on step/result dicts, extracted from ``executor.py`` so
that ``loops.py`` and ``calls.py`` can import them directly instead of
back-referencing the executor. Dependency direction: leaf module; imports no
sibling execution module.

Contract: workflow-executor implementation-architecture doc, step-result
section.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from .runtime_step import StepResult  # verify origin: grep -n "import StepResult" orchestrator/workflow/executor.py

# moved function bodies (self dropped), one per confirmed-pure name ...
```

- [ ] **Step 3: Replace executor bodies with delegators**

For each moved name, replace the method body with a one-line delegator to the new module function, e.g.:
```python
def _step_id(self, step: Dict[str, Any], fallback_index: Optional[int] = None) -> str:
    return step_results.step_id(step, fallback_index)
```
Add `from . import step_results` to executor imports. For the `@staticmethod` `_to_step_result`, keep it as a static delegator:
```python
@staticmethod
def _to_step_result(result: Dict[str, Any], fallback_name: str) -> StepResult:
    return step_results.to_step_result(result, fallback_name)
```

- [ ] **Step 4: Grep tests for direct bindings of every moved name**

```bash
for n in _attach_outcome _json_safe_runtime_value _step_id _contract_violation_result _to_step_result; do
  echo "== $n =="; grep -rnE "\.${n}\b|import ${n}\b" tests/ | grep -v "\.pyc"
done
```
Verified counts (2026-07-07): `_json_safe_runtime_value` 2, `_contract_violation_result` 1, `_step_id` 4 (method bindings; the raw substring count is inflated by `step_id`/`_step_identity`), `_attach_outcome` 0, `_to_step_result` 0. Decision rule: **all five delegators are PERMANENT** because test suites and internal callers bind them on the executor. Do not drop the delegators.

- [ ] **Step 5: Switch loops.py and calls.py to DIRECT imports**

In `loops.py`, add `from . import step_results` and replace:
- `self.executor._attach_outcome(` → `step_results.attach_outcome(` (only if Step-1 confirmed `_attach_outcome` pure; else leave the back-reference)
- `self.executor._step_id(` → `step_results.step_id(`
- `self.executor._json_safe_runtime_value(` → `step_results.json_safe_runtime_value(`
- `self.executor._to_step_result(` → `step_results.to_step_result(`

In `calls.py`, add `from . import step_results` and replace:
- `self.executor._contract_violation_result(` → `step_results.contract_violation_result(`
- `self.executor._step_id(` → `step_results.step_id(`
- `self.executor._json_safe_runtime_value(` → `step_results.json_safe_runtime_value(`

Re-measure the residual back-reference surface (feeds Task 7):
```bash
grep -oE "self\.executor\.[a-zA-Z_][a-zA-Z0-9_]*" orchestrator/workflow/loops.py | sed 's/self\.executor\.//' | sort -u | wc -l
grep -oE "self\.executor\.[a-zA-Z_][a-zA-Z0-9_]*" orchestrator/workflow/calls.py | sed 's/self\.executor\.//' | sort -u | wc -l
```
Expected: loops ~23, calls ~13 (fewer if `_attach_outcome` also moved). Record the exact residual member lists — they are the Task 7 Protocol surface.

- [ ] **Step 6: Verify**

```bash
python -c "import orchestrator.workflow.executor, orchestrator.workflow.loops, orchestrator.workflow.calls, orchestrator.workflow.step_results"
pytest tests/test_runtime_step_lifecycle.py tests/test_workflow_executor_characterization.py tests/test_workflow_lisp_call_frames.py -q
```
Expected: import clean; suites PASS.

- [ ] **Step 7: Commit**

```bash
git add orchestrator/workflow/step_results.py orchestrator/workflow/executor.py orchestrator/workflow/loops.py orchestrator/workflow/calls.py
git commit -m "Extract pure step result helpers and switch loop and call executors to direct imports"
```

---

## Task 5: Extract the step-kind interpreter families into `orchestrator/workflow/steps/`

The step-kind interpreter families span :9452-10806. Directory `orchestrator/workflow/steps/` does **not** yet exist (verified — no collision). These are config-driven interpreters (`step["pure_projection"]`, `step["materialize_view"]`, etc.). **Critical measured finding:** the four families collectively touch ~40 distinct executor members (`_contract_violation_result` x31, `_v214_failure_result` x15, `_workspace_relative_path` x11, `workspace` x9, plus ~35 sibling private helpers like `_resolve_materialize_view_value`, `_restore_file_bytes`, `_atomic_write_bytes`, `_executable_node_for_step`, `state_manager`, `workflow_artifacts`). This is a wide surface — the extraction uses a `StepRuntime` protocol capturing exactly those members, and the interpreter functions receive a `StepRuntime` handle. **One family per commit; materialize_view LAST; keep its delegator permanently** (11 test bindings of `_execute_materialize_view`).

Families (verified defs):
- `resource_transition`: `_execute_resource_transition` (:9459) + supporting `_resource_transition_artifacts` / `_normalize_resource_transition_paths` / `_resolve_resource_transition_bindings`
- `pure_projection`: `_execute_pure_projection` (:9564) + `_pure_projection_artifacts` / `_resolve_pure_projection_bindings` / `_reuse_pure_projection_bundle`
- `materialize_view`: `_execute_materialize_view` (:9686) + `_materialize_view_artifacts` / `_resolve_materialize_view_value` / `_reuse_materialized_view` / `_materialize_view_evidence_path`
- `scalars`: `_execute_scalar_step` (:10010) + `_invalid_scalar_value_result` / `_validate_scalar_value`
- structured if/match join helpers: `_execute_structured_if_branch` (:10602), `_execute_structured_if_join` (:10620), `_execute_structured_match_case` (:10702), `_execute_structured_match_join` (:10720) — extract only if they touch the same narrow slice; otherwise leave them (they are dispatch glue, not a family).

**Interfaces — `StepRuntime` protocol (designed from the measured member set):**

```python
# orchestrator/workflow/steps/runtime.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

class StepRuntime(Protocol):
    """The executor surface the step-kind interpreters need. Captures exactly
    the members measured across the interpreter bodies (:9452-10806).
    Implemented structurally by WorkflowExecutor; the interpreters never see
    the executor type. Contract: workflow-executor impl-arch doc, step-kind
    interpreter section."""
    workspace: Path
    workflow_artifacts: Any
    state_manager: Any

    # shared result/error constructors
    def _contract_violation_result(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...
    def _v214_failure_result(self, *args: Any, **kwargs: Any) -> Dict[str, Any]: ...  # confirm sig at :8145
    def _invalid_scalar_value_result(self, *args: Any, **kwargs: Any) -> Dict[str, Any]: ...

    # path / io helpers
    def _workspace_relative_path(self, path: Path) -> str: ...
    def _resolve_workspace_path(self, *args: Any) -> Path: ...
    def _atomic_write_text(self, target: Path, content: str) -> None: ...
    def _atomic_write_bytes(self, target: Path, content: bytes) -> None: ...
    def _capture_existing_file_bytes(self, *args: Any) -> Any: ...
    def _restore_file_bytes(self, *args: Any) -> None: ...
    def _bounded_private_runtime_bundle_path(self, *args: Any) -> Path: ...
    def _prepare_runtime_output_bundle_parent(self, *args: Any) -> None: ...

    # value resolution
    def _resolve_runtime_value(self, *args: Any) -> Any: ...
    def _resolve_ref_value(self, *args: Any) -> Any: ...
    def _json_safe_runtime_value(self, value: Any) -> Any: ...
    def _resolve_output_contract_paths(self, *args: Any) -> Any: ...
    def _resolve_structured_output_artifacts(self, *args: Any) -> Any: ...
    def _executable_node_for_step(self, step: Dict[str, Any]) -> Any: ...

    # family-specific resolvers (kept on the executor, exposed via the protocol)
    def _resolve_resource_transition_bindings(self, *args: Any) -> Any: ...
    def _normalize_resource_transition_paths(self, *args: Any) -> Any: ...
    def _resource_transition_artifacts(self, *args: Any) -> Any: ...
    def _resolve_pure_projection_bindings(self, *args: Any) -> Any: ...
    def _pure_projection_artifacts(self, *args: Any) -> Any: ...
    def _reuse_pure_projection_bundle(self, *args: Any) -> Any: ...
    def _is_inactive_pure_projection_union_output(self, *args: Any) -> bool: ...
    def _resolve_materialize_view_value(self, *args: Any) -> Any: ...
    def _resolve_materialize_view_target_value(self, *args: Any) -> Any: ...
    def _materialize_view_artifacts(self, *args: Any) -> Any: ...
    def _materialize_view_evidence_path(self, *args: Any) -> Path: ...
    def _reuse_materialized_view(self, *args: Any) -> Any: ...
    def _resolve_transition_json_pointer(self, *args: Any) -> Any: ...
    def _latest_published_scalar_value(self, *args: Any) -> Any: ...
    def _validate_scalar_value(self, *args: Any) -> Any: ...
    def _execute_scalar_step(self, step: Dict[str, Any]) -> Dict[str, Any]: ...  # materialize_view calls scalar
```

Design decision recorded: the interpreter *bodies* move to `steps/<family>.py` as free functions `execute_<family>(runtime: StepRuntime, step: Dict[str, Any]) -> Dict[str, Any]`. The dozens of family-specific *helpers* they call (`_resolve_materialize_view_value`, etc.) **stay on the executor** and are reached through the `StepRuntime` protocol. This keeps the move mechanical (one top-level interpreter body per file) and avoids a cascading move of 35 helpers. If a helper is used by exactly one family and is itself pure, it may move with that family — decide per helper in Step 2, defaulting to "leave on executor."

**Files:**
- Create: `orchestrator/workflow/steps/__init__.py`, `orchestrator/workflow/steps/runtime.py`
- Create (one per commit): `orchestrator/workflow/steps/resource_transition.py`, `pure_projection.py`, `materialize_view.py`, `scalars.py`
- Modify: `orchestrator/workflow/executor.py` (delegators)

### Task 5a: Scaffold `steps/` package and the `StepRuntime` protocol

- [ ] **Step 1: Confirm the directory does not exist and create the package**

```bash
test -d orchestrator/workflow/steps && echo EXISTS || echo ABSENT
```
Expected: `ABSENT`. Create `orchestrator/workflow/steps/__init__.py` (empty docstring) and `orchestrator/workflow/steps/runtime.py` with the `StepRuntime` protocol above. Confirm the exact signatures of `_v214_failure_result` (:8145), `_invalid_scalar_value_result` (:10445), `_resolve_output_contract_paths` (:8003) and tighten the `*args` placeholders where the real signature is short.

- [ ] **Step 2: Verify import**

```bash
python -c "from orchestrator.workflow.steps.runtime import StepRuntime; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/workflow/steps/__init__.py orchestrator/workflow/steps/runtime.py
git commit -m "Add step runtime protocol and steps package scaffold"
```

### Task 5b: Extract `resource_transition` (one commit)

- [ ] **Step 1: Measure this family's exact member set**

```bash
sed -n '9459,9563p' orchestrator/workflow/executor.py | grep -oE "self\.[a-zA-Z_][a-zA-Z0-9_]*" | sort -u
```
Confirm every member appears in the `StepRuntime` protocol; if one is missing, add it to `runtime.py` in this commit.

- [ ] **Step 2: Create `steps/resource_transition.py`**

Move the `_execute_resource_transition` body into `def execute_resource_transition(runtime: StepRuntime, step: Dict[str, Any]) -> Dict[str, Any]:`, replacing each `self.` with `runtime.`. Leave the family helpers (`_resource_transition_artifacts`, `_normalize_resource_transition_paths`, `_resolve_resource_transition_bindings`) on the executor (they are reached via `runtime.`).

- [ ] **Step 3: Replace executor method with a delegator**

```python
def _execute_resource_transition(self, step: Dict[str, Any]) -> Dict[str, Any]:
    from .steps.resource_transition import execute_resource_transition
    return execute_resource_transition(self, step)
```
(Function-local import avoids any package-load ordering issue; `steps/` imports only `steps.runtime`, never `executor`.)

- [ ] **Step 4: Grep tests for direct bindings**

```bash
grep -rnE "\._execute_resource_transition\b|import .*execute_resource_transition" tests/ | grep -v "\.pyc"
```
Verified: 0 test bindings. Decision rule: delegator is DROPPABLE later, but keep it this commit (the if-chain in `_run_top_level_step` calls it). Note: droppable.

- [ ] **Step 5: Verify**

```bash
python -c "import orchestrator.workflow.executor, orchestrator.workflow.steps.resource_transition"
pytest tests/test_workflow_executor_characterization.py -q -k "resource or transition" || pytest tests/test_workflow_executor_characterization.py -q
```
Expected: PASS. If a dedicated resource-transition suite exists (`grep -rln "resource_transition" tests/`), run it too.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow/steps/resource_transition.py orchestrator/workflow/steps/runtime.py orchestrator/workflow/executor.py
git commit -m "Extract resource transition step interpreter"
```

### Task 5c: Extract `pure_projection` (one commit)

Same procedure as 5b for `_execute_pure_projection` (:9564).

- [ ] **Step 1:** `sed -n '9564,9685p' orchestrator/workflow/executor.py | grep -oE "self\.[a-zA-Z_][a-zA-Z0-9_]*" | sort -u` — reconcile with `StepRuntime`.
- [ ] **Step 2:** Create `steps/pure_projection.py` with `execute_pure_projection(runtime, step)`.
- [ ] **Step 3:** Delegator on executor (function-local import pattern).
- [ ] **Step 4:** `grep -rnE "\._execute_pure_projection\b" tests/ | grep -v "\.pyc"` — verified 0; delegator DROPPABLE but kept.
- [ ] **Step 5:** `pytest tests/test_workflow_lisp_pure_projection_runtime.py -q` — expected PASS.
- [ ] **Step 6:** `git add orchestrator/workflow/steps/pure_projection.py orchestrator/workflow/steps/runtime.py orchestrator/workflow/executor.py && git commit -m "Extract pure projection step interpreter"`

### Task 5d: Extract `scalars` (one commit)

Same procedure for `_execute_scalar_step` (:10010) plus `_invalid_scalar_value_result` / `_validate_scalar_value` (decide per Step-2 whether these helpers move with the family or stay — default stay).

- [ ] **Step 1:** `sed -n '10010,10460p' orchestrator/workflow/executor.py | grep -oE "self\.[a-zA-Z_][a-zA-Z0-9_]*" | sort -u` — reconcile with `StepRuntime`. Note `materialize_view` calls `_execute_scalar_step`, so the scalar interpreter must be extractable before materialize_view but its executor delegator must remain callable from `runtime._execute_scalar_step`.
- [ ] **Step 2:** Create `steps/scalars.py` with `execute_scalar_step(runtime, step)`.
- [ ] **Step 3:** Delegator on executor; ensure `StepRuntime._execute_scalar_step` still resolves (the delegator satisfies the protocol).
- [ ] **Step 4:** `grep -rnE "\._execute_scalar_step\b" tests/ | grep -v "\.pyc"` — verified 0; delegator kept because materialize_view and the if-chain call it (PERMANENT-until-materialize_view-lands, then still kept as it is a protocol member).
- [ ] **Step 5:** `pytest tests/test_workflow_executor_characterization.py tests/test_observability_summary_runtime.py -q` — expected PASS.
- [ ] **Step 6:** `git add orchestrator/workflow/steps/scalars.py orchestrator/workflow/steps/runtime.py orchestrator/workflow/executor.py && git commit -m "Extract scalar step interpreter"`

### Task 5e: Extract `materialize_view` LAST (one commit) — permanent delegator

- [ ] **Step 1:** `sed -n '9686,10009p' orchestrator/workflow/executor.py | grep -oE "self\.[a-zA-Z_][a-zA-Z0-9_]*" | sort -u` — reconcile with `StepRuntime`. This family calls `self._execute_scalar_step` and `self._resolve_materialize_view_value`; both are protocol members reached via `runtime.`.
- [ ] **Step 2:** Create `steps/materialize_view.py` with `execute_materialize_view(runtime, step)`.
- [ ] **Step 3:** Delegator on executor:
```python
def _execute_materialize_view(self, step: Dict[str, Any]) -> Dict[str, Any]:
    from .steps.materialize_view import execute_materialize_view
    return execute_materialize_view(self, step)
```
- [ ] **Step 4:** `grep -rnE "\._execute_materialize_view\b|WorkflowExecutor\._execute_materialize_view" tests/ | grep -v "\.pyc"` — verified **11** bindings in `tests/test_workflow_lisp_materialize_view_runtime.py`. Decision rule: **delegator is PERMANENT** — do not drop.
- [ ] **Step 5:** `pytest tests/test_workflow_lisp_materialize_view_runtime.py -q` — expected PASS (this is the highest-risk suite; run `pytest --collect-only tests/test_workflow_lisp_materialize_view_runtime.py` first to confirm the 11 bindings still resolve).
- [ ] **Step 6:** `git add orchestrator/workflow/steps/materialize_view.py orchestrator/workflow/steps/runtime.py orchestrator/workflow/executor.py && git commit -m "Extract materialize view step interpreter behind a permanent delegator"`

---

## Task 6: Extract the adjudication cluster into `adjudication_runner.py`

The adjudication cluster spans :6034-7925 (~25 methods). **Name-collision check:** `orchestrator/workflow/adjudication/` is an existing *package* (value/paths/scoring/ledger modules; imported at executor.py:125). The new module is `orchestrator/workflow/adjudication_runner.py` — a sibling file, **no collision** with the `adjudication/` package. (The brief said `adjudication.py`; the tree actually has a package. Confirmed no `adjudication_runner.py` exists.)

The cluster's external (non-adjudication) executor surface, measured over :6034-7925: `_resume_mismatch` x26, `workspace` x20, `_stable_runtime_hash` x7, `_text_hash` x4, `provider_executor` x4, `_path_under` x4, `_create_provider_context` x4, `_contract_violation_result` x4, plus ~22 singletons (`prompt_composer`, `provider_registry`, `_execute_provider_invocation`, `state_manager`, `_compose_provider_prompt_for_step`, `_resolve_output_contract_paths`, `current_step`, `max_retries`, `retry_delay_ms`, `global_secrets`, `workflow_version`, ...). This is a broad surface driven mostly by provider-invocation plumbing.

Design decision recorded: because the surface is wide **and** several members are mutable executor state (`current_step`, `_resume_mismatch` accumulator), the runner is constructed with explicit collaborators for the stable deps (`workspace`, `state_manager`, retry policy, provider plumbing) **and one callback** for `_execute_provider_invocation` (:7943) — matching the brief. The keep-`_execute_adjudicated_provider_with_context`-as-delegator rule holds: the 622-line orchestration method (:6059-6681) becomes a delegator; inside the runner it is split by its existing phase boundaries to satisfy the ≤12 complexity gate.

**Interfaces (designed from the measured deps and the confirmed phase boundaries at :6076/6162/6449/6485/6521):**

```python
# adjudication_runner.py
class AdjudicationRunner:
    """Runs adjudicated-provider steps: resume-state reconciliation, candidate
    scoring, ledger writes, failure-path construction. Extracted from
    executor.py; reaches provider invocation through an injected callback and
    the executor's stable collaborators. Never imports executor.py.

    Contract: workflow-executor impl-arch doc, adjudication runner section."""
    def __init__(
        self,
        *,
        workspace: Path,
        state_manager: Any,
        provider_executor: Any,
        provider_registry: Any,
        prompt_composer: Any,
        retry_policy_for_step: Callable[[Mapping[str, Any]], RetryPolicy],
        invoke_provider: Callable[..., Any],   # bound to executor._execute_provider_invocation
        create_provider_context: Callable[..., Any],
        # + the remaining measured callables/attrs threaded as needed:
        #   contract_violation_result, resolve_output_contract_paths, stable_runtime_hash,
        #   text_hash, path_under, resume_mismatch accessor, step_id, ...
    ) -> None: ...

    def execute_adjudicated_provider_with_context(self, step, context) -> Dict[str, Any]:
        """Top-level orchestration; internally delegates to the phase methods."""
        ...
    # phase methods carved from :6059-6681 to meet the complexity gate:
    def _load_or_reconcile_resume_state(self, ...): ...   # config check + ledger path + resume load (:6076-6162)
    def _run_and_score_candidates(self, ...): ...         # candidate execution + scoring (:6162-6480)
    def _finalize_selection_and_ledgers(self, ...): ...   # selection, collision check, ledger writes (:6485-6553)
    # + the ~22 other adjudication methods moved verbatim (_score_adjudicated_candidate,
    #   _write_adjudication_ledgers, _load_adjudication_resume_state, _adjudication_failure_result, ...)
```

Note on scope realism: this is the largest and riskiest extraction (~1,900 lines, wide mutable surface). If threading the full callable set through `__init__` proves to exceed a clean ≤10-argument constructor, the fallback (recorded) is to pass a single typed `AdjudicationHost` protocol object (same shape as `ExecutorRuntime` from Task 7 but scoped to the adjudication surface) rather than a whole-executor reference. **Do not** pass `self` (the whole executor) — that would re-create the back-reference this plan is removing. Decide in Step 2 based on the measured argument count; prefer the protocol if the constructor would take >8 params.

**Files:**
- Create: `orchestrator/workflow/adjudication_runner.py`
- Modify: `orchestrator/workflow/executor.py`

- [ ] **Step 1: Confirm collision-freedom and the full method list**

```bash
test -e orchestrator/workflow/adjudication_runner.py && echo EXISTS || echo ABSENT
ls orchestrator/workflow/adjudication/
grep -n "def _adjudication\|def _score_adjudicated\|def _write_adjudication\|def _load_adjudication\|def _resolve_adjudication\|def _persist_adjudication\|def _candidate_step\|def _execute_adjudicated\|def _wait_for_adjudication\|def _resolve_provider_params_for_adjudication\|def _resolve_provider_params_for_adjudication" orchestrator/workflow/executor.py
```
Expected: `ABSENT`; the `adjudication/` package lists baseline/evidence/ledger/models/paths/promotion/resume/scoring/utils. The grep enumerates the ~25 cluster methods (:6034-7925). Build the exact move list from this output.

- [ ] **Step 2: Measure the external dependency surface and pick the constructor shape**

```bash
sed -n '6034,7925p' orchestrator/workflow/executor.py | grep -oE "self\.[a-zA-Z_][a-zA-Z0-9_]*" | sed 's/self\.//' | sort | uniq -c | sort -rn | grep -vE "adjudicat|_score_adjudicated|_candidate_step|_persist_adjudication|_write_adjudication|_load_adjudication|_resolve_adjudication|_resolve_provider_params_for_adjudication"
```
Count the distinct external members. Decision rule: if ≤8 → explicit constructor params; if >8 → define a scoped `AdjudicationHost(Protocol)` in `adjudication_runner.py` capturing exactly these members and take a single `host: AdjudicationHost` param plus the `invoke_provider` callback. Record which shape you chose and why.

- [ ] **Step 3: Confirm the internal phase boundaries of `_execute_adjudicated_provider_with_context`**

```bash
sed -n '6059,6681p' orchestrator/workflow/executor.py | grep -nE "_load_adjudication_resume_state|_score_adjudicated_candidate|_write_adjudication_ledgers|_adjudication_ledger_path_collision_message|resume_state =|candidate_configs_to_run|ledger_path =" | head
```
Expected boundaries: config/ledger-path check → `_load_adjudication_resume_state` (resume load) → candidate run + `_score_adjudicated_candidate` → selection + `_adjudication_ledger_path_collision_message` → `_write_adjudication_ledgers`. Carve `_load_or_reconcile_resume_state` / `_run_and_score_candidates` / `_finalize_selection_and_ledgers` along these seams so each stays ≤12 cyclomatic.

- [ ] **Step 4: Create `adjudication_runner.py` and move the cluster**

Move all ~25 methods into `AdjudicationRunner` (drop the `_adjudication_` name prefix on internal method names where it reads cleaner, keeping public `execute_adjudicated_provider_with_context`). Copy the imports the bodies need (`RetryPolicy`, `PathSurface`, `AdjudicationDeadline`, the `adjudication` package symbols, etc. — resolve each against executor's header). Split `execute_adjudicated_provider_with_context` into the three phase methods per Step 3.

- [ ] **Step 5: Wire the runner into the executor**

In `__init__`, construct `self._adjudication_runner = AdjudicationRunner(...)` with the chosen deps (callback bound as `invoke_provider=self._execute_provider_invocation`). Replace each moved method on the executor with a delegator only where a test or the if-chain binds it. Grep first:

```bash
for n in _execute_adjudicated_provider_with_context _score_adjudicated_candidate _write_adjudication_ledgers _load_adjudication_resume_state _adjudication_failure_result _adjudication_retry_policy; do
  echo "== $n =="; grep -rnE "\.${n}\b" tests/ | grep -v "\.pyc"
done
```
Decision rule: keep a delegator for every name that appears in tests OR is called from outside the cluster inside executor.py (`grep -n "self\._execute_adjudicated_provider_with_context\|self\._score_adjudicated" orchestrator/workflow/executor.py`). `_execute_adjudicated_provider_with_context` keeps its delegator per the brief. Record permanent vs droppable.

- [ ] **Step 6: Verify**

```bash
python -c "import orchestrator.workflow.executor, orchestrator.workflow.adjudication_runner"
grep -rln "adjudicat" tests/ | head
pytest $(grep -rln "adjudicat" tests/ | tr '\n' ' ') -q
```
Expected: import clean; all adjudication suites PASS. Complexity check on the carved method (optional but recommended): run any repo complexity linter, or verify by inspection that each phase method is ≤12 branches.

- [ ] **Step 7: Commit**

```bash
git add orchestrator/workflow/adjudication_runner.py orchestrator/workflow/executor.py
git commit -m "Extract adjudication runner into its own module"
```

---

## Task 7: Type `LoopExecutor` and `CallExecutor` with an `ExecutorRuntime` protocol

**Do this only after Task 4 shrinks the back-reference surface.** Re-measure the residual `self.executor.*` member sets used by `loops.py` and `calls.py` post-Task-4, then define a single `ExecutorRuntime(Protocol)` capturing their union, and type the two constructors with it (replacing `executor: Any`). This documents the real coupling and lets a type checker catch drift; it does not change runtime behavior.

**Files:**
- Create: `orchestrator/workflow/executor_runtime.py`
- Modify: `orchestrator/workflow/loops.py`, `orchestrator/workflow/calls.py`

- [ ] **Step 1: Re-measure the residual surface (post-Task-4)**

```bash
echo "== loops residual =="; grep -oE "self\.executor\.[a-zA-Z_][a-zA-Z0-9_]*" orchestrator/workflow/loops.py | sed 's/self\.executor\.//' | sort -u
echo "== calls residual =="; grep -oE "self\.executor\.[a-zA-Z_][a-zA-Z0-9_]*" orchestrator/workflow/calls.py | sed 's/self\.executor\.//' | sort -u
```
Expected ~23 (loops) + ~13 (calls), union ~30 distinct. Gate check: if the union exceeds ~30 members, note that a single protocol is wide; still proceed (it documents reality) but consider two narrower protocols (`LoopHost`, `CallHost`) if the overlap is small. Decision rule: one shared `ExecutorRuntime` if overlap ≥ 1/3 of each set; otherwise two protocols.

- [ ] **Step 2: Create `executor_runtime.py`**

```python
"""Structural protocol for the executor surface used by LoopExecutor and
CallExecutor. Sized against the measured residual back-reference set after the
step-result extraction. WorkflowExecutor satisfies it structurally; loops.py /
calls.py depend on this protocol, not on the executor class.

Contract: workflow-executor impl-arch doc, executor-runtime protocol section.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, Protocol

class ExecutorRuntime(Protocol):
    # attributes (from the measured set) ...
    state_manager: Any
    current_step: Any
    executable_ir: Any
    debug: bool
    workspace: Any
    loaded_bundle: Any
    observability: Any
    resume_mode: bool
    # ... one member per name the Step-1 grep printed, with the real type where cheap ...
    # methods ...
    def _runtime_step_for_node_id(self, node_id: str) -> Any: ...
    def _attach_outcome(self, *args: Any, **kwargs: Any) -> Dict[str, Any]: ...
    # ... etc for every residual method ...
```
Populate it exactly from Step-1 output (do not guess members not in the grep).

- [ ] **Step 3: Type the two constructors**

In `loops.py` and `calls.py`, add `from .executor_runtime import ExecutorRuntime` (under `TYPE_CHECKING` if needed to avoid any import cycle — but there is none, since `executor_runtime.py` is a leaf) and change:
```python
def __init__(self, executor: Any) -> None:
```
to:
```python
def __init__(self, executor: ExecutorRuntime) -> None:
```

- [ ] **Step 4: Verify**

```bash
python -c "import orchestrator.workflow.loops, orchestrator.workflow.calls, orchestrator.workflow.executor_runtime, orchestrator.workflow.executor"
pytest tests/test_runtime_step_lifecycle.py tests/test_workflow_lisp_call_frames.py tests/test_workflow_executor_characterization.py -q
```
Expected: import clean; suites PASS. (Runtime behavior is unchanged; this is a typing-only edit.) Optionally run the repo type checker over the three files if one is configured.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow/executor_runtime.py orchestrator/workflow/loops.py orchestrator/workflow/calls.py
git commit -m "Type loop and call executors with an executor runtime protocol"
```

---

## Task 8: Slice `execute()` into prologue / loop / epilogue helpers

`execute()` spans :2945-3581 (~637 lines; next method `_resolve_step_type` at :3582). Slice it into private methods **on the same class** — no new module, no behavior change. Verified internal structure:
- **Prologue (~:2968-3120):** `self.resume_mode = resume`; state setup; entry managed-write-root + runtime-context bindings; resume-planning (`resume_planner.detect_interrupted_provider_session_visit`, `_determine_resume_restart_node_id`); compiled-frontend display emit at :3108.
- **Loop (~:3120-3540):** the step-execution driver.
- **Epilogue (~:3540-3580):** finalization, `resolve_workflow_outputs`, `workflow_outputs_status` transitions, `_persist_workflow_boundary_state`, `update_status`, `_emit_typed_terminal_summary`, terminal return.

**Files:**
- Modify: `orchestrator/workflow/executor.py`

**Interfaces (private helpers on `WorkflowExecutor`):**

```python
def _execute_prologue(self, state: Dict[str, Any], *, resume: bool) -> Optional[Dict[str, Any]]:
    """Resume planning + entry-binding setup. Returns an early-exit result dict
    (e.g. a resume-integrity failure) or None to proceed."""
def _execute_epilogue(self, state: Dict[str, Any], terminal_status: str) -> Dict[str, Any]:
    """Finalization, workflow-output resolution, terminal-summary emit, return."""
```
The loop body may stay inline in `execute()` or become `_execute_step_loop`; decide by whether extracting it leaves `execute()` readable and each helper ≤12 cyclomatic. Prefer the smallest set of extractions that gets `execute()` under ~150 lines.

- [ ] **Step 1: Confirm the exact seams**

```bash
sed -n '2945,3582p' orchestrator/workflow/executor.py | grep -nE "self.resume_mode = resume|resume_planner|_determine_resume_restart_node_id|_emit_compiled_frontend_step_display|_ensure_finalization_state|resolve_workflow_outputs|_persist_workflow_boundary_state|update_status|_emit_typed_terminal_summary|return persisted_state|return state"
```
Map each printed line to prologue / loop / epilogue. The prologue ends where the step-execution loop begins; the epilogue begins at `_ensure_finalization_state(state)` near :3542.

- [ ] **Step 2: Extract `_execute_epilogue` first (lowest risk)**

Cut :3542-3580 into `_execute_epilogue(self, state, terminal_status)` returning the terminal dict; call it from `execute()`. This block is self-contained (reads `state`, `terminal_status`, `self.executable_ir`, `self.workspace`, finalization helpers). Preserve the exact return semantics: `completed` returns `persisted_state`; otherwise returns `state` with `status` set.

- [ ] **Step 3: Extract `_execute_prologue`**

Cut :2968-<loop-start> into `_execute_prologue(self, state, *, resume)`. It must return an `Optional[Dict]`: when a resume-integrity/guard path currently `return`s early from `execute()`, `_execute_prologue` returns that dict and `execute()` does `if (early := self._execute_prologue(state, resume=resume)) is not None: return early`. Keep `self.resume_mode = resume` as the first line inside the prologue.

- [ ] **Step 4: Verify no behavior drift**

```bash
python -c "import orchestrator.workflow.executor"
pytest tests/test_workflow_executor_characterization.py tests/test_runtime_step_lifecycle.py tests/test_observability_summary_runtime.py -q
```
Expected: PASS. The characterization suite drives real `execute()` runs and reads `state.json`, so it is the drift detector. If any characterization assertion changes, a seam was cut mid-transaction — revert that seam and split at a cleaner boundary.

- [ ] **Step 5: Confirm the size/complexity win**

```bash
awk 'NR>=2945 && /^    def / {print NR": "$0; if (++n==2) exit}' orchestrator/workflow/executor.py
wc -l orchestrator/workflow/executor.py
```
Expected: `execute()` now materially shorter; total file line count reduced across Tasks 2-8 by roughly the moved-cluster sizes (call_frame ~360, frontend ~220, step_results ~120, interpreters ~1,200, adjudication ~1,900 — minus the delegators left behind).

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow/executor.py
git commit -m "Slice executor run method into prologue and epilogue helpers"
```

---

## Final gate: full-suite verification

### Task 9: Full executor-surface suite + orchestrator smoke

- [ ] **Step 1: Full targeted suite (use the tmux skill if long)**

```bash
pytest tests/test_workflow_executor_characterization.py tests/test_runtime_step_lifecycle.py \
       tests/test_workflow_lisp_materialize_view_runtime.py tests/test_workflow_lisp_pure_projection_runtime.py \
       tests/test_observability_summary_runtime.py tests/test_workflow_lisp_call_frames.py -q
```
Expected: all PASS (this is the brief's stated blast radius; near-zero risk if delegators were kept).

- [ ] **Step 2: Full suite**

Run in tmux: `pytest -q`
Expected: same failures-before == failures-after (capture a baseline `pytest -q` on the pre-Task-2 tree if it carried in-flight failures, and compare).

- [ ] **Step 3: Orchestrator smoke**

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"
```
Expected: PASS.

- [ ] **Step 4: Report**

Summarize: lines removed from `executor.py` per task; new module sizes (each must be <500 lines — split further if not); the final residual `self.executor.*` member counts for loops/calls; which delegators are permanent vs droppable; any StepRuntime/ExecutorRuntime protocol members that had to be added beyond the measured sets. Do not push; leave commits local for review.

---

## Sequencing summary (one commit each)

1. resume_mode `__init__` default — **entry gate, already Phase-1 Task 6** (confirm landed, do not redo).
2. `call_frame_state.py` — extract `_CallFrameStateManager`; retarget `calls.py`; drop re-export.
3. `frontend_origins.py` — extract `CompiledFrontendIndex`.
4. `step_results.py` — extract five pure helpers; switch `loops.py`/`calls.py` to direct imports (shrinks the back-reference surface — prerequisite for Task 7).
5. `steps/` interpreter families — one commit each (5a scaffold, 5b resource_transition, 5c pure_projection, 5d scalars, 5e materialize_view LAST with permanent delegator).
6. `adjudication_runner.py` — extract the adjudication cluster; keep `_execute_adjudicated_provider_with_context` as delegator, split internally by phase.
7. `executor_runtime.py` — `ExecutorRuntime` Protocol typing `LoopExecutor`/`CallExecutor` (only after Task 4).
8. `execute()` slicing — prologue/epilogue private helpers, same class.
