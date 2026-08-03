from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from jsonschema import Draft202012Validator
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLI = REPOSITORY_ROOT / "scripts/experiments/es/cli.py"
sys.path.insert(0, str(REPOSITORY_ROOT))


def _load_module(name: str) -> ModuleType:
    path = REPOSITORY_ROOT / f"scripts/experiments/es/{name}.py"
    spec = importlib.util.spec_from_file_location(f"es_{name}_cli_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision_lock = _load_module("decision_lock")
metering = _load_module("metering")

from scripts.experiments.es import synthesis  # noqa: E402
from tests.experiments import test_es_synthesis as synthesis_fixtures  # noqa: E402


def _sha(fill: str) -> str:
    return "sha256:" + fill * 64


def _canonical(value: object) -> bytes:
    return decision_lock.canonical_json_bytes(value)


def _run(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _bindings(schedule: dict[str, object]) -> dict[str, str]:
    result = {
        "arm_workflow_sha256": _sha("1"),
        "environment_lock_sha256": _sha("2"),
        "evaluator_fixture_manifest_sha256": _sha("3"),
        "prompt_manifest_sha256": _sha("4"),
        "randomization_manifest_sha256": (
            "sha256:" + hashlib.sha256(_canonical(schedule)).hexdigest()
        ),
        "report_schema_sha256": _sha("6"),
        "source_projection_manifest_sha256": _sha("7"),
        "task_profile_sha256": _sha("8"),
        "task_seed_manifest_sha256": _sha("9"),
    }
    return result


def _synthesis_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, Path, list[Path], list[dict[str, Any]]]:
    lock, schedule, bindings = synthesis_fixtures._lock_and_schedule()
    indexes = [
        synthesis_fixtures._attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=ordinal,
            outcome="RICH",
        )
        for ordinal in (1, 2)
    ]
    lock_path = tmp_path / "lock.json"
    randomization_path = tmp_path / "randomization.json"
    bindings_path = tmp_path / "bindings.json"
    index_paths = [tmp_path / f"attempt-{ordinal}.json" for ordinal in (1, 2)]
    lock_path.write_bytes(_canonical(lock))
    randomization_path.write_bytes(_canonical(schedule))
    bindings_path.write_bytes(_canonical(bindings))
    for path, index in zip(index_paths, indexes, strict=True):
        path.write_bytes(synthesis.canonical_report_bytes(index))
    return lock_path, randomization_path, bindings_path, index_paths, indexes


def test_es_cli_module_is_present() -> None:
    assert (REPOSITORY_ROOT / "scripts/experiments/es/cli.py").is_file()


def test_validate_attempt_index_replays_public_validation_and_publishes_canonical_copy(
    tmp_path: Path,
) -> None:
    lock, randomization, bindings, index_paths, indexes = _synthesis_inputs(tmp_path)
    output = tmp_path / "validated-index.json"

    completed = _run(
        "validate-attempt-index",
        "--lock",
        str(lock),
        "--randomization",
        str(randomization),
        "--bindings",
        str(bindings),
        "--input",
        str(index_paths[0]),
        "--expected-index-sha256",
        indexes[0]["index_sha256"],
        "--output",
        str(output),
    )

    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stderr == b""
    assert json.loads(completed.stdout) == {
        "attempt_id": "ES-ATTEMPT-01",
        "index_sha256": indexes[0]["index_sha256"],
        "status": "valid",
    }
    assert output.read_bytes() == synthesis.canonical_report_bytes(indexes[0])


