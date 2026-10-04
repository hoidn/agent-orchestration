"""Native result qualification over the shared evaluated performers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import textwrap
from dataclasses import replace

import pytest

from orchestrator.contracts.output_contract import OutputContractError
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.compiler import (
    compile_stage1_entrypoint,
    linked_module_type_environment,
)
from orchestrator.workflow_lisp.contracts import (
    derive_prompt_guided_structured_result_contract,
)
from tests.test_workflow_evaluated_commands import (
    _Owners,
    _argv,
    _checked_command,
    _script,
)
from tests.test_workflow_evaluated_providers import _fixture as _provider_fixture


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


def _whole_value_contract(
    tmp_path: Path, declarations: str, result_type: str
) -> dict:
    module = "dynamic_performer_contracts"
    source = tmp_path / f"{module}.orc"
    source.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule {module})
  {declarations})
''',
        encoding="utf-8",
    )
    linked = compile_stage1_entrypoint(source, source_roots=(tmp_path,))
    type_env = linked_module_type_environment(linked, module)
    type_ref = type_env.resolve_type(
        result_type,
        span=linked.entry_module.span,
        form_path=("workflow-lisp", result_type),
    )
    contract = derive_prompt_guided_structured_result_contract(
        type_ref,
        workflow_name="dynamic-performer",
        step_id="native-result",
        type_env=type_env,
        span=linked.entry_module.span,
        form_path=("workflow-lisp", "native-result"),
        whole_value=True,
    )
    return {"kind": contract.contract_kind, "payload": dict(contract.payload)}


def _native_node(node: dict, contract: dict) -> dict:
    return {**node, "contract": contract}


def _write_result_script(owners: _Owners) -> Path:
    return _script(
        owners,
        '''
        import os, sys
        from pathlib import Path
        Path("dispatches.txt").open("ab").write(b"x")
        Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(
            sys.argv[1].encode()
        )
        ''',
    )


def _perform_native(api, owners: _Owners, node: dict, script: Path, payload: bytes):
    return api.perform_command(
        node,
        [sys.executable, script.name, payload.decode("utf-8")],
        attempt_files=owners.attempt_files,
        workspace_files=owners.workspace_files,
        native_result=True,
    )


@pytest.mark.parametrize(
    ("declarations", "result_type", "payload", "expected"),
    (
        (
            "(defrecord Report (approved Bool) (count Int) (score Float))",
            "Report",
            b'{"approved":true,"count":7,"score":4}',
            {"approved": True, "count": 7, "score": 4.0},
        ),
        (
            "(defrecord Note (text String)) (defrecord Blocker (reason String)) "
            "(defunion Decision :forall (F B) (APPROVE (evidence F)) (BLOCKED (state B)))",
            "Decision[Note Blocker]",
            b'{"variant":"APPROVE","evidence":{"text":"accepted"}}',
            {"variant": "APPROVE", "evidence": {"text": "accepted"}},
        ),
        ("", "Bool", b"true", True),
        ("(defrecord Empty)", "Empty", b"{}", {}),
    ),
    ids=("record", "applied-union", "scalar", "empty-record"),
)
def test_native_command_returns_stage1_whole_value_once(
    tmp_path: Path,
    owners: _Owners,
    declarations: str,
    result_type: str,
    payload: bytes,
    expected: object,
) -> None:
    import orchestrator.workflow.evaluated.commands as commands

    typed_node = _checked_command(
        owners.workspace_files.workspace,
        declarations=declarations,
        return_type=result_type,
    )
    node = _native_node(
        typed_node,
        _whole_value_contract(tmp_path, declarations, result_type),
    )
    script = _write_result_script(owners)
    reads: list[str] = []
    original_read = owners.attempt_files.read

    def counted_read(path):
        reads.append(os.fspath(path))
        return original_read(path)

    owners.attempt_files.read = counted_read
    result, digest = _perform_native(commands, owners, node, script, payload)

    assert result == expected
    assert not hasattr(result, "json_value")
    assert digest == "sha256:" + hashlib.sha256(payload).hexdigest()
    assert reads == ["result.json"]
    assert (owners.workspace_files.workspace / "dispatches.txt").read_bytes() == b"x"


@pytest.mark.parametrize(
    "payload",
    (
        b'{"approved":"true","count":1,"score":2.0}',
        b'{"approved":true,"count":"1","score":2.0}',
        b'{"approved":true,"count":9223372036854775808,"score":2.0}',
        b'{"approved":true,"count":1,"score":2.0,"extra":0}',
        b'{"approved":true,"approved":false,"count":1,"score":2.0}',
        b'{"approved":true,"count":1,"score":2.0,}',
    ),
    ids=(
        "wrong-bool",
        "wrong-int",
        "int64-overflow",
        "extra-field",
        "duplicate-key",
        "malformed-json",
    ),
)
def test_native_command_strictly_rejects_invalid_root_values(
    tmp_path: Path, owners: _Owners, payload: bytes
) -> None:
    import orchestrator.workflow.evaluated.commands as commands

    declarations = "(defrecord Report (approved Bool) (count Int) (score Float))"
    typed_node = _checked_command(
        owners.workspace_files.workspace,
        declarations=declarations,
        return_type="Report",
    )
    node = _native_node(
        typed_node,
        _whole_value_contract(tmp_path, declarations, "Report"),
    )
    script = _write_result_script(owners)

    with pytest.raises(OutputContractError):
        _perform_native(commands, owners, node, script, payload)

    assert (owners.workspace_files.workspace / "dispatches.txt").read_bytes() == b"x"


@pytest.mark.parametrize("contract_shape", ("flattened", "malformed"))
def test_native_command_rejects_non_root_contract_before_dispatch(
    tmp_path: Path, owners: _Owners, contract_shape: str
) -> None:
    import orchestrator.workflow.evaluated.commands as commands

    declarations = "(defrecord Report (count Int))"
    typed_node = _checked_command(
        owners.workspace_files.workspace,
        declarations=declarations,
        return_type="Report",
    )
    node = typed_node
    if contract_shape == "malformed":
        contract = _whole_value_contract(tmp_path, declarations, "Report")
        contract["payload"]["fields"][0]["type"] = "unsupported-schema"
        node = _native_node(typed_node, contract)
    script = _write_result_script(owners)

    with pytest.raises(commands.CommandPerformerError):
        _perform_native(
            commands,
            owners,
            node,
            script,
            b'{"count":1}',
        )

    assert not (owners.workspace_files.workspace / "dispatches.txt").exists()


def test_native_applied_union_rejects_inactive_variant_field(
    tmp_path: Path, owners: _Owners
) -> None:
    import orchestrator.workflow.evaluated.commands as commands

    declarations = (
        "(defrecord Note (text String)) (defrecord Blocker (reason String)) "
        "(defunion Decision :forall (F B) (APPROVE (evidence F)) (BLOCKED (state B)))"
    )
    typed_node = _checked_command(
        owners.workspace_files.workspace,
        declarations=declarations,
        return_type="Decision[Note Blocker]",
    )
    node = _native_node(
        typed_node,
        _whole_value_contract(tmp_path, declarations, "Decision[Note Blocker]"),
    )
    script = _write_result_script(owners)

    with pytest.raises(OutputContractError):
        _perform_native(
            commands,
            owners,
            node,
            script,
            b'{"variant":"APPROVE","evidence":{"text":"ok"},"state":{"reason":"inactive"}}',
        )


def _checked_provider_effect(tmp_path: Path):
    source, _provider_config, _prompt_config, _request = _provider_fixture(
        tmp_path,
        prompt_kind="input_file",
    )
    typed = compile_typed_program(
        source,
        entry_workflow="main::run",
        source_roots=(source.parent,),
        command_boundaries={},
        provider_externs={"providers.review": "codex"},
        prompt_externs={
            "prompts.base": {"input_file": "prompt.md"},
        },
        workspace_root=tmp_path,
    )
    built = build_closed_program(typed)
    program = ClosedProgram.from_artifact(built.artifact())
    captured = {}

    def capture(node, operands, _identity, _owner, _reader):
        captured["node"] = node
        captured["operands"] = operands
        return coerce_evaluated_value({"ok": True}, node["result"])

    evaluate_closed_program(
        program,
        {"message": "typed input"},
        effect_handler=capture,
    )
    return source, captured["node"], captured["operands"]


def _native_provider_request(tmp_path: Path, source: Path, node: dict, operands):
    from orchestrator.workflow.evaluated.providers import resolve_provider_input

    declarations = "(defrecord Result (ok Bool))"
    native_node = _native_node(
        node,
        _whole_value_contract(tmp_path, declarations, "Result"),
    )
    resolved = resolve_provider_input(
        native_node,
        operands,
        workspace=tmp_path,
        reader=None,
        result_path="attempt/result.json",
    )
    return native_node, resolved


def _local_provider_script(binary: Path, *, write_report: bool) -> None:
    report_line = 'Path("report.txt").write_text("present", encoding="utf-8")' if write_report else "pass"
    binary.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            f'''\
            import os
            from pathlib import Path
            with Path("dispatches.txt").open("ab") as stream:
                stream.write(b"x")
            Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
                '{{"ok":true}}', encoding="utf-8"
            )
            {report_line}
            print("local-provider")
            '''
        ),
        encoding="utf-8",
    )
    binary.chmod(0o700)


@pytest.mark.parametrize(
    ("write_report", "expected_name", "error_fragment"),
    (
        (False, "report", "missing"),
        (True, "__result__", "disjoint"),
    ),
    ids=("required-output", "artifact-overlap"),
)
def test_native_provider_checks_required_files_and_overlap_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_report: bool,
    expected_name: str,
    error_fragment: str,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.providers.registry import ProviderRegistry
    from orchestrator.workflow.evaluated.providers import (
        ProviderPerformerError,
        perform_provider,
    )

    source, typed_node, operands = _checked_provider_effect(tmp_path)
    binary = tmp_path / "bin" / "codex"
    _local_provider_script(binary, write_report=write_report)
    monkeypatch.setenv(
        "PATH",
        str(binary.parent) + os.pathsep + os.environ["PATH"],
    )
    native_node, resolved = _native_provider_request(
        tmp_path,
        source,
        typed_node,
        operands,
    )
    resolved = replace(
        resolved,
        expected_outputs=[
            {
                "name": expected_name,
                "path": "report.txt",
                "type": "string",
                "required": True,
            }
        ],
    )
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    attempt_files = WorkspaceFiles(attempt_root)
    workspace_files = WorkspaceFiles(tmp_path)
    try:
        with pytest.raises(ProviderPerformerError) as caught:
            perform_provider(
                native_node,
                resolved,
                "effect-1",
                executor=ProviderExecutor(tmp_path, ProviderRegistry()),
                attempt_files=attempt_files,
                workspace_files=workspace_files,
                result_path="attempt/result.json",
                native_result=True,
            )
        assert error_fragment in str(caught.value).lower()
        assert (tmp_path / "dispatches.txt").read_bytes() == b"x"
    finally:
        attempt_files.close()
        workspace_files.close()


def test_native_provider_returns_root_from_plain_values_after_one_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.providers.registry import ProviderRegistry
    from orchestrator.workflow.evaluated.providers import (
        _resolve_provider_input_values,
        perform_provider,
    )

    source, typed_node, operands = _checked_provider_effect(tmp_path)
    binary = tmp_path / "bin" / "codex"
    _local_provider_script(binary, write_report=False)
    monkeypatch.setenv(
        "PATH",
        str(binary.parent) + os.pathsep + os.environ["PATH"],
    )
    native_node, resolved = _native_provider_request(
        tmp_path,
        source,
        typed_node,
        operands,
    )
    plain_values = tuple(value.json_value() for value in operands)
    resolved_from_plain_values = _resolve_provider_input_values(
        native_node,
        plain_values,
        workspace=tmp_path,
        reader=None,
        result_path="attempt/result.json",
    )
    assert resolved_from_plain_values.prompt == resolved.prompt
    assert resolved_from_plain_values.input_parts == resolved.input_parts

    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    attempt_files = WorkspaceFiles(attempt_root)
    workspace_files = WorkspaceFiles(tmp_path)
    reads: list[str] = []
    original_read = attempt_files.read

    def counted_read(path):
        reads.append(os.fspath(path))
        return original_read(path)

    attempt_files.read = counted_read
    try:
        result, digest = perform_provider(
            native_node,
            resolved_from_plain_values,
            "effect-1",
            executor=ProviderExecutor(tmp_path, ProviderRegistry()),
            attempt_files=attempt_files,
            workspace_files=workspace_files,
            result_path="attempt/result.json",
            native_result=True,
        )
        assert result == {"ok": True}
        assert not hasattr(result, "json_value")
        assert digest == "sha256:" + hashlib.sha256(b'{"ok":true}').hexdigest()
        assert reads == ["result.json"]
        assert (tmp_path / "dispatches.txt").read_bytes() == b"x"
    finally:
        attempt_files.close()
        workspace_files.close()


def test_native_provider_rejects_non_root_contract_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.providers.registry import ProviderRegistry
    from orchestrator.workflow.evaluated.providers import (
        ProviderPerformerError,
        perform_provider,
        resolve_provider_input,
    )

    _source, typed_node, operands = _checked_provider_effect(tmp_path)
    binary = tmp_path / "bin" / "codex"
    _local_provider_script(binary, write_report=False)
    monkeypatch.setenv(
        "PATH",
        str(binary.parent) + os.pathsep + os.environ["PATH"],
    )
    resolved = resolve_provider_input(
        typed_node,
        operands,
        workspace=tmp_path,
        reader=None,
        result_path="attempt/result.json",
    )
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    attempt_files = WorkspaceFiles(attempt_root)
    workspace_files = WorkspaceFiles(tmp_path)
    try:
        with pytest.raises(ProviderPerformerError):
            perform_provider(
                typed_node,
                resolved,
                "effect-1",
                executor=ProviderExecutor(tmp_path, ProviderRegistry()),
                attempt_files=attempt_files,
                workspace_files=workspace_files,
                result_path="attempt/result.json",
                native_result=True,
            )
        assert not (tmp_path / "dispatches.txt").exists()
        assert not attempt_files.exists("prompt.txt")
    finally:
        attempt_files.close()
        workspace_files.close()


def test_native_command_document_bytes_match_typed_field_order() -> None:
    import orchestrator.workflow.evaluated.commands as commands

    string = {"kind": "primitive", "name": "String"}
    node = {
        "argv": ["python"],
        "argv_transport": [
            {"kind": "template", "parts": [{"kind": "slot", "name": ["input", "string", "value"], "path": [], "filters": []}]}
        ],
        "document": [
            ("review_report", "review-report-expression"),
            ("execution_report", "execution-report-expression"),
        ],
    }
    operands = (
        coerce_evaluated_value("python", string),
        coerce_evaluated_value("slot-value", string),
        coerce_evaluated_value("artifacts/review.json", string),
        coerce_evaluated_value("artifacts/exécution.json", string),
    )
    ordered_pairs = (
        ("review_report", "artifacts/review.json"),
        ("execution_report", "artifacts/exécution.json"),
    )

    native_bytes = commands._serialize_inline_command_document(ordered_pairs)

    assert native_bytes == (
        '{"review_report":"artifacts/review.json",'
        '"execution_report":"artifacts/exécution.json"}'
    ).encode("utf-8")
    assert commands.inline_command_document(node, operands) == native_bytes


def test_command_document_absence_count_and_json_errors_keep_typed_behavior() -> None:
    import orchestrator.workflow.evaluated.commands as commands

    string = {"kind": "primitive", "name": "String"}
    assert commands.inline_command_document({"argv": [], "argv_transport": []}, ()) is None

    node = {
        "argv": [],
        "argv_transport": [],
        "document": [("first", "first-expression"), ("second", "second-expression")],
    }
    with pytest.raises(commands.CommandTemplateError) as caught:
        commands.inline_command_document(
            node,
            (coerce_evaluated_value("only-one", string),),
        )
    assert caught.value.code == "memo_inconsistent"

    for invalid in (float("nan"), "lone-surrogate-\ud800"):
        with pytest.raises(commands.CommandTemplateError) as caught:
            commands._serialize_inline_command_document((("field", invalid),))
        assert caught.value.code == "effect_input_invalid"


def test_native_command_document_bytes_reach_real_command_dispatch(
    tmp_path: Path,
    owners: _Owners,
) -> None:
    import orchestrator.workflow.evaluated.commands as commands

    document = commands._serialize_inline_command_document(
        (
            ("review_report", "artifacts/review.json"),
            ("execution_report", "artifacts/exécution.json"),
        )
    )
    node = _checked_command(
        owners.workspace_files.workspace,
        return_type="Value",
    )
    input_path = os.path.relpath(
        owners.attempt_files.workspace / "inputs.json",
        owners.workspace_files.workspace,
    ).replace(os.sep, "/")
    script = _script(
        owners,
        '''
        import os, sys
        from pathlib import Path
        raw = Path(sys.argv[1]).read_bytes()
        Path("received-document.bin").write_bytes(raw)
        Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(raw)
        ''',
    )

    result, _digest = commands.perform_command(
        node,
        [sys.executable, script.name, input_path],
        attempt_files=owners.attempt_files,
        workspace_files=owners.workspace_files,
        input_document=document,
    )

    assert owners.attempt_files.read("inputs.json") == document
    assert (owners.workspace_files.workspace / "received-document.bin").read_bytes() == document
    assert result.json_value() == {
        "review_report": "artifacts/review.json",
        "execution_report": "artifacts/exécution.json",
    }
