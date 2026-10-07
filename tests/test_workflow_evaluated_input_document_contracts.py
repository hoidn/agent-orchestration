"""Checked document fields and recursive failures at the reached boundary."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated import effect_inputs
from orchestrator.workflow.evaluated import runtime
from tests.test_workflow_evaluated_command_lifecycle import _program, _publish, _started_snapshot


def _path_program(root, *, remove=True):
    (root / "make.py").write_text(
        'import json, os\nfrom pathlib import Path\n'
        'p=Path("artifacts/work/report.md");p.parent.mkdir(parents=True,exist_ok=True);p.write_text("report")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(str(p)))\n')
    action = 'Path("artifacts/work/report.md").unlink()\n' if remove else ''
    (root / "later.py").write_text('import os\nfrom pathlib import Path\n' + action +
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("0")\n')
    (root / "consume.py").write_text('import os\nfrom pathlib import Path\n'
        'Path("consumer-dispatched").touch()\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5")\n')
    return _program(root, '''(let* ((report (command-result make :argv ("python" "make.py") :returns Report)))
        (command-result consume :argv ("python" "consume.py"
            (command-result later :argv ("python" "later.py") :returns Int))
          :inputs ((trials (list (record Trial :report report)))) :returns Int))''',
        declarations='(defpath Report :kind relpath :under "artifacts/work" :must-exist true) (defrecord Trial (report Report))',
        bindings={"make": "make.py", "later": "later.py", "consume": "consume.py"})


def test_input_contract_is_checked_before_own_started(tmp_path, monkeypatch):
    _, program = _path_program(tmp_path)
    errors = []
    real = effect_inputs._resolve_effect_input

    def capture(*args, **kwargs):
        try:
            return real(*args, **kwargs)
        except Exception as exc:
            errors.append(exc)
            raise

    monkeypatch.setattr(effect_inputs, "_resolve_effect_input", capture)
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (1, None)
        snapshot = _started_snapshot(authority, program)
        assert len(snapshot.active_commits) == 2
        assert len([entry for entry in snapshot.entries if entry.data["record"] == "started"]) == 2
        assert not (tmp_path / "consumer-dispatched").exists()
        assert errors[0].code == "effect_input_invalid"
        assert errors[0].field == "trials"
        assert errors[0].value_path == "/trials/0/report"
        assert errors[0].violation.type == "missing_target"
        assert errors[0].violation.context["value"] == "artifacts/work/report.md"


INT = {"kind": "primitive", "name": "Int"}
FLOAT = {"kind": "primitive", "name": "Float"}
STRING = {"kind": "primitive", "name": "String"}
REPORT = {"kind": "path", "name": "Report", "under": "artifacts/work", "must_exist_target": True}
TRIAL = {"kind": "record", "name": "Trial", "fields": [{"name": "report", "type": REPORT}]}
CHOICE = {"kind": "union", "name": "Choice", "variants": [
    {"name": "YES", "fields": [{"name": "count", "type": INT}]}, {"name": "NO", "fields": []}]}


def _prepare_field(tmp_path, descriptor, value, field="payload"):
    from orchestrator.workflow.evaluated.inputs import prepare_command_document
    from orchestrator.workflow.evaluated.values import EvaluatedValue
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    node = {"argv": [], "argv_transport": [], "document": [[field, {}]]}
    with closing(WorkspaceFiles(tmp_path)) as files:
        return prepare_command_document(node, [EvaluatedValue(value, descriptor)], external=True,
            workspace=tmp_path, workspace_files=files)


@pytest.mark.parametrize("descriptor,value,pointer", [
    (INT, True, "/payload"), (FLOAT, float("inf"), "/payload"),
    ({"kind": "primitive", "name": "Bool"}, 0, "/payload"),
    (STRING, 1, "/payload"), ({"kind": "enum", "name": "Color", "allowed": ["red"]}, "blue", "/payload"),
    ({"kind": "list", "item": INT}, "[1]", "/payload"),
    (TRIAL, '{"report":"artifacts/work/report.md"}', "/payload"),
    (CHOICE, {"variant": "YES", "count": "wrong"}, "/payload/count"),
    (CHOICE, {"variant": "NO", "count": 2}, "/payload"),
    ({"kind": "optional", "item": INT}, "wrong", "/payload"),
    ({"kind": "map", "key": STRING, "value": INT}, {1: 2}, "/payload"),
    ({"kind": "map", "key": STRING, "value": INT}, {"a/b~c": True}, "/payload/a~1b~0c"),
])
def test_direct_document_rejects_malformed_runtime_values_without_string_decoding(tmp_path, descriptor, value, pointer):
    from orchestrator.workflow.evaluated.inputs import DocumentInputError

    with pytest.raises(DocumentInputError) as caught:
        _prepare_field(tmp_path, descriptor, value)
    assert caught.value.code == "effect_input_invalid"
    assert caught.value.field == "payload"
    assert caught.value.value_path == pointer
    assert caught.value.violation.type == "invalid_transportable_value"


@pytest.mark.parametrize("value,code", [
    ("artifacts/work/missing.md", "missing_target"),
    ("../escape.md", "path_escape"), ("artifacts/elsewhere/report.md", "outside_under_root")])
def test_nested_document_leaf_violation_keeps_field_path_and_code(tmp_path, value, code):
    from orchestrator.workflow.evaluated.inputs import DocumentInputError

    with pytest.raises(DocumentInputError) as caught:
        _prepare_field(tmp_path, {"kind": "list", "item": TRIAL}, [{"report": value}], "trials")
    assert caught.value.field == "trials"
    assert caught.value.value_path == "/trials/0/report"
    assert caught.value.violation.type == code
    assert caught.value.violation.context["value"] == value
    assert caught.value.violations[0]["context"] == caught.value.violation.context


def test_optional_active_union_and_field_names_keep_escaped_leaf(tmp_path):
    from orchestrator.workflow.evaluated.inputs import DocumentInputError

    descriptor = {"kind": "optional", "item": {"kind": "union", "name": "Outcome", "variants": [
        {"name": "YES", "fields": [{"name": "reports", "type": {"kind": "map", "key": STRING, "value": REPORT}}]},
        {"name": "NO", "fields": []}]}}
    with pytest.raises(DocumentInputError) as caught:
        _prepare_field(tmp_path, descriptor, {"variant": "YES", "reports": {"a/b~c": "artifacts/work/missing.md"}}, "a/b~c")
    assert caught.value.value_path == "/a~1b~0c/reports/a~1b~0c"
    assert caught.value.violation.type == "missing_target"
    assert _prepare_field(tmp_path, descriptor, None)[0] == b'{"payload":null}'
    assert _prepare_field(tmp_path, descriptor, {"variant": "NO"})[0] == b'{"payload":{"variant":"NO"}}'


def test_committed_document_divergence_is_structured_readonly_and_restore_reuses(tmp_path, monkeypatch):
    from tests.test_workflow_evaluated_invalidate import _tree_bytes

    _, program = _path_program(tmp_path, remove=False)
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        report = tmp_path / "artifacts/work/report.md"
        report.unlink()
        authority.memo_path.open("ab").write(b'{"record":"unfinished"')
        (authority.run_root / "state.json").write_text('{"stale":true}')
        before = _tree_bytes(authority.run_root)
        io_calls = _observe_replay_io(monkeypatch)
        errors = []
        real = runtime._resume_refusal

        def refuse(error):
            errors.append(error)
            return real(error)

        monkeypatch.setattr(runtime, "_resume_refusal", refuse)
        assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=tmp_path) == (2, None)
        assert _tree_bytes(authority.run_root) == before
        _assert_committed_violation(errors[0])
        assert io_calls == []
        report.write_text("restored, contents are not input identity")
        assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        assert _tree_bytes(authority.run_root) == before
        assert io_calls == []


def _assert_committed_violation(error):
    assert error.code == "effect_input_diverged"
    assert error.field == "trials"
    assert error.value_path == "/trials/0/report"
    assert error.violation.type == "missing_target"
    assert error.violation.context["value"] == "artifacts/work/report.md"


def test_canonical_external_bytes_keep_nested_values_and_ordered_nominal_contract(tmp_path):
    import json
    from orchestrator.workflow.evaluated.inputs import prepare_command_document
    from orchestrator.workflow.evaluated.values import EvaluatedValue
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    from orchestrator.workflow.run_ref.contracts import canonical_sha256

    node = {"argv": [], "argv_transport": [], "document": [["z", {}], ["a", {}]]}
    value = {"z": ["é", None, False, 0], "a": {"z": 2, "a": 1}}
    operands = [EvaluatedValue(value, {"kind": "primitive", "name": "Value"}), EvaluatedValue("red", {"kind": "enum", "name": "Color", "allowed": ["red"]})]
    with closing(WorkspaceFiles(tmp_path)) as files:
        raw, contract = prepare_command_document(node, operands, external=True, workspace=tmp_path, workspace_files=files)
        reordered, other = prepare_command_document({**node, "document": list(reversed(node["document"]))}, list(reversed(operands)), external=True,
            workspace=tmp_path, workspace_files=files)
    assert raw == b'{"a":"red","z":{"a":{"a":1,"z":2},"z":["\xc3\xa9",null,false,0]}}'
    assert json.loads(raw)["z"] == value
    assert reordered == raw
    assert contract[1][1]["name"] == "Color"
    assert canonical_sha256(contract) != canonical_sha256(other)


def _observe_replay_io(monkeypatch):
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    calls = []
    repair, perform = runtime.repair_torn_tail, runtime.perform_command
    create, read = WorkspaceFiles.create, WorkspaceFiles.read

    def repaired(*args, **kwargs):
        calls.append("repair")
        return repair(*args, **kwargs)

    def performed(*args, **kwargs):
        calls.append("dispatch")
        return perform(*args, **kwargs)

    def created(owner, path, *args, **kwargs):
        if str(path).endswith("inputs.json"):
            calls.append("create")
        return create(owner, path, *args, **kwargs)

    def read_document(owner, path, *args, **kwargs):
        if str(path).endswith(("inputs.json", "report.md")):
            calls.append("read")
        return read(owner, path, *args, **kwargs)

    monkeypatch.setattr(runtime, "repair_torn_tail", repaired)
    monkeypatch.setattr(runtime, "perform_command", performed)
    monkeypatch.setattr(WorkspaceFiles, "create", created)
    monkeypatch.setattr(WorkspaceFiles, "read", read_document)
    return calls
