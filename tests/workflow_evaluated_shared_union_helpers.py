"""Real producer/consumer fixtures and durable shared-projection oracles."""

import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun
from tests.test_workflow_evaluated_command_template_scopes import _assert_two_public_resumes
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.test_workflow_lisp_closed_shared_union_field import INT_SOURCE
from tests.workflow_evaluated_totality_helpers import (
    public_files, public_run, compile_public, checked_run, assert_commit_bytes,
)
from tests.workflow_lisp_closed_program_helpers import install


PRODUCER = '''import json, os, sys
from pathlib import Path
tag, raw = sys.argv[1:3]
with open("producer.log", "a") as log: log.write(json.dumps([tag, int(raw)]) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"variant":tag,"n":int(raw)}))
'''

CONSUMER = '''import json, os, sys
from pathlib import Path
data = Path(sys.argv[-1]).read_bytes()
document = json.loads(data)
with open("consumer.log", "a") as log: log.write(json.dumps(sys.argv[1:]) + "\\n")
Path("consumer.document.bin").write_bytes(data)
value = {"n": int(sys.argv[1]) + document["first"] + document["second"]}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(value))
'''


def _int_files(root, variant):
    n = 7 if variant == "YES" else 9
    source = INT_SOURCE.replace('"probe.py"', '"consumer.py"').replace(
        ':argv ("python" "consumer.py" value.n) :returns Output',
        ':argv ("python" "consumer.py" value.n) :inputs ((second value.n) (first value.n)) :returns Output')
    source = source.replace('(extract (variant Choice YES :n 7))',
        f'(extract (command-result produce :argv ("python" "producer.py" "{variant}" {n}) :returns Choice))')
    path = install(root, source)
    producer = root / "producer.py"
    producer.write_text(PRODUCER)
    (root / "consumer.py").write_text(CONSUMER)
    files = public_files(root, producer, ("produce", "probe"))
    files["source"] = path
    files["commands"].write_text(json.dumps({
        "produce": {"kind": "external_tool", "stable_command": ["python", "producer.py"], "closure": ["producer.py"]},
        "probe": {"kind": "external_tool", "stable_command": ["python", "consumer.py"], "closure": ["consumer.py"]}}))
    return files, n


def _pause_after_consumer(files, monkeypatch):
    original = runtime.append_record
    commits = []

    def after_append(path, record, **kwargs):
        entry = original(path, record, **kwargs)
        if record["record"] == "committed":
            commits.append(entry)
            if len(commits) == 2:
                raise _InterruptedRun()
        return entry

    with monkeypatch.context() as observed:
        observed.setattr(runtime, "append_record", after_append)
        with pytest.raises(_InterruptedRun):
            public_run(files)
    return commits


def _assert_int_commits(root, authority, snapshot, variant, n):
    producer, consumer = snapshot.active_commits.values()
    assert len(snapshot.latest_starts) == 2
    assert producer.data["value"] == {"variant": variant, "n": n}
    assert consumer.data["value"] == {"n": n * 3}
    assert [producer.data["depends_on"], consumer.data["depends_on"]] == [[], [producer.data["identity"]]]
    assert (root / "producer.log").read_text() == json.dumps([variant, n]) + "\n"
    (argv,) = [json.loads(line) for line in (root / "consumer.log").read_text().splitlines()]
    input_path = authority.run_root / Path(consumer.data["result_path"]).parent / "inputs.json"
    assert argv == [str(n), input_path.relative_to(root).as_posix()]
    expected = json.dumps({"second": n, "first": n}, sort_keys=True, separators=(",", ":")).encode()
    _assert_int_document(root, authority, consumer, argv[-1], expected)
    for entry in (producer, consumer):
        assert_commit_bytes(authority, entry)


def _assert_int_document(root, authority, consumer, token, expected):
    input_path = authority.run_root / Path(consumer.data["result_path"]).parent / "inputs.json"
    assert root / token == input_path
    assert input_path.read_bytes() == (root / "consumer.document.bin").read_bytes() == expected
    parts = consumer.data["input_parts"]
    assert parts["document"] == "sha256:" + hashlib.sha256(expected).hexdigest()
    descriptor = {"kind": "primitive", "name": "Int"}
    assert parts["input_contract"] == canonical_sha256([["second", descriptor], ["first", descriptor]])


PAYLOAD_PRODUCER = '''import json, os
from pathlib import Path
data = Path("producer.payload.json").read_bytes()
with open("producer.log", "ab") as log: log.write(data + b"\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(data)
'''

TEXT_CONSUMER = '''import json, os, sys
from pathlib import Path
with open("consumer.log", "a") as log: log.write(json.dumps(sys.argv[1:]) + "\\n")
if len(sys.argv) > 2: Path("consumer.document.bin").write_bytes(Path(sys.argv[-1]).read_bytes())
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"status":sys.argv[1]}))
'''


