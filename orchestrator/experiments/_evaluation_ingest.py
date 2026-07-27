"""Sealed blinded-review ingestion internals."""

from __future__ import annotations

import os
import stat
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path, PurePosixPath

from .contracts import PilotContractError, canonical_json_bytes, load_record
from ._evaluation_support import (
    EvaluationError,
    _canonical_root,
    _fail,
    _relative_path,
    _safe_component,
    _sha256_bytes,
    _source_file,
    _strict_json,
)


def _expected_labels(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, (tuple, list))
        or len(value) < 2
        or len(set(value)) != len(value)
        or any(not isinstance(item, str) or not item for item in value)
    ):
        _fail("review_binding_mismatch", "candidate labels")
    return tuple(value)


def _citation_paths(record: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for collection_name in ("candidates", "pairwise_results"):
        collection = record.get(collection_name)
        if not isinstance(collection, list):
            _fail("review_record_invalid", collection_name)
        for item in collection:
            if not isinstance(item, Mapping):
                _fail("review_record_invalid", collection_name)
            citations = item.get("evidence_citations")
            if not isinstance(citations, list):
                _fail("review_record_invalid", "evidence_citations")
            values.extend(citations)
            if collection_name == "candidates":
                assessments = item.get("dimension_assessments")
                if not isinstance(assessments, list):
                    _fail("review_record_invalid", "dimension_assessments")
                for assessment in assessments:
                    if not isinstance(assessment, Mapping):
                        _fail(
                            "review_record_invalid",
                            "dimension_assessments",
                        )
                    nested_citations = assessment.get("evidence_citations")
                    if not isinstance(nested_citations, list):
                        _fail(
                            "review_record_invalid",
                            "dimension_assessments.evidence_citations",
                        )
                    values.extend(nested_citations)
    return tuple(values)


def _verify_closed_package_tree(
    package: Path,
    *,
    permitted_files: Collection[str],
) -> None:
    allowed_files = set(permitted_files) | {"manifest.json"}
    allowed_directories: set[str] = set()
    for path_text in allowed_files:
        for parent in PurePosixPath(path_text).parents:
            if parent.parts:
                allowed_directories.add(parent.as_posix())
    observed_files: set[str] = set()

    def walk(directory: Path, relative_directory: PurePosixPath) -> None:
        try:
            with os.scandir(directory) as scan:
                children = list(scan)
        except OSError as exc:
            raise EvaluationError("review_package_invalid", str(directory)) from exc
        for child in children:
            relative = relative_directory / child.name
            path_text = relative.as_posix()
            try:
                identity = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise EvaluationError(
                    "review_package_invalid",
                    path_text,
                ) from exc
            if stat.S_ISDIR(identity.st_mode):
                if path_text not in allowed_directories:
                    _fail("review_package_invalid", f"undeclared node {path_text}")
                walk(Path(child.path), relative)
            elif stat.S_ISREG(identity.st_mode):
                if path_text not in allowed_files:
                    _fail("review_package_invalid", f"undeclared node {path_text}")
                observed_files.add(path_text)
            else:
                _fail("review_package_invalid", f"non-regular node {path_text}")

    walk(package, PurePosixPath())
    if observed_files != allowed_files:
        _fail("review_package_invalid", "payload set")


def ingest_review(
    path: Path,
    *,
    package_root: Path,
    expected_bindings: Mapping[str, object],
    used_session_ids: Collection[str],
    prior_records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Load one sealed review and fail closed on binding or citation drift."""

    try:
        record = load_record(path, expected_kind="review_result.v1")
    except (OSError, PilotContractError) as exc:
        raise EvaluationError("review_record_invalid", str(exc)) from exc
    package = _canonical_root(package_root, must_exist=True)
    manifest_path = package / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise EvaluationError("review_package_invalid", "manifest") from exc
    manifest = _strict_json(
        manifest_path,
        code="review_package_invalid",
    )
    if (
        canonical_json_bytes(manifest) != manifest_bytes
        or set(manifest)
        != {"package_id", "task_path", "candidate_labels", "files"}
        or manifest.get("package_id") != expected_bindings.get("package_id")
        or _sha256_bytes(manifest_bytes)
        != expected_bindings.get("package_manifest_digest")
    ):
        _fail("review_package_invalid", "manifest binding")
    _safe_component(manifest.get("package_id"))
    rows = manifest.get("files")
    if not isinstance(rows, list):
        _fail("review_package_invalid", "files")
    permitted_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "path",
            "mode",
            "size",
            "sha256",
        }:
            _fail("review_package_invalid", "manifest row")
        relative = _relative_path(row.get("path"))
        path_text = relative.as_posix()
        if path_text in permitted_paths or path_text == "manifest.json":
            _fail("review_package_invalid", "duplicate path")
        permitted_paths.add(path_text)
        source, data, mode = _source_file(package, relative)
        if (
            row.get("size") != len(data)
            or row.get("mode") != mode
            or row.get("sha256") != _sha256_bytes(data)
            or source != package.joinpath(*relative.parts)
        ):
            _fail("review_package_invalid", path_text)
    _verify_closed_package_tree(
        package,
        permitted_files=permitted_paths,
    )

    expected_labels = _expected_labels(expected_bindings.get("candidate_labels"))
    actual_labels = tuple(
        item["opaque_label"] for item in record["candidates"]
    )
    if actual_labels != expected_labels:
        _fail("review_binding_mismatch", "candidate labels")
    for key in ("pilot_lock_digest", "rubric_digest", "review_class"):
        if record.get(key) != expected_bindings.get(key):
            _fail("review_binding_mismatch", key)

    session_id = record["session_id"]
    reviewer_id = record["reviewer_id"]
    if session_id in used_session_ids:
        _fail("review_session_reused", session_id)
    for prior in prior_records:
        if prior.get("session_id") == session_id:
            _fail("review_session_reused", session_id)
        if prior.get("reviewer_id") == reviewer_id:
            _fail("review_reviewer_reused", reviewer_id)

    label_set = set(expected_labels)
    for result in record["pairwise_results"]:
        if (
            result["candidate_a_label"] not in label_set
            or result["candidate_b_label"] not in label_set
            or result["candidate_a_label"] == result["candidate_b_label"]
        ):
            _fail("review_binding_mismatch", "pairwise labels")

    for citation in _citation_paths(record):
        try:
            relative = _relative_path(citation)
        except EvaluationError as exc:
            raise EvaluationError("review_citation_escape", citation) from exc
        if citation not in permitted_paths:
            _fail("review_citation_not_in_package", citation)
    return record
