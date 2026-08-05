"""Closed visible-task package and deterministic Git seed for ES F1."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_TASK_ASSET_ROOT = REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/task"
_TASK_PROFILE = REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/task-profile.json"
_TASK_PROFILE_SCHEMA = _TASK_PROFILE.with_name("task-profile.schema.json")

F1_BUILTIN_ARCHITECTURES = (
    "cnn",
    "ffno",
    "fno",
    "fno_vanilla",
    "hybrid",
    "hybrid_resnet",
    "hybrid_resnet_convnext_bottleneck",
    "hybrid_resnet_ffno_bottleneck",
    "hybrid_resnet_ffno_ptychoblock_encoder",
    "hybrid_resnet_ptychoblock_ffno_encoder",
    "neuralop_uno",
    "spectral_resnet_bottleneck_linear_decoder",
    "spectral_resnet_bottleneck_net",
    "stable_hybrid",
)
F1_PROVIDER_VISIBLE_SELECTORS = (
    "tests/torch/test_generator_registry.py",
    "tests/torch/test_construction_consolidation.py",
    "tests/torch/test_generator_adapter.py",
    "tests/torch/test_config_bridge.py",
    "tests/torch/test_model_spec.py",
    "tests/torch/test_model_spec_v2.py",
    "tests/torch/test_lightning_checkpoint.py",
    "tests/torch/test_artifact_schema.py",
    "tests/torch/test_artifact_schema_v2.py",
    "tests/torch/test_workflows_components.py",
    "tests/torch/test_fno_generators.py",
    "tests/torch/test_fno_lightning_integration.py",
    "tests/torch/test_neuralop_uno_generator.py",
    "tests/torch/test_model_output_modes.py",
    "tests/torch/test_model_manager.py",
    "tests/torch/test_model_training.py",
    "tests/torch/test_train_lightning_execution_contract.py",
    "tests/torch/test_object_big_generator_contract.py",
    "tests/torch/test_structural_config_ownership.py",
)
F1_LIFECYCLE_STAGES = (
    "CONFIGURATION",
    "CONSTRUCTION",
    "FORWARD",
    "BACKWARD",
    "OPTIMIZER_STEP",
    "CHECKPOINT_PERSISTENCE",
    "CHECKPOINT_FRESH_RELOAD",
    "BUNDLE_PERSISTENCE",
    "BUNDLE_FRESH_RELOAD",
    "POST_RELOAD_INFERENCE",
    "STRUCTURAL_IDENTITY",
    "ROUND_TRIP_RECONSTRUCTION",
)
F1_HARD_CLAUSE_IDS = (
    "F1-H01-FOCUSED-SUITES",
    "F1-H02-SCHEMA-CONFORMANCE",
    "F1-H03-BUILTIN-SIGNATURES",
    "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
    "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
    "F1-H06-STRUCTURAL-ROUNDTRIP",
    "F1-H07-STRUCTURAL-IDENTITY-REJECTION",
    "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",
    "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
    "F1-H10-OWNERSHIP-BOUNDARY",
)

_CONTROLLED_GIT_ENVIRONMENT_NAMES = frozenset(
    {
        "GIT_AUTHOR_DATE",
        "GIT_AUTHOR_EMAIL",
        "GIT_AUTHOR_NAME",
        "GIT_COMMITTER_DATE",
        "GIT_COMMITTER_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_INDEX_FILE",
    }
)


class TaskPackageError(ValueError):
    """One checked-in or materialized F1 task-package invariant failed."""

    def __init__(self, code: str, value: object, detail: str) -> None:
        super().__init__(f"{code}: {detail}: {value!r}")
        self.code = code
        self.value = value
        self.detail = detail


@dataclass(frozen=True)
class TaskProfile:
    task_id: str
    fixed_output_paths: tuple[str, ...]
    candidate_declared_output_ids: tuple[str, ...]
    hard_clause_ids: tuple[str, ...]
    finding_dispositions: tuple[str, ...]
    reviewer_perspective_ids: tuple[str, ...]
    review_dimension_ids: tuple[str, ...]
    focused_selectors: tuple[str, ...]
    builtin_architectures: tuple[str, ...]
    required_task_seed_schema_version: str
    selector_manifest_record_digest: str
    environment_name: str
    claim_limit_ids: tuple[str, ...]
    raw: dict[str, object]


@dataclass(frozen=True)
class VisibleAsset:
    source_path: str
    target_path: str
    mode: str
    object_type: str
    oid: str
    byte_count: int
    digest: str


@dataclass(frozen=True)
class TaskSeedManifest:
    parent_commit: str
    parent_tree: str
    parent_locator: Path
    parent_snapshot_digest: str
    visible_assets: tuple[VisibleAsset, ...]
    visible_assets_digest: str
    tree: str
    commit: str
    commit_message: bytes
    commit_content_bytes: int
    commit_content_digest: str
    object_count: int
    locator: Path
    repository_snapshot_digest: str
    e1_source_manifest_digest: str
    e1_post_setup_manifest_digest: str
    raw: dict[str, object]


@dataclass(frozen=True)
class TaskSeedResult:
    locator: Path
    commit: str
    tree: str
    parent_commit: str
    commit_count: int
    object_count: int
    unreachable_object_count: int
    reused: bool


@dataclass(frozen=True)
class VisibleCheckManifest:
    python_executable: Path
    argv_prefix: tuple[str, ...]
    working_directory_policy: str
    required_environment: tuple[tuple[str, str], ...]
    timeout_seconds: int
    invocation_order: tuple[str, ...]
    pre_edit_selectors: tuple[str, ...]
    candidate_selector: str
    raw: dict[str, object]


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _reject_nonfinite_constant(value: str) -> NoReturn:
    raise TaskPackageError(
        "task_package_noncanonical",
        value,
        "JSON non-finite numeric constants are forbidden",
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TaskPackageError(
                "task_package_noncanonical",
                key,
                "JSON object contains a duplicate key",
            )
        result[key] = value
    return result


def _load_canonical_json(path: Path, *, schema_path: Path) -> dict[str, object]:
    candidate = Path(path)
    try:
        raw = candidate.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_constant,
        )
        schema_raw = Path(schema_path).read_bytes()
        schema = json.loads(
            schema_raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_constant,
        )
    except TaskPackageError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskPackageError(
            "task_package_unreadable",
            str(candidate),
            "record or its schema is missing or unreadable",
        ) from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise TaskPackageError(
            "task_package_noncanonical",
            str(candidate),
            "record must be canonical JSON followed by one LF",
        )
    if not isinstance(schema, dict) or schema_raw != canonical_json_bytes(schema):
        raise TaskPackageError(
            "task_package_noncanonical",
            str(schema_path),
            "schema must be canonical JSON followed by one LF",
        )
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    if errors:
        raise TaskPackageError(
            "task_package_schema_invalid",
            str(candidate),
            errors[0].message,
        )
    return value


def _digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise TaskPackageError(
            "task_package_unreadable", str(path), "bound asset is unreadable"
        ) from exc


@lru_cache(maxsize=2)
def _validate_preedit_selector_authority_bytes(
    path: Path,
    schema_path: Path,
    raw: bytes,
    schema_raw: bytes,
) -> None:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_constant,
        )
        schema = json.loads(
            schema_raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_constant,
        )
    except TaskPackageError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskPackageError(
            "task_package_selector_authority_mismatch",
            str(path),
            "Task-0 selector authority or schema is unreadable",
        ) from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise TaskPackageError(
            "task_package_selector_authority_mismatch",
            str(path),
            "Task-0 selector authority is not canonical JSON",
        )
    if not isinstance(schema, dict):
        raise TaskPackageError(
            "task_package_selector_authority_mismatch",
            str(schema_path),
            "Task-0 selector schema is not a JSON object",
        )
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    if errors:
        raise TaskPackageError(
            "task_package_selector_authority_mismatch",
            str(path),
            errors[0].message,
        )


def _load_preedit_selector_authority(
    path: Path,
    schema_path: Path,
) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        schema_raw = schema_path.read_bytes()
    except OSError as exc:
        raise TaskPackageError(
            "task_package_selector_authority_mismatch",
            str(path),
            "Task-0 selector authority or schema is unreadable",
        ) from exc
    _validate_preedit_selector_authority_bytes(
        path,
        schema_path,
        raw,
        schema_raw,
    )
    value = json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_nonfinite_constant,
    )
    assert isinstance(value, dict)
    return value


def _git_object_id(object_type: str, payload: bytes) -> str:
    framed = f"{object_type} {len(payload)}".encode("ascii") + b"\0" + payload
    return hashlib.sha1(framed).hexdigest()


def directory_snapshot_digest(root: Path) -> str:
    """Digest a directory's paths, kinds, modes, bytes, and link text."""

    candidate = Path(root)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise TaskPackageError(
            "task_seed_repository_unreadable",
            str(candidate),
            "snapshot root is missing or unreadable",
        ) from exc
    if not candidate.is_absolute() or candidate != resolved or not candidate.is_dir():
        raise TaskPackageError(
            "task_seed_locator_invalid",
            str(candidate),
            "snapshot root must be a canonical absolute directory",
        )
    paths = sorted(
        candidate.rglob("*"),
        key=lambda path: path.relative_to(candidate).as_posix().encode("utf-8"),
    )
    rows: list[dict[str, object]] = []
    for path in paths:
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise TaskPackageError(
                "task_seed_repository_unreadable",
                str(path),
                "repository entry cannot be inspected",
            ) from exc
        relative = path.relative_to(candidate).as_posix()
        mode = f"{stat.S_IMODE(metadata.st_mode):04o}"
        if stat.S_ISREG(metadata.st_mode):
            try:
                payload = path.read_bytes()
            except OSError as exc:
                raise TaskPackageError(
                    "task_seed_repository_unreadable",
                    str(path),
                    "repository file cannot be read",
                ) from exc
            rows.append(
                {
                    "kind": "file",
                    "mode": mode,
                    "path": relative,
                    "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
            )
        elif stat.S_ISDIR(metadata.st_mode):
            rows.append({"kind": "directory", "mode": mode, "path": relative})
        elif stat.S_ISLNK(metadata.st_mode):
            rows.append(
                {
                    "kind": "symlink",
                    "mode": mode,
                    "path": relative,
                    "target": os.readlink(path),
                }
            )
        else:
            raise TaskPackageError(
                "task_seed_repository_unsupported",
                relative,
                "repository contains a non-file, non-directory, non-symlink entry",
            )
    return "sha256:" + hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def _run_git(
    repository: Path,
    *args: str,
    input_bytes: bytes | None = None,
    environment: dict[str, str] | None = None,
) -> bytes:
    env = _git_environment(environment)
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), *args),
            check=False,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as exc:
        raise TaskPackageError(
            "task_seed_git_failed",
            args,
            "Git could not be launched",
        ) from exc
    if completed.returncode != 0:
        raise TaskPackageError(
            "task_seed_git_failed",
            {
                "argv": args,
                "exit_code": completed.returncode,
                "stderr": completed.stderr.decode("utf-8", errors="replace"),
            },
            "Git command failed",
        )
    return completed.stdout


