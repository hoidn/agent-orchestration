"""Deterministic, history-free Git source projections for study inputs."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")

FOCUSED_TEST_PATHS = (
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
)

_FORBIDDEN_F1_MODULE_PREFIXES = (
    "PtychoNN",
    "notebooks.archive.ePIE_recon_simulation",
    "ptycho.FRC",
    "ptycho.evaluation",
    "scripts.orchestration",
)
_PTYCHOPINN_EDITABLE_PREFIX = "__editable___ptychopinn_"
_F1_EXCLUDED_PATHS = (
    ".claude",
    ".gitmodules",
    "PtychoNN",
    "notebooks/archive/ePIE_recon_simulation",
    "ptycho/FRC",
    "scripts/orchestration",
)


class ProjectionError(ValueError):
    """A projection input or artifact fails its closed deterministic contract."""

    def __init__(self, code: str, value: object, detail: str) -> None:
        super().__init__(f"{code}: {detail}: {value!r}")
        self.code = code
        self.value = value
        self.detail = detail


@dataclass(frozen=True)
class ExclusionRow:
    mode: str
    object_type: str
    oid: str
    path: str


@dataclass(frozen=True)
class RetainedRow:
    mode: str
    object_type: str
    oid: str
    path: str
    link_target: str | None = None


@dataclass(frozen=True)
class SourceInspection:
    source_commit: str
    source_tree: str
    source_leaf_count: int
    excluded_rows: tuple[ExclusionRow, ...]
    retained_rows: tuple[RetainedRow, ...]
    retained_leaf_count: int
    retained_inventory_digest: str
    retained_mode_counts: tuple[tuple[str, int], ...]
    symlinks: tuple[RetainedRow, ...]


@dataclass(frozen=True)
class ProjectionResult:
    locator: Path
    commit: str
    tree: str
    object_ids: tuple[str, ...]
    parent_count: int
    unreachable_object_count: int
    reused: bool


@dataclass(frozen=True)
class ImportOriginProbeResult:
    report_path: Path
    report_digest: str
    exit_code: int
    collected: int
    outcomes: tuple[tuple[str, int], ...]
    removed_hooks: tuple[str, ...]
    forbidden_roots: tuple[Path, ...]
    loaded_forbidden_modules: tuple[str, ...]
    forbidden_origin_rows: tuple[tuple[str, str], ...]
    projected_origin_rows: tuple[tuple[str, str], ...]
    module_origin_rows: tuple[tuple[str, str], ...]
    cache_artifacts: tuple[str, ...]
    plugin_autoload_disabled: bool
    outside_project_origin_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class StaticImportClosure:
    file_rows: tuple[tuple[str, str], ...]
    imported_modules: tuple[str, ...]
    unresolved_imports: tuple[str, ...]
    forbidden_imports: tuple[str, ...]
    excluded_path_rows: tuple[tuple[str, str], ...]
    digest: str


@dataclass(frozen=True)
class ProjectionManifest:
    source_repository: str
    source_commit: str
    source_tree: str
    exclusions: tuple[ExclusionRow, ...]
    exclusion_digest: str
    retained_leaf_count: int
    retained_mode_counts: tuple[tuple[str, int], ...]
    retained_inventory_digest: str
    retained_tree: str
    recipe_policy: str
    author_name: str
    author_email: str
    author_timestamp: int
    author_timezone: str
    commit_message: bytes
    message_digest: str
    commit_content_bytes: int
    commit_content_digest: str
    projection_commit: str
    canonical_storage_root: Path
    locator_relative_path: str


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _require_dict(
    value: object,
    *,
    keys: set[str],
    label: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ProjectionError(
            "projection_manifest_noncanonical",
            value,
            f"{label} must contain exactly {sorted(keys)!r}",
        )
    return value


def _require_string(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ProjectionError(
            "projection_manifest_noncanonical",
            value,
            f"{label} must be a string",
        )
    return value


def _require_sha1(value: object, *, label: str) -> str:
    text = _require_string(value, label=label)
    if _SHA1_RE.fullmatch(text) is None:
        raise ProjectionError(
            "projection_manifest_noncanonical",
            value,
            f"{label} must be one lowercase Git SHA-1",
        )
    return text


def _require_sha256(value: object, *, label: str) -> str:
    text = _require_string(value, label=label)
    if _SHA256_RE.fullmatch(text) is None:
        raise ProjectionError(
            "projection_manifest_noncanonical",
            value,
            f"{label} must be one sha256-prefixed digest",
        )
    return text


def git_object_id(object_type: str, payload: bytes) -> str:
    """Return the SHA-1 object identity for exact Git-framed bytes."""

    if not isinstance(object_type, str) or not object_type or "\0" in object_type:
        raise TypeError("Git object type must be nonempty NUL-free text")
    if not isinstance(payload, bytes):
        raise TypeError("Git object payload must be bytes")
    framed = object_type.encode("ascii") + b" " + str(len(payload)).encode("ascii")
    return hashlib.sha1(framed + b"\0" + payload).hexdigest()


def render_commit_content(manifest: ProjectionManifest) -> bytes:
    """Render the exact parentless root-commit content bound by a manifest."""

    identity = (
        f"{manifest.author_name} <{manifest.author_email}> "
        f"{manifest.author_timestamp} {manifest.author_timezone}"
    )
    return (
        f"tree {manifest.retained_tree}\n"
        f"author {identity}\n"
        f"committer {identity}\n"
        "\n"
    ).encode("utf-8") + manifest.commit_message


def load_projection_manifest(path: Path) -> ProjectionManifest:
    """Load one exact canonical v1 manifest and verify all internal vectors."""

    manifest_path = Path(path)
    try:
        raw = manifest_path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectionError(
            "projection_manifest_unreadable",
            str(manifest_path),
            "manifest is missing or unreadable",
        ) from exc
    if raw != canonical_json_bytes(value):
        raise ProjectionError(
            "projection_manifest_noncanonical",
            str(manifest_path),
            "manifest bytes are not canonical JSON followed by one LF",
        )
    top = _require_dict(
        value,
        keys={
            "schema_version",
            "source",
            "exclusions",
            "retained",
            "recipe",
            "policies",
            "locator",
        },
        label="manifest",
    )
    if top["schema_version"] != "es_source_projection.v1":
        raise ProjectionError(
            "projection_manifest_noncanonical",
            top["schema_version"],
            "schema_version is unsupported",
        )

    source = _require_dict(
        top["source"],
        keys={"repository", "commit", "tree"},
        label="source",
    )
    exclusions = _require_dict(
        top["exclusions"],
        keys={"rows", "serialization", "sha256"},
        label="exclusions",
    )
    if exclusions["serialization"] != "canonical-json-lf.v1":
        raise ProjectionError(
            "projection_manifest_noncanonical",
            exclusions["serialization"],
            "exclusion serialization is unsupported",
        )
    row_values = exclusions["rows"]
    if not isinstance(row_values, list):
        raise ProjectionError(
            "projection_manifest_noncanonical",
            row_values,
            "exclusion rows must be a list",
        )
    parsed_rows: list[ExclusionRow] = []
    for index, raw_row in enumerate(row_values):
        row = _require_dict(
            raw_row,
            keys={"mode", "object_type", "oid", "path"},
            label=f"exclusion row {index}",
        )
        parsed_rows.append(
            ExclusionRow(
                mode=_require_string(row["mode"], label="exclusion mode"),
                object_type=_require_string(
                    row["object_type"], label="exclusion object_type"
                ),
                oid=_require_sha1(row["oid"], label="exclusion oid"),
                path=_require_string(row["path"], label="exclusion path"),
            )
        )
    row_digest = "sha256:" + hashlib.sha256(
        canonical_json_bytes(row_values)
    ).hexdigest()
    exclusion_digest = _require_sha256(
        exclusions["sha256"], label="exclusion sha256"
    )
    if row_digest != exclusion_digest:
        raise ProjectionError(
            "projection_exclusion_digest_mismatch",
            row_digest,
            "exclusion rows do not match their digest",
        )

    retained = _require_dict(
        top["retained"],
        keys={
            "leaf_count",
            "mode_counts",
            "inventory_serialization",
            "inventory_sha256",
            "tree",
        },
        label="retained",
    )
    if retained["inventory_serialization"] != "git-ls-tree-r-z.v1":
        raise ProjectionError(
            "projection_manifest_noncanonical",
            retained["inventory_serialization"],
            "retained inventory serialization is unsupported",
        )
    leaf_count = retained["leaf_count"]
    if isinstance(leaf_count, bool) or not isinstance(leaf_count, int) or leaf_count < 0:
        raise ProjectionError(
            "projection_manifest_noncanonical",
            leaf_count,
            "retained leaf_count must be a nonnegative integer",
        )
    mode_counts = _require_dict(
        retained["mode_counts"],
        keys={"regular", "executable", "symlink"},
        label="retained mode_counts",
    )
    parsed_counts: list[tuple[str, int]] = []
    for name in ("regular", "executable", "symlink"):
        count = mode_counts[name]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ProjectionError(
                "projection_manifest_noncanonical",
                count,
                f"retained {name} count must be a nonnegative integer",
            )
        parsed_counts.append((name, count))
    if sum(count for _, count in parsed_counts) != leaf_count:
        raise ProjectionError(
            "projection_manifest_noncanonical",
            mode_counts,
            "retained mode counts do not sum to leaf_count",
        )

    recipe = _require_dict(
        top["recipe"],
        keys={
            "policy",
            "author",
            "message",
            "message_bytes",
            "message_sha256",
            "commit_content_bytes",
            "commit_content_sha256",
            "commit",
        },
        label="recipe",
    )
    author = _require_dict(
        recipe["author"],
        keys={"name", "email", "timestamp", "timezone"},
        label="recipe author",
    )
    timestamp = author["timestamp"]
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise ProjectionError(
            "projection_manifest_noncanonical",
            timestamp,
            "recipe author timestamp must be an integer",
        )
    recipe_policy = _require_string(recipe["policy"], label="recipe policy")
    if recipe_policy != "e-series-source-projection.v1":
        raise ProjectionError(
            "projection_manifest_noncanonical",
            recipe_policy,
            "recipe policy is unsupported",
        )
    message = _require_string(recipe["message"], label="recipe message").encode(
        "utf-8"
    )
    message_bytes = recipe["message_bytes"]
    if (
        isinstance(message_bytes, bool)
        or not isinstance(message_bytes, int)
        or message_bytes < 0
    ):
        raise ProjectionError(
            "projection_manifest_noncanonical",
            message_bytes,
            "recipe message_bytes must be a nonnegative integer",
        )
    message_digest = _require_sha256(
        recipe["message_sha256"], label="recipe message_sha256"
    )
    if message_bytes != len(message) or message_digest != (
        "sha256:" + hashlib.sha256(message).hexdigest()
    ):
        raise ProjectionError(
            "projection_recipe_digest_mismatch",
            recipe["message_sha256"],
            "commit message byte vector does not match its binding",
        )

    policies = _require_dict(
        top["policies"],
        keys={"lfs", "object_closure", "symlinks"},
        label="policies",
    )
    expected_policies = {
        "lfs": "reject-pointers-and-filter-attributes.v1",
        "object_closure": "reachable-only.v1",
        "symlinks": "lexically-contained-relative-utf8.v1",
    }
    if policies != expected_policies:
        raise ProjectionError(
            "projection_manifest_noncanonical",
            policies,
            "projection policies are unsupported",
        )
    locator = _require_dict(
        top["locator"],
        keys={"namespace", "object_format", "relative_path", "storage_root"},
        label="locator",
    )
    if (
        locator["namespace"] != "es-source-projections.v1"
        or locator["object_format"] != "sha1"
    ):
        raise ProjectionError(
            "projection_manifest_noncanonical",
            locator,
            "projection locator policy is unsupported",
        )

    commit_content_bytes = recipe["commit_content_bytes"]
    if (
        isinstance(commit_content_bytes, bool)
        or not isinstance(commit_content_bytes, int)
        or commit_content_bytes < 0
    ):
        raise ProjectionError(
            "projection_manifest_noncanonical",
            commit_content_bytes,
            "recipe commit_content_bytes must be a nonnegative integer",
        )
    storage_root_text = _require_string(
        locator["storage_root"], label="locator storage_root"
    )
    storage_root = Path(storage_root_text)
    if (
        not storage_root.is_absolute()
        or storage_root.resolve(strict=False) != storage_root
    ):
        raise ProjectionError(
            "projection_manifest_noncanonical",
            storage_root_text,
            "locator storage_root must be canonical absolute text",
        )

    manifest = ProjectionManifest(
        source_repository=_require_string(
            source["repository"], label="source repository"
        ),
        source_commit=_require_sha1(source["commit"], label="source commit"),
        source_tree=_require_sha1(source["tree"], label="source tree"),
        exclusions=tuple(parsed_rows),
        exclusion_digest=exclusion_digest,
        retained_leaf_count=leaf_count,
        retained_mode_counts=tuple(parsed_counts),
        retained_inventory_digest=_require_sha256(
            retained["inventory_sha256"], label="retained inventory_sha256"
        ),
        retained_tree=_require_sha1(retained["tree"], label="retained tree"),
        recipe_policy=recipe_policy,
        author_name=_require_string(author["name"], label="recipe author name"),
        author_email=_require_string(author["email"], label="recipe author email"),
        author_timestamp=timestamp,
        author_timezone=_require_string(
            author["timezone"], label="recipe author timezone"
        ),
        commit_message=message,
        message_digest=message_digest,
        commit_content_bytes=commit_content_bytes,
        commit_content_digest=_require_sha256(
            recipe["commit_content_sha256"], label="recipe commit_content_sha256"
        ),
        projection_commit=_require_sha1(recipe["commit"], label="recipe commit"),
        canonical_storage_root=storage_root,
        locator_relative_path=_require_string(
            locator["relative_path"], label="locator relative_path"
        ),
    )
    content = render_commit_content(manifest)
    if (
        manifest.commit_content_bytes != len(content)
        or manifest.commit_content_digest
        != "sha256:" + hashlib.sha256(content).hexdigest()
        or manifest.projection_commit != git_object_id("commit", content)
    ):
        raise ProjectionError(
            "projection_recipe_digest_mismatch",
            manifest.projection_commit,
            "root commit content does not match its exact recipe",
        )
    if manifest.locator_relative_path != f"git-sha1/{manifest.projection_commit}":
        raise ProjectionError(
            "projection_manifest_noncanonical",
            manifest.locator_relative_path,
            "locator relative path does not match the projected commit",
        )
    return manifest


def _run_git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProjectionError(
            "projection_source_unreadable",
            str(repository),
            f"Git could not execute {' '.join(arguments)!r}",
        ) from exc
    return completed.stdout


def _decode_tree_rows(raw: bytes) -> tuple[tuple[RetainedRow, bytes], ...]:
    rows: list[tuple[RetainedRow, bytes]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, path_bytes = record.split(b"\t", 1)
            mode_bytes, type_bytes, oid_bytes = header.split(b" ", 2)
            mode = mode_bytes.decode("ascii", errors="strict")
            object_type = type_bytes.decode("ascii", errors="strict")
            oid = oid_bytes.decode("ascii", errors="strict")
            path = path_bytes.decode("utf-8", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProjectionError(
                "projection_source_inventory_invalid",
                record,
                "Git tree row is not canonical UTF-8 ls-tree data",
            ) from exc
        pure = PurePosixPath(path)
        if (
            not path
            or pure.is_absolute()
            or pure.as_posix() != path
            or any(part in {"", ".", ".."} for part in pure.parts)
            or "\n" in path
            or "\r" in path
        ):
            raise ProjectionError(
                "projection_source_inventory_invalid",
                path,
                "Git tree path is not canonical relative UTF-8 text",
            )
        if _SHA1_RE.fullmatch(oid) is None:
            raise ProjectionError(
                "projection_source_inventory_invalid",
                oid,
                "Git tree row has an invalid object identity",
            )
        rows.append((RetainedRow(mode, object_type, oid, path), record + b"\0"))
    return tuple(rows)


def _read_blob(repository: Path, oid: str) -> bytes:
    return _run_git(repository, "cat-file", "blob", oid)


def _blob_sizes(repository: Path, oids: tuple[str, ...]) -> dict[str, int]:
    unique = tuple(dict.fromkeys(oids))
    if not unique:
        return {}
    raw = _run_git(
        repository,
        "cat-file",
        "--batch-check=%(objectname) %(objectsize)",
        input_bytes=("\n".join(unique) + "\n").encode("ascii"),
    )
    sizes: dict[str, int] = {}
    for line in raw.splitlines():
        try:
            oid_bytes, size_bytes = line.split(b" ", 1)
            oid = oid_bytes.decode("ascii", errors="strict")
            size = int(size_bytes)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProjectionError(
                "projection_source_inventory_invalid",
                line,
                "Git object-size response is malformed",
            ) from exc
        sizes[oid] = size
    if set(sizes) != set(unique):
        raise ProjectionError(
            "projection_source_inventory_invalid",
            sorted(set(unique) - set(sizes)),
            "Git object-size response is incomplete",
        )
    return sizes


def _attributes_enable_lfs(payload: bytes) -> bool:
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if line and not line.startswith(b"#") and b"filter=lfs" in line.split():
            return True
    return False


def _is_lfs_pointer(payload: bytes) -> bool:
    return payload.startswith(b"version https://git-lfs.github.com/spec/v1\n")


def _contained_symlink_target(path: str, payload: bytes) -> str:
    try:
        target = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ProjectionError(
            "projection_source_symlink_unsupported",
            path,
            "symlink target is not UTF-8",
        ) from exc
    target_path = PurePosixPath(target)
    if not target or "\0" in target or target_path.is_absolute() or "\\" in target:
        raise ProjectionError(
            "projection_source_symlink_unsupported",
            path,
            "symlink target must be nonempty relative POSIX text",
        )
    resolved = list(PurePosixPath(path).parent.parts)
    for part in target_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not resolved:
                raise ProjectionError(
                    "projection_source_symlink_unsupported",
                    path,
                    "symlink target escapes the projected root",
                )
            resolved.pop()
        else:
            resolved.append(part)
    if not resolved:
        raise ProjectionError(
            "projection_source_symlink_unsupported",
            path,
            "symlink target resolves to the projected root",
        )
    return target


def validate_retained_entry(
    row: RetainedRow,
    payload: bytes | None,
    *,
    excluded_paths: tuple[str, ...] = (),
) -> RetainedRow:
    """Validate one retained leaf under the closed projection policies."""

    if row.object_type != "blob" or row.mode not in {"100644", "100755", "120000"}:
        raise ProjectionError(
            "projection_source_entry_unsupported",
            f"{row.mode}/{row.object_type} {row.path}",
            "retained entry has an unsupported Git mode or type",
        )
    if PurePosixPath(row.path).name == ".gitattributes":
        if payload is None:
            raise ProjectionError(
                "projection_source_inventory_invalid",
                row.path,
                "retained Git attributes payload was not supplied",
            )
        if _attributes_enable_lfs(payload):
            raise ProjectionError(
                "projection_source_lfs_unsupported",
                row.path,
                "retained Git attributes enable LFS",
            )
    if payload is not None and _is_lfs_pointer(payload):
        raise ProjectionError(
            "projection_source_lfs_unsupported",
            row.path,
            "retained blob is a Git LFS pointer",
        )
    if row.mode != "120000":
        return row
    if payload is None:
        raise ProjectionError(
            "projection_source_inventory_invalid",
            row.path,
            "retained symlink payload was not supplied",
        )
    target = _contained_symlink_target(row.path, payload)
    resolved_parts = list(PurePosixPath(row.path).parent.parts)
    for part in PurePosixPath(target).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            resolved_parts.pop()
        else:
            resolved_parts.append(part)
    resolved_target = PurePosixPath(*resolved_parts)
    for excluded_text in excluded_paths:
        excluded = PurePosixPath(excluded_text)
        if resolved_target.parts[: len(excluded.parts)] == excluded.parts:
            raise ProjectionError(
                "projection_source_symlink_unsupported",
                row.path,
                "symlink target depends on an excluded source root",
            )
    return RetainedRow(
        row.mode,
        row.object_type,
        row.oid,
        row.path,
        target,
    )


def inspect_source(
    repository: Path,
    manifest: ProjectionManifest,
) -> SourceInspection:
    """Verify the exact source tree and return its closed retained inventory."""

    candidate = Path(repository)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProjectionError(
            "projection_source_unreadable",
            str(candidate),
            "source repository cannot be resolved",
        ) from exc
    if not candidate.is_absolute() or candidate != resolved:
        raise ProjectionError(
            "projection_source_identity_mismatch",
            str(candidate),
            "source repository path must be canonical and absolute",
        )
    if str(candidate) != manifest.source_repository:
        raise ProjectionError(
            "projection_source_identity_mismatch",
            str(candidate),
            "source repository does not match the manifest locator",
        )
    resolved_commit = _run_git(
        candidate, "rev-parse", f"{manifest.source_commit}^{{commit}}"
    ).decode("ascii", errors="strict").strip()
    resolved_tree = _run_git(
        candidate, "rev-parse", f"{manifest.source_commit}^{{tree}}"
    ).decode("ascii", errors="strict").strip()
    if resolved_commit != manifest.source_commit:
        raise ProjectionError(
            "projection_source_identity_mismatch",
            resolved_commit,
            "source revision did not resolve to the exact manifest commit",
        )
    if resolved_tree != manifest.source_tree:
        raise ProjectionError(
            "projection_source_tree_mismatch",
            resolved_tree,
            "source revision tree does not match the manifest",
        )

    raw_inventory = _run_git(
        candidate, "ls-tree", "-rz", "-r", manifest.source_commit
    )
    decoded = _decode_tree_rows(raw_inventory)
    exclusion_paths = {row.path for row in manifest.exclusions}
    if len(exclusion_paths) != len(manifest.exclusions):
        raise ProjectionError(
            "projection_exclusion_set_mismatch",
            [row.path for row in manifest.exclusions],
            "manifest exclusion paths are repeated",
        )
    actual_exclusions: list[ExclusionRow] = []
    retained_pairs: list[tuple[RetainedRow, bytes]] = []
    for row, raw_row in decoded:
        if row.path in exclusion_paths:
            actual_exclusions.append(
                ExclusionRow(row.mode, row.object_type, row.oid, row.path)
            )
        else:
            retained_pairs.append((row, raw_row))
    if tuple(actual_exclusions) != manifest.exclusions:
        raise ProjectionError(
            "projection_exclusion_set_mismatch",
            actual_exclusions,
            "source exclusion rows do not exactly match the manifest",
        )

    retained_raw = b"".join(raw_row for _, raw_row in retained_pairs)
    retained_digest = "sha256:" + hashlib.sha256(retained_raw).hexdigest()
    if retained_digest != manifest.retained_inventory_digest:
        raise ProjectionError(
            "projection_retained_inventory_mismatch",
            retained_digest,
            "retained Git rows do not match the manifest digest",
        )
    if len(retained_pairs) != manifest.retained_leaf_count:
        raise ProjectionError(
            "projection_retained_inventory_mismatch",
            len(retained_pairs),
            "retained leaf count does not match the manifest",
        )

    counts = {"regular": 0, "executable": 0, "symlink": 0}
    blob_oids: list[str] = []
    for row, _ in retained_pairs:
        if row.object_type != "blob" or row.mode not in {"100644", "100755", "120000"}:
            raise ProjectionError(
                "projection_source_entry_unsupported",
                f"{row.mode}/{row.object_type} {row.path}",
                "retained entry has an unsupported Git mode or type",
            )
        counts[
            "regular"
            if row.mode == "100644"
            else "executable"
            if row.mode == "100755"
            else "symlink"
        ] += 1
        blob_oids.append(row.oid)
    actual_counts = tuple((name, counts[name]) for name in counts)
    if actual_counts != manifest.retained_mode_counts:
        raise ProjectionError(
            "projection_retained_inventory_mismatch",
            actual_counts,
            "retained mode counts do not match the manifest",
        )

    sizes = _blob_sizes(candidate, tuple(blob_oids))
    retained_rows: list[RetainedRow] = []
    symlinks: list[RetainedRow] = []
    for row, _ in retained_pairs:
        payload: bytes | None = None
        if (
            row.mode == "120000"
            or PurePosixPath(row.path).name == ".gitattributes"
            or sizes[row.oid] <= 4096
        ):
            payload = _read_blob(candidate, row.oid)
        validated = validate_retained_entry(
            row,
            payload,
            excluded_paths=tuple(exclusion_paths),
        )
        if validated.mode == "120000":
            retained_rows.append(validated)
            symlinks.append(validated)
        else:
            retained_rows.append(validated)

    return SourceInspection(
        source_commit=resolved_commit,
        source_tree=resolved_tree,
        source_leaf_count=len(decoded),
        excluded_rows=tuple(actual_exclusions),
        retained_rows=tuple(retained_rows),
        retained_leaf_count=len(retained_rows),
        retained_inventory_digest=retained_digest,
        retained_mode_counts=actual_counts,
        symlinks=tuple(symlinks),
    )


def projection_locator(
    manifest: ProjectionManifest,
    *,
    storage_root: Path | None = None,
) -> Path:
    """Return the canonical absolute content-addressed repository locator."""

    root = manifest.canonical_storage_root if storage_root is None else Path(storage_root)
    resolved = root.resolve(strict=False)
    if not root.is_absolute() or root != resolved:
        raise ProjectionError(
            "projection_locator_noncanonical",
            str(root),
            "projection storage root must be canonical and absolute",
        )
    relative = PurePosixPath(manifest.locator_relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ProjectionError(
            "projection_locator_noncanonical",
            manifest.locator_relative_path,
            "manifest projection locator is not canonical relative text",
        )
    locator = root.joinpath(*relative.parts)
    if not locator.is_absolute() or locator.resolve(strict=False) != locator:
        raise ProjectionError(
            "projection_locator_noncanonical",
            str(locator),
            "projection locator did not remain canonical and absolute",
        )
    return locator


@dataclass
class _TreeNode:
    directories: dict[str, "_TreeNode"]
    leaves: dict[str, RetainedRow]

    @classmethod
    def empty(cls) -> "_TreeNode":
        return cls(directories={}, leaves={})


def _retained_tree_trie(rows: tuple[RetainedRow, ...]) -> _TreeNode:
    root = _TreeNode.empty()
    for row in rows:
        parts = PurePosixPath(row.path).parts
        node = root
        for part in parts[:-1]:
            if part in node.leaves:
                raise ProjectionError(
                    "projection_source_inventory_invalid",
                    row.path,
                    "retained path collides with a retained leaf",
                )
            node = node.directories.setdefault(part, _TreeNode.empty())
        name = parts[-1]
        if name in node.leaves or name in node.directories:
            raise ProjectionError(
                "projection_source_inventory_invalid",
                row.path,
                "retained paths collide or repeat",
            )
        node.leaves[name] = row
    return root


def _copy_blob_objects(
    source: Path,
    target: Path,
    rows: tuple[RetainedRow, ...],
) -> None:
    oids = tuple(sorted({row.oid for row in rows}))
    if not oids:
        return
    with tempfile.TemporaryFile() as object_input:
        object_input.write(("\n".join(oids) + "\n").encode("ascii"))
        object_input.seek(0)
        try:
            pack = subprocess.Popen(
                (
                    "git",
                    "-C",
                    str(source),
                    "pack-objects",
                    "--stdout",
                    "--window=0",
                    "--depth=0",
                    "--no-reuse-delta",
                    "--no-reuse-object",
                ),
                stdin=object_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if pack.stdout is None:
                raise AssertionError("pack-objects stdout pipe was not created")
            indexed = subprocess.run(
                ("git", "-C", str(target), "index-pack", "--stdin"),
                check=False,
                stdin=pack.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            pack.stdout.close()
            pack_stderr = pack.stderr.read() if pack.stderr is not None else b""
            pack_returncode = pack.wait()
        except OSError as exc:
            raise ProjectionError(
                "projection_materialization_failed",
                str(target),
                "Git object transfer could not be launched",
            ) from exc
    if pack_returncode != 0 or indexed.returncode != 0:
        raise ProjectionError(
            "projection_materialization_failed",
            str(target),
            "retained Git blob transfer failed: "
            + (pack_stderr + indexed.stderr).decode("utf-8", errors="replace"),
        )


def _write_tree_objects(repository: Path, node: _TreeNode) -> str:
    rows: list[tuple[str, str, str, str]] = []
    for name, child in node.directories.items():
        rows.append(("040000", "tree", _write_tree_objects(repository, child), name))
    for name, leaf in node.leaves.items():
        rows.append((leaf.mode, "blob", leaf.oid, name))
    rows.sort(key=lambda row: row[3].encode("utf-8"))
    payload = b"".join(
        f"{mode} {object_type} {oid}\t{name}".encode("utf-8") + b"\0"
        for mode, object_type, oid, name in rows
    )
    tree = _run_git(repository, "mktree", "-z", input_bytes=payload).decode(
        "ascii", errors="strict"
    ).strip()
    if _SHA1_RE.fullmatch(tree) is None:
        raise ProjectionError(
            "projection_materialization_failed",
            tree,
            "Git mktree returned an invalid object identity",
        )
    return tree


def _all_object_rows(repository: Path) -> tuple[tuple[str, str], ...]:
    raw = _run_git(
        repository,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype)",
    )
    rows: list[tuple[str, str]] = []
    for line in raw.splitlines():
        try:
            oid_bytes, type_bytes = line.split(b" ", 1)
            oid = oid_bytes.decode("ascii", errors="strict")
            object_type = type_bytes.decode("ascii", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProjectionError(
                "projection_repository_invalid",
                line,
                "Git object inventory is malformed",
            ) from exc
        rows.append((oid, object_type))
    return tuple(sorted(rows))


def _reachable_object_ids(repository: Path) -> frozenset[str]:
    raw = _run_git(repository, "rev-list", "--objects", "--all")
    return frozenset(
        line.split(b" ", 1)[0].decode("ascii", errors="strict")
        for line in raw.splitlines()
        if line
    )


def _verify_repository_integrity(repository: Path) -> None:
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
        )
    except OSError:
        raise ProjectionError(
            "projection_repository_invalid",
            str(repository),
            "Git could not launch strict projection integrity validation",
        ) from None
    if completed.returncode != 0:
        diagnostics = (completed.stdout + completed.stderr).decode(
            "utf-8", errors="replace"
        )
        raise ProjectionError(
            "projection_repository_invalid",
            {"exit_code": completed.returncode, "diagnostics": diagnostics},
            "strict Git projection integrity validation failed",
        )


def verify_projection(
    locator: Path,
    manifest: ProjectionManifest,
) -> ProjectionResult:
    """Fail closed unless a projection contains exactly one parentless history."""

    repository = Path(locator)
    try:
        resolved = repository.resolve(strict=True)
    except OSError as exc:
        raise ProjectionError(
            "projection_repository_invalid",
            str(repository),
            "projection repository is missing",
        ) from exc
    if repository != resolved or not repository.is_absolute():
        raise ProjectionError(
            "projection_locator_noncanonical",
            str(repository),
            "projection repository locator must be canonical and absolute",
        )
    is_bare = _run_git(repository, "rev-parse", "--is-bare-repository").decode(
        "ascii", errors="strict"
    ).strip()
    if is_bare != "true":
        raise ProjectionError(
            "projection_repository_invalid",
            str(repository),
            "projection repository must be bare",
        )
    escape_paths = tuple(
        path.relative_to(repository).as_posix()
        for path in (
            repository / "objects" / "info" / "alternates",
            repository / "info" / "grafts",
            repository / "shallow",
        )
        if os.path.lexists(path)
    )
    if escape_paths:
        raise ProjectionError(
            "projection_repository_escape",
            escape_paths,
            "projection repository declares an external or substituted object source",
        )
    head_ref = _run_git(repository, "symbolic-ref", "HEAD").decode(
        "ascii", errors="strict"
    ).strip()
    if head_ref != "refs/heads/projection":
        raise ProjectionError(
            "projection_history_leakage",
            head_ref,
            "projection HEAD must select its sole canonical ref",
        )
    raw_refs = _run_git(
        repository,
        "for-each-ref",
        "--format=%(refname) %(objectname)",
    )
    refs = tuple(line.decode("ascii", errors="strict") for line in raw_refs.splitlines())
    expected_ref = f"refs/heads/projection {manifest.projection_commit}"
    if refs != (expected_ref,):
        raise ProjectionError(
            "projection_history_leakage",
            refs,
            "projection must expose exactly one ref at the bound root commit",
        )
    content = _run_git(repository, "cat-file", "commit", manifest.projection_commit)
    expected_content = render_commit_content(manifest)
    parent_count = sum(line.startswith(b"parent ") for line in content.splitlines())
    if content != expected_content or parent_count != 0:
        raise ProjectionError(
            "projection_history_leakage",
            manifest.projection_commit,
            "projection root commit bytes changed or contain a parent",
        )
    resolved_tree = _run_git(
        repository, "rev-parse", f"{manifest.projection_commit}^{{tree}}"
    ).decode("ascii", errors="strict").strip()
    if resolved_tree != manifest.retained_tree:
        raise ProjectionError(
            "projection_tree_mismatch",
            resolved_tree,
            "projection tree does not match the manifest",
        )
    inventory = _run_git(
        repository, "ls-tree", "-rz", "-r", manifest.projection_commit
    )
    inventory_digest = "sha256:" + hashlib.sha256(inventory).hexdigest()
    decoded = _decode_tree_rows(inventory)
    if (
        inventory_digest != manifest.retained_inventory_digest
        or len(decoded) != manifest.retained_leaf_count
    ):
        raise ProjectionError(
            "projection_retained_inventory_mismatch",
            inventory_digest,
            "projection leaf inventory does not match the manifest",
        )

    _verify_repository_integrity(repository)
    all_rows = _all_object_rows(repository)
    all_ids = frozenset(oid for oid, _ in all_rows)
    reachable = _reachable_object_ids(repository)
    extra = tuple(sorted(all_ids - reachable))
    missing = tuple(sorted(reachable - all_ids))
    if extra:
        raise ProjectionError(
            "projection_extra_object",
            extra,
            "projection contains unreachable objects",
        )
    if missing:
        raise ProjectionError(
            "projection_repository_invalid",
            missing,
            "projection reachability names missing objects",
        )
    commit_ids = tuple(oid for oid, object_type in all_rows if object_type == "commit")
    unsupported = tuple(
        (oid, object_type)
        for oid, object_type in all_rows
        if object_type not in {"blob", "tree", "commit"}
    )
    if commit_ids != (manifest.projection_commit,) or unsupported:
        raise ProjectionError(
            "projection_history_leakage",
            {"commits": commit_ids, "unsupported": unsupported},
            "projection object closure contains history or unsupported objects",
        )
    return ProjectionResult(
        locator=repository,
        commit=manifest.projection_commit,
        tree=resolved_tree,
        object_ids=tuple(sorted(all_ids)),
        parent_count=parent_count,
        unreachable_object_count=0,
        reused=True,
    )


def materialize_projection(
    manifest: ProjectionManifest,
    *,
    source_repository: Path,
    storage_root: Path | None = None,
) -> ProjectionResult:
    """Build or verify one isolated, content-addressed Git projection."""

    inspection = inspect_source(Path(source_repository), manifest)
    locator = projection_locator(manifest, storage_root=storage_root)
    if os.path.lexists(locator):
        verified = verify_projection(locator, manifest)
        return ProjectionResult(**{**verified.__dict__, "reused": True})
    locator.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{manifest.projection_commit}.",
            dir=locator.parent,
        )
    )
    try:
        _run_git(staging, "init", "--bare", "--quiet")
        _copy_blob_objects(
            Path(source_repository),
            staging,
            inspection.retained_rows,
        )
        tree = _write_tree_objects(
            staging,
            _retained_tree_trie(inspection.retained_rows),
        )
        if tree != manifest.retained_tree:
            raise ProjectionError(
                "projection_tree_mismatch",
                tree,
                "constructed tree does not match the manifest",
            )
        content = render_commit_content(manifest)
        commit = _run_git(
            staging,
            "hash-object",
            "-t",
            "commit",
            "-w",
            "--stdin",
            input_bytes=content,
        ).decode("ascii", errors="strict").strip()
        if commit != manifest.projection_commit:
            raise ProjectionError(
                "projection_recipe_digest_mismatch",
                commit,
                "Git did not reproduce the bound projection commit",
            )
        _run_git(staging, "update-ref", "refs/heads/projection", commit)
        _run_git(staging, "symbolic-ref", "HEAD", "refs/heads/projection")
        verify_projection(staging, manifest)
        try:
            os.replace(staging, locator)
        except OSError:
            if not os.path.lexists(locator):
                raise
            shutil.rmtree(staging)
            verified = verify_projection(locator, manifest)
            return ProjectionResult(**{**verified.__dict__, "reused": True})
    except Exception:
        if os.path.lexists(staging):
            shutil.rmtree(staging)
        raise
    verified = verify_projection(locator, manifest)
    return ProjectionResult(**{**verified.__dict__, "reused": False})


def outside_project_owned_origins(
    rows: tuple[tuple[str, str], ...],
    *,
    workspace: Path,
    prefixes: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """Return project-owned modules whose recorded origin escapes the workspace."""

    root = Path(workspace).resolve(strict=False)
    outside: list[tuple[str, str]] = []
    for name, origin in rows:
        owned = any(
            name == prefix or name.startswith(prefix + ".") for prefix in prefixes
        )
        if owned and not Path(origin).resolve(strict=False).is_relative_to(root):
            outside.append((name, origin))
    return tuple(sorted(outside))


_IMPORT_ORIGIN_BOOTSTRAP = r'''
import importlib
import json
import os
import pathlib
import sys

workspace = pathlib.Path(os.environ["ES_PROBE_WORKSPACE"]).resolve(strict=True)
report_path = pathlib.Path(os.environ["ES_PROBE_REPORT"]).resolve(strict=False)
selectors = tuple(json.loads(os.environ["ES_PROBE_SELECTORS"]))
collect_only = os.environ["ES_PROBE_COLLECT_ONLY"] == "1"
authored_forbidden = tuple(
    pathlib.Path(value).resolve(strict=False)
    for value in json.loads(os.environ["ES_PROBE_FORBIDDEN_ROOTS"])
)
forbidden_prefixes = tuple(json.loads(os.environ["ES_PROBE_FORBIDDEN_MODULES"]))
project_prefixes = tuple(json.loads(os.environ["ES_PROBE_PROJECT_MODULES"]))
editable_prefix = os.environ["ES_PROBE_EDITABLE_PREFIX"]
plugin_autoload_disabled = os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1"

hook_modules = set()
mapping_paths = []
for hook in (*sys.meta_path, *sys.path_hooks):
    module_name = getattr(hook, "__module__", "")
    if module_name.startswith(editable_prefix):
        hook_modules.add(module_name)
        module = sys.modules.get(module_name)
        if module is None:
            module = importlib.import_module(module_name)
        mapping = getattr(module, "MAPPING", {})
        namespaces = getattr(module, "NAMESPACES", {})
        for value in mapping.values():
            mapping_paths.append(str(value))
        for values in namespaces.values():
            mapping_paths.extend(str(value) for value in values)

editable_roots = []
if mapping_paths:
    editable_roots.append(pathlib.Path(os.path.commonpath(mapping_paths)).resolve(strict=False))
forbidden_roots = tuple(dict.fromkeys((*authored_forbidden, *editable_roots)))

sys.meta_path[:] = [
    hook for hook in sys.meta_path
    if not getattr(hook, "__module__", "").startswith(editable_prefix)
]
sys.path_hooks[:] = [
    hook for hook in sys.path_hooks
    if not getattr(hook, "__module__", "").startswith(editable_prefix)
]
sys.path[:] = [
    value for value in sys.path
    if not str(value).startswith("__editable__.ptychopinn-")
]
sys.path_importer_cache.clear()
for module_name in tuple(sys.modules):
    if module_name.startswith(editable_prefix):
        sys.modules.pop(module_name, None)

outcomes = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}

class OriginPlugin:
    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            if report.passed:
                outcomes["passed"] += 1
            elif report.failed:
                outcomes["failed"] += 1
            elif report.skipped:
                outcomes["skipped"] += 1
        elif report.failed:
            outcomes["errors"] += 1

    def pytest_sessionfinish(self, session, exitstatus):
        rows = set()
        for name, module in tuple(sys.modules.items()):
            origins = []
            spec = getattr(module, "__spec__", None)
            origin = getattr(spec, "origin", None)
            if isinstance(origin, str):
                origins.append(origin)
            module_file = getattr(module, "__file__", None)
            if isinstance(module_file, str):
                origins.append(module_file)
            locations = getattr(spec, "submodule_search_locations", None)
            if locations is not None:
                origins.extend(str(value) for value in locations)
            for value in origins:
                path = pathlib.Path(value)
                if path.is_absolute():
                    rows.add((name, str(path.resolve(strict=False))))
        ordered_rows = sorted(rows)
        projected = []
        forbidden_origins = []
        outside_project_origins = []
        for name, value in ordered_rows:
            path = pathlib.Path(value)
            if path.is_relative_to(workspace):
                projected.append([name, value])
            if any(path.is_relative_to(root) for root in forbidden_roots):
                forbidden_origins.append([name, value])
            if (
                any(name == prefix or name.startswith(prefix + ".") for prefix in project_prefixes)
                and not path.is_relative_to(workspace)
            ):
                outside_project_origins.append([name, value])
        forbidden_modules = sorted(
            name for name in sys.modules
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
        )
        payload = {
            "schema_version": "es_import_origin_probe.v1",
            "python_executable": str(pathlib.Path(sys.executable).resolve(strict=True)),
            "workspace": str(workspace),
            "selectors": list(selectors),
            "collect_only": collect_only,
            "exit_code": int(exitstatus),
            "collected": int(session.testscollected),
            "outcomes": outcomes,
            "removed_hooks": sorted(hook_modules),
            "forbidden_roots": [str(path) for path in forbidden_roots],
            "forbidden_module_prefixes": list(forbidden_prefixes),
            "project_owned_module_prefixes": list(project_prefixes),
            "plugin_autoload_disabled": plugin_autoload_disabled,
            "loaded_forbidden_modules": forbidden_modules,
            "forbidden_origin_rows": forbidden_origins,
            "outside_project_origin_rows": outside_project_origins,
            "projected_origin_rows": projected,
            "module_origin_rows": [list(row) for row in ordered_rows],
        }
        report_path.write_bytes(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            + b"\n"
        )

import pytest
arguments = ["-q", "-p", "no:cacheprovider"]
if collect_only:
    arguments.append("--collect-only")
arguments.extend(selectors)
raise SystemExit(pytest.main(arguments, plugins=[OriginPlugin()]))
'''


def _canonical_absolute(path: Path, *, label: str, must_exist: bool) -> Path:
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise ProjectionError(
            "projection_probe_path_invalid",
            str(candidate),
            f"{label} cannot be resolved",
        ) from exc
    if not candidate.is_absolute() or candidate != resolved:
        raise ProjectionError(
            "projection_probe_path_invalid",
            str(candidate),
            f"{label} must be canonical and absolute",
        )
    return candidate


def _pair_rows(value: object, *, label: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ProjectionError(
            "projection_probe_report_invalid", value, f"{label} must be a list"
        )
    rows: list[tuple[str, str]] = []
    for raw in value:
        if (
            not isinstance(raw, list)
            or len(raw) != 2
            or not all(isinstance(item, str) for item in raw)
        ):
            raise ProjectionError(
                "projection_probe_report_invalid", raw, f"{label} row is malformed"
            )
        rows.append((raw[0], raw[1]))
    return tuple(rows)


def run_import_origin_probe(
    *,
    python: Path,
    workspace: Path,
    selectors: tuple[str, ...],
    report_path: Path,
    collect_only: bool,
    forbidden_roots: tuple[Path, ...] = (),
) -> ImportOriginProbeResult:
    """Run the explicit ES v1 pytest bootstrap and audit every module origin."""

    interpreter_locator = Path(python)
    if not interpreter_locator.is_absolute():
        raise ProjectionError(
            "projection_probe_path_invalid",
            str(interpreter_locator),
            "Python interpreter locator must be absolute",
        )
    try:
        interpreter = interpreter_locator.resolve(strict=True)
    except OSError as exc:
        raise ProjectionError(
            "projection_probe_path_invalid",
            str(interpreter_locator),
            "Python interpreter cannot be resolved",
        ) from exc
    root = _canonical_absolute(Path(workspace), label="projected workspace", must_exist=True)
    report = _canonical_absolute(Path(report_path), label="probe report", must_exist=False)
    if not interpreter.is_file() or not root.is_dir() or report.is_relative_to(root):
        raise ProjectionError(
            "projection_probe_path_invalid",
            {"python": str(interpreter), "workspace": str(root), "report": str(report)},
            "probe paths have invalid kinds or report aliases the projected workspace",
        )
    if os.path.lexists(report):
        raise ProjectionError(
            "projection_probe_report_preexisting",
            str(report),
            "probe report must not preexist",
        )
    if not selectors or any(
        not isinstance(value, str)
        or not value
        or PurePosixPath(value).is_absolute()
        or ".." in PurePosixPath(value).parts
        for value in selectors
    ):
        raise ProjectionError(
            "projection_probe_selector_invalid",
            selectors,
            "probe selectors must be nonempty canonical relative paths",
        )
    bound_forbidden = tuple(
        _canonical_absolute(Path(path), label="forbidden root", must_exist=False)
        for path in forbidden_roots
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "XDG_CACHE_HOME": str(report.parent / "xdg-cache"),
            "MPLCONFIGDIR": str(report.parent / "mpl-cache"),
            "ES_PROBE_WORKSPACE": str(root),
            "ES_PROBE_REPORT": str(report),
            "ES_PROBE_SELECTORS": json.dumps(list(selectors), separators=(",", ":")),
            "ES_PROBE_COLLECT_ONLY": "1" if collect_only else "0",
            "ES_PROBE_FORBIDDEN_ROOTS": json.dumps(
                [str(path) for path in bound_forbidden], separators=(",", ":")
            ),
            "ES_PROBE_FORBIDDEN_MODULES": json.dumps(
                list(_FORBIDDEN_F1_MODULE_PREFIXES), separators=(",", ":")
            ),
            "ES_PROBE_PROJECT_MODULES": json.dumps(
                list(
                    dict.fromkeys(
                        (
                            "ptycho",
                            "ptycho_torch",
                            "conftest",
                            *(
                                PurePosixPath(selector).stem
                                for selector in selectors
                            ),
                            *(
                                ".".join(PurePosixPath(selector).with_suffix("").parts)
                                for selector in selectors
                            ),
                        )
                    )
                ),
                separators=(",", ":"),
            ),
            "ES_PROBE_EDITABLE_PREFIX": _PTYCHOPINN_EDITABLE_PREFIX,
        }
    )
    from scripts.experiments.es import boundary_proofs as boundary

    carrier = boundary._verify_pytest_carrier(
        boundary.PINNED_PYTEST_CARRIER,
        expected_sha256=boundary.PINNED_PYTEST_CARRIER_SHA256,
    )
    completed = boundary._run_private_tmp_child(
        carrier,
        (str(interpreter), "-c", _IMPORT_ORIGIN_BOOTSTRAP),
        cwd=root,
        env=env,
        preserved_paths=(root, report.parent),
    )
    try:
        raw = report.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectionError(
            "projection_probe_report_invalid",
            {"stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:]},
            "probe did not produce a readable report",
        ) from exc
    if raw != canonical_json_bytes(payload) or not isinstance(payload, dict):
        raise ProjectionError(
            "projection_probe_report_invalid",
            str(report),
            "probe report is not canonical JSON followed by one LF",
        )
    required = {
        "schema_version",
        "python_executable",
        "workspace",
        "selectors",
        "collect_only",
        "exit_code",
        "collected",
        "outcomes",
        "removed_hooks",
        "forbidden_roots",
        "forbidden_module_prefixes",
        "project_owned_module_prefixes",
        "plugin_autoload_disabled",
        "loaded_forbidden_modules",
        "forbidden_origin_rows",
        "outside_project_origin_rows",
        "projected_origin_rows",
        "module_origin_rows",
    }
    if set(payload) != required or payload["schema_version"] != "es_import_origin_probe.v1":
        raise ProjectionError(
            "projection_probe_report_invalid",
            payload,
            "probe report fields or schema changed",
        )
    exit_code = payload["exit_code"]
    collected = payload["collected"]
    outcomes = payload["outcomes"]
    if (
        isinstance(exit_code, bool)
        or not isinstance(exit_code, int)
        or isinstance(collected, bool)
        or not isinstance(collected, int)
        or not isinstance(outcomes, dict)
        or set(outcomes) != {"passed", "failed", "skipped", "errors"}
        or any(isinstance(value, bool) or not isinstance(value, int) for value in outcomes.values())
    ):
        raise ProjectionError(
            "projection_probe_report_invalid", payload, "probe counts are malformed"
        )
    if completed.returncode != exit_code:
        raise ProjectionError(
            "projection_probe_report_invalid",
            (completed.returncode, exit_code),
            "process and pytest exit codes disagree",
        )
    removed = payload["removed_hooks"]
    roots = payload["forbidden_roots"]
    loaded = payload["loaded_forbidden_modules"]
    project_prefixes = payload["project_owned_module_prefixes"]
    plugin_autoload_disabled = payload["plugin_autoload_disabled"]
    if (
        not isinstance(plugin_autoload_disabled, bool)
        or plugin_autoload_disabled is not True
        or not isinstance(project_prefixes, list)
        or not all(
            isinstance(value, str)
            for value in (*removed, *roots, *loaded, *project_prefixes)
        )
    ):
        raise ProjectionError(
            "projection_probe_report_invalid", payload, "probe string rows are malformed"
        )
    cache_artifacts = tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.name in {"__pycache__", ".pytest_cache"}
            or path.suffix in {".pyc", ".pyo"}
        )
    )
    result = ImportOriginProbeResult(
        report_path=report,
        report_digest="sha256:" + hashlib.sha256(raw).hexdigest(),
        exit_code=exit_code,
        collected=collected,
        outcomes=tuple((name, outcomes[name]) for name in ("passed", "failed", "skipped", "errors")),
        removed_hooks=tuple(removed),
        forbidden_roots=tuple(Path(value) for value in roots),
        loaded_forbidden_modules=tuple(loaded),
        forbidden_origin_rows=_pair_rows(
            payload["forbidden_origin_rows"], label="forbidden origin rows"
        ),
        projected_origin_rows=_pair_rows(
            payload["projected_origin_rows"], label="projected origin rows"
        ),
        module_origin_rows=_pair_rows(payload["module_origin_rows"], label="module origin rows"),
        cache_artifacts=cache_artifacts,
        plugin_autoload_disabled=plugin_autoload_disabled,
        outside_project_origin_rows=_pair_rows(
            payload["outside_project_origin_rows"],
            label="outside project origin rows",
        ),
    )
    if (
        result.loaded_forbidden_modules
        or result.forbidden_origin_rows
        or result.outside_project_origin_rows
        or result.cache_artifacts
    ):
        raise ProjectionError(
            "projection_import_closure_failed",
            {
                "modules": result.loaded_forbidden_modules,
                "origins": result.forbidden_origin_rows,
                "outside_project_origins": result.outside_project_origin_rows,
                "cache_artifacts": result.cache_artifacts,
            },
            "projected test process escaped its bound import/cache closure",
        )
    return result


def run_focused_baseline(
    *,
    python: Path,
    workspace: Path,
    report_path: Path,
    forbidden_roots: tuple[Path, ...],
) -> ImportOriginProbeResult:
    """Run the exact ten-module ES F1 baseline through the closed probe."""

    return run_import_origin_probe(
        python=python,
        workspace=workspace,
        selectors=FOCUSED_TEST_PATHS,
        report_path=report_path,
        collect_only=False,
        forbidden_roots=forbidden_roots,
    )


def _local_module_files(workspace: Path, module_name: str) -> tuple[Path, ...]:
    if not module_name or any(not part for part in module_name.split(".")):
        return ()
    relative = Path(*module_name.split("."))
    candidates = (workspace / relative.with_suffix(".py"), workspace / relative / "__init__.py")
    selected = [path for path in candidates if path.is_file()]
    parts = module_name.split(".")
    for length in range(1, len(parts)):
        parent_init = workspace.joinpath(*parts[:length], "__init__.py")
        if parent_init.is_file():
            selected.append(parent_init)
    return tuple(dict.fromkeys(selected))


def _file_package_parts(workspace: Path, path: Path) -> tuple[str, ...]:
    relative = path.relative_to(workspace)
    return relative.parts[:-1]


def _resolve_relative_import(
    workspace: Path,
    path: Path,
    *,
    level: int,
    module: str | None,
) -> str | None:
    package = list(_file_package_parts(workspace, path))
    climb = level - 1
    if climb > len(package):
        return None
    if climb:
        package = package[:-climb]
    if module:
        package.extend(module.split("."))
    return ".".join(package) if package else None


def _import_names(workspace: Path, path: Path) -> tuple[str, ...]:
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise ProjectionError(
            "projection_static_closure_invalid",
            str(path),
            "Python source cannot be parsed for static closure",
        ) from exc
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _resolve_relative_import(
                    workspace,
                    path,
                    level=node.level,
                    module=node.module,
                )
            else:
                base = node.module
            if base:
                names.add(base)
                for alias in node.names:
                    if alias.name != "*":
                        names.add(f"{base}.{alias.name}")
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            dynamic_import = (
                isinstance(function, ast.Name) and function.id == "__import__"
            ) or (
                isinstance(function, ast.Attribute) and function.attr == "import_module"
            )
            first = node.args[0]
            if dynamic_import and isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
    return tuple(sorted(names))


def compute_static_import_closure(
    *,
    workspace: Path,
    selectors: tuple[str, ...],
) -> StaticImportClosure:
    """Compute the exact local AST import closure for the F1 focused selectors."""

    root = _canonical_absolute(Path(workspace), label="static workspace", must_exist=True)
    if not root.is_dir() or not selectors:
        raise ProjectionError(
            "projection_static_closure_invalid",
            str(root),
            "static closure requires a directory and at least one selector",
        )
    pending: list[Path] = []
    for selector in selectors:
        pure = PurePosixPath(selector)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise ProjectionError(
                "projection_static_closure_invalid",
                selector,
                "static selector is not canonical relative text",
            )
        path = root.joinpath(*pure.parts)
        if not path.is_file():
            raise ProjectionError(
                "projection_static_closure_invalid",
                selector,
                "static selector is missing from the projection",
            )
        pending.append(path)

    visited: set[Path] = set()
    imported: set[str] = set()
    unresolved: set[str] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        for module_name in _import_names(root, path):
            imported.add(module_name)
            local = _local_module_files(root, module_name)
            if local:
                pending.extend(local)
            else:
                unresolved.add(module_name)

    forbidden = tuple(
        sorted(
            module_name
            for module_name in imported
            if any(
                module_name == prefix or module_name.startswith(prefix + ".")
                for prefix in _FORBIDDEN_F1_MODULE_PREFIXES
            )
        )
    )
    rows = tuple(
        sorted(
            (
                path.relative_to(root).as_posix(),
                "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in visited
        )
    )
    excluded: list[tuple[str, str]] = []
    for path_text, digest in rows:
        path = PurePosixPath(path_text)
        for excluded_text in _F1_EXCLUDED_PATHS:
            excluded_path = PurePosixPath(excluded_text)
            if path.parts[: len(excluded_path.parts)] == excluded_path.parts:
                excluded.append((path_text, digest))
                break
    payload = {
        "schema_version": "es_static_import_closure.v1",
        "selectors": list(selectors),
        "files": [
            {"path": path, "sha256": digest}
            for path, digest in rows
        ],
        "imported_modules": sorted(imported),
        "unresolved_imports": sorted(unresolved),
        "forbidden_imports": list(forbidden),
        "excluded_path_rows": [list(row) for row in excluded],
    }
    result = StaticImportClosure(
        file_rows=rows,
        imported_modules=tuple(sorted(imported)),
        unresolved_imports=tuple(sorted(unresolved)),
        forbidden_imports=forbidden,
        excluded_path_rows=tuple(excluded),
        digest="sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    )
    if result.forbidden_imports or result.excluded_path_rows:
        raise ProjectionError(
            "projection_static_closure_failed",
            {
                "forbidden_imports": result.forbidden_imports,
                "excluded_paths": result.excluded_path_rows,
            },
            "focused static closure reaches an excluded surface",
        )
    return result


__all__ = [
    "ExclusionRow",
    "FOCUSED_TEST_PATHS",
    "ImportOriginProbeResult",
    "ProjectionError",
    "ProjectionManifest",
    "ProjectionResult",
    "RetainedRow",
    "SourceInspection",
    "StaticImportClosure",
    "canonical_json_bytes",
    "compute_static_import_closure",
    "git_object_id",
    "inspect_source",
    "load_projection_manifest",
    "materialize_projection",
    "outside_project_owned_origins",
    "projection_locator",
    "render_commit_content",
    "run_import_origin_probe",
    "run_focused_baseline",
    "validate_retained_entry",
    "verify_projection",
]
