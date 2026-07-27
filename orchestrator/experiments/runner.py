"""Bounded three-treatment runner for the lean `.orc` effectiveness pilot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import stat
import string
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from orchestrator.security.secrets import SecretsManager

from . import workspace
from .contracts import (
    PilotContractError,
    canonical_json_bytes,
    canonical_sha256,
    load_record,
    validate_record,
)


_ALLOWED_PLACEHOLDERS = {
    "workspace",
    "task_path",
    "result_path",
    "provider_config",
    "prompt_config",
    "command_config",
}
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMMIT_IDENTITY = re.compile(r"^commit:([0-9a-f]{40,64})$")
_TREATMENT_CONFIG_FIELDS = {
    "argv",
    "environment",
    "environment_identity",
    "timeout_milliseconds",
}
_RAW_RESULT_FIELDS = {"provider_call_count", "token_counts", "cost"}


class RunnerError(ValueError):
    """The locked block cannot be executed without violating its protocol."""


class QuiescenceError(RunnerError):
    """A launched process group could not be proven quiescent."""


class SharedContrastInvalidation(RunnerError):
    """A shared launch fault invalidated the three-treatment contrast."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ArmCommand:
    treatment_id: str
    opaque_arm_label: str
    command_digest: str
    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    timeout_milliseconds: int
    workspace: Path
    runtime_root: Path
    result_path: Path


@dataclass(frozen=True)
class ArmExecution:
    opaque_arm_label: str
    treatment_id: str
    command_digest: str
    lifecycle_outcome: str
    product_frozen: bool
    product_manifest_digest: str | None
    provider_call_count: int
    elapsed_milliseconds: int
    evidence_references: tuple[str, ...]
    token_counts: object
    cost: object

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "opaque_arm_label": self.opaque_arm_label,
            "treatment_id": self.treatment_id,
            "command_digest": self.command_digest,
            "lifecycle_outcome": self.lifecycle_outcome,
            "product_frozen": self.product_frozen,
            "provider_call_count": self.provider_call_count,
            "elapsed_milliseconds": self.elapsed_milliseconds,
            "evidence_references": list(self.evidence_references),
            "token_counts": self.token_counts,
            "cost": self.cost,
        }
        if self.product_manifest_digest is not None:
            record["product_manifest_digest"] = self.product_manifest_digest
        return record


@dataclass(frozen=True)
class BlockAttempt:
    record: dict[str, Any]
    path: Path


@dataclass(frozen=True)
class _PreparedArm:
    command: ArmCommand
    staged_assets: tuple[tuple[Path, bytes], ...]
    credential_names: tuple[str, ...]


@dataclass(frozen=True)
class _Preflight:
    repo: Path
    commit: str
    archive_digest: str
    exclusions: tuple[PurePosixPath, ...]
    visible_check_argv: tuple[str, ...]
    visible_check_timeout_milliseconds: int
    maximum_start_skew_milliseconds: int
    quiescence_grace_milliseconds: int
    arms: tuple[_PreparedArm, ...]
    attempt_class: str
    sequence_index: int
    record_path: Path


@dataclass(frozen=True)
class _RawResult:
    provider_call_count: int
    token_counts: object
    cost: object


class _ProcessGroups:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._groups: set[int] = set()

    def add(self, process_group_id: int) -> None:
        with self._lock:
            self._groups.add(process_group_id)

    def discard(self, process_group_id: int) -> None:
        with self._lock:
            self._groups.discard(process_group_id)

    def terminate_all(self, grace_milliseconds: int) -> bool:
        with self._lock:
            groups = tuple(self._groups)
        all_quiescent = True
        for process_group_id in groups:
            if _terminate_process_group(process_group_id, grace_milliseconds):
                self.discard(process_group_id)
            else:
                all_quiescent = False
        return all_quiescent


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _strict_json_bytes(data: bytes, *, label: str) -> object:
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


def _strict_object(data: bytes, *, label: str) -> dict[str, object]:
    value = _strict_json_bytes(data, label=label)
    if not isinstance(value, dict):
        raise RunnerError(f"{label} must be a JSON object")
    return value


def _canonical_absolute_path(value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"{label} must be an explicit absolute path")
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=False).as_posix() != value:
        raise RunnerError(f"{label} must be an explicit canonical absolute path")
    return path


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


