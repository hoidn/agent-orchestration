"""Public checked shared-union projection through real durable commands."""

import json
from pathlib import Path

import pytest

from tests.workflow_evaluated_shared_union_helpers import (
    _int_files, _pause_after_consumer, _assert_int_commits, _payload_files, _exercise_payload,
    _assert_shared_payload_owner,
    _observe_pure_referent,
)
from tests.workflow_evaluated_totality_helpers import compile_public, checked_run
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.test_workflow_evaluated_command_template_scopes import _assert_two_public_resumes
from tests.test_workflow_lisp_closed_shared_union_field import NESTED_SOURCE, HELPER_SOURCE, ENTRY_SOURCE, PREFIX_SOURCE, PATH_SOURCE, MATCH_SOURCE, BOUND_SOURCE, _nodes
from orchestrator.workflow.run_ref.contracts import canonical_sha256


@pytest.mark.parametrize("variant", ("YES", "NO"))
def test_public_shared_int_producer_consumer_reuses_after_commit(tmp_path, monkeypatch, variant):
    files, n = _int_files(tmp_path, variant)
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    committed = _pause_after_consumer(files, monkeypatch)
    authority, paused = checked_run(tmp_path)
    assert paused.terminal is None
    assert list(paused.active_commits.values()) == committed
    _assert_int_commits(tmp_path, authority, paused, variant, n)
    prefix = authority.memo_path.read_bytes()
    resumed = _resume_cli(tmp_path, authority.header["run_id"])
    assert resumed.returncode == 0, resumed.stderr
    authority, completed = checked_run(tmp_path)
    assert completed.terminal.data["value"] == {"n": n * 3}
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert list(completed.active_commits.values()) == committed
    _assert_two_public_resumes(tmp_path, tmp_path / "producer.log", tmp_path / "consumer.log", tmp_path / "consumer.document.bin")
    _assert_int_commits(tmp_path, authority, completed, variant, n)


def _nested_sources(mode):
    if mode == "local":
        source = NESTED_SOURCE.replace('"probe.py"', '"consumer.py"').replace(
            ':argv ("python" "consumer.py" choice.selection.item-id)',
            ':argv ("python" "consumer.py" choice.selection.item-id) :inputs ((selected choice.selection))')
        source = source.replace('(choose (variant Selection SELECTED :selection (record Payload :item-id "seed")))',
            '(choose (command-result produce :argv ("python" "producer.py") :returns Selection))')
        return source, None, "probe/shared_nested::Payload"
    if mode == "prefix":
        source = PREFIX_SOURCE.replace('"probe.py"', '"consumer.py"').replace(
            ':argv ("python" "consumer.py" choice.selection.item-id)',
            ':argv ("python" "consumer.py" choice.selection.item-id) :inputs ((selected choice.selection))')
        source = source.replace('(defworkflow run ((choice Choice)) -> Output\n    (let*',
            '(defworkflow run () -> Output\n    (let* ((choice (command-result produce :argv ("python" "producer.py") :returns Choice)))\n    (let*') + ')'
        return source, None, "probe/shared_prefix::Payload"
    helper = HELPER_SOURCE.replace('"probe.py"', '"consumer.py"')
    entry = ENTRY_SOURCE.replace("FIELD_TYPE", "String").replace("FIELD_VALUE", '"seed"').replace(
        '(h.project (variant Choice A :selection (record Payload :item-id "seed")))',
        '(h.project (command-result produce :argv ("python" "producer.py") :returns Choice))')
    if mode == "rich-imported":
        declarations = '''(defenum Status A B) (defunion Nested (ON (status Status)) (OFF (status Status)))
          (defrecord Leaf (status Status)) (defrecord Payload
            (item-id String) (status Status) (nested Nested) (leaves List[Leaf]))'''
        helper = helper.replace('(defrecord Payload (item-id String))', declarations)
        entry = entry.replace('(defrecord Payload (item-id String))', declarations)
        helper = helper.replace('-> Output', '-> Payload').replace(
            ''':effects ((uses-command probe)) :lowering inline
    (command-result probe
      :argv ("python" "consumer.py" choice.selection.item-id) :returns Output)''',
            ':effects () :lowering inline choice.selection')
        entry = entry.replace('(h.project (command-result produce :argv ("python" "producer.py") :returns Choice))',
            '''(let* ((choice (command-result produce :argv ("python" "producer.py") :returns Choice))
                     (selected (h.project choice)))
              (command-result probe :argv ("python" "consumer.py" selected.item-id)
                :inputs ((selected selected)) :returns h.Output))''')
    return {"helper.orc": helper, "entry.orc": entry}, "entry.orc", "helper::Payload"