def _payload_files(root, sources, payload, *, entry_path=None, consumer=TEXT_CONSUMER):
    source = install(root, sources, entry_path=entry_path)
    producer = root / "producer.py"
    producer.write_text(PAYLOAD_PRODUCER)
    (root / "producer.payload.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    (root / "consumer.py").write_text(consumer)
    files = public_files(root, producer, ("produce", "probe"))
    files["source"] = source
    files["commands"].write_text(json.dumps({
        "produce": {"kind": "external_tool", "stable_command": ["python", "producer.py"],
                    "closure": ["producer.py", "producer.payload.json"]},
        "probe": {"kind": "external_tool", "stable_command": ["python", "consumer.py"], "closure": ["consumer.py"]}}))
    return files


def _exercise_payload(files, monkeypatch, payload, projection, result, *, document=None):
    root = files["workspace"]
    compile_public(files)
    monkeypatch.chdir(root)
    commits = _pause_after_consumer(files, monkeypatch)
    authority, before = checked_run(root)
    assert before.terminal is None
    assert list(before.active_commits.values()) == commits
    _assert_payload_commits(root, authority, before, payload, projection, result, document)
    prefix = authority.memo_path.read_bytes()
    resumed = _resume_cli(root, authority.header["run_id"])
    assert resumed.returncode == 0, resumed.stderr
    authority, after = checked_run(root)
    assert after.terminal.data["value"] == result
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert list(after.active_commits.values()) == commits
    _assert_two_public_resumes(root, root / "producer.log", root / "consumer.log")
    _assert_payload_commits(root, authority, after, payload, projection, result, document)
    return authority, after


def _assert_payload_commits(root, authority, snapshot, payload, projection, result, document):
    producer, consumer = snapshot.active_commits.values()
    assert len(snapshot.latest_starts) == 2
    assert [producer.data["value"], consumer.data["value"]] == [payload, result]
    assert [producer.data["depends_on"], consumer.data["depends_on"]] == [[], [producer.data["identity"]]]
    assert (root / "producer.log").read_bytes() == (root / "producer.payload.json").read_bytes() + b"\n"
    (argv,) = [json.loads(line) for line in (root / "consumer.log").read_text().splitlines()]
    if document is None:
        assert argv == [projection]
    else:
        token = (authority.run_root / Path(consumer.data["result_path"]).parent / "inputs.json").relative_to(root).as_posix()
        assert argv == [projection, token]
        _assert_payload_document(root, consumer, document)
    for entry in (producer, consumer):
        assert_commit_bytes(authority, entry)


def _assert_payload_document(root, consumer, document):
    expected = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert (root / "consumer.document.bin").read_bytes() == expected
    assert consumer.data["input_parts"]["document"] == "sha256:" + hashlib.sha256(expected).hexdigest()


def _assert_shared_payload_owner(authority, snapshot, target_name, *, document, whole):
    from tests.test_workflow_lisp_closed_shared_union_field import _nodes

    consumer = list(snapshot.active_commits.values())[1]
    target = authority.program.tree["types"][target_name]
    if document:
        assert consumer.data["input_parts"]["input_contract"] == canonical_sha256([["selected", target]])
    else:
        assert "document" not in consumer.data["input_parts"]
    fields = [node for node in _nodes(authority.program.tree) if node.get("k") == "field" and node.get("shared")]
    path = ["selection"] if whole else ["selection", "item-id"]
    shared = [target] if whole else [target, None]
    assert any(node["path"] == path and node["shared"] == shared for node in fields)


def _observe_pure_referent(monkeypatch, referent):
    from orchestrator.workflow.evaluated import values
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    calls = {"fields": [], "pure_io": [], "boundary_io": []}
    active = [False]
    original_field = values._VALUE_EVALUATORS["field"]

    def field(node, *args, **kwargs):
        previous = active[0]
        active[0] = bool(node.get("shared"))
        if active[0]:
            calls["fields"].append(node["path"])
        try:
            return original_field(node, *args, **kwargs)
        finally:
            active[0] = previous

    def observe(method, name):
        def checked(owner, path, *args, **kwargs):
            if owner.workspace / Path(path) == referent:
                calls["pure_io" if active[0] else "boundary_io"].append(name)
                if active[0]:
                    pytest.fail("pure shared field observed committed referent: " + name)
            return method(owner, path, *args, **kwargs)
        return checked

    monkeypatch.setitem(values._VALUE_EVALUATORS, "field", field)
    for name in ("exists", "stat", "read", "open_read", "sha256"):
        monkeypatch.setattr(WorkspaceFiles, name, observe(getattr(WorkspaceFiles, name), name))
    return calls