def _verified_assets(lock: Mapping[str, object]) -> dict[str, bytes]:
    apparatus = lock["apparatus"]
    if not isinstance(apparatus, Mapping):
        raise RunnerError("lock apparatus is not an object")
    control_root = _canonical_absolute_path(
        apparatus["control_root"],
        label="apparatus.control_root",
    )
    if not control_root.is_dir() or control_root.is_symlink():
        raise RunnerError("apparatus.control_root is not a regular directory")

    verified: dict[str, bytes] = {}
    manifest = apparatus["asset_manifest"]
    if not isinstance(manifest, list):
        raise RunnerError("apparatus.asset_manifest is not an array")
    for entry in manifest:
        if not isinstance(entry, Mapping):
            raise RunnerError("apparatus manifest entry is not an object")
        relative_path = entry["path"]
        expected_digest = entry["sha256"]
        if not isinstance(relative_path, str) or not isinstance(expected_digest, str):
            raise RunnerError("apparatus manifest entry is malformed")
        data = _read_manifest_asset(control_root, relative_path)
        if _sha256_bytes(data) != expected_digest:
            raise RunnerError(f"apparatus asset digest mismatch: {relative_path}")
        verified[relative_path] = data
    return verified


def _environment_mapping(value: object, *, label: str) -> dict[str, str]:
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


def _string_list(value: object, *, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise RunnerError(f"{label} must be a nonempty-string array")
    return tuple(value)


def _substitute(value: str, replacements: Mapping[str, str], *, label: str) -> str:
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


def _opaque_label(seed: str, block_id: str, treatment_id: str) -> str:
    material = f"{seed}\0{block_id}\0{treatment_id}".encode("utf-8")
    return f"arm-{hashlib.sha256(material).hexdigest()[:16]}"


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first in second.parents
        or second in first.parents
    )


def _contains_logical_token(value: str, tokens: tuple[str, ...]) -> bool:
    return any(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
            value,
            flags=re.IGNORECASE,
        )
        is not None
        for token in tokens
    )


def _validate_candidate_visibility(
    *,
    arms: tuple[_PreparedArm, ...],
    evidence_root: Path,
    record_path: Path,
    randomization_seed: str,
    treatment_ids: tuple[str, ...],
) -> None:
    for arm in arms:
        command = arm.command
        peer_commands = tuple(
            peer.command
            for peer in arms
            if peer.command.opaque_arm_label != command.opaque_arm_label
        )
        forbidden_fragments = (
            str(evidence_root),
            str(record_path),
            randomization_seed,
            *(
                fragment
                for peer in peer_commands
                for fragment in (
                    str(peer.workspace),
                    str(peer.runtime_root),
                    str(peer.result_path),
                    peer.opaque_arm_label,
                )
            ),
        )
        visible_values = (
            *command.argv,
            *(key for key, _value in command.environment),
            *(value for _key, value in command.environment),
        )
        if any(
            fragment and fragment in value
            for value in visible_values
            for fragment in forbidden_fragments
        ) or any(
            _contains_logical_token(value, treatment_ids)
            for value in visible_values
        ):
            raise RunnerError(
                "candidate-visible command exposes controller-only data"
            )


def _attempt_identity(
    lock: Mapping[str, object],
    block_id: str,
    evidence_root: Path,
) -> tuple[str, int, Path]:
    fixture_id = lock["fixture_id"]
    smoke_id = lock["smoke_id"]
    live_ids = lock["live_attempt_ids"]
    if not isinstance(fixture_id, str) or not isinstance(smoke_id, str):
        raise RunnerError("lock attempt identifiers are malformed")
    if not isinstance(live_ids, list) or any(
        not isinstance(item, str) for item in live_ids
    ):
        raise RunnerError("lock live attempt identifiers are malformed")

    known_ids = [fixture_id, smoke_id, *live_ids]
    existing: dict[str, dict[str, Any]] = {}
    for known_id in known_ids:
        path = evidence_root / known_id / "block-attempt.json"
        if path.exists():
            existing[known_id] = load_record(
                path,
                expected_kind="block_attempt.v1",
            )
        elif path.parent.exists():
            raise RunnerError(f"incomplete evidence already exists for {known_id}")

    if block_id not in known_ids:
        raise RunnerError(f"block_id is not locked: {block_id}")
    if block_id in existing:
        raise RunnerError(f"block_id is already used: {block_id}")

    used_live = [item for item in live_ids if item in existing]
    if used_live != live_ids[: len(used_live)]:
        raise RunnerError("existing live attempts are not a contiguous prefix")

    if block_id == fixture_id:
        return "FIXTURE", 0, evidence_root / block_id / "block-attempt.json"
    if block_id == smoke_id:
        return "SMOKE", 0, evidence_root / block_id / "block-attempt.json"
    next_index = len(used_live)
    if next_index >= len(live_ids) or block_id != live_ids[next_index]:
        raise RunnerError("live block_id must be the next locked prefix item")
    return "LIVE", next_index, evidence_root / block_id / "block-attempt.json"