@pytest.mark.parametrize("mode", ("local", "prefix", "imported", "rich-imported"))
@pytest.mark.parametrize("second", (False, True))
def test_public_shared_nested_payload_keeps_checked_owner_and_complete_document(tmp_path, monkeypatch, mode, second):
    sources, entry, target_name = _nested_sources(mode)
    selected = {"item-id": "雪-seed"}
    if mode == "rich-imported":
        selected.update(status="A", nested={"variant": "ON", "status": "A"}, leaves=[{"status": "B"}])
    tag = ("ALTERNATE" if second else "SELECTED") if mode == "local" else ("B" if second else "A")
    payload = {"variant": tag, "selection": selected}
    files = _payload_files(tmp_path, sources, payload, entry_path=entry)
    document = None if mode == "imported" else {"selected": selected}
    authority, snapshot = _exercise_payload(files, monkeypatch, payload, "雪-seed", {"status": "雪-seed"}, document=document)
    _assert_shared_payload_owner(authority, snapshot, target_name, document=document is not None, whole=mode == "rich-imported")
    if mode in ("imported", "rich-imported"):
        assert authority.program.tree["types"]["entry::Payload"] != authority.program.tree["types"][target_name]


def _path_source():
    return PATH_SOURCE.replace('"probe.py"', '"consumer.py"').replace(
        '(defworkflow run ((path ReportPath)) -> Output\n    (project (variant Choice REPORT :artifact path)))',
        '(defworkflow run () -> Output\n    (project (command-result produce :argv ("python" "producer.py") :returns Choice)))')


@pytest.mark.parametrize("variant", ("REPORT", "ARTIFACT"))
@pytest.mark.parametrize("delete", (False, True))
def test_public_committed_shared_path_replay_never_reobserves_pure_referent(tmp_path, monkeypatch, variant, delete):
    from orchestrator.cli.commands.resume import resume_workflow
    from tests.test_workflow_evaluated_providers import _orchestrate_snapshot

    referent = tmp_path / "state/report.md"
    referent.parent.mkdir()
    referent.write_text("original report")
    payload = {"variant": variant, "artifact": "state/report.md"}
    files = _payload_files(tmp_path, _path_source(), payload)
    authority, snapshot = _exercise_payload(files, monkeypatch, payload, "state/report.md", {"status": "state/report.md"})
    fields = [node for node in _nodes(authority.program.tree) if node.get("k") == "field" and node.get("shared")]
    assert any(node["shared"] == [authority.program.tree["types"]["Path.state-root"]] for node in fields)
    if delete:
        referent.unlink()
    else:
        referent.write_text("changed committed referent")
    before = _orchestrate_snapshot(tmp_path)
    calls = _observe_pure_referent(monkeypatch, referent)
    assert resume_workflow(authority.header["run_id"]) == 0
    assert calls["fields"]
    assert calls["pure_io"] == []
    assert calls["boundary_io"] == []
    assert _orchestrate_snapshot(tmp_path) == before
    _assert_two_public_resumes(tmp_path, tmp_path / "producer.log", tmp_path / "consumer.log")


def test_public_fresh_shared_path_result_still_requires_existing_target(tmp_path, monkeypatch):
    from tests.workflow_evaluated_totality_helpers import public_run

    files = _payload_files(tmp_path, _path_source(), {"variant": "REPORT", "artifact": "state/missing.md"})
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    assert public_run(files).exit_code == 1
    authority, snapshot = checked_run(tmp_path)
    assert len(snapshot.latest_starts) == 1
    assert not snapshot.active_commits
    assert snapshot.terminal.data["outcome"] == "failed"
    failure = next(entry for entry in snapshot.entries if entry.data.get("record") == "failed")
    assert failure.data["violations"] == [{"type": "variant_field_type_invalid",
        "message": "relpath target does not exist", "context": {
            "json_pointer": "/artifact", "path": (authority.run_root / snapshot.latest_starts[failure.data["identity"]].data["result_path"]).relative_to(tmp_path).as_posix(),
            "value": "state/missing.md", "variant": "REPORT"}}]
    assert not (tmp_path / "consumer.log").exists()


