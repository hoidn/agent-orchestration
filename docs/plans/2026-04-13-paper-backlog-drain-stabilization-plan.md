# Paper Backlog Drain Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the paper backlog drain workflow so it is a small deterministic loop around the generic backlog item stack, with explicit provider output contracts and no reads from child-workflow private state.

**Architecture:** Keep the selector as the only judgment-heavy provider step; keep loop mechanics, ledger updates, routing, and item-stack handoff in workflow YAML. The selector emits a strict JSON `output_bundle` whose concrete path is injected into the prompt by the orchestrator. The paper adapter routes on `READY|NONE_READY`, calls the generic item stack for `READY`, exports the child `item_outcome` through the `match` statement, and records the ledger from statement outputs rather than reading `item_outcome.txt` directly.

**Tech Stack:** Python, pytest, workflow DSL `2.7`, `output_bundle`, structured `repeat_until`, structured `match`, reusable `call`, Codex provider via stdin, downstream `/home/ollie/Documents/ptychopinnpaper2` workflow copy.

---

## Constraints And Context

- Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.
- The repo has existing uncommitted changes related to `output_bundle` prompt contract injection. Preserve unrelated dirty files and review the diff before editing.
- `specs/` are normative; `docs/workflow_drafting_guide.md` is guidance. If they conflict, update docs to match specs and tests.
- The paper workflow runs from `/home/ollie/Documents/ptychopinnpaper2` with `PYTHONPATH=/home/ollie/Documents/agent-orchestration`.
- When launching paper workflows manually, activate `ptycho311` via shell activation, not `conda run`, so tmux streaming output remains visible:

```bash
source /home/ollie/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
export PYTHONPATH=/home/ollie/Documents/agent-orchestration${PYTHONPATH:+:$PYTHONPATH}
```

## File Structure

- Modify `orchestrator/contracts/prompt_contract.py`: render the JSON `output_bundle` prompt contract with concrete path, JSON object format, field names, JSON pointers, types, enum values, relpath constraints, and optional required flags.
- Modify `orchestrator/workflow/prompting.py`: append the output contract suffix for provider steps with either `expected_outputs` or `output_bundle`.
- Modify `tests/test_prompt_contract_injection.py`: cover provider `output_bundle` prompt contract injection and resolved `${inputs.*}` / `${run.id}` paths.
- Modify `docs/workflow_drafting_guide.md`: state that provider steps with `output_bundle` also get an injected output contract and that prompts should not duplicate those paths.
- Modify `specs/dsl.md`, `specs/providers.md`, and `specs/acceptance/index.md`: keep normative prompt-contract wording aligned with implementation.
- Modify `tests/test_structured_control_flow.py`: add a focused regression for `repeat_until + output_bundle + match + call + statement output + ledger record` so the paper drain shape is covered without launching Codex.
- Modify `/home/ollie/Documents/ptychopinnpaper2/workflows/paper_backlog_next_design_plan_impl_stack.yaml`: move ledger recording out of the `READY` case, expose selected item outcome through `RouteSelectedBacklogItem`, and record from the match statement output.
- Modify `/home/ollie/Documents/ptychopinnpaper2/workflows/prompts/paper_backlog/select_next_backlog_item.md`: remove duplicated output-field/path prose and rely on the injected output bundle contract.

## Task 1: Finish Output-Bundle Prompt Contract Support

