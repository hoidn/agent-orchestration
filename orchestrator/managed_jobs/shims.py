"""Shim materialization and command parsing for managed jobs."""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_PAYLOADS = {"python", "python3", "torchrun"}
SHIM_NAMES = ("python", "python3", "torchrun", "conda", "uv")


class UnsupportedShimInvocation(ValueError):
    """Raised when a shim invocation is intentionally not managed."""


@dataclass(frozen=True)
class ParsedShimInvocation:
    """Normalized payload selected from a shim invocation."""

    payload_argv: list[str]


def _script_for(shim_name: str) -> str:
    return "\n".join(
        [
            "#!/usr/bin/env sh",
            f"exec \"${{MANAGED_JOB_REAL_PYTHON:-{shlex.quote(sys.executable)}}}\" -m orchestrator.managed_jobs.runner --shim {shlex.quote(shim_name)} -- \"$@\"",
            "",
        ]
    )


def materialize_shims(shim_dir: Path) -> dict[str, Path]:
    """Create deterministic executable shim scripts under a run-owned directory."""

    shim_dir.mkdir(parents=True, exist_ok=True)
    created: dict[str, Path] = {}
    for name in SHIM_NAMES:
        path = shim_dir / name
        path.write_text(_script_for(name), encoding="utf-8")
        path.chmod(path.stat().st_mode | 0o755)
        created[name] = path
    return created


def _consume_option(argv: list[str], index: int) -> int:
    option = argv[index]
    if option in {"-n", "--name", "-p", "--prefix", "--project"}:
        return index + 2
    if option.startswith("-"):
        return index + 1
    return index


def _parse_nested_payload(owner: str, argv: list[str]) -> list[str]:
    index = 0
    while index < len(argv) and argv[index].startswith("-"):
        next_index = _consume_option(argv, index)
        if next_index <= index:
            break
        index = next_index
    if index >= len(argv) or argv[index] not in SUPPORTED_PAYLOADS:
        raise UnsupportedShimInvocation(f"unsupported {owner} payload")
    return [argv[index], *argv[index + 1 :]]


def parse_shim_invocation(shim_name: str, argv: list[str]) -> ParsedShimInvocation:
    """Normalize direct, conda-run, and uv-run shim invocations."""

    if shim_name in {"python", "python3", "torchrun"}:
        return ParsedShimInvocation([shim_name, *argv])
    if shim_name == "conda":
        if not argv or argv[0] != "run":
            raise UnsupportedShimInvocation("unsupported conda invocation")
        return ParsedShimInvocation(_parse_nested_payload("conda", argv[1:]))
    if shim_name == "uv":
        if not argv or argv[0] != "run":
            raise UnsupportedShimInvocation("unsupported uv invocation")
        return ParsedShimInvocation(_parse_nested_payload("uv", argv[1:]))
    raise UnsupportedShimInvocation(f"unsupported shim '{shim_name}'")


def managed_shim_environment(env: dict[str, str], shim_dir: Path) -> dict[str, str]:
    """Return an environment that routes supported launch commands through shims."""

    updated = dict(env)
    updated["MANAGED_JOB_SHIM_DIR"] = str(shim_dir)
    updated.setdefault("MANAGED_JOB_REAL_PYTHON", sys.executable)
    updated["PATH"] = str(shim_dir) + os.pathsep + updated.get("PATH", "")
    return updated
