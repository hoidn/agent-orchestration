from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_metering() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/experiments/es/metering.py"
    spec = importlib.util.spec_from_file_location("es_metering", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metering = _load_metering()


def test_metering_module_is_present() -> None:
    assert (REPOSITORY_ROOT / "scripts/experiments/es/metering.py").is_file()


def _raw_jsonl(
    *,
    session_id: str = "019f929b-bea9-76a2-955d-5991618b6f34",
    usage: dict[str, object] | None = None,
) -> bytes:
    selected_usage = usage or {
        "input_tokens": 16911,
        "cached_input_tokens": 13056,
        "cache_write_input_tokens": 0,
        "output_tokens": 5,
        "reasoning_output_tokens": 0,
    }
    rows = [
        {"type": "thread.started", "thread_id": session_id},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "item_0", "type": "agent_message", "text": "OK"},
        },
        {"type": "turn.completed", "usage": selected_usage},
    ]
    # This deliberately preserves the provider's observed field order rather than
    # pretending the immutable raw event stream is a reserialized JSON document.
    return b"".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
        for row in rows
    )


def _sha(fill: str) -> str:
    return "sha256:" + fill * 64


def _executable_chain() -> dict[str, object]:
    return {
        "provider_family": "codex-cli",
        "version": "codex-cli 0.145.0",
        "launcher_path": "/opt/codex/bin/codex.js",
        "launcher_sha256": _sha("3"),
        "interpreter_path": "/opt/node/bin/node",
        "interpreter_sha256": _sha("4"),
    }


def _receipt(
    root: Path,
    *,
    role_id: str = "IMPLEMENTATION",
    call_slot_id: str = "DIRECT.I",
    provider_attempt_id: str = "provider-attempt-01",
    session_id: str = "019f929b-bea9-76a2-955d-5991618b6f34",
    raw_name: str = "raw/provider-attempt-01.jsonl",
) -> tuple[Path, dict[str, Any]]:
    raw = _raw_jsonl(session_id=session_id)
    raw_path = root / raw_name
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    usage = metering.parse_codex_jsonl(raw, expected_session_id=session_id)
    record = metering.build_usage_receipt(
        usage,
        study_id="F1_ES",
        block_id="BLOCK-01",
        role_id=role_id,
        call_slot_id=call_slot_id,
        provider_attempt_id=provider_attempt_id,
        prompt_sha256=_sha("1"),
        contract_sha256=_sha("2"),
        raw_jsonl_path=raw_name,
        executable_chain=_executable_chain(),
        process={
            "pid": 4312,
            "argv": [
                "/opt/codex/bin/codex",
                "exec",
                "--json",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "bounded task",
            ],
        },
        exit_status=0,
    )
    receipt_path = root / f"receipts/{provider_attempt_id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(metering.canonical_json_bytes(record))
    return receipt_path, record


def _expected_call(
    *,
    role_id: str = "IMPLEMENTATION",
    call_slot_id: str = "DIRECT.I",
    provider_attempt_id: str = "provider-attempt-01",
) -> dict[str, object]:
    return {
        "study_id": "F1_ES",
        "block_id": "BLOCK-01",
        "role_id": role_id,
        "call_slot_id": call_slot_id,
        "provider_attempt_id": provider_attempt_id,
        "prompt_sha256": _sha("1"),
        "contract_sha256": _sha("2"),
        "executable_chain": _executable_chain(),
    }


def _tamper_process_flags(record: dict[str, Any]) -> None:
    argv = record["process"]["argv"]
    argv.remove("--skip-git-repo-check")
    record["process"]["argv_sha256"] = (
        "sha256:" + hashlib.sha256(metering.canonical_json_bytes(argv)).hexdigest()
    )


