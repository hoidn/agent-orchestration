"""Locked apparatus parsing and staging helpers for the lean-pilot runner."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import string
import tempfile
from pathlib import Path, PurePosixPath
from typing import Mapping

from orchestrator.security.secrets import SecretsManager
from orchestrator.workflow_lisp.build import (
    load_frontend_initialization_configuration,
)
from orchestrator.workflow_lisp.command_boundaries import (
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

from ._pilot_prepare_support import PilotPreparationError
from ._runner_types import RunnerError
from ._treatment_runtime import derive_treatment_runtime


_ALLOWED_PLACEHOLDERS = {
    "workspace",
    "task_path",
    "result_path",
    "provider_config",
    "prompt_config",
    "command_config",
    "apparatus_root",
    "treatment_runtime_root",
}
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TREATMENT_CONFIG_FIELDS = {
    "argv",
    "environment",
    "environment_identity",
    "provider_policy_digest",
    "timeout_milliseconds",
}


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def strict_json_bytes(data: bytes, *, label: str) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RunnerError(f"{label} is not UTF-8 JSON") from exc

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise RunnerError(f"{label} has duplicate field {key!r}")
            value[key] = item
        return value

    def reject_float(value: str) -> object:
        raise RunnerError(f"{label} contains non-integer number {value!r}")

    def reject_constant(value: str) -> object:
        raise RunnerError(f"{label} contains non-JSON constant {value!r}")

    try:
        return json.loads(
            text,
            object_pairs_hook=object_pairs,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except RunnerError:
        raise
    except json.JSONDecodeError as exc:
        raise RunnerError(f"{label} is invalid JSON: {exc.msg}") from exc


def strict_object(data: bytes, *, label: str) -> dict[str, object]:
    value = strict_json_bytes(data, label=label)
    if not isinstance(value, dict):
        raise RunnerError(f"{label} must be a JSON object")
    return value


def canonical_absolute_path(value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"{label} must be an explicit absolute path")
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=False).as_posix() != value:
        raise RunnerError(f"{label} must be an explicit canonical absolute path")
    return path


def verified_treatment_runtime(
    value: object,
    *,
    repository_root: Path,
) -> Path:
    if not isinstance(value, Mapping):
        raise RunnerError("apparatus.treatment_runtime is required for launch")
    import_root = canonical_absolute_path(
        value.get("import_root"),
        label="apparatus.treatment_runtime.import_root",
    )
    revision_identity = value.get("revision_identity")
    if (
        import_root != repository_root
        or not isinstance(revision_identity, str)
        or not revision_identity.startswith("commit:")
        or not isinstance(value.get("tree_identity"), str)
    ):
        raise RunnerError("apparatus.treatment_runtime binding is malformed")
    try:
        observed = derive_treatment_runtime(
            import_root,
            revision_identity.removeprefix("commit:"),
        )
    except PilotPreparationError as exc:
        raise RunnerError(f"treatment runtime verification failed: {exc}") from exc
    if observed != dict(value):
        raise RunnerError("treatment runtime identity mismatch")
    return import_root


def _read_manifest_asset(control_root: Path, relative_path: str) -> bytes:
    relative = PurePosixPath(relative_path)
    candidate = control_root.joinpath(*relative.parts)
    try:
        identity = candidate.lstat()
    except OSError as exc:
        raise RunnerError(f"missing apparatus asset: {relative_path}") from exc
    if not stat.S_ISREG(identity.st_mode) or candidate.is_symlink():
        raise RunnerError(f"apparatus asset is not a regular file: {relative_path}")
    try:
        if candidate.resolve(strict=True) != candidate:
            raise RunnerError(
                f"apparatus asset traverses a symbolic link: {relative_path}"
            )
        return candidate.read_bytes()
    except OSError as exc:
        raise RunnerError(f"cannot read apparatus asset: {relative_path}") from exc


def verified_assets(lock: Mapping[str, object]) -> dict[str, bytes]:
    apparatus = lock["apparatus"]
    if not isinstance(apparatus, Mapping):
        raise RunnerError("lock apparatus is not an object")
    control_root = canonical_absolute_path(
        apparatus["control_root"],
        label="apparatus.control_root",
    )
    if not control_root.is_dir() or control_root.is_symlink():
        raise RunnerError("apparatus.control_root is not a regular directory")

    verified: dict[str, bytes] = {}
    manifest = apparatus["asset_manifest"]
    if not isinstance(manifest, list):
        raise RunnerError("apparatus.asset_manifest is not an array")
    expected_paths: set[str] = set()
    for entry in manifest:
        if not isinstance(entry, Mapping):
            raise RunnerError("apparatus manifest entry is not an object")
        relative_path = entry["path"]
        expected_digest = entry["sha256"]
        if not isinstance(relative_path, str) or not isinstance(expected_digest, str):
            raise RunnerError("apparatus manifest entry is malformed")
        if relative_path in expected_paths:
            raise RunnerError(f"duplicate apparatus asset: {relative_path}")
        expected_paths.add(relative_path)
        data = _read_manifest_asset(control_root, relative_path)
        if sha256_bytes(data) != expected_digest:
            raise RunnerError(f"apparatus asset digest mismatch: {relative_path}")
        if control_root.as_posix().encode("utf-8") in data:
            raise RunnerError(
                f"apparatus asset exposes original control_root: {relative_path}"
            )
        verified[relative_path] = data

    observed_paths: set[str] = set()
    observed_directories: set[str] = set()
    expected_directories = {
        parent.as_posix()
        for path in expected_paths
        for parent in PurePosixPath(path).parents
        if parent.parts
    }

    def walk(directory: Path, relative: PurePosixPath) -> None:
        try:
            with os.scandir(directory) as scan:
                children = list(scan)
        except OSError as exc:
            raise RunnerError("cannot enumerate apparatus.control_root") from exc
        for child in children:
            child_relative = relative / child.name
            try:
                identity = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise RunnerError(
                    "cannot inspect apparatus control tree node: "
                    f"{child_relative.as_posix()}"
                ) from exc
            if stat.S_ISDIR(identity.st_mode):
                observed_directories.add(child_relative.as_posix())
                walk(Path(child.path), child_relative)
            elif stat.S_ISREG(identity.st_mode):
                observed_paths.add(child_relative.as_posix())
            else:
                raise RunnerError(
                    "apparatus control tree contains a non-regular asset: "
                    f"{child_relative.as_posix()}"
                )

    walk(control_root, PurePosixPath())
    extra = observed_paths - expected_paths
    missing = expected_paths - observed_paths
    if extra:
        raise RunnerError("extra apparatus asset: " + ", ".join(sorted(extra)))
    if missing:
        raise RunnerError("missing apparatus asset: " + ", ".join(sorted(missing)))
    extra_directories = observed_directories - expected_directories
    missing_directories = expected_directories - observed_directories
    if extra_directories:
        raise RunnerError(
            "extra apparatus directory: "
            + ", ".join(sorted(extra_directories))
        )
    if missing_directories:
        raise RunnerError(
            "missing apparatus directory: "
            + ", ".join(sorted(missing_directories))
        )
    return verified


def environment_mapping(value: object, *, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RunnerError(f"{label} must be an object")
    environment: dict[str, str] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or _ENVIRONMENT_NAME.fullmatch(key) is None
            or not isinstance(item, str)
        ):
            raise RunnerError(f"{label} must map environment names to strings")
        environment[key] = item
    return environment


def string_list(value: object, *, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise RunnerError(f"{label} must be a nonempty-string array")
    return tuple(value)


def substitute(value: str, replacements: Mapping[str, str], *, label: str) -> str:
    formatter = string.Formatter()
    try:
        parsed = tuple(formatter.parse(value))
    except ValueError as exc:
        raise RunnerError(f"{label} has malformed placeholder syntax") from exc
    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if (
            field_name not in _ALLOWED_PLACEHOLDERS
            or format_spec
            or conversion is not None
        ):
            raise RunnerError(f"{label} has unknown placeholder {field_name!r}")
    try:
        return value.format_map(dict(replacements))
    except (KeyError, ValueError) as exc:
        raise RunnerError(f"{label} has invalid placeholder syntax") from exc


def opaque_label(seed: str, block_id: str, treatment_id: str) -> str:
    material = f"{seed}\0{block_id}\0{treatment_id}".encode("utf-8")
    return f"arm-{hashlib.sha256(material).hexdigest()[:16]}"


def paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def resolve_credentials(names: tuple[str, ...]) -> dict[str, str]:
    context = SecretsManager().resolve_secrets(declared_secrets=list(names))
    if context.missing_secrets:
        raise RunnerError(
            "missing locked provider credentials: "
            + ", ".join(context.missing_secrets)
        )
    return dict(context.secret_values)


def stage_verified_assets(
    *,
    root: Path,
    verified: Mapping[str, bytes],
) -> tuple[tuple[Path, bytes], ...]:
    return tuple(
        (root.joinpath(*PurePosixPath(relative_path).parts), data)
        for relative_path, data in sorted(verified.items())
    )


def write_staged_assets(
    staged_assets: tuple[tuple[Path, bytes], ...],
) -> None:
    for path, data in staged_assets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def validate_standard_role_manifests(
    *,
    verified: Mapping[str, bytes],
    provider_path: str,
    prompt_path: str,
    command_path: str,
) -> None:
    try:
        with tempfile.TemporaryDirectory(
            prefix="lean-pilot-manifest-preflight-"
        ) as directory:
            root = Path(directory)
            write_staged_assets(
                stage_verified_assets(root=root, verified=verified)
            )
            configuration = load_frontend_initialization_configuration(
                workspace_root=root,
                source_roots=(root,),
                provider_externs_path=root.joinpath(
                    *PurePosixPath(provider_path).parts
                ),
                prompt_externs_path=root.joinpath(
                    *PurePosixPath(prompt_path).parts
                ),
                command_boundaries_path=root.joinpath(
                    *PurePosixPath(command_path).parts
                ),
            )
            build_command_boundary_environment(configuration.command_boundaries)
    except (LispFrontendCompileError, OSError, ValueError) as exc:
        raise RunnerError(
            "apparatus role configs must be standard Workflow Lisp extern manifests"
        ) from exc

    for name, binding in configuration.prompt_externs.items():
        if isinstance(binding, str):
            source_kind = "asset_file"
            path = binding
        elif isinstance(binding, Mapping):
            if set(binding) == {"asset_file"}:
                source_kind = "asset_file"
                path = binding["asset_file"]
            elif set(binding) == {"input_file"}:
                source_kind = "input_file"
                path = binding["input_file"]
            else:
                source_kind = None
                path = None
        else:
            raise RunnerError(
                "apparatus prompt config is not a standard Workflow Lisp "
                "extern manifest"
            )
        if source_kind != "asset_file":
            raise RunnerError(
                f"apparatus prompt extern {name} must use asset_file"
            )
        if not isinstance(path, str) or path not in verified:
            raise RunnerError(
                f"missing apparatus prompt asset for {name}: {path}"
            )


def parse_treatment_config(
    data: bytes,
    *,
    label: str,
    expected_environment_identity: str,
    expected_provider_policy_digest: str,
) -> tuple[tuple[str, ...], dict[str, str], int]:
    config = strict_object(data, label=label)
    if set(config) != _TREATMENT_CONFIG_FIELDS:
        raise RunnerError(f"{label} has unknown or missing fields")
    argv = string_list(config["argv"], label=f"{label}.argv")
    if not argv:
        raise RunnerError(f"{label}.argv must contain at least one command")
    environment = environment_mapping(
        config["environment"],
        label=f"{label}.environment",
    )
    if config["environment_identity"] != expected_environment_identity:
        raise RunnerError(f"{label} environment identity mismatch")
    if config["provider_policy_digest"] != expected_provider_policy_digest:
        raise RunnerError(f"{label} provider policy digest mismatch")
    timeout = config["timeout_milliseconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise RunnerError(f"{label}.timeout_milliseconds must be positive")
    return argv, environment, timeout
