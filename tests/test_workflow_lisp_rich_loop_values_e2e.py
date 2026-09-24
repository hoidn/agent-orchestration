"""Public rich-loop value fixtures for target-2.29."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import PreparedProviderPolicy
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
from orchestrator.workflow_lisp.contracts import FlattenedContractField
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.loops import _placeholder_literals


_HELPER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defmodule rich_loop_values/helper)
  (export Task Progress Report advance)
  (defrecord Task (id String))
  (defrecord Progress (remaining List[Task]) (round Int))
  (defrecord Report (remaining List[Task]) (round Int) (status String))
  (defproc advance ((state Progress)) -> Progress
    :effects ()
    :lowering inline
    (record-update state
      :remaining (list/rest state.remaining)
      :round (+ state.round 1))))
"""


_ENTRY_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defmodule rich_loop_values/entry)
  (import rich_loop_values/helper :only (Task Progress Report advance))
  (export run)
  (defworkflow run () -> Report
    (let* ((items
             (provider-result providers.seed
               :prompt prompts.seed
               :inputs ()
               :returns List[Task])))
      (loop/recur :max 1
        :state (record Progress :remaining items :round 0)
        :on-exhausted
          (record Report
            :remaining state.remaining
            :round state.round
            :status "exhausted")
        (fn (state)
          (if (= state.round -1)
            (done (record Report
                    :remaining state.remaining
                    :round state.round
                    :status "done"))
            (let* ((next (advance state)))
              (continue next))))))))
"""


_MULTI_ITERATION_ENTRY_SOURCE = _ENTRY_SOURCE.replace(
    "(defworkflow run () -> Report",
    "(defworkflow run ((finish Bool)) -> Report",
).replace(
    ":max 1",
    ":max 3",
).replace(
    """        (fn (state)
          (if (= state.round -1)
            (done (record Report
                    :remaining state.remaining
                    :round state.round
                    :status \"done\"))
            (let* ((next (advance state)))
              (continue next))))))))
""",
    """        (fn (state)
          (if (= state.round 2)
            (if finish
              (done (record Report
                      :remaining state.remaining
                      :round state.round
                      :status \"done\"))
              (continue state))
            (let* ((next (advance state)))
              (continue next))))))))
""",
)


_ROOT_LIST_ENTRY_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defmodule rich_loop_values/entry)
  (import rich_loop_values/helper :only (Task Report))
  (export run)
  (defworkflow run ((finish Bool)) -> Report
    (let* ((items
             (provider-result providers.seed
               :prompt prompts.seed
               :inputs ()
               :returns List[Task])))
      (loop/recur :max 3
        :state items
        :on-exhausted
          (record Report :remaining state :round 3 :status "exhausted")
        (fn (state)
          (if (= (list/length state) 1)
            (if finish
              (done (record Report
                      :remaining state :round 2 :status "done"))
              (continue (list/rest state)))
            (continue (list/rest state))))))))
"""


_ROOT_LIST_UNION_ENTRY_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.29")
  (defmodule rich_loop_values/entry)
  (import rich_loop_values/helper :only (Task))
  (export run)
  (defunion TaskOutcome
    (PENDING (task Task))
    (BLOCKED (reason String)))
  (defworkflow run () -> List[TaskOutcome]
    (let* ((items
             (provider-result providers.seed
               :prompt prompts.seed
               :inputs ()
               :returns List[TaskOutcome])))
      (loop/recur :max 1 :state items :on-exhausted state
        (fn (state)
          (if (list/empty? state) (done state) (continue state)))))))
