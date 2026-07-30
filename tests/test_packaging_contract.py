from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_built_wheel_excludes_demo_packages_and_model_weights(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    wheel_root = tmp_path / "wheel"
    source_root.mkdir()
    wheel_root.mkdir()
    shutil.copyfile(REPO_ROOT / "pyproject.toml", source_root / "pyproject.toml")
    shutil.copyfile(REPO_ROOT / "LICENSE.md", source_root / "LICENSE.md")
    shutil.copytree(
        REPO_ROOT / "orchestrator",
        source_root / "orchestrator",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    environment = dict(os.environ)
    environment["PIP_NO_INDEX"] = "1"

    built = subprocess.run(
        (
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_root),
            str(source_root),
        ),
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert built.returncode == 0, built.stderr
    wheels = tuple(wheel_root.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        members = archive.namelist()
    assert not any(member.startswith("orchestrator/demo/") for member in members)
    assert not any(member.endswith(".pt") for member in members)
