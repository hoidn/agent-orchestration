"""F3b-checkpoint witnesses (Task 5ck) on the throwaway holder.

The approved copier (`orchestrator/workflow/run_ref/checkpoint.py`) runs on the
host between a clone on host disk and the holder's tmpfs `/workspace`, reached
through the root descriptor the harness opens from `/proc/<holder>/root` at
ready. Seeding reproduces the clone in a fresh holder (symlinks as strings,
setuid masked, `.git` left out); a checkpoint after a leaf makes the clone
equal to the tmpfs under a `committed` header; a checkpointing process killed
mid-copy leaves `intent`, which `preflight_checkpoint` repairs to `committed`
by re-freezing. Holder death after a commit and wall charging are Task 6
witnesses; resume repair is Task 7. Fixtures: `tests/e2e/run_ref_fixtures.py`.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.checkpoint import (
    checkpoint_workspace,
    preflight_checkpoint,
    publish_initial_header,
    read_checkpoint_header,
    seed_workspace,
    workspace_manifest,
)
from tests.e2e.run_ref_fixtures import launch, sealed_rootfs  # noqa: F401 (fixtures)
from tests.e2e.run_ref_holder import Holder

pytestmark = pytest.mark.e2e

WORKSPACE_BYTES = 32 << 20  # the harness's /workspace tmpfs size

GUEST_VIEW = r"""
import json, os, stat
view = {}
for directory, dirs, files in os.walk("/workspace"):
    for name in sorted(dirs + files):
        path = os.path.join(directory, name)
        info = os.lstat(path)
        view[os.path.relpath(path, "/workspace")] = [stat.filemode(info.st_mode),
                                                     os.readlink(path) if stat.S_ISLNK(info.st_mode) else None]
print(json.dumps(view, sort_keys=True))
"""

GUEST_EDIT = r"""
import os, sys
os.chdir("/workspace")
step = sys.argv[1]
open("src/main.py", "w").write(f"print('edited in {step}')\n")
os.makedirs(f"new-{step}/deep", exist_ok=True)
open(f"new-{step}/deep/data.bin", "wb").write(os.urandom(4096))
os.symlink("../src/main.py", f"new-{step}/link")
if step == "leaf-1":
    os.remove("notes.txt")
    open("guest-setuid", "w").write("#!/bin/sh\n")
    os.chmod("guest-setuid", 0o4755)
    os.link("src/main.py", "hardlink.py")
    os.mkfifo("pipe")
"""

KILLED_CHECKPOINT = """
import os, sys
from pathlib import Path
from orchestrator.workflow.run_ref import checkpoint
tmpfs_fd, clone, header = int(sys.argv[1]), sys.argv[2], sys.argv[3]
real_fchmod = os.fchmod
def crash(descriptor, mode):
    if os.path.isfile(f"/proc/self/fd/{descriptor}"):
        os.kill(os.getpid(), 9)  # a real kill after the first temporary's bytes, before its rename
    real_fchmod(descriptor, mode)
os.fchmod = crash
destination = os.open(clone, os.O_RDONLY | os.O_DIRECTORY)
checkpoint.checkpoint_workspace(tmpfs_fd, destination, Path(header), effect_identity="effect-2", ordinal=2,
                                max_bytes=int(sys.argv[4]))
