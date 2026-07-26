from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


POLICY_SCHEMA = "provider-phase-isolation-v1.schema.json"
ENVIRONMENT_SCHEMA = "provider-environment-manifest-v1.schema.json"


def test_policy_schema_loads_as_a_packaged_resource_outside_checkout_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    isolation = importlib.import_module("orchestrator.providers.isolation")

    schema = isolation.load_provider_isolation_schema(POLICY_SCHEMA)

    assert schema["$id"].endswith(POLICY_SCHEMA)
    assert schema["properties"]["schema_version"]["const"] == (
        "provider_phase_isolation.v1"
    )


def test_built_wheel_imports_only_installed_package_and_loads_every_schema(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    build_root = tmp_path / "wheel-source"
    wheel_dir = tmp_path / "wheelhouse"
    target = tmp_path / "installed"
    build_root.mkdir()
    wheel_dir.mkdir()
    target.mkdir()
    shutil.copytree(repo_root / "orchestrator", build_root / "orchestrator")
    shutil.copy2(repo_root / "pyproject.toml", build_root / "pyproject.toml")
    shutil.copy2(repo_root / "LICENSE.md", build_root / "LICENSE.md")

    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            str(build_root),
        ],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert build.returncode == 0, build.stdout
    wheels = tuple(wheel_dir.glob("orchestrator-*.whl"))
    assert len(wheels) == 1, build.stdout

    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(target),
            str(wheels[0]),
        ],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert install.returncode == 0, install.stdout

    probe = """
import importlib.resources
import json
from pathlib import Path
import sys

target = Path(sys.argv[1]).resolve()
source = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(target))
import orchestrator

package_path = Path(orchestrator.__file__).resolve()
assert package_path.is_relative_to(target), (package_path, target)
assert not package_path.is_relative_to(source), (package_path, source)
root = importlib.resources.files("orchestrator.providers.schemas")
names = sorted(item.name for item in root.iterdir() if item.name.endswith(".json"))
assert names
for name in names:
    with root.joinpath(name).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
print(json.dumps(names))
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    imported = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            probe,
            str(target),
            str(repo_root),
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert imported.returncode == 0, imported.stdout
    resource_names = json.loads(imported.stdout.strip().splitlines()[-1])
    assert POLICY_SCHEMA in resource_names
    assert ENVIRONMENT_SCHEMA in resource_names
