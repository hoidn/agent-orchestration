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


def test_runtime_emits_typed_terminal_observability_summary_without_provider(tmp_path: Path):
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.14"
name: lisp_frontend_design_delta/drain::drain
outputs:
  status:
    kind: scalar
    type: enum
    allowed: ["BLOCKED"]
    from:
      ref: root.steps.Finalize.artifacts.status
  selected_item:
    kind: scalar
    type: string
    from:
      ref: root.steps.Finalize.artifacts.selected_item
  blocker_class:
    kind: scalar
    type: enum
    allowed: ["missing_resource"]
    from:
      ref: root.steps.Finalize.artifacts.blocker_class
steps:
  - name: Finalize
    command:
      - python
      - -c
      - |
        import json
        from pathlib import Path

        state_dir = Path("state")
        audit_dir = Path("runtime-audits")
        run_legacy_dir = Path(".orchestrate/runs/run-typed-terminal-runtime/artifacts/work")
        state_dir.mkdir(parents=True, exist_ok=True)
        audit_dir.mkdir(parents=True, exist_ok=True)
        run_legacy_dir.mkdir(parents=True, exist_ok=True)
        (run_legacy_dir / "drain_summary.json").write_text(
            json.dumps({"status": "BLOCKED", "selected_item": "docs/design/example.md"}) + "\\n",
            encoding="utf-8",
        )
        Path("state/final.json").write_text(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "selected_item": "docs/design/example.md",
                    "blocker_class": "missing_resource",
                }
            )
            + "\\n",
            encoding="utf-8",
        )
        Path("runtime-audits/design_delta_parent_drain_transition_audit.jsonl").write_text(
            json.dumps(
                {
                    "transition_name": "record_selected_item_outcome",
                    "resource_kind": "drain_status",
                    "resource_id": "design-delta-parent-drain",
                    "idempotency_key": "idem-1",
                    "request_digest": "sha256:req",
                    "outcome_code": "committed",
                    "version": "1",
                    "result": {"status": "BLOCKED"},
                }
            )
            + "\\n",
            encoding="utf-8",
        )
    output_bundle:
      path: state/final.json
      fields:
        - name: status
          kind: scalar
          type: enum
          allowed: ["BLOCKED"]
          json_pointer: /status
        - name: selected_item
          type: string
          json_pointer: /selected_item
        - name: blocker_class
          type: enum
          allowed: ["missing_resource"]
          json_pointer: /blocker_class
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-typed-terminal-runtime")
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
                "provider": "unused_summary_provider",
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
    assert final_state["workflow_outputs"]["status"] == "BLOCKED"
    assert (summaries_dir / "typed-terminal-summary.json").exists()
    assert (summaries_dir / "typed-terminal-summary.md").exists()
    assert (summaries_dir / "observability_summary_report.json").exists()
    report = json.loads((summaries_dir / "observability_summary_report.json").read_text(encoding="utf-8"))
    index = json.loads((summaries_dir / "index.json").read_text(encoding="utf-8"))
    typed_terminal_entries = [entry for entry in index["entries"] if entry["kind"] == "typed_terminal"]
    assert report["status"] == "pass"
    assert report["selected_c0_row_ids"] == ["c0.drain_summary_report_target_final_summary_view"]
    assert len(typed_terminal_entries) == 1
    assert typed_terminal_entries[0]["authority"] == "observability_only"


def test_runtime_skips_typed_terminal_observability_summary_for_unscoped_workflow(tmp_path: Path) -> None:
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.14"
name: unrelated-typed-terminal-runtime
outputs:
  status:
    kind: scalar
    type: enum
    allowed: ["DONE"]
    from:
      ref: root.steps.Finalize.artifacts.status
steps:
  - name: Finalize
    command:
      - python
      - -c
      - |
        import json
        from pathlib import Path

        Path("state").mkdir(parents=True, exist_ok=True)
        Path("state/final.json").write_text(
            json.dumps({"status": "DONE"}) + "\\n",
            encoding="utf-8",
        )
    output_bundle:
      path: state/final.json
      fields:
        - name: status
          kind: scalar
          type: enum
          allowed: ["DONE"]
          json_pointer: /status
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-unrelated-typed-terminal-runtime")
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
                "provider": "unused_summary_provider",
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
    assert final_state["workflow_outputs"]["status"] == "DONE"
    assert not (summaries_dir / "typed-terminal-summary.json").exists()
    assert not (summaries_dir / "typed-terminal-summary.md").exists()
    assert not (summaries_dir / "observability_summary_report.json").exists()


def test_runtime_persists_failing_observability_report_for_invalid_transition_audit(tmp_path: Path) -> None:
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.14"
name: lisp_frontend_design_delta/drain::drain
outputs:
  status:
    kind: scalar
    type: enum
    allowed: ["BLOCKED"]
    from:
      ref: root.steps.Finalize.artifacts.status
  selected_item:
    kind: scalar
    type: string
    from:
      ref: root.steps.Finalize.artifacts.selected_item
  blocker_class:
    kind: scalar
    type: enum
    allowed: ["missing_resource"]
    from:
      ref: root.steps.Finalize.artifacts.blocker_class
