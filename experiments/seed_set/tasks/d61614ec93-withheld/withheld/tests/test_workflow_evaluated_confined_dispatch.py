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