**Files:**
- Modify: `orchestrator/contracts/prompt_contract.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `specs/dsl.md`
- Modify: `specs/providers.md`
- Modify: `specs/acceptance/index.md`

- [ ] **Step 1: Inspect the current partial diff**

Run:

```bash
git diff -- orchestrator/contracts/prompt_contract.py orchestrator/workflow/prompting.py tests/test_prompt_contract_injection.py docs/workflow_drafting_guide.md specs/dsl.md specs/providers.md specs/acceptance/index.md
```

Expected: either no output-bundle prompt support yet, or the current uncommitted support already present. Do not discard unrelated edits.

- [ ] **Step 2: Write or verify the failing test for provider output-bundle contract injection**

In `tests/test_prompt_contract_injection.py`, ensure there is a test equivalent to:

```python
def test_provider_output_bundle_appends_contract_block_with_resolved_path(tmp_path: Path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "docs" / "backlog").mkdir(parents=True)
    (tmp_path / "docs" / "backlog" / "item.md").write_text("# Item\n")
    (tmp_path / "prompts" / "select.md").write_text("Select a backlog item.\n")

    workflow = {
        "version": "2.7",
        "name": "prompt-contract-output-bundle",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
                "default": "state/default-root",
            }
        },
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Select",
            "provider": "mock_provider",
            "input_file": "prompts/select.md",
            "output_bundle": {
                "path": "${inputs.state_root}/${run.id}/selection.json",
                "fields": [
                    {
                        "name": "selection_decision",
                        "json_pointer": "/selection_decision",
                        "type": "enum",
                        "allowed": ["READY", "NONE_READY"],
                    },
                    {
                        "name": "selected_item_path",
                        "json_pointer": "/selected_item_path",
                        "type": "relpath",
                        "under": "docs/backlog",
                        "must_exist_target": True,
                    },
                ],
            },
        }],
    }
```

The test should assert:

```python
assert "Write the following JSON bundle exactly as specified." in captured["prompt"]
assert "path: state/run-root/test-run/selection.json" in captured["prompt"]
assert "path: ${inputs.state_root}/${run.id}/selection.json" not in captured["prompt"]
assert "name: selection_decision" in captured["prompt"]
assert "json_pointer: /selection_decision" in captured["prompt"]
assert "allowed: READY, NONE_READY" in captured["prompt"]
assert "name: selected_item_path" in captured["prompt"]
assert "must_exist_target: true" in captured["prompt"]
```

- [ ] **Step 3: Run the focused test and confirm red if support is absent**

Run:

```bash
pytest tests/test_prompt_contract_injection.py::test_provider_output_bundle_appends_contract_block_with_resolved_path -q
```

Expected before implementation: fail because no output-bundle `Output Contract` block is injected, or pass if the current partial implementation already covers it. If it passes, do not rewrite working code for style.

- [ ] **Step 4: Implement the minimal runtime support if needed**

In `orchestrator/contracts/prompt_contract.py`, add a renderer shaped like:

```python
def render_output_bundle_contract_block(output_bundle: Dict[str, Any]) -> str:
    lines: List[str] = [
        "## Output Contract",
        "Write the following JSON bundle exactly as specified.",
        f"- path: {output_bundle['path']}",
        "  format: JSON object",
        "  fields:",
    ]
    for spec in output_bundle.get("fields", []):
        lines.append(f"    - name: {spec['name']}")
        lines.append(f"      json_pointer: {spec['json_pointer']}")
        lines.append(f"      type: {spec['type']}")
        if "allowed" in spec:
            lines.append("      allowed: " + ", ".join(str(value) for value in spec["allowed"]))
        if "under" in spec:
            lines.append(f"      under: {spec['under']}")
        if spec.get("must_exist_target"):
            lines.append("      must_exist_target: true")
        if spec.get("required") is False:
            lines.append("      required: false")
    return "\n".join(lines) + "\n"