def _match_source():
    source = MATCH_SOURCE.replace('"probe.py"', '"consumer.py"')
    source = source.replace(':argv ("python" "consumer.py" proven.a)',
        ':argv ("python" "consumer.py" proven.a) :inputs ((selected proven.a))')
    source = source.replace(':argv ("python" "consumer.py" proven.b)',
        ':argv ("python" "consumer.py" proven.b) :inputs ((selected proven.b))')
    start = source.index('  (defworkflow run ')
    return source[:start] + '''  (defworkflow run () -> Output
      (extract (command-result produce :argv ("python" "producer.py") :returns Outer))))'''


@pytest.mark.parametrize("second", (False, True))
def test_public_shared_full_union_match_reaches_only_active_specific_field(tmp_path, monkeypatch, second):
    tag, inner, field, value = ("RIGHT", "B", "b", "right") if second else ("LEFT", "A", "a", "left")
    payload = {"variant": tag, "selection": {"variant": inner, field: value}}
    files = _payload_files(tmp_path, _match_source(), payload)
    authority, snapshot = _exercise_payload(files, monkeypatch, payload, value,
        {"status": value}, document={"selected": value})
    nodes = [node for node in _nodes(authority.program.tree) if node.get("k") == "field"]
    assert any(node.get("shared") == [authority.program.tree["types"]["probe/shared_match::Inner"]] for node in nodes)
    assert any(node["path"] == [field] and "shared" not in node for node in nodes)
    commit = list(snapshot.active_commits.values())[1]
    assert commit.data["input_parts"]["input_contract"] == canonical_sha256([
        ["selected", {"kind": "primitive", "name": "String"}]])


@pytest.mark.parametrize("variant", ("YES", "NO"))
def test_public_shared_projection_forwarding_and_capture_preserve_value(tmp_path, monkeypatch, variant):
    n = 7 if variant == "YES" else 9
    source = BOUND_SOURCE.replace('"probe.py"', '"consumer.py"')
    start = source.index('  (defworkflow run ')
    source = source[:start] + '''  (defworkflow run () -> Output
      (forward (command-result produce :argv ("python" "producer.py") :returns Choice))))'''
    consumer = '''import json,os,pathlib,sys
pathlib.Path("consumer.log").open("a").write(json.dumps(sys.argv[1:])+"\\n")
pathlib.Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"n":int(sys.argv[1])}))
'''
    payload = {"variant": variant, "n": n}
    files = _payload_files(tmp_path, source, payload, consumer=consumer)
    authority, _ = _exercise_payload(files, monkeypatch, payload, str(n), {"n": n})
    deliver = next(row for row in authority.program.tree["definitions"].values() if row["key"][2] == "deliver")
    assert deliver["key"][7] == [{"type": {"kind": "primitive", "name": "Int"},
        "routes": [["parameter", "fixed"]]}]


def test_public_shared_artifact_tamper_refuses_before_any_dispatch(tmp_path, monkeypatch):
    from orchestrator.cli.commands import evaluated
    from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun
    from tests.test_workflow_evaluated_providers import _orchestrate_snapshot
    from tests.workflow_evaluated_totality_helpers import public_run

    files, _ = _int_files(tmp_path, "YES")
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    original = evaluated.execute_pure_run
    def pause(*args, **kwargs):
        raise _InterruptedRun()
    monkeypatch.setattr(evaluated, "execute_pure_run", pause)
    with pytest.raises(_InterruptedRun):
        public_run(files)
    monkeypatch.setattr(evaluated, "execute_pure_run", original)
    authority, snapshot = checked_run(tmp_path)
    assert not snapshot.latest_starts and not snapshot.active_commits
    tree = json.loads(authority.program_path.read_bytes())
    node = next(node for node in _nodes(tree) if node.get("k") == "field" and node.get("shared"))
    node["shared"] = []
    authority.program_path.write_text(json.dumps(tree))
    before = _orchestrate_snapshot(tmp_path)
    refused = _resume_cli(tmp_path, authority.header["run_id"])
    assert refused.returncode != 0
    assert "memo_inconsistent" in refused.stderr
    assert _orchestrate_snapshot(tmp_path) == before
    assert not (tmp_path / "producer.log").exists() and not (tmp_path / "consumer.log").exists()


