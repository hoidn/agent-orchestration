"""Content-bound controller staging for calibrated live-review assets."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from ._evaluation_support import (
    EvaluationError,
    _fail,
    _publish_new_payload,
    _source_file,
)


_SCHEMA_RELATIVE = PurePosixPath(
    "controller-runtime/live-review/live-output.schema.json"
)
_RUBRIC_RELATIVE = PurePosixPath("controller-runtime/live-review/rubric.md")


def _stage_asset(
    *,
    evidence_root: Path,
    relative: PurePosixPath,
    expected: bytes,
) -> Path:
    try:
        path, observed, mode = _source_file(evidence_root, relative)
    except EvaluationError as exc:
        if exc.code != "evaluation_source_missing":
            raise EvaluationError(
                "live_reviewer_staged_asset_invalid",
                relative.as_posix(),
            ) from exc
        try:
            _publish_new_payload(
                root=evidence_root,
                relative=relative,
                data=expected,
            )
        except EvaluationError as publish_exc:
            if publish_exc.code != "evaluation_output_exists":
                raise EvaluationError(
                    "live_reviewer_staged_asset_invalid",
                    relative.as_posix(),
                ) from publish_exc
        try:
            path, observed, mode = _source_file(evidence_root, relative)
        except EvaluationError as read_exc:
            raise EvaluationError(
                "live_reviewer_staged_asset_invalid",
                relative.as_posix(),
            ) from read_exc
    if observed != expected or mode != 0o644:
        _fail("live_reviewer_staged_asset_invalid", relative.as_posix())
    return path


def stage_live_reviewer_assets(
    *,
    apparatus: Mapping[str, object],
    evidence_root: Path,
) -> dict[str, object]:
    """Stage or revalidate the exact bytes already verified by preflight."""

    schema_bytes = apparatus.get("schema_bytes")
    rubric_bytes = apparatus.get("rubric_bytes")
    if not isinstance(schema_bytes, bytes) or not isinstance(rubric_bytes, bytes):
        _fail("live_reviewer_staged_asset_invalid", "verified bytes")
    staged = dict(apparatus)
    staged["schema_path"] = _stage_asset(
        evidence_root=evidence_root,
        relative=_SCHEMA_RELATIVE,
        expected=schema_bytes,
    )
    staged["rubric_path"] = _stage_asset(
        evidence_root=evidence_root,
        relative=_RUBRIC_RELATIVE,
        expected=rubric_bytes,
    )
    return staged
