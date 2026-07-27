"""Validation and frozen-source support for private pilot preparation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from . import workspace
from ._evaluation_calibration_support import (
    EvaluationError,
    _validate_reviewer_execution,
)
from .contracts import canonical_json_bytes, canonical_sha256


class PilotPreparationError(ValueError):
    """The prospective pilot apparatus cannot be prepared safely."""


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_OBJECT = re.compile(r"^[0-9a-f]{40,64}$")


def _fail(message: str) -> None:
    raise PilotPreparationError(message)


def _obj(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object")
    return value


def _closed(value: object, keys: set[str], label: str) -> Mapping[str, object]:
    result = _obj(value, label)
    if set(result) != keys:
        _fail(f"{label} has missing or extra fields")
    return result


def _items(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        _fail(f"{label} must be a list")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be nonempty text")
    return value


def _relative(value: object, label: str) -> str:
    text = _text(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or path.as_posix() != text or any(
        part in {".", ".."} for part in path.parts
    ) or "\\" in text or "\x00" in text:
        _fail(f"{label} must be canonical relative POSIX text")
    return text


def _component(value: object, label: str) -> str:
    text = _text(value, label)
    if text in {".", ".."} or "/" in text or "\\" in text or "\x00" in text:
        _fail(f"{label} must be a safe component")
    return text


def _texts(
    value: object, label: str, *, paths: bool = False, components: bool = False
) -> list[str]:
    parser = _relative if paths else _component if components else _text
    result = [parser(item, label) for item in _items(value, label)]
    if len(result) != len(set(result)):
        _fail(f"{label} contains duplicate values")
    return result


def _sha(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _digest(value: object, label: str) -> str:
    result = _text(value, label)
    if _DIGEST.fullmatch(result) is None:
        _fail(f"{label} is not a SHA-256 digest")
    return result


def _regular(path: Path, label: str) -> bytes:
    if not path.is_absolute():
        _fail(f"{label} must be absolute")
    try:
        identity, resolved = path.lstat(), path.resolve(strict=True)
        if resolved != path or not stat.S_ISREG(identity.st_mode):
            _fail(f"{label} must be a canonical regular file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise PilotPreparationError(f"{label} is unreadable") from exc
    return data


def _json(
    data: bytes,
    label: str,
    *,
    canonical: bool = False,
) -> dict[str, object]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotPreparationError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must be one JSON object")
    if canonical and canonical_json_bytes(value) != data:
        _fail(f"{label} must be canonical JSON")
    return value


def _directory(path: Path, label: str) -> Path:
    if not path.is_absolute():
        _fail(f"{label} must be absolute")
    try:
        identity, resolved = path.lstat(), path.resolve(strict=True)
    except OSError as exc:
        raise PilotPreparationError(f"{label} is unreadable") from exc
    if resolved != path or not stat.S_ISDIR(identity.st_mode):
        _fail(f"{label} must be a canonical directory")
    return path


def _fresh(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.resolve(strict=False) != path:
        _fail(f"{label} must be canonical absolute")
    _directory(path.parent, f"{label} parent")
    if os.path.lexists(path):
        _fail(f"{label} must not exist")
    return path


def _git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PilotPreparationError("cannot read frozen Git apparatus") from exc


def _commit(repo: Path, revision: str, label: str) -> str:
    if _OBJECT.fullmatch(revision) is None:
        _fail(f"{label} must be a full commit ID")
    resolved = str(
        _git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}")
    ).strip()
    if resolved != revision:
        _fail(f"{label} did not resolve exactly")
    return revision


def _blob(repo: Path, revision: str, source: str) -> bytes:
    if str(_git(repo, "cat-file", "-t", f"{revision}:{source}")).strip() != "blob":
        _fail(f"repository source is not a blob: {source}")
    result = _git(repo, "show", f"{revision}:{source}", text=False)
    assert isinstance(result, bytes)
    return result


def _classified(value: Mapping[str, object]) -> set[str]:
    apparatus = _obj(value["apparatus"], "apparatus")
    review = _obj(value["review"], "review")
    result = set(apparatus["treatment_asset_paths"])
    result |= {str(review["rubric_path"]), str(review["calibration_evidence_path"])}
    for name in ("evaluator", "reviewer_command"):
        result |= set(_obj(review[name], name)["asset_paths"])
    return result


def _sources(
    value: dict[str, object], repo: Path, revision: str, seal_path: Path
) -> tuple[list[dict[str, str]], dict[str, bytes]]:
    parsed: list[tuple[Mapping[str, object], str, str | None]] = []
    destinations, repository_sources, external = set(), set(), 0
    for raw in _items(value["sources"], "sources"):
        row = _obj(raw, "source row")
        kind = row.get("source_kind")
        keys = {"source_kind", "destination_path", "sha256"}
        if kind == "repository":
            keys.add("source_path")
        elif kind == "external_calibration_seal":
            external += 1
        else:
            _fail("source row has unsupported source kind")
        _closed(row, keys, "source row")
        destination = _relative(row["destination_path"], "source destination")
        source = (
            _relative(row["source_path"], "repository source")
            if kind == "repository"
            else None
        )
        if destination in destinations or source is not None and source in repository_sources:
            _fail("duplicate source or destination")
        destinations.add(destination)
        if source is not None:
            repository_sources.add(source)
        parsed.append((row, destination, source))
    review = _obj(value["review"], "review")
    if destinations != _classified(value):
        _fail("source destinations do not equal classified apparatus assets")
    if external != 1 or not any(
        row["source_kind"] == "external_calibration_seal"
        and destination == review["calibration_evidence_path"]
        for row, destination, _ in parsed
    ):
        _fail("exactly one explicit calibration seal is required")
    content, manifest = {}, []
    for row, destination, source in parsed:
        data = (
            _blob(repo, revision, source)
            if source
            else _regular(seal_path, "calibration seal")
        )
        expected = _digest(row["sha256"], "source digest")
        if _sha(data) != expected:
            _fail(f"source digest mismatch: {destination}")
        content[destination] = data
        manifest.append({"path": destination, "sha256": expected})
    manifest.sort(key=lambda row: row["path"].encode())
    return manifest, content


def _archive(value: Mapping[str, object], repo: Path, task_bytes: bytes) -> None:
    archive = _obj(value["archive"], "archive")
    commit = _commit(repo, str(archive["revision_identity"])[7:], "archive revision")
    try:
        treeish = workspace._verified_git_subtree(
            repo,
            commit,
            PurePosixPath(str(archive["source_subtree_path"])),
            str(archive["source_tree_identity"]),
        )
        with TemporaryDirectory(prefix="lean-pilot-archive-") as temporary:
            root = Path(temporary) / "root"
            frozen = workspace.materialize_git_archive(repo, treeish, root)
            if frozen.digest != archive["archive_digest"]:
                _fail("frozen archive digest mismatch")
            task = (root / str(archive["task_source_path"])).resolve(strict=False)
            if _regular(task, "archived task") != task_bytes:
                _fail("archived task bytes mismatch")
    except workspace.WorkspaceError as exc:
        raise PilotPreparationError(f"frozen Git tree/archive invalid: {exc}") from exc


def _bundle(paths: Sequence[str], manifest: Mapping[str, dict[str, str]]) -> str:
    return canonical_sha256([manifest[path] for path in sorted(paths, key=str.encode)])


def _calibration(value: Mapping[str, object], content: Mapping[str, bytes]) -> None:
    review = _obj(value["review"], "review")
    reviewer = _obj(review["reviewer_command"], "reviewer command bundle")
    config = _closed(
        _json(content[str(reviewer["config_path"])], "reviewer command"),
        {
            "schema_version",
            "reviewer_execution",
            "calibration_lock_path",
            "live_output_schema_path",
            "live_output_schema_digest",
        },
        "reviewer command",
    )
    calibration_path = _relative(config["calibration_lock_path"], "calibration lock path")
    schema_path = _relative(config["live_output_schema_path"], "live schema path")
    if (
        calibration_path not in reviewer["asset_paths"]
        or schema_path not in reviewer["asset_paths"]
    ):
        _fail("reviewer command references an unbound asset")
    if _sha(content[schema_path]) != config["live_output_schema_digest"]:
        _fail("reviewer live schema digest mismatch")
    lock = _json(content[calibration_path], "calibration lock")
    if config["reviewer_execution"] != lock.get("reviewer_execution"):
        _fail("calibrated reviewer execution mismatch")
    try:
        _validate_reviewer_execution(config["reviewer_execution"], code="pilot_prepare")
    except EvaluationError as exc:
        raise PilotPreparationError(f"calibrated reviewer execution invalid: {exc}") from exc
    seal = _json(
        content[str(review["calibration_evidence_path"])],
        "calibration seal",
        canonical=True,
    )
    rubric = _obj(lock.get("rubric"), "calibration rubric")
    validation = _obj(seal.get("validation"), "calibration validation")
    if (
        seal.get("status") != "PASSED"
        or validation.get("result") != "PASSED"
        or seal.get("calibration_lock_digest") != canonical_sha256(lock)
        or any(
            seal.get(key) != lock.get(key)
            for key in ("calibration_id", "round", "revision")
        )
        or seal.get("rubric_digest") != rubric.get("digest")
        or lock.get("reviewer_ids") != review["reviewer_ids"]
    ):
        _fail("calibration seal and calibration lock do not match")
    packages, reviewers = lock.get("package_ids"), list(review["reviewer_ids"])
    if not isinstance(packages, list) or len(packages) != 3:
        _fail("calibration package set is invalid")
    expected = {
        (reviewer_id, package_id): outcome
        for reviewer_id in reviewers
        for package_id, outcome in zip(packages, ("A", "B", "TIE"), strict=True)
    }
    observed, sessions = {}, set()
    for raw in _items(seal.get("review_bindings"), "calibration reviews"):
        row = _obj(raw, "calibration review")
        key = (
            _text(row.get("reviewer_id"), "reviewer ID"),
            _text(row.get("package_id"), "package ID"),
        )
        session = _text(row.get("session_id"), "session ID")
        if key in observed or session in sessions:
            _fail("calibration review/session duplication")
        observed[key] = _text(row.get("outcome"), "calibration outcome")
        sessions.add(session)
    if observed != expected or len(sessions) != 6:
        _fail("calibration did not pass the exact six-review matrix")


def _configs(value: Mapping[str, object], content: Mapping[str, bytes]) -> None:
    apparatus = _obj(value["apparatus"], "apparatus")
    environment = _obj(apparatus["environment"], "environment")
    policy_digest = canonical_sha256(value["provider_policy"])
    for raw in value["treatments"]:
        row = _obj(raw, "treatment")
        path = str(row["command_config_path"])
        config = _json(content[path], f"treatment config {path}")
        launcher_environment = config.get("environment")
        if (
            config.get("provider_policy_digest") != policy_digest
            or config.get("environment_identity") != environment["identity"]
            or not isinstance(launcher_environment, Mapping)
            or set(launcher_environment) != {"PATH", "PYTHONUNBUFFERED"}
            or not isinstance(launcher_environment.get("PATH"), str)
            or launcher_environment.get("PYTHONUNBUFFERED") != "1"
        ):
            _fail(f"treatment config has uncontrolled defaults: {path}")
    runtime = _json(content["runtime-control.json"], "runtime control")
    check = _obj(runtime.get("visible_check"), "runtime visible check")
    locked_check = _obj(apparatus["visible_check"], "visible check")
    if (
        check.get("argv") != locked_check["argv"]
        or not isinstance(check.get("timeout_seconds"), int)
        or check["timeout_seconds"] * 1000 != locked_check["timeout_milliseconds"]
        or runtime.get("product_exclusions")
        != apparatus["product_projection_exclusions"]
    ):
        _fail("runtime-control differs from locked apparatus")
    review = _obj(value["review"], "review")
    evaluator = _obj(review["evaluator"], "evaluator")
    config = _closed(
        _json(content[str(evaluator["config_path"])], "evaluator config"),
        {
            "schema_version",
            "module_path",
            "runtime_asset_paths",
            "timeout_milliseconds",
            "output_contract",
        },
        "evaluator config",
    )
    runtime_paths = _texts(
        config["runtime_asset_paths"],
        "evaluator runtime assets",
        paths=True,
    )
    if (
        config["schema_version"] != "lean-pilot-hidden-evaluator.v1"
        or config["module_path"] not in runtime_paths
        or {str(evaluator["config_path"]), *runtime_paths} != set(evaluator["asset_paths"])
        or not isinstance(config["timeout_milliseconds"], int)
        or config["timeout_milliseconds"] <= 0
    ):
        _fail("evaluator config does not match its bundle")
