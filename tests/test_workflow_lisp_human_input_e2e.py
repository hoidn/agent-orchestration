"""Public Workflow Lisp/CLI coverage for durable host-input loops."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.main import main
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import PreparedProviderPolicy
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.human_input import get_human_input


_HELPER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.32")
  (defmodule human_input_e2e/helper)
  (export ask-host)
  (defworkflow ask-host ((question String)) -> HumanReply
    (request-input question)))
"""


_ENTRY_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.32")
  (defmodule human_input_e2e/entry)
  (import human_input_e2e/helper :only (ask-host))
  (export run)
  (defrecord Progress (round Int))
  (defworkflow run () -> HumanReply
    (let* ((question
             (provider-result providers.seed
               :prompt prompts.seed
               :inputs ()
               :returns String)))
      (loop/recur :max 3
        :state (record Progress :round 0)
        :on-exhausted (variant HumanReply CANCELLED)
        (fn (state)
          (let* ((reply (call ask-host :question question)))
            (match reply
              ((ANSWERED answer)
                (if (= state.round 0)
                  (continue (record Progress :round 1))
                  (done (variant HumanReply ANSWERED :text answer.text))))
              ((CANCELLED cancelled)
                (done (variant HumanReply CANCELLED))))))))))
"""


_FAIL_AFTER_REPLY_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.32")
  (defmodule human_input_e2e/entry)
  (import human_input_e2e/helper :only (ask-host))
  (export run)
  (defrecord Progress (round Int))
  (defworkflow run () -> String
    (loop/recur :max 1
      :state (record Progress :round 0)
      :on-exhausted "exhausted"
      (fn (state)
        (let* ((reply (call ask-host :question "Continue?")))
          (match reply
            ((ANSWERED answer)
              (let* ((after (provider-result providers.fail
                              :prompt prompts.fail
                              :inputs ()
                              :returns String)))
                (done after)))
            ((CANCELLED cancelled)
              (let* ((after (provider-result providers.fail
                              :prompt prompts.fail
                              :inputs ()
                              :returns String)))
                (done after)))))))))
"""


def _write_sources(
    workspace: Path,
    *,
    entry_source: str = _ENTRY_SOURCE,
) -> dict[str, Path]:
    helper = workspace / "human_input_e2e" / "helper.orc"
    helper.parent.mkdir()
    helper.write_text(_HELPER_SOURCE, encoding="utf-8")
    entry = helper.with_name("entry.orc")
    entry.write_text(entry_source, encoding="utf-8")
    prompts = helper.parent / "prompts"
    prompts.mkdir()
    (prompts / "seed.md").write_text("seed\n", encoding="utf-8")
    (prompts / "fail.md").write_text("fail\n", encoding="utf-8")
    providers = workspace / "providers.json"
    providers.write_text(
        json.dumps({"providers.seed": "seed", "providers.fail": "fail"}),
        encoding="utf-8",
    )
    prompt_externs = workspace / "prompts.json"
    prompt_externs.write_text(
        json.dumps({"prompts.seed": "prompts/seed.md", "prompts.fail": "prompts/fail.md"}),
        encoding="utf-8",
    )
    return {
        "entry": entry,
        "providers": providers,
        "prompts": prompt_externs,
        "source_root": workspace,
    }


def _frontend_argv(command: str, files: dict[str, Path]) -> list[str]:
    return [
        command,
        str(files["entry"]),
        "--source-root",
        str(files["source_root"]),
        "--entry-workflow",
        "run",
        "--provider-externs-file",
        str(files["providers"]),
        "--prompt-externs-file",
        str(files["prompts"]),
    ]


def _provider_transport(calls: list[str]):
    def prepare(_self, provider_name, *_args, **kwargs):
        calls.append(provider_name)
        prompt = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            provider_name=provider_name,
            prompt=prompt,
            prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name,
                model=None,
                effort=None,
                timeout_sec=kwargs.get("timeout_sec"),
                input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}),
            input_mode="stdin",
        ), None

    def execute(_self, invocation, **_kwargs):
        if invocation.provider_name == "fail":
            return SimpleNamespace(
                exit_code=2,
                stdout=b"",
                stderr=b"downstream failure",
                duration_ms=1,
                error=None,
                missing_placeholders=None,
                invalid_prompt_placeholder=False,
                raw_stdout=None,
                normalized_stdout=None,
                provider_session=None,
            )
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps("host question") + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    return prepare, execute


