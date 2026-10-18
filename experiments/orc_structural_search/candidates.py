"""Candidate identity, immutable snapshots and compilation through the ordinary `orchestrator compile` CLI.

A candidate is a directory. `.orchestrate/` (the compiler's build cache) is derived, not content.
`compile_candidate` runs this checkout's orchestrator (`python -P -m orchestrator` with PYTHONPATH set to the
repository root) with cwd=root, so the build cache lands inside the candidate.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from experiments.orc_structural_search.config import ExperimentConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_CACHE = ".orchestrate"


@dataclass(frozen=True)
class CompileOutcome:
    status: str  # "accepted" | "rejected"
    build_key: str | None
    program_digest: str | None
    diagnostics: tuple[dict, ...]


def candidate_id(root: Path, *, orchestrator_commit: str) -> str:
    """sha256 over every regular file (relative path, NUL, bytes) in sorted order, then the commit."""
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.relative_to(root).parts[0] != BUILD_CACHE)
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    digest.update(orchestrator_commit.encode())
    return f"sha256:{digest.hexdigest()}"


def snapshot(parent: Path, edited_files: Mapping[str, bytes], dest: Path) -> Path:
    """Copy `parent` to a new `dest` and overwrite the edited files there; `parent` is never written."""
    shutil.copytree(parent, dest, ignore=shutil.ignore_patterns(BUILD_CACHE))  # FileExistsError if dest exists
    for name, data in edited_files.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return dest


def compile_candidate(root: Path, config: ExperimentConfig) -> CompileOutcome:
    source_root = root / config.source_root
    module = config.entry_workflow.split("::")[0]
    command = [
        sys.executable, "-P", "-m", "orchestrator", "compile", str((source_root / module).with_suffix(".orc")),
        "--entry-workflow", config.entry_workflow,
        "--source-root", str(source_root),
        "--provider-externs-file", str(root / config.providers_file),
    ]
    if config.command_boundaries_file is not None:
        command += ["--command-boundaries-file", str(root / config.command_boundaries_file)]
    command.append("--diagnostics-json")
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    if not lines:
        raise RuntimeError(f"compile printed nothing (exit {result.returncode}): {result.stderr}")
    document = json.loads(lines[-1])
    if document.get("status") == "accepted" and result.returncode == 0:
        return CompileOutcome("accepted", document["build_key"], document["program_digest"], ())
    if document.get("status") == "rejected" and result.returncode != 0:
        return CompileOutcome("rejected", None, None, tuple(document["diagnostics"]))
    raise RuntimeError(f"unexpected compile result (exit {result.returncode}): {lines[-1]}")
