"""One-dispatch performer for checked Workflow Lisp command effects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import os
from pathlib import Path
from importlib.machinery import PathFinder
from typing import Any

from orchestrator.contracts.output_contract import (
    _load_bundle_json,
    _validate_output_bundle_document_bytes,
    _validate_variant_output_bundle_document_bytes,
)
from orchestrator.exec.output_capture import CaptureMode
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.workflow.workspace_files import WorkspaceFiles

from .calls import _write_path
from .closure import _package_root
from .values import EvaluatedValue, coerce_evaluated_value


class CommandPerformerError(RuntimeError):
    """A checked command could not produce a committed typed result."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_info: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_info = None if exit_info is None else dict(exit_info)


def perform_command(
    node: Mapping[str, Any],
    argv: Sequence[str],
    *,
    attempt_files: WorkspaceFiles,
    workspace_files: WorkspaceFiles,
    input_document: bytes | None = None,
    timeout_sec: float | None = None,
) -> tuple[EvaluatedValue, str]:
    """Launch one already-resolved command and validate its attempt-owned result."""
    launch_argv = list(argv)
    if not launch_argv or any(not isinstance(token, str) for token in launch_argv):
        raise ValueError("final command argv must contain string tokens")

    result_path = _workspace_relative_path(
        workspace_files.workspace,
        attempt_files.workspace / "result.json",
    )
    launch_env = {
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": result_path,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if input_document is not None:
        if not isinstance(input_document, bytes):
            raise TypeError("input_document must be canonical bytes")
        attempt_files.create("inputs.json", input_document, exclusive=True, mode=0o600)

    _check_package_module_origin(node, launch_argv, launch_env, workspace_files.workspace)

    execution = StepExecutor(
        workspace_files.workspace,
        attempt_capture_files=attempt_files,
    ).execute_command(
        "evaluated-command",
        launch_argv,
        cwd=workspace_files.workspace,
        env=launch_env,
        timeout_sec=timeout_sec,
        output_capture=CaptureMode.TEXT,
    )
    if execution.exit_code != 0:
        error_type = (execution.error or {}).get("type")
        code = "command_timeout" if error_type == "timeout" else "command_exit_nonzero"
        exit_info = {
            "exit_code": execution.exit_code,
            "error": execution.error,
        }
        raise CommandPerformerError(
            code,
            f"evaluated command failed with exit code {execution.exit_code}",
            exit_info=exit_info,
        )

    try:
        result_bytes = attempt_files.read("result.json")
    except FileNotFoundError as exc:
        raise CommandPerformerError(
            "command_result_missing",
            f"evaluated command did not create result.json at {result_path}",
        ) from exc
    except (OSError, ValueError) as exc:
        raise CommandPerformerError(
            "command_result_unreadable",
            f"cannot read evaluated command result at {result_path}: {exc}",
        ) from exc

    artifacts = _validate_result_bytes(node, result_bytes, result_path, workspace_files)
    projected = _project_checked_result(node, artifacts)
    projected = _restore_record_containers(
        projected,
        _load_bundle_json(result_bytes, reject_nonstandard_constants=False),
        node["result"],
    )
    value = coerce_evaluated_value(
        projected,
        node["result"],
        committed_result_path=result_path,
        context="evaluated command result",
    )
    return value, "sha256:" + sha256(result_bytes).hexdigest()


def _workspace_relative_path(workspace: Path, target: Path) -> str:
    return os.path.relpath(target, workspace).replace(os.sep, "/")


def _validate_result_bytes(
    node: Mapping[str, Any],
    result_bytes: bytes,
    result_path: str,
    workspace_files: WorkspaceFiles,
) -> dict[str, Any]:
    contract = node["contract"]
    kind = contract["kind"]
    payload = contract["payload"]
    diagnostic_payload = {**payload, "path": result_path}
    if kind == "output_bundle":
        return _validate_output_bundle_document_bytes(
            diagnostic_payload,
            result_bytes,
            workspace_files,
            finite_floats=True,
        )
    if kind == "variant_output":
        return _validate_variant_output_bundle_document_bytes(
            diagnostic_payload,
            result_bytes,
            workspace_files,
            finite_floats=True,
        )
    raise CommandPerformerError(
        "command_result_contract",
        f"unsupported checked command result contract {kind!r}",
    )


def _project_checked_result(
    node: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> Any:
    # The caller supplies a ClosedProgram-checked node; only result bytes are
    # untrusted here, and the shared byte validator checked the artifact values.
    contract = node["contract"]
    payload = contract["payload"]
    if contract["kind"] == "variant_output":
        return _project_variant_result(payload, artifacts)
    fields = payload.get("fields")
    projected: dict[str, Any] = {}
    for field in fields:
        name = field["name"]
        pointer = field["json_pointer"]
        if name not in artifacts:
            continue
        if pointer == "":
            if len(fields) != 1:
                raise CommandPerformerError("command_result_projection", "root result pointer overlaps other fields")
            return artifacts[name]
        _write_checked_field(projected, pointer, artifacts[name])
    return projected


def _project_variant_result(
    payload: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    discriminant = payload.get("discriminant")
    variants = payload.get("variants")
    shared_fields = payload.get("shared_fields", [])
    discriminant_name = discriminant["name"]
    discriminant_pointer = discriminant["json_pointer"]
    projected: dict[str, Any] = {}
    _write_checked_field(projected, discriminant_pointer, artifacts[discriminant_name])
    variant = variants.get(artifacts[discriminant_name])
    variant_fields = variant["fields"]
    for field in (*shared_fields, *variant_fields):
        name = field["name"]
        pointer = field["json_pointer"]
        if name in artifacts:
            _write_checked_field(projected, pointer, artifacts[name])
    return projected


def _write_checked_field(target: dict[str, Any], pointer: str, value: Any) -> None:
    if not pointer.startswith("/"):
        raise CommandPerformerError("command_result_projection", "checked result pointer is invalid")
    path = [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]
    if not path or not all(path) or not _write_path(target, path, value):
        raise CommandPerformerError("command_result_projection", "checked result pointers overlap")


def _restore_record_containers(projected: Any, document: Any, descriptor: Mapping[str, Any]) -> Any:
    # Flattened checked contracts omit records without leaves. Keep the validated
    # leaf projection, but require their declared containers in the actual JSON.
    kind = descriptor["kind"]
    if kind not in {"record", "union"}:
        return projected
    if not isinstance(document, dict):
        raise CommandPerformerError(
            "command_result_projection",
            f"required result container {descriptor['name']!r} is missing or is not an object",
        )
    if kind == "union":
        fields = next(row for row in descriptor["variants"] if row["name"] == projected["variant"])["fields"]
    else:
        fields = descriptor["fields"]
    if projected is None:
        projected = {}
    for field in fields:
        name = field["name"]
        if field["type"]["kind"] == "record":
            projected[name] = _restore_record_containers(projected.get(name), document.get(name), field["type"])
    return projected


def _check_package_module_origin(
    node: Mapping[str, Any],
    argv: list[str],
    env: Mapping[str, str],
    cwd: Path,
) -> None:
    if not _is_builtin_module_invocation(argv) or not _has_package_closure(node):
        return

    effective_env = os.environ.copy()
    effective_env.update(env)
    StepExecutor._ensure_orchestrator_module_on_pythonpath(argv, effective_env)
    package_root = _package_root()
    module_origin = None
    for fullname, spec in _module_specs(argv[2], _effective_search_path(effective_env, cwd)):
        origin = _filesystem_origin(spec, cwd)
        try:
            module_origin = origin.relative_to(package_root)
        except ValueError as exc:
            raise CommandPerformerError(
                "command_module_origin_mismatch",
                f"builtin module prefix {fullname!r} resolves outside package root {package_root}",
            ) from exc
    if not _covered_by_package_closure(node, package_root, module_origin):
        raise CommandPerformerError(
            "command_module_origin_mismatch",
            f"builtin module {argv[2]!r} is not covered by the checked package closure",
        )


def _is_builtin_module_invocation(argv: Sequence[str]) -> bool:
    return (
        len(argv) >= 3
        and Path(argv[0]).name.startswith("python")
        and argv[1] == "-m"
        and argv[2].startswith("orchestrator.")
    )


def _has_package_closure(node: Mapping[str, Any]) -> bool:
    closure = node.get("closure")
    return isinstance(closure, list) and any(
        isinstance(row, Mapping) and row.get("base") == "package:orchestrator"
        for row in closure
    )


def _effective_search_path(env: Mapping[str, str], cwd: Path) -> list[str]:
    paths = [str(cwd)]
    pythonpath = env.get("PYTHONPATH", "")
    for entry in pythonpath.split(os.pathsep):
        if not entry:
            paths.append(str(cwd))
        elif os.path.isabs(entry):
            paths.append(entry)
        else:
            paths.append(os.path.abspath(os.fspath(cwd / entry)))
    return paths


def _module_specs(module: str, search_path: list[str]) -> list[tuple[str, Any]]:
    parts = module.split(".")
    fullname = ""
    locations: Sequence[str] | None = search_path
    result = []
    for part in parts:
        fullname = f"{fullname}.{part}" if fullname else part
        current = PathFinder.find_spec(fullname, list(locations) if locations is not None else None)
        if current is None:
            raise CommandPerformerError(
                "command_module_origin_mismatch",
                f"cannot resolve builtin module {module!r} on the effective child import path",
            )
        locations = current.submodule_search_locations
        if fullname != module and locations is None:
            raise CommandPerformerError(
                "command_module_origin_mismatch",
                f"builtin module parent {fullname!r} is not a package",
            )
        result.append((fullname, current))
    return result


def _filesystem_origin(spec: Any, cwd: Path) -> Path:
    raw_origin = getattr(spec, "origin", None)
    if not isinstance(raw_origin, str) or raw_origin in {"built-in", "frozen"}:
        raise CommandPerformerError(
            "command_module_origin_mismatch",
            "builtin module has no concrete filesystem origin",
        )
    spelling = Path(raw_origin)
    if not spelling.is_absolute():
        spelling = cwd / spelling
    try:
        origin = spelling.resolve(strict=True)
    except OSError as exc:
        raise CommandPerformerError(
            "command_module_origin_mismatch",
            f"builtin module origin is not resolvable: {spelling}",
        ) from exc
    if not origin.is_file():
        raise CommandPerformerError(
            "command_module_origin_mismatch",
            f"builtin module origin is not a regular file: {origin}",
        )
    return origin


def _covered_by_package_closure(
    node: Mapping[str, Any],
    package_root: Path,
    relative_origin: Path,
) -> bool:
    closure = node.get("closure")
    if not isinstance(closure, list):
        return False
    for row in closure:
        if not isinstance(row, Mapping) or row.get("base") != "package:orchestrator":
            continue
        spelling = row.get("path")
        if not isinstance(spelling, str):
            continue
        declared = (package_root / spelling).resolve(strict=False)
        module_file = package_root / relative_origin
        if module_file == declared:
            return True
        if declared.is_dir() and module_file.is_relative_to(declared):
            return True
    return False


__all__ = ["CommandPerformerError", "perform_command"]