"""


class _PostCommitInterruption(BaseException):
    pass


def _write_fixture(
    workspace: Path,
    *,
    entry_source: str = _ENTRY_SOURCE,
) -> dict[str, Path]:
    helper = workspace / "rich_loop_values" / "helper.orc"
    helper.parent.mkdir()
    helper.write_text(_HELPER_SOURCE, encoding="utf-8")
    source = helper.with_name("entry.orc")
    source.write_text(entry_source, encoding="utf-8")
    prompts = helper.parent / "prompts"
    prompts.mkdir()
    (prompts / "seed.md").write_text("seed\n", encoding="utf-8")
    providers = workspace / "providers.json"
    providers.write_text(json.dumps({"providers.seed": "seed"}), encoding="utf-8")
    prompt_externs = workspace / "prompts.json"
    prompt_externs.write_text(
        json.dumps({"prompts.seed": "prompts/seed.md"}),
        encoding="utf-8",
    )
    return {
        "source": source,
        "source_root": workspace,
        "providers": providers,
        "prompts": prompt_externs,
    }


def _build_request(workspace: Path, files: dict[str, Path]) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=files["source"],
        source_roots=(workspace,),
        entry_workflow="run",
        provider_externs_path=files["providers"],
        prompt_externs_path=files["prompts"],
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=True,
        workspace_root=workspace,
    )


def _run_args(files: dict[str, Path], *, input_file: Path | None = None) -> Namespace:
    return Namespace(
        workflow=str(files["source"]), context=None, context_file=None, input=[], input_file=str(input_file) if input_file else None,
        clean_processed=False, archive_processed=None, debug=False, stream_output=False,
        dry_run=False, backup_state=False, state_dir=None, on_error="stop", max_retries=0,
        retry_delay=0, quiet=True, verbose=False, log_level="error", step_summaries=False,
        summary_mode=None, summary_provider="claude_sonnet_summary", summary_timeout_sec=120,
        summary_max_input_chars=12000, summary_profile=None, live_agent_notes=False,
        live_agent_note_provider=None, live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30, live_agent_note_max_tail_chars=6000,
        entry_workflow="run", source_root=[str(files["source_root"])],
        provider_externs_file=str(files["providers"]), prompt_externs_file=str(files["prompts"]),
        imported_workflow_bundles_file=None, command_boundaries_file=None, emit_debug_yaml=True,
    )


def _run_argv(files: dict[str, Path]) -> list[str]:
    return [
        "orchestrator", "run", str(files["source"]), "--source-root", str(files["source_root"]),
        "--entry-workflow", "run", "--provider-externs-file", str(files["providers"]),
        "--prompt-externs-file", str(files["prompts"]), "--emit-debug-yaml",
    ]


def test_imported_record_update_preserves_provider_fed_rich_loop_state(
    tmp_path: Path,
) -> None:
    """The imported updater is a normal bound loop value, not a caller workaround."""

    files = _write_fixture(tmp_path)

    bundle = build_frontend_bundle(_build_request(tmp_path, files)).validated_bundle

    assert any(step.provider == "seed" for step in bundle.surface.steps)
    assert not any(step.name.endswith("__exhausted_placeholders") for step in bundle.surface.steps)


def test_imported_record_update_supports_two_committed_rich_iterations(
    tmp_path: Path,
) -> None:
    """A done/exhausted choice observes the state after two helper updates."""

    files = _write_fixture(tmp_path, entry_source=_MULTI_ITERATION_ENTRY_SOURCE)

    bundle = build_frontend_bundle(_build_request(tmp_path, files)).validated_bundle

    assert any(step.provider == "seed" for step in bundle.surface.steps)


def test_imported_record_update_rich_loop_remains_refused_before_target_229(
    tmp_path: Path,
) -> None:
    files = _write_fixture(tmp_path, entry_source=_ENTRY_SOURCE.replace('"2.29"', '"2.28"'))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(_build_request(tmp_path, files))

    assert excinfo.value.diagnostics[0].code == "loop_recur_state_type_invalid"


def test_loop_placeholders_keep_optional_and_map_contract_values() -> None:
    fields = (
        FlattenedContractField("maybe", ("result", "maybe"), {"type": "optional"}),
        FlattenedContractField("labels", ("result", "labels"), {"type": "map"}),
    )

    assert _placeholder_literals(fields) == {"maybe": None, "labels": {}}


def test_public_run_keeps_provider_tasks_through_imported_loop_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public executor carries provider tasks through the imported updater."""

    files = _write_fixture(tmp_path)
    calls: list[str] = []

    def prepare(_self, provider_name, *_args, **kwargs):
        calls.append(provider_name)
        prompt = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            provider_name=provider_name, prompt=prompt, prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name, model=None, effort=None,
                timeout_sec=kwargs.get("timeout_sec"), input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}), input_mode="stdin",
        ), None

    def execute(_self, invocation, **_kwargs):
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps([{"id": "one"}, {"id": "two"}]) + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False, raw_stdout=None,
            normalized_stdout=None, provider_session=None,
        )

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ), patch.object(sys, "argv", _run_argv(files)):
        result = run_workflow(_run_args(files))

    assert result.exit_code == 0
    assert calls == ["seed"]
    assert result.workflow_outputs["return__remaining"] == ({"id": "two"},)
    assert result.workflow_outputs["return__round"] == 1
    assert result.workflow_outputs["return__status"] == "exhausted"