def _provider_credentials(
    provider_config: dict[str, object],
    allowed_keys: set[str],
) -> tuple[tuple[str, ...], dict[str, str]]:
    if set(provider_config) != {"credential_environment_keys"}:
        raise RunnerError("provider config has unknown or missing fields")
    names = _string_list(
        provider_config["credential_environment_keys"],
        label="provider credential_environment_keys",
    )
    if len(set(names)) != len(names):
        raise RunnerError("provider credential_environment_keys contains duplicates")
    if any(
        _ENVIRONMENT_NAME.fullmatch(name) is None or name not in allowed_keys
        for name in names
    ):
        raise RunnerError("provider credential key is outside the lock allowlist")
    if {"HOME", "TMPDIR"} & set(names):
        raise RunnerError(
            "provider credential key uses a controller-owned environment key"
        )
    context = SecretsManager().resolve_secrets(declared_secrets=list(names))
    if context.missing_secrets:
        raise RunnerError(
            "missing locked provider credentials: "
            + ", ".join(context.missing_secrets)
        )
    return names, dict(context.secret_values)


def _parse_treatment_config(
    data: bytes,
    *,
    label: str,
    expected_environment_identity: str,
) -> tuple[tuple[str, ...], dict[str, str], int]:
    config = _strict_object(data, label=label)
    if set(config) != _TREATMENT_CONFIG_FIELDS:
        raise RunnerError(f"{label} has unknown or missing fields")
    argv = _string_list(config["argv"], label=f"{label}.argv")
    if not argv:
        raise RunnerError(f"{label}.argv must contain at least one command")
    environment = _environment_mapping(
        config["environment"],
        label=f"{label}.environment",
    )
    if config["environment_identity"] != expected_environment_identity:
        raise RunnerError(f"{label} environment identity mismatch")
    timeout = config["timeout_milliseconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise RunnerError(f"{label}.timeout_milliseconds must be positive")
    return argv, environment, timeout


def _preflight(
    *,
    lock: Mapping[str, object],
    block_id: str,
    work_root: Path,
    evidence_root: Path,
) -> _Preflight:
    try:
        validate_record(lock)
    except PilotContractError as exc:
        raise RunnerError(str(exc)) from exc
    locked_evidence = lock["evidence_root"]
    if (
        not isinstance(locked_evidence, str)
        or evidence_root.resolve(strict=False).as_posix() != locked_evidence
    ):
        raise RunnerError("supplied evidence_root does not exactly match the lock")
    if _paths_overlap(work_root, evidence_root):
        raise RunnerError("work_root and evidence_root must be disjoint")

    archive = lock["archive"]
    if not isinstance(archive, Mapping):
        raise RunnerError("lock archive is not an object")
    repo = _canonical_absolute_path(
        archive["repository_identity"],
        label="archive.repository_identity",
    )
    revision = archive["revision_identity"]
    if not isinstance(revision, str):
        raise RunnerError("archive.revision_identity is malformed")
    match = _COMMIT_IDENTITY.fullmatch(revision)
    if match is None:
        raise RunnerError("archive.revision_identity must be exact commit:<rev>")
    commit = match.group(1)
    archive_digest = archive["archive_digest"]
    if not isinstance(archive_digest, str):
        raise RunnerError("archive.archive_digest is malformed")

    attempt_class, sequence_index, record_path = _attempt_identity(
        lock,
        block_id,
        evidence_root,
    )
    verified = _verified_assets(lock)
    apparatus = lock["apparatus"]
    if not isinstance(apparatus, Mapping):
        raise RunnerError("lock apparatus is not an object")

    role_paths = (
        apparatus["task_path"],
        apparatus["provider_config_path"],
        apparatus["prompt_config_path"],
        apparatus["command_config_path"],
    )
    if any(not isinstance(path, str) or path not in verified for path in role_paths):
        raise RunnerError("apparatus role binding is not verified")
    task_path, provider_path, prompt_path, shared_command_path = role_paths
    provider_config = _strict_object(
        verified[provider_path],
        label="provider config",
    )
    _strict_object(verified[prompt_path], label="prompt config")
    shared_config = _strict_object(
        verified[shared_command_path],
        label="shared command config",
    )
    if set(shared_config) != {"environment"}:
        raise RunnerError("shared command config has unknown or missing fields")
    shared_environment = _environment_mapping(
        shared_config["environment"],
        label="shared command environment",
    )

    apparatus_environment = apparatus["environment"]
    if not isinstance(apparatus_environment, Mapping):
        raise RunnerError("apparatus environment is not an object")
    allowed = _string_list(
        apparatus_environment["allowed_keys"],
        label="apparatus environment allowed_keys",
    )
    allowed_keys = set(allowed)
    if not {"HOME", "TMPDIR"} <= allowed_keys:
        raise RunnerError(
            "apparatus environment allowed_keys must include HOME and TMPDIR"
        )
    environment_identity = apparatus_environment["identity"]
    if not isinstance(environment_identity, str):
        raise RunnerError("apparatus environment identity is malformed")
    credential_names, secret_values = _provider_credentials(
        provider_config,
        allowed_keys,
    )

    visible_check = apparatus["visible_check"]
    if not isinstance(visible_check, Mapping):
        raise RunnerError("apparatus visible_check is not an object")
    visible_argv = _string_list(
        visible_check["argv"],
        label="apparatus visible_check argv",
    )
    visible_timeout = visible_check["timeout_milliseconds"]
    if (
        isinstance(visible_timeout, bool)
        or not isinstance(visible_timeout, int)
        or visible_timeout <= 0
    ):
        raise RunnerError("visible check timeout must be positive")

    exclusions_raw = apparatus["product_projection_exclusions"]
    if not isinstance(exclusions_raw, list) or any(
        not isinstance(item, str) for item in exclusions_raw
    ):
        raise RunnerError("product projection exclusions are malformed")
    exclusions = tuple(PurePosixPath(item) for item in exclusions_raw)
    maximum_skew = apparatus["maximum_start_skew_milliseconds"]
    quiescence_grace = apparatus["quiescence_grace_milliseconds"]
    if (
        isinstance(maximum_skew, bool)
        or not isinstance(maximum_skew, int)
        or maximum_skew <= 0
        or isinstance(quiescence_grace, bool)
        or not isinstance(quiescence_grace, int)
        or quiescence_grace <= 0
    ):
        raise RunnerError("apparatus timing bounds are malformed")

    treatments = lock["treatments"]
    if not isinstance(treatments, list):
        raise RunnerError("lock treatments are not an array")
    seed = lock["randomization_seed"]
    if not isinstance(seed, str):
        raise RunnerError("lock randomization seed is malformed")
    block_work_root = work_root / block_id
    prepared: list[_PreparedArm] = []
    for treatment in treatments:
        if not isinstance(treatment, Mapping):
            raise RunnerError("lock treatment is not an object")
        treatment_id = treatment["treatment_id"]
        command_path = treatment["command_config_path"]
        command_digest = treatment["command_digest"]
        if (
            not isinstance(treatment_id, str)
            or not isinstance(command_path, str)
            or not isinstance(command_digest, str)
            or command_path not in verified
        ):
            raise RunnerError("treatment command binding is malformed")
        if _sha256_bytes(verified[command_path]) != command_digest:
            raise RunnerError(f"{treatment_id} command digest mismatch")
        config_argv, config_environment, timeout = _parse_treatment_config(
            verified[command_path],
            label=f"{treatment_id} command config",
            expected_environment_identity=environment_identity,
        )

        opaque_label = _opaque_label(seed, block_id, treatment_id)
        workspace_path = block_work_root / opaque_label / "workspace"
        runtime_root = block_work_root / ".controller" / opaque_label
        result_path = runtime_root / "raw-result.json"
        asset_root = runtime_root / "assets"
        staged_paths = {
            "task_path": asset_root / "asset-0",
            "provider_config": asset_root / "asset-1",
            "prompt_config": asset_root / "asset-2",
            "command_config": asset_root / "asset-3",
        }
        replacements = {
            "workspace": str(workspace_path),
            "task_path": str(staged_paths["task_path"]),
            "result_path": str(result_path),
            "provider_config": str(staged_paths["provider_config"]),
            "prompt_config": str(staged_paths["prompt_config"]),
            "command_config": str(staged_paths["command_config"]),
        }
        argv = tuple(
            _substitute(
                item,
                replacements,
                label=f"{treatment_id} command argv",
            )
            for item in config_argv
        )

        environment = dict(shared_environment)
        environment.update(config_environment)
        if "HOME" in environment or "TMPDIR" in environment:
            raise RunnerError("HOME and TMPDIR are controller-owned environment keys")
        for key, value in tuple(environment.items()):
            if key not in allowed_keys:
                raise RunnerError(
                    f"{treatment_id} environment key is outside the lock: {key}"
                )
            environment[key] = _substitute(
                value,
                replacements,
                label=f"{treatment_id} environment value",
            )
        environment["HOME"] = str(runtime_root / "home")
        environment["TMPDIR"] = str(runtime_root / "tmp")
        environment.update(secret_values)
        missing_environment = allowed_keys - set(environment)
        if missing_environment:
            raise RunnerError(
                "allowed environment keys lack verified values: "
                + ", ".join(sorted(missing_environment))
            )
        if set(environment) != allowed_keys:
            raise RunnerError("closed environment does not match the lock allowlist")

        prepared.append(
            _PreparedArm(
                command=ArmCommand(
                    treatment_id=treatment_id,
                    opaque_arm_label=opaque_label,
                    command_digest=command_digest,
                    argv=argv,
                    environment=tuple(sorted(environment.items())),
                    timeout_milliseconds=timeout,
                    workspace=workspace_path,
                    runtime_root=runtime_root,
                    result_path=result_path,
                ),
                staged_assets=(
                    (staged_paths["task_path"], verified[task_path]),
                    (staged_paths["provider_config"], verified[provider_path]),
                    (staged_paths["prompt_config"], verified[prompt_path]),
                    (staged_paths["command_config"], verified[command_path]),
                ),
                credential_names=credential_names,
            )
        )

    prepared_arms = tuple(prepared)
    _validate_candidate_visibility(
        arms=prepared_arms,
        evidence_root=evidence_root,
        record_path=record_path,
        randomization_seed=seed,
        treatment_ids=tuple(
            arm.command.treatment_id for arm in prepared_arms
        ),
    )
    return _Preflight(
        repo=repo,
        commit=commit,
        archive_digest=archive_digest,
        exclusions=exclusions,
        visible_check_argv=visible_argv,
        visible_check_timeout_milliseconds=visible_timeout,
        maximum_start_skew_milliseconds=maximum_skew,
        quiescence_grace_milliseconds=quiescence_grace,
        arms=prepared_arms,
        attempt_class=attempt_class,
        sequence_index=sequence_index,
        record_path=record_path,
    )


def _atomic_record(path: Path, record: dict[str, Any]) -> None:
    validate_record(record)
    data = canonical_json_bytes(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / (
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def _started_record(
    lock: Mapping[str, object],
    block_id: str,
    preflight: _Preflight,
) -> dict[str, Any]:
    return {
        "record_kind": "block_attempt.v1",
        "pilot_lock_digest": canonical_sha256(lock),
        "attempt_class": preflight.attempt_class,
        "sequence_index": preflight.sequence_index,
        "block_id": block_id,
        "status": "STARTED",
        "treatment_executions": [],
    }


def _allocate_workspaces(preflight: _Preflight, block_id: str) -> None:
    if not preflight.arms:
        raise RunnerError("lock contains no treatment arms")
    block_root = preflight.arms[0].command.workspace.parents[1]
    block_root.mkdir(parents=True, exist_ok=False)
    manifests = []
    for arm in preflight.arms:
        arm.command.workspace.parent.mkdir()
        manifest = workspace.materialize_git_archive(
            preflight.repo,
            preflight.commit,
            arm.command.workspace,
        )
        if manifest.digest != preflight.archive_digest:
            raise RunnerError(
                f"source archive digest mismatch while allocating {block_id}"
            )
        manifests.append(manifest)
        arm.command.runtime_root.mkdir(parents=True)
        for path, data in arm.staged_assets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        environment = dict(arm.command.environment)
        for special in ("HOME", "TMPDIR"):
            value = environment.get(special)
            if value is not None:
                Path(value).mkdir(parents=True)
    if any(manifest != manifests[0] for manifest in manifests[1:]):
        raise RunnerError("allocated treatment workspaces are not byte-identical")


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(
    process_group_id: int,
    grace_milliseconds: int,
) -> bool:
    if not _process_group_exists(process_group_id):
        return True
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + (grace_milliseconds / 1_000)
    while time.monotonic() < deadline:
        if not _process_group_exists(process_group_id):
            return True
        time.sleep(0.005)
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        return True
    final_deadline = time.monotonic() + 1.0
    while time.monotonic() < final_deadline:
        if not _process_group_exists(process_group_id):
            return True
        time.sleep(0.005)
    return False


def _quiesce_process(
    process: subprocess.Popen[bytes],
    grace_milliseconds: int,
) -> None:
    _terminate_process_group(process.pid, grace_milliseconds)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired as exc:
        raise QuiescenceError(
            f"process {process.pid} could not be reaped after termination"
        ) from exc
    if _process_group_exists(process.pid):
        raise QuiescenceError(
            f"process group {process.pid} remains after termination and reap"
        )


def _raw_result(
    data: bytes,
    *,
    currency: str,
) -> _RawResult:
    value = _strict_json_bytes(data, label="arm raw result")
    if not isinstance(value, dict) or set(value) != _RAW_RESULT_FIELDS:
        raise RunnerError("arm raw result has unknown or missing fields")
    count = value["provider_call_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise RunnerError("arm raw result provider_call_count is invalid")

    token_counts = value["token_counts"]
    if token_counts != "UNKNOWN":
        if (
            not isinstance(token_counts, dict)
            or set(token_counts) != {"input", "output"}
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item < 0
                for item in token_counts.values()
            )
        ):
            raise RunnerError("arm raw result token_counts is invalid")

    cost = value["cost"]
    if cost != "UNKNOWN":
        if (
            not isinstance(cost, dict)
            or set(cost) != {"cost_microunits", "currency"}
            or isinstance(cost["cost_microunits"], bool)
            or not isinstance(cost["cost_microunits"], int)
            or cost["cost_microunits"] < 0
            or cost["currency"] != currency
        ):
            raise RunnerError("arm raw result cost is invalid")
    return _RawResult(
        provider_call_count=count,
        token_counts=token_counts,
        cost=cost,
    )


def _environment_metadata(
    command: ArmCommand,
    credential_names: tuple[str, ...],
) -> dict[str, object]:
    names = {key for key, _value in command.environment}
    return {
        "environment_key_presence": [
            {"name": name, "present": name in names}
            for name in sorted(names)
        ],
        "credential_key_presence": [
            {"name": name, "present": name in names}
            for name in sorted(credential_names)
        ],
    }


def _write_evidence(path: Path, value: bytes | object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, bytes) else canonical_json_bytes(value)
    path.write_bytes(data)


def _run_check(
    *,
    argv: tuple[str, ...],
    timeout_milliseconds: int,
    workspace_root: Path,
    environment: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    grace_milliseconds: int,
    groups: _ProcessGroups,
) -> bool:
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except OSError:
            return False
        groups.add(process.pid)
        quiescent = False
        try:
            try:
                return_code = process.wait(timeout=timeout_milliseconds / 1_000)
            except subprocess.TimeoutExpired:
                return_code = None
            _quiesce_process(process, grace_milliseconds)
            quiescent = True
            return return_code == 0
        finally:
            if quiescent:
                groups.discard(process.pid)


def _run_arm(
    *,
    arm: _PreparedArm,
    preflight: _Preflight,
    lock: Mapping[str, object],
    evidence_root: Path,
    barrier: threading.Barrier,
    launch_times: dict[str, int],
    launch_lock: threading.Lock,
    groups: _ProcessGroups,
) -> ArmExecution:
    command = arm.command
    evidence_directory = (
        evidence_root
        / preflight.record_path.parent.name
        / command.opaque_arm_label
    )
    stdout_path = evidence_directory / "stdout.txt"
    stderr_path = evidence_directory / "stderr.txt"
    raw_evidence_path = evidence_directory / "raw-result.json"
    environment_path = evidence_directory / "environment.json"
    check_stdout_path = evidence_directory / "check-stdout.txt"
    check_stderr_path = evidence_directory / "check-stderr.txt"
    evidence_directory.mkdir(parents=True, exist_ok=True)
    _write_evidence(
        environment_path,
        _environment_metadata(command, arm.credential_names),
    )
    environment = dict(command.environment)

    started = time.monotonic_ns()
    lifecycle = "COMPLETED"
    process: subprocess.Popen[bytes] | None = None
    return_code: int | None = None
    timed_out = False
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        barrier.wait()
        launch_time = time.monotonic_ns()
        with launch_lock:
            launch_times[command.opaque_arm_label] = launch_time
        try:
            process = subprocess.Popen(
                command.argv,
                cwd=command.workspace,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except OSError:
            lifecycle = "LAUNCH_FAILURE"
        if process is not None:
            groups.add(process.pid)
            quiescent = False
            try:
                try:
                    return_code = process.wait(
                        timeout=command.timeout_milliseconds / 1_000
                    )
                except subprocess.TimeoutExpired:
                    timed_out = True
                _quiesce_process(process, preflight.quiescence_grace_milliseconds)
                quiescent = True
            finally:
                if quiescent:
                    groups.discard(process.pid)

    raw_bytes = b""
    if command.result_path.exists() and command.result_path.is_file():
        raw_bytes = command.result_path.read_bytes()
    _write_evidence(raw_evidence_path, raw_bytes)

    raw = _RawResult(
        provider_call_count=0,
        token_counts="UNKNOWN",
        cost="UNKNOWN",
    )
    raw_valid = False
    if raw_bytes:
        try:
            provider_policy = lock["provider_policy"]
            if not isinstance(provider_policy, Mapping):
                raise RunnerError("provider policy is malformed")
            currency = provider_policy["currency"]
            if not isinstance(currency, str):
                raise RunnerError("provider currency is malformed")
            raw = _raw_result(raw_bytes, currency=currency)
            raw_valid = True
        except RunnerError:
            raw_valid = False

    if timed_out:
        lifecycle = "TIMEOUT"
    elif lifecycle != "LAUNCH_FAILURE" and return_code != 0:
        lifecycle = "NONZERO_EXIT"
    elif lifecycle == "COMPLETED" and not raw_valid:
        lifecycle = "PROTOCOL_FAILURE"

    treatment = next(
        item
        for item in lock["treatments"]
        if item["treatment_id"] == command.treatment_id
    )
    bounds = treatment["provider_call_bounds"]
    if (
        lifecycle == "COMPLETED"
        and isinstance(bounds, Mapping)
        and (
            raw.provider_call_count < bounds["minimum"]
            or raw.provider_call_count > bounds["maximum"]
        )
    ):
        lifecycle = "PROTOCOL_FAILURE"

    check_passed = _run_check(
        argv=preflight.visible_check_argv,
        timeout_milliseconds=preflight.visible_check_timeout_milliseconds,
        workspace_root=command.workspace,
        environment=environment,
        stdout_path=check_stdout_path,
        stderr_path=check_stderr_path,
        grace_milliseconds=preflight.quiescence_grace_milliseconds,
        groups=groups,
    )
    if lifecycle == "COMPLETED" and not check_passed:
        lifecycle = "CHECK_FAILURE"

    product = workspace.freeze_product(command.workspace, preflight.exclusions)
    elapsed = max(0, (time.monotonic_ns() - started) // 1_000_000)
    references = tuple(
        path.relative_to(evidence_root).as_posix()
        for path in (
            stdout_path,
            stderr_path,
            raw_evidence_path,
            environment_path,
            check_stdout_path,
            check_stderr_path,
        )
    )
    return ArmExecution(
        opaque_arm_label=command.opaque_arm_label,
        treatment_id=command.treatment_id,
        command_digest=command.command_digest,
        lifecycle_outcome=lifecycle,
        product_frozen=True,
        product_manifest_digest=product.digest,
        provider_call_count=raw.provider_call_count if raw_valid else 0,
        elapsed_milliseconds=elapsed,
        evidence_references=references,
        token_counts=raw.token_counts if raw_valid else "UNKNOWN",
        cost=raw.cost if raw_valid else "UNKNOWN",
    )


def _execute_arms(
    *,
    preflight: _Preflight,
    lock: Mapping[str, object],
    evidence_root: Path,
    groups: _ProcessGroups,
) -> tuple[ArmExecution, ...]:
    barrier = threading.Barrier(4)
    launch_times: dict[str, int] = {}
    launch_lock = threading.Lock()
    results: dict[str, ArmExecution] = {}
    failures: list[BaseException] = []
    result_lock = threading.Lock()

    def worker(arm: _PreparedArm) -> None:
        try:
            result = _run_arm(
                arm=arm,
                preflight=preflight,
                lock=lock,
                evidence_root=evidence_root,
                barrier=barrier,
                launch_times=launch_times,
                launch_lock=launch_lock,
                groups=groups,
            )
            with result_lock:
                results[arm.command.treatment_id] = result
        except BaseException as exc:
            with result_lock:
                failures.append(exc)
            barrier.abort()
            groups.terminate_all(preflight.quiescence_grace_milliseconds)

    threads = [
        threading.Thread(target=worker, args=(arm,), daemon=False)
        for arm in preflight.arms
    ]
    for thread in threads:
        thread.start()
    barrier_failure: threading.BrokenBarrierError | None = None
    try:
        barrier.wait()
    except threading.BrokenBarrierError as exc:
        barrier_failure = exc
    except BaseException:
        barrier.abort()
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        for thread in threads:
            thread.join()
        raise
    for thread in threads:
        thread.join()

    worker_failures = tuple(
        failure
        for failure in failures
        if not isinstance(failure, threading.BrokenBarrierError)
    )
    if worker_failures:
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        raise worker_failures[0]
    if barrier_failure is not None or failures:
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        raise SharedContrastInvalidation(
            "SHARED_LAUNCH_BARRIER_FAILED",
            "arm launch barrier broke",
        ) from barrier_failure
    if len(launch_times) != 3:
        raise RunnerError("not all arm launch workers reached the barrier")
    launch_values = tuple(launch_times.values())
    skew_milliseconds = (max(launch_values) - min(launch_values)) / 1_000_000
    if skew_milliseconds > preflight.maximum_start_skew_milliseconds:
        raise SharedContrastInvalidation(
            "SHARED_START_SKEW_EXCEEDED",
            "arm start skew exceeded the locked maximum",
        )
    return tuple(
        results[arm.command.treatment_id]
        for arm in preflight.arms
    )


def _terminal_record(
    started: dict[str, Any],
    *,
    status: str,
    executions: tuple[ArmExecution, ...] = (),
    reason_code: str | None = None,
) -> dict[str, Any]:
    record = dict(started)
    record["status"] = status
    record["treatment_executions"] = [
        execution.to_record() for execution in executions
    ]
    if reason_code is not None:
        record["reason_code"] = reason_code
    else:
        record.pop("reason_code", None)
    return record


def run_block(
    *,
    lock: Mapping[str, object],
    block_id: str,
    work_root: Path,
    evidence_root: Path,
) -> BlockAttempt:
    """Run one fresh locked three-treatment block and persist its attempt."""

    work_root = Path(work_root).resolve(strict=False)
    evidence_root = Path(evidence_root).resolve(strict=False)
    preflight = _preflight(
        lock=lock,
        block_id=block_id,
        work_root=work_root,
        evidence_root=evidence_root,
    )
    started = _started_record(lock, block_id, preflight)
    _atomic_record(preflight.record_path, started)
    groups = _ProcessGroups()

    try:
        _allocate_workspaces(preflight, block_id)
    except Exception:
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        invalid = _terminal_record(
            started,
            status="INVALID",
            reason_code="SHARED_ARCHIVE_ALLOCATION_FAILED",
        )
        _atomic_record(preflight.record_path, invalid)
        return BlockAttempt(record=invalid, path=preflight.record_path)

    try:
        executions = _execute_arms(
            preflight=preflight,
            lock=lock,
            evidence_root=evidence_root,
            groups=groups,
        )
        valid = _terminal_record(
            started,
            status="VALID",
            executions=executions,
        )
        _atomic_record(preflight.record_path, valid)
        return BlockAttempt(record=valid, path=preflight.record_path)
    except QuiescenceError:
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        raise
    except SharedContrastInvalidation as exc:
        if not groups.terminate_all(preflight.quiescence_grace_milliseconds):
            raise QuiescenceError(
                "one or more process groups remain after cleanup"
            ) from exc
        invalid = _terminal_record(
            started,
            status="INVALID",
            reason_code=exc.reason_code,
        )
        _atomic_record(preflight.record_path, invalid)
        return BlockAttempt(record=invalid, path=preflight.record_path)
    except Exception as exc:
        if not groups.terminate_all(preflight.quiescence_grace_milliseconds):
            raise QuiescenceError(
                "one or more process groups remain after cleanup"
            ) from exc
        aborted = _terminal_record(
            started,
            status="ABORTED",
            reason_code="CONTROLLER_EXCEPTION",
        )
        _atomic_record(preflight.record_path, aborted)
        return BlockAttempt(record=aborted, path=preflight.record_path)


__all__ = [
    "ArmCommand",
    "ArmExecution",
    "BlockAttempt",
    "RunnerError",
    "run_block",
]
