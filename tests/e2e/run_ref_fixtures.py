"""Shared fixtures for the run-ref holder e2e modules (throwaway F3b evidence).

`sealed_rootfs` (module scope) skips without ORCHESTRATE_E2E, the CLIs or a
reachable user systemd manager, and when the Task 1 image record is absent
(fails instead with RUN_REF_REQUIRE_IMAGE=1); it rehashes the cached rootfs
against the pinned `TREE_DIGEST`. `launch` starts `Holder`s and stops every
one at teardown, asserting that no scope stays populated.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e
from tests.e2e.run_ref_holder import Holder

# Task 1 image (docs/reports/run-ref-confinement-feasibility/README.md, F3).
IMAGE_RECORD = Path.home() / ".cache/run-ref-spike-images/records" / (
    "sha256-2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe.json")
TREE_DIGEST = "sha256:973cd37339e7ef7627c497292983fa6b110ef784f121f41d8a52edc6385fadae"  # pinned, not read from the cache


def tree_digest(rootfs: Path) -> str:
    """Canonical digest of the sealed tree, as recorded by the Task 1 importer."""
    rows = []
    for directory, dirs, files in os.walk(rootfs):
        dirs.sort()
        for name in sorted(dirs + files):
            path = Path(directory, name)
            rel = path.relative_to(rootfs).as_posix()
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                rows.append([rel, "symlink", os.readlink(path)])
            elif stat.S_ISDIR(info.st_mode):
                rows.append([rel, "dir", stat.S_IMODE(info.st_mode)])
            else:
                rows.append([rel, "file", stat.S_IMODE(info.st_mode), info.st_size,
                             hashlib.sha256(path.read_bytes()).hexdigest()])
    return "sha256:" + hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def skip_unless_user_manager() -> None:
    skip_if_no_e2e()
    for command in ("bwrap", "systemd-run", "systemctl"):
        skip_if_no_cli(command)
    if subprocess.run(["systemctl", "--user", "show", "-p", "Version"], capture_output=True,
                      timeout=15).returncode != 0:
        pytest.skip("user systemd manager unreachable")


@pytest.fixture(scope="module")
def sealed_rootfs() -> Path:
    skip_unless_user_manager()
    if not IMAGE_RECORD.exists():
        message = f"Task 1 image record {IMAGE_RECORD} absent; import it as the feasibility README describes"
        if os.getenv("RUN_REF_REQUIRE_IMAGE") == "1":
            pytest.fail(message)
        pytest.skip(message)
    rootfs = Path(json.loads(IMAGE_RECORD.read_text())["rootfs"])
    assert tree_digest(rootfs) == TREE_DIGEST, "sealed rootfs does not match the pinned tree digest"
    return rootfs


@pytest.fixture
def launch(sealed_rootfs, tmp_path):
    started: list[Holder] = []

    def _launch(release: str | None = "token", **limits) -> Holder:
        holder = Holder(sealed_rootfs, tmp_path, **limits)
        started.append(holder)
        return holder.launch(release=release)

    yield _launch
    reports, errors = [], []
    for holder in started:  # stop every holder even when one stop raises
        try:
            reports.append((holder.unit, holder.stop()))
        except Exception as exc:  # re-raised below after the remaining holders are stopped
            errors.append((holder.unit, exc))
    if errors:
        unit, exc = errors[0]
        raise RuntimeError(f"stopping holder {unit} failed ({len(errors)} of {len(started)} stops failed)") from exc
    assert [unit for unit, report in reports if report.get("scope_populated")] == []
