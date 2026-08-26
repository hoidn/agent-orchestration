"""Descriptor-safe filesystem helpers for ``prompt run`` (Task 8).

Narrowly named sibling of ``orchestrator.cli.commands.prompt``: the
component-wise no-follow conf/run-root openers, the generated-root creator,
run-root reservation, and the inference snapshot materializer.
Everything here raises ``PromptCliError``/``PromptRunError`` (defined here
and re-exported by the CLI module) so admission failures keep the documented
exit codes (2 before any provider call or write, 1 afterwards).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import MappingProxyType

from orchestrator import prompt_scaffold
from orchestrator._common.safe_tree import SafeTreeError, read_regular_file
from orchestrator.providers.omp_conf import admit_conf_tree
from orchestrator.providers.omp_launch_fs import (
    LaunchFsError,
    directory_identity,
    open_dir_no_follow,
)
from orchestrator.prompt_scaffold import (
    ScaffoldSnapshotError,
    ScaffoldVerificationError,
)
from orchestrator.prompt_scaffold_fs import open_generated_root, open_root_creating
from orchestrator.prompt_scaffold_render import wfl_string_literal
from orchestrator.state import StateManager

INFERENCE_PROVIDER = "omp_conf_inference"
_SNAPSHOT_DIR = "prompt-inputs"


class PromptCliError(Exception):
    """Grammar/admission error: exit 2 before provider calls or writes."""


class PromptRunError(Exception):
    """Post-admission failure: scaffold verification, reservation, compile, run."""


def _thaw_frozen(value: object) -> object:
    """Convert frozen result payloads back to plain containers for the
    contract authority (mapping proxies are not dict instances)."""
    if isinstance(value, MappingProxyType):
        return {key: _thaw_frozen(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_frozen(item) for item in value]
    return value


def _read_prompt_file(prompt_path: Path) -> bytes:
    """Read one --prompt-file through its no-follow parent descriptor.

    The parent chain is opened component-wise no-follow and the leaf is
    opened against that dirfd as a regular file, so a symlink or special
    node at ANY position fails closed instead of being followed.
    """
    absolute = os.path.abspath(str(prompt_path))
    try:
        parent_fd = open_dir_no_follow(os.path.dirname(absolute))
    except LaunchFsError as exc:
        raise PromptRunError(
            f"cannot open --prompt-file parent: {exc}") from exc
    try:
        try:
            return read_regular_file(parent_fd, os.path.basename(absolute))
        except SafeTreeError as exc:
            raise PromptRunError(
                f"cannot read --prompt-file {prompt_path}: {exc}") from exc
    finally:
        os.close(parent_fd)


def _admit_conf_dir(conf_path: Path) -> object:
    """Admit a conf tree through component-wise no-follow directory fds."""
    try:
        fd = open_generated_root(conf_path)
    except ScaffoldVerificationError as exc:
        raise PromptRunError(f"cannot open conf {conf_path}: {exc}") from exc
    try:
        return admit_conf_tree(fd)
    except Exception as exc:
        raise PromptRunError(f"conf admission failed for {conf_path}: {exc}") from exc
    finally:
        os.close(fd)


def _create_prompt_inputs_root(
    run_root: Path,
    identity: tuple[int, int],
    *,
    run_root_fd: int | None = None,
) -> tuple[Path, int]:
    if run_root_fd is None:
        try:
            fd = open_generated_root(run_root)
        except ScaffoldVerificationError as exc:
            raise PromptRunError(
                f"cannot open reserved run root {run_root}: {exc}") from exc
    else:
        fd = os.dup(run_root_fd)
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != identity:
            raise PromptRunError(
                f"reserved run root {run_root} changed identity")
        os.mkdir(_SNAPSHOT_DIR, 0o700, dir_fd=fd)
        prompt_inputs_fd = os.open(
            _SNAPSHOT_DIR,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=fd,
        )
    except FileExistsError as exc:
        raise PromptRunError(f"prompt-inputs already exists under {run_root}") from exc
    except OSError as exc:
        raise PromptRunError(
            f"cannot create prompt-inputs under {run_root}: {exc}") from exc
    finally:
        os.close(fd)
    return run_root / _SNAPSHOT_DIR, prompt_inputs_fd


def _ensure_generated_root(workspace: Path) -> Path:
    generated = Path(workspace) / "workflows" / "generated"
    try:
        fd = open_root_creating(generated)
    except ScaffoldSnapshotError as exc:
        raise PromptRunError(
            f"cannot create generated root {generated}: {exc}") from exc
    os.close(fd)
    return generated


def _new_reserved_run(
    runs_root: Path, workspace: Path
) -> tuple[str, Path, tuple[int, int]]:
    """Allocate one run id and exclusively reserve its root under runs_root."""
    run_id = StateManager.new_run_id()
    try:
        run_root = prompt_scaffold.create_run_root(runs_root, run_id)
    except ScaffoldSnapshotError as exc:
        raise PromptRunError(f"run root reservation failed: {exc}") from exc
    try:
        identity = directory_identity(str(run_root))
    except (LaunchFsError, OSError) as exc:
        raise PromptRunError(
            f"reserved run root cannot be inspected: {exc}") from exc
    return run_id, run_root, identity




def _write_bytes_at(directory_fd: int, filename: str, payload: bytes) -> None:
    descriptor = os.open(
        filename,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory_fd,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def _write_inference_snapshot(
    prompt_inputs_fd: int, model: str, inference_prompt: str, asset_path: str
) -> None:
    """Materialize the inference workflow, code-owned prompt, and externs."""
    try:
        workflow_bytes = Path(asset_path).read_bytes()
    except OSError as exc:
        raise PromptRunError(f"cannot read inference asset: {exc}") from exc
    marker = b"      :inputs (task_prompt output_request)\n"
    if workflow_bytes.count(marker) != 1:
        raise PromptRunError(
            "inference asset lacks exactly one typed-input marker; "
            "refusing to run without typed inputs")
    try:
        rendered = workflow_bytes.replace(
            marker,
            (
                f"      :inputs (task_prompt output_request)\n"
                f'      :model "{wfl_string_literal(model)}"\n'
            ).encode("utf-8"),
        )
        _write_bytes_at(
            prompt_inputs_fd, "infer-output-contract.orc", rendered
        )
        _write_bytes_at(
            prompt_inputs_fd, "inference-prompt.md", inference_prompt.encode()
        )
        _write_bytes_at(
            prompt_inputs_fd,
            "providers.json",
            (json.dumps({"providers.inference": INFERENCE_PROVIDER},
                        sort_keys=True) + "\n").encode(),
        )
        _write_bytes_at(
            prompt_inputs_fd,
            "prompts.json",
            (json.dumps(
                {"prompts.inference": {"asset_file": "inference-prompt.md"}},
                sort_keys=True,
            ) + "\n").encode(),
        )
    except ValueError as exc:
        raise PromptRunError(
            f"cannot render the model into the inference workflow: {exc}"
        ) from exc
    except OSError as exc:
        raise PromptRunError(f"cannot materialize inference snapshot: {exc}") from exc