def test_parse_codex_jsonl_extracts_the_exact_0145_terminal_usage() -> None:
    raw = _raw_jsonl()

    usage = metering.parse_codex_jsonl(
        raw,
        expected_session_id="019f929b-bea9-76a2-955d-5991618b6f34",
    )

    assert usage.session_id == "019f929b-bea9-76a2-955d-5991618b6f34"
    assert usage.event_line == 4
    assert usage.input_tokens == 16911
    assert usage.cached_input_tokens == 13056
    assert usage.cache_write_input_tokens == 0
    assert usage.output_tokens == 5
    assert usage.reasoning_output_tokens == 0
    assert usage.reported_total_tokens == 16916
    assert usage.raw_jsonl_bytes == len(raw)
    assert usage.raw_jsonl_sha256 == (
        "sha256:" + hashlib.sha256(raw).hexdigest()
    )
    terminal_line = raw.splitlines(keepends=True)[3]
    assert usage.terminal_event_sha256 == (
        "sha256:" + hashlib.sha256(terminal_line).hexdigest()
    )


def test_checked_in_0145_raw_fixture_matches_the_observed_terminal_shape() -> None:
    fixture = (
        REPOSITORY_ROOT
        / "tests/experiments/fixtures/es_task3/codex-0.145.0-success.jsonl"
    ).read_bytes()
    assert fixture == _raw_jsonl()
    assert metering.parse_codex_jsonl(
        fixture,
        expected_session_id="019f929b-bea9-76a2-955d-5991618b6f34",
    ).reported_total_tokens == 16916


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda raw: raw[:-1], "codex_jsonl_not_lf_terminated"),
        (lambda raw: b"\xff" + raw, "codex_jsonl_not_utf8"),
        (
            lambda raw: raw.replace(b'"turn.completed"', b'"turn.failed"'),
            "codex_terminal_usage_missing",
        ),
        (
            lambda raw: raw + raw.splitlines(keepends=True)[-1],
            "codex_terminal_usage_duplicate",
        ),
        (
            lambda raw: raw.replace(
                b'{"type":"turn.started"}',
                b'{"type":"turn.started","type":"turn.started"}',
            ),
            "codex_json_duplicate_key",
        ),
        (
            lambda raw: raw.replace(b'{"type":"turn.started"}', b"{"),
            "codex_json_malformed",
        ),
        (
            lambda raw: raw.replace(b"\n", b"\r\n", 1),
            "codex_jsonl_noncanonical",
        ),
        (
            lambda raw: raw.replace(
                b'{"type":"turn.started"}', b'{ "type": "turn.started" }'
            ),
            "codex_jsonl_noncanonical",
        ),
        (
            lambda raw: raw.replace(
                b'{"type":"turn.started"}',
                b'{"type":"turn.started","usage":{"input_tokens":1,'
                b'"cached_input_tokens":0,"cache_write_input_tokens":0,'
                b'"output_tokens":1,"reasoning_output_tokens":0}}',
            ),
            "codex_usage_conflicting",
        ),
        (
            lambda raw: raw
            + b'{"type":"item.completed","thread_id":"foreign"}\n',
            "codex_terminal_not_last",
        ),
    ],
)
def test_parse_codex_jsonl_fails_closed_on_stream_corruption(
    mutator: object,
    code: str,
) -> None:
    raw = mutator(_raw_jsonl())  # type: ignore[operator]

    with pytest.raises(metering.MeteringError, match=f"^{code}"):
        metering.parse_codex_jsonl(
            raw,
            expected_session_id="019f929b-bea9-76a2-955d-5991618b6f34",
        )


@pytest.mark.parametrize(
    "usage",
    [
        {
            "input_tokens": 1,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "output_tokens": 1,
        },
        {
            "input_tokens": 1,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "output_tokens": 1,
            "reasoning_output_tokens": 0,
            "total_tokens": 2,
        },
        {
            "input_tokens": True,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "output_tokens": 1,
            "reasoning_output_tokens": 0,
        },
        {
            "input_tokens": -1,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "output_tokens": 1,
            "reasoning_output_tokens": 0,
        },
    ],
)
def test_parse_codex_jsonl_requires_the_exact_closed_usage_shape(
    usage: dict[str, object],
) -> None:
    with pytest.raises(metering.MeteringError, match="^codex_usage_invalid"):
        metering.parse_codex_jsonl(
            _raw_jsonl(usage=usage),
            expected_session_id="019f929b-bea9-76a2-955d-5991618b6f34",
        )