def _git_environment(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Build a Git environment independent of ambient repository/config state."""

    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
        }
    )
    if overrides:
        rejected = tuple(
            sorted(
                name
                for name in overrides
                if name.startswith("GIT_")
                and name not in _CONTROLLED_GIT_ENVIRONMENT_NAMES
            )
        )
        if rejected:
            raise TaskPackageError(
                "task_seed_git_environment_invalid",
                rejected,
                "Git environment override is not part of the controlled recipe",
            )
        environment.update(overrides)
    return environment


def _repository_path(value: object, *, label: str) -> Path:
    if not isinstance(value, str):
        raise TaskPackageError(
            "task_package_noncanonical", value, f"{label} must be relative text"
        )
    relative_path = PurePosixPath(value)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or relative_path.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise TaskPackageError(
            "task_package_path_invalid", value, f"{label} is not canonical relative text"
        )
    candidate = REPOSITORY_ROOT.joinpath(*relative_path.parts)
    try:
        relative = candidate.resolve(strict=False).relative_to(REPOSITORY_ROOT)
    except (OSError, ValueError) as exc:
        raise TaskPackageError(
            "task_package_path_invalid", value, f"{label} escapes the repository"
        ) from exc
    if relative.as_posix() != value:
        raise TaskPackageError(
            "task_package_path_invalid", value, f"{label} is not canonical"
        )
    return candidate


def _expected_visible_asset_pairs() -> tuple[tuple[str, str], ...]:
    """Derive the closed candidate-visible overlay from checked-in bindings."""

    profile = _load_canonical_json(
        _TASK_PROFILE,
        schema_path=_TASK_PROFILE_SCHEMA,
    )
    visible_contract = cast(dict[str, object], profile["visible_contract"])
    contract_source = _repository_path(
        visible_contract["source_path"], label="visible contract source path"
    )
    contract_schema_source = _repository_path(
        visible_contract["schema_path"], label="visible contract schema path"
    )
    if (
        _digest(contract_source) != visible_contract["sha256"]
        or _digest(contract_schema_source) != visible_contract["schema_sha256"]
    ):
        raise TaskPackageError(
            "task_seed_asset_allowlist_mismatch",
            str(contract_source),
            "checked-in visible contract bindings changed",
        )
    contract = _load_canonical_json(
        contract_source,
        schema_path=contract_schema_source,
    )

    neutral_brief = cast(dict[str, object], profile["neutral_brief"])
    contract_brief = cast(dict[str, object], contract["neutral_brief"])
    visible_schemas = cast(dict[str, object], contract["visible_schemas"])
    schema_bindings = cast(list[dict[str, object]], profile["visible_schema_bindings"])
    visible_check = cast(dict[str, object], profile["visible_check"])
    contract_check = cast(dict[str, object], contract["visible_checks"])
    expected_schema_targets = {
        "CANDIDATE_EXTENSION_EVIDENCE": visible_schemas[
            "candidate_extension_evidence"
        ],
        "LIFECYCLE_PROBE_REQUEST": visible_schemas["lifecycle_probe_request"],
        "LIFECYCLE_PROBE_RESULT": visible_schemas["lifecycle_probe_result"],
    }
    if (
        neutral_brief["overlay_path"] != contract_brief["path"]
        or neutral_brief["sha256"] != contract_brief["sha256"]
        or tuple(binding["id"] for binding in schema_bindings)
        != tuple(expected_schema_targets)
        or any(
            binding["overlay_path"]
            != expected_schema_targets[cast(str, binding["id"])]
            for binding in schema_bindings
        )
        or visible_check["overlay_path"] != contract_check["path"]
        or visible_check["schema_overlay_path"] != contract_check["schema_path"]
        or visible_check["sha256"] != contract_check["sha256"]
        or visible_check["schema_sha256"] != contract_check["schema_sha256"]
    ):
        raise TaskPackageError(
            "task_seed_asset_allowlist_mismatch",
            profile,
            "checked-in profile and visible contract disagree on overlay bindings",
        )

    bound_sources = (
        (
            neutral_brief["source_path"],
            neutral_brief["overlay_path"],
            neutral_brief["sha256"],
        ),
        (
            visible_contract["source_path"],
            visible_contract["overlay_path"],
            visible_contract["sha256"],
        ),
        (
            visible_contract["schema_path"],
            visible_contract["schema_overlay_path"],
            visible_contract["schema_sha256"],
        ),
        *(
            (
                binding["source_path"],
                binding["overlay_path"],
                binding["sha256"],
            )
            for binding in schema_bindings
        ),
        (
            visible_check["source_path"],
            visible_check["overlay_path"],
            visible_check["sha256"],
        ),
        (
            visible_check["schema_source_path"],
            visible_check["schema_overlay_path"],
            visible_check["schema_sha256"],
        ),
    )
    pairs: list[tuple[str, str]] = []
    for source_value, target_value, digest in bound_sources:
        source_path = str(source_value)
        target_path = str(target_value)
        source = _repository_path(source_path, label="visible asset source path")
        _repository_path(target_path, label="visible asset overlay path")
        if _digest(source) != digest:
            raise TaskPackageError(
                "task_seed_asset_allowlist_mismatch",
                source_path,
                "checked-in visible asset binding changed",
            )
        pairs.append((source_path, target_path))
    ordered = tuple(sorted(pairs))
    if len(ordered) != 8 or len(set(ordered)) != 8:
        raise TaskPackageError(
            "task_seed_asset_allowlist_mismatch",
            ordered,
            "candidate-visible overlay must contain exactly eight unique bindings",
        )
    return ordered


def _require_visible_asset_allowlist(
    visible_assets: tuple[VisibleAsset, ...],
) -> None:
    observed = tuple((row.source_path, row.target_path) for row in visible_assets)
    expected = _expected_visible_asset_pairs()
    if observed != expected:
        raise TaskPackageError(
            "task_seed_asset_allowlist_mismatch",
            {"expected": expected, "observed": observed},
            "task seed assets differ from the checked-in candidate-visible bindings",
        )


def load_visible_check_manifest(path: Path) -> VisibleCheckManifest:
    """Load the complete candidate-visible runner and invocation contract."""

    manifest_path = Path(path)
    payload = _load_canonical_json(
        manifest_path,
        schema_path=manifest_path.with_name("visible-check-manifest.schema.json"),
    )
    runner = payload["runner"]
    invocations = payload["invocations"]
    assert isinstance(runner, dict)
    assert isinstance(invocations, list)
    invocation_order = tuple(cast(list[str], payload["invocation_order"]))
    invocation_ids = tuple(str(row["id"]) for row in invocations)
    if invocation_ids != invocation_order:
        raise TaskPackageError(
            "visible_check_invocation_mismatch",
            invocation_ids,
            "invocations must appear exactly once in their frozen order",
        )
    pre_edit = cast(list[str], invocations[0]["selectors"])
    candidate = cast(list[str], invocations[1]["selectors"])
    if tuple(pre_edit) != F1_PROVIDER_VISIBLE_SELECTORS or candidate != [
        "tests/torch/test_es_f1_extension_boundary.py"
    ]:
        raise TaskPackageError(
            "visible_check_selector_mismatch",
            (pre_edit, candidate),
            "visible checks changed from the frozen pre-edit and candidate selectors",
        )
    environment_rows = cast(list[dict[str, str]], runner["required_environment"])
    required_environment = tuple(
        (row["name"], row["value"]) for row in environment_rows
    )
    expected_environment = (
        ("PYTHONPATH", ""),
        ("PYTHONDONTWRITEBYTECODE", "1"),
        ("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1"),
    )
    if required_environment != expected_environment:
        raise TaskPackageError(
            "visible_check_environment_mismatch",
            required_environment,
            "visible runner environment changed",
        )
    python_executable = Path(str(runner["python_executable"]))
    if _digest(python_executable) != runner["python_executable_sha256"]:
        raise TaskPackageError(
            "visible_check_environment_mismatch",
            str(python_executable),
            "visible runner executable digest changed",
        )
    return VisibleCheckManifest(
        python_executable=python_executable,
        argv_prefix=tuple(cast(list[str], runner["argv_prefix"])),
        working_directory_policy=str(runner["working_directory_policy"]),
        required_environment=required_environment,
        timeout_seconds=int(runner["timeout_seconds"]),
        invocation_order=invocation_order,
        pre_edit_selectors=tuple(pre_edit),
        candidate_selector=candidate[0],
        raw=payload,
    )


def load_visible_task_contract(path: Path) -> dict[str, object]:
    """Load the exact v2 matrix contract without requiring a Task-3 seed."""

    contract_path = Path(path)
    payload = _load_canonical_json(
        contract_path,
        schema_path=contract_path.with_name("visible-task-contract.schema.json"),
    )
    hard_ids = tuple(
        str(row["id"]) for row in cast(list[dict[str, object]], payload["hard_contract"])
    )
    if tuple(cast(list[str], payload["builtin_architectures"])) != F1_BUILTIN_ARCHITECTURES:
        raise TaskPackageError(
            "task_package_architecture_mismatch",
            payload["builtin_architectures"],
            "built-in architectures changed from the exact frozen order",
        )
    if tuple(cast(list[str], payload["focused_selectors"])) != F1_PROVIDER_VISIBLE_SELECTORS:
        raise TaskPackageError(
            "task_package_selector_mismatch",
            payload["focused_selectors"],
            "provider-visible selectors changed from the exact frozen order",
        )
    if tuple(cast(list[str], payload["required_lifecycle_stages"])) != F1_LIFECYCLE_STAGES:
        raise TaskPackageError(
            "task_package_lifecycle_mismatch",
            payload["required_lifecycle_stages"],
            "required lifecycle stages changed from the exact frozen order",
        )
    if hard_ids != F1_HARD_CLAUSE_IDS:
        raise TaskPackageError(
            "task_package_hard_clause_mismatch",
            hard_ids,
            "hard clauses changed from the exact frozen order",
        )
    return payload


def load_task_profile(path: Path) -> TaskProfile:
    """Load and cross-check the closed Task-1 successor profile assets."""

    profile_path = Path(path)
    payload = _load_canonical_json(
        profile_path,
        schema_path=profile_path.with_name("task-profile.schema.json"),
    )
    visible = payload["visible_contract"]
    assert isinstance(visible, dict)
    contract_path = _repository_path(
        visible["source_path"], label="visible contract source path"
    )
    contract_schema_path = _repository_path(
        visible["schema_path"], label="visible contract schema path"
    )
    if _digest(contract_path) != visible["sha256"]:
        raise TaskPackageError(
            "task_package_digest_mismatch",
            str(contract_path),
            "visible contract digest changed",
        )
    if _digest(contract_schema_path) != visible["schema_sha256"]:
        raise TaskPackageError(
            "task_package_digest_mismatch",
            str(contract_schema_path),
            "visible contract schema digest changed",
        )
    contract = load_visible_task_contract(contract_path)
    payload_fixed_outputs = cast(list[str], payload["fixed_output_paths"])
    payload_declared_outputs = cast(
        list[str], payload["candidate_declared_output_ids"]
    )
    payload_hard_ids = cast(list[str], payload["hard_clause_ids"])
    payload_dispositions = cast(list[str], payload["finding_dispositions"])
    payload_perspectives = cast(list[str], payload["reviewer_perspective_ids"])
    payload_selectors = cast(list[str], payload["focused_selectors"])
    payload_builtins = cast(list[str], payload["builtin_architectures"])
    payload_claim_ids = cast(list[str], payload["claim_limit_ids"])
    payload_review_dimensions = cast(list[str], payload["review_dimension_ids"])
    contract_dispositions = cast(list[str], contract["finding_dispositions"])
    contract_selectors = cast(list[str], contract["focused_selectors"])
    contract_builtins = cast(list[str], contract["builtin_architectures"])
    fixed_outputs = tuple(
        row["path"] for row in contract["candidate_outputs"]["fixed"]  # type: ignore[index,union-attr]
    )
    declared_outputs = tuple(
        row["id"]
        for row in contract["candidate_outputs"]["candidate_declared"]  # type: ignore[index,union-attr]
    )
    hard_ids = tuple(row["id"] for row in contract["hard_contract"])  # type: ignore[union-attr]
    perspective_ids = tuple(
        row["id"] for row in contract["reviewer_perspectives"]  # type: ignore[union-attr]
    )
    claim_ids = tuple(row["id"] for row in contract["claim_limits"])  # type: ignore[union-attr]
    contract_review_dimensions = tuple(
        cast(list[str], contract["review_dimensions"])
    )
    comparisons = (
        ("task_id", payload["task_id"], contract["task_id"]),
        ("fixed_output_paths", tuple(payload_fixed_outputs), fixed_outputs),
        (
            "candidate_declared_output_ids",
            tuple(payload_declared_outputs),
            declared_outputs,
        ),
        ("hard_clause_ids", tuple(payload_hard_ids), hard_ids),
        (
            "finding_dispositions",
            tuple(payload_dispositions),
            tuple(contract_dispositions),
        ),
        (
            "reviewer_perspective_ids",
            tuple(payload_perspectives),
            perspective_ids,
        ),
        (
            "focused_selectors",
            tuple(payload_selectors),
            tuple(contract_selectors),
        ),
        (
            "builtin_architectures",
            tuple(payload_builtins),
            tuple(contract_builtins),
        ),
        ("claim_limit_ids", tuple(payload_claim_ids), claim_ids),
        (
            "review_dimension_ids",
            tuple(payload_review_dimensions),
            contract_review_dimensions,
        ),
    )
    for label, recorded, expected in comparisons:
        if recorded != expected:
            raise TaskPackageError(
                "task_package_binding_mismatch",
                recorded,
                f"{label} disagrees with the visible contract",
            )
    if tuple(payload_builtins) != F1_BUILTIN_ARCHITECTURES:
        raise TaskPackageError(
            "task_package_architecture_mismatch",
            payload_builtins,
            "built-in architectures changed from the exact frozen order",
        )
    if tuple(payload_hard_ids) != F1_HARD_CLAUSE_IDS:
        raise TaskPackageError(
            "task_package_hard_clause_mismatch",
            payload_hard_ids,
            "hard clauses changed from the exact frozen order",
        )
    if tuple(payload_selectors) != F1_PROVIDER_VISIBLE_SELECTORS:
        raise TaskPackageError(
            "task_package_selector_mismatch",
            payload_selectors,
            "provider-visible selectors changed from the exact frozen order",
        )
    profile_environment = payload["environment"]
    contract_environment = contract["environment"]
    assert isinstance(profile_environment, dict)
    assert isinstance(contract_environment, dict)
    for key in (
        "conda_environment",
        "python_executable",
        "python_version",
        "python_executable_sha256",
        "focused_selectors_sha256",
    ):
        if profile_environment[key] != contract_environment[key]:
            raise TaskPackageError(
                "task_package_binding_mismatch",
                profile_environment[key],
                f"environment.{key} disagrees with the visible contract",
            )

    seed_binding = payload["task_seed"]
    brief_binding = payload["neutral_brief"]
    schema_bindings = payload["visible_schema_bindings"]
    check_binding = payload["visible_check"]
    selector_binding = payload["selector_authority"]
    assert isinstance(seed_binding, dict)
    assert isinstance(brief_binding, dict)
    assert isinstance(schema_bindings, list)
    assert isinstance(check_binding, dict)
    assert isinstance(selector_binding, dict)
    expected_seed_binding = {
        "manifest_path": "experiments/orc_effectiveness/f1_es/task-seed-manifest.json",
        "required_schema_version": "es_f1_task_seed.v2",
        "schema_path": "experiments/orc_effectiveness/f1_es/task-seed-manifest.schema.json",
    }
    if seed_binding != expected_seed_binding:
        raise TaskPackageError(
            "task_package_binding_mismatch",
            seed_binding,
            "Task 1 may declare only the exact Task-3 successor seed requirement",
        )
    selector_manifest_path = _repository_path(
        selector_binding["manifest_path"], label="pre-edit selector manifest path"
    )
    selector_schema_path = _repository_path(
        selector_binding["schema_path"], label="pre-edit selector schema path"
    )
    selector_manifest = _load_preedit_selector_authority(
        selector_manifest_path,
        selector_schema_path,
    )
    record_without_digest = {
        key: value
        for key, value in selector_manifest.items()
        if key != "record_sha256"
    }
    computed_selector_record_digest = "sha256:" + hashlib.sha256(
        canonical_json_bytes(record_without_digest)
    ).hexdigest()
    provider_selector_rows = cast(
        list[dict[str, object]],
        selector_manifest["provider_visible_pytest_selectors"],
    )
    controller_selector_rows = cast(
        list[dict[str, object]],
        selector_manifest["controller_only_proof_selectors"],
    )
    selector_paths = tuple(
        str(row["pytest_module_path"]) for row in provider_selector_rows
    )
    selector_paths_digest = "sha256:" + hashlib.sha256(
        canonical_json_bytes(list(selector_paths))
    ).hexdigest()
    if (
        selector_manifest["record_sha256"]
        != selector_binding["record_sha256"]
        or computed_selector_record_digest != selector_binding["record_sha256"]
        or selector_paths != F1_PROVIDER_VISIBLE_SELECTORS
        or selector_paths_digest
        != selector_binding["provider_visible_pytest_selectors_sha256"]
        or not controller_selector_rows
    ):
        raise TaskPackageError(
            "task_package_selector_authority_mismatch",
            selector_binding,
            "task profile must bind the complete two-lane Task-0 selector authority",
        )

    brief_path = _repository_path(
        brief_binding["source_path"], label="neutral brief source path"
    )
    contract_brief = contract["neutral_brief"]
    assert isinstance(contract_brief, dict)
    if (
        _digest(brief_path) != brief_binding["sha256"]
        or brief_binding["sha256"] != contract_brief["sha256"]
        or brief_binding["overlay_path"] != contract_brief["path"]
    ):
        raise TaskPackageError(
            "task_package_digest_mismatch",
            str(brief_path),
            "neutral task brief binding changed",
        )

    expected_schema_paths = {
        "CANDIDATE_EXTENSION_EVIDENCE": contract["visible_schemas"][  # type: ignore[index]
            "candidate_extension_evidence"
        ],
        "LIFECYCLE_PROBE_REQUEST": contract["visible_schemas"][  # type: ignore[index]
            "lifecycle_probe_request"
        ],
        "LIFECYCLE_PROBE_RESULT": contract["visible_schemas"][  # type: ignore[index]
            "lifecycle_probe_result"
        ],
    }
    if tuple(row["id"] for row in schema_bindings) != tuple(expected_schema_paths):
        raise TaskPackageError(
            "task_package_binding_mismatch",
            schema_bindings,
            "visible schema IDs changed or are out of order",
        )
    for binding in schema_bindings:
        assert isinstance(binding, dict)
        source = _repository_path(
            binding["source_path"], label="visible schema source path"
        )
        if (
            _digest(source) != binding["sha256"]
            or binding["overlay_path"] != expected_schema_paths[binding["id"]]
        ):
            raise TaskPackageError(
                "task_package_digest_mismatch",
                str(source),
                "visible schema binding changed",
            )
    check_path = _repository_path(
        check_binding["source_path"], label="visible check source path"
    )
    check_schema_path = _repository_path(
        check_binding["schema_source_path"], label="visible check schema path"
    )
    contract_check = contract["visible_checks"]
    assert isinstance(contract_check, dict)
    if (
        _digest(check_path) != check_binding["sha256"]
        or _digest(check_schema_path) != check_binding["schema_sha256"]
        or check_binding["overlay_path"] != contract_check["path"]
        or check_binding["schema_overlay_path"] != contract_check["schema_path"]
        or check_binding["sha256"] != contract_check["sha256"]
        or check_binding["schema_sha256"] != contract_check["schema_sha256"]
    ):
        raise TaskPackageError(
            "task_package_digest_mismatch",
            str(check_path),
            "visible check binding changed",
        )
    checks = load_visible_check_manifest(check_path)
    if checks.pre_edit_selectors != tuple(payload_selectors):
        raise TaskPackageError(
            "task_package_binding_mismatch",
            checks.pre_edit_selectors,
            "visible checks disagree with the task profile selectors",
        )
    perspective_rows = cast(
        list[dict[str, object]], contract["reviewer_perspectives"]
    )
    owned_dimensions = tuple(
        dimension
        for perspective in perspective_rows
        for dimension in cast(list[str], perspective["owned_dimensions"])
    )
    if (
        len(set(owned_dimensions)) != len(owned_dimensions)
        or set(owned_dimensions) != set(contract_review_dimensions)
    ):
        raise TaskPackageError(
            "task_package_binding_mismatch",
            owned_dimensions,
            "reviewer perspectives must partition the exact frozen dimensions",
        )
    selectors_digest = "sha256:" + hashlib.sha256(
        canonical_json_bytes(payload_selectors)
    ).hexdigest()
    if selectors_digest != profile_environment["focused_selectors_sha256"]:
        raise TaskPackageError(
            "task_package_binding_mismatch",
            selectors_digest,
            "focused selector digest changed",
        )
    python_executable = Path(str(profile_environment["python_executable"]))
    if _digest(python_executable) != profile_environment["python_executable_sha256"]:
        raise TaskPackageError(
            "task_package_environment_mismatch",
            str(python_executable),
            "frozen Python executable digest changed",
        )
    return TaskProfile(
        task_id=str(payload["task_id"]),
        fixed_output_paths=fixed_outputs,
        candidate_declared_output_ids=declared_outputs,
        hard_clause_ids=hard_ids,
        finding_dispositions=tuple(payload_dispositions),
        reviewer_perspective_ids=perspective_ids,
        review_dimension_ids=contract_review_dimensions,
        focused_selectors=tuple(payload_selectors),
        builtin_architectures=tuple(payload_builtins),
        required_task_seed_schema_version=str(
            seed_binding["required_schema_version"]
        ),
        selector_manifest_record_digest=str(selector_binding["record_sha256"]),
        environment_name=str(profile_environment["conda_environment"]),
        claim_limit_ids=claim_ids,
        raw=payload,
    )


def load_execution_ready_task_profile(
    path: Path,
    *,
    task_seed_manifest_path: Path | None,
) -> TaskProfile:
    """Gate visible execution on the fully loaded and verified successor seed."""

    profile = load_task_profile(path)
    if task_seed_manifest_path is None:
        raise TaskPackageError(
            "task_package_seed_not_ready",
            None,
            "the required Task-3 successor seed is missing",
        )
    seed_path = Path(task_seed_manifest_path)
    try:
        raw = seed_path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_constant,
        )
    except TaskPackageError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskPackageError(
            "task_package_seed_not_ready",
            str(seed_path),
            "the required Task-3 successor seed is unreadable",
        ) from exc
    observed_version = value.get("schema_version") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or raw != canonical_json_bytes(value)
        or observed_version != profile.required_task_seed_schema_version
    ):
        raise TaskPackageError(
            "task_package_seed_not_ready",
            observed_version,
            "the task seed is missing, predecessor-versioned, or unknown",
        )
    seed_binding = cast(dict[str, object], profile.raw["task_seed"])
    bound_manifest_path = _repository_path(
        seed_binding["manifest_path"], label="task seed manifest path"
    )
    bound_schema_path = _repository_path(
        seed_binding["schema_path"], label="task seed schema path"
    )
    if (
        seed_path != bound_manifest_path
        or seed_path.with_name("task-seed-manifest.schema.json")
        != bound_schema_path
    ):
        raise TaskPackageError(
            "task_package_seed_not_ready",
            str(seed_path),
            "the task seed is not at the task-profile-bound manifest and schema path",
        )
    manifest = load_task_seed_manifest(seed_path)
    if manifest.raw["schema_version"] != profile.required_task_seed_schema_version:
        raise TaskPackageError(
            "task_package_seed_not_ready",
            manifest.raw["schema_version"],
            "the loaded task seed disagrees with the task profile",
        )
    return profile


def render_task_seed_commit_content(manifest: TaskSeedManifest) -> bytes:
    """Render the exact deterministic child commit bound by the seed manifest."""

    recipe = manifest.raw["recipe"]
    assert isinstance(recipe, dict)
    author = recipe["author"]
    assert isinstance(author, dict)
    identity = (
        f"{author['name']} <{author['email']}> "
        f"{author['timestamp']} {author['timezone']}"
    )
    return (
        f"tree {manifest.tree}\n"
        f"parent {manifest.parent_commit}\n"
        f"author {identity}\n"
        f"committer {identity}\n\n"
    ).encode("utf-8") + manifest.commit_message


def load_task_seed_manifest(path: Path) -> TaskSeedManifest:
    """Load one exact seed recipe and verify its checked-in byte bindings."""

    manifest_path = Path(path)
    payload = _load_canonical_json(
        manifest_path,
        schema_path=manifest_path.with_name("task-seed-manifest.schema.json"),
    )
    parent = payload["parent_projection"]
    assets_payload = payload["visible_assets"]
    recipe = payload["recipe"]
    repository = payload["repository"]
    actual_e1 = payload["actual_e1"]
    assert isinstance(parent, dict)
    assert isinstance(assets_payload, dict)
    assert isinstance(recipe, dict)
    assert isinstance(repository, dict)
    assert isinstance(actual_e1, dict)

    projection_manifest_path = _repository_path(
        parent["manifest_path"], label="parent projection manifest path"
    )
    if _digest(projection_manifest_path) != parent["manifest_sha256"]:
        raise TaskPackageError(
            "task_seed_parent_mismatch",
            str(projection_manifest_path),
            "parent projection manifest digest changed",
        )

    storage_root = Path(str(repository["storage_root"]))
    relative_path = Path(str(repository["relative_path"]))
    locator = storage_root / relative_path
    if (
        not storage_root.is_absolute()
        or storage_root.resolve(strict=False) != storage_root
        or relative_path.is_absolute()
        or locator.resolve(strict=False) != locator
        or str(locator) != repository["locator"]
        or relative_path.as_posix() != f"git-sha1/{recipe['commit']}"
    ):
        raise TaskPackageError(
            "task_seed_locator_invalid",
            repository["locator"],
            "task-seed locator is not the bound absolute content address",
        )
    parent_locator = Path(str(parent["repository_locator"]))
    if (
        not parent_locator.is_absolute()
        or parent_locator.resolve(strict=False) != parent_locator
    ):
        raise TaskPackageError(
            "task_seed_parent_mismatch",
            str(parent_locator),
            "parent projection locator is not canonical and absolute",
        )
    from scripts.experiments.es.projection import load_projection_manifest

    projection_manifest = load_projection_manifest(projection_manifest_path)
    projection_locator = (
        projection_manifest.canonical_storage_root
        / projection_manifest.locator_relative_path
    )
    parent_snapshot_digest = directory_snapshot_digest(parent_locator)
    if (
        projection_manifest.projection_commit != parent["commit"]
        or projection_manifest.retained_tree != parent["tree"]
        or projection_locator != parent_locator
        or parent_snapshot_digest != parent["repository_snapshot_sha256"]
    ):
        raise TaskPackageError(
            "task_seed_parent_mismatch",
            {
                "commit": projection_manifest.projection_commit,
                "locator": str(projection_locator),
                "snapshot": parent_snapshot_digest,
                "tree": projection_manifest.retained_tree,
            },
            "parent projection fields are not fully cross-bound",
        )

    rows: list[VisibleAsset] = []
    canonical_rows: list[dict[str, object]] = []
    raw_asset_pairs = tuple(
        (str(row["source_path"]), str(row["target_path"]))
        for row in assets_payload["rows"]  # type: ignore[union-attr]
    )
    if raw_asset_pairs != _expected_visible_asset_pairs():
        raise TaskPackageError(
            "task_seed_asset_allowlist_mismatch",
            raw_asset_pairs,
            "task seed assets differ from the checked-in candidate-visible bindings",
        )
    for raw_row in assets_payload["rows"]:  # type: ignore[union-attr]
        assert isinstance(raw_row, dict)
        source_path = str(raw_row["source_path"])
        target_path = str(raw_row["target_path"])
        source = _repository_path(source_path, label="visible asset source path")
        try:
            asset_bytes = source.read_bytes()
        except OSError as exc:
            raise TaskPackageError(
                "task_seed_asset_mismatch",
                source_path,
                "visible asset source is unreadable",
            ) from exc
        repository_asset_bytes = _run_git(
            locator,
            "show",
            f"{recipe['commit']}:{target_path}",
        )
        digest = "sha256:" + hashlib.sha256(asset_bytes).hexdigest()
        oid = _git_object_id("blob", asset_bytes)
        if (
            len(asset_bytes) != raw_row["bytes"]
            or digest != raw_row["sha256"]
            or oid != raw_row["oid"]
            or repository_asset_bytes != asset_bytes
        ):
            raise TaskPackageError(
                "task_seed_asset_mismatch",
                source_path,
                "visible asset bytes disagree with the seed row",
            )
        if target_path != f"benchmark/es_f1/{Path(source_path).name}":
            raise TaskPackageError(
                "task_seed_asset_path_invalid",
                target_path,
                "visible asset target must be the fixed benchmark overlay basename",
            )
        canonical_row = {
            "bytes": raw_row["bytes"],
            "mode": raw_row["mode"],
            "object_type": raw_row["object_type"],
            "oid": raw_row["oid"],
            "sha256": raw_row["sha256"],
            "source_path": source_path,
            "target_path": target_path,
        }
        canonical_rows.append(canonical_row)
        rows.append(
            VisibleAsset(
                source_path=source_path,
                target_path=target_path,
                mode=str(raw_row["mode"]),
                object_type=str(raw_row["object_type"]),
                oid=oid,
                byte_count=len(asset_bytes),
                digest=digest,
            )
        )
    ordering = tuple((row.source_path, row.target_path) for row in rows)
    if ordering != tuple(sorted(ordering)) or len(set(ordering)) != len(ordering):
        raise TaskPackageError(
            "task_seed_asset_order_invalid",
            ordering,
            "visible assets must be unique and sorted source to overlay target",
        )
    _require_visible_asset_allowlist(tuple(rows))
    rows_digest = "sha256:" + hashlib.sha256(
        canonical_json_bytes(canonical_rows)
    ).hexdigest()
    if (
        assets_payload["row_count"] != len(rows)
        or assets_payload["sha256"] != rows_digest
    ):
        raise TaskPackageError(
            "task_seed_asset_digest_mismatch",
            rows_digest,
            "visible asset row digest or count changed",
        )

    message = str(recipe["message"]).encode("utf-8")
    expected_message = (
        "E-series F1 deterministic task seed\n\n"
        f"Projection-Commit: {parent['commit']}\n"
        f"Visible-Assets-SHA256: {rows_digest.removeprefix('sha256:')}\n"
        "Task-Seed-Policy: es-f1-task-seed.v2\n"
    ).encode("utf-8")
    if message != expected_message:
        raise TaskPackageError(
            "task_seed_recipe_mismatch",
            recipe["message"],
            "task-seed commit message changed",
        )
    if (
        recipe["message_bytes"] != len(message)
        or recipe["message_sha256"]
        != "sha256:" + hashlib.sha256(message).hexdigest()
    ):
        raise TaskPackageError(
            "task_seed_recipe_mismatch",
            recipe["message_sha256"],
            "task-seed message byte binding changed",
        )

    result = TaskSeedManifest(
        parent_commit=str(parent["commit"]),
        parent_tree=str(parent["tree"]),
        parent_locator=parent_locator,
        parent_snapshot_digest=str(parent["repository_snapshot_sha256"]),
        visible_assets=tuple(rows),
        visible_assets_digest=rows_digest,
        tree=str(recipe["tree"]),
        commit=str(recipe["commit"]),
        commit_message=message,
        commit_content_bytes=int(recipe["commit_content_bytes"]),
        commit_content_digest=str(recipe["commit_content_sha256"]),
        object_count=int(repository["object_count"]),
        locator=locator,
        repository_snapshot_digest=str(repository["repository_snapshot_sha256"]),
        e1_source_manifest_digest=str(actual_e1["source_tree_manifest_sha256"]),
        e1_post_setup_manifest_digest=str(
            actual_e1["post_setup_tree_manifest_sha256"]
        ),
        raw=payload,
    )
    content = render_task_seed_commit_content(result)
    if (
        len(content) != result.commit_content_bytes
        or "sha256:" + hashlib.sha256(content).hexdigest()
        != result.commit_content_digest
        or _git_object_id("commit", content) != result.commit
    ):
        raise TaskPackageError(
            "task_seed_recipe_mismatch",
            result.commit,
            "task-seed commit content or identity changed",
        )
    if (
        actual_e1["resolved_commit"] != result.commit
        or actual_e1["verified_git_tree"] != f"git-tree:{result.tree}"
        or result.e1_source_manifest_digest != result.e1_post_setup_manifest_digest
    ):
        raise TaskPackageError(
            "task_seed_e1_binding_mismatch",
            actual_e1,
            "actual E1 bindings disagree with the task-seed identity",
        )
    verify_task_seed(result.locator, result)
    return result


def load_candidate_extension_evidence(path: Path) -> dict[str, object]:
    """Validate candidate declarations without manufacturing evaluator verdicts."""

    payload = _load_canonical_json(
        Path(path),
        schema_path=_TASK_ASSET_ROOT / "candidate-extension-evidence.schema.json",
    )
    profile = load_task_profile(_TASK_PROFILE)
    claims = payload["claims"]
    builtins = payload["builtin_architectures"]
    witness = payload["candidate_witness"]
    assert isinstance(claims, list)
    assert isinstance(builtins, list)
    assert isinstance(witness, dict)
    claim_ids = tuple(row["clause_id"] for row in claims)
    if claim_ids != profile.hard_clause_ids:
        raise TaskPackageError(
            "candidate_evidence_clause_mismatch",
            claim_ids,
            "candidate claims must enumerate every hard clause exactly once in order",
        )
    builtin_ids = tuple(str(row["public_id"]) for row in builtins)
    if builtin_ids != profile.builtin_architectures:
        raise TaskPackageError(
            "candidate_evidence_builtin_matrix_mismatch",
            builtin_ids,
            "built-in architecture rows must be exact, unique, and ordered",
        )
    witness_id = str(witness["public_id"])
    if witness_id in set(profile.builtin_architectures):
        raise TaskPackageError(
            "candidate_evidence_witness_identity_invalid",
            witness_id,
            "candidate witness must be distinct from every frozen public ID",
        )
    for architecture in (*builtins, witness):
        assert isinstance(architecture, dict)
        structural_fields = architecture["structural_fields"]
        assert isinstance(structural_fields, list)
        field_names = tuple(str(row["name"]) for row in structural_fields)
        if len(set(field_names)) != len(field_names) or any(
            row["baseline_value"] == row["alternate_value"]
            for row in structural_fields
        ):
            raise TaskPackageError(
                "candidate_evidence_structural_field_invalid",
                structural_fields,
                "each architecture needs unique fields with distinct alternate values",
            )
    builtin_field_names = {
        str(field["name"])
        for architecture in builtins
        for field in architecture["structural_fields"]
    }
    witness_field_names = {
        str(field["name"]) for field in witness["structural_fields"]
    }
    if not witness_field_names - builtin_field_names:
        raise TaskPackageError(
            "candidate_evidence_witness_structural_field_invalid",
            tuple(sorted(witness_field_names)),
            "candidate witness needs at least one witness-only structural field name",
        )
    declared_paths = (
        str(payload["architecture_decision_path"]),
        str(payload["extension_author_guide_path"]),
    )
    if (
        len(set(declared_paths)) != 2
        or any(
            path == fixed or path.startswith("benchmark/es_f1/")
            for path in declared_paths
            for fixed in profile.fixed_output_paths
        )
    ):
        raise TaskPackageError(
            "candidate_evidence_path_invalid",
            declared_paths,
            "candidate-declared document paths collide with frozen outputs",
        )
    return payload


def load_lifecycle_probe_request(path: Path) -> dict[str, object]:
    """Load one evaluator-owned full-matrix lifecycle request."""

    request_path = Path(path)
    payload = _load_canonical_json(
        request_path,
        schema_path=_TASK_ASSET_ROOT / "lifecycle-probe-request.schema.json",
    )
    evidence_path = request_path.parent / str(payload["candidate_evidence_path"])
    if _digest(evidence_path) != payload["candidate_evidence_sha256"]:
        raise TaskPackageError(
            "lifecycle_probe_evidence_mismatch",
            str(evidence_path),
            "candidate evidence bytes disagree with the request binding",
        )
    evidence = load_candidate_extension_evidence(evidence_path)
    if payload["candidate_id"] != evidence["candidate_id"]:
        raise TaskPackageError(
            "lifecycle_probe_evidence_mismatch",
            payload["candidate_id"],
            "candidate ID disagrees with the bound evidence",
        )
    evidence_builtins = cast(list[dict[str, object]], evidence["builtin_architectures"])
    evidence_witness = cast(dict[str, object], evidence["candidate_witness"])
    evidence_rows = (*evidence_builtins, evidence_witness)
    cases = cast(list[dict[str, object]], payload["architecture_cases"])
    architecture_ids = tuple(str(row["architecture_id"]) for row in cases)
    expected_ids = tuple(str(row["public_id"]) for row in evidence_rows)
    if architecture_ids != expected_ids:
        raise TaskPackageError(
            "lifecycle_probe_architecture_matrix_mismatch",
            architecture_ids,
            "lifecycle cases must match the exact built-in-plus-witness order",
        )
    if tuple(cast(list[str], payload["required_lifecycle_stages"])) != F1_LIFECYCLE_STAGES:
        raise TaskPackageError(
            "lifecycle_probe_stage_mismatch",
            payload["required_lifecycle_stages"],
            "the complete boundary lifecycle must be requested exactly once",
        )
    bound_paths: list[str] = []
    for case, declared in zip(cases, evidence_rows, strict=True):
        architecture_id = str(case["architecture_id"])
        if architecture_id in F1_BUILTIN_ARCHITECTURES:
            expected_n = 128 if architecture_id == "neuralop_uno" else 64
            if case["N"] != expected_n:
                raise TaskPackageError(
                    "lifecycle_probe_image_size_mismatch",
                    {"architecture_id": architecture_id, "N": case["N"]},
                    "neuralop_uno requires N=128 and every other built-in "
                    "requires N=64",
                )
        expected_case_bindings = (
            declared["construction_route"],
            declared["persisted_rebuild_route"],
            declared["structural_fields"],
        )
        observed_case_bindings = (
            case["construction_route"],
            case["persisted_rebuild_route"],
            case["structural_fields"],
        )
        if observed_case_bindings != expected_case_bindings:
            raise TaskPackageError(
                "lifecycle_probe_case_binding_mismatch",
                architecture_id,
                "request routes and structural fields disagree with candidate evidence",
            )
        for binding_name in ("config", "input"):
            binding = cast(dict[str, str], case[binding_name])
            bound_paths.append(binding["path"])
    if len(bound_paths) != len(set(bound_paths)):
        raise TaskPackageError(
            "lifecycle_probe_case_binding_mismatch",
            bound_paths,
            "per-case config and input paths must be unique",
        )
    output_dir = str(payload["lifecycle_output_dir"])
    if output_dir == "benchmark/es_f1" or output_dir.startswith("benchmark/es_f1/"):
        raise TaskPackageError(
            "lifecycle_probe_path_invalid",
            output_dir,
            "lifecycle output cannot overlap frozen visible assets",
        )
    return payload


def load_lifecycle_probe_result(
    path: Path,
    *,
    expected_architecture_ids: tuple[str, ...] | None = None,
    expected_candidate_id: str | None = None,
) -> dict[str, object]:
    """Load candidate artifact paths; evaluator-owned behavior stays out of the record."""

    payload = _load_canonical_json(
        Path(path),
        schema_path=_TASK_ASSET_ROOT / "lifecycle-probe-result.schema.json",
    )
    if expected_architecture_ids is None or expected_candidate_id is None:
        raise TaskPackageError(
            "lifecycle_probe_result_context_missing",
            None,
            "the evaluator must supply the request-derived architecture order "
            "and candidate ID",
        )
    rows = cast(list[dict[str, str]], payload["architecture_results"])
    observed_ids = tuple(row["architecture_id"] for row in rows)
    if (
        len(expected_architecture_ids) != 15
        or expected_architecture_ids[:14] != F1_BUILTIN_ARCHITECTURES
        or expected_architecture_ids[-1] in set(F1_BUILTIN_ARCHITECTURES)
        or observed_ids != expected_architecture_ids
    ):
        raise TaskPackageError(
            "lifecycle_probe_result_matrix_mismatch",
            observed_ids,
            "result rows must match the request-derived fifteen-row order",
        )
    if payload["candidate_id"] != expected_candidate_id:
        raise TaskPackageError(
            "lifecycle_probe_result_candidate_mismatch",
            payload["candidate_id"],
            "result candidate ID must match the request-derived candidate ID",
        )
    artifact_paths = tuple(
        artifact_path
        for row in rows
        for artifact_path in (row["checkpoint_path"], row["bundle_path"])
    )
    if len(artifact_paths) != len(set(artifact_paths)) or any(
        artifact_path == "benchmark/es_f1"
        or artifact_path.startswith("benchmark/es_f1/")
        for artifact_path in artifact_paths
    ):
        raise TaskPackageError(
            "lifecycle_probe_artifact_path_invalid",
            artifact_paths,
            "every checkpoint and bundle path must be unique",
        )
    return payload


def _all_git_objects(repository: Path) -> tuple[tuple[str, str], ...]:
    output = _run_git(
        repository,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype)",
    )
    rows: list[tuple[str, str]] = []
    for line in output.splitlines():
        parts = line.decode("ascii", errors="strict").split(" ")
        if len(parts) != 2:
            raise TaskPackageError(
                "task_seed_repository_invalid",
                line,
                "Git object inventory is malformed",
            )
        rows.append((parts[0], parts[1]))
    return tuple(sorted(rows))


def verify_task_seed(locator: Path, manifest: TaskSeedManifest) -> TaskSeedResult:
    """Fail closed unless a seed is the exact two-commit visible-asset overlay."""

    _require_visible_asset_allowlist(manifest.visible_assets)
    repository = Path(locator)
    try:
        resolved = repository.resolve(strict=True)
    except OSError as exc:
        raise TaskPackageError(
            "task_seed_repository_invalid",
            str(repository),
            "task-seed repository is missing",
        ) from exc
    if repository != resolved or not repository.is_absolute():
        raise TaskPackageError(
            "task_seed_locator_invalid",
            str(repository),
            "task-seed repository must be canonical and absolute",
        )
    if _run_git(repository, "rev-parse", "--is-bare-repository") != b"true\n":
        raise TaskPackageError(
            "task_seed_repository_invalid",
            str(repository),
            "task-seed repository must be bare",
        )
    escape_paths = tuple(
        path.relative_to(repository).as_posix()
        for path in (
            repository / "objects" / "info" / "alternates",
            repository / "info" / "grafts",
            repository / "shallow",
            repository / "refs" / "replace",
        )
        if os.path.lexists(path)
    )
    if escape_paths:
        raise TaskPackageError(
            "task_seed_repository_escape",
            escape_paths,
            "task-seed repository declares substituted or external identity",
        )
    if _run_git(repository, "remote") != b"":
        raise TaskPackageError(
            "task_seed_repository_escape",
            str(repository),
            "task-seed repository must not declare remotes",
        )
    head = _run_git(repository, "symbolic-ref", "HEAD").decode().strip()
    if head != "refs/heads/task-seed":
        raise TaskPackageError(
            "task_seed_history_mismatch", head, "task-seed HEAD changed"
        )
    refs = tuple(
        line.decode("ascii")
        for line in _run_git(
            repository, "for-each-ref", "--format=%(refname) %(objectname)"
        ).splitlines()
    )
    expected_ref = f"refs/heads/task-seed {manifest.commit}"
    if refs != (expected_ref,):
        raise TaskPackageError(
            "task_seed_history_mismatch",
            refs,
            "task-seed must expose exactly one canonical ref",
        )
    history = tuple(
        line.decode("ascii")
        for line in _run_git(
            repository, "rev-list", "--parents", "--topo-order", "--all"
        ).splitlines()
    )
    if history != (
        f"{manifest.commit} {manifest.parent_commit}",
        manifest.parent_commit,
    ):
        raise TaskPackageError(
            "task_seed_history_mismatch",
            history,
            "task seed must contain the exact parent and one child",
        )
    child_content = _run_git(repository, "cat-file", "commit", manifest.commit)
    if child_content != render_task_seed_commit_content(manifest):
        raise TaskPackageError(
            "task_seed_history_mismatch",
            manifest.commit,
            "task-seed child commit bytes changed",
        )
    parent_content = _run_git(
        repository, "cat-file", "commit", manifest.parent_commit
    )
    canonical_parent_content = _run_git(
        manifest.parent_locator, "cat-file", "commit", manifest.parent_commit
    )
    if parent_content != canonical_parent_content:
        raise TaskPackageError(
            "task_seed_parent_mismatch",
            manifest.parent_commit,
            "parent projection commit bytes changed",
        )
    resolved_tree = (
        _run_git(repository, "rev-parse", f"{manifest.commit}^{{tree}}")
        .decode("ascii")
        .strip()
    )
    parent_tree = (
        _run_git(repository, "rev-parse", f"{manifest.parent_commit}^{{tree}}")
        .decode("ascii")
        .strip()
    )
    if resolved_tree != manifest.tree or parent_tree != manifest.parent_tree:
        raise TaskPackageError(
            "task_seed_tree_mismatch",
            (resolved_tree, parent_tree),
            "task-seed child or parent tree changed",
        )
    changes = tuple(
        line.decode("utf-8")
        for line in _run_git(
            repository,
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "--no-renames",
            "-r",
            manifest.commit,
        ).splitlines()
    )
    expected_changes = tuple(f"A\t{row.target_path}" for row in manifest.visible_assets)
    if changes != expected_changes:
        raise TaskPackageError(
            "task_seed_overlay_mismatch",
            changes,
            "child changes are not exactly the frozen visible assets",
        )
    for row in manifest.visible_assets:
        child_row = _run_git(
            repository, "ls-tree", manifest.commit, "--", row.target_path
        ).decode("utf-8")
        expected = f"{row.mode} {row.object_type} {row.oid}\t{row.target_path}\n"
        if child_row != expected:
            raise TaskPackageError(
                "task_seed_overlay_mismatch",
                row.target_path,
                "visible asset Git row changed",
            )
        if _run_git(
            repository, "ls-tree", manifest.parent_commit, "--", row.target_path
        ) != b"":
            raise TaskPackageError(
                "task_seed_overlay_mismatch",
                row.target_path,
                "visible asset already exists in the parent projection",
            )
    try:
        completed = subprocess.run(
            (
                "git",
                "-C",
                str(repository),
                "fsck",
                "--full",
                "--strict",
                "--no-reflogs",
                "--unreachable",
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
    except OSError as exc:
        raise TaskPackageError(
            "task_seed_git_failed", str(repository), "strict Git fsck could not launch"
        ) from exc
    if completed.returncode != 0:
        raise TaskPackageError(
            "task_seed_repository_invalid",
            (completed.stdout + completed.stderr).decode("utf-8", errors="replace"),
            "strict Git fsck failed",
        )
    all_rows = _all_git_objects(repository)
    all_ids = frozenset(oid for oid, _ in all_rows)
    reachable = frozenset(
        line.split(b" ", 1)[0].decode("ascii")
        for line in _run_git(repository, "rev-list", "--objects", "--all").splitlines()
    )
    extras = tuple(sorted(all_ids - reachable))
    missing = tuple(sorted(reachable - all_ids))
    if extras or missing:
        raise TaskPackageError(
            "task_seed_object_closure_mismatch",
            {"extra": extras, "missing": missing},
            "task-seed object inventory is not its exact reachable closure",
        )
    commits = tuple(sorted(oid for oid, kind in all_rows if kind == "commit"))
    if (
        len(all_rows) != manifest.object_count
        or commits != tuple(sorted((manifest.parent_commit, manifest.commit)))
    ):
        raise TaskPackageError(
            "task_seed_object_closure_mismatch",
            {"object_count": len(all_rows), "commits": commits},
            "task-seed object count or commit set changed",
        )
    snapshot = directory_snapshot_digest(repository)
    if snapshot != manifest.repository_snapshot_digest:
        raise TaskPackageError(
            "task_seed_repository_snapshot_mismatch",
            snapshot,
            "task-seed repository bytes changed",
        )
    return TaskSeedResult(
        locator=repository,
        commit=manifest.commit,
        tree=manifest.tree,
        parent_commit=manifest.parent_commit,
        commit_count=2,
        object_count=len(all_rows),
        unreachable_object_count=0,
        reused=True,
    )


def _copy_parent_objects(parent: Path, target: Path, commit: str) -> None:
    git_environment = _git_environment()
    try:
        pack = subprocess.Popen(
            ("git", "-C", str(parent), "pack-objects", "--stdout", "--revs"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=git_environment,
        )
        if pack.stdin is None or pack.stdout is None:
            raise OSError("Git pack pipes were not created")
        pack.stdin.write(commit.encode("ascii") + b"\n")
        pack.stdin.close()
        indexed = subprocess.run(
            ("git", "-C", str(target), "index-pack", "--stdin"),
            check=False,
            stdin=pack.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=git_environment,
        )
        pack.stdout.close()
        pack_stderr = pack.stderr.read() if pack.stderr is not None else b""
        pack_exit = pack.wait()
    except OSError as exc:
        raise TaskPackageError(
            "task_seed_materialization_failed",
            str(target),
            "parent object transfer could not launch",
        ) from exc
    if pack_exit != 0 or indexed.returncode != 0:
        raise TaskPackageError(
            "task_seed_materialization_failed",
            (pack_stderr + indexed.stderr).decode("utf-8", errors="replace"),
            "parent object transfer failed",
        )


def _verify_parent_projection(locator: Path, manifest_path: Path) -> None:
    script = "\n".join(
        (
            "import sys",
            "from pathlib import Path",
            "from scripts.experiments.es.projection import (",
            "    load_projection_manifest,",
            "    verify_projection,",
            ")",
            "manifest = load_projection_manifest(Path(sys.argv[2]))",
            "verify_projection(Path(sys.argv[1]), manifest)",
        )
    )
    try:
        completed = subprocess.run(
            (
                sys.executable,
                "-c",
                script,
                str(locator),
                str(manifest_path),
            ),
            check=False,
            cwd=REPOSITORY_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment({"PYTHONDONTWRITEBYTECODE": "1"}),
        )
    except OSError as exc:
        raise TaskPackageError(
            "task_seed_parent_verification_failed",
            str(locator),
            "parent projection verifier could not launch",
        ) from exc
    if completed.returncode != 0:
        raise TaskPackageError(
            "task_seed_parent_verification_failed",
            {
                "exit_code": completed.returncode,
                "stderr": completed.stderr.decode("utf-8", errors="replace"),
            },
            "parent projection failed its full corruption and closure verification",
        )


def materialize_task_seed(
    manifest: TaskSeedManifest,
    *,
    storage_root: Path | None = None,
) -> TaskSeedResult:
    """Create or reuse the immutable child seed without touching its parent."""

    _require_visible_asset_allowlist(manifest.visible_assets)
    parent_before = directory_snapshot_digest(manifest.parent_locator)
    if parent_before != manifest.parent_snapshot_digest:
        raise TaskPackageError(
            "task_seed_parent_snapshot_mismatch",
            parent_before,
            "canonical source projection bytes changed before seed creation",
        )
    from scripts.experiments.es.projection import load_projection_manifest

    parent_manifest_path = _repository_path(
        manifest.raw["parent_projection"]["manifest_path"],  # type: ignore[index]
        label="parent projection manifest path",
    )
    parent_manifest = load_projection_manifest(parent_manifest_path)
    _verify_parent_projection(manifest.parent_locator, parent_manifest_path)
    parent_manifest_locator = (
        parent_manifest.canonical_storage_root / parent_manifest.locator_relative_path
    )
    if (
        parent_manifest.projection_commit != manifest.parent_commit
        or parent_manifest.retained_tree != manifest.parent_tree
        or parent_manifest_locator != manifest.parent_locator
    ):
        raise TaskPackageError(
            "task_seed_parent_mismatch",
            {
                "commit": parent_manifest.projection_commit,
                "locator": str(parent_manifest_locator),
                "tree": parent_manifest.retained_tree,
            },
            "parent projection manifest disagrees with the task-seed binding",
        )

    root = (
        Path(manifest.raw["repository"]["storage_root"])  # type: ignore[index]
        if storage_root is None
        else Path(storage_root)
    )
    if not root.is_absolute() or root.resolve(strict=False) != root:
        raise TaskPackageError(
            "task_seed_locator_invalid",
            str(root),
            "task-seed storage root must be canonical and absolute",
        )
    namespace = root / "git-sha1"
    namespace.mkdir(parents=True, exist_ok=True)
    locator = namespace / manifest.commit
    if locator.exists():
        existing = verify_task_seed(locator, manifest)
        if directory_snapshot_digest(manifest.parent_locator) != parent_before:
            raise TaskPackageError(
                "task_seed_parent_snapshot_mismatch",
                str(manifest.parent_locator),
                "source projection changed while reusing the task seed",
            )
        return existing

    with tempfile.TemporaryDirectory(prefix=".es-task-seed-", dir=namespace) as temp:
        temporary_root = Path(temp)
        repository = temporary_root / "repository.git"
        _run_git(temporary_root, "init", "--bare", str(repository))
        _copy_parent_objects(manifest.parent_locator, repository, manifest.parent_commit)
        index = temporary_root / "task-seed.index"
        index_env = {"GIT_INDEX_FILE": str(index)}
        _run_git(
            repository,
            "read-tree",
            manifest.parent_commit,
            environment=index_env,
        )
        for row in manifest.visible_assets:
            source = _repository_path(
                row.source_path, label="visible asset source path"
            )
            try:
                asset_bytes = source.read_bytes()
            except OSError as exc:
                raise TaskPackageError(
                    "task_seed_asset_mismatch",
                    row.source_path,
                    "visible asset source is unreadable during seed creation",
                ) from exc
            if (
                len(asset_bytes) != row.byte_count
                or "sha256:" + hashlib.sha256(asset_bytes).hexdigest()
                != row.digest
                or _git_object_id("blob", asset_bytes) != row.oid
            ):
                raise TaskPackageError(
                    "task_seed_asset_mismatch",
                    row.source_path,
                    "visible asset source changed after manifest binding",
                )
            oid = (
                _run_git(
                    repository,
                    "hash-object",
                    "-w",
                    "--stdin",
                    input_bytes=asset_bytes,
                )
                .decode("ascii")
                .strip()
            )
            if oid != row.oid:
                raise TaskPackageError(
                    "task_seed_asset_mismatch",
                    row.source_path,
                    "Git wrote a different visible-asset blob identity",
                )
            _run_git(
                repository,
                "update-index",
                "--add",
                "--cacheinfo",
                f"{row.mode},{row.oid},{row.target_path}",
                environment=index_env,
            )
        tree = (
            _run_git(repository, "write-tree", environment=index_env)
            .decode("ascii")
            .strip()
        )
        if tree != manifest.tree:
            raise TaskPackageError(
                "task_seed_tree_mismatch",
                tree,
                "rendered task-seed tree changed",
            )
        recipe = manifest.raw["recipe"]
        assert isinstance(recipe, dict)
        author = recipe["author"]
        assert isinstance(author, dict)
        identity_env = {
            "GIT_AUTHOR_NAME": str(author["name"]),
            "GIT_AUTHOR_EMAIL": str(author["email"]),
            "GIT_AUTHOR_DATE": f"{author['timestamp']} {author['timezone']}",
            "GIT_COMMITTER_NAME": str(author["name"]),
            "GIT_COMMITTER_EMAIL": str(author["email"]),
            "GIT_COMMITTER_DATE": f"{author['timestamp']} {author['timezone']}",
        }
        commit = (
            _run_git(
                repository,
                "commit-tree",
                tree,
                "-p",
                manifest.parent_commit,
                input_bytes=manifest.commit_message,
                environment=identity_env,
            )
            .decode("ascii")
            .strip()
        )
        if commit != manifest.commit:
            raise TaskPackageError(
                "task_seed_recipe_mismatch",
                commit,
                "Git rendered a different task-seed commit identity",
            )
        _run_git(repository, "update-ref", "refs/heads/task-seed", commit)
        _run_git(repository, "symbolic-ref", "HEAD", "refs/heads/task-seed")
        index.unlink()
        staged = verify_task_seed(repository, manifest)
        try:
            repository.rename(locator)
        except OSError:
            if not locator.exists():
                raise
            existing = verify_task_seed(locator, manifest)
            if directory_snapshot_digest(manifest.parent_locator) != parent_before:
                raise TaskPackageError(
                    "task_seed_parent_snapshot_mismatch",
                    str(manifest.parent_locator),
                    "source projection changed during concurrent seed creation",
                )
            return existing
        created = TaskSeedResult(
            locator=locator,
            commit=staged.commit,
            tree=staged.tree,
            parent_commit=staged.parent_commit,
            commit_count=staged.commit_count,
            object_count=staged.object_count,
            unreachable_object_count=staged.unreachable_object_count,
            reused=False,
        )
    if directory_snapshot_digest(manifest.parent_locator) != parent_before:
        raise TaskPackageError(
            "task_seed_parent_snapshot_mismatch",
            str(manifest.parent_locator),
            "source projection changed during task-seed creation",
        )
    return created
