"""A privately published closed child resumes through its own public recipe."""

import json
import pytest

from orchestrator.workflow.evaluated.memo import append_record, read_memo
from orchestrator.workflow.run_ref import child, runtime
from tests import test_workflow_evaluated_run_ref_caller as caller
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.test_workflow_run_ref_child import _build_path_fixture
from tests.test_workflow_evaluated_path_compile import _closed_source, _typed_closed_launch


def test_child_public_resume_uses_own_recipe_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(
        root, target_dsl_version="2.35"))
    with caller._checked_launch_fixture(tmp_path) as (request, fixture, document, owner):
        launch = runtime.RunRefChildLaunch("path", fixture.request_path, document,
            fixture.materialized_source.workspace_path, document["child_run_id"], owner.root_fd)
        process = runtime._default_child_launcher(launch)
        assert process.returncode == 0, process.stderr.decode()
        returned = json.loads(process.stdout)
        identity = document["parent_authority"]["identity"]
        append_record(request.parent_run_root / "memo.jsonl", {"record": "failed", "identity": identity,
            "attempt": 2, "code": "fixture_parent_removed", "exit_info": {}}, run_files=owner)
        retained = request.parent_run_root.with_name("unavailable-parent")
        request.parent_run_root.rename(retained)
        parent_before = _tree_bytes(retained)
        workspace = fixture.materialized_source.workspace_path
        run_root = workspace / ".orchestrate" / "runs" / document["child_run_id"]
        before = _tree_bytes(workspace)
        for _ in range(2):
            result = _resume_cli(workspace, run_root.name)
            assert result.returncode == 0, result.stderr
            assert _tree_bytes(workspace) == before
        assert _tree_bytes(retained) == parent_before
        assert read_memo(run_root / "memo.jsonl", {}).terminal.data["value"] == returned["workflow_outputs"]["__result__"]


@pytest.mark.parametrize("optional", [None, "present"])
def test_closed_child_json_and_omitted_defaults_resume(tmp_path, monkeypatch, capsys, optional):
    from orchestrator.workflow.evaluated.authority import load_run_authority

    common = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule common) (export Packet Choice)
      (defunion Choice (KEEP (text String)) (DROP))
      (defrecord Packet (choices List[Choice]) (scores Map[String,Int]) (note Optional[String])))'''
    imports = {"common.orc": common}
    definition = "(import common :only (Packet Choice))"
    source = _closed_source(parameters='(payload Packet) (label String :default "omitted")',
                            import_form=definition, returns="Packet")
    value = {"choices": [{"variant": "KEEP", "text": "nested"}, {"variant": "DROP"}],
             "scores": {"one": 1, "two": 2}, "note": optional}
    with _typed_closed_launch(tmp_path, monkeypatch, source, type_name="Packet", value=value,
                              definitions=definition, imports=imports, returns="Packet") as (_request, fixture, document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 0, capsys.readouterr().err
        returned = json.loads(capsys.readouterr().out)
        workspace = fixture.materialized_source.workspace_path
        authority = load_run_authority(fixture.state_dir / document["child_run_id"])
        assert authority.header["resume_request"]["input_overrides"] == {"payload": value}
        assert authority.header["bound_inputs"] == {"payload": value, "label": "omitted"}
        assert returned["workflow_outputs"] == {"__result__": value}
        snapshot = _tree_bytes(workspace)
        for _ in range(2):
            result = _resume_cli(workspace, document["child_run_id"])
            assert result.returncode == 0, result.stderr
            assert _tree_bytes(workspace) == snapshot


def test_child_resume_uses_post_copy_override_once(tmp_path, monkeypatch, capsys):
    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.workflow.evaluated.authority import load_run_authority

    common = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common)
      (export WorkPath) (defpath WorkPath :kind relpath :under "artifacts" :must-exist true))'''
    definition = "(import common :only (WorkPath))"
    source = _closed_source(parameters="(payload WorkPath)", import_form=definition, body='"copied"')
    with _typed_closed_launch(tmp_path, monkeypatch, source, type_name="WorkPath", value="artifacts/seed.txt",
        definitions=definition, imports={"common.orc": common}, parent_files={"artifacts/seed.txt": "source bytes"}) as (request, fixture, document, owner):
        copied = document["inputs"]["payload"]
        assert copied != "artifacts/seed.txt"
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 0, capsys.readouterr().err
        capsys.readouterr()
        authority = load_run_authority(fixture.state_dir / document["child_run_id"])
        assert authority.header["resume_request"]["input_overrides"] == {"payload": copied}
        assert (fixture.materialized_source.workspace_path / copied).read_text() == "source bytes"
        (request.parent_workspace / "artifacts" / "seed.txt").unlink()
        monkeypatch.setattr(runtime, "_copy_path_value", lambda *_args, **_kwargs: pytest.fail("second path copy"))
        workspace = fixture.materialized_source.workspace_path
        monkeypatch.chdir(workspace)
        before = _tree_bytes(workspace)
        for _ in range(2):
            assert resume_workflow(document["child_run_id"]) == 0
            assert _tree_bytes(workspace) == before


@pytest.mark.parametrize("change", ["semantic", "missing_source", "missing_import", "format", "home"])
def test_child_resume_rebuilds_only_own_sources(tmp_path, monkeypatch, capsys, change):
    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.workflow.evaluated.authority import load_run_authority

    common = '(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common) (export carry) (defproc carry ((x String)) -> String :effects () :lowering inline x))'
    source = _closed_source(import_form="(import common :only (carry))", body="(carry payload)")
    with _typed_closed_launch(tmp_path, monkeypatch, source, imports={"common.orc": common}) as (_request, fixture, document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 0, capsys.readouterr().err
        capsys.readouterr()
        workspace = fixture.materialized_source.workspace_path
        authority = load_run_authority(fixture.state_dir / document["child_run_id"])
        published_root = authority.header["run_ref_root"]
        entry = workspace / "candidate.orc"
        if change == "semantic":
            entry.write_text(source.replace("(carry payload)", '"changed"'))
        elif change == "missing_source":
            entry.unlink()
        elif change == "missing_import":
            (workspace / "common.orc").unlink()
        elif change == "format":
            entry.write_text("; formatting only\n" + source.replace("(carry payload)", "(carry    payload)"))
        else:
            home = tmp_path / "different-home"
            home.mkdir()
            monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(workspace)
        before = _tree_bytes(workspace)
        expected = 0 if change in {"format", "home"} else 2
        for _ in range(2):
            assert resume_workflow(document["child_run_id"]) == expected
            assert _tree_bytes(workspace) == before
        assert load_run_authority(fixture.state_dir / document["child_run_id"]).header["run_ref_root"] == published_root