def test_public_run_carries_provider_list_of_unions_through_root_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider List[union] remains a root loop value at the public boundary."""

    files = _write_fixture(tmp_path, entry_source=_ROOT_LIST_UNION_ENTRY_SOURCE)
    calls: list[str] = []

    def prepare(_self, provider_name, *_args, **kwargs):
        calls.append(provider_name)
        prompt = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            provider_name=provider_name, prompt=prompt, prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name, model=None, effort=None,
                timeout_sec=kwargs.get("timeout_sec"), input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}), input_mode="stdin",
        ), None

    def execute(_self, invocation, **_kwargs):
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([
                {"variant": "PENDING", "task": {"id": "one"}},
                {"variant": "BLOCKED", "reason": "unavailable"},
            ]) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False, raw_stdout=None,
            normalized_stdout=None, provider_session=None,
        )

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ), patch.object(sys, "argv", _run_argv(files)):
        result = run_workflow(_run_args(files))

    assert result.exit_code == 0
    assert calls == ["seed"]
    assert result.workflow_outputs["__result__"] == (
        {"variant": "PENDING", "task": {"id": "one"}},
        {"variant": "BLOCKED", "reason": "unavailable"},
    )


def test_public_run_rejects_malformed_provider_list_of_unions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider data missing a union tag cannot enter the root loop state."""

    files = _write_fixture(tmp_path, entry_source=_ROOT_LIST_UNION_ENTRY_SOURCE)
    calls: list[str] = []

    def prepare(_self, provider_name, *_args, **kwargs):
        calls.append(provider_name)
        prompt = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            provider_name=provider_name, prompt=prompt, prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name, model=None, effort=None,
                timeout_sec=kwargs.get("timeout_sec"), input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}), input_mode="stdin",
        ), None

    def execute(_self, invocation, **_kwargs):
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([{"task": {"id": "one"}}]) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False, raw_stdout=None,
            normalized_stdout=None, provider_session=None,
        )

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ), patch.object(sys, "argv", _run_argv(files)):
        result = run_workflow(_run_args(files))

    assert result.exit_code == 1
    assert calls == ["seed"]
    assert not result.workflow_outputs