def test_parse_codex_jsonl_rejects_duplicate_or_cross_attempt_threads() -> None:
    raw = _raw_jsonl()
    duplicate_thread = raw.splitlines(keepends=True)[0] + raw
    with pytest.raises(metering.MeteringError, match="^codex_thread_duplicate"):
        metering.parse_codex_jsonl(
            duplicate_thread,
            expected_session_id="019f929b-bea9-76a2-955d-5991618b6f34",
        )

    with pytest.raises(metering.MeteringError, match="^codex_session_mismatch"):
        metering.parse_codex_jsonl(raw, expected_session_id="different-session")

    cross_thread = raw.replace(
        b'{"type":"turn.started"}',
        b'{"type":"turn.started","thread_id":"different-session"}',
    )
    with pytest.raises(metering.MeteringError, match="^codex_cross_thread_event"):
        metering.parse_codex_jsonl(
            cross_thread,
            expected_session_id="019f929b-bea9-76a2-955d-5991618b6f34",
        )


def test_usage_receipt_binds_raw_event_process_and_exact_cost_unit(
    tmp_path: Path,
) -> None:
    receipt_path, record = _receipt(tmp_path)
    schema_path = (
        REPOSITORY_ROOT
        / "experiments/orc_effectiveness/f1_es/usage-receipt.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    Draft202012Validator(schema).validate(record)

    assert receipt_path.read_bytes() == metering.canonical_json_bytes(record)
    assert record["cost_unit"] == "CODEX_REPORTED_TOTAL_TOKENS"
    assert record["usage"] == {
        "cache_write_input_tokens": 0,
        "cached_input_tokens": 13056,
        "input_tokens": 16911,
        "output_tokens": 5,
        "reasoning_output_tokens": 0,
        "reported_total_tokens": 16916,
    }
    assert record["terminal_event"] == {
        "line": 4,
        "sha256": metering.parse_codex_jsonl(
            _raw_jsonl(),
            expected_session_id="019f929b-bea9-76a2-955d-5991618b6f34",
        ).terminal_event_sha256,
    }
    assert record["raw_jsonl"] == {
        "bytes": len(_raw_jsonl()),
        "path": "raw/provider-attempt-01.jsonl",
        "sha256": "sha256:" + hashlib.sha256(_raw_jsonl()).hexdigest(),
    }
    assert record["process"]["argv_sha256"] == (
        "sha256:"
        + hashlib.sha256(
            metering.canonical_json_bytes(record["process"]["argv"])
        ).hexdigest()
    )


def test_validate_receipt_join_reopens_raw_bytes_and_enforces_all_uniqueness(
    tmp_path: Path,
) -> None:
    first_path, _ = _receipt(tmp_path)
    second_path, _ = _receipt(
        tmp_path,
        call_slot_id="PRODUCT_QA.I",
        provider_attempt_id="provider-attempt-02",
        session_id="019f929b-bea9-76a2-955d-5991618b6f35",
        raw_name="raw/provider-attempt-02.jsonl",
    )

    rows = metering.validate_receipt_join(
        [first_path, second_path],
        [
            _expected_call(),
            _expected_call(
                call_slot_id="PRODUCT_QA.I",
                provider_attempt_id="provider-attempt-02",
            ),
        ],
        evidence_root=tmp_path,
    )

    assert [row["call_slot_id"] for row in rows] == [
        "DIRECT.I",
        "PRODUCT_QA.I",
    ]

    second = json.loads(second_path.read_text())
    for field in ("call_slot_id", "provider_attempt_id", "session_id"):
        tampered = copy.deepcopy(second)
        tampered[field] = json.loads(first_path.read_text())[field]
        second_path.write_bytes(metering.canonical_json_bytes(tampered))
        with pytest.raises(metering.MeteringError, match="^receipt_join_duplicate"):
            metering.validate_receipt_join(
                [first_path, second_path],
                [
                    _expected_call(),
                    _expected_call(
                        call_slot_id="PRODUCT_QA.I",
                        provider_attempt_id="provider-attempt-02",
                    ),
                ],
                evidence_root=tmp_path,
            )
        second_path.write_bytes(metering.canonical_json_bytes(second))


def test_validate_receipt_join_reports_a_missing_evidence_root(
    tmp_path: Path,
) -> None:
    receipt_path, _ = _receipt(tmp_path)
    expected_calls = [_expected_call()]
    assert len(
        metering.validate_receipt_join(
            [receipt_path],
            expected_calls,
            evidence_root=tmp_path,
        )
    ) == 1

    missing_root = tmp_path / "missing-evidence-root"
    with pytest.raises(
        metering.MeteringError,
        match=(
            "^receipt_evidence_root_unreadable: "
            + re.escape(str(missing_root))
            + "$"
        ),
    ):
        metering.validate_receipt_join(
            [receipt_path],
            expected_calls,
            evidence_root=missing_root,
        )


def test_validate_receipt_join_reports_a_missing_bound_raw_jsonl(
    tmp_path: Path,
) -> None:
    receipt_path, _ = _receipt(tmp_path)
    expected_calls = [_expected_call()]
    assert len(
        metering.validate_receipt_join(
            [receipt_path],
            expected_calls,
            evidence_root=tmp_path,
        )
    ) == 1

    (tmp_path / "raw/provider-attempt-01.jsonl").unlink()
    with pytest.raises(
        metering.MeteringError,
        match=r"^receipt_raw_unreadable: raw/provider-attempt-01\.jsonl$",
    ):
        metering.validate_receipt_join(
            [receipt_path],
            expected_calls,
            evidence_root=tmp_path,
        )


def test_validate_receipt_join_covers_frozen_role_catalog_and_rejects_role_tamper(
    tmp_path: Path,
) -> None:
    call_slots = (
        "DIRECT.I",
        "DESIGN_QA.D",
        "DESIGN_QA.DR",
        "DESIGN_QA.DREV",
        "DESIGN_QA.I",
        "PRODUCT_QA.I",
        "PRODUCT_QA.PR",
        "PRODUCT_QA.FIX",
        "RICH.D",
        "RICH.DR",
        "RICH.DREV",
        "RICH.I",
        "RICH.PR",
        "RICH.FIX",
        "EVAL.SCORER_DIRECT",
        "EVAL.SCORER_DESIGN_QA",
        "EVAL.SCORER_PRODUCT_QA",
        "EVAL.SCORER_RICH",
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
        "EVAL.ADJUDICATOR",
        "EVAL.INTEGRATED_REVIEW",
    )
    receipt_paths: list[Path] = []
    expected_calls: list[dict[str, object]] = []
    for index, call_slot_id in enumerate(call_slots, start=1):
        role_id = call_slot_id.partition(".")[2]
        provider_attempt_id = f"provider-attempt-{index:02d}"
        receipt_path, _ = _receipt(
            tmp_path,
            role_id=role_id,
            call_slot_id=call_slot_id,
            provider_attempt_id=provider_attempt_id,
            session_id=f"019f929b-bea9-76a2-955d-5991618b6f{index:02d}",
            raw_name=f"raw/{provider_attempt_id}.jsonl",
        )
        receipt_paths.append(receipt_path)
        expected_calls.append(
            _expected_call(
                role_id=role_id,
                call_slot_id=call_slot_id,
                provider_attempt_id=provider_attempt_id,
            )
        )

    rows = metering.validate_receipt_join(
        receipt_paths,
        expected_calls,
        evidence_root=tmp_path,
    )

    assert {
        (str(row["call_slot_id"]), str(row["role_id"])) for row in rows
    } == {(call_slot_id, call_slot_id.partition(".")[2]) for call_slot_id in call_slots}
    assert len(rows) == 22
    assert len({row["role_id"] for row in rows}) == 14

    role_tamper = copy.deepcopy(expected_calls)
    role_tamper[0]["role_id"] = "WRONG_ROLE"
    with pytest.raises(
        metering.MeteringError,
        match=r"^receipt_join_binding_mismatch: DIRECT\.I\.role_id$",
    ):
        metering.validate_receipt_join(
            receipt_paths,
            role_tamper,
            evidence_root=tmp_path,
        )


@pytest.mark.parametrize("digest_field", ["launcher_sha256", "interpreter_sha256"])
def test_validate_receipt_join_rejects_correct_version_with_wrong_chain_digest(
    tmp_path: Path,
    digest_field: str,
) -> None:
    receipt_path, record = _receipt(tmp_path)
    altered = copy.deepcopy(record)
    altered["executable_chain"][digest_field] = _sha("a")
    assert altered["executable_chain"]["version"] == "codex-cli 0.145.0"
    receipt_path.write_bytes(metering.canonical_json_bytes(altered))

    with pytest.raises(metering.MeteringError, match="^receipt_join_binding_mismatch"):
        metering.validate_receipt_join(
            [receipt_path],
            [_expected_call()],
            evidence_root=tmp_path,
        )


@pytest.mark.parametrize(
    "tamper",
    [
        lambda record: record.update(prompt_sha256=_sha("9")),
        lambda record: record["usage"].update(reported_total_tokens=999),
        lambda record: record["raw_jsonl"].update(bytes=1),
        lambda record: record["terminal_event"].update(line=3),
        _tamper_process_flags,
        lambda record: record.update(unexpected=True),
    ],
)
def test_validate_receipt_join_rejects_every_binding_tamper(
    tmp_path: Path,
    tamper: object,
) -> None:
    receipt_path, record = _receipt(tmp_path)
    altered = copy.deepcopy(record)
    tamper(altered)  # type: ignore[operator]
    receipt_path.write_bytes(metering.canonical_json_bytes(altered))

    with pytest.raises(metering.MeteringError):
        metering.validate_receipt_join(
            [receipt_path],
            [_expected_call()],
            evidence_root=tmp_path,
        )


def test_validate_receipt_join_rejects_noncanonical_duplicate_and_bad_utf8(
    tmp_path: Path,
) -> None:
    receipt_path, record = _receipt(tmp_path)
    canonical = receipt_path.read_bytes()
    variants = [
        json.dumps(record, indent=2).encode() + b"\n",
        canonical.replace(b'{"block_id"', b'{"block_id":"BLOCK-01","block_id"'),
        b"\xff" + canonical,
    ]
    for raw in variants:
        receipt_path.write_bytes(raw)
        with pytest.raises(metering.MeteringError):
            metering.validate_receipt_join(
                [receipt_path],
                [_expected_call()],
                evidence_root=tmp_path,
            )


def test_normalize_codex_argv_injects_one_json_flag_and_preserves_required_flags() -> None:
    argv = metering.normalize_codex_argv(
        [
            "/opt/codex/bin/codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "bounded task",
        ]
    )
    assert argv.count("--json") == 1
    assert argv[:3] == (
        "/opt/codex/bin/codex",
        "exec",
        "--json",
    )
    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    assert "--skip-git-repo-check" in argv


def test_normalize_codex_argv_preserves_prompt_arguments_after_inner_separator() -> None:
    prompt = ("resume", "this", "ordinary task")
    argv = metering.normalize_codex_argv(
        [
            "/opt/codex/bin/codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--",
            *prompt,
        ]
    )

    separator = argv.index("--")
    assert argv[separator + 1 :] == prompt
    assert argv[2:separator].count("--json") == 1


def test_installed_0145_launcher_resolves_to_the_factual_plan_digest() -> None:
    chain = metering.resolve_executable_chain(
        "/home/ollie/.nvm/versions/node/v20.19.4/bin/codex"
    )
    assert chain["version"] == "codex-cli 0.145.0"
    assert chain["launcher_path"] == (
        "/home/ollie/.nvm/versions/node/v20.19.4/lib/node_modules/"
        "@openai/codex/bin/codex.js"
    )
    assert chain["launcher_sha256"] == (
        "sha256:134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477"
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["codex", "exec", "task"],
        ["codex", "exec", "--json", "--json", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "task"],
        ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "task"],
        ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--", "--skip-git-repo-check", "task"],
        ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--", "--json", "task"],
        ["codex", "exec", "resume", "session", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"],
        ["codex", "resume", "session", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"],
    ],
)
def test_normalize_codex_argv_rejects_flag_drift_and_resume(argv: list[str]) -> None:
    with pytest.raises(metering.MeteringError, match="^codex_argv_invalid"):
        metering.normalize_codex_argv(argv)
