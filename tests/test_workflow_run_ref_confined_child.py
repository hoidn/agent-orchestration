"""Confined run-ref children through the public run, with a host fake standing in for the holder.

The parent program runs in-process through `orchestrator run` (2.38); the child's
commands dispatch through `ConfinedChildSession`, whose `Holder` is replaced by
`FakeHolder`: leaves are host processes in a scratch `/workspace`, while seeding and
checkpoints run the real copier helper. This proves the wiring (lifecycle stages,
settlement, FAILED, budget charging, refusals), not confinement: real holders are
exercised in tests/e2e/test_e2e_run_ref_confined_child.py.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import time
import tempfile
import secrets

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref import confined_lifecycle, confined_session, image_store
from orchestrator.workflow.run_ref.checkpoint import read_checkpoint_header, workspace_manifest
from orchestrator.workflow.run_ref.confinement import HostFacts
from orchestrator.workflow.run_ref.leaf import HolderDeath, LeafOutcome
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
from tests.test_workflow_run_ref_confinement import _oci_layout, _removable_tmp  # noqa: F401

HOST = HostFacts(bwrap=True, systemd_run=True, ptrace_scope=1, machine="x86_64")
FIRST = 'echo first > out.txt; echo 3 > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"'
SECOND = 'test -f out.txt && echo 4 > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"'
PARENT = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule controller) (export run)
  (defworkflow candidate-body ((seed Int)) -> Int
    (let* ((first (command-result first :argv ("FIRST_EXE" "first.sh") :returns Int))
           (second (command-result second :argv ("sh" "second.sh") :returns Int)))
      (+ (+ first second) seed)))
  (defworkflow run ((seed Int) (revision String)) -> String
    (let* ((child (run-ref :source (:repo "REPO" :commit revision)
                    :program (:workflow candidate-body) :inputs (:seed seed)
                    :policy (:environment :confined :image "IMAGE" :network :none
                             :limits (:wall-seconds WALL :memory-mib 1024 :cpus 1 :pids 64
                                      :workspace-mib 64 :output-mib 8)))))
      (match child ((COMPLETED c) "completed") ((FAILED f) f.code)))))'''


class FakeHolder:
    """`Holder` stand-in: host processes in a scratch `/workspace`; the real copier for host helpers."""

    launched: list["FakeHolder"] = []
    launch_error: RunRefRuntimeError | None = None
    leaf_seconds = 0.0
    helper_seconds = 0.0
    leaves: list[str] = []

    def __init__(self, image, limits, *, control_dir, git_dir_fd=None):
        self.control_dir = Path(control_dir)
        scratch = Path(tempfile.mkdtemp(prefix="fake-", dir=control_dir))
        self.workspace, self.result = scratch / "fake-workspace", scratch / "fake-result"
        self.workspace.mkdir()
        self.result.mkdir()
        self.fd = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY)
        self.stopped = False

    def launch(self):
        if FakeHolder.launch_error is not None:
            raise FakeHolder.launch_error
        from orchestrator.providers.isolation_backend import DurableLaunchReleaseGate
        from orchestrator.workflow.run_ref.confined_budget import boot_id
        from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
        token = secrets.token_hex(32)
        identity = "sha256:" + "b" * 64
        (self.control_dir / f"scope-{token[:16]}.json").write_bytes(canonical_json_bytes({
            "schema_version": "run_ref_holder_scope.v1", "boot_id": boot_id(),
            "scope_path": f"/sys/fs/cgroup/run-ref-{token[:16]}.scope", "unit": f"run-ref-{token[:16]}.scope",
            "launch_token": "sha256:" + token, "containment_identity": identity}))
        gate = DurableLaunchReleaseGate.create(self.control_dir / f"holder-release-{token[:16]}.json",
            launch_token="sha256:" + token, containment_identity=identity)
        gate.record_intent()
        gate.consume_release(gate.record_commit())
        FakeHolder.launched.append(self)
        return self

    def root_fd(self, mount):
        return self.fd

    def run_host_helper(self, argv, *, pass_fds, timeout_sec):
        time.sleep(FakeHolder.helper_seconds)
        return subprocess.run(argv, pass_fds=pass_fds, capture_output=True, timeout=timeout_sec, check=False)

    def run_leaf(self, request):
        FakeHolder.leaves.append(request.leaf_id)
        (self.result / request.leaf_id).mkdir()
        env = {name: value.replace("/result/", f"{self.result}/") for name, value in request.env.items()}
        started = time.monotonic()
        done = subprocess.run(["/bin/sh", request.argv[-1]], cwd=self.workspace, env=env, capture_output=True,
                              timeout=request.timeout_sec, check=False)
        if "kill-the-holder" in (self.workspace / request.argv[-1]).read_text():
            return LeafOutcome(exit_code=None, timed_out=False, stdout=b"", stderr=b"", stdout_truncated=False,
                               stderr_truncated=False, result_files={}, duration_ms=1, quiesced_by_exit=False,
                               holder_death=HolderDeath("run_ref_environment_lost", "spawner stopped"))
        time.sleep(FakeHolder.leaf_seconds)
        files = {path.name: path.read_bytes() for path in (self.result / request.leaf_id).iterdir()}
        return LeafOutcome(exit_code=done.returncode, timed_out=False, stdout=done.stdout, stderr=done.stderr,
                           stdout_truncated=False, stderr_truncated=False, result_files=files,
                           duration_ms=int((time.monotonic() - started) * 1000), quiesced_by_exit=True,
                           holder_death=None)

    def stop(self):
        if not self.stopped:
            self.stopped = True
            os.close(self.fd)


@pytest.fixture
def world(tmp_path, monkeypatch):
    layout, image = _oci_layout(tmp_path)
    refs = tmp_path / "refs"
    image_store.import_oci_layout(refs / confined_lifecycle.IMAGES_DIRNAME, image, layout)
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "boundaries.json").write_text(json.dumps({
        name: {"stable_command": ["sh", f"{name}.sh"], "closure": []} for name in ("first", "second")}))
    monkeypatch.setattr(confined_session, "Holder", FakeHolder)
    monkeypatch.setattr(confined_lifecycle, "probe_host", lambda: HOST)
    monkeypatch.setattr(FakeHolder, "launched", [])
    monkeypatch.setattr(FakeHolder, "launch_error", None)
    monkeypatch.setattr(FakeHolder, "leaf_seconds", 0.0)
    monkeypatch.setattr(FakeHolder, "helper_seconds", 0.0)
    monkeypatch.setattr(FakeHolder, "leaves", [])
    monkeypatch.chdir(parent)
    return {"parent": parent, "refs": refs, "repository": tmp_path / "repository", "image": image}


def _write(world, *, first=FIRST, second=SECOND, wall=60, first_exe="sh"):
    """The candidate repository carries the two leaf scripts; the parent pins its commit."""
    repository = world["repository"]
    git = lambda *args: subprocess.run(["git", "-C", str(repository), *args], check=True,  # noqa: E731
                                       capture_output=True, text=True).stdout.strip()
    repository.mkdir()
    git("init", "--quiet")
    git("config", "user.name", "Run Ref Test")
    git("config", "user.email", "run-ref@example.invalid")
    (repository / "first.sh").write_text(first + "\n")
    (repository / "second.sh").write_text(second + "\n")
    git("add", ".")
    git("commit", "--quiet", "-m", "candidate")
    world["commit"] = git("rev-parse", "HEAD")
    if first_exe != "sh":
        boundaries = json.loads((world["parent"] / "boundaries.json").read_text())
        boundaries["first"]["stable_command"] = [first_exe, "first.sh"]
        (world["parent"] / "boundaries.json").write_text(json.dumps(boundaries))
    source = (PARENT.replace("FIRST_EXE", first_exe).replace("REPO", repository.as_uri())
              .replace("IMAGE", world["image"]).replace("WALL", str(wall)))
    (world["parent"] / "controller.orc").write_text(source)


def _cli(*arguments: str) -> int:
    from orchestrator.cli.main import main

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return main(list(arguments))


def _child_memo(child_root):
    child = load_run_authority(child_root)
    return read_memo(child.memo_path, site_classes(child.program))


def _run(world, **edits) -> tuple[int, object]:
    _write(world, **edits)
    status = _cli("run", "controller.orc", "--entry-workflow", "controller::run", "--command-boundaries-file",
                  "boundaries.json", "--run-ref-root", str(world["refs"]),
                  "--input", "seed=1", "--input", f"revision={world['commit']}")
    runs = world["parent"] / ".orchestrate" / "runs"
    if not runs.exists():
        return status, None
    (run_root,) = runs.iterdir()
    authority = load_run_authority(run_root)
    return status, (authority, read_memo(authority.memo_path, site_classes(authority.program)))


def _site(memo):
    (commit,) = [entry for entry in memo.active_commits.values() if entry.data["effect_class"] == "run_ref"]
    return commit.data


def _attempt(site):
    workspace = Path(site["proof"]["settled_result"]["workspace_path"])
    child_root = Path(json.loads((workspace.parent / "evidence-manifest.json").read_bytes())["paths"]["control_root"])
    return workspace, child_root


def _defer_cleanup(monkeypatch):
    """Keep live-state fixtures at the durable settlement / cleanup boundary."""
    from orchestrator.workflow.evaluated import run_ref
    monkeypatch.setattr(run_ref, '_cleanup_if_confined', lambda *args: None)


def _observe_cleanup(monkeypatch):
    from orchestrator.workflow.run_ref import confined_cleanup
    from orchestrator.workflow.run_ref.confined_lifecycle import _layout
    real = confined_cleanup.cleanup_settled
    captures = {}
    def observe(request, **kwargs):
        ordinal = load_attempt_ledger(request.ledger_path).rows[-1].attempt_ordinal
        layout = _layout(request, ordinal)
        fd = os.open(layout.workspace, os.O_RDONLY | os.O_DIRECTORY)
        try:
            captures[layout.child_root] = dict(header=read_checkpoint_header(layout.child_root / 'checkpoint.json'),
                manifest=workspace_manifest(fd), names=sorted(path.name for path in layout.workspace.iterdir()),
                out=(layout.workspace / 'out.txt').read_text() if (layout.workspace / 'out.txt').exists() else None,
                identity=(os.fstat(fd).st_dev, os.fstat(fd).st_ino))
        finally:
            os.close(fd)
        return real(request, **kwargs)
    monkeypatch.setattr(confined_cleanup, 'cleanup_settled', observe)
    return captures


def test_two_command_leaves_complete_and_settle_through_the_lifecycle(world, monkeypatch):
    captures = _observe_cleanup(monkeypatch)
    status, (authority, memo) = _run(world)
    site = _site(memo)
    workspace, child_root = _attempt(site)
    captured = captures[child_root]
    header, clone_digest = captured['header'], captured['manifest'].digest
    recipe = json.loads((child_root / 'child-recipe.json').read_bytes())
    assert captured['identity'] == (recipe['owned_roots']['clone']['device'], recipe['owned_roots']['clone']['inode'])
    assert not workspace.exists() and not (child_root / 'checkpoint.json').exists()
    ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    budget = json.loads((child_root / "budget.json").read_bytes())
    result = site["value"]["result"]
    started = [entry.data["input_parts"] for entry in _child_memo(child_root).entries
               if entry.data["record"] == "started"]

    assert {
        "status": status, "terminal": memo.terminal.data["value"], "variant": site["value"]["variant"],
        "value": result["value"], "settled": (site["identity"], site["attempt"]) in memo.settlements,
        "stages": [row.stage for row in ledger.rows if row.event_kind == "progress"][-2:],
        "clone_out": captured["out"], "header": (header.state, header.ordinal),
        "clone_is_last_header": header.manifest_digest == clone_digest,
        "child_root_under_parent": child_root.parent == authority.run_root / "run-ref-children",
        "untracked": [row["path"] for row in result["workspace_delta"]["untracked_files"]],
        "elapsed_is_charged_wall": result["accounting"]["elapsed_ms"] == budget["charged_ms"],
        "host_time_charged": budget["host_ms"] > 0, "holders": len(FakeHolder.launched),
        "holder_stopped": FakeHolder.launched[0].stopped,
        "scripts_bound_at_started": [sorted(name for name in parts if name.startswith("clone-")) for parts in started],
    } == {
        "status": 0, "terminal": "completed", "variant": "COMPLETED", "value": 8, "settled": True,
        "stages": ["completed_pending_parent_commit", "committed"],
        "clone_out": "first\n", "header": ("committed", 1), "clone_is_last_header": True,
        "child_root_under_parent": True, "untracked": ["out.txt"], "elapsed_is_charged_wall": True,
        "host_time_charged": True, "holders": 1, "holder_stopped": True,
        "scripts_bound_at_started": [["clone-file:1:first.sh"], ["clone-file:1:second.sh"]],
    }


def test_completed_parent_resume_revalidates_the_confined_result_without_a_holder(world):
    status, (authority, _memo) = _run(world)
    FakeHolder.launched.clear()

    resumed = _cli("resume", authority.run_root.name, "--run-ref-root", str(world["refs"]))

    assert (status, resumed, FakeHolder.launched) == (0, 0, [])


def test_a_tampered_attempt_snapshot_refuses_the_parent_resume(world):
    _status, (authority, memo) = _run(world)
    _workspace, child_root = _attempt(_site(memo))
    blob = next((child_root / "snapshots").iterdir())
    blob.write_bytes(b"echo tampered\n")

    assert _cli("resume", authority.run_root.name, "--run-ref-root", str(world["refs"])) != 0


def test_a_holder_death_after_a_committed_effect_settles_failed_with_the_clone_at_its_header(world, monkeypatch):
    captures = _observe_cleanup(monkeypatch)
    status, (_authority, memo) = _run(world, second="touch late.txt # kill-the-holder")
    site = _site(memo)
    workspace, child_root = _attempt(site)
    captured = captures[child_root]
    header = captured['header']
    assert not workspace.exists() and not (child_root / 'checkpoint.json').exists()
    child_memo = _child_memo(child_root)

    assert {
        "status": status, "terminal": memo.terminal.data["value"],
        "failed": {key: site["value"][key] for key in ("variant", "code")},
        "terminal_status": site["value"]["accounting"]["terminal_status"],
        "clone": captured["names"], "header": (header.state, header.ordinal),
        "child_failed": [row.data["code"] for row in child_memo.entries if row.data["record"] == "failed"],
    } == {
        "status": 0, "terminal": "run_ref_environment_lost",
        "failed": {"variant": "FAILED", "code": "run_ref_environment_lost"}, "terminal_status": "failed",
        "clone": [".git", "first.sh", "out.txt", "second.sh"], "header": ("committed", 1),
        "child_failed": ["run_ref_environment_lost"],
    }


def test_a_tiny_wall_budget_settles_failed_budget_exhausted(world):
    FakeHolder.leaf_seconds = 1.2

    status, (_authority, memo) = _run(world, wall=1)

    assert (status, memo.terminal.data["value"], _site(memo)["value"]["variant"]) == (
        0, "run_ref_budget_exhausted", "FAILED")


def test_host_work_is_charged_to_the_wall_budget(world):
    FakeHolder.helper_seconds = 1.2  # the seeding helper alone outlasts :wall-seconds 1

    status, (_authority, memo) = _run(world, wall=1)

    assert (status, memo.terminal.data["value"], FakeHolder.leaves) == (0, "run_ref_budget_exhausted", [])


def test_a_clone_resolving_executable_is_refused_before_started_and_settles_failed(world):
    status, (_authority, memo) = _run(world, first_exe="./tool.sh")

    assert (status, memo.terminal.data["value"], FakeHolder.launched) == (
        0, "run_ref_environment_effect_unsupported", [])


def test_a_leaf_writing_a_reserved_root_fails_its_checkpoint_as_escape_after_refreezing(world, monkeypatch):
    captures = _observe_cleanup(monkeypatch)
    status, (_authority, memo) = _run(world, first='mkdir .orchestrate; echo 3 > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"')
    _workspace, child_root = _attempt(_site(memo))

    assert (status, memo.terminal.data["value"], captures[child_root]["header"].state) == (
        0, "run_ref_environment_escape_rejected", "committed")


def test_a_launch_refused_before_release_aborts_the_parent_effect(world):
    FakeHolder.launch_error = RunRefRuntimeError("run_ref_environment_unavailable", "scope_not_delegated")

    status, (_authority, memo) = _run(world)

    assert (status, memo.terminal.data["outcome"], memo.terminal.data["code"],
            [entry for entry in memo.active_commits.values()]) == (
        1, "failed", "run_ref_environment_unavailable", [])


def test_a_provider_child_is_refused_before_any_run_state_or_holder(world):
    _write(world)
    (world["parent"] / "providers.json").write_text(json.dumps({"providers.review": "probe-provider"}))
    source = (world["parent"] / "controller.orc").read_text().replace(
        '(command-result first :argv ("sh" "first.sh") :returns Int)',
        "(provider-result providers.review :prompt prompts.base :inputs (seed) :returns Int)")
    (world["parent"] / "controller.orc").write_text(source.replace(":network :none", ":network :model-only"))
    (world["parent"] / "prompt.md").write_text("review\n")
    (world["parent"] / "prompts.json").write_text(json.dumps({"prompts.base": "prompt.md"}))

    status = _cli("run", "controller.orc", "--entry-workflow", "controller::run", "--command-boundaries-file",
                  "boundaries.json", "--provider-externs-file", "providers.json", "--prompt-externs-file",
                  "prompts.json", "--run-ref-root", str(world["refs"]),
                  "--input", "seed=1", "--input", f"revision={world['commit']}")

    assert (status, (world["parent"] / ".orchestrate" / "runs").exists(), FakeHolder.launched) == (2, False, [])


def _rebuilt_child(world, authority, site):
    """Admission and the reused provisioning of the settled attempt, as a resume would see them."""
    from base64 import b64decode

    from orchestrator.workflow.evaluated.machine import site_nodes
    from orchestrator.workflow.run_ref.confined_config import decode_run_ref_confined_static_config
    from orchestrator.workflow.run_ref.confinement import (
        admit_confined_child, confined_attempt_layout, provision_confined_child)
    from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
    from orchestrator.workflow.run_ref.wire import confined_child_request

    [node] = [node for node in site_nodes(authority.program).values() if node["class"] == "run_ref"]
    config = decode_run_ref_confined_static_config(b64decode(node["config"]))
    inputs = {"seed": 1}
    request = confined_child_request(config, commit=world["commit"], inputs=inputs)
    admission = admit_confined_child(config, request, commit=world["commit"], inputs=inputs,
                                     parent_program=authority.program,
                                     image_store=world["refs"] / confined_lifecycle.IMAGES_DIRNAME, host=HOST)
    visit = RunRefVisitKey(**site["proof"]["settled_result"]["visit"])
    layout = confined_attempt_layout(run_ref_root=world["refs"], parent_run_root=authority.run_root, visit=visit,
                                     attempt_ordinal=site["proof"]["settled_result"]["attempt_ordinal"],
                                     config=config)
    return admission, provision_confined_child(admission, layout, run_ref_root=world["refs"],
                                               parent_run_root=authority.run_root,
                                               parent_workspace=world["parent"])


def test_a_reused_attempt_is_checked_against_its_last_checkpoint_not_its_baseline(world, monkeypatch):
    _defer_cleanup(monkeypatch)
    _status, (authority, memo) = _run(world)
    workspace, _child_root = _attempt(_site(memo))
    admission, provisioned = _rebuilt_child(world, authority, _site(memo))
    admission.close()
    (workspace / "out.txt").write_text("edited on the host\n")

    with pytest.raises(RunRefRuntimeError) as caught:
        _rebuilt_child(world, authority, _site(memo))

    assert (provisioned.layout.workspace, caught.value.code) == (workspace, "run_ref_environment_changed")


def test_resume_of_the_child_refuses_image_pins_that_drifted(world, monkeypatch):
    from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
    from orchestrator.workflow.run_ref.evaluated_child import execute_confined_child

    _defer_cleanup(monkeypatch)
    _status, (authority, memo) = _run(world)
    _workspace, child_root = _attempt(_site(memo))
    header = json.loads((child_root / "run.json").read_bytes())
    for pin in header["interpreters"].values():
        pin["digest"] = "sha256:" + "0" * 64
    (child_root / "run.json").write_bytes(canonical_json_bytes(header))
    admission, provisioned = _rebuilt_child(world, authority, _site(memo))
    try:
        with pytest.raises(RunRefRuntimeError) as caught:
            execute_confined_child(admission, provisioned, run_ref_root=world["refs"])
    finally:
        admission.close()

    assert (sorted(header["interpreters"]), caught.value.code) == (["sh"], "run_ref_environment_changed")
