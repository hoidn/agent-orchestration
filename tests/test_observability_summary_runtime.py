"""Runtime smoke coverage for phase-performance summaries."""

import json
from pathlib import Path

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def test_phase_performance_profile_summarizes_provider_and_call_boundaries(tmp_path: Path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Do provider work.\n", encoding="utf-8")

    child_file = tmp_path / "child.yaml"
    child_file.write_text(
        """
version: "2.5"
name: summary-child
inputs:
  write_root:
    type: relpath
    under: state
outputs:
  child_status:
    kind: scalar
    type: enum
    allowed: ["DONE"]
    from:
      ref: root.steps.ChildCommand.artifacts.child_status
steps:
  - name: ChildCommand
    id: child_command
    command:
      - python
      - -c
      - |
        import json, pathlib
        path = pathlib.Path("${inputs.write_root}") / "child.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"child_status": "DONE"}))
    output_bundle:
      path: ${inputs.write_root}/child.json
      fields:
        - name: child_status
          json_pointer: /child_status
          type: enum
          allowed: ["DONE"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.5"
name: summary-runtime
imports:
  child: ./child.yaml
providers:
  fake_provider:
    command: ["bash", "-lc", "cat >/dev/null; printf 'provider done\\n'"]
    input_mode: "stdin"
  fake_summary:
    command: ["bash", "-lc", "cat >/dev/null; printf 'summary ok\\n'"]
    input_mode: "stdin"
steps:
  - name: CommandWork
    id: command_work
    command: ["bash", "-lc", "echo command"]
    output_capture: text
  - name: ProviderWork
    id: provider_work
    provider: fake_provider
    input_file: prompt.md
  - name: PhaseWork
    id: phase_work
    call: child
    with:
      write_root: state/child
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-summary-runtime")
    state_manager.initialize("workflow.yaml", {})

    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=False,
        observability={
            "step_summaries": {
                "enabled": True,
                "mode": "sync",
                "provider": "fake_summary",
                "timeout_sec": 30,
                "best_effort": True,
                "max_input_chars": 12000,
                "profile": "phase-performance",
            }
        },
    )

    final_state = executor.execute(on_error="stop")

    summaries_dir = state_manager.run_root / "summaries"
    assert final_state["status"] == "completed"
    assert (summaries_dir / "ProviderWork.provider.summary.md").read_text() == "summary ok\n"
    assert (summaries_dir / "PhaseWork.phase.summary.md").read_text() == "summary ok\n"
    assert not (summaries_dir / "CommandWork.summary.md").exists()
    assert not (summaries_dir / "CommandWork.step.summary.md").exists()
    index = json.loads((summaries_dir / "index.json").read_text(encoding="utf-8"))
    assert [entry["step_name"] for entry in index["entries"]] == ["ProviderWork", "PhaseWork"]
    assert (summaries_dir / "README.md").exists()
    assert (summaries_dir / "run-summary.md").exists()