def test_public_fresh_shared_path_input_refuses_before_dispatch(tmp_path, monkeypatch, caplog):
    from tests.workflow_evaluated_totality_helpers import public_run

    source = PATH_SOURCE.replace('"probe.py"', '"consumer.py"')
    files = _payload_files(tmp_path, source, {})
    compile_public(files)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"path": "state/missing.md"}))
    monkeypatch.chdir(tmp_path)
    result = public_run(files, input_file=inputs)
    assert result.exit_code == 2
    assert result.run_id is None and result.run_root is None
    assert [record.getMessage() for record in caplog.records] == ["Validation error: Workflow input binding failed"]
    assert not list((tmp_path / ".orchestrate/runs").glob("*/header.json"))
    assert not (tmp_path / "producer.log").exists()
    assert not (tmp_path / "consumer.log").exists()


def _ordinary_union_sources(*, unprojected=False):
    declarations = '(defunion Inner (A (a String)) (B (b String)))'
    helper = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule helper) (export Inner Output project consume)
      (defrecord Output (status String)) DECLARATIONS
      (defproc project :forall (T) ((value T))
        :where ((T has-shared-union-field selection Inner)) -> Inner
        :effects () :lowering inline value.selection)
      (defworkflow consume ((choice Inner)) -> Output
        (match choice
          ((A selected) (command-result probe :argv ("python" "consumer.py" selected.a) :returns Output))
          ((B selected) (command-result probe :argv ("python" "consumer.py" selected.b) :returns Output)))))'''.replace('DECLARATIONS', declarations)
    operand = '(variant Inner A :a "wrong-owner")' if unprojected else '(h.project (command-result produce :argv ("python" "producer.py") :returns Outer))'
    entry = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule entry) (import helper :as h) (export run)
      DECLARATIONS
      (defunion Outer (LEFT (selection Inner)) (RIGHT (selection Inner)))
      (defworkflow run () -> h.Output (call h.consume :choice OPERAND)))'''
    return {"helper.orc": helper, "entry.orc": entry.replace('DECLARATIONS', declarations).replace('OPERAND', operand)}


@pytest.mark.parametrize("second", (False, True))
def test_public_certified_full_union_target_crosses_ordinary_helper_match(tmp_path, monkeypatch, second):
    outer, inner, field, value = ("RIGHT", "B", "b", "right") if second else ("LEFT", "A", "a", "left")
    payload = {"variant": outer, "selection": {"variant": inner, field: value}}
    files = _payload_files(tmp_path, _ordinary_union_sources(), payload, entry_path="entry.orc")
    authority, _ = _exercise_payload(files, monkeypatch, payload, value, {"status": value})
    types = authority.program.tree["types"]
    assert types["entry::Inner"] != types["helper::Inner"]
    assert any(node.get("shared") == [types["helper::Inner"]] for node in _nodes(authority.program.tree))


def test_public_unprojected_homonymous_union_keeps_ordinary_nominal_refusal(tmp_path):
    from tests.test_workflow_lisp_closed_program_compile_cli import _compile

    sources = _ordinary_union_sources(unprojected=True)
    files = _payload_files(tmp_path, sources, {}, entry_path="entry.orc")
    result = _compile(files)
    operand = '(variant Inner A :a "wrong-owner")'
    line, row = next((number, row) for number, row in enumerate(sources["entry.orc"].splitlines(), 1) if operand in row)
    assert result.returncode != 0
    assert f"entry.orc:{line}:{row.index(operand) + 1}: [type_mismatch]" in result.stderr
