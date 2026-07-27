"""One-shot calibrated provider execution for live lean-pilot review."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import tempfile
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

from jsonschema import Draft202012Validator

from orchestrator.providers import CodexExecJsonlAccumulator

from ._evaluation_ingest import ingest_review
from ._evaluation_support import (
    EvaluationError,
    _canonical_root,
    _fail,
    _relative_path,
    _safe_component,
    _sha256_bytes,
    _source_file,
)
from ._pilot_review_assets import stage_live_reviewer_assets
from ._pilot_review_support import (
    _command,
    _package_contract,
    _prompt,
    _publish,
    validate_live_reviewer_apparatus,
)
from .contracts import canonical_json_bytes, canonical_sha256


def _run_process(
    *,
    command: list[str],
    package_root: Path,
    environment: Mapping[str, str],
    prompt: Mapping[str, object],
    timeout_milliseconds: int,
    evidence: Path,
    prefix: str,
) -> tuple[bytes, bytes, subprocess.Popen[bytes]]:
    process = subprocess.Popen(
        command,
        cwd=package_root,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(
            canonical_json_bytes(prompt),
            timeout=timeout_milliseconds / 1000,
        )
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        _publish(
            evidence,
            f"{prefix}/stdout.jsonl",
            stdout,
            code="live_reviewer_transport_invalid",
        )
        _publish(
            evidence,
            f"{prefix}/stderr.txt",
            stderr,
            code="live_reviewer_transport_invalid",
        )
        _fail("live_reviewer_transport_invalid", "timeout")
    _publish(
        evidence,
        f"{prefix}/stdout.jsonl",
        stdout,
        code="live_reviewer_transport_invalid",
    )
    _publish(
        evidence,
        f"{prefix}/stderr.txt",
        stderr,
        code="live_reviewer_transport_invalid",
    )
    return stdout, stderr, process


def _provider_payload(
    *,
    apparatus: Mapping[str, object],
    stdout: bytes,
    exit_status: int,
    last_message_path: Path,
) -> tuple[str, int, dict[str, object]]:
    accumulator = CodexExecJsonlAccumulator()
    accumulator.feed(stdout)
    metadata, transport_error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=True,
    )
    if exit_status != 0 or transport_error is not None or metadata is None:
        _fail("live_reviewer_transport_invalid", repr(transport_error))
    try:
        identity = last_message_path.lstat()
        resolved = last_message_path.resolve(strict=True)
        payload = json.loads(last_message_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("live_reviewer_output_invalid", str(exc)) from exc
    if (
        last_message_path.is_symlink()
        or resolved != last_message_path
        or not stat.S_ISREG(identity.st_mode)
        or not isinstance(payload, dict)
    ):
        _fail("live_reviewer_output_invalid", "last message")
    errors = sorted(
        Draft202012Validator(apparatus["schema"]).iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.path),
    )
    if errors:
        _fail("live_reviewer_output_invalid", errors[0].message)
    return str(metadata["session_id"]), int(metadata["event_count"]), payload


def _canonical_object(
    *,
    evidence: Path,
    relative: str,
    code: str,
) -> tuple[dict[str, object], bytes]:
    try:
        _path, raw, _mode = _source_file(evidence, _relative_path(relative))
        value = json.loads(raw)
    except (
        EvaluationError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise EvaluationError(code, relative) from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(code, relative)
    return value, raw


def _file_binding(
    *,
    evidence: Path,
    relative: str,
    code: str,
) -> tuple[dict[str, object], bytes]:
    try:
        _path, raw, _mode = _source_file(evidence, _relative_path(relative))
    except EvaluationError as exc:
        raise EvaluationError(code, relative) from exc
    return {
        "path": relative,
        "size": len(raw),
        "sha256": _sha256_bytes(raw),
    }, raw


def _completion_record(
    *,
    evidence: Path,
    prefix: str,
    intent: Mapping[str, object],
    exit_status: int,
    session_id: str,
    event_count: int,
) -> dict[str, object]:
    artifacts = {}
    for key, filename in (
        ("stdout", "stdout.jsonl"),
        ("stderr", "stderr.txt"),
        ("last_message", "last-message.json"),
    ):
        binding, _raw = _file_binding(
            evidence=evidence,
            relative=f"{prefix}/{filename}",
            code="live_reviewer_transport_invalid",
        )
        artifacts[key] = binding
    return {
        "schema_version": "lean-pilot-live-review-transport-completion.v1",
        "launch_intent_digest": canonical_sha256(intent),
        "exit_status": exit_status,
        "session_id": session_id,
        "event_count": event_count,
        "artifacts": artifacts,
    }


def _retained_transport(
    *,
    apparatus: Mapping[str, object],
    evidence: Path,
    prefix: str,
    intent: Mapping[str, object],
    last_message_path: Path,
) -> tuple[str, dict[str, object]]:
    completion, _raw = _canonical_object(
        evidence=evidence,
        relative=f"{prefix}/transport-completion.json",
        code="live_reviewer_transport_invalid",
    )
    expected_keys = {
        "schema_version",
        "launch_intent_digest",
        "exit_status",
        "session_id",
        "event_count",
        "artifacts",
    }
    artifacts = completion.get("artifacts")
    if (
        set(completion) != expected_keys
        or completion.get("schema_version")
        != "lean-pilot-live-review-transport-completion.v1"
        or completion.get("launch_intent_digest") != canonical_sha256(intent)
        or type(completion.get("exit_status")) is not int
        or completion.get("exit_status") != 0
        or not isinstance(completion.get("session_id"), str)
        or not completion["session_id"]
        or type(completion.get("event_count")) is not int
        or completion["event_count"] <= 0
        or not isinstance(artifacts, dict)
        or set(artifacts) != {"stdout", "stderr", "last_message"}
    ):
        _fail("live_reviewer_transport_invalid", "completion")
    raw_artifacts: dict[str, bytes] = {}
    for key, filename in (
        ("stdout", "stdout.jsonl"),
        ("stderr", "stderr.txt"),
        ("last_message", "last-message.json"),
    ):
        relative = f"{prefix}/{filename}"
        binding, raw_artifacts[key] = _file_binding(
            evidence=evidence,
            relative=relative,
            code="live_reviewer_transport_invalid",
        )
        if artifacts.get(key) != binding:
            _fail("live_reviewer_transport_invalid", relative)
    try:
        session_id, event_count, payload = _provider_payload(
            apparatus=apparatus,
            stdout=raw_artifacts["stdout"],
            exit_status=completion["exit_status"],  # type: ignore[arg-type]
            last_message_path=last_message_path,
        )
    except EvaluationError as exc:
        raise EvaluationError(
            "live_reviewer_transport_invalid",
            str(exc),
        ) from exc
    if (
        session_id != completion["session_id"]
        or event_count != completion["event_count"]
    ):
        _fail("live_reviewer_transport_invalid", "metadata")
    return session_id, payload


def _finalize_review(
    *,
    lock: Mapping[str, object],
    block: str,
    reviewer: str,
    session_id: str,
    payload: Mapping[str, object],
    package: Mapping[str, object],
    evidence: Path,
    prefix: str,
    used_session_ids: Collection[str],
    prior_block_records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if session_id in used_session_ids or any(
        item.get("session_id") == session_id for item in prior_block_records
    ):
        _fail("review_session_reused", session_id)
    record = {
        "record_kind": "review_result.v1",
        "review_id": f"{block}-{reviewer}",
        "pilot_lock_digest": canonical_sha256(lock),
        "reviewer_id": reviewer,
        "session_id": session_id,
        "review_class": "LIVE",
        "rubric_digest": lock["review"]["rubric_digest"],  # type: ignore[index]
        "candidates": payload["candidates"],
        "pairwise_results": payload["pairwise_results"],
    }
    record_bytes = canonical_json_bytes(record)
    with tempfile.NamedTemporaryFile(
        prefix=".review-result-pending-",
        dir=evidence / prefix,
        delete=False,
    ) as pending:
        pending.write(record_bytes)
        pending.flush()
        os.fsync(pending.fileno())
        pending_path = Path(pending.name)
    try:
        loaded = ingest_review(
            pending_path,
            package_root=package["root"],  # type: ignore[arg-type]
            expected_bindings={
                "pilot_lock_digest": canonical_sha256(lock),
                "rubric_digest": lock["review"]["rubric_digest"],  # type: ignore[index]
                "review_class": "LIVE",
                "candidate_labels": tuple(
                    package["manifest"]["candidate_labels"]  # type: ignore[index]
                ),
                "package_id": block,
                "package_manifest_digest": package["manifest_digest"],
                "reviewer_id": reviewer,
            },
            used_session_ids=used_session_ids,
            prior_records=prior_block_records,
        )
    finally:
        pending_path.unlink(missing_ok=True)
    _publish(
        evidence,
        f"{prefix}/review-result.json",
        canonical_json_bytes(loaded),
        code="live_reviewer_review_exists",
    )
    return loaded


def run_live_review_slot(
    *,
    lock: Mapping[str, object],
    block_id: str,
    package_root: Path,
    reviewer_id: str,
    control_root: Path,
    evidence_root: Path,
    reviewer_environment_path: Path,
    used_session_ids: Collection[str],
    prior_block_records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Run one immutable calibrated reviewer slot at most once."""

    block = _safe_component(block_id)
    reviewer = _safe_component(reviewer_id)
    evidence = _canonical_root(evidence_root, must_exist=True)
    if evidence.as_posix() != lock.get("evidence_root"):
        _fail("live_reviewer_apparatus_invalid", "evidence root")
    prefix = f"{block}/reviews/{reviewer}"
    intent_relative = f"{prefix}/launch-intent.json"
    intent_exists = os.path.lexists(evidence / intent_relative)
    for name in (
        "last-message.json",
        "stdout.jsonl",
        "stderr.txt",
        "transport-completion.json",
        "review-result.json",
    ):
        if not intent_exists and os.path.lexists(evidence / prefix / name):
            _fail("live_reviewer_slot_invalid", f"{block}:{reviewer}:{name}")
    if any(item.get("reviewer_id") == reviewer for item in prior_block_records):
        _fail("review_reviewer_reused", reviewer)
    apparatus = validate_live_reviewer_apparatus(
        lock=lock,
        control_root=control_root,
        reviewer_environment_path=reviewer_environment_path,
    )
    apparatus = stage_live_reviewer_assets(
        apparatus=apparatus,
        evidence_root=evidence,
    )
    if reviewer not in apparatus["reviewer_ids"]:
        _fail("live_reviewer_binding_invalid", "reviewer")
    calibration_sessions = apparatus["calibration_session_ids"]
    assert isinstance(calibration_sessions, frozenset)
    if not calibration_sessions.issubset(set(used_session_ids)):
        _fail("live_reviewer_session_ledger_invalid", "calibration coverage")
    package = _package_contract(package_root, block)
    prompt = _prompt(
        package=package,
        rubric_path=apparatus["rubric_path"],  # type: ignore[arg-type]
        reviewer_id=reviewer,
    )
    last_message_path = evidence / prefix / "last-message.json"
    command = _command(apparatus, last_message_path=last_message_path)
    execution = apparatus["execution"]
    assert isinstance(execution, Mapping)
    environment_contract = execution["environment"]
    assert isinstance(environment_contract, Mapping)
    intent = {
        "block_id": block,
        "reviewer_id": reviewer,
        "pilot_lock_digest": canonical_sha256(lock),
        "package_id": block,
        "package_manifest_digest": package["manifest_digest"],
        "environment_identity": environment_contract["identity"],
        "command": command,
        "prompt_contract": prompt,
    }
    if intent_exists:
        retained_intent, _raw = _canonical_object(
            evidence=evidence,
            relative=intent_relative,
            code="live_reviewer_slot_consumed",
        )
        if retained_intent != intent:
            _fail("live_reviewer_slot_consumed", f"{block}:{reviewer}")
        if not os.path.lexists(evidence / prefix / "transport-completion.json"):
            _fail("live_reviewer_slot_consumed", f"{block}:{reviewer}")
        if os.path.lexists(evidence / prefix / "review-result.json"):
            _fail("live_reviewer_review_exists", f"{block}:{reviewer}")
        session_id, payload = _retained_transport(
            apparatus=apparatus,
            evidence=evidence,
            prefix=prefix,
            intent=intent,
            last_message_path=last_message_path,
        )
        return _finalize_review(
            lock=lock,
            block=block,
            reviewer=reviewer,
            session_id=session_id,
            payload=payload,
            package=package,
            evidence=evidence,
            prefix=prefix,
            used_session_ids=used_session_ids,
            prior_block_records=prior_block_records,
        )
    _publish(
        evidence,
        intent_relative,
        canonical_json_bytes(intent),
        code="live_reviewer_slot_consumed",
    )
    stdout, _stderr, process = _run_process(
        command=command,
        package_root=package["root"],  # type: ignore[arg-type]
        environment=apparatus["environment"],  # type: ignore[arg-type]
        prompt=prompt,
        timeout_milliseconds=execution["timeout_milliseconds"],  # type: ignore[arg-type]
        evidence=evidence,
        prefix=prefix,
    )
    session_id, event_count, payload = _provider_payload(
        apparatus=apparatus,
        stdout=stdout,
        exit_status=process.returncode,
        last_message_path=last_message_path,
    )
    if session_id in used_session_ids or any(
        item.get("session_id") == session_id for item in prior_block_records
    ):
        _fail("review_session_reused", session_id)
    completion = _completion_record(
        evidence=evidence,
        prefix=prefix,
        intent=intent,
        exit_status=process.returncode,
        session_id=session_id,
        event_count=event_count,
    )
    _publish(
        evidence,
        f"{prefix}/transport-completion.json",
        canonical_json_bytes(completion),
        code="live_reviewer_transport_invalid",
    )
    return _finalize_review(
        lock=lock,
        block=block,
        reviewer=reviewer,
        session_id=session_id,
        payload=payload,
        package=package,
        evidence=evidence,
        prefix=prefix,
        used_session_ids=used_session_ids,
        prior_block_records=prior_block_records,
    )