"""


def _clone(root: Path) -> Path:
    clone = root / "clone"
    (clone / "src").mkdir(parents=True)
    (clone / "src" / "main.py").write_text("print('base')\n")
    (clone / "notes.txt").write_text("base notes\n")
    (clone / "tool").write_text("#!/bin/sh\necho tool\n")
    os.chmod(clone / "tool", 0o4755)  # setuid on the host clone: masked when seeded
    os.symlink("src/main.py", clone / "entry")
    os.symlink("/etc/hostname", clone / "host-link")  # copied as a string, never followed
    (clone / ".git").mkdir()
    (clone / ".git" / "config").write_text("[core]\n")  # bound read-only in the profile, never copied
    for path, mode in (("src", 0o755), ("src/main.py", 0o644), ("notes.txt", 0o644)):
        os.chmod(clone / path, mode)  # independent of the host umask
    return clone


def _masked(manifest) -> list[tuple]:
    return [(e.path, e.kind, e.mode & 0o777, e.size, e.sha256, e.link_target) for e in manifest.entries]


def _guest_view(holder: Holder) -> dict:
    result = holder.run("view", "exec python3 /run/runref/view/probe.py\n", files={"probe.py": GUEST_VIEW})
    assert result["outcome"] == "exited", result
    return json.loads(result["stdout"])


def _edit(holder: Holder, step: str) -> None:
    result = holder.run(step, f"exec python3 /run/runref/{step}/probe.py {step}\n", files={"probe.py": GUEST_EDIT})
    assert (result["outcome"], result["status"]) == ("exited", 0), result


def _temporaries(clone: Path) -> list[str]:
    return sorted(str(p.relative_to(clone)) for p in clone.rglob(".rr-*.tmp"))


@pytest.fixture
def seeded(launch, tmp_path):
    """A fresh holder seeded from the clone, the clone's root descriptor and its initial header."""
    clone = _clone(tmp_path)
    holder = launch()
    disk = os.open(clone, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    header = tmp_path / "control" / "checkpoint.json"
    header.parent.mkdir(mode=0o700)
    publish_initial_header(header, workspace_manifest(disk).digest)
    seeded = seed_workspace(disk, holder.roots["workspace"], max_bytes=WORKSPACE_BYTES)
    yield {"clone": clone, "holder": holder, "disk": disk, "header": header, "seeded": seeded}
    os.close(disk)


def test_host_seeding_reproduces_the_clone_with_symlinks_preserved_and_setuid_masked(seeded):
    holder, disk = seeded["holder"], seeded["disk"]
    tmpfs = workspace_manifest(holder.roots["workspace"])
    view = _guest_view(holder)

    assert {
        "tmpfs_equals_masked_clone": tmpfs.entries == tuple(
            type(e)(*row) for e, row in zip(workspace_manifest(disk).entries, _masked(workspace_manifest(disk)))),
        "copy_result_is_the_tmpfs_manifest": seeded["seeded"].manifest.digest == tmpfs.digest,
        "clone_keeps_setuid": stat.S_IMODE(os.stat("tool", dir_fd=disk).st_mode),
        "guest_view": view,
        "initial_header": read_checkpoint_header(seeded["header"]).state,
    } == {
        "tmpfs_equals_masked_clone": True,
        "copy_result_is_the_tmpfs_manifest": True,
        "clone_keeps_setuid": 0o4755,
        "guest_view": {"entry": ["lrwxrwxrwx", "src/main.py"], "host-link": ["lrwxrwxrwx", "/etc/hostname"],
                       "notes.txt": ["-rw-r--r--", None], "src": ["drwxr-xr-x", None],
                       "src/main.py": ["-rw-r--r--", None], "tool": ["-rwxr-xr-x", None]},
        "initial_header": "committed",
    }


def test_checkpoint_after_a_leaf_makes_the_clone_equal_to_the_tmpfs_under_a_committed_header(seeded):
    holder, disk, header_path = seeded["holder"], seeded["disk"], seeded["header"]
    _edit(holder, "leaf-1")
    header = checkpoint_workspace(holder.roots["workspace"], disk, header_path, effect_identity="effect-1",
                                  ordinal=1, max_bytes=WORKSPACE_BYTES)
    tmpfs, clone = workspace_manifest(holder.roots["workspace"]), workspace_manifest(disk)
    clone_dir = seeded["clone"]

    assert {
        "header": (header.state, header.effect_identity, header.ordinal, header.skipped_special),
        "header_on_disk": read_checkpoint_header(header_path) == header,
        "header_digest_is_the_clone": header.manifest_digest == clone.digest,
        "clone_equals_masked_tmpfs": _masked(clone) == _masked(tmpfs),
        "guest_setuid_masked_on_clone": stat.S_IMODE(os.stat("guest-setuid", dir_fd=disk).st_mode),
        "removed_and_special": (os.path.lexists(clone_dir / "notes.txt"), os.path.lexists(clone_dir / "pipe")),
        "hardlink_flattened": os.stat("hardlink.py", dir_fd=disk).st_nlink,
        "git_untouched": (clone_dir / ".git" / "config").read_text(),
        "preflight_accepts": preflight_checkpoint(header_path, disk) == header,
    } == {
        "header": ("committed", "effect-1", 1, 1),  # the FIFO is skipped and counted
        "header_on_disk": True,
        "header_digest_is_the_clone": True,
        "clone_equals_masked_tmpfs": True,
        "guest_setuid_masked_on_clone": 0o755,
        "removed_and_special": (False, False),
        "hardlink_flattened": 1,
        "git_untouched": "[core]\n",
        "preflight_accepts": True,
    }


def test_a_checkpoint_killed_mid_copy_leaves_intent_that_preflight_repairs_by_refreezing(seeded):
    holder, disk, header_path, clone_dir = seeded["holder"], seeded["disk"], seeded["header"], seeded["clone"]
    _edit(holder, "leaf-2")
    tmpfs_fd = holder.roots["workspace"]
    killed = subprocess.run(
        [sys.executable, "-c", KILLED_CHECKPOINT, str(tmpfs_fd), str(clone_dir), str(header_path),
         str(WORKSPACE_BYTES)],
        pass_fds=(tmpfs_fd,), env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}, timeout=60)
    after_kill = read_checkpoint_header(header_path)
    temporaries = _temporaries(clone_dir)
    # The kill hit the first file (new-leaf-2/deep/data.bin); src/main.py, later in walk order, is still the base.
    partial = ((clone_dir / "src" / "main.py").read_text(),
               os.path.lexists(clone_dir / "new-leaf-2" / "deep" / "data.bin"))
    repaired = preflight_checkpoint(header_path, disk)

    assert {
        "killed": killed.returncode,
        "after_kill": (after_kill.state, after_kill.effect_identity, after_kill.ordinal, after_kill.manifest_digest),
        "one_temporary_mid_copy": len(temporaries),
        "clone_is_partial": partial,
        "repaired": (repaired.state, repaired.effect_identity, repaired.ordinal),
        "repaired_digest_is_the_refrozen_clone": repaired.manifest_digest == workspace_manifest(disk).digest,
        "temporaries_after_repair": _temporaries(clone_dir),
        "preflight_again_accepts": preflight_checkpoint(header_path, disk) == repaired,
    } == {
        "killed": -9,
        "after_kill": ("intent", "effect-2", 2, None),
        "one_temporary_mid_copy": 1,
        "clone_is_partial": ("print('base')\n", False),
        "repaired": ("committed", "effect-2", 2),
        "repaired_digest_is_the_refrozen_clone": True,
        "temporaries_after_repair": [],
        "preflight_again_accepts": True,
    }
