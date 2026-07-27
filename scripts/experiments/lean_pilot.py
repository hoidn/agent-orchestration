#!/usr/bin/env python3
"""Thin command-line entry point for the bounded lean-pilot utilities."""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Sequence

from orchestrator.experiments.contracts import (
    PilotContractError,
    canonical_json_bytes,
    canonical_sha256,
    load_record,
)
from orchestrator.experiments.runner import run_block
from orchestrator.experiments.reporting import (
    ReportingError,
    ReviewBinding,
    UnblindingBinding,
    build_pilot_summary,
    load_attempt_records,
    parse_canonical_decimal,
    plan_sample_size,
    render_pilot_markdown,
)
from orchestrator.experiments.workspace import freeze_product


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-lock")
    validate.add_argument("--lock", type=Path, required=True)

    run = commands.add_parser("run-block")
    run.add_argument("--lock", type=Path, required=True)
    run.add_argument("--block-id", required=True)
    run.add_argument("--work-root", type=Path, required=True)
    run.add_argument("--evidence-root", type=Path, required=True)

    freeze = commands.add_parser("freeze-product")
    freeze.add_argument("--root", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)

    sample = commands.add_parser("plan-sample-size")
    for name in (
        "null-rate",
        "target-rate",
        "alpha",
        "power",
        "max-tie-rate",
        "accrual-probability",
        "max-cost-ratio",
    ):
        sample.add_argument(f"--{name}", required=True)
    for name in (
        "max-invalid-attempts",
        "min-calls-per-block",
        "max-calls-per-block",
        "search-limit",
    ):
        sample.add_argument(f"--{name}", type=int, required=True)

    summarize = commands.add_parser("summarize")
    for name in (
        "lock",
        "evidence-root",
        "review-bindings",
        "unblinding-bindings",
        "json-output",
        "markdown-output",
    ):
        summarize.add_argument(f"--{name}", type=Path, required=True)
    return parser


def _json_exact(value: object) -> object:
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, dict):
        return {key: _json_exact(item) for key, item in value.items()}
    return value


def _canonical_array(path: Path, *, code: str) -> list[object]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportingError(code) from exc
    if not isinstance(value, list) or canonical_json_bytes(value) != raw:
        raise ReportingError(code)
    return value


def _closed_bindings(
    path: Path,
    *,
    binding_type: type[ReviewBinding] | type[UnblindingBinding],
    code: str,
) -> list[ReviewBinding] | list[UnblindingBinding]:
    fields = set(binding_type.__dataclass_fields__)
    bindings: list[ReviewBinding] | list[UnblindingBinding] = []
    for value in _canonical_array(path, code=code):
        if not isinstance(value, dict) or set(value) != fields:
            raise ReportingError(code)
        try:
            bindings.append(binding_type(**value))
        except TypeError as exc:
            raise ReportingError(code) from exc
    return bindings


def _review_path(evidence_root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ReportingError("review_path_invalid")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != value
    ):
        raise ReportingError("review_path_invalid")
    path = evidence_root.joinpath(*relative.parts)
    try:
        identity = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReportingError("review_path_invalid") from exc
    if (
        not stat.S_ISREG(identity.st_mode)
        or path.is_symlink()
        or resolved != path
        or not resolved.is_relative_to(evidence_root)
    ):
        raise ReportingError("review_path_invalid")
    return path


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(
        second
    ) or second.is_relative_to(first)


def _summary_output_paths(
    args: argparse.Namespace,
    *,
    evidence_root: Path,
) -> tuple[Path, Path]:
    outputs = (args.json_output, args.markdown_output)
    resolved_inputs = tuple(
        path.resolve(strict=True)
        for path in (
            args.lock,
            args.review_bindings,
            args.unblinding_bindings,
        )
    )
    if outputs[0] == outputs[1]:
        raise ReportingError("summary_output_overlap")
    for output in outputs:
        if not output.is_absolute() or output.resolve(strict=False) != output:
            raise ReportingError("summary_output_invalid")
        try:
            output.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ReportingError("summary_output_invalid") from exc
        else:
            raise ReportingError("summary_output_exists")
        if _overlaps(output, evidence_root) or any(
            _overlaps(output, input_path) for input_path in resolved_inputs
        ):
            raise ReportingError("summary_output_overlap")
    return outputs


