from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import textwrap

import pytest

from orchestrator.contracts.output_contract import OutputContractError
from orchestrator.workflow.pure_expr import PureExprEvaluationError
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.syntax import EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION


@dataclass
class _Owners:
    workspace_files: WorkspaceFiles
    run_files: WorkspaceFiles
    attempt_files: WorkspaceFiles


@pytest.fixture
def owners(tmp_path: Path):
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    workspace.mkdir()
    state.mkdir()
    workspace_files = WorkspaceFiles(workspace)
    run_files = WorkspaceFiles(state)
    run_files.ensure_directory("effects/e1")
    attempt_files = run_files.subroot("effects/e1")
    try:
        yield _Owners(workspace_files, run_files, attempt_files)
    finally:
        attempt_files.close()
        run_files.close()
        workspace_files.close()


def _command_api():
    return importlib.import_module("orchestrator.workflow.evaluated.commands")


def _checked_command(
    workspace: Path,
    *,
    return_type: str,
    declarations: str = "",
    stable_command: tuple[str, ...] = ("python", "probe.py"),
    closure: tuple[str, ...] = (),
    origin: str = "workspace",
) -> dict:
    source_path = workspace / "performer_probe.orc"
    source_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule performer_probe)
  (export run)
  {declarations}
  (defworkflow run () -> {return_type}
    (command-result fetch
      :argv ({" ".join(json.dumps(token) for token in stable_command)})
      :returns {return_type})))
''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        source_path,
        entry_workflow="performer_probe::run",
        source_roots=(workspace,),
        command_boundaries={
            "fetch": ExternalToolBinding(
                name="fetch",
                stable_command=stable_command,
                closure=closure,
            )
        },
        workspace_root=workspace,
    )
    if origin != "workspace":
        configuration = dict(typed.configuration_bindings)
        used_origins = dict(configuration["used_command_boundary_origins"])
        module_origins = dict(used_origins[typed.entry_module])
        module_origins["fetch"] = origin
        used_origins[typed.entry_module] = module_origins
        configuration["used_command_boundary_origins"] = used_origins
        boundary_origins = dict(typed.command_boundary_origins)
        boundary_origins["fetch"] = origin
        typed = replace(
            typed,
            command_boundary_origins=boundary_origins,
            configuration_bindings=configuration,
        )
    built = build_closed_program(typed)
    checked = ClosedProgram.from_artifact(built.artifact())
    effects = [
        row
        for row in _walk(checked.tree)
        if row.get("k") == "perform" and row.get("class") == "command"
    ]
    assert len(effects) == 1
    if closure:
        assert {row["base"] for row in effects[0]["closure"]} == {origin}
    return effects[0]


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _script(owners: _Owners, source: str, name: str = "probe.py") -> Path:
    path = owners.workspace_files.workspace / name
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def _result_writer(owners: _Owners) -> Path:
    return _script(
        owners,
        '''
        import os, sys
        from pathlib import Path
        Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(sys.argv[1].encode())
        ''',
    )


def _argv(script: Path, *arguments: str) -> list[str]:
    # This is the caller's final argv: argv[0] is already C3-resolved.
    return [sys.executable, script.name, *arguments]


def _perform(api, owners: _Owners, node: dict, argv: list[str], **options):
    return api.perform_command(
        node,
        argv,
        attempt_files=owners.attempt_files,
        workspace_files=owners.workspace_files,
        **options,
    )


def _workspace_relative(owners: _Owners, leaf: str) -> str:
    relative = os.path.relpath(
        owners.attempt_files.workspace / leaf,
        owners.workspace_files.workspace,
    )
    return Path(relative).as_posix()


