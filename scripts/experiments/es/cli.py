"""Command-line façade for deterministic ES evidence operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, NoReturn, Sequence

try:  # Direct script execution places this directory, not the repo, on sys.path.
    from . import decision_lock, metering, synthesis
except ImportError:  # pragma: no cover - exercised by subprocess CLI tests
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.experiments.es import (  # type: ignore[no-redef]
        decision_lock,
        metering,
        synthesis,
    )


def _reject_constant(value: str) -> NoReturn:
    raise decision_lock.DecisionLockError("json_number_noncanonical", value)


def _reject_float(value: str) -> NoReturn:
    raise decision_lock.DecisionLockError("json_number_noncanonical", value)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise decision_lock.DecisionLockError("json_duplicate_key", key)
        result[key] = value
    return result


def _load_canonical_value(path: Path) -> object:
    candidate = Path(path)
    try:
        raw = candidate.read_bytes()
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except decision_lock.DecisionLockError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise decision_lock.DecisionLockError(
            "json_record_invalid", str(candidate)
        ) from exc
    if decision_lock.canonical_json_bytes(value) != raw:
        raise decision_lock.DecisionLockError(
            "json_record_noncanonical", str(candidate)
        )
    return value


def _load_canonical_synthesis_value(path: Path) -> object:
    candidate = Path(path)
    try:
        raw = candidate.read_bytes()
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except decision_lock.DecisionLockError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise synthesis.SynthesisError("synthesis_json_invalid", str(candidate)) from exc
    if synthesis.canonical_report_bytes(value) != raw:
        raise synthesis.SynthesisError(
            "synthesis_json_noncanonical", str(candidate)
        )
    return value


def _publish_exclusive(path: Path, data: bytes) -> None:
    candidate = Path(path)
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            candidate,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise decision_lock.DecisionLockError(
            "output_not_exclusive", str(candidate)
        ) from exc
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise decision_lock.DecisionLockError(
                    "output_publication_failed", str(candidate)
                )
            view = view[written:]
        os.fsync(descriptor)
    except Exception:
        candidate.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _print_json(value: object) -> None:
    sys.stdout.buffer.write(decision_lock.canonical_json_bytes(value))
    sys.stdout.buffer.flush()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="es")
    commands = parser.add_subparsers(dest="command_name", required=True)

    schedule = commands.add_parser("generate-schedule")
    schedule.add_argument("--seed-sha256", required=True)
    schedule.add_argument("--output", type=Path, required=True)

    derive = commands.add_parser("derive-lock")
    derive.add_argument("--bindings", type=Path, required=True)
    derive.add_argument("--schedule", type=Path, required=True)
    derive.add_argument("--output", type=Path, required=True)

    validate_lock = commands.add_parser("validate-lock")
    validate_lock.add_argument("--lock", type=Path, required=True)
    validate_lock.add_argument("--bindings", type=Path, required=True)
    validate_lock.add_argument("--schedule", type=Path, required=True)

    receipts = commands.add_parser("validate-receipts")
    receipts.add_argument("--evidence-root", type=Path, required=True)
    receipts.add_argument("--expected-calls", type=Path, required=True)
    receipts.add_argument("receipt_paths", type=Path, nargs="+")

    validate_index = commands.add_parser("validate-attempt-index")
    validate_index.add_argument("--lock", type=Path, required=True)
    validate_index.add_argument("--randomization", type=Path, required=True)
    validate_index.add_argument("--bindings", type=Path, required=True)
    validate_index.add_argument("--input", type=Path, required=True)
    validate_index.add_argument("--expected-index-sha256", required=True)
    validate_index.add_argument("--output", type=Path, required=True)

    synthesize = commands.add_parser("synthesize-report")
    synthesize.add_argument("--lock", type=Path, required=True)
    synthesize.add_argument("--randomization", type=Path, required=True)
    synthesize.add_argument("--bindings", type=Path, required=True)
    synthesize.add_argument(
        "--input", dest="input_paths", action="append", type=Path, required=True
    )
    synthesize.add_argument(
        "--expected-index-sha256",
        dest="expected_index_digests",
        action="append",
        required=True,
    )
    synthesize.add_argument("--output", type=Path, required=True)

    meter = commands.add_parser("meter-exec")
    meter.add_argument("--evidence-root", type=Path, required=True)
    meter.add_argument("--raw-jsonl", required=True)
    meter.add_argument("--receipt", required=True)
    meter.add_argument("--study-id", required=True)
    meter.add_argument("--block-id", required=True)
    meter.add_argument("--role-id", required=True)
    meter.add_argument("--call-slot-id", required=True)
    meter.add_argument("--provider-attempt-id", required=True)
    meter.add_argument("--prompt-sha256", required=True)
    meter.add_argument("--contract-sha256", required=True)
    meter.add_argument("--expected-session-id")
    meter.add_argument("provider_argv", nargs=argparse.REMAINDER)
    return parser


def _object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise decision_lock.DecisionLockError("json_object_required", field)
    return value


def _run(args: argparse.Namespace) -> int:
    if args.command_name == "generate-schedule":
        value = decision_lock.generate_randomization_manifest(args.seed_sha256)
        _publish_exclusive(args.output, decision_lock.canonical_json_bytes(value))
        return 0
    if args.command_name == "derive-lock":
        bindings = _object(_load_canonical_value(args.bindings), field="bindings")
        schedule = _object(_load_canonical_value(args.schedule), field="schedule")
        value = decision_lock.build_decision_lock(
            bindings=bindings,
            randomization_manifest=schedule,
        )
        _publish_exclusive(args.output, decision_lock.canonical_json_bytes(value))
        _print_json({"lock_sha256": decision_lock.decision_lock_digest(value)})
        return 0
    if args.command_name == "validate-lock":
        value = _object(_load_canonical_value(args.lock), field="lock")
        bindings = _object(_load_canonical_value(args.bindings), field="bindings")
        schedule = _object(_load_canonical_value(args.schedule), field="schedule")
        decision_lock.validate_decision_lock(
            value,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )
        _print_json(
            {
                "lock_sha256": decision_lock.decision_lock_digest(value),
                "status": "valid",
            }
        )
        return 0
    if args.command_name == "validate-receipts":
        expected = _load_canonical_value(args.expected_calls)
        if not isinstance(expected, list) or any(
            not isinstance(row, dict) for row in expected
        ):
            raise metering.MeteringError("receipt_join_expected_calls_invalid")
        records = metering.validate_receipt_join(
            args.receipt_paths,
            expected,
            evidence_root=args.evidence_root,
        )
        _print_json({"receipt_count": len(records), "status": "valid"})
        return 0
    if args.command_name == "validate-attempt-index":
        lock = _object(_load_canonical_value(args.lock), field="lock")
        randomization = _object(
            _load_canonical_value(args.randomization), field="randomization"
        )
        bindings = _object(_load_canonical_value(args.bindings), field="bindings")
        attempt_index = _object(
            _load_canonical_synthesis_value(args.input), field="input"
        )
        validated = synthesis.validate_attempt_evidence_index(
            attempt_index,
            expected_index_sha256=args.expected_index_sha256,
            decision_lock=lock,
            randomization_manifest=randomization,
            expected_bindings=bindings,
        )
        _publish_exclusive(args.output, synthesis.canonical_report_bytes(validated))
        _print_json(
            {
                "attempt_id": validated["attempt_record"]["attempt_id"],
                "index_sha256": validated["index_sha256"],
                "status": "valid",
            }
        )
        return 0
    if args.command_name == "synthesize-report":
        lock = _object(_load_canonical_value(args.lock), field="lock")
        randomization = _object(
            _load_canonical_value(args.randomization), field="randomization"
        )
        bindings = _object(_load_canonical_value(args.bindings), field="bindings")
        indexed_attempts = [
            _object(_load_canonical_synthesis_value(path), field="input")
            for path in args.input_paths
        ]
        report = synthesis.synthesize_report(
            indexed_attempts=indexed_attempts,
            expected_index_digests=args.expected_index_digests,
            decision_lock=lock,
            randomization_manifest=randomization,
            expected_bindings=bindings,
        )
        report_bytes = synthesis.canonical_report_bytes(report)
        _publish_exclusive(args.output, report_bytes)
        _print_json(
            {
                "report_sha256": "sha256:" + hashlib.sha256(report_bytes).hexdigest(),
                "screen_result": report["screen_result"],
                "status": "synthesized",
            }
        )
        return 0
    if args.command_name == "meter-exec":
        provider_argv = list(args.provider_argv)
        if provider_argv and provider_argv[0] == "--":
            provider_argv.pop(0)
        exit_status, _ = metering.run_metered_command(
            provider_argv,
            evidence_root=args.evidence_root,
            raw_jsonl_path=args.raw_jsonl,
            receipt_path=args.receipt,
            study_id=args.study_id,
            block_id=args.block_id,
            role_id=args.role_id,
            call_slot_id=args.call_slot_id,
            provider_attempt_id=args.provider_attempt_id,
            prompt_sha256=args.prompt_sha256,
            contract_sha256=args.contract_sha256,
            expected_session_id=args.expected_session_id,
        )
        return exit_status
    raise decision_lock.DecisionLockError("command_invalid")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        return _run(parser.parse_args(argv))
    except (
        decision_lock.DecisionLockError,
        metering.MeteringError,
        synthesis.SynthesisError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