def _publish_new_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.resolve(strict=True) != path.parent or path.parent.is_symlink():
        raise ReportingError("summary_output_invalid")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ReportingError("summary_output_exists") from exc
        except OSError as exc:
            raise ReportingError("summary_output_invalid") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _summarize(args: argparse.Namespace) -> int:
    lock = load_record(args.lock, expected_kind="pilot_lock.v1")
    try:
        evidence_root = args.evidence_root.resolve(strict=True)
    except OSError as exc:
        raise ReportingError("evidence_root_invalid") from exc
    if (
        not args.evidence_root.is_absolute()
        or args.evidence_root.as_posix() != evidence_root.as_posix()
        or not evidence_root.is_dir()
        or args.evidence_root.is_symlink()
        or evidence_root.as_posix() != lock["evidence_root"]
    ):
        raise ReportingError("evidence_root_invalid")
    review_bindings = _closed_bindings(
        args.review_bindings,
        binding_type=ReviewBinding,
        code="review_bindings_invalid",
    )
    unblinding = _closed_bindings(
        args.unblinding_bindings,
        binding_type=UnblindingBinding,
        code="unblinding_bindings_invalid",
    )
    if not all(isinstance(value, ReviewBinding) for value in review_bindings):
        raise AssertionError("review binding type narrowing failed")
    review_paths = [value.review_path for value in review_bindings]
    if len(set(review_paths)) != len(review_paths):
        raise ReportingError("review_bindings_invalid")
    try:
        reviews = [
            load_record(
                _review_path(evidence_root, value),
                expected_kind="review_result.v1",
            )
            for value in review_paths
        ]
    except (OSError, PilotContractError) as exc:
        raise ReportingError("review_record_invalid") from exc
    summary = build_pilot_summary(
        lock=lock,
        block_attempts=load_attempt_records(
            lock=lock,
            evidence_root=evidence_root,
        ),
        reviews=reviews,
        sealed_review_bindings=review_bindings,
        unblinding=unblinding,
    )
    json_output, markdown_output = _summary_output_paths(
        args,
        evidence_root=evidence_root,
    )
    _publish_new_file(json_output, canonical_json_bytes(summary))
    try:
        _publish_new_file(
            markdown_output,
            render_pilot_markdown(summary).encode("utf-8"),
        )
    except Exception:
        json_output.unlink(missing_ok=True)
        raise
    print(canonical_sha256(summary))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-lock":
        lock = load_record(args.lock, expected_kind="pilot_lock.v1")
        print(canonical_sha256(lock))
        return 0
    if args.command == "run-block":
        lock = load_record(args.lock, expected_kind="pilot_lock.v1")
        attempt = run_block(
            lock=lock,
            block_id=args.block_id,
            work_root=args.work_root,
            evidence_root=args.evidence_root,
        )
        print(canonical_json_bytes(attempt.record).decode("utf-8"))
        return 0
    if args.command == "plan-sample-size":
        plan = plan_sample_size(
            null_rate=parse_canonical_decimal(args.null_rate),
            target_rate=parse_canonical_decimal(args.target_rate),
            alpha=parse_canonical_decimal(args.alpha),
            power=parse_canonical_decimal(args.power),
            max_tie_rate=parse_canonical_decimal(args.max_tie_rate),
            accrual_probability=parse_canonical_decimal(
                args.accrual_probability
            ),
            max_invalid_attempts=args.max_invalid_attempts,
            max_cost_ratio=parse_canonical_decimal(args.max_cost_ratio),
            min_calls_per_block=args.min_calls_per_block,
            max_calls_per_block=args.max_calls_per_block,
            search_limit=args.search_limit,
        )
        print(canonical_json_bytes(_json_exact(asdict(plan))).decode("utf-8"))
        return 0
    if args.command == "summarize":
        return _summarize(args)

    manifest = freeze_product(args.root, ())
    output = {
        "digest": manifest.digest,
        "entries": [asdict(entry) for entry in manifest.entries],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(output))
    print(manifest.digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
