"""Strict Codex JSONL metering for the ES effectiveness study.

This module is deliberately study-owned.  It does not depend on the retired
experiment package and does not infer usage from elapsed time.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NamedTuple, NoReturn, Sequence, cast

from jsonschema import Draft202012Validator


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_USAGE_KEYS = frozenset(
    {
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    }
)
_EXPECTED_CALL_KEYS = frozenset(
    {
        "study_id",
        "block_id",
        "role_id",
        "call_slot_id",
        "provider_attempt_id",
        "prompt_sha256",
        "contract_sha256",
        "executable_chain",
    }
)
_RECEIPT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "experiments/orc_effectiveness/f1_es/usage-receipt.schema.json"
)


class MeteringError(ValueError):
    """One metering stream, receipt, or join invariant failed closed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class TerminalUsage(NamedTuple):
    """The sole terminal usage event and its exact raw-stream bindings."""

    session_id: str
    event_line: int
    raw_jsonl_bytes: int
    raw_jsonl_sha256: str
    terminal_event_sha256: str
    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    reported_total_tokens: int


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _reject_constant(value: str) -> NoReturn:
    raise MeteringError("json_noncanonical_number", value)


def _reject_float(value: str) -> NoReturn:
    raise MeteringError("json_noncanonical_number", value)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MeteringError("codex_json_duplicate_key", key)
        result[key] = value
    return result


def _strict_record_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MeteringError("receipt_json_duplicate_key", key)
        result[key] = value
    return result


