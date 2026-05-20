"""Runtime smoke coverage for phase-performance summaries."""

import json
import textwrap
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


def test_phase_performance_profile_summarizes_nested_provider_visits(tmp_path: Path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Decide whether the loop should stop.\n", encoding="utf-8")

    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.7"
name: nested-summary-runtime
providers:
  fake_provider:
    command:
      - bash
      - -lc
      - |
        cat >/dev/null
        mkdir -p state
        count=$(cat state/review-count.txt 2>/dev/null || printf '0')
        count=$((count + 1))
        printf '%s\\n' "$count" > state/review-count.txt
        if [ "$count" -lt 2 ]; then decision=REVISE; else decision=APPROVE; fi
        printf '{"review_decision":"%s"}\\n' "$decision" > state/review-decision.json
    input_mode: "stdin"
  fake_summary:
    command: ["bash", "-lc", "cat >/dev/null; printf 'summary ok\\n'"]
    input_mode: "stdin"
steps:
  - name: ReviewLoop
    id: review_loop
    repeat_until:
      id: review_iteration
      outputs:
        review_decision:
          kind: scalar
          type: enum
          allowed: [APPROVE, REVISE]
          from:
            ref: self.steps.ReviewProvider.artifacts.review_decision
      condition:
        compare:
          left:
            ref: self.outputs.review_decision
          op: eq
          right: APPROVE
      max_iterations: 3
      steps:
        - name: ReviewProvider
          id: review_provider
          provider: fake_provider
          input_file: prompt.md
          output_bundle:
            path: state/review-decision.json
            fields:
              - name: review_decision
                json_pointer: /review_decision
                type: enum
                allowed: [APPROVE, REVISE]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-nested-summary-runtime")
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
    index = json.loads((summaries_dir / "index.json").read_text(encoding="utf-8"))
    provider_entries = [
        entry
        for entry in index["entries"]
        if entry["kind"] == "provider" and entry["step_name"] == "ReviewProvider"
    ]
    assert final_state["status"] == "completed"
    assert len(provider_entries) == 2
    assert provider_entries[0]["summary_path"] != provider_entries[1]["summary_path"]
    for entry in provider_entries:
        assert (state_manager.run_root / entry["summary_path"]).read_text() == "summary ok\n"


def test_live_agent_notes_summarize_session_transport_during_provider_step(tmp_path: Path):
    workflow_file = tmp_path / "workflow.yaml"
    session_script = textwrap.dedent(
        """
        import json, sys, time
        print(json.dumps({"type": "session.started", "session_id": "sess-live"}), flush=True)
        print(json.dumps({"type": "assistant.message", "role": "assistant", "text": "working live"}), flush=True)
        time.sleep(0.25)
        print(json.dumps({"type": "response.completed", "session_id": "sess-live"}), flush=True)
        """
    ).strip()
    workflow_file.write_text(
        f"""
version: "2.10"
name: live-note-runtime
providers:
  session_provider:
    command: ["python", "-c", {json.dumps(session_script)}]
    input_mode: "stdin"
    session_support:
      metadata_mode: codex_exec_jsonl_stdout
      fresh_command: ["python", "-c", {json.dumps(session_script)}]
      resume_command: ["python", "-c", {json.dumps(session_script + " # ${SESSION_ID}")}]
  live_summary:
    command: ["bash", "-lc", "cat >/dev/null; printf 'live note from tail\\n'"]
    input_mode: "stdin"
steps:
  - name: ProviderWork
    id: provider_work
    provider: session_provider
    provider_session:
      mode: fresh
      publish_artifact: implementation_session_id
artifacts:
  implementation_session_id:
    kind: scalar
    type: string
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-live-note-runtime")
    state_manager.initialize("workflow.yaml", {})

    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=True,
        observability={
            "step_summaries": {
                "enabled": True,
                "mode": "sync",
                "provider": "live_summary",
                "timeout_sec": 30,
                "best_effort": True,
                "max_input_chars": 12000,
                "profile": "phase-performance",
                "live_agent_notes": {
                    "enabled": True,
                    "provider": "live_summary",
                    "interval_sec": 0.05,
                    "timeout_sec": 10,
                    "max_tail_chars": 2000,
                },
            }
        },
    )

    final_state = executor.execute(on_error="stop")

    summaries_dir = state_manager.run_root / "summaries"
    metadata = json.loads((summaries_dir / "live-current-step.json").read_text(encoding="utf-8"))
    assert final_state["status"] == "completed"
    assert (summaries_dir / "live-current-step.md").read_text(encoding="utf-8") == "live note from tail\n"
    assert metadata["schema"] == "orchestrator_live_agent_note/v1"
    assert metadata["step_name"] == "ProviderWork"
    assert metadata["provider"] == "live_summary"
