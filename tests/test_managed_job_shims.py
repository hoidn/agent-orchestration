from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.managed_jobs import provider_guard
from orchestrator.managed_jobs.shims import (
    UnsupportedShimInvocation,
    materialize_shims,
    parse_shim_invocation,
)


def test_materialize_shims_creates_run_owned_executables(tmp_path: Path) -> None:
    shim_dir = tmp_path / "run" / "managed_jobs" / "step" / "1" / "shims"

    created = materialize_shims(shim_dir)

    assert set(created) == {"python", "python3", "torchrun", "conda", "uv"}
    assert (shim_dir / "python").is_file()
    assert "orchestrator.managed_jobs.runner" in (shim_dir / "python").read_text(encoding="utf-8")
    assert (shim_dir / "python").stat().st_mode & 0o111


@pytest.mark.parametrize(
    ("shim", "argv", "expected"),
    [
        ("python", ["scripts/train.py", "--epochs", "1"], ["python", "scripts/train.py", "--epochs", "1"]),
        ("python3", ["scripts/train.py"], ["python3", "scripts/train.py"]),
        ("torchrun", ["--nproc-per-node", "2", "scripts/train.py"], ["torchrun", "--nproc-per-node", "2", "scripts/train.py"]),
        ("conda", ["run", "-n", "env", "python", "scripts/train.py"], ["python", "scripts/train.py"]),
        ("conda", ["run", "--no-capture-output", "-p", "/env", "torchrun", "scripts/train.py"], ["torchrun", "scripts/train.py"]),
        ("uv", ["run", "python", "scripts/train.py"], ["python", "scripts/train.py"]),
        ("uv", ["run", "--project", ".", "torchrun", "scripts/train.py"], ["torchrun", "scripts/train.py"]),
    ],
)
def test_parse_supported_shim_invocations(shim: str, argv: list[str], expected: list[str]) -> None:
    parsed = parse_shim_invocation(shim, argv)

    assert parsed.payload_argv == expected


@pytest.mark.parametrize(
    ("shim", "argv"),
    [
        ("conda", ["activate", "env"]),
        ("conda", ["run", "-n", "env", "bash", "train.sh"]),
        ("uv", ["pip", "install", "x"]),
        ("uv", ["run", "bash", "train.sh"]),
    ],
)
def test_unsupported_conda_and_uv_forms_fail_closed(shim: str, argv: list[str]) -> None:
    with pytest.raises(UnsupportedShimInvocation, match="unsupported"):
        parse_shim_invocation(shim, argv)


def test_provider_guard_materializes_shims_and_exports_environment(tmp_path: Path) -> None:
    seen = {}

    def fake_run(command, *, env):
        seen["command"] = command
        seen["env"] = env

        class Completed:
            returncode = 0

        return Completed()

    shim_dir = tmp_path / "shims"
    with patch("orchestrator.managed_jobs.provider_guard.subprocess.run", fake_run):
        status = provider_guard.main(
            [
                "--policy",
                str(tmp_path / "policy.yaml"),
                "--audit-path",
                str(tmp_path / "audit.jsonl"),
                "--state-root",
                str(tmp_path / "state"),
                "--pending-policy",
                str(tmp_path / "pending.jsonl"),
                "--backend",
                "local",
                "--shim-dir",
                str(shim_dir),
                "--",
                "provider",
            ]
        )

    assert status == 0
    assert seen["env"]["MANAGED_JOB_SHIM_DIR"] == str(shim_dir)
    assert seen["env"]["PATH"].split(":")[0] == str(shim_dir)
    assert (shim_dir / "python").is_file()
