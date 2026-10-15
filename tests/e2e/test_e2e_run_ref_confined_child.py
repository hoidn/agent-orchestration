"""Confined run-ref children end to end: public `orchestrator run` at 2.38 with a real holder.

Task 6c witnesses. The parent compiles a confined `run-ref :program (:workflow ...)`
site whose child runs two command leaves (`python3 write.py`, then `python3
read.py`, which reads the file the first wrote) through `ConfinedChildSession`
and a real `Holder` over the Task 1 image (packed by `run_ref_image_fixture`, imported
into `<run-ref root>/images`). Witnessed: COMPLETED with the expected value, the
clone equal to its last committed checkpoint header, child authority under the
parent run root, the terminal witness over committed command effects (the parent
resume revalidates it), a holder death after a committed effect (a leaf stops the
spawner) settling FAILED with `run_ref_environment_lost` and the clone at its last
header, host time charged in accounting and a tiny `:wall-seconds` settling FAILED
with `run_ref_budget_exhausted`. Provider refusal is qualified by the Increment A
lifecycle test in `test_e2e_run_ref_confined.py`.
Cases skip without ORCHESTRATE_E2E, the CLIs, a user manager or the image record.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.checkpoint import read_checkpoint_header, workspace_manifest
from orchestrator.workflow.run_ref.image_store import import_oci_layout
from tests.e2e.run_ref_fixtures import IMAGE_RECORD, skip_unless_user_manager
from tests.e2e.run_ref_image_fixture import _writable, build_oci_layout

pytestmark = pytest.mark.e2e

REPOSITORY = Path(__file__).resolve().parents[2]
WRITE = 'import os\nopen("out.txt", "w").write("written by leaf one\\n")\n' \
        'open(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], "w").write("3")\n'
READ = 'import os\nn = len(open("out.txt").read())\nopen(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], "w").write(str(n))\n'
STOP = 'import os, signal\nopen("late.txt", "w").write("never checkpointed\\n")\nos.kill(os.getppid(), signal.SIGSTOP)\n'
PARENT = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule controller) (export run)
  (defworkflow candidate-body ((seed Int)) -> Int
    (let* ((first (command-result first :argv ("python3" "write.py") :returns Int))
           (second (command-result second :argv ("python3" "read.py") :returns Int)))
      (+ (+ first second) seed)))
  (defworkflow run ((seed Int) (revision String)) -> String
    (let* ((child (run-ref :source (:repo "REPO" :commit revision)
                    :program (:workflow candidate-body) :inputs (:seed seed)
                    :policy (:environment :confined :image "IMAGE" :network :none
                             :limits (:wall-seconds WALL :memory-mib 1024 :cpus 1 :pids 64
                                      :workspace-mib 32 :output-mib 8)))))
      (match child ((COMPLETED c) "completed") ((FAILED f) f.code)))))'''


@pytest.fixture(scope="module")
def refs(tmp_path_factory):
    """A run-reference root whose image store holds the Task 1 image."""
    skip_unless_user_manager()
    if not IMAGE_RECORD.exists():
        pytest.skip(f"Task 1 image record {IMAGE_RECORD} absent; import it as the feasibility README describes")
    work = tmp_path_factory.mktemp("confined-child")
    image = build_oci_layout(Path(json.loads(IMAGE_RECORD.read_text())["rootfs"]), work / "layout")
    root = work / "refs"
    import_oci_layout(root / "images", image, work / "layout")
    yield root, image
    _writable(root / "images")


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _candidate(root: Path, second: str) -> tuple[Path, str]:
    repository = root / "candidate"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "Run Ref E2E")
    _git(repository, "config", "user.email", "run-ref@example.invalid")
    (repository / "write.py").write_text(WRITE)
    (repository / "read.py").write_text(second)
    _git(repository, "add", ".")
    _git(repository, "commit", "--quiet", "-m", "candidate")
    return repository, _git(repository, "rev-parse", "HEAD")


def _cli(parent: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "orchestrator", *arguments], cwd=parent, capture_output=True,
                          text=True, timeout=600, env={**os.environ, "PYTHONPATH": str(REPOSITORY)})


def _run(tmp_path: Path, refs, *, second: str = READ, wall: int = 120, policy_edit=None):
    root, image = refs
    repository, commit = _candidate(tmp_path, second)
    parent = tmp_path / "parent"
    parent.mkdir()
    source = PARENT.replace("REPO", repository.as_uri()).replace("IMAGE", image).replace("WALL", str(wall))
    (parent / "controller.orc").write_text(policy_edit(source) if policy_edit else source)
    (parent / "boundaries.json").write_text(json.dumps({
        "first": {"stable_command": ["python3", "write.py"], "closure": []},
        "second": {"stable_command": ["python3", "read.py"], "closure": []}}))
    return parent, _cli(parent, "run", "controller.orc", "--entry-workflow", "controller::run",
                        "--command-boundaries-file", "boundaries.json", "--run-ref-root", str(root),
                        "--input", "seed=1", "--input", f"revision={commit}")


def _settled(parent: Path):
    (run_root,) = (parent / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    memo = read_memo(authority.memo_path, site_classes(authority.program))
    (site,) = [entry.data for entry in memo.active_commits.values() if entry.data["effect_class"] == "run_ref"]
    workspace = Path(site["proof"]["settled_result"]["workspace_path"])
    manifest = json.loads((workspace.parent / "evidence-manifest.json").read_bytes())
    return authority, memo, site, workspace, Path(manifest["paths"]["control_root"])


def _clone_digest(workspace: Path) -> str:
    fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
    try:
        return workspace_manifest(fd).digest
    finally:
        os.close(fd)


def _retained_checkpoint(workspace: Path, child_root: Path):
    """Keep the last-checkpoint oracle after the disposable clone/header have been retired."""
    from dataclasses import asdict
    import hashlib
    from orchestrator.workflow.run_ref.checkpoint import CheckpointHeader, _HEADER_SCHEMA
    from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
    from orchestrator.workflow.run_ref.workspace import TreeEntry, manifest_from_entries
    evidence = json.loads((workspace.parent / 'evidence-manifest.json').read_bytes())
    trees = json.loads((workspace.parent / 'retained-trees.json').read_bytes())
    final = manifest_from_entries(TreeEntry(**entry) for entry in trees['final']['entries'])
    assert final.digest == trees['final']['digest'] == evidence['final_workspace_digest']
    commits = list(_child_memo(child_root).active_commits.values())
    last = max(commits, key=lambda entry: entry.offset).data if commits else None
    path = Path(last['result_path']) if last else None
    header = CheckpointHeader('committed', path.parent.parent.name if path else 'none',
                              int(path.parent.name.removeprefix('attempt-')) if path else 0, final.digest)
    encoded = canonical_json_bytes({'schema': _HEADER_SCHEMA, **asdict(header)})
    assert evidence['cleanup_checkpoint']['digest'] == 'sha256:' + hashlib.sha256(encoded).hexdigest()
    assert not workspace.exists() and not (child_root / 'checkpoint.json').exists()
    return header, final


def _child_memo(child_root: Path):
    child = load_run_authority(child_root)
    return read_memo(child.memo_path, site_classes(child.program))


def _scope_units() -> list[str]:
    shown = subprocess.run(["systemctl", "--user", "list-units", "--all", "--plain", "--no-legend", "run-ref-*"],
                           capture_output=True, text=True, timeout=30).stdout
    return [line.split()[0] for line in shown.splitlines() if line.strip()]


def test_two_command_leaves_complete_through_the_public_run(tmp_path, refs):
    parent, completed = _run(tmp_path, refs)
    authority, memo, site, workspace, child_root = _settled(parent)
    header, final = _retained_checkpoint(workspace, child_root)
    budget = json.loads((child_root / "budget.json").read_bytes())
    accounting = site["value"]["result"]["accounting"]
    child_commits = [entry.data["effect_class"] for entry in _child_memo(child_root).active_commits.values()]
    resumed = _cli(parent, "resume", authority.run_root.name, "--run-ref-root", str(refs[0]))

    assert {
        "run": completed.returncode, "terminal": memo.terminal.data["value"],
        "value": site["value"]["result"]["value"], "clone_out": next(row for row in final.entries if row.path == "out.txt").sha256,
        "header": (header.state, header.ordinal), "clone_is_last_header": header.manifest_digest == final.digest,
        "child_root_under_parent_run": child_root.is_relative_to(authority.run_root),
        "no_authority_in_clone": [entry.path for entry in final.entries if entry.path.split("/")[0] == ".orchestrate"],
        "child_commits": child_commits, "resume_revalidates_witness": resumed.returncode,
        "elapsed_is_charged_wall": accounting["elapsed_ms"] == budget["charged_ms"],
        "host_time_charged": budget["host_ms"] > 0, "scopes_left": _scope_units(),
    } == {
        "run": 0, "terminal": "completed", "value": 24, "clone_out": "sha256:" + __import__("hashlib").sha256(b"written by leaf one\n").hexdigest(),
        "header": ("committed", 1), "clone_is_last_header": True, "child_root_under_parent_run": True,
        "no_authority_in_clone": [], "child_commits": ["command", "command"], "resume_revalidates_witness": 0,
        "elapsed_is_charged_wall": True, "host_time_charged": True, "scopes_left": [],
    }, completed.stderr


def test_a_holder_death_after_a_committed_effect_settles_failed_lost(tmp_path, refs):
    parent, completed = _run(tmp_path, refs, second=STOP)
    _authority, memo, site, workspace, child_root = _settled(parent)
    header, final = _retained_checkpoint(workspace, child_root)
    failed = [row.data["code"] for row in _child_memo(child_root).entries if row.data["record"] == "failed"]

    assert {
        "run": completed.returncode, "terminal": memo.terminal.data["value"], "variant": site["value"]["variant"],
        "header": (header.state, header.ordinal), "clone_is_last_header": header.manifest_digest == final.digest,
        "late_file_in_clone": any(entry.path == "late.txt" for entry in final.entries), "child_failed": failed, "scopes_left": _scope_units(),
    } == {
        "run": 0, "terminal": "run_ref_environment_lost", "variant": "FAILED", "header": ("committed", 1),
        "clone_is_last_header": True, "late_file_in_clone": False, "child_failed": ["run_ref_environment_lost"],
        "scopes_left": [],
    }, completed.stderr


def test_a_tiny_wall_budget_settles_failed_budget_exhausted(tmp_path, refs):
    """The second leaf would sleep 5 s; its timeout is clamped to what launch, seeding and leaf one left."""
    parent, completed = _run(tmp_path, refs, wall=1, second="import time\ntime.sleep(5)\n" + READ)
    _authority, memo, site, _workspace, child_root = _settled(parent)
    budget = json.loads((child_root / "budget.json").read_bytes())

    assert (completed.returncode, memo.terminal.data["value"], site["value"]["accounting"]["terminal_status"],
            900 <= budget["charged_ms"] < 5000, budget["host_ms"] > 0, _scope_units()) == (
        0, "run_ref_budget_exhausted", "failed", True, True, []), completed.stderr
