"""Public direct provider execution for the dynamic Workflow Lisp profile."""

from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import shutil
import sys

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow.dynamic.state import load_dynamic_view
from orchestrator.workflow.dynamic.runtime import execute_dynamic_run
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.dynamic.build import prepare_dynamic_program_bundle
from orchestrator.workflow_lisp.dynamic.program import DynamicProgram
from tests.test_workflow_dynamic_source import write_source


COMMAND_PROBE = "tests/fixtures/workflow_lisp/dynamic/command_probe.py"


def _source(
    tmp_path, *, raw_note=False, raw_message=False, bool_model=False,
    bad_effort=False, budget=1000,
):
    write_source(tmp_path, "old/prompts", '''
      (export Decision NotePath ReportPath review)
      (defpath NotePath :kind relpath :under "notes" :must-exist true)
      (defpath ReportPath :kind relpath :under "reports" :must-exist false)
      (defunion Decision (APPROVE (ok Bool) (score Int)) (REJECT (reason String)))
      (defprompt review
        (:fills (note :doc NotePath) (message :text) (report :path :out ReportPath))
        -> Decision "Review {message}; report: {report}")
    ''', budget=None, target="2.35")
    note_type = "Value" if raw_note else "NotePath"
    message_type = "Value" if raw_message else "String"
    model_type = "Value" if bool_model else "String"
    effort_type = "Value" if bad_effort else "String"
    return write_source(tmp_path, "demo/main", f'''
      (import old/prompts :only (Decision NotePath ReportPath review))
      (export main)
      (defrecord CommandResult (literal String) (computed String) (opaque String) (first Int) (second Int))
      (define (accept answer)
        (command-result probe
          :argv ("python" "{COMMAND_PROBE}" "finish" "approved"
            (field answer "score") "selected" 11 12)
          :returns CommandResult))
      (define (reject answer)
        (command-result probe
          :argv ("python" "{COMMAND_PROBE}" "finish" "rejected"
            (field answer "reason") "selected" 0 0)
          :returns CommandResult))
      (defworkflow main ((note {note_type}) (message {message_type})
                         (report ReportPath) (model {model_type}) (effort {effort_type}))
        -> CommandResult
        (let* ((answer (provider-result providers.review
                         :prompt (review :note note :message message :report report)
                         :model model :effort effort))
               (continuation (if (= (field answer "variant") "APPROVE") accept reject)))
          (continuation answer)))
    ''', budget=budget)


def _provider_node(tree):
    if isinstance(tree, dict):
        if tree.get("k") == "perform" and tree.get("class") == "provider":
            return tree
        for value in tree.values():
            found = _provider_node(value)
            if found is not None:
                return found
    elif isinstance(tree, list):
        for value in tree:
            found = _provider_node(value)
            if found is not None:
                return found
    return None


def _args(path, providers, commands, values):
    inputs = path.parent.parent / "inputs.json"
    inputs.write_text(json.dumps(values), encoding="utf-8")
    return create_parser().parse_args([
        "run", str(path), "--source-root", str(path.parent.parent),
        "--provider-externs-file", str(providers),
        "--command-boundaries-file", str(commands),
        "--input-file", str(inputs),
    ])


def _manifests(tmp_path):
    providers = tmp_path / "providers.json"
    providers.write_text(json.dumps({"providers.review": "codex"}), encoding="utf-8")
    commands = tmp_path / "commands.json"
    commands.write_text(json.dumps({"probe": {
        "kind": "external_tool",
        "stable_command": ["python", COMMAND_PROBE],
        "closure": [],
    }}), encoding="utf-8")
    return providers, commands