def test_synthesize_report_replays_ordered_immutable_indexes_and_publishes_canonical_report(
    tmp_path: Path,
) -> None:
    lock_path, randomization_path, bindings_path, index_paths, indexes = (
        _synthesis_inputs(tmp_path)
    )
    output = tmp_path / "report.json"
    arguments = [
        "synthesize-report",
        "--lock",
        str(lock_path),
        "--randomization",
        str(randomization_path),
        "--bindings",
        str(bindings_path),
    ]
    for path, index in zip(index_paths, indexes, strict=True):
        arguments.extend(
            [
                "--input",
                str(path),
                "--expected-index-sha256",
                index["index_sha256"],
            ]
        )
    arguments.extend(["--output", str(output)])

    completed = _run(*arguments)

    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stderr == b""
    expected = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[index["index_sha256"] for index in indexes],
        decision_lock=json.loads(lock_path.read_text()),
        randomization_manifest=json.loads(randomization_path.read_text()),
        expected_bindings=json.loads(bindings_path.read_text()),
    )
    expected_bytes = synthesis.canonical_report_bytes(expected)
    assert output.read_bytes() == expected_bytes
    assert json.loads(completed.stdout) == {
        "report_sha256": "sha256:" + hashlib.sha256(expected_bytes).hexdigest(),
        "screen_result": "SCREEN_PASSED",
        "status": "synthesized",
    }


def _validate_attempt_arguments(
    *,
    lock: Path,
    randomization: Path,
    bindings: Path,
    input_path: Path,
    expected_digest: str,
    output: Path,
) -> list[str]:
    return [
        "validate-attempt-index",
        "--lock",
        str(lock),
        "--randomization",
        str(randomization),
        "--bindings",
        str(bindings),
        "--input",
        str(input_path),
        "--expected-index-sha256",
        expected_digest,
        "--output",
        str(output),
    ]


def test_attempt_index_cli_rejects_noncanonical_input_and_external_digest_drift(
    tmp_path: Path,
) -> None:
    lock, randomization, bindings, index_paths, indexes = _synthesis_inputs(tmp_path)
    output = tmp_path / "validated.json"
    arguments = _validate_attempt_arguments(
        lock=lock,
        randomization=randomization,
        bindings=bindings,
        input_path=index_paths[0],
        expected_digest=indexes[0]["index_sha256"],
        output=output,
    )
    index_paths[0].write_text(json.dumps(indexes[0], indent=2))

    noncanonical = _run(*arguments)

    assert noncanonical.returncode == 2
    assert noncanonical.stdout == b""
    assert noncanonical.stderr == (
        f"synthesis_json_noncanonical: {index_paths[0]}\n".encode()
    )
    assert not output.exists()

    index_paths[0].write_bytes(synthesis.canonical_report_bytes(indexes[0]))
    drifted = list(arguments)
    drifted[drifted.index("--expected-index-sha256") + 1] = _sha("0")
    digest_failure = _run(*drifted)
    assert digest_failure.returncode == 2
    assert digest_failure.stdout == b""
    assert digest_failure.stderr == b"synthesis_index_digest_mismatch\n"
    assert not output.exists()


def test_new_provider_free_cli_publications_are_exclusive(tmp_path: Path) -> None:
    lock, randomization, bindings, index_paths, indexes = _synthesis_inputs(tmp_path)
    output = tmp_path / "occupied.json"
    output.write_bytes(b"owner bytes\n")

    completed = _run(
        *_validate_attempt_arguments(
            lock=lock,
            randomization=randomization,
            bindings=bindings,
            input_path=index_paths[0],
            expected_digest=indexes[0]["index_sha256"],
            output=output,
        )
    )

    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr == f"output_not_exclusive: {output}\n".encode()
    assert output.read_bytes() == b"owner bytes\n"


@pytest.mark.parametrize("forbidden_flag", ["--launch", "--run", "--resume", "--provider"])
def test_new_provider_free_cli_rejects_live_operation_flags(
    tmp_path: Path,
    forbidden_flag: str,
) -> None:
    output = tmp_path / "not-published.json"
    arguments = _validate_attempt_arguments(
        lock=tmp_path / "lock.json",
        randomization=tmp_path / "randomization.json",
        bindings=tmp_path / "bindings.json",
        input_path=tmp_path / "attempt.json",
        expected_digest=_sha("0"),
        output=output,
    )

    completed = _run(*arguments, forbidden_flag)

    assert completed.returncode == 2
    assert completed.stdout == b""
    assert b"unrecognized arguments" in completed.stderr
    assert forbidden_flag.encode() in completed.stderr
    assert not output.exists()