def test_public_run_does_not_treat_a_failed_iteration_as_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-commit iteration failure cannot publish the exhaustion output."""

    files = _write_fixture(tmp_path, entry_source=_MULTI_ITERATION_ENTRY_SOURCE)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"finish": False}), encoding="utf-8")

    def prepare(_self, provider_name, *_args, **kwargs):
        prompt = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            provider_name=provider_name, prompt=prompt, prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name, model=None, effort=None,
                timeout_sec=kwargs.get("timeout_sec"), input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}), input_mode="stdin",
        ), None

    def execute(_self, invocation, **_kwargs):
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([{"id": "one"}, {"id": "two"}, {"id": "three"}]) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False, raw_stdout=None,
            normalized_stdout=None, provider_session=None,
        )

    original_hook = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_repeat_until_commit

    def fail_second_iteration(self, step, progress):
        original_hook(self, step, progress)
        if progress.get("current_iteration") == 1:
            raise RuntimeError("test iteration failure")

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_repeat_until_commit",
        fail_second_iteration,
    ), patch.object(sys, "argv", _run_argv(files)):
        result = run_workflow(_run_args(files, input_file=inputs))

    assert result.exit_code == 1
    assert not result.workflow_outputs


@pytest.mark.parametrize("finish, expected_status", [(True, "done"), (False, "exhausted")])
def test_public_run_preserves_rich_state_across_two_imported_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finish: bool, expected_status: str,
) -> None:
    """Both terminal paths observe the state produced by two imported updates."""

    files = _write_fixture(tmp_path, entry_source=_MULTI_ITERATION_ENTRY_SOURCE)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"finish": finish}), encoding="utf-8")
    calls: list[str] = []

    def prepare(_self, provider_name, *_args, **kwargs):
        calls.append(provider_name)
        prompt = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            provider_name=provider_name, prompt=prompt, prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name, model=None, effort=None,
                timeout_sec=kwargs.get("timeout_sec"), input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}), input_mode="stdin",
        ), None

    def execute(_self, invocation, **_kwargs):
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([{"id": "one"}, {"id": "two"}, {"id": "three"}]) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False, raw_stdout=None,
            normalized_stdout=None, provider_session=None,
        )

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ), patch.object(sys, "argv", ["orchestrator", "run", str(files["source"])]):
        result = run_workflow(_run_args(files, input_file=inputs))

    assert result.exit_code == 0
    assert calls == ["seed"]
    assert result.workflow_outputs["return__remaining"] == ({"id": "three"},)
    assert result.workflow_outputs["return__round"] == 2
    assert result.workflow_outputs["return__status"] == expected_status


@pytest.mark.parametrize(
    ("entry_source", "finish", "expected_outputs"),
    [
        (
            _MULTI_ITERATION_ENTRY_SOURCE,
            False,
            {
                "return__remaining": [{"id": "three"}],
                "return__round": 2,
                "return__status": "exhausted",
            },
        ),
        (
            _ROOT_LIST_ENTRY_SOURCE,
            True,
            {
                "return__remaining": [{"id": "three"}],
                "return__round": 2,
                "return__status": "done",
            },
        ),
    ],
    ids=["record-state-exhaustion", "root-list-done"],
)
def test_public_resume_keeps_two_committed_rich_updates_without_replaying_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_source: str,
    finish: bool,
    expected_outputs: dict[str, object],
) -> None:
    """Resume preserves root and record rich state without replaying seed."""

    files = _write_fixture(tmp_path, entry_source=entry_source)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"finish": finish}), encoding="utf-8")
    calls: list[str] = []

    def prepare(_self, provider_name, *_args, **kwargs):
        calls.append(provider_name)
        prompt = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            provider_name=provider_name, prompt=prompt, prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name, model=None, effort=None,
                timeout_sec=kwargs.get("timeout_sec"), input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}), input_mode="stdin",
        ), None

    def execute(_self, invocation, **_kwargs):
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([{"id": "one"}, {"id": "two"}, {"id": "three"}]) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False, raw_stdout=None,
            normalized_stdout=None, provider_session=None,
        )

    original_hook = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_repeat_until_commit
    interrupted = False

    def interrupt_after_second_iteration(self, step, progress):
        nonlocal interrupted
        original_hook(self, step, progress)
        if progress.get("current_iteration") == 1 and not interrupted:
            interrupted = True
            raise _PostCommitInterruption

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_repeat_until_commit",
        interrupt_after_second_iteration,
    ), patch.object(sys, "argv", _run_argv(files)):
        with pytest.raises(_PostCommitInterruption):
            run_workflow(_run_args(files, input_file=inputs))

    run_id = next((tmp_path / ".orchestrate" / "runs").iterdir()).name
    assert calls == ["seed"]
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute,
    ):
        assert resume_workflow(run_id=run_id, retry_delay_ms=0) == 0

    assert calls == ["seed"]
    resumed = json.loads(
        (tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8")
    )
    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == expected_outputs

    clean_workspace = tmp_path / "clean"
    clean_workspace.mkdir()
    clean_files = _write_fixture(clean_workspace, entry_source=entry_source)
    clean_inputs = clean_workspace / "inputs.json"
    clean_inputs.write_text(json.dumps({"finish": finish}), encoding="utf-8")
    with monkeypatch.context() as clean_patch:
        clean_patch.chdir(clean_workspace)
        with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
            ProviderExecutor, "execute", execute,
        ), patch.object(sys, "argv", _run_argv(clean_files)):
            clean = run_workflow(_run_args(clean_files, input_file=clean_inputs))

    assert clean.exit_code == 0
    assert [dict(item) for item in clean.workflow_outputs["return__remaining"]] == expected_outputs["return__remaining"]
    assert clean.workflow_outputs["return__round"] == expected_outputs["return__round"]
    assert clean.workflow_outputs["return__status"] == expected_outputs["return__status"]