def _stage_tools(tmp_path, monkeypatch):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    provider = binary_dir / "codex"
    shutil.copyfile(Path(__file__).parent / "fixtures/workflow_lisp/dynamic/provider_probe.py", provider)
    provider.chmod(0o700)
    (tmp_path / "tests/fixtures/workflow_lisp/dynamic").mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent / "fixtures/workflow_lisp/dynamic/command_probe.py",
                    tmp_path / COMMAND_PROBE)
    monkeypatch.setenv("PATH", str(binary_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(tmp_path)


def _forbid_workflow_executor(monkeypatch):
    from orchestrator.workflow.executor import WorkflowExecutor

    def fail(*_args, **_kwargs):
        raise AssertionError("dynamic provider execution constructed WorkflowExecutor")

    monkeypatch.setattr(WorkflowExecutor, "__init__", fail)


def _values(**overrides):
    return {
        "note": "notes/input.md",
        "message": "inspect candidate",
        "report": "reports/review.md",
        "model": "local-model",
        "effort": "low",
        **overrides,
    }


def test_public_provider_selects_closure_and_runs_later_command(tmp_path, monkeypatch):
    path = _source(tmp_path, budget=37)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("IMPORTED PROMPT DOCUMENT", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, providers, commands, _values()))

    assert result.exit_code == 0
    assert result.workflow_outputs == {
        "literal": "approved", "computed": "7", "opaque": "selected",
        "first": 11, "second": 12,
    }
    event = json.loads((tmp_path / "provider_events.jsonl").read_text().splitlines()[0])
    assert "IMPORTED PROMPT DOCUMENT" in event["prompt"]
    assert "inspect candidate" in event["prompt"]
    assert event["argv"] == [
        "exec", "--model", "local-model", "--config",
        "model_reasoning_effort=low", "--dangerously-bypass-approvals-and-sandbox",
    ]
    view = load_dynamic_view(result.run_root)
    assert view["steps_used"] == 37
    assert [(row["effect_class"], row["status"]) for row in view["effects"]] == [
        ("provider", "completed"), ("command", "completed"),
    ]
    provider_attempt = result.run_root / view["effects"][0]["result_path"].rsplit("/", 1)[0]
    assert event["result_path"] == os.path.relpath(
        result.run_root / view["effects"][0]["result_path"], tmp_path,
    ).replace(os.sep, "/")
    assert (provider_attempt / "prompt.txt").read_text(encoding="utf-8") == event["prompt"]
    assert (tmp_path / "reports/review.md").read_text(encoding="utf-8") == "provider report"
    commands_seen = [json.loads(line) for line in (tmp_path / "command_events.jsonl").read_text().splitlines()]
    assert [row["action"] for row in commands_seen] == ["finish"]


def test_public_provider_resnapshots_imported_document_on_fresh_run(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    note = tmp_path / "notes/input.md"
    note.write_text("FIRST DOCUMENT SNAPSHOT", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)

    first = run_workflow(_args(path, providers, commands, _values()))
    note.write_text("SECOND DOCUMENT SNAPSHOT", encoding="utf-8")
    second = run_workflow(_args(path, providers, commands, _values()))

    assert first.exit_code == second.exit_code == 0
    assert first.run_id != second.run_id
    events = [
        json.loads(line)
        for line in (tmp_path / "provider_events.jsonl").read_text().splitlines()
    ]
    assert len(events) == 2
    assert "FIRST DOCUMENT SNAPSHOT" in events[0]["prompt"]
    assert "SECOND DOCUMENT SNAPSHOT" in events[1]["prompt"]


def test_admitted_provider_extern_alias_uses_definition_owner_binding(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("captured document", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    built = prepare_dynamic_program_bundle(FrontendBuildRequest(
        source_path=path,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        provider_externs_path=providers,
        command_boundaries_path=commands,
    ))
    tree = json.loads(built.program.artifact())
    node = _provider_node(tree["definitions"])
    assert node["provider"] == "codex"
    node["provider"] = "providers.review"
    admitted = DynamicProgram.from_artifact(json.dumps(tree))
    built = replace(built, program=admitted)

    exit_code, _run_id, run_root, outputs = execute_dynamic_run(
        built, _values(), workspace=tmp_path, workflow_path=path,
    )
    view = load_dynamic_view(run_root)

    assert exit_code == 0, view["error"]
    assert outputs == view["workflow_outputs"]
    assert [row["effect_class"] for row in view["effects"]] == ["provider", "command"]
    assert [row["status"] for row in view["effects"]] == ["completed", "completed"]
    assert (tmp_path / "provider_events.jsonl").is_file()


def test_admitted_provider_without_policy_uses_shared_empty_policy(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("captured document", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    built = prepare_dynamic_program_bundle(FrontendBuildRequest(
        source_path=path,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        provider_externs_path=providers,
        command_boundaries_path=commands,
    ))
    tree = json.loads(built.program.artifact())
    node = _provider_node(tree["definitions"])
    node["policy"] = None
    entries = tree["source_map"]["entries"]
    for pointer in list(entries):
        if "/policy/" in pointer:
            del entries[pointer]
    built = replace(built, program=DynamicProgram.from_artifact(json.dumps(tree)))

    exit_code, _run_id, run_root, outputs = execute_dynamic_run(
        built, _values(), workspace=tmp_path, workflow_path=path,
    )
    view = load_dynamic_view(run_root)

    assert exit_code == 0, view["error"]
    assert outputs == view["workflow_outputs"]
    assert [row["status"] for row in view["effects"]] == ["completed", "completed"]
    event = json.loads((tmp_path / "provider_events.jsonl").read_text().splitlines()[0])
    argv = event["argv"]
    assert argv[argv.index("--model") + 1] == "gpt-5.5"
    assert argv[argv.index("--config") + 1] == "model_reasoning_effort=high"
    assert "--dangerously-bypass-approvals-and-sandbox" in argv


def test_sourcefree_imported_provider_asset_uses_library_owner(tmp_path, monkeypatch):
    library = write_source(tmp_path, "lib/provider", '''
      (export invoke)
      (defunion Answer (APPROVE (ok Bool) (score Int)) (REJECT (reason String)))
      (define (invoke)
        (provider-result providers.review :prompt prompts.base :returns Answer))
    ''', budget=None)
    path = write_source(tmp_path, "demo/main", '''
      (import lib/provider :only (invoke))
      (export main)
      (defworkflow main () -> Value (invoke))
    ''')
    (library.parent / "prompt.md").write_text("LIBRARY ASSET SNAPSHOT", encoding="utf-8")
    (path.parent / "prompt.md").write_text("CALLER DECOY", encoding="utf-8")
    providers, _commands = _manifests(tmp_path)
    prompts = tmp_path / "prompts.json"
    prompts.write_text(json.dumps({"prompts.base": {"asset_file": "prompt.md"}}), encoding="utf-8")
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    built = prepare_dynamic_program_bundle(FrontendBuildRequest(
        source_path=path,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        provider_externs_path=providers,
        prompt_externs_path=prompts,
    ))
    node = _provider_node(json.loads(built.program.artifact())["definitions"])
    assert node["prompt_owner"] == {"asset_base": "lib", "module": "lib/provider"}
    library.unlink()
    path.unlink()

    exit_code, _run_id, run_root, outputs = execute_dynamic_run(
        built, {}, workspace=tmp_path, workflow_path=path,
    )
    view = load_dynamic_view(run_root)
    event = json.loads((tmp_path / "provider_events.jsonl").read_text().splitlines()[0])

    assert exit_code == 0, view["error"]
    assert "LIBRARY ASSET SNAPSHOT" in event["prompt"]
    assert "CALLER DECOY" not in event["prompt"]
    assert outputs == view["workflow_outputs"] == {
        "variant": "APPROVE", "ok": True, "score": 7,
    }


def test_public_provider_dryrun_never_launches_or_allocates(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("document", encoding="utf-8")
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)

    args = _args(path, providers, commands, _values())
    args.dry_run = True
    result = run_workflow(args)

    assert result.exit_code == 0
    assert not (tmp_path / "provider_events.jsonl").exists()
    assert not (tmp_path / "command_events.jsonl").exists()
    assert not (tmp_path / ".orchestrate/runs").exists()


@pytest.mark.parametrize("dry_run", [False, True])
def test_provider_without_execute_permission_refuses_before_dispatch(
    tmp_path, monkeypatch, caplog, dry_run,
):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("document", encoding="utf-8")
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    binary_dir = tmp_path / "bin"
    (binary_dir / "codex").chmod(0o600)
    for name in ("python", "python3"):
        (binary_dir / name).symlink_to(sys.executable)
    monkeypatch.setenv("PATH", str(binary_dir))
    args = _args(path, providers, commands, _values())
    args.dry_run = dry_run

    with caplog.at_level(logging.ERROR):
        result = run_workflow(args)

    assert result.exit_code == 2 and result.run_root is None
    assert "command_interpreter_missing" in caplog.text
    assert "document" not in caplog.text
    assert not (tmp_path / "provider_events.jsonl").exists()
    assert not (tmp_path / "command_events.jsonl").exists()
    assert not (tmp_path / ".orchestrate/runs").exists()


@pytest.mark.parametrize(
    ("options", "values", "expected_code"),
    [
        ({"raw_message": True}, _values(message=17), "dynamic_boundary_invalid"),
        ({"bool_model": True}, _values(model=False), "dynamic_boundary_invalid"),
        ({"bad_effort": True}, _values(effort=False), "dynamic_boundary_invalid"),
        ({"raw_note": True}, _values(note="../private.md"), "dynamic_boundary_invalid"),
    ],
    ids=("fill-type", "model-type", "effort-type", "document-path"),
)
def test_provider_fill_policy_and_path_refusals_precede_dispatch(
    tmp_path, monkeypatch, options, values, expected_code,
):
    path = _source(tmp_path, **options)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("source note", encoding="utf-8")
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, providers, commands, values))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"] == []
    assert view["error"]["code"] == expected_code
    assert not (tmp_path / "provider_events.jsonl").exists()
    assert not (tmp_path / "command_events.jsonl").exists()
    assert "PRIVATE" not in json.dumps(view["error"])


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("wrong-bool", "provider_result_invalid"),
        ("inactive-field", "provider_result_invalid"),
        ("int64-overflow", "provider_result_invalid"),
        ("missing-report", "provider_result_invalid"),
        ("missing-bundle", "provider_result_missing"),
        ("stdout-bundle", "provider_result_missing"),
    ],
)
def test_provider_failure_never_publishes_success_or_runs_next_command(
    tmp_path, monkeypatch, mode, expected_code,
):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("PRIVATE DOCUMENT", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    monkeypatch.setenv("DYNAMIC_PROVIDER_MODE", mode)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, providers, commands, _values()))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["workflow_outputs"] is None
    assert len(view["effects"]) == 1
    assert view["effects"][0]["effect_class"] == "provider"
    assert view["effects"][0]["status"] == "failed"
    assert view["error"]["code"] == expected_code
    if expected_code == "provider_result_invalid":
        assert view["error"]["metadata"]["violation_kinds"]
        assert view["error"]["metadata"]["expected_contract"]["kind"] == "union"
    assert "PRIVATE DOCUMENT" not in json.dumps(view["error"])
    assert "private-provider-stdout" not in json.dumps(view)
    assert not (tmp_path / "command_events.jsonl").exists()