def test_task7_cli_does_not_import_controller_or_private_runtime() -> None:
    tree = ast.parse(CLI.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        (
            f"{node.module}.{alias.name}"
            if node.module
            else alias.name
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    )
    assert "controller" not in imported
    assert not any(
        name == "orchestrator.experiments"
        or name.startswith("orchestrator.experiments.")
        or name == "orchestrator.workflow.trial.runtime"
        or name.startswith("orchestrator.workflow.trial.runtime.")
        for name in imported
    )


def test_task3_modules_do_not_import_the_retired_experiment_package() -> None:
    for name in ("metering.py", "decision_lock.py", "cli.py"):
        tree = ast.parse(
            (REPOSITORY_ROOT / "scripts/experiments/es" / name).read_text()
        )
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert not any(
            name == "orchestrator.experiments"
            or name.startswith("orchestrator.experiments.")
            for name in imported
        )


def test_generate_schedule_derive_lock_and_validate_lock_round_trip(
    tmp_path: Path,
) -> None:
    schedule_path = tmp_path / "schedule.json"
    generated = _run(
        "generate-schedule",
        "--seed-sha256",
        _sha("a"),
        "--output",
        str(schedule_path),
    )
    assert generated.returncode == 0, generated.stderr.decode()
    schedule = json.loads(schedule_path.read_text())
    assert schedule_path.read_bytes() == _canonical(schedule)
    Draft202012Validator(
        json.loads(
            (
                REPOSITORY_ROOT
                / "experiments/orc_effectiveness/f1_es/randomization-manifest.schema.json"
            ).read_text()
        )
    ).validate(schedule)

    bindings_path = tmp_path / "bindings.json"
    bindings = _bindings(schedule)
    bindings_path.write_bytes(_canonical(bindings))
    lock_path = tmp_path / "decision-lock.json"
    derived = _run(
        "derive-lock",
        "--bindings",
        str(bindings_path),
        "--schedule",
        str(schedule_path),
        "--output",
        str(lock_path),
    )
    assert derived.returncode == 0, derived.stderr.decode()
    lock = json.loads(lock_path.read_text())
    assert lock_path.read_bytes() == _canonical(lock)
    assert json.loads(derived.stdout) == {
        "lock_sha256": decision_lock.decision_lock_digest(lock)
    }

    validated = _run(
        "validate-lock",
        "--lock",
        str(lock_path),
        "--bindings",
        str(bindings_path),
        "--schedule",
        str(schedule_path),
    )
    assert validated.returncode == 0, validated.stderr.decode()
    assert json.loads(validated.stdout) == {
        "lock_sha256": decision_lock.decision_lock_digest(lock),
        "status": "valid",
    }


def test_cli_publications_are_exclusive_and_lock_validation_rejects_tamper(
    tmp_path: Path,
) -> None:
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text("occupied\n")
    repeated = _run(
        "generate-schedule",
        "--seed-sha256",
        _sha("a"),
        "--output",
        str(schedule_path),
    )
    assert repeated.returncode != 0
    assert schedule_path.read_text() == "occupied\n"

    schedule = decision_lock.generate_randomization_manifest(_sha("a"))
    schedule_path.write_bytes(_canonical(schedule))
    bindings = _bindings(schedule)
    bindings_path = tmp_path / "bindings.json"
    bindings_path.write_bytes(_canonical(bindings))
    lock = decision_lock.build_decision_lock(
        bindings=bindings,
        randomization_manifest=schedule,
    )
    lock["derived"]["call_bounds"]["valid_block"]["maximum"] = 21
    lock_path = tmp_path / "decision-lock.json"
    lock_path.write_bytes(_canonical(lock))

    rejected = _run(
        "validate-lock",
        "--lock",
        str(lock_path),
        "--bindings",
        str(bindings_path),
        "--schedule",
        str(schedule_path),
    )
    assert rejected.returncode != 0
    assert b"decision_lock_mismatch" in rejected.stderr


def _fake_codex(tmp_path: Path) -> Path:
    source = (
        REPOSITORY_ROOT
        / "tests/experiments/fixtures/es_task3/fake_codex_cli.py"
    )
    target = tmp_path / "fake-codex"
    shutil.copyfile(source, target)
    target.chmod(0o755)
    return target


def _meter_arguments(root: Path, fake: Path) -> list[str]:
    return [
        "meter-exec",
        "--evidence-root",
        str(root),
        "--raw-jsonl",
        "raw/provider-attempt-01.jsonl",
        "--receipt",
        "receipts/provider-attempt-01.json",
        "--study-id",
        "F1_ES",
        "--block-id",
        "BLOCK-01",
        "--role-id",
        "IMPLEMENTATION",
        "--call-slot-id",
        "DIRECT.I",
        "--provider-attempt-id",
        "provider-attempt-01",
        "--prompt-sha256",
        _sha("1"),
        "--contract-sha256",
        _sha("2"),
        "--expected-session-id",
        "019f929b-bea9-76a2-955d-5991618b6f34",
        "--",
        str(fake),
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "bounded task",
    ]


def test_meter_exec_byte_tees_provider_output_and_publishes_one_bound_receipt(
    tmp_path: Path,
) -> None:
    fake = _fake_codex(tmp_path)

    completed = _run(*_meter_arguments(tmp_path, fake))

    assert completed.returncode == 0, completed.stderr.decode()
    raw_path = tmp_path / "raw/provider-attempt-01.jsonl"
    receipt_path = tmp_path / "receipts/provider-attempt-01.json"
    assert completed.stdout == raw_path.read_bytes()
    receipt = json.loads(receipt_path.read_text())
    assert receipt_path.read_bytes() == metering.canonical_json_bytes(receipt)
    assert receipt["usage"]["reported_total_tokens"] == 16
    assert receipt["process"]["argv"].count("--json") == 1
    assert receipt["process"]["argv"][2] == "--json"
    assert receipt["executable_chain"]["version"] == "codex-cli 0.145.0"
    assert receipt["executable_chain"]["launcher_sha256"] == (
        "sha256:" + hashlib.sha256(fake.read_bytes()).hexdigest()
    )
    expected_chain = metering.resolve_executable_chain(str(fake))
    assert receipt["executable_chain"] == expected_chain

    expected_path = tmp_path / "expected-calls.json"
    expected_path.write_bytes(
        _canonical(
            [
                {
                    "block_id": "BLOCK-01",
                    "call_slot_id": "DIRECT.I",
                    "contract_sha256": _sha("2"),
                    "executable_chain": expected_chain,
                    "prompt_sha256": _sha("1"),
                    "provider_attempt_id": "provider-attempt-01",
                    "role_id": "IMPLEMENTATION",
                    "study_id": "F1_ES",
                }
            ]
        )
    )
    joined = _run(
        "validate-receipts",
        "--evidence-root",
        str(tmp_path),
        "--expected-calls",
        str(expected_path),
        str(receipt_path),
    )
    assert joined.returncode == 0, joined.stderr.decode()
    assert json.loads(joined.stdout) == {"receipt_count": 1, "status": "valid"}


def test_validate_receipts_cli_normalizes_missing_evidence_paths(
    tmp_path: Path,
) -> None:
    fake = _fake_codex(tmp_path)
    metered = _run(*_meter_arguments(tmp_path, fake))
    assert metered.returncode == 0, metered.stderr.decode()
    receipt_path = tmp_path / "receipts/provider-attempt-01.json"
    raw_path = tmp_path / "raw/provider-attempt-01.jsonl"
    expected_chain = metering.resolve_executable_chain(str(fake))
    expected_path = tmp_path / "expected-calls.json"
    expected_path.write_bytes(
        _canonical(
            [
                {
                    "block_id": "BLOCK-01",
                    "call_slot_id": "DIRECT.I",
                    "contract_sha256": _sha("2"),
                    "executable_chain": expected_chain,
                    "prompt_sha256": _sha("1"),
                    "provider_attempt_id": "provider-attempt-01",
                    "role_id": "IMPLEMENTATION",
                    "study_id": "F1_ES",
                }
            ]
        )
    )

    def validate(evidence_root: Path) -> subprocess.CompletedProcess[bytes]:
        return _run(
            "validate-receipts",
            "--evidence-root",
            str(evidence_root),
            "--expected-calls",
            str(expected_path),
            str(receipt_path),
        )

    control = validate(tmp_path)
    assert control.returncode == 0, control.stderr.decode()
    assert json.loads(control.stdout) == {"receipt_count": 1, "status": "valid"}

    missing_root = tmp_path / "missing-evidence-root"
    root_failure = validate(missing_root)
    assert root_failure.returncode == 2
    assert root_failure.stdout == b""
    assert root_failure.stderr == (
        f"receipt_evidence_root_unreadable: {missing_root}\n".encode()
    )
    assert b"Traceback" not in root_failure.stderr

    raw_path.unlink()
    raw_failure = validate(tmp_path)
    assert raw_failure.returncode == 2
    assert raw_failure.stdout == b""
    assert raw_failure.stderr == b"receipt_raw_unreadable: raw/provider-attempt-01.jsonl\n"
    assert b"Traceback" not in raw_failure.stderr


def test_meter_exec_rejects_resume_flag_drift_and_reused_output_without_launch(
    tmp_path: Path,
) -> None:
    fake = _fake_codex(tmp_path)
    invalid = _meter_arguments(tmp_path, fake)
    invalid[-1] = "resume"
    rejected = _run(*invalid)
    assert rejected.returncode != 0
    assert b"codex_argv_invalid" in rejected.stderr
    assert not (tmp_path / "raw/provider-attempt-01.jsonl").exists()

    valid = _run(*_meter_arguments(tmp_path, fake))
    assert valid.returncode == 0
    raw = (tmp_path / "raw/provider-attempt-01.jsonl").read_bytes()
    receipt = (tmp_path / "receipts/provider-attempt-01.json").read_bytes()
    repeated = _run(*_meter_arguments(tmp_path, fake))
    assert repeated.returncode != 0
    assert (tmp_path / "raw/provider-attempt-01.jsonl").read_bytes() == raw
    assert (tmp_path / "receipts/provider-attempt-01.json").read_bytes() == receipt


def test_meter_exec_preserves_nonzero_provider_exit_in_receipt_and_process_status(
    tmp_path: Path,
) -> None:
    fake = _fake_codex(tmp_path)
    arguments = _meter_arguments(tmp_path, fake)
    arguments[-1] = "exit-7"

    completed = _run(*arguments)

    assert completed.returncode == 7
    receipt = json.loads(
        (tmp_path / "receipts/provider-attempt-01.json").read_text()
    )
    assert receipt["exit_status"] == 7
    assert completed.stdout == (tmp_path / "raw/provider-attempt-01.jsonl").read_bytes()


def test_cli_rejects_noncanonical_duplicate_and_float_control_records(
    tmp_path: Path,
) -> None:
    schedule = decision_lock.generate_randomization_manifest(_sha("a"))
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_bytes(_canonical(schedule))
    bindings = _bindings(schedule)
    bindings_path = tmp_path / "bindings.json"
    lock_path = tmp_path / "lock.json"
    lock_path.write_bytes(
        _canonical(
            decision_lock.build_decision_lock(
                bindings=bindings,
                randomization_manifest=schedule,
            )
        )
    )

    variants = [
        json.dumps(bindings, indent=2).encode() + b"\n",
        _canonical(bindings).replace(
            b'{"arm_workflow_sha256"',
            b'{"arm_workflow_sha256":"' + _sha("1").encode() + b'","arm_workflow_sha256"',
        ),
        _canonical({**bindings, "unexpected_float": 1}).replace(b"1}", b"1.0}"),
    ]
    for raw in variants:
        bindings_path.write_bytes(raw)
        rejected = _run(
            "validate-lock",
            "--lock",
            str(lock_path),
            "--bindings",
            str(bindings_path),
            "--schedule",
            str(schedule_path),
        )
        assert rejected.returncode != 0
