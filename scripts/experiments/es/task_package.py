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
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_TASK_ASSET_ROOT = REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/task"
_TASK_PROFILE = REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/task-profile.json"
_TASK_PROFILE_SCHEMA = _TASK_PROFILE.with_name("task-profile.schema.json")

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
    from scripts.experiments.es.projection import FOCUSED_TEST_PATHS

    if tuple(pre_edit) != FOCUSED_TEST_PATHS or candidate != [
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


def load_task_profile(path: Path) -> TaskProfile:
    """Load and cross-check the closed Task-2 F1 profile."""

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
    contract = _load_canonical_json(
        contract_path,
        schema_path=contract_schema_path,
    )
    payload_fixed_outputs = cast(list[str], payload["fixed_output_paths"])
    payload_declared_outputs = cast(
        list[str], payload["candidate_declared_output_ids"]
    )
    payload_hard_ids = cast(list[str], payload["hard_clause_ids"])
    payload_dispositions = cast(list[str], payload["finding_dispositions"])
    payload_perspectives = cast(list[str], payload["reviewer_perspective_ids"])
    payload_selectors = cast(list[str], payload["focused_selectors"])
    payload_claim_ids = cast(list[str], payload["claim_limit_ids"])
    payload_review_dimensions = cast(list[str], payload["review_dimension_ids"])
    contract_dispositions = cast(list[str], contract["finding_dispositions"])
    contract_selectors = cast(list[str], contract["focused_selectors"])
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
    assert isinstance(seed_binding, dict)
    assert isinstance(brief_binding, dict)
    assert isinstance(schema_bindings, list)
    assert isinstance(check_binding, dict)
    seed_path = _repository_path(
        seed_binding["manifest_path"], label="task-seed manifest path"
    )
    seed_schema_path = _repository_path(
        seed_binding["schema_path"], label="task-seed schema path"
    )
    if _digest(seed_path) != seed_binding["manifest_sha256"]:
        raise TaskPackageError(
            "task_package_digest_mismatch",
            str(seed_path),
            "task-seed manifest digest changed",
        )
    if _digest(seed_schema_path) != seed_binding["schema_sha256"]:
        raise TaskPackageError(
            "task_package_digest_mismatch",
            str(seed_schema_path),
            "task-seed schema digest changed",
        )
    seed = load_task_seed_manifest(seed_path)
    if seed.commit != seed_binding["commit"] or seed.tree != seed_binding["tree"]:
        raise TaskPackageError(
            "task_package_binding_mismatch",
            (seed.commit, seed.tree),
            "task profile disagrees with the task-seed identity",
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
        environment_name=str(profile_environment["conda_environment"]),
        claim_limit_ids=claim_ids,
        raw=payload,
    )


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

    rows: list[VisibleAsset] = []
    canonical_rows: list[dict[str, object]] = []
    for raw_row in assets_payload["rows"]:  # type: ignore[union-attr]
        assert isinstance(raw_row, dict)
        source_path = str(raw_row["source_path"])
        target_path = str(raw_row["target_path"])
        source = _repository_path(source_path, label="visible asset source path")
        try:
            asset_bytes = source.read_bytes()
        except OSError as exc:
            raise TaskPackageError(
                "task_seed_asset_unreadable", source_path, "visible asset is unreadable"
            ) from exc
        digest = "sha256:" + hashlib.sha256(asset_bytes).hexdigest()
        oid = _git_object_id("blob", asset_bytes)
        if (
            len(asset_bytes) != raw_row["bytes"]
            or digest != raw_row["sha256"]
            or oid != raw_row["oid"]
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
        "Task-Seed-Policy: es-f1-task-seed.v1\n"
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
    if not parent_locator.is_absolute() or parent_locator.resolve(strict=False) != parent_locator:
        raise TaskPackageError(
            "task_seed_parent_mismatch",
            str(parent_locator),
            "parent projection locator is not canonical and absolute",
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
    return result


def load_candidate_extension_evidence(path: Path) -> dict[str, object]:
    """Validate candidate declarations without manufacturing evaluator verdicts."""

    payload = _load_canonical_json(
        Path(path),
        schema_path=_TASK_ASSET_ROOT / "candidate-extension-evidence.schema.json",
    )
    profile = load_task_profile(_TASK_PROFILE)
    claims = payload["claims"]
    representative = payload["representative_architecture"]
    witness = payload["witness_architecture"]
    structural_fields = payload["structural_fields"]
    assert isinstance(claims, list)
    assert isinstance(representative, dict)
    assert isinstance(witness, dict)
    assert isinstance(structural_fields, list)
    claim_ids = tuple(row["clause_id"] for row in claims)
    if claim_ids != profile.hard_clause_ids:
        raise TaskPackageError(
            "candidate_evidence_clause_mismatch",
            claim_ids,
            "candidate claims must enumerate every hard clause exactly once in order",
        )
    if (
        representative["frozen_registry_member"] is not True
        or witness["frozen_registry_member"] is not False
        or representative["public_id"] == witness["public_id"]
    ):
        raise TaskPackageError(
            "candidate_evidence_architecture_invalid",
            (representative, witness),
            "representative and witness roles are inconsistent or ambiguous",
        )
    field_names = tuple(row["name"] for row in structural_fields)
    if len(set(field_names)) != len(field_names) or any(
        row["baseline_value"] == row["alternate_value"] for row in structural_fields
    ):
        raise TaskPackageError(
            "candidate_evidence_structural_field_invalid",
            structural_fields,
            "structural fields must be unique and have distinct alternate values",
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
    """Load one evaluator-owned lifecycle request with distinct architecture roles."""

    payload = _load_canonical_json(
        Path(path),
        schema_path=_TASK_ASSET_ROOT / "lifecycle-probe-request.schema.json",
    )
    if payload["representative_architecture"] == payload["witness_architecture"]:
        raise TaskPackageError(
            "lifecycle_probe_architecture_ambiguous",
            payload["representative_architecture"],
            "representative and witness architecture IDs must differ",
        )
    output_dir = str(payload["lifecycle_output_dir"])
    if output_dir == "benchmark/es_f1" or output_dir.startswith("benchmark/es_f1/"):
        raise TaskPackageError(
            "lifecycle_probe_path_invalid",
            output_dir,
            "lifecycle output cannot overlap frozen visible assets",
        )
    return payload


def load_lifecycle_probe_result(path: Path) -> dict[str, object]:
    """Load candidate artifact paths; evaluator-owned behavior stays out of the record."""

    return _load_canonical_json(
        Path(path),
        schema_path=_TASK_ASSET_ROOT / "lifecycle-probe-result.schema.json",
    )


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
            asset = _repository_path(row.source_path, label="visible asset source path")
            oid = (
                _run_git(
                    repository,
                    "hash-object",
                    "-w",
                    "--stdin",
                    input_bytes=asset.read_bytes(),
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