```

In `orchestrator/workflow/prompting.py`, update `apply_output_contract_prompt_suffix` so it chooses `render_output_contract_block(expected_outputs)` when present, otherwise `render_output_bundle_contract_block(output_bundle)` when the step has an `output_bundle`.

- [ ] **Step 5: Align docs and specs**

Update the wording so these three statements are simultaneously true:

- `specs/dsl.md`: `inject_output_contract` applies to provider steps with `expected_outputs` or `output_bundle`.
- `specs/providers.md`: provider prompt composition appends an `Output Contract` for `expected_outputs` or `output_bundle`, with resolved paths.
- `docs/workflow_drafting_guide.md`: provider `output_bundle` steps receive concrete bundle path and field contract in the prompt suffix, so prompts should not duplicate it unless the step is unusually high risk.

- [ ] **Step 6: Run focused verification**

Run:

```bash
pytest tests/test_prompt_contract_injection.py -q
```

Expected: all tests in that file pass.

- [ ] **Step 7: Commit Task 1**

Only if Task 1 changes are clean and scoped:

```bash
git add orchestrator/contracts/prompt_contract.py orchestrator/workflow/prompting.py tests/test_prompt_contract_injection.py docs/workflow_drafting_guide.md specs/dsl.md specs/providers.md specs/acceptance/index.md
git commit -m "Support output bundle prompt contracts"
```

## Task 2: Add A Regression For The Drain Control-Flow Shape

**Files:**
- Modify: `tests/test_structured_control_flow.py`

- [ ] **Step 1: Add imports if missing**

Add only the imports the new test needs:

```python
import json
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.providers.executor import ProviderExecutor
```

- [ ] **Step 2: Add a minimal item-stack library helper**

Add a helper near the existing repeat-until call helpers:

```python
def _write_drain_item_library(workspace: Path) -> None:
    library_path = workspace / "workflows" / "library" / "drain_item_stack.yaml"
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.7",
                "name": "drain-item-stack",
                "inputs": {
                    "item_state_root": {"type": "relpath", "under": "state"},
                    "brief_path": {"type": "relpath", "under": "docs", "must_exist_target": True},
                },
                "outputs": {
                    "item_outcome": {
                        "kind": "scalar",
                        "type": "enum",
                        "allowed": ["APPROVED", "SKIPPED"],
                        "from": {"ref": "root.steps.PublishItemOutputs.artifacts.item_outcome"},
                    },
                },
                "steps": [
                    {
                        "name": "WriteOutcome",
                        "id": "write_outcome",
                        "command": [
                            "bash",
                            "-lc",
                            "mkdir -p '${inputs.item_state_root}' && printf 'APPROVED\\n' > '${inputs.item_state_root}/item_outcome.txt'",
                        ],
                    },
                    {
                        "name": "PublishItemOutputs",
                        "id": "publish_item_outputs",
                        "command": ["bash", "-lc", "true"],
                        "expected_outputs": [
                            {
                                "name": "item_outcome",
                                "path": "${inputs.item_state_root}/item_outcome.txt",
                                "type": "enum",
                                "allowed": ["APPROVED", "SKIPPED"],
                            }
                        ],
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
```

- [ ] **Step 3: Add the drain workflow fixture**

Add a helper that constructs a workflow with:

- `repeat_until` max 2.
- provider `SelectNextBacklogItem` using `output_bundle`.
- `RouteSelectedBacklogItem` as a `match`.
- READY case calls `item_stack`.
- READY case exports `selected_item_outcome` from `self.steps.RunSelectedBacklogItem.artifacts.item_outcome`.
- NONE_READY case sets and exports `selected_item_outcome: NONE_READY`.
- `RecordProcessedBacklogItem` runs after the `match`, reads `steps.RouteSelectedBacklogItem.artifacts.selected_item_outcome`, and appends to the ledger only when outcome is not `NONE_READY`.

The essential structure should be:

```python
"artifacts": {
    "backlog_loop_decision": {
        "kind": "scalar",
        "type": "enum",
        "allowed": ["READY", "NONE_READY"],
    },
    "selected_item_outcome": {
        "kind": "scalar",
        "type": "enum",
        "allowed": ["APPROVED", "SKIPPED", "NONE_READY"],
    },
},
```

and:

```python
"outputs": {
    "selection_decision": {
        "kind": "scalar",
        "type": "enum",
        "allowed": ["READY", "NONE_READY"],
        "from": {"ref": "self.steps.RouteSelectedBacklogItem.artifacts.backlog_loop_decision"},
    },
},
```

- [ ] **Step 4: Add the runtime test**

Use `ProviderExecutor` patching, like `tests/test_workflow_examples_v0.py`, so no real provider runs:

```python
def test_repeat_until_drain_records_declared_call_output_from_match_statement(tmp_path: Path):
    _write_drain_item_library(tmp_path)
    (tmp_path / "docs" / "backlog").mkdir(parents=True)
    (tmp_path / "docs" / "backlog" / "item.md").write_text("# Item\n", encoding="utf-8")
    workflow_path = _write_workflow(tmp_path, _drain_selector_workflow())
    loaded = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    calls = {"count": 0}
    prompts: list[str] = []

    def _prepare_invocation(_self, *_args, **kwargs):
        prompts.append(kwargs.get("prompt_content", "") or "")
        return SimpleNamespace(input_mode="stdin", prompt=prompts[-1]), None

    def _execute(_self, _invocation, **_kwargs):
        index = calls["count"]
        calls["count"] += 1
        decision = "READY" if index == 0 else "NONE_READY"
        selected = "docs/backlog/item.md" if decision == "READY" else "docs/backlog/README.md"
        if selected.endswith("README.md"):
            (tmp_path / "docs" / "backlog" / "README.md").write_text("# Backlog\n", encoding="utf-8")
        path = tmp_path / "state" / "selector" / "test-run" / "iterations" / str(index) / "selection.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"selection_decision": decision, "selected_item_path": selected}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()

    assert state["status"] == "completed"
    assert calls["count"] == 2
    assert state["steps"]["DrainReadyBacklogItems"]["artifacts"]["selection_decision"] == "NONE_READY"
    assert state["steps"]["DrainReadyBacklogItems[0].RouteSelectedBacklogItem"]["artifacts"]["selected_item_outcome"] == "APPROVED"
    assert state["steps"]["DrainReadyBacklogItems[1].RouteSelectedBacklogItem"]["artifacts"]["selected_item_outcome"] == "NONE_READY"
    ledger = json.loads((tmp_path / "state" / "selector" / "test-run" / "processed_ledger.json").read_text())
    assert ledger == {
        "processed_items": [
            {
                "iteration": 0,
                "selected_item_path": "docs/backlog/item.md",
                "item_outcome": "APPROVED",
            }
        ]
    }
    assert "path: state/selector/test-run/iterations/0/selection.json" in prompts[0]
```

- [ ] **Step 5: Run the new focused test**

Run:

```bash
pytest tests/test_structured_control_flow.py -k "drain_records_declared_call_output" -q
```

Expected: pass.

- [ ] **Step 6: Run related structured-control tests**

Run:

```bash
pytest tests/test_structured_control_flow.py -k "repeat_until or match" -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add tests/test_structured_control_flow.py
git commit -m "Cover drain loop call-output dataflow"
```

## Task 3: Simplify The Paper Backlog Drain Workflow

**Files:**
- Modify: `/home/ollie/Documents/ptychopinnpaper2/workflows/paper_backlog_next_design_plan_impl_stack.yaml`
- Modify: `/home/ollie/Documents/ptychopinnpaper2/workflows/prompts/paper_backlog/select_next_backlog_item.md`

- [ ] **Step 1: Add a statement-level selected outcome artifact**

In the paper workflow `artifacts:` block, add:

```yaml
  selected_item_outcome:
    kind: scalar
    type: enum
    allowed: ["APPROVED", "SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION", "NONE_READY"]
```

- [ ] **Step 2: Export the child outcome through the `READY` match case**

In `RouteSelectedBacklogItem.match.cases.READY.outputs`, keep `backlog_loop_decision` and add:

```yaml
                  selected_item_outcome:
                    kind: scalar
                    type: enum
                    allowed: ["APPROVED", "SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION", "NONE_READY"]
                    from:
                      ref: self.steps.RunSelectedBacklogItem.artifacts.item_outcome
```

This uses the generic stack's declared workflow output instead of reading `${item_state_root}/item_outcome.txt`.

- [ ] **Step 3: Export a sentinel outcome through the `NONE_READY` case**

In `RouteSelectedBacklogItem.match.cases.NONE_READY.outputs`, add matching `selected_item_outcome` and add a scalar step:

```yaml
                  selected_item_outcome:
                    kind: scalar
                    type: enum
                    allowed: ["APPROVED", "SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION", "NONE_READY"]
                    from:
                      ref: self.steps.WriteNoneReadyItemOutcome.artifacts.selected_item_outcome
```

with:

```yaml
                  - name: WriteNoneReadyItemOutcome
                    id: write_none_ready_item_outcome
                    set_scalar:
                      artifact: selected_item_outcome
                      value: NONE_READY
```

- [ ] **Step 4: Move ledger recording after the `match`**

Remove `RecordProcessedBacklogItem` from the READY case. Add it as the next loop-body step after `RouteSelectedBacklogItem`, so it reads the match statement artifact:

```yaml
        - name: RecordProcessedBacklogItem
          id: record_processed_backlog_item
          command:
            - python
            - -c
            - |
              import json
              import pathlib
              import sys

              selector_state_root = pathlib.Path(sys.argv[1])
              run_id = sys.argv[2]
              iteration = int(sys.argv[3])
              selected_item_path = sys.argv[4]
              item_outcome = sys.argv[5]

              ledger_path = selector_state_root / run_id / "processed_ledger.json"
              ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
              if item_outcome != "NONE_READY":
                  processed_items = ledger.setdefault("processed_items", [])
                  processed_items.append(
                      {
                          "iteration": iteration,
                          "selected_item_path": selected_item_path,
                          "item_outcome": item_outcome,
                      }
                  )
                  ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
              (selector_state_root / run_id / "processed_ledger_path.txt").write_text(
                  ledger_path.as_posix() + "\n",
                  encoding="utf-8",
              )
            - ${inputs.selector_state_root}
            - ${run.id}
            - ${loop.index}
            - ${steps.PrepareSelectedBacklogItemInputs.artifacts.selected_item_path}
            - ${steps.RouteSelectedBacklogItem.artifacts.selected_item_outcome}
          expected_outputs:
            - name: processed_ledger_path
              path: ${inputs.selector_state_root}/${run.id}/processed_ledger_path.txt
              type: relpath
              under: state
              must_exist_target: true
```

The record step intentionally still runs on `NONE_READY`; it refreshes the ledger pointer but does not append a fake processed item.

- [ ] **Step 5: Tighten the selector prompt**

In `/home/ollie/Documents/ptychopinnpaper2/workflows/prompts/paper_backlog/select_next_backlog_item.md`, replace the final output block:

```markdown
Write only the JSON file required by the output contract. The JSON must contain:
- `selection_decision`: `READY` or `NONE_READY`
- `selected_item_path`: path to the chosen backlog item under `docs/backlog`, or `docs/backlog/README.md` when `NONE_READY`

Create the output file's parent directory if it does not already exist.
```

with:

```markdown
Write only the JSON bundle required by the Output Contract. Create its parent directory if it does not already exist.
```

Do not duplicate the bundle path or fields in the prompt; the injected contract is the authoritative path/field list.

- [ ] **Step 6: Validate the paper workflow schema**

Run:

```bash
cd /home/ollie/Documents/ptychopinnpaper2
source /home/ollie/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
export PYTHONPATH=/home/ollie/Documents/agent-orchestration${PYTHONPATH:+:$PYTHONPATH}
python -m orchestrator run workflows/paper_backlog_next_design_plan_impl_stack.yaml --dry-run
```

Expected: dry-run succeeds without undefined variables, invalid match outputs, or path-contract validation errors.

- [ ] **Step 7: Inspect the composed selector prompt with a debug smoke**

Run a bounded debug run only if you are ready for a real provider invocation:

```bash
cd /home/ollie/Documents/ptychopinnpaper2
source /home/ollie/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
export PYTHONPATH=/home/ollie/Documents/agent-orchestration${PYTHONPATH:+:$PYTHONPATH}
python -m orchestrator run workflows/paper_backlog_next_design_plan_impl_stack.yaml --stream-output --debug
```

Expected in `.orchestrate/runs/<run_id>/logs/SelectNextBacklogItem.prompt.txt`:

```text
## Output Contract
Write the following JSON bundle exactly as specified.
- path: state/paper-backlog-selector/<run_id>/iterations/0/selection.json
```

Do not use `conda run`; it can swallow streaming output.

- [ ] **Step 8: Commit Task 3 in the paper repo**

```bash
cd /home/ollie/Documents/ptychopinnpaper2
git add workflows/paper_backlog_next_design_plan_impl_stack.yaml workflows/prompts/paper_backlog/select_next_backlog_item.md
git commit -m "Stabilize paper backlog drain workflow"
```

## Task 4: End-To-End Verification And Cleanup

**Files:**
- Verify: local repo tests
- Verify: paper repo dry-run and, if approved, real debug run

- [ ] **Step 1: Run local focused tests**

```bash
cd /home/ollie/Documents/agent-orchestration
pytest tests/test_prompt_contract_injection.py -q
pytest tests/test_structured_control_flow.py -k "drain_records_declared_call_output or repeat_until or match" -q
```

Expected: pass.

- [ ] **Step 2: Run representative reusable-stack smoke tests**

```bash
cd /home/ollie/Documents/agent-orchestration
pytest tests/test_workflow_examples_v0.py::test_backlog_priority_design_plan_impl_stack_v2_call_runtime \
       tests/test_workflow_examples_v0.py::test_design_plan_impl_review_stack_v2_call_runtime \
       -q
```

Expected: both pass.

- [ ] **Step 3: Run paper workflow dry-run**

```bash
cd /home/ollie/Documents/ptychopinnpaper2
source /home/ollie/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
export PYTHONPATH=/home/ollie/Documents/agent-orchestration${PYTHONPATH:+:$PYTHONPATH}
python -m orchestrator run workflows/paper_backlog_next_design_plan_impl_stack.yaml --dry-run
```

Expected: dry-run succeeds.

- [ ] **Step 4: Check diffs before final commit**

```bash
cd /home/ollie/Documents/agent-orchestration
git diff --check
git status --short

cd /home/ollie/Documents/ptychopinnpaper2
git diff --check -- workflows/paper_backlog_next_design_plan_impl_stack.yaml workflows/prompts/paper_backlog/select_next_backlog_item.md
git status --short
```

Expected: no whitespace errors. Status may include unrelated dirty files; stage only files from this plan.

- [ ] **Step 5: Commit local repo changes if not already committed**

```bash
cd /home/ollie/Documents/agent-orchestration
git add orchestrator/contracts/prompt_contract.py \
        orchestrator/workflow/prompting.py \
        tests/test_prompt_contract_injection.py \
        tests/test_structured_control_flow.py \
        docs/workflow_drafting_guide.md \
        specs/dsl.md \
        specs/providers.md \
        specs/acceptance/index.md \
        docs/plans/2026-04-13-paper-backlog-drain-stabilization-plan.md
git commit -m "Stabilize drain workflow contracts"
```

- [ ] **Step 6: Relaunch the drain only after confirming intent**

Use tmux for a real long-running workflow:

```bash
tmux new-session -d -s paper-backlog-drain-fixed
tmux send-keys -t paper-backlog-drain-fixed "cd /home/ollie/Documents/ptychopinnpaper2" C-m
tmux send-keys -t paper-backlog-drain-fixed "source /home/ollie/miniconda3/etc/profile.d/conda.sh && conda activate ptycho311 && export PYTHONPATH=/home/ollie/Documents/agent-orchestration\${PYTHONPATH:+:\$PYTHONPATH} && python -m orchestrator run workflows/paper_backlog_next_design_plan_impl_stack.yaml --stream-output --debug" C-m
```

Expected: selector prompt includes a concrete output-bundle path; iteration 0 writes `state/paper-backlog-selector/<run_id>/iterations/0/selection.json`; ledger records the selected item outcome using the generic stack output.

## Review Notes

The writing-plans skill normally asks for a plan-document-reviewer subagent. Do not spawn that reviewer unless the user explicitly authorizes subagents; current session policy only permits subagents when the user asks for them. If no reviewer is authorized, do a manual review against:

- `docs/workflow_drafting_guide.md`, sections on output contracts, `match`, `repeat_until`, and `call`.
- `specs/dsl.md`, structured control and reusable call boundary.
- `specs/providers.md`, provider prompt composition.
- The previous failed run evidence:
  - undefined `steps.RunSelectedBacklogItem.artifacts.item_outcome`
  - relpath contract pointed at a rich JSON ledger body
  - selector prompt lacked concrete `output_bundle.path`