steps:
  - name: Finalize
    command:
      - python
      - -c
      - |
        import json
        from pathlib import Path

        state_dir = Path("state")
        run_audit_dir = Path(".orchestrate/runs/run-typed-terminal-invalid-audit/runtime-audits")
        run_legacy_dir = Path(".orchestrate/runs/run-typed-terminal-invalid-audit/artifacts/work")
        state_dir.mkdir(parents=True, exist_ok=True)
        run_audit_dir.mkdir(parents=True, exist_ok=True)
        run_legacy_dir.mkdir(parents=True, exist_ok=True)
        (run_legacy_dir / "drain_summary.json").write_text(
            json.dumps({"status": "BLOCKED", "selected_item": "docs/design/example.md"}) + "\\n",
            encoding="utf-8",
        )
        Path("state/final.json").write_text(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "selected_item": "docs/design/example.md",
                    "blocker_class": "missing_resource",
                }
            )
            + "\\n",
            encoding="utf-8",
        )
        (run_audit_dir / "design_delta_parent_drain_transition_audit.jsonl").write_text(
            "{not-json}\\n",
            encoding="utf-8",
        )
    output_bundle:
      path: state/final.json
      fields:
        - name: status
          kind: scalar
          type: enum
          allowed: ["BLOCKED"]
          json_pointer: /status
        - name: selected_item
          type: string
          json_pointer: /selected_item
        - name: blocker_class
          type: enum
          allowed: ["missing_resource"]
          json_pointer: /blocker_class
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-typed-terminal-invalid-audit")
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
                "provider": "unused_summary_provider",
                "timeout_sec": 30,
                "best_effort": True,
                "max_input_chars": 12000,
                "profile": "phase-performance",
            }
        },
    )

    final_state = executor.execute(on_error="stop")

    summaries_dir = state_manager.run_root / "summaries"
    report = json.loads((summaries_dir / "observability_summary_report.json").read_text(encoding="utf-8"))
    payload = json.loads((summaries_dir / "typed-terminal-summary.json").read_text(encoding="utf-8"))
    index = json.loads((summaries_dir / "index.json").read_text(encoding="utf-8"))
    typed_terminal_entries = [entry for entry in index["entries"] if entry["kind"] == "typed_terminal"]

    assert final_state["status"] == "completed"
    assert report["status"] == "fail"
    assert payload["transition_audit"]["status"] == "invalid"
    assert "observability_summary_transition_audit_invalid" in {
        diagnostic["code"]
        for diagnostic in report["diagnostics"]["errors"]
    }
    assert len(typed_terminal_entries) == 1
    assert typed_terminal_entries[0]["authority"] == "observability_only"


def test_validated_terminal_projection_uses_compiled_workflow_outputs_when_state_outputs_absent(
    tmp_path: Path,
) -> None:
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.14"
name: typed-terminal-projection-runtime
outputs:
  status:
    kind: scalar
    type: enum
    allowed: ["BLOCKED"]
    from:
      ref: root.steps.Finalize.artifacts.status
  selected_item:
    kind: scalar
    type: string
    from:
      ref: root.steps.Finalize.artifacts.selected_item
  blocker_class:
    kind: scalar
    type: enum
    allowed: ["missing_resource"]
    from:
      ref: root.steps.Finalize.artifacts.blocker_class
steps:
  - name: Finalize
    command: ["bash", "-lc", "exit 0"]
    output_bundle:
      path: state/final.json
      fields:
        - name: status
          kind: scalar
          type: enum
          allowed: ["BLOCKED"]
          json_pointer: /status
        - name: selected_item
          type: string
          json_pointer: /selected_item
        - name: blocker_class
          type: enum
          allowed: ["missing_resource"]
          json_pointer: /blocker_class
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-typed-terminal-projection")
    state_manager.initialize("workflow.yaml", {})
    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=False,
    )

    projection = executor._validated_terminal_projection_for_observability(
        {
            "run_id": "run-typed-terminal-projection",
            "status": "completed",
            "steps": {
                "Finalize": {
                    "artifacts": {
                        "status": "BLOCKED",
                        "selected_item": "docs/design/example.md",
                        "blocker_class": "missing_resource",
                    }
                }
            },
        }
    )

    assert projection == {
        "status": "BLOCKED",
        "selected_item": "docs/design/example.md",
        "blocker_class": "missing_resource",
    }


def test_transition_audit_paths_ignore_workspace_foreign_audits(tmp_path: Path) -> None:
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.14"
name: typed-terminal-audit-scope
steps:
  - name: Noop
    command: ["bash", "-lc", "exit 0"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-typed-terminal-audit-scope")
    state_manager.initialize("workflow.yaml", {})
    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=False,
    )

    foreign_audit = tmp_path / "fixtures" / "foreign_transition_audit.jsonl"
    foreign_audit.parent.mkdir(parents=True, exist_ok=True)
    foreign_audit.write_text("{}\n", encoding="utf-8")

    assert executor._transition_audit_paths() == []


def test_old_writer_paths_ignore_workspace_foreign_legacy_summaries(tmp_path: Path) -> None:
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.14"
name: typed-terminal-old-writer-scope
steps:
  - name: Noop
    command: ["bash", "-lc", "exit 0"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-typed-terminal-old-writer-scope")
    state_manager.initialize("workflow.yaml", {})
    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=False,
    )

    foreign_legacy_summary = tmp_path / "artifacts" / "work" / "drain_summary.json"
    foreign_legacy_summary.parent.mkdir(parents=True, exist_ok=True)
    foreign_legacy_summary.write_text(
        json.dumps({"status": "BLOCKED", "selected_item": "docs/design/example.md"}) + "\n",
        encoding="utf-8",
    )

    assert executor._observability_old_writer_paths() == {}
