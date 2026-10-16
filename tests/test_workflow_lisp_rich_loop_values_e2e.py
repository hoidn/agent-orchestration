"""Public rich-loop value fixtures for target-2.29."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import PreparedProviderPolicy
from types import SimpleNamespace
from types import SimpleNamespace

import pytest


from orchestrator.providers.types import PreparedProviderPolicy
from orchestrator.workflow_lisp.contracts import FlattenedContractField
from orchestrator.workflow_lisp.loops import _placeholder_literals


_HELPER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
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
  (:target-dsl "2.35")
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
  (:target-dsl "2.35")
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
  (:target-dsl "2.35")
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
            env=dict(kwargs.get("env") or {}), input_mode="stdin", metadata_mode=None,
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

    from orchestrator.cli.commands.run import run_workflow
    from tests.test_workflow_evaluated_cli import _run_args
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo
    args = _run_args(files, input_file=inputs if "inputs" in locals() else None)
    args.entry_workflow = "rich_loop_values/entry::run"
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(ProviderExecutor, "execute", execute):
        result = run_workflow(args)
    assert calls == ["seed"]
    assert result.run_root is not None
    authority = load_run_authority(result.run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert result.exit_code == 0
    assert snapshot.terminal.data["value"] == {'remaining': [{'id': 'two'}], 'round': 1, 'status': 'exhausted'}


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
            env=dict(kwargs.get("env") or {}), input_mode="stdin", metadata_mode=None,
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

    from orchestrator.cli.commands.run import run_workflow
    from tests.test_workflow_evaluated_cli import _run_args
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo
    args = _run_args(files, input_file=inputs if "inputs" in locals() else None)
    args.entry_workflow = "rich_loop_values/entry::run"
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(ProviderExecutor, "execute", execute):
        result = run_workflow(args)
    assert calls == ["seed"]
    assert result.run_root is not None
    authority = load_run_authority(result.run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert result.exit_code == 0
    assert snapshot.terminal.data["value"] == [{'variant': 'PENDING', 'task': {'id': 'one'}}, {'variant': 'BLOCKED', 'reason': 'unavailable'}]


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
            env=dict(kwargs.get("env") or {}), input_mode="stdin", metadata_mode=None,
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

    from orchestrator.cli.commands.run import run_workflow
    from tests.test_workflow_evaluated_cli import _run_args
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo
    args = _run_args(files, input_file=inputs if "inputs" in locals() else None)
    args.entry_workflow = "rich_loop_values/entry::run"
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(ProviderExecutor, "execute", execute):
        result = run_workflow(args)
    assert calls == ["seed"]
    assert result.run_root is not None
    authority = load_run_authority(result.run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert result.exit_code == 1
    assert not snapshot.active_commits
    assert snapshot.terminal.data["outcome"] == "failed"
    assert snapshot.terminal.data["code"] == "provider_result_invalid"




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
            env=dict(kwargs.get("env") or {}), input_mode="stdin", metadata_mode=None,
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

    from orchestrator.cli.commands.run import run_workflow
    from tests.test_workflow_evaluated_cli import _run_args
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo
    args = _run_args(files, input_file=inputs if "inputs" in locals() else None)
    args.entry_workflow = "rich_loop_values/entry::run"
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(ProviderExecutor, "execute", execute):
        result = run_workflow(args)
    assert calls == ["seed"]
    assert result.run_root is not None
    authority = load_run_authority(result.run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert result.exit_code == 0
    assert snapshot.terminal.data["value"] == {"remaining": [{"id": "three"}], "round": 2, "status": expected_status}