def _persisted_step_rows(value: object, step_id: str) -> list[dict[str, object]]:
    if isinstance(value, dict):
        rows = (
            [value]
            if value.get("step_id") == step_id and isinstance(value.get("artifacts"), dict)
            else []
        )
        for child in value.values():
            rows.extend(_persisted_step_rows(child, step_id))
        return rows
    if isinstance(value, list):
        return [row for child in value for row in _persisted_step_rows(child, step_id)]
    return []


def test_public_cli_imported_host_input_loop_answers_then_cancels_without_provider_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Answering one imported request reaches a distinct second request on resume."""

    files = _write_sources(tmp_path)
    calls: list[str] = []
    prepare, execute = _provider_transport(calls)
    monkeypatch.chdir(tmp_path)

    assert main(_frontend_argv("compile", files)) == 0
    capsys.readouterr()
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ), patch.object(sys, "argv", ["orchestrator", *_frontend_argv("run", files)]):
        assert main(_frontend_argv("run", files)) == 0

    runs = tuple((tmp_path / ".orchestrate" / "runs").iterdir())
    assert len(runs) == 1
    run_id = runs[0].name
    first = get_human_input(runs[0])
    assert first is not None
    assert first["status"] == "pending"
    assert calls == ["seed"]
    waiting_state = json.loads(
        (runs[0] / "state.json").read_text(encoding="utf-8")
    )
    assert waiting_state["status"] == "suspended"
    waiting_inputs = waiting_state["bound_inputs"]
    waiting_visits = waiting_state["step_visits"]
    frame_ids = tuple(first["resume_scope"]["call_frame_ids"])
    assert len(frame_ids) == 1
    assert tuple(waiting_state["call_frames"]) == frame_ids
    assert waiting_state["call_frames"][frame_ids[0]]["state"]["status"] == "running"

    assert main(["input", "get", run_id]) == 0
    assert json.loads(capsys.readouterr().out) == first
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        assert main(["resume", run_id, "--retry-delay", "0"]) == 0
    assert get_human_input(runs[0]) == first
    still_waiting = json.loads((runs[0] / "state.json").read_text(encoding="utf-8"))
    assert still_waiting["status"] == "suspended"
    assert still_waiting["bound_inputs"] == waiting_inputs
    assert still_waiting["step_visits"] == waiting_visits
    assert tuple(still_waiting["call_frames"]) == frame_ids
    assert still_waiting["call_frames"][frame_ids[0]]["state"]["status"] == "running"
    assert calls == ["seed"]

    assert main(["input", "answer", run_id, first["request_id"], "--text", "first"]) == 0
    capsys.readouterr()

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        assert main(["resume", run_id, "--retry-delay", "0"]) == 0

    second = get_human_input(runs[0])
    assert second is not None
    assert second["status"] == "pending"
    assert second["request_id"] != first["request_id"]
    assert calls == ["seed"]
    answered_rows = _persisted_step_rows(
        json.loads((runs[0] / "state.json").read_text(encoding="utf-8")),
        first["runtime_step_id"],
    )
    assert len(answered_rows) == 1
    assert answered_rows[0]["visit_count"] == 1
    assert answered_rows[0]["artifacts"] == {"variant": "ANSWERED", "text": "first"}

    assert main(["input", "cancel", run_id, second["request_id"]]) == 0
    capsys.readouterr()
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        assert main(["resume", run_id, "--retry-delay", "0"]) == 0

    state = json.loads((runs[0] / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"return__variant": "CANCELLED"}
    assert calls == ["seed"]


@pytest.mark.parametrize(
    "submission",
    (
        ("answer", ["--text", "yes"], {"variant": "ANSWERED", "text": "yes"}),
        ("cancel", [], {"variant": "CANCELLED"}),
    ),
)
def test_public_cli_completed_reply_survives_a_downstream_failure_without_reasking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    submission: tuple[str, list[str], dict[str, str]],
) -> None:
    """The compiled human-reply checkpoint reuses both reply alternatives."""

    files = _write_sources(tmp_path, entry_source=_FAIL_AFTER_REPLY_SOURCE)
    calls: list[str] = []
    prepare, execute = _provider_transport(calls)
    monkeypatch.chdir(tmp_path)

    assert main(_frontend_argv("compile", files)) == 0
    capsys.readouterr()
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ), patch.object(sys, "argv", ["orchestrator", *_frontend_argv("run", files)]):
        assert main(_frontend_argv("run", files)) == 0

    run_root = next((tmp_path / ".orchestrate" / "runs").iterdir())
    run_id = run_root.name
    request = get_human_input(run_root)
    assert request is not None and request["status"] == "pending"
    assert calls == []
    command, options, expected_reply = submission
    assert main(["input", command, run_id, request["request_id"], *options]) == 0
    capsys.readouterr()

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ):
        assert main(["resume", run_id, "--retry-delay", "0"]) == 1
    failed = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert get_human_input(run_root)["status"] == "consumed"
    assert calls == ["fail"]

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ):
        assert main(["resume", run_id, "--retry-delay", "0"]) == 1
    retried = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    assert retried["status"] == "failed"
    assert retried["steps"] == failed["steps"]
    assert get_human_input(run_root)["status"] == "consumed"
    reply_rows = _persisted_step_rows(failed, request["runtime_step_id"])
    assert len(reply_rows) == 1
    assert reply_rows[0]["visit_count"] == 1
    assert reply_rows[0]["artifacts"] == {
        "variant": expected_reply["variant"],
        **({"text": expected_reply["text"]} if "text" in expected_reply else {}),
    }
    assert calls == ["fail", "fail"]


def test_public_cli_consumed_reply_before_checkpoint_never_reasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A compiled reply commit remains authoritative if its shadow hook is interrupted."""

    files = _write_sources(tmp_path, entry_source=_FAIL_AFTER_REPLY_SOURCE)
    calls: list[str] = []
    prepare, execute = _provider_transport(calls)
    monkeypatch.chdir(tmp_path)
    assert main(_frontend_argv("compile", files)) == 0
    capsys.readouterr()
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ), patch.object(sys, "argv", ["orchestrator", *_frontend_argv("run", files)]):
        assert main(_frontend_argv("run", files)) == 0

    run_root = next((tmp_path / ".orchestrate" / "runs").iterdir())
    run_id = run_root.name
    request = get_human_input(run_root)
    assert request is not None and request["status"] == "pending"
    assert main(["input", "answer", run_id, request["request_id"], "--text", "yes"]) == 0
    capsys.readouterr()

    class AfterConsume(BaseException):
        pass

    def interrupt(self, state, step_name, step, result):
        if step_name.endswith("request_input"):
            raise AfterConsume

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(ProviderExecutor, "execute", execute), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt,
    ), pytest.raises(AfterConsume):
        main(["resume", run_id, "--retry-delay", "0"])

    consumed = get_human_input(run_root)
    assert consumed is not None
    assert consumed["request_id"] == request["request_id"]
    assert consumed["status"] == "consumed"

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ):
        status = main(["resume", run_id, "--retry-delay", "0"])
    assert status == 1
    resumed_state = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    assert resumed_state["status"] == "failed"
    assert calls == ["fail"]
    reply_rows = _persisted_step_rows(resumed_state, request["runtime_step_id"])
    assert len(reply_rows) == 1
    assert reply_rows[0]["visit_count"] == 1
    assert reply_rows[0]["artifacts"] == {"variant": "ANSWERED", "text": "yes"}
    resumed_request = get_human_input(run_root)
    assert resumed_request is not None
    assert resumed_request["request_id"] == request["request_id"]
    assert resumed_request["status"] == "consumed"
