"""Dispatch side of confined run-ref leaves, against a fake leaf runner.

The fake runner records each LeafRequest and returns a scripted LeafOutcome; it
proves what the dispatch side hands the holder, not confinement itself (that is
the e2e suites' job).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated import interpreters
from orchestrator.workflow.evaluated.authority import load_run_authority, publish_run_authority
from orchestrator.workflow.run_ref.image_store import SealedImage
from tests.test_workflow_evaluated_interpreters import _checked_command_program


IMAGE_DIGEST = "sha256:" + "a" * 64


def _executable(path: Path, content: bytes = b"#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o755)
    return path


@pytest.fixture
def image(tmp_path: Path):
    """A fake sealed rootfs: /bin -> usr/bin, python3 -> python3.12, an absolute link."""
    root = tmp_path / "rootfs"
    _executable(root / "usr/bin/python3.12", b"image python")
    (root / "usr/bin/python3").symlink_to("python3.12")
    (root / "bin").symlink_to("usr/bin")
    _executable(root / "opt/tool/run", b"image tool")
    (root / "usr/bin/tool").symlink_to("/opt/tool/run")
    (root / "usr/bin/scratchy").symlink_to("/tmp/planted")
    for mount in ("workspace", "tmp", "result"):
        (root / mount).mkdir()
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    sealed = SealedImage(fd, {"tree_digest": IMAGE_DIGEST})
    try:
        yield sealed
    finally:
        sealed.close()


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def test_bare_token_pins_through_the_image_path_never_the_host(image) -> None:
    pin = interpreters.pin_image_interpreter(image, "python3")

    assert pin == {"image": IMAGE_DIGEST, "path": "/usr/bin/python3",
                   "resolved": "/usr/bin/python3.12", "digest": _digest(b"image python")}
    with pytest.raises(interpreters.InterpreterError) as excinfo:
        interpreters.pin_image_interpreter(image, "git")  # on the host PATH, not in the image
    assert excinfo.value.code == "run_ref_environment_unavailable"


def test_absolute_image_symlink_resolves_beneath_the_image_root(image) -> None:
    pin = interpreters.pin_image_interpreter(image, "tool")

    assert (pin["path"], pin["resolved"], pin["digest"]) == (
        "/usr/bin/tool", "/opt/tool/run", _digest(b"image tool"))


def test_image_pin_into_guest_scratch_is_refused(image) -> None:
    with pytest.raises(interpreters.InterpreterError) as excinfo:
        interpreters.pin_image_interpreter(image, "scratchy")
    assert excinfo.value.code == "run_ref_environment_unavailable"


def test_image_pin_check_reports_drift_and_host_check_refuses_it(image) -> None:
    pin = interpreters.pin_image_interpreter(image, "python3")

    assert interpreters.check_image_interpreter(pin, image) is None
    moved = SealedImage(image.root_fd, {"tree_digest": "sha256:" + "b" * 64})
    assert interpreters.check_image_interpreter(pin, moved) == "run_ref_environment_changed"
    with pytest.raises(ValueError, match="malformed"):
        interpreters.check_command_interpreter(pin)


@pytest.mark.parametrize("token,expected", [
    ("python3", True), ("/usr/bin/python3", True), ("./run.sh", False), ("scripts/run.sh", False),
    ("/workspace/run.sh", False), ("/tmp/x", False), ("/result/x", False), ("/usr/../tmp/x", False),
])
def test_only_tokens_outside_clone_and_scratch_are_image_resolvable(token, expected) -> None:
    assert interpreters.image_resolvable(token) is expected


def _publish_confined(run_root: Path, program, image) -> None:
    with publish_run_authority(
        run_root, program, run_id=run_root.name, workflow_file="pure.orc",
        workflow_checksum=_digest(b"source"),
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs={}, image=image,
    ):
        pass


def test_confined_header_records_image_pins_and_skips_clone_tokens(
    tmp_path: Path, image, monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = _checked_command_program(tmp_path / "source", entry_sites=(
        ("first", ("python3", "first.py")), ("local", ("./local.sh", "x")),
        ("absolute", ("/usr/bin/tool", "y"))))
    monkeypatch.setenv("PATH", str(tmp_path / "no-host-binaries"))
    run_root = tmp_path / "runs" / "confined"

    _publish_confined(run_root, program, image)
    authority = load_run_authority(run_root)

    pins = authority.header["interpreters"]
    assert sorted(pins) == ["/usr/bin/tool", "python3"]
    assert pins["python3"]["path"] == "/usr/bin/python3"
    assert pins["/usr/bin/tool"]["resolved"] == "/opt/tool/run"


def test_mixed_host_and_image_pins_refuse_on_load(tmp_path: Path, image) -> None:
    program = _checked_command_program(tmp_path / "source", entry_sites=(
        ("first", ("python3", "first.py")), ("absolute", ("/usr/bin/tool", "y"))))
    run_root = tmp_path / "runs" / "mixed"
    _publish_confined(run_root, program, image)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["interpreters"]["python3"] = {"path": "/usr/bin/python3", "digest": _digest(b"host")}
    header_path.write_text(json.dumps(header), encoding="utf-8")

    with pytest.raises(RunAuthorityError):
        load_run_authority(run_root)


# --- dispatch refusals (Q1), image evidence (C4), guest spelling (R2/R3) ---------------

from types import SimpleNamespace  # noqa: E402

from orchestrator.workflow.evaluated import confined_dispatch as cd  # noqa: E402
from orchestrator.workflow.evaluated.authority import RunAuthorityError  # noqa: E402
from orchestrator.workflow.evaluated.commands import CommandPerformerError, command_result  # noqa: E402
from orchestrator.workflow.evaluated.effect_execution import PreparedAttempt, perform_external  # noqa: E402
from orchestrator.workflow.run_ref.leaf import HolderDeath, LeafOutcome  # noqa: E402
from orchestrator.workflow.workspace_files import WorkspaceFiles  # noqa: E402
from tests.test_workflow_evaluated_commands import _checked_command, owners  # noqa: E402,F401


def _node(command, closure=(), kind="command"):
    return {"class": kind, "command": list(command), "closure": [dict(row) for row in closure]}


def _pins(image, *tokens):
    return {token: interpreters.pin_image_interpreter(image, token) for token in tokens}


@pytest.mark.parametrize("command,closure", [
    (("./run.sh",), ()),
    (("/workspace/run.sh",), ()),
    (("/tmp/run.sh",), ()),
    (("python3", "x.py"), ({"base": "workspace", "path": "lib/helper.py"},)),
    (("python3", "-m", "orchestrator.x"), ({"base": "package:orchestrator", "path": "x.py"},)),
    (("python3",), ({"base": "absolute", "path": "/workspace/lib"},)),
    (("unpinned",), ()),
])
def test_clone_resolving_executables_and_closures_refuse_at_dispatch(image, command, closure) -> None:
    pins = _pins(image, "python3")

    with pytest.raises(cd.ConfinedDispatchRefusal) as excinfo:
        cd.require_confinable(_node(command, closure), pins)

    assert excinfo.value.code == "run_ref_environment_effect_unsupported"


def test_providers_refuse_until_the_model_transport_exists(image) -> None:
    with pytest.raises(cd.ConfinedDispatchRefusal) as excinfo:
        cd.require_confinable(_node((), kind="provider"), {})
    assert excinfo.value.code == "run_ref_provider_transport_unavailable"


def test_image_pinned_command_and_closure_are_admitted(image) -> None:
    cd.require_confinable(_node(("python3", "x.py"), ({"base": "absolute", "path": "/opt/tool"},)),
                          _pins(image, "python3"))


def test_retry_and_precommit_evidence_covers_image_pins_only(image, tmp_path: Path) -> None:
    node = _node(("python3", "tests/test_x.py"), ({"base": "absolute", "path": "/opt/tool"},))
    pins = _pins(image, "python3")
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "tests").mkdir()
    (clone / "tests/test_x.py").write_text("before")

    before = cd.image_implementation_files(node, pins, image)
    (clone / "tests/test_x.py").write_text("rewritten by the command")
    after = cd.image_implementation_files(node, pins, image)

    assert before == after
    assert {json.loads(key)[0] for key in before} == {"absolute"}
    assert before['["absolute","/usr/bin/python3",0]']["target"] == "/usr/bin/python3.12"
    assert before['["absolute","/opt/tool",null]']["kind"] == "directory"
    (Path(f"/proc/self/fd/{image.root_fd}") / "opt/tool/run").write_bytes(b"changed image")
    assert cd.image_implementation_files(node, pins, image) != before


def test_guest_spelling_names_the_leaf_result_directory() -> None:
    result_path = "effects/" + "c" * 64 + "/attempt-2/result.json"
    leaf = cd.leaf_id(result_path)

    assert "/" not in leaf and leaf.endswith("attempt-2")
    assert cd.guest_result_path(result_path) == f"/result/{leaf}/result.json"
    assert cd.guest_cwd(Path("/host/clone"), None) == "/workspace"
    assert cd.guest_cwd(Path("/host/clone"), Path("/host/clone/pkg/sub")) == "/workspace/pkg/sub"
    with pytest.raises(cd.ConfinedDispatchRefusal):
        cd.guest_cwd(Path("/host/clone"), Path("/host/elsewhere"))


# --- leaf dispatch through a fake runner -----------------------------------------------

class FakeRunner:
    """Records LeafRequests; returns one scripted LeafOutcome per call."""

    def __init__(self, **outcome):
        self.requests = []
        self.outcome = LeafOutcome(**{
            "exit_code": 0, "timed_out": False, "stdout": b"out", "stderr": b"err",
            "stdout_truncated": False, "stderr_truncated": False,
            "result_files": {"result.json": b'{"count":7}'}, "duration_ms": 5,
            "quiesced_by_exit": True, "holder_death": None, **outcome})

    def run_leaf(self, request):
        self.requests.append(request)
        return self.outcome


RESULT_PATH = "effects/" + "d" * 64 + "/attempt-1/result.json"


def _attempt(owners, image, node, *, runner, kind="command", argv=None, document=None,
             remaining=30.0, launch_cwd=None):
    pins = _pins(image, "python3")
    context = cd.ConfinedLeafContext(runner=runner, image=image, network="none",
                                     remaining_wall_seconds=remaining)
    workspace = owners.workspace_files.workspace
    return PreparedAttempt(
        SimpleNamespace(header={"interpreters": pins}), {**node, "class": kind}, "site", 1,
        RESULT_PATH, "sha256:" + "0" * 64, {}, {}, (),
        (argv or ["python3", "probe.py", "payload"], document), workspace, owners.workspace_files,
        {}, None, owners.attempt_files, launch_cwd, False, context)


def _count_node(owners):
    return _checked_command(owners.workspace_files.workspace,
                            declarations="(defrecord Report (count Int))", return_type="Report",
                            stable_command=("python3", "probe.py"))


def test_confined_command_runs_through_the_leaf_runner_with_guest_values_only(
    owners, image, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOST_SECRET_SENTINEL", "leak")
    node = _count_node(owners)
    (owners.workspace_files.workspace / "pkg").mkdir()
    runner = FakeRunner()

    outcome = perform_external(_attempt(owners, image, node, runner=runner,
                                        launch_cwd=owners.workspace_files.workspace / "pkg"))

    [request] = runner.requests
    leaf = cd.leaf_id(RESULT_PATH)
    assert request.argv == ("/usr/bin/python3", "probe.py", "payload")
    assert request.cwd == "/workspace/pkg"
    assert request.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == f"/result/{leaf}/result.json"
    assert "HOST_SECRET_SENTINEL" not in request.env
    assert not any(str(owners.workspace_files.workspace) in value for value in request.env.values())
    assert (request.leaf_id, request.network, request.timeout_sec) == (leaf, "none", 30.0)
    assert request.input_files == {}
    assert owners.attempt_files.read("stdout.txt") == b"out"
    assert owners.attempt_files.read("stderr.txt") == b"err"
    value, _digest_value = command_result(node, attempt_files=owners.attempt_files,
        workspace_files=owners.workspace_files, result_path=outcome.result_path)
    assert value.json_value() == {"count": 7}


def test_external_input_document_reaches_the_leaf_as_a_result_file(owners, image) -> None:
    node = _count_node(owners)
    runner = FakeRunner()

    perform_external(_attempt(owners, image, node, runner=runner, document=b'{"x":1}'))

    [request] = runner.requests
    assert request.argv[-1] == f"/result/{cd.leaf_id(RESULT_PATH)}/inputs.json"
    assert request.input_files == {"inputs.json": b'{"x":1}'}
    assert owners.attempt_files.read("inputs.json") == b'{"x":1}'


def test_holder_death_fails_the_attempt_with_its_code_and_keeps_streams(owners, image) -> None:
    runner = FakeRunner(exit_code=None, quiesced_by_exit=False, result_files={},
                        holder_death=HolderDeath("run_ref_environment_lost", "spawner nice changed"))

    with pytest.raises(CommandPerformerError) as excinfo:
        perform_external(_attempt(owners, image, _count_node(owners), runner=runner))

    assert excinfo.value.code == "run_ref_environment_lost"
    assert "nice" in str(excinfo.value)
    assert owners.attempt_files.read("stderr.txt") == b"err"


def test_timeout_at_the_wall_clamp_exhausts_the_budget(owners, image) -> None:
    runner = FakeRunner(exit_code=None, timed_out=True, quiesced_by_exit=False)

    with pytest.raises(CommandPerformerError) as excinfo:
        perform_external(_attempt(owners, image, _count_node(owners), runner=runner, remaining=2.5))

    assert excinfo.value.code == "run_ref_budget_exhausted"
    assert runner.requests[0].timeout_sec == 2.5


def test_exhausted_wall_budget_refuses_before_any_leaf(owners, image) -> None:
    runner = FakeRunner()

    with pytest.raises(CommandPerformerError) as excinfo:
        perform_external(_attempt(owners, image, _count_node(owners), runner=runner, remaining=0.0))

    assert excinfo.value.code == "run_ref_budget_exhausted"
    assert runner.requests == []


def test_explicit_timeout_below_the_wall_budget_is_an_ordinary_timeout(owners, image) -> None:
    runner = FakeRunner(exit_code=None, timed_out=True, quiesced_by_exit=False,
                        stdout_truncated=True)
    executor = cd.LeafCommandExecutor(cd.ConfinedLeafContext(runner=runner, image=image,
        network="none", remaining_wall_seconds=60.0), owners.attempt_files, "leaf", {})

    execution = executor.execute_command("evaluated-command", ["/usr/bin/python3"],
        cwd=Path("/workspace"), env={}, timeout_sec=5)

    assert (execution.exit_code, execution.error["type"]) == (124, "timeout")
    assert runner.requests[0].timeout_sec == 5
    assert execution.capture_result.truncated is True
    assert execution.capture_result.debug == {"stdout_truncated": True, "stderr_truncated": False}


def test_confined_provider_and_run_ref_never_reach_a_host_launch(owners, image) -> None:
    runner = FakeRunner()
    for kind, code in (("provider", "run_ref_provider_transport_unavailable"),
                       ("run_ref", "run_ref_environment_effect_unsupported")):
        with pytest.raises(cd.ConfinedDispatchRefusal) as excinfo:
            perform_external(_attempt(owners, image, _count_node(owners), runner=runner, kind=kind))
        assert excinfo.value.code == code
    assert runner.requests == []


def test_dispatch_refuses_a_clone_executable_without_launching(owners, image) -> None:
    runner = FakeRunner()
    node = {**_count_node(owners), "command": ["./probe.sh"]}

    with pytest.raises(cd.ConfinedDispatchRefusal):
        perform_external(_attempt(owners, image, node, runner=runner, argv=["./probe.sh"]))

    assert runner.requests == []


# --- D5 attempt snapshots (P1, Q3, Q5) ---------------------------------------------------

@pytest.fixture
def clone(tmp_path: Path):
    root = tmp_path / "clone"
    (root / "tests").mkdir(parents=True)
    (root / "tests/test_x.py").write_bytes(b"assert True\n")
    (root / "data/nested").mkdir(parents=True)
    (root / "data/a.txt").write_bytes(b"A")
    (root / "data/nested/b.txt").write_bytes(b"B")
    (root / "link").symlink_to("/etc/passwd")
    (root / "linkdir").symlink_to("/etc")
    (root / "pkg").mkdir()
    (root / "top.py").write_bytes(b"top")
    os.mkfifo(root / "pipe")
    files = WorkspaceFiles(root)
    try:
        yield files
    finally:
        files.close()


def _canonical_digest(value) -> str:
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    return canonical_sha256(value)


def test_token_files_bind_by_content_and_symlinks_by_target_string(clone) -> None:
    node = _node(("python3", "tests/test_x.py", "data", "link", "linkdir/hosts", "missing.txt",
                  "-v", "/usr/lib/x", "pipe", "top.py/inner"))

    binding = cd.bind_clone_inputs(cd.command_clone_rows(node, "."), clone, max_bytes=1 << 20)

    assert binding.parts == {
        "clone-file:1:tests/test_x.py": _digest(b"assert True\n"),
        "clone-file:2:data/a.txt": _digest(b"A"),
        "clone-file:2:data/nested/b.txt": _digest(b"B"),
        "clone-link:3:link": _canonical_digest({"symlink": "/etc/passwd"}),
        "clone-link:4:linkdir": _canonical_digest({"symlink": "/etc"}),
    }
    assert {_digest(content) for content in binding.blobs.values()} == set(binding.blobs)
    assert b"root:" not in b"".join(binding.blobs.values())  # the host target is never read


def test_tokens_resolve_from_the_guest_cwd_inside_the_workspace_only(clone) -> None:
    node = _node(("python3", "../top.py", "/workspace/top.py", "../../escape.py"))

    rows = cd.command_clone_rows(node, "pkg")

    assert rows == [("1", "top.py"), ("2", "top.py")]


def test_oversized_token_binding_refuses_before_any_snapshot(clone) -> None:
    with pytest.raises(cd.ConfinedDispatchRefusal) as excinfo:
        cd.bind_clone_inputs([("1", "data")], clone, max_bytes=1)
    assert excinfo.value.code == "run_ref_budget_exhausted"


def test_snapshot_is_allowance_checked_before_copy_and_content_addressed(clone, tmp_path: Path) -> None:
    (tmp_path / "snapshots").mkdir()
    store = WorkspaceFiles(tmp_path / "snapshots")
    binding = cd.bind_clone_inputs([("1", "data"), ("2", "data/a.txt")], clone, max_bytes=1 << 20)
    try:
        with pytest.raises(cd.ConfinedDispatchRefusal) as excinfo:
            cd.store_attempt_snapshot(store, binding.blobs, allowance_bytes=1)
        assert excinfo.value.code == "run_ref_budget_exhausted"
        assert os.listdir(store.root_fd) == []

        assert cd.store_attempt_snapshot(store, binding.blobs, allowance_bytes=2) == 2
        assert cd.store_attempt_snapshot(store, binding.blobs, allowance_bytes=0) == 0
        assert cd.verify_attempt_snapshot(store, {**binding.parts, "argv": "sha256:" + "0" * 64}) == binding.parts
    finally:
        store.close()


@pytest.mark.parametrize("damage", ["tamper", "remove"])
def test_tampered_or_missing_snapshot_fails_closed_not_diverged(clone, tmp_path: Path, damage) -> None:
    (tmp_path / "snapshots").mkdir()
    store = WorkspaceFiles(tmp_path / "snapshots")
    binding = cd.bind_clone_inputs([("1", "tests/test_x.py")], clone, max_bytes=1 << 20)
    try:
        cd.store_attempt_snapshot(store, binding.blobs, allowance_bytes=1 << 20)
        blob = tmp_path / "snapshots" / _digest(b"assert True\n").removeprefix("sha256:")
        blob.write_bytes(b"assert False\n") if damage == "tamper" else blob.unlink()

        with pytest.raises(cd.ConfinedDispatchRefusal) as excinfo:
            cd.verify_attempt_snapshot(store, binding.parts)
        assert excinfo.value.code == "run_ref_environment_changed"
        if damage == "tamper":
            with pytest.raises(cd.ConfinedDispatchRefusal):
                cd.store_attempt_snapshot(store, binding.blobs, allowance_bytes=1 << 20)
    finally:
        store.close()


def test_provider_doc_fills_and_dependencies_name_clone_rows() -> None:
    from orchestrator.workflow.evaluated.providers import provider_dependency_rows

    node = {"inputs": [{"name": "x"}], "prompt": {"fills": [
        {"name": "report", "kind": "doc"}, {"name": "message", "kind": "text"}]},
        "dependencies": {"required": ["req"], "optional": ["opt"]}}

    required, optional = provider_dependency_rows(node, ("in", "docs/r.md", "hi", "a.txt", "b.txt"))

    assert required == [("report", "docs/r.md"), ("required:0", "a.txt")]
    assert optional == [("optional:0", "b.txt")]


def test_a_leaf_that_left_processes_behind_fails_naming_it(owners, image) -> None:
    runner = FakeRunner(exit_code=0, quiesced_by_exit=False, lingered=True)

    with pytest.raises(CommandPerformerError) as excinfo:
        perform_external(_attempt(owners, image, _count_node(owners), runner=runner))

    assert excinfo.value.code == "command_exit_nonzero"
    assert excinfo.value.exit_info["lingered"] is True
    assert "linger" in str(excinfo.value)
