"""Verified-byte staging for the private lean-pilot evaluator apparatus."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from . import _runner_apparatus as apparatus
from ._evaluation_support import _relative_path
from ._pilot_evidence_support import PilotEvidenceError, _fail
from ._runner_types import RunnerError
from .evaluation import EvaluationError


def _evaluator_contract(
    *,
    lock: Mapping[str, object],
    verified: Mapping[str, bytes],
) -> tuple[PurePosixPath, tuple[PurePosixPath, ...], int]:
    review = lock.get("review")
    if not isinstance(review, Mapping):
        _fail("pilot_evidence_evaluator_invalid", "lock")
    bundle = review.get("evaluator")
    if not isinstance(bundle, Mapping):
        _fail("pilot_evidence_evaluator_invalid", "bundle")
    config_path = bundle.get("config_path")
    asset_paths = bundle.get("asset_paths")
    if not isinstance(config_path, str) or not isinstance(asset_paths, list):
        _fail("pilot_evidence_evaluator_invalid", "bundle")
    try:
        config = apparatus.strict_object(
            verified[config_path],
            label="pilot evaluator config",
        )
    except (KeyError, RunnerError) as exc:
        raise PilotEvidenceError(
            "pilot_evidence_evaluator_invalid",
            "config",
        ) from exc
    expected_contract = {
        "format": "canonical-json-object",
        "required_keys": [
            "failure_categories",
            "soft_quality",
            "summary",
            "verdict",
        ],
        "verdicts": ["PASS", "FAIL"],
    }
    if set(config) != {
        "schema_version",
        "module_path",
        "runtime_asset_paths",
        "timeout_milliseconds",
        "output_contract",
    } or config.get("schema_version") != "lean-pilot-hidden-evaluator.v1":
        _fail("pilot_evidence_evaluator_invalid", "config shape")
    module_value = config.get("module_path")
    runtime_values = config.get("runtime_asset_paths")
    timeout = config.get("timeout_milliseconds")
    if (
        not isinstance(module_value, str)
        or not isinstance(runtime_values, list)
        or not runtime_values
        or len(runtime_values) != len(set(runtime_values))
        or isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or timeout <= 0
        or config.get("output_contract") != expected_contract
    ):
        _fail("pilot_evidence_evaluator_invalid", "config values")
    try:
        module = _relative_path(module_value)
        runtime_paths = tuple(_relative_path(item) for item in runtime_values)
    except EvaluationError as exc:
        raise PilotEvidenceError(
            "pilot_evidence_evaluator_invalid",
            "runtime paths",
        ) from exc
    normalized = {item.as_posix() for item in runtime_paths}
    if (
        len(normalized) != len(runtime_paths)
        or normalized != set(asset_paths) - {config_path}
        or module.as_posix() not in normalized
        or any(path not in verified for path in normalized)
    ):
        _fail("pilot_evidence_evaluator_invalid", "asset closure")
    return (
        module,
        tuple(sorted(runtime_paths, key=lambda item: item.as_posix().encode())),
        timeout,
    )


def _write_verified_closure(
    *,
    root: Path,
    paths: tuple[PurePosixPath, ...],
    verified: Mapping[str, bytes],
) -> None:
    if (
        not root.is_absolute()
        or root.resolve(strict=False) != root
        or os.path.lexists(root)
    ):
        _fail("pilot_evidence_evaluator_invalid", "runtime root")
    try:
        root.mkdir()
        for relative in paths:
            target = root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            data = verified[relative.as_posix()]
            with target.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        for relative in paths:
            target = root.joinpath(*relative.parts)
            if target.read_bytes() != verified[relative.as_posix()]:
                _fail("pilot_evidence_evaluator_invalid", "staged bytes")
    except (KeyError, OSError) as exc:
        raise PilotEvidenceError(
            "pilot_evidence_evaluator_invalid",
            "staging",
        ) from exc


def _stage_evaluator_apparatus(
    *,
    lock: Mapping[str, object],
    verified: Mapping[str, bytes],
    root: Path,
) -> tuple[Path, int]:
    module, runtime_paths, timeout = _evaluator_contract(
        lock=lock,
        verified=verified,
    )
    _write_verified_closure(
        root=root,
        paths=runtime_paths,
        verified=verified,
    )
    return root.joinpath(*module.parts), timeout