def _validate_json_value(value: object, *, label: str) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise MeteringError("json_not_utf8", label) from exc
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, label=f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise MeteringError("json_key_invalid", label)
            _validate_json_value(key, label=f"{label}.key")
            _validate_json_value(item, label=f"{label}.{key}")
        return
    raise MeteringError("json_value_invalid", f"{label}:{type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize the closed study records as compact sorted UTF-8 plus one LF."""

    _validate_json_value(value, label="record")
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8", "strict")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MeteringError("json_value_invalid", str(exc)) from exc


def _positive_identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise MeteringError("receipt_field_invalid", field)
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise MeteringError("receipt_field_invalid", field) from exc
    return value


def _sha_field(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise MeteringError("receipt_field_invalid", field)
    return value


def _nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MeteringError("codex_usage_invalid", field)
    return value


def _parse_event(line: bytes, *, line_number: int) -> dict[str, Any]:
    try:
        text = line[:-1].decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise MeteringError("codex_jsonl_not_utf8", str(line_number)) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except MeteringError:
        raise
    except json.JSONDecodeError as exc:
        raise MeteringError("codex_json_malformed", str(line_number)) from exc
    if not isinstance(value, dict):
        raise MeteringError("codex_event_not_object", str(line_number))
    try:
        _validate_json_value(value, label=f"event[{line_number}]")
    except MeteringError as exc:
        if exc.code == "json_not_utf8":
            raise MeteringError("codex_jsonl_not_utf8", str(line_number)) from exc
        raise
    compact = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8", "strict")
    if line[:-1] != compact:
        raise MeteringError("codex_jsonl_noncanonical", str(line_number))
    return value


def parse_codex_jsonl(
    raw: bytes,
    expected_session_id: str | None,
) -> TerminalUsage:
    """Parse one fresh Codex 0.145.0 JSONL turn and bind its terminal usage."""

    if not isinstance(raw, bytes) or not raw:
        raise MeteringError("codex_jsonl_empty")
    if not raw.endswith(b"\n"):
        raise MeteringError("codex_jsonl_not_lf_terminated")
    try:
        raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise MeteringError("codex_jsonl_not_utf8") from exc
    lines = raw.splitlines(keepends=True)
    if any(line == b"\n" or not line.endswith(b"\n") for line in lines):
        raise MeteringError("codex_jsonl_empty_or_partial_line")
    events = [
        _parse_event(line, line_number=index)
        for index, line in enumerate(lines, start=1)
    ]

    thread_rows = [
        (index, event)
        for index, event in enumerate(events, start=1)
        if event.get("type") == "thread.started"
    ]
    if not thread_rows:
        raise MeteringError("codex_thread_missing")
    if len(thread_rows) != 1:
        raise MeteringError("codex_thread_duplicate")
    thread_line, thread_event = thread_rows[0]
    if set(thread_event) != {"type", "thread_id"}:
        raise MeteringError("codex_thread_invalid", str(thread_line))
    session_id = thread_event["thread_id"]
    if not isinstance(session_id, str) or not session_id:
        raise MeteringError("codex_thread_invalid", str(thread_line))
    if expected_session_id is not None and session_id != expected_session_id:
        raise MeteringError("codex_session_mismatch")

    terminal_rows = [
        (index, event)
        for index, event in enumerate(events, start=1)
        if event.get("type") == "turn.completed"
    ]
    if not terminal_rows:
        raise MeteringError("codex_terminal_usage_missing")
    if len(terminal_rows) != 1:
        raise MeteringError("codex_terminal_usage_duplicate")
    terminal_line, terminal_event = terminal_rows[0]
    if terminal_line != len(events):
        raise MeteringError("codex_terminal_not_last")
    if set(terminal_event) != {"type", "usage"}:
        raise MeteringError("codex_terminal_usage_invalid")

    for index, event in enumerate(events, start=1):
        event_session = event.get("thread_id")
        if event_session is not None and event_session != session_id:
            raise MeteringError("codex_cross_thread_event", str(index))
        if index != terminal_line and "usage" in event:
            raise MeteringError("codex_usage_conflicting", str(index))

    usage = terminal_event["usage"]
    if not isinstance(usage, dict) or set(usage) != _USAGE_KEYS:
        raise MeteringError("codex_usage_invalid", "keys")
    tokens = {
        key: _nonnegative_int(usage[key], field=key) for key in sorted(_USAGE_KEYS)
    }
    terminal_raw = lines[terminal_line - 1]
    return TerminalUsage(
        session_id=session_id,
        event_line=terminal_line,
        raw_jsonl_bytes=len(raw),
        raw_jsonl_sha256=_sha256(raw),
        terminal_event_sha256=_sha256(terminal_raw),
        input_tokens=tokens["input_tokens"],
        cached_input_tokens=tokens["cached_input_tokens"],
        cache_write_input_tokens=tokens["cache_write_input_tokens"],
        output_tokens=tokens["output_tokens"],
        reasoning_output_tokens=tokens["reasoning_output_tokens"],
        reported_total_tokens=tokens["input_tokens"] + tokens["output_tokens"],
    )


def _relative_path(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise MeteringError("receipt_field_invalid", field)
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != value
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or "\\" in value
    ):
        raise MeteringError("receipt_field_invalid", field)
    return value


def _validated_executable_chain(value: Mapping[str, object]) -> dict[str, object]:
    keys = {
        "provider_family",
        "version",
        "launcher_path",
        "launcher_sha256",
        "interpreter_path",
        "interpreter_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise MeteringError("receipt_field_invalid", "executable_chain")
    if value["provider_family"] != "codex-cli" or value["version"] != "codex-cli 0.145.0":
        raise MeteringError("receipt_field_invalid", "executable_chain.identity")
    for field in ("launcher_path", "interpreter_path"):
        path = value[field]
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise MeteringError("receipt_field_invalid", f"executable_chain.{field}")
    for field in ("launcher_sha256", "interpreter_sha256"):
        _sha_field(value[field], field=f"executable_chain.{field}")
    return dict(value)


def _validated_process(value: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {"pid", "argv"}:
        raise MeteringError("receipt_field_invalid", "process")
    pid = value["pid"]
    argv = value["argv"]
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise MeteringError("receipt_field_invalid", "process.pid")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise MeteringError("receipt_field_invalid", "process.argv")
    normalized_argv = list(argv)
    return {
        "argv": normalized_argv,
        "argv_sha256": _sha256(canonical_json_bytes(normalized_argv)),
        "pid": pid,
    }


def build_usage_receipt(
    usage: TerminalUsage,
    *,
    study_id: str,
    block_id: str,
    role_id: str,
    call_slot_id: str,
    provider_attempt_id: str,
    prompt_sha256: str,
    contract_sha256: str,
    raw_jsonl_path: str,
    executable_chain: Mapping[str, object],
    process: Mapping[str, object],
    exit_status: int,
) -> dict[str, object]:
    """Build one closed receipt without inferring or repricing provider usage."""

    if not isinstance(usage, TerminalUsage):
        raise MeteringError("receipt_field_invalid", "usage")
    if isinstance(exit_status, bool) or not isinstance(exit_status, int):
        raise MeteringError("receipt_field_invalid", "exit_status")
    record: dict[str, object] = {
        "schema_version": "es_usage_receipt.v1",
        "cost_unit": "CODEX_REPORTED_TOTAL_TOKENS",
        "study_id": _positive_identifier(study_id, field="study_id"),
        "block_id": _positive_identifier(block_id, field="block_id"),
        "role_id": _positive_identifier(role_id, field="role_id"),
        "call_slot_id": _positive_identifier(call_slot_id, field="call_slot_id"),
        "provider_attempt_id": _positive_identifier(
            provider_attempt_id, field="provider_attempt_id"
        ),
        "session_id": _positive_identifier(usage.session_id, field="session_id"),
        "prompt_sha256": _sha_field(prompt_sha256, field="prompt_sha256"),
        "contract_sha256": _sha_field(contract_sha256, field="contract_sha256"),
        "executable_chain": _validated_executable_chain(executable_chain),
        "process": _validated_process(process),
        "raw_jsonl": {
            "path": _relative_path(raw_jsonl_path, field="raw_jsonl.path"),
            "bytes": usage.raw_jsonl_bytes,
            "sha256": usage.raw_jsonl_sha256,
        },
        "terminal_event": {
            "line": usage.event_line,
            "sha256": usage.terminal_event_sha256,
        },
        "usage": {
            "input_tokens": usage.input_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "cache_write_input_tokens": usage.cache_write_input_tokens,
            "output_tokens": usage.output_tokens,
            "reasoning_output_tokens": usage.reasoning_output_tokens,
            "reported_total_tokens": usage.reported_total_tokens,
        },
        "exit_status": exit_status,
    }
    _validate_receipt_record(record)
    return record


def _load_canonical_object(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_record_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except MeteringError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MeteringError("receipt_json_invalid", str(path)) from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise MeteringError("receipt_json_noncanonical", str(path))
    return value


def _receipt_schema() -> dict[str, Any]:
    schema = _load_canonical_object(_RECEIPT_SCHEMA_PATH)
    return schema


def _validate_receipt_record(record: Mapping[str, object]) -> None:
    schema = _receipt_schema()
    errors = sorted(Draft202012Validator(schema).iter_errors(record), key=str)
    if errors:
        raise MeteringError("receipt_schema_invalid", errors[0].message)
    usage = record["usage"]
    process = record["process"]
    assert isinstance(usage, Mapping) and isinstance(process, Mapping)
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "reported_total_tokens",
    ):
        value = usage[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MeteringError("receipt_usage_invalid", key)
    if usage["reported_total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        raise MeteringError("receipt_usage_invalid", "reported_total_tokens")
    argv = process["argv"]
    if process["argv_sha256"] != _sha256(canonical_json_bytes(argv)):
        raise MeteringError("receipt_process_invalid", "argv_sha256")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise MeteringError("receipt_process_invalid", "argv")
    try:
        normalized_argv = normalize_codex_argv(cast(list[str], argv))
    except MeteringError as exc:
        raise MeteringError("receipt_process_invalid", "argv") from exc
    if tuple(argv) != normalized_argv:
        raise MeteringError("receipt_process_invalid", "argv")


def _validate_expected_call(value: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _EXPECTED_CALL_KEYS:
        raise MeteringError("receipt_join_expected_call_invalid")
    result: dict[str, object] = {}
    for key in sorted(_EXPECTED_CALL_KEYS):
        item = value[key]
        if key == "executable_chain":
            if not isinstance(item, Mapping):
                raise MeteringError("receipt_join_expected_call_invalid")
            result[key] = _validated_executable_chain(item)
        elif key.endswith("_sha256"):
            result[key] = _sha_field(item, field=f"expected.{key}")
        else:
            result[key] = _positive_identifier(item, field=f"expected.{key}")
    return result


def validate_receipt_join(
    receipt_paths: Sequence[Path],
    expected_calls: Sequence[Mapping[str, object]],
    *,
    evidence_root: Path,
) -> tuple[dict[str, object], ...]:
    """Validate exact call coverage and reopen every receipt's immutable raw stream."""

    root_candidate = Path(evidence_root)
    try:
        root = root_candidate.resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(str(root_candidate))
    except (OSError, ValueError) as exc:
        raise MeteringError(
            "receipt_evidence_root_unreadable", str(root_candidate)
        ) from exc
    expected = [_validate_expected_call(row) for row in expected_calls]
    if len({row["call_slot_id"] for row in expected}) != len(expected):
        raise MeteringError("receipt_join_expected_call_duplicate")
    records: list[dict[str, object]] = []
    for path in receipt_paths:
        record = _load_canonical_object(Path(path))
        _validate_receipt_record(record)
        records.append(record)
    for field in ("call_slot_id", "provider_attempt_id", "session_id"):
        values = [record[field] for record in records]
        if len(set(values)) != len(values):
            raise MeteringError("receipt_join_duplicate", field)
    if len(records) != len(expected):
        raise MeteringError("receipt_join_cardinality")
    by_slot = {str(record["call_slot_id"]): record for record in records}
    if set(by_slot) != {row["call_slot_id"] for row in expected}:
        raise MeteringError("receipt_join_call_slots")
    expected_by_slot = {row["call_slot_id"]: row for row in expected}
    for call_slot, record in by_slot.items():
        expected_row = expected_by_slot[call_slot]
        for key, value in expected_row.items():
            if record[key] != value:
                raise MeteringError("receipt_join_binding_mismatch", f"{call_slot}.{key}")

    for record in records:
        raw_binding = record["raw_jsonl"]
        assert isinstance(raw_binding, Mapping)
        relative = _relative_path(raw_binding["path"], field="raw_jsonl.path")
        try:
            raw_path = (root / relative).resolve(strict=True)
            raw_path.relative_to(root)
            raw = raw_path.read_bytes()
        except (OSError, ValueError) as exc:
            raise MeteringError("receipt_raw_unreadable", relative) from exc
        if len(raw) != raw_binding["bytes"] or _sha256(raw) != raw_binding["sha256"]:
            raise MeteringError("receipt_raw_binding_mismatch", relative)
        parsed = parse_codex_jsonl(raw, expected_session_id=str(record["session_id"]))
        usage = record["usage"]
        terminal = record["terminal_event"]
        assert isinstance(usage, Mapping) and isinstance(terminal, Mapping)
        expected_usage = {
            "input_tokens": parsed.input_tokens,
            "cached_input_tokens": parsed.cached_input_tokens,
            "cache_write_input_tokens": parsed.cache_write_input_tokens,
            "output_tokens": parsed.output_tokens,
            "reasoning_output_tokens": parsed.reasoning_output_tokens,
            "reported_total_tokens": parsed.reported_total_tokens,
        }
        if usage != expected_usage:
            raise MeteringError("receipt_usage_binding_mismatch", relative)
        if terminal != {
            "line": parsed.event_line,
            "sha256": parsed.terminal_event_sha256,
        }:
            raise MeteringError("receipt_terminal_binding_mismatch", relative)
    return tuple(sorted(records, key=lambda row: str(row["call_slot_id"])))


def normalize_codex_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Return one fresh unrestricted noninteractive Codex exec invocation."""

    values = list(argv)
    required = (
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
    )
    contract_flags = (*required, "--json")
    if (
        len(values) < 3
        or any(not isinstance(item, str) or not item for item in values)
        or values[1] != "exec"
    ):
        raise MeteringError("codex_argv_invalid")
    separator = values.index("--", 2) if "--" in values[2:] else len(values)
    active_segment = values[2:separator]
    prompt_segment = values[separator + 1 :] if separator < len(values) else []
    if (
        "resume" in active_segment
        or any(active_segment.count(flag) != 1 for flag in required)
        or active_segment.count("--json") > 1
        or any(flag in prompt_segment for flag in contract_flags)
    ):
        raise MeteringError("codex_argv_invalid")
    if "--json" not in active_segment:
        values.insert(2, "--json")
    return tuple(values)


def _file_sha256(path: Path) -> str:
    try:
        return _sha256(path.read_bytes())
    except OSError as exc:
        raise MeteringError("executable_chain_unreadable", str(path)) from exc


def resolve_executable_chain(command: str) -> dict[str, object]:
    """Resolve and verify the launcher, shebang interpreter, and pinned version."""

    if not isinstance(command, str) or not command:
        raise MeteringError("executable_chain_invalid", "command")
    located = shutil.which(command) if "/" not in command else command
    if located is None:
        raise MeteringError("executable_chain_unreadable", command)
    try:
        launcher = Path(located).resolve(strict=True)
        first_line = launcher.read_bytes().splitlines()[0].decode("utf-8", "strict")
    except (OSError, IndexError, UnicodeDecodeError) as exc:
        raise MeteringError("executable_chain_unreadable", command) from exc
    if not first_line.startswith("#!"):
        raise MeteringError("executable_chain_invalid", "missing shebang")
    try:
        shebang = shlex.split(first_line[2:].strip())
    except ValueError as exc:
        raise MeteringError("executable_chain_invalid", "shebang") from exc
    if not shebang:
        raise MeteringError("executable_chain_invalid", "shebang")
    if Path(shebang[0]).name == "env":
        if len(shebang) != 2:
            raise MeteringError("executable_chain_invalid", "env shebang")
        interpreter_value = shutil.which(shebang[1])
        if interpreter_value is None:
            raise MeteringError("executable_chain_unreadable", shebang[1])
    else:
        if len(shebang) != 1:
            raise MeteringError("executable_chain_invalid", "direct shebang")
        interpreter_value = shebang[0]
    try:
        interpreter = Path(interpreter_value).resolve(strict=True)
    except OSError as exc:
        raise MeteringError("executable_chain_unreadable", interpreter_value) from exc
    version_probe = subprocess.run(
        [str(Path(located).absolute()), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        version = version_probe.stdout.decode("utf-8", "strict").strip()
    except UnicodeDecodeError as exc:
        raise MeteringError("executable_chain_version_invalid") from exc
    if version_probe.returncode != 0 or version != "codex-cli 0.145.0":
        raise MeteringError("executable_chain_version_invalid", version)
    return {
        "provider_family": "codex-cli",
        "version": version,
        "launcher_path": str(launcher),
        "launcher_sha256": _file_sha256(launcher),
        "interpreter_path": str(interpreter),
        "interpreter_sha256": _file_sha256(interpreter),
    }


def _exclusive_descriptor(path: Path) -> int:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        return os.open(path, flags, 0o600)
    except OSError as exc:
        raise MeteringError("evidence_publication_not_exclusive", str(path)) from exc


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise MeteringError("evidence_publication_failed")
        view = view[written:]


def _publish_exclusive(path: Path, data: bytes) -> None:
    descriptor = _exclusive_descriptor(path)
    try:
        _write_all(descriptor, data)
        os.fsync(descriptor)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise
    finally:
        os.close(descriptor)


def run_metered_command(
    argv: Sequence[str],
    *,
    evidence_root: Path,
    raw_jsonl_path: str,
    receipt_path: str,
    study_id: str,
    block_id: str,
    role_id: str,
    call_slot_id: str,
    provider_attempt_id: str,
    prompt_sha256: str,
    contract_sha256: str,
    expected_session_id: str | None,
) -> tuple[int, dict[str, object]]:
    """Execute one fresh call, preserve exact output, and publish one receipt."""

    normalized = normalize_codex_argv(argv)
    root = Path(evidence_root).resolve(strict=True)
    raw_relative = _relative_path(raw_jsonl_path, field="raw_jsonl_path")
    receipt_relative = _relative_path(receipt_path, field="receipt_path")
    if raw_relative == receipt_relative:
        raise MeteringError("evidence_publication_overlap")
    raw_path = root / raw_relative
    target_receipt = root / receipt_relative
    if target_receipt.exists() or target_receipt.is_symlink():
        raise MeteringError("evidence_publication_not_exclusive", receipt_relative)
    executable_chain = resolve_executable_chain(normalized[0])
    raw_descriptor = _exclusive_descriptor(raw_path)
    try:
        process = subprocess.Popen(
            normalized,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate()
        _write_all(raw_descriptor, stdout)
        os.fsync(raw_descriptor)
    finally:
        os.close(raw_descriptor)
    sys.stdout.buffer.write(stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(stderr)
    sys.stderr.buffer.flush()
    usage = parse_codex_jsonl(stdout, expected_session_id=expected_session_id)
    receipt = build_usage_receipt(
        usage,
        study_id=study_id,
        block_id=block_id,
        role_id=role_id,
        call_slot_id=call_slot_id,
        provider_attempt_id=provider_attempt_id,
        prompt_sha256=prompt_sha256,
        contract_sha256=contract_sha256,
        raw_jsonl_path=raw_relative,
        executable_chain=executable_chain,
        process={"pid": process.pid, "argv": list(normalized)},
        exit_status=process.returncode,
    )
    _publish_exclusive(target_receipt, canonical_json_bytes(receipt))
    return process.returncode, receipt


__all__ = [
    "MeteringError",
    "TerminalUsage",
    "build_usage_receipt",
    "canonical_json_bytes",
    "normalize_codex_argv",
    "parse_codex_jsonl",
    "resolve_executable_chain",
    "run_metered_command",
    "validate_receipt_join",
]
