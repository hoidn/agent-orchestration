"""Closed `prompt import`: exact primary lookup and Task 8 execution reuse."""

from __future__ import annotations

import hashlib
import os
import sys
from argparse import Namespace
from pathlib import Path
from orchestrator.providers.omp_session import OmpSessionError, parse_journal_bytes
from orchestrator.prompt_session import PromptSessionError, ResolvedPrimary, extract_prompt_bytes, resolve_prompt_session

from .prompt import _Captured, prompt_workflow
from .prompt_io import PromptCliError, PromptRunError, _new_reserved_run
from .prompt_run_service import materialize_and_run


def _single(values: list[str] | None, flag: str) -> str | None:
    items = values or []
    if len(items) > 1:
        raise PromptCliError(f"--{flag} must be given at most once")
    return items[0] if items else None


def _parse(args: Namespace) -> dict[str, object]:
    reuse = getattr(args, "reuse_run_contract", 0)
    values = {
        name: _single(getattr(args, name, None), name.replace("_", "-"))
        for name in ("provider", "model", "conf", "returns", "output")
    }
    if reuse:
        if reuse != 1 or any(value is not None for value in values.values()):
            raise PromptCliError("--reuse-run-contract must be the sole mode flag")
        return {"reuse": True}
    provider = values["provider"]
    if provider is None:
        raise PromptCliError("exactly one public --provider is required")
    if provider not in ("omp", "omp_no_tools", "omp_conf", "omp_unrestricted_workspace"):
        raise PromptCliError("provider is not a public OMP provider")
    if provider == "omp_conf" and values["conf"] is None:
        raise PromptCliError("--conf is required for provider omp_conf")
    if provider != "omp_conf" and values["conf"] is not None:
        raise PromptCliError("--conf is only allowed for provider omp_conf")
    if values["returns"] is not None and values["output"] is not None:
        raise PromptCliError("--returns and --output are mutually exclusive")
    for flag in ("model", "conf", "returns", "output"):
        if values[flag] == "":
            raise PromptCliError(f"--{flag} must be a non-empty value")
    return {"reuse": False, **values}


def _new_contract_namespace(mode: dict[str, object], prompt: bytes) -> Namespace:
    return Namespace(
        prompt_command="run",
        prompt=[prompt.decode("utf-8")],
        prompt_file=None,
        provider=[mode["provider"]],
        model=None if mode["model"] is None else [mode["model"]],
        conf=None if mode["conf"] is None else [mode["conf"]],
        returns=None if mode["returns"] is None else [mode["returns"]],
        output=None if mode["output"] is None else [mode["output"]],
        scaffold=None,
    )


def _close_owned(*descriptors: int) -> None:
    first_error = None
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError as exc:
            first_error = first_error or exc
    if first_error is not None:
        raise first_error


def _open_source_private(resolved: ResolvedPrimary) -> tuple[int, int]:
    run_fd = -1
    try:
        run_fd = os.open(
            resolved.run_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        run_stat = os.fstat(run_fd)
        if (run_stat.st_dev, run_stat.st_ino) != resolved.run_identity:
            raise PromptSessionError(
                "prompt_import_invalid", "source run directory identity changed"
            )
        private_fd = os.open(
            "prompt-inputs",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=run_fd,
        )
        return run_fd, private_fd
    except PromptSessionError:
        if run_fd >= 0:
            try:
                _close_owned(run_fd)
            except OSError:
                pass
        raise
    except OSError as exc:
        if run_fd >= 0:
            try:
                _close_owned(run_fd)
            except OSError:
                pass
        raise PromptSessionError(
            "prompt_import_invalid", "source private authority cannot be opened"
        ) from exc


def _verified_private_scaffold(resolved: ResolvedPrimary):
    from orchestrator.prompt_session_scaffold import verify_private_scaffold

    run_fd, private_fd = _open_source_private(resolved)
    try:
        verification = verify_private_scaffold(private_fd, resolved.link)
    finally:
        try:
            _close_owned(private_fd, run_fd)
        except OSError as exc:
            raise PromptSessionError(
                "prompt_import_invalid", "source private authority cannot be closed"
            ) from exc
    captured = _Captured(
        prompt=verification.files["prompt.md"],
        prompt_sha256=resolved.link.document["digests"]["authored_prompt_sha256"],
        provider=verification.provider,
        model=verification.model,
        conf_manifest=None,
        contract_mode="rerun",
        contract_request=None,
        slug="prompt",
    )
    return verification, captured, verification.semantic_contract


def _run_private_reuse(resolved: ResolvedPrimary) -> int:
    verification, captured, contract = _verified_private_scaffold(resolved)
    workspace = Path.cwd()
    runs_root = workspace / ".orchestrate" / "runs"
    run_id, run_root, identity = _new_reserved_run(runs_root, workspace)
    scaffold_workspace = Path(resolved.link.document["workflow_workspace"])
    scaffold_path = scaffold_workspace / resolved.link.document["scaffold_relpath"]
    return materialize_and_run(
        workspace=workspace, runs_root=runs_root, run_id=run_id,
        run_root=run_root, identity=identity, captured=captured,
        contract=contract, verification=verification, print_scaffold=False,
        scaffold_path=scaffold_path, scaffold_workspace=scaffold_workspace,
    )


def prompt_import_workflow(args: Namespace) -> int:
    """Entry for exact linked-primary import; return the process exit code."""
    try:
        mode = _parse(args)
        resolved = resolve_prompt_session(Path.cwd() / ".orchestrate" / "runs", args.session_id)
        try:
            journal = parse_journal_bytes(resolved.journal_bytes, relpath=resolved.primary_basename)
        except OmpSessionError as exc:
            raise PromptSessionError("prompt_import_invalid", "journal is invalid") from exc
        prompt = extract_prompt_bytes(journal)
        if not mode["reuse"]:
            return prompt_workflow(_new_contract_namespace(mode, prompt))
        if hashlib.sha256(prompt).hexdigest() != resolved.link.document["digests"]["composed_prompt_sha256"]:
            raise PromptSessionError("prompt_import_invalid", "composed prompt disagrees")
        return _run_private_reuse(resolved)
    except PromptCliError as exc:
        print(f"prompt import: {exc}", file=sys.stderr)
        return 2
    except (PromptRunError, PromptSessionError) as exc:
        print(f"prompt import: {exc}", file=sys.stderr)
        return 1
