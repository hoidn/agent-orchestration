"""Public 2.35 parents whose path children return nested typed paths."""

from __future__ import annotations

import base64
from hashlib import sha256
import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated import runtime as evaluated_runtime
from orchestrator.workflow.evaluated.machine import site_nodes
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.run_ref.runtime import (
    declared_artifacts_from_value, flatten_run_ref_result_artifacts,
)
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from tests.e2e.test_e2e_workflow_lisp_run_ref import _assert_complete_evidence_manifest, _git
from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun
from tests.test_workflow_evaluated_run_ref import _authority, _public_fixture
from tests.test_workflow_evaluated_run_ref_settlement import _commit_gap, _service_run


SEED = "artifacts/seed.txt"
SEED_BYTES = b"seed bytes from the materialized source\n"
PARENT_FILES = {"a.txt": b"parent a bytes\n", "b.txt": b"parent b bytes\n",
                "d.txt": b"parent d bytes\n", "x.txt": b"parent x bytes\n"}
INPUTS = {"payload": {"a": "artifacts/a.txt", "b": "artifacts/b.txt", "d": "artifacts/d.txt",
                      "extra": "artifacts/x.txt", "absent": None}}

PATH_MODULE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.24") (defmodule common)
  (export WorkPath) (defpath WorkPath :kind relpath :under "artifacts" :must-exist true))'''
SHAPE_TYPES = '''(defunion Pick (FILE (file WorkPath)) (NONE))
  (defrecord Inputs (a WorkPath) (b WorkPath) (d WorkPath) (extra Optional[WorkPath]) (absent Optional[WorkPath]))
  (defrecord Listed (primary WorkPath) (items List[WorkPath]))
  (defrecord Bundle (primary WorkPath) (items List[WorkPath]) (extra Optional[WorkPath])
    (absent Optional[WorkPath]) (chosen Pick) (skipped Pick))'''
SHAPE_MODULE = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.24") (defmodule shapes)
  (import common :only (WorkPath)) (export Inputs Pick Listed Bundle) {SHAPE_TYPES})'''