def test_dispatches_once_projects_declared_record_and_hashes_one_attempt_read(
    owners: _Owners,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = _checked_command(
        owners.workspace_files.workspace,
        declarations="(defrecord Report (count Int) (label String))",
        return_type="Report",
    )
    payload = b'{"count":7,"label":"ready","undeclared":{"keep":false}}'
    script = _script(
        owners,
        '''
        import os, sys
        from pathlib import Path
        Path("dispatches.txt").open("ab").write(b"x")
        Path("launch.json").write_text(
            __import__("json").dumps({"argv": sys.argv[1:], "result_path": os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], "cwd": os.getcwd(), "bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE")}),
            encoding="utf-8",
        )
        Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(sys.argv[1].encode())
        ''',
    )
    final_argv = _argv(script, payload.decode())
    expected_path = _workspace_relative(owners, "result.json")
    original_read = owners.attempt_files.read
    reads: list[str] = []

    def counted_read(path):
        reads.append(os.fspath(path))
        return original_read(path)

    monkeypatch.setattr(owners.attempt_files, "read", counted_read)

    result, result_digest = _perform(_command_api(), owners, node, final_argv)

    assert result.json_value() == {"count": 7, "label": "ready"}
    assert result.committed_result_path == expected_path
    assert result_digest == "sha256:" + hashlib.sha256(payload).hexdigest()
    assert reads == ["result.json"]
    assert owners.attempt_files.exists("result.json")
    assert not owners.workspace_files.exists("result.json")
    assert owners.attempt_files.read("stdout.txt") == b""
    assert owners.attempt_files.read("stderr.txt") == b""
    assert (owners.workspace_files.workspace / "dispatches.txt").read_bytes() == b"x"
    launched = json.loads((owners.workspace_files.workspace / "launch.json").read_text())
    assert launched == {
        "argv": [payload.decode()],
        "result_path": expected_path,
        "cwd": str(owners.workspace_files.workspace),
        "bytecode": "1",
    }


def test_nonzero_exit_keeps_logs_but_rejects_result(owners: _Owners) -> None:
    api = _command_api()
    node = _checked_command(
        owners.workspace_files.workspace,
        declarations="(defrecord Report (count Int))",
        return_type="Report",
    )
    script = _script(
        owners,
        '''
        import os, sys
        from pathlib import Path
        Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"count":8}', encoding="utf-8")
        sys.stdout.buffer.write(b"nonzero stdout")
        sys.stderr.buffer.write(b"nonzero stderr")
        raise SystemExit(17)
        ''',
    )

    with pytest.raises(api.CommandPerformerError) as excinfo:
        _perform(api, owners, node, _argv(script))
    assert excinfo.value.code == "command_exit_nonzero"
    assert excinfo.value.exit_info == {"exit_code": 17, "error": None}

    assert owners.attempt_files.read("result.json") == b'{"count":8}'
    assert owners.attempt_files.read("stdout.txt") == b"nonzero stdout"
    assert owners.attempt_files.read("stderr.txt") == b"nonzero stderr"


def test_timeout_persists_partial_streams(owners: _Owners) -> None:
    api = _command_api()
    node = _checked_command(
        owners.workspace_files.workspace,
        declarations="(defrecord Report (count Int))",
        return_type="Report",
    )
    script = _script(
        owners,
        '''
        import sys, time
        sys.stdout.buffer.write(b"started\\n")
        sys.stdout.flush()
        time.sleep(5)
        ''',
    )

    with pytest.raises(api.CommandPerformerError) as excinfo:
        _perform(api, owners, node, _argv(script), timeout_sec=1)
    assert excinfo.value.code == "command_timeout"
    assert excinfo.value.exit_info["exit_code"] == 124
    assert excinfo.value.exit_info["error"] == {
        "type": "timeout",
        "message": "Command timed out after 1 seconds",
        "context": {"timeout_sec": 1},
    }

    assert owners.attempt_files.read("stdout.txt") == b"started\n"
    assert owners.attempt_files.read("stderr.txt") == b""
    assert not owners.attempt_files.exists("result.json")


def test_missing_result_does_not_fall_back_to_stdout(owners: _Owners) -> None:
    api = _command_api()
    node = _checked_command(
        owners.workspace_files.workspace,
        declarations="(defrecord Report (count Int))",
        return_type="Report",
    )
    script = _script(
        owners,
        '''
        print('{"count":91}')
        ''',
    )

    with pytest.raises(api.CommandPerformerError) as excinfo:
        _perform(api, owners, node, _argv(script))

    assert excinfo.value.code == "command_result_missing"
    assert owners.attempt_files.read("stdout.txt") == b'{"count":91}\n'
    assert owners.attempt_files.read("stderr.txt") == b""
    assert not owners.attempt_files.exists("result.json")


@pytest.mark.parametrize(
    ("payload", "expected", "invalid"),
    [
        ('{"variant":"Ready","count":3,"undeclared":true}', {"variant": "Ready", "count": 3}, False),
        ('{"variant":"Ready","count":3,"reason":"inactive"}', None, True),
    ],
)
def test_top_level_union_projects_only_selected_variant_fields(
    owners: _Owners, payload: str, expected: dict | None, invalid: bool,
) -> None:
    api = _command_api()
    node = _checked_command(
        owners.workspace_files.workspace,
        declarations="(defunion Choice (Ready (count Int)) (Skipped (reason String)))",
        return_type="Choice",
    )
    script = _result_writer(owners)
    if invalid:
        with pytest.raises(OutputContractError) as excinfo:
            _perform(api, owners, node, _argv(script, payload))
        assert any(row["type"] == "variant_forbidden_field_present" for row in excinfo.value.violations)
    else:
        result, _digest = _perform(api, owners, node, _argv(script, payload))
        assert result.json_value() == expected


def test_value_result_preserves_arbitrary_json_object_keys(
    owners: _Owners,
) -> None:
    node = _checked_command(
        owners.workspace_files.workspace,
        return_type="Value",
    )
    payload = b'{"__result__":{"inside":true},"variant":"opaque","extra":[1,null]}'
    script = _result_writer(owners)
    result, _digest = _perform(_command_api(), owners, node, _argv(script, payload.decode()))

    assert result.json_value() == json.loads(payload)


def test_relpath_is_validated_against_workspace_when_attempt_root_is_external(
    owners: _Owners,
) -> None:
    node = _checked_command(
        owners.workspace_files.workspace,
        declarations='(defpath ArtifactPath :kind relpath :under "artifacts" :must-exist true)',
        return_type="ArtifactPath",
    )
    (owners.workspace_files.workspace / "artifacts").mkdir()
    (owners.workspace_files.workspace / "artifacts" / "report.txt").write_text("ok")
    expected_path = _workspace_relative(owners, "result.json")
    payload = b'"artifacts/report.txt"'
    script = _result_writer(owners)
    result, _digest = _perform(_command_api(), owners, node, _argv(script, payload.decode()))

    assert result.json_value() == "artifacts/report.txt"
    assert result.committed_result_path == expected_path
    assert Path(expected_path).is_absolute() is False
    assert ".." in Path(expected_path).parts
    assert owners.attempt_files.exists("result.json")
    assert not owners.workspace_files.exists("result.json")


def test_path_under_external_run_root_is_rejected_with_request_path(owners: _Owners) -> None:
    api = _command_api()
    node = _checked_command(
        owners.workspace_files.workspace,
        declarations='(defpath ArtifactPath :kind relpath :under "artifacts" :must-exist true)',
        return_type="ArtifactPath",
    )
    owners.run_files.ensure_directory("artifacts")
    owners.run_files.create("artifacts/report.txt", b"run-only")
    expected_path = _workspace_relative(owners, "result.json")
    payload = b'"artifacts/report.txt"'
    script = _result_writer(owners)

    with pytest.raises(OutputContractError) as excinfo:
        _perform(api, owners, node, _argv(script, payload.decode()))

    assert any(
        violation["context"].get("path") == expected_path
        for violation in excinfo.value.violations
    )
    assert owners.run_files.read("artifacts/report.txt") == b"run-only"


def test_input_document_is_created_exclusively_and_is_read_by_the_real_command(
    owners: _Owners,
) -> None:
    node = _checked_command(
        owners.workspace_files.workspace,
        return_type="Value",
    )
    document = b'{"answer":42}'
    input_path = _workspace_relative(owners, "inputs.json")
    script = _script(
        owners,
        '''
        import os, sys
        from pathlib import Path
        raw = Path(sys.argv[1]).read_bytes()
        Path("dispatches.txt").open("ab").write(b"x")
        Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(raw)
        ''',
    )
    final_argv = _argv(script, input_path)
    api = _command_api()

    result, _digest = _perform(api, owners, node, final_argv, input_document=document)

    assert result.json_value() == {"answer": 42}
    assert owners.attempt_files.read("inputs.json") == document
    assert (owners.workspace_files.workspace / "dispatches.txt").read_bytes() == b"x"
    assert len(final_argv) == 3 and final_argv[-1] == input_path

    with pytest.raises(FileExistsError):
        _perform(api, owners, node, final_argv, input_document=document)

    assert (owners.workspace_files.workspace / "dispatches.txt").read_bytes() == b"x"
    assert owners.attempt_files.read("inputs.json") == document


@pytest.mark.parametrize(
    ("shape", "payload", "expected"),
    [
        ("record", '{"empty":{},"n":7,"extra":true}', {"empty": {}, "n": 7}),
        ("record", '{"n":7}', None),
        ("record", '{"empty":0,"n":7}', None),
        ("nested", '{"box":{"empty":{},"extra":true},"n":7}', {"box": {"empty": {}}, "n": 7}),
        ("nested", '{"n":7}', None),
        ("nested", '{"box":[],"n":7}', None),
        ("empty", '{"extra":true}', {}),
        ("empty", 'null', None),
        ("union", '{"variant":"Ready","empty":{},"shared":{},"n":7,"extra":true}', {"variant": "Ready", "empty": {}, "shared": {}, "n": 7}),
        ("union", '{"variant":"Ready","shared":{},"n":7}', None),
        ("union", '{"variant":"Ready","empty":0,"shared":{},"n":7}', None),
        ("union", '{"variant":"Ready","empty":{},"n":7}', None),
        ("union", '{"variant":"Ready","empty":{},"shared":[],"n":7}', None),
        ("union", '{"variant":"Skipped","shared":{},"reason":"later"}', {"variant": "Skipped", "shared": {}, "reason": "later"}),
    ],
)
def test_empty_record_containers_follow_checked_record_and_active_variant(
    owners: _Owners, shape: str, payload: str, expected: dict | None,
) -> None:
    declarations, result_type = {
        "record": ("(defrecord Report (empty Empty) (n Int))", "Report"),
        "nested": ("(defrecord Box (empty Empty)) (defrecord Report (box Box) (n Int))", "Report"),
        "empty": ("", "Empty"),
        "union": ("(defunion Choice (Ready (empty Empty) (shared Empty) (n Int)) (Skipped (shared Empty) (reason String)))", "Choice"),
    }[shape]
    node = _checked_command(
        owners.workspace_files.workspace,
        declarations="(defrecord Empty) " + declarations,
        return_type=result_type,
    )
    script = _result_writer(owners)
    api = _command_api()
    if expected is None:
        with pytest.raises((api.CommandPerformerError, PureExprEvaluationError)):
            _perform(api, owners, node, _argv(script, payload))
    else:
        value, digest = _perform(api, owners, node, _argv(script, payload))
        assert value.json_value() == expected
        assert digest == "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    assert owners.attempt_files.read("result.json") == payload.encode()