SAME_MODULE = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.24") (defmodule common)
  (export WorkPath Inputs Pick Listed Bundle)
  (defpath WorkPath :kind relpath :under "artifacts" :must-exist true) {SHAPE_TYPES})'''

_SEED_INPUT = f' (seed WorkPath :default "{SEED}")'
_MATCH = "(let* ((child {call})) (match child.value{field} ((FILE selected) true) ((NONE selected) false)))"
_BUNDLE = ("(record Bundle :primary seed :items (list payload.a payload.b) :extra payload.extra "
           ":absent payload.absent :chosen (variant Pick FILE :file payload.d) :skipped (variant Pick NONE))")
CASES = {
    "legacy-list": dict(child_target="2.24", returns="Listed", inputs="(a WorkPath) (b WorkPath)" + _SEED_INPUT,
        call_inputs=":a payload.a :b payload.b", child_body="(record Listed :primary seed :items (list a b))",
        parent="(let* ((child {call})) true)"),
    "legacy-union": dict(child_target="2.24", returns="Pick", inputs="(d WorkPath)", call_inputs=":d payload.d",
        child_body="(variant Pick FILE :file d)", parent=_MATCH.replace("{field}", "")),
    "evaluated-nested": dict(child_target="2.35", returns="Bundle", inputs="(payload Inputs)" + _SEED_INPUT,
        call_inputs=":payload payload", child_body=_BUNDLE, parent=_MATCH.replace("{field}", ".chosen")),
}
CASES["evaluated-same-module"] = dict(CASES["evaluated-nested"], modules={"common.orc": SAME_MODULE})
CASES["legacy-same-module"] = dict(CASES["legacy-union"], modules={"common.orc": SAME_MODULE})
# The child's `shapes` imports a homonymous `WorkPath` declared in module `other`.
HOMONYM = dict(child_target="2.24", returns="Pick", inputs="", call_inputs="", child_body="(variant Pick NONE)",
    parent=_MATCH.replace("{field}", ""), child_modules={
        "common.orc": PATH_MODULE, "other.orc": PATH_MODULE.replace("(defmodule common)", "(defmodule other)"),
        "shapes.orc": SHAPE_MODULE.replace("(import common :only", "(import other :only")})


def _expected_value(case, request):
    inputs, returns = request["inputs"], CASES[case]["returns"]
    if returns == "Listed":
        return {"primary": SEED, "items": [inputs["a"], inputs["b"]]}
    if returns == "Pick":
        return {"variant": "FILE", "file": inputs["d"]}
    payload = inputs["payload"]
    return {"primary": SEED, "items": [payload["a"], payload["b"]], "extra": payload["extra"],
            "absent": None, "chosen": {"variant": "FILE", "file": payload["d"]}, "skipped": {"variant": "NONE"}}


def _expected_leaves(case, value):
    returns = CASES[case]["returns"]
    if returns == "Listed":
        return [("value.items[0]", value["items"][0]), ("value.items[1]", value["items"][1]),
                ("value.primary", SEED)]
    if returns == "Pick":
        return [("value.file", value["file"])]
    return [("value.chosen.file", value["chosen"]["file"]), ("value.extra", value["extra"]),
            ("value.items[0]", value["items"][0]), ("value.items[1]", value["items"][1]),
            ("value.primary", SEED)]


def path_envelope_fixture(root, case, spec=None):
    spec = spec or CASES[case]
    root.mkdir(parents=True, exist_ok=True)
    modules = spec.get("modules", {"common.orc": PATH_MODULE, "shapes.orc": SHAPE_MODULE})
    imports = ("(import common :only (WorkPath Inputs Pick Listed Bundle))" if "shapes.orc" not in modules
               else "(import common :only (WorkPath)) (import shapes :only (Inputs Pick Listed Bundle))")
    parent, source, refs = _public_fixture(root, child_target=spec["child_target"], imports=imports,
        child_imports=imports, parameters="(payload Inputs)", inputs=spec["inputs"],
        call_inputs=spec["call_inputs"], child_body=spec["child_body"], returns=spec["returns"],
        body=lambda call: spec["parent"].format(call=call))
    _commit_files(root / "candidate", source, {**spec.get("child_modules", modules), SEED: SEED_BYTES})
    for name, content in modules.items():
        (parent / name).write_text(content)
    (parent / "artifacts").mkdir()
    for name, content in PARENT_FILES.items():
        (parent / "artifacts" / name).write_bytes(content)
    inputs = parent / "inputs.json"
    inputs.write_text(json.dumps(INPUTS))
    return parent, source, refs, ("--input-file", str(inputs))


def _commit_files(candidate, source, files):
    old_commit = _git(candidate, "rev-parse", "HEAD")
    for name, content in files.items():
        path = candidate / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    _git(candidate, "add", ".")
    _git(candidate, "-c", "user.name=Run Ref E2E", "-c", "user.email=run-ref-e2e@example.invalid",
         "commit", "--quiet", "-m", "path envelope fixture")
    source.write_text(source.read_text().replace(old_commit, _git(candidate, "rev-parse", "HEAD")))


def settled_evidence(parent):
    authority, memo = _authority(parent)
    (commit,) = memo.active_commits.values()
    settlement = commit.data["proof"]["settled_result"]
    attempt_root = Path(settlement["workspace_path"]).parent
    documents = {name: json.loads((attempt_root / f"{name}.json").read_bytes()) for name in
                 ("child-request", "child-result", "workspace-delta", "accounting")}
    return authority, memo, commit, attempt_root, documents


def _path_names(descriptor):
    kind = descriptor["kind"]
    if kind == "path":
        return {descriptor["name"]}
    nested = [field["type"] for field in descriptor.get("fields", ())]
    nested += [field["type"] for variant in descriptor.get("variants", ()) for field in variant["fields"]]
    nested += [descriptor["item"]] if "item" in descriptor else []
    return set().union(*map(_path_names, nested)) if nested else set()


def frontend_path_names(descriptor):
    """The descriptor a legacy child records in its v1 signature: path names stay as declared."""
    if isinstance(descriptor, list):
        return [frontend_path_names(item) for item in descriptor]
    if not isinstance(descriptor, dict):
        return descriptor
    renamed = {key: frontend_path_names(value) for key, value in descriptor.items()}
    if descriptor.get("kind") == "path":
        renamed["name"] = descriptor["name"].rsplit("::", 1)[-1]
    return renamed


def recorded_signature_return(child_target, claim, *, bare_paths):
    """Evaluated children record the claim; legacy v1 records keep the child's frontend names."""
    return frontend_path_names(claim) if child_target == "2.24" and bare_paths else claim


def assert_nested_path_envelope(case, parent, refs):
    authority, memo, commit, attempt_root, documents = settled_evidence(parent)
    settlement = commit.data["proof"]["settled_result"]
    assert memo.terminal.data == {"record": "terminal", "outcome": "completed", "value": True}
    assert (commit.data["identity"], commit.data["attempt"]) in memo.settlements
    manifest = _assert_complete_evidence_manifest(attempt_root, settlement=settlement, mode="path")
    value = _expected_value(case, documents["child-request"])
    descriptor = _assert_envelope(case, authority, commit, documents, manifest, value)
    workspace = Path(settlement["workspace_path"])
    _assert_declared_artifacts(case, parent, workspace, value, descriptor, documents["workspace-delta"])
    child_root = workspace / ".orchestrate" / "runs" / documents["child-request"]["child_run_id"]
    if CASES[case]["child_target"] == "2.24":
        _assert_legacy_child(child_root, settlement, documents["child-result"], manifest)
    else:
        _assert_evaluated_child(child_root, settlement, documents["child-result"], manifest, value)
    ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    assert ledger.rows[-1].stage == "committed"
    assert ledger.rows[-1].bindings.evidence_manifest_digest == canonical_sha256(manifest)
    return authority, commit


def _assert_envelope(case, authority, commit, documents, manifest, value):
    envelope = commit.data["value"]
    assert envelope == {"value": value, "workspace_delta": documents["workspace-delta"],
                        "accounting": documents["accounting"]}
    assert canonical_sha256(envelope) == manifest["result_envelope_digest"]
    static = static_config(authority.program)
    descriptor = static.result_descriptor["envelope"]["fields"][0]["type"]
    owner = "shapes" if "modules" not in CASES[case] else "common"
    assert descriptor["name"] == f'{owner}::{CASES[case]["returns"]}'
    assert _path_names(descriptor) == {"common::WorkPath"}
    assert documents["child-result"]["path_compile"]["signature"]["return"] == recorded_signature_return(
        CASES[case]["child_target"], descriptor, bare_paths="modules" in CASES[case])
    assert commit.data["proof"]["artifacts"] == flatten_run_ref_result_artifacts(
        envelope, static.result_descriptor["envelope"])
    return descriptor


def _assert_declared_artifacts(case, parent, workspace, value, descriptor, delta):
    leaves = _expected_leaves(case, value)
    declared = declared_artifacts_from_value(value, descriptor)
    assert [(row.name, row.path) for row in declared] == leaves
    rows = []
    for name, path in leaves:
        child_file = workspace / path
        status = child_file.lstat()
        content = child_file.read_bytes()
        if path == SEED:
            assert content == SEED_BYTES
        else:
            assert path.startswith("artifacts/.run-ref-inputs/") and not (parent / path).exists()
            assert content == PARENT_FILES[Path(path).name]
        rows.append({"name": name, "path": path, "kind": "file", "mode": status.st_mode & 0o7777,
                     "size": len(content), "sha256": "sha256:" + sha256(content).hexdigest(),
                     "link_target": None})
    assert delta["declared_artifacts"] == rows


def _assert_legacy_child(child_root, settlement, result, manifest):
    identity = result["path_compile"]["program_identity"]
    assert result["path_compile"]["evidence"]["program_identity_digest"] == identity["digest"]
    assert result["schema_version"] == "run_ref_path_child_result.v1"
    assert "__result__" not in result["workflow_outputs"]
    assert identity["schema_version"] == "workflow_lisp_program_identity.v2"
    state = (child_root / "state.json").read_bytes()
    assert settlement["child_terminal_state_digest"] == "sha256:" + sha256(state).hexdigest()
    assert manifest["paths"]["child_state"] == (child_root / "state.json").as_posix()


def _assert_evaluated_child(child_root, settlement, result, manifest, value):
    identity = result["path_compile"]["program_identity"]
    assert result["path_compile"]["evidence"]["program_identity_digest"] == identity["digest"]
    assert result["schema_version"] == "run_ref_path_child_result.v2"
    assert result["workflow_outputs"] == {"__result__": value}
    assert identity["schema_version"] == "run_ref_closed_program_identity.v1"
    assert identity["digest"] == canonical_sha256({key: identity[key] for key in identity if key != "digest"})
    header, program, terminal_digest = _evaluated_terminal(child_root)
    assert identity["program_digest"] == header["program_digest"] == program.digest
    assert identity["digest"] != identity["program_digest"]
    assert settlement["child_terminal_state_digest"] == terminal_digest
    assert manifest["paths"]["child_state"] == (child_root / "run.json").as_posix()


def _evaluated_terminal(child_root):
    header, program, memo = ((child_root / name).read_bytes() for name in
                             ("run.json", "closed_program.json", "memo.jsonl"))
    digest = canonical_sha256({
        "domain": "run_ref_evaluated_child_terminal.v1",
        "header_sha256": "sha256:" + sha256(header).hexdigest(),
        "program_sha256": "sha256:" + sha256(program).hexdigest(),
        "memo_sha256": "sha256:" + sha256(memo).hexdigest()})
    return json.loads(header), ClosedProgram.from_artifact(program.decode()), digest


def interrupt_after(monkeypatch, parent, source, refs, inputs, gap):
    """Stop a real public service run at a durable commit or settlement boundary."""
    if gap != "settled":
        return _commit_gap(monkeypatch, parent, source, refs, gap=gap, extra=inputs)
    real_settle = evaluated_runtime.settle_evaluated_run_ref

    def settle_then_stop(*args, **kwargs):
        real_settle(*args, **kwargs)
        raise _InterruptedRun()

    with monkeypatch.context() as context:
        context.setattr(evaluated_runtime, "settle_evaluated_run_ref", settle_then_stop)
        with pytest.raises(_InterruptedRun):
            _service_run(context, parent, source, refs, *inputs)
    authority, snapshot = _authority(parent)
    (commit,) = snapshot.active_commits.values()
    assert (commit.data["identity"], commit.data["attempt"]) in snapshot.settlements
    assert snapshot.terminal is None and not snapshot.unsettled_coordinators
    return authority, snapshot


def tamper_child_evidence(kind, authority, attempt_root, child_root):
    """Change or remove exactly one piece of committed E1 or memo authority in place."""
    delta_path = attempt_root / "workspace-delta.json"
    declared = json.loads(delta_path.read_bytes())["declared_artifacts"][0]["path"]
    artifact = attempt_root / "workspace" / declared
    actions = {
        "artifact": lambda: artifact.write_bytes(b"tampered declared artifact bytes\n"),
        "missing-artifact": artifact.unlink,
        "delta": lambda: _tamper_delta(delta_path),
        "missing-delta": delta_path.unlink,
        "terminal": lambda: _tamper_child_terminal(child_root),
        "missing-terminal": (child_root / "memo.jsonl").unlink,
        "proof": lambda: _rewrite_commit(authority.memo_path, lambda commit: _move_proof_leaf(commit, declared)),
        "missing-proof": lambda: _rewrite_commit(authority.memo_path, lambda commit: commit.pop("proof")),
    }
    actions[kind]()


def _tamper_delta(delta_path):
    delta = json.loads(delta_path.read_bytes())
    delta["declared_artifacts"][0]["size"] += 1
    delta_path.write_bytes(canonical_json_bytes(delta) + b"\n")


def _rewrite_commit(memo_path, change):
    rows = [json.loads(line) for line in memo_path.read_bytes().splitlines()]
    (commit,) = [row for row in rows if row["record"] == "committed"]
    change(commit)
    memo_path.write_bytes(b"".join(json.dumps(row).encode() + b"\n" for row in rows))


def _move_proof_leaf(commit, declared):
    artifacts = commit["proof"]["artifacts"]
    for key in [key for key in artifacts if key == "value" or key.startswith("value__")]:
        artifacts[key] = json.loads(json.dumps(artifacts[key]).replace(declared, "artifacts/elsewhere.txt"))


def _tamper_child_terminal(child_root):
    state = child_root / "state.json"
    if state.exists() and not (child_root / "closed_program.json").exists():
        document = json.loads(state.read_bytes())
        document["workflow_outputs"]["return__variant"] = "NONE"
        state.write_text(json.dumps(document))
        return
    memo = child_root / "memo.jsonl"
    rows = [json.loads(line) for line in memo.read_bytes().splitlines()]
    rows[-1]["value"]["primary"] = "artifacts/elsewhere.txt"
    memo.write_bytes(b"".join(json.dumps(row).encode() + b"\n" for row in rows))


LOCAL_TYPES = ('(defpath LocalPath :kind relpath :under "artifacts" :must-exist true) '
               '(defrecord LocalSolo (primary LocalPath))')


def local_parent_fixture(root, child_target):
    """Parent `controller` declares its path type locally; the child imports a same-named types module."""
    types_module = (f'(workflow-lisp (:language "0.1") (:target-dsl "{child_target}") (defmodule controller) '
                    f'(export LocalPath LocalSolo) {LOCAL_TYPES})')
    parent, source, refs = _public_fixture(root, child_target=child_target, definitions=LOCAL_TYPES,
        child_imports="(import controller :only (LocalPath LocalSolo))", inputs=f'(seed LocalPath :default "{SEED}")',
        child_body="(record LocalSolo :primary seed)", returns="LocalSolo",
        body=lambda call: f"(let* ((child {call})) true)")
    _commit_files(root / "candidate", source, {"controller.orc": types_module, SEED: SEED_BYTES})
    return parent, source, refs, ()


def static_config(program):
    (node,) = site_nodes(program).values()
    return decode_run_ref_static_config(base64.b64decode(node["config"]))
