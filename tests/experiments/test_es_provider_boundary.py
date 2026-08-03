from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments.es import provider_boundary
from scripts.experiments.es import metering


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_fake_codex(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import sys

marker = Path(os.environ["ES_TEST_CHILD_MARKER"])
marker.parent.mkdir(parents=True, exist_ok=True)
marker.write_text("started\\n", encoding="utf-8")
if sys.argv[1:] == ["--version"]:
    print(os.environ.get("ES_TEST_CODEX_VERSION", "codex-cli 0.145.0"))
    raise SystemExit(0)

prompt = sys.stdin.buffer.read()
rows = [json.loads(line) for line in Path(os.environ["ES_TEST_JOURNAL"]).read_text(encoding="utf-8").splitlines()]
prompt_sha = "sha256:" + hashlib.sha256(prompt).hexdigest()
slot = os.environ["ES_TEST_PROMPT_TO_SLOT_" + prompt.decode("ascii").upper()]
if not any(row["call_slot_id"] == slot for row in rows):
    raise SystemExit(91)
observation = Path(os.environ["ES_TEST_OBSERVATIONS"]) / (prompt.decode("ascii") + ".json")
observation.parent.mkdir(parents=True, exist_ok=True)
observation.write_text(json.dumps({"prompt_sha256": prompt_sha, "slots": [row["call_slot_id"] for row in rows]}, sort_keys=True), encoding="utf-8")
session = "session-" + hashlib.sha256(prompt).hexdigest()[:16]
events = [
    {"type": "thread.started", "thread_id": session},
    {"type": "turn.started"},
    {"type": "turn.completed", "usage": {"input_tokens": 3, "cached_input_tokens": 1, "cache_write_input_tokens": 0, "output_tokens": 2, "reasoning_output_tokens": 1}},
]
for event in events:
    print(json.dumps(event, separators=(",", ":")))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path.resolve()


def _metered(real_codex: Path) -> tuple[str, ...]:
    return (
        str(real_codex),
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.5",
        "--config",
        "model_reasoning_effort=high",
        "--",
        "-",
    )


def _outer() -> tuple[str, ...]:
    return (
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.5",
        "--config",
        "reasoning_effort=high",
    )


def _call(
    *,
    slot: str,
    prompt: bytes,
    cwd: Path,
    real_codex: Path,
) -> provider_boundary.BoundaryCall:
    return provider_boundary.BoundaryCall(
        call_slot_id=slot,
        role_id=slot,
        cwd_selector=provider_boundary.CwdSelector.exact(cwd.resolve()),
        prompt_sha256=_sha(prompt),
        contract_sha256=SHA_B,
        outer_argv=_outer(),
        metered_argv=_metered(real_codex),
        static_call_sha256=SHA_C,
        provider_attempt_id="provider-" + slot.lower().replace(".", "-"),
        raw_jsonl_path="raw/" + slot.lower().replace(".", "-") + ".jsonl",
        receipt_path="receipts/" + slot.lower().replace(".", "-") + ".json",
        expected_session_id=None,
    )


def _manifest(
    tmp_path: Path,
    calls: tuple[provider_boundary.BoundaryCall, ...],
) -> provider_boundary.BoundaryManifest:
    evidence = (tmp_path / "evidence").resolve()
    evidence.mkdir(exist_ok=True)
    return provider_boundary.BoundaryManifest(
        study_id="F1-ES",
        attempt_id="ES-ATTEMPT-01",
        decision_lock_sha256=SHA_A,
        evidence_root=evidence,
        journal_path=evidence / "call-allocations.jsonl",
        settlement_journal_path=evidence / "call-settlements.jsonl",
        calls=calls,
    )


def _receipt_bytes(
    *,
    attempt_id: str,
    call_slot_id: str,
    exit_status: int = 0,
) -> bytes:
    return metering.canonical_json_bytes(
        {
            "block_id": attempt_id,
            "call_slot_id": call_slot_id,
            "exit_status": exit_status,
        }
    )


def _invoke(
    *,
    shim: Path,
    cwd: Path,
    prompt: bytes,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            str(shim),
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--model",
            "gpt-5.5",
            "--config",
            "reasoning_effort=high",
        ],
        cwd=cwd,
        env=environment,
        input=prompt,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_manifest_is_closed_immutable_and_content_addressed(tmp_path: Path) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )

    with pytest.raises(FrozenInstanceError):
        manifest.attempt_id = "changed"  # type: ignore[misc]

    publication = provider_boundary.write_manifest_exclusive(
        (tmp_path / "boundary.json").resolve(), manifest
    )
    assert publication.sha256 == manifest.sha256
    assert manifest.settlement_journal_path == (
        manifest.evidence_root / "call-settlements.jsonl"
    )
    assert provider_boundary.load_manifest(
        publication.path, expected_sha256=publication.sha256
    ) == manifest

    publication.path.chmod(0o600)
    publication.path.write_bytes(publication.path.read_bytes().replace(b"DIRECT", b"ALTERED"))
    with pytest.raises(provider_boundary.ProviderBoundaryError, match="manifest_digest"):
        provider_boundary.load_manifest(
            publication.path, expected_sha256=publication.sha256
        )


def test_resolution_fails_closed_on_absent_or_ambiguous_slot(tmp_path: Path) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    one = _call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real)
    manifest = _manifest(tmp_path, (one,))

    with pytest.raises(provider_boundary.ProviderBoundaryError, match="call_absent"):
        provider_boundary.resolve_call(
            manifest,
            cwd=cwd,
            prompt=b"different",
            argv=one.outer_argv,
        )

    ambiguous = _manifest(
        tmp_path,
        (
            one,
            replace(
                one,
                call_slot_id="RICH.I",
                provider_attempt_id="provider-rich",
                raw_jsonl_path="raw/rich-i.jsonl",
                receipt_path="receipts/rich-i.json",
            ),
        ),
    )
    with pytest.raises(provider_boundary.ProviderBoundaryError, match="call_ambiguous"):
        provider_boundary.resolve_call(
            ambiguous,
            cwd=cwd,
            prompt=b"alpha",
            argv=one.outer_argv,
        )


def test_settlement_publication_is_canonical_chained_and_allocation_bound(
    tmp_path: Path,
) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    allocation = provider_boundary.publish_allocation(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
        call_slot_id="DIRECT.I",
        static_call_sha256=SHA_C,
    )
    receipt = _receipt_bytes(
        attempt_id=manifest.attempt_id,
        call_slot_id="DIRECT.I",
        exit_status=7,
    )

    settlement = provider_boundary.publish_settlement(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        allocation=allocation,
        receipt_bytes=receipt,
        elapsed_ms=37,
    )

    assert settlement.sequence == 1
    assert settlement.previous_settlement_sha256 is None
    assert settlement.call_slot_id == "DIRECT.I"
    assert settlement.allocation_sha256 == allocation.sha256
    assert settlement.attempt_id == manifest.attempt_id
    assert settlement.decision_lock_sha256 == manifest.decision_lock_sha256
    assert settlement.static_call_sha256 == SHA_C
    assert settlement.exit_status == 7
    assert settlement.receipt_sha256 == _sha(receipt)
    assert settlement.elapsed_ms == 37
    assert settlement.record["settlement_sha256"] == settlement.sha256
    assert provider_boundary.load_settlement_journal(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
    ) == (settlement,)


def test_settlement_loader_rejects_tamper_missing_allocation_and_duplicate(
    tmp_path: Path,
) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    allocation = provider_boundary.publish_allocation(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
        call_slot_id="DIRECT.I",
        static_call_sha256=SHA_C,
    )
    receipt = _receipt_bytes(
        attempt_id=manifest.attempt_id,
        call_slot_id="DIRECT.I",
    )
    provider_boundary.publish_settlement(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        allocation=allocation,
        receipt_bytes=receipt,
        elapsed_ms=37,
    )

    with pytest.raises(provider_boundary.ProviderBoundaryError, match="duplicate"):
        provider_boundary.publish_settlement(
            manifest.settlement_journal_path,
            allocation_journal_path=manifest.journal_path,
            allocation=allocation,
            receipt_bytes=receipt,
            elapsed_ms=38,
        )

    row = json.loads(manifest.settlement_journal_path.read_text(encoding="utf-8"))
    row["elapsed_ms"] = 999
    manifest.settlement_journal_path.write_bytes(metering.canonical_json_bytes(row))
    with pytest.raises(
        provider_boundary.ProviderBoundaryError,
        match="settlement_journal_invalid",
    ):
        provider_boundary.load_settlement_journal(
            manifest.settlement_journal_path,
            allocation_journal_path=manifest.journal_path,
            attempt_id=manifest.attempt_id,
            decision_lock_sha256=manifest.decision_lock_sha256,
        )

    missing_path = manifest.evidence_root / "missing-settlements.jsonl"
    unrecorded = replace(
        allocation,
        call_slot_id="EVAL.UNRECORDED",
        static_call_sha256=SHA_D,
    )
    with pytest.raises(
        provider_boundary.ProviderBoundaryError,
        match="settlement_allocation_missing",
    ):
        provider_boundary.publish_settlement(
            missing_path,
            allocation_journal_path=manifest.journal_path,
            allocation=unrecorded,
            receipt_bytes=_receipt_bytes(
                attempt_id=manifest.attempt_id,
                call_slot_id="EVAL.UNRECORDED",
            ),
            elapsed_ms=1,
        )
    assert missing_path.read_bytes() == b""


def test_settlement_crosscheck_waits_for_inflight_allocation_write(
    tmp_path: Path,
) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    allocation = provider_boundary.publish_allocation(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
        call_slot_id="DIRECT.I",
        static_call_sha256=SHA_C,
    )
    settlement = provider_boundary.publish_settlement(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        allocation=allocation,
        receipt_bytes=_receipt_bytes(
            attempt_id=manifest.attempt_id,
            call_slot_id=allocation.call_slot_id,
        ),
        elapsed_ms=1,
    )
    descriptor = os.open(manifest.journal_path, os.O_RDONLY)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                provider_boundary.load_settlement_journal,
                manifest.settlement_journal_path,
                allocation_journal_path=manifest.journal_path,
                attempt_id=manifest.attempt_id,
                decision_lock_sha256=manifest.decision_lock_sha256,
            )
            with pytest.raises(TimeoutError):
                pending.result(timeout=0.1)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            assert pending.result(timeout=1) == (settlement,)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def test_outer_and_inner_argv_drift_fail_independently(tmp_path: Path) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    call = _call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real)
    manifest = _manifest(tmp_path, (call,))

    with pytest.raises(provider_boundary.ProviderBoundaryError, match="call_absent"):
        provider_boundary.resolve_call(
            manifest,
            cwd=cwd,
            prompt=b"alpha",
            argv=(*call.outer_argv[:-1], "model_reasoning_effort=high"),
        )

    with pytest.raises(provider_boundary.ProviderBoundaryError, match="metered_argv"):
        replace(
            call,
            metered_argv=(*call.metered_argv[:-3], "reasoning_effort=high", "--", "-"),
        )


def test_wrapper_publishes_before_child_and_delegates_to_metering(tmp_path: Path) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    publication = provider_boundary.write_manifest_exclusive(
        (tmp_path / "boundary.json").resolve(), manifest
    )
    shim = provider_boundary.install_path_shim((tmp_path / "shim").resolve())
    environment = os.environ.copy()
    environment.update(
        provider_boundary.boundary_environment(
            shim_dir=shim.parent,
            manifest=publication,
            inherited_path=environment["PATH"],
        )
    )
    environment.update(
        {
            "ES_TEST_CHILD_MARKER": str(tmp_path / "child-started"),
            "ES_TEST_JOURNAL": str(manifest.journal_path),
            "ES_TEST_OBSERVATIONS": str(tmp_path / "observations"),
            "ES_TEST_PROMPT_TO_SLOT_ALPHA": "DIRECT.I",
        }
    )

    completed = _invoke(
        shim=shim,
        cwd=cwd,
        prompt=b"alpha",
        environment=environment,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    rows = provider_boundary.load_allocation_journal(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
    )
    assert [row.call_slot_id for row in rows] == ["DIRECT.I"]
    assert (manifest.evidence_root / "raw/direct-i.jsonl").is_file()
    assert (manifest.evidence_root / "receipts/direct-i.json").is_file()
    observation = json.loads((tmp_path / "observations/alpha.json").read_text())
    assert observation == {"prompt_sha256": _sha(b"alpha"), "slots": ["DIRECT.I"]}


def test_boundary_settles_after_receipt_with_monotonic_elapsed_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    publication = provider_boundary.write_manifest_exclusive(
        (tmp_path / "boundary.json").resolve(), manifest
    )
    monkeypatch.setenv("ES_TEST_CHILD_MARKER", str(tmp_path / "child-started"))
    monkeypatch.setenv("ES_TEST_JOURNAL", str(manifest.journal_path))
    monkeypatch.setenv("ES_TEST_OBSERVATIONS", str(tmp_path / "observations"))
    monkeypatch.setenv("ES_TEST_PROMPT_TO_SLOT_ALPHA", "DIRECT.I")

    actual_publish = provider_boundary.publish_settlement
    publication_observations: list[tuple[bool, bool]] = []

    def checked_publish(
        path: Path,
        **kwargs: object,
    ) -> provider_boundary.SettlementEvent:
        publication_observations.append(
            (
                (manifest.evidence_root / "raw/direct-i.jsonl").is_file(),
                (manifest.evidence_root / "receipts/direct-i.json").is_file(),
            )
        )
        return actual_publish(path, **kwargs)  # type: ignore[arg-type]

    clock = iter((10_000_000_000, 10_237_999_999))
    monkeypatch.setattr(provider_boundary.time, "monotonic_ns", lambda: next(clock))
    monkeypatch.setattr(provider_boundary, "publish_settlement", checked_publish)

    execution = provider_boundary.execute_boundary(
        argv=_outer(),
        prompt=b"alpha",
        cwd=cwd,
        environ={
            provider_boundary.MANIFEST_PATH_ENV: str(publication.path),
            provider_boundary.MANIFEST_SHA256_ENV: publication.sha256,
        },
    )

    assert publication_observations == [(True, True)]
    assert execution.settlement.elapsed_ms == 237
    assert execution.settlement.exit_status == execution.exit_status == 0
    assert execution.settlement.receipt_sha256 == _sha(execution.receipt_bytes)
    assert provider_boundary.load_settlement_journal(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
    ) == (execution.settlement,)


def test_concurrent_treatment_and_scorer_calls_form_one_chain(tmp_path: Path) -> None:
    direct_cwd = (tmp_path / "direct").resolve()
    scorer_cwd = (tmp_path / "scorer").resolve()
    direct_cwd.mkdir()
    scorer_cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    calls = (
        _call(slot="DIRECT.I", prompt=b"alpha", cwd=direct_cwd, real_codex=real),
        _call(
            slot="EVAL.SCORER_DIRECT",
            prompt=b"beta",
            cwd=scorer_cwd,
            real_codex=real,
        ),
    )
    manifest = _manifest(tmp_path, calls)
    publication = provider_boundary.write_manifest_exclusive(
        (tmp_path / "boundary.json").resolve(), manifest
    )
    shim = provider_boundary.install_path_shim((tmp_path / "shim").resolve())
    environment = os.environ.copy()
    environment.update(
        provider_boundary.boundary_environment(
            shim_dir=shim.parent,
            manifest=publication,
            inherited_path=environment["PATH"],
        )
    )
    environment.update(
        {
            "ES_TEST_CHILD_MARKER": str(tmp_path / "child-started"),
            "ES_TEST_JOURNAL": str(manifest.journal_path),
            "ES_TEST_OBSERVATIONS": str(tmp_path / "observations"),
            "ES_TEST_PROMPT_TO_SLOT_ALPHA": "DIRECT.I",
            "ES_TEST_PROMPT_TO_SLOT_BETA": "EVAL.SCORER_DIRECT",
        }
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(
                _invoke,
                shim=shim,
                cwd=direct_cwd,
                prompt=b"alpha",
                environment=environment,
            ),
            pool.submit(
                _invoke,
                shim=shim,
                cwd=scorer_cwd,
                prompt=b"beta",
                environment=environment,
            ),
        )
        results = tuple(future.result() for future in futures)

    assert [result.returncode for result in results] == [0, 0]
    rows = provider_boundary.load_allocation_journal(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
    )
    assert [row.sequence for row in rows] == [1, 2]
    assert {row.call_slot_id for row in rows} == {
        "DIRECT.I",
        "EVAL.SCORER_DIRECT",
    }
    assert rows[0].previous_allocation_sha256 is None
    assert rows[1].previous_allocation_sha256 == rows[0].sha256
    settlements = provider_boundary.load_settlement_journal(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
    )
    assert [row.sequence for row in settlements] == [1, 2]
    assert {row.call_slot_id for row in settlements} == {
        "DIRECT.I",
        "EVAL.SCORER_DIRECT",
    }
    assert settlements[0].previous_settlement_sha256 is None
    assert settlements[1].previous_settlement_sha256 == settlements[0].sha256
    allocations_by_slot = {row.call_slot_id: row for row in rows}
    assert all(
        row.allocation_sha256 == allocations_by_slot[row.call_slot_id].sha256
        for row in settlements
    )

    review = provider_boundary.publish_allocation(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
        call_slot_id="EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        static_call_sha256=SHA_D,
    )
    continued = provider_boundary.load_allocation_journal(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
    )
    assert review.sequence == 3
    assert review.previous_allocation_sha256 == rows[-1].sha256
    assert continued[-1] == review
    review_settlement = provider_boundary.publish_settlement(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        allocation=review,
        receipt_bytes=_receipt_bytes(
            attempt_id=manifest.attempt_id,
            call_slot_id=review.call_slot_id,
        ),
        elapsed_ms=11,
    )
    assert review_settlement.sequence == 3
    assert review_settlement.previous_settlement_sha256 == settlements[-1].sha256


def test_allocation_publication_failure_starts_no_provider_process(tmp_path: Path) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    manifest.journal_path.write_bytes(b"not-json\n")
    publication = provider_boundary.write_manifest_exclusive(
        (tmp_path / "boundary.json").resolve(), manifest
    )
    shim = provider_boundary.install_path_shim((tmp_path / "shim").resolve())
    environment = os.environ.copy()
    environment.update(
        provider_boundary.boundary_environment(
            shim_dir=shim.parent,
            manifest=publication,
            inherited_path=environment["PATH"],
        )
    )
    marker = tmp_path / "child-started"
    environment.update(
        {
            "ES_TEST_CHILD_MARKER": str(marker),
            "ES_TEST_JOURNAL": str(manifest.journal_path),
            "ES_TEST_OBSERVATIONS": str(tmp_path / "observations"),
            "ES_TEST_PROMPT_TO_SLOT_ALPHA": "DIRECT.I",
        }
    )

    completed = _invoke(
        shim=shim,
        cwd=cwd,
        prompt=b"alpha",
        environment=environment,
    )

    assert completed.returncode != 0
    assert b"allocation_journal" in completed.stderr
    assert not marker.exists()
    assert not manifest.settlement_journal_path.exists()


def test_settlement_publication_failure_is_not_reported_as_boundary_success(
    tmp_path: Path,
) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    manifest.settlement_journal_path.write_bytes(b"not-json\n")
    publication = provider_boundary.write_manifest_exclusive(
        (tmp_path / "boundary.json").resolve(), manifest
    )
    shim = provider_boundary.install_path_shim((tmp_path / "shim").resolve())
    environment = os.environ.copy()
    environment.update(
        provider_boundary.boundary_environment(
            shim_dir=shim.parent,
            manifest=publication,
            inherited_path=environment["PATH"],
        )
    )
    marker = tmp_path / "child-started"
    environment.update(
        {
            "ES_TEST_CHILD_MARKER": str(marker),
            "ES_TEST_JOURNAL": str(manifest.journal_path),
            "ES_TEST_OBSERVATIONS": str(tmp_path / "observations"),
            "ES_TEST_PROMPT_TO_SLOT_ALPHA": "DIRECT.I",
        }
    )

    completed = _invoke(
        shim=shim,
        cwd=cwd,
        prompt=b"alpha",
        environment=environment,
    )

    assert completed.returncode == 70
    assert b"settlement_journal_invalid" in completed.stderr
    assert marker.is_file()
    assert (manifest.evidence_root / "raw/direct-i.jsonl").is_file()
    assert (manifest.evidence_root / "receipts/direct-i.json").is_file()
    assert manifest.settlement_journal_path.read_bytes() == b"not-json\n"


def test_prelaunch_metering_failure_publishes_no_bogus_settlement(
    tmp_path: Path,
) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    publication = provider_boundary.write_manifest_exclusive(
        (tmp_path / "boundary.json").resolve(), manifest
    )
    shim = provider_boundary.install_path_shim((tmp_path / "shim").resolve())
    environment = os.environ.copy()
    environment.update(
        provider_boundary.boundary_environment(
            shim_dir=shim.parent,
            manifest=publication,
            inherited_path=environment["PATH"],
        )
    )
    marker = tmp_path / "child-started"
    environment.update(
        {
            "ES_TEST_CHILD_MARKER": str(marker),
            "ES_TEST_JOURNAL": str(manifest.journal_path),
            "ES_TEST_OBSERVATIONS": str(tmp_path / "observations"),
            "ES_TEST_PROMPT_TO_SLOT_ALPHA": "DIRECT.I",
            "ES_TEST_CODEX_VERSION": "unexpected-version",
        }
    )

    completed = _invoke(
        shim=shim,
        cwd=cwd,
        prompt=b"alpha",
        environment=environment,
    )

    assert completed.returncode == 70
    assert b"provider_boundary_metering_failed" in completed.stderr
    assert marker.is_file()
    assert [
        row.call_slot_id
        for row in provider_boundary.load_allocation_journal(
            manifest.journal_path,
            attempt_id=manifest.attempt_id,
            decision_lock_sha256=manifest.decision_lock_sha256,
        )
    ] == ["DIRECT.I"]
    assert not manifest.settlement_journal_path.exists()
    assert not (manifest.evidence_root / "receipts/direct-i.json").exists()


def test_path_environment_is_exact_and_does_not_offer_resume(tmp_path: Path) -> None:
    manifest_path = (tmp_path / "manifest.json").resolve()
    publication = provider_boundary.ManifestPublication(manifest_path, SHA_D)
    shim_dir = (tmp_path / "shim").resolve()
    values = provider_boundary.boundary_environment(
        shim_dir=shim_dir,
        manifest=publication,
        inherited_path="/usr/bin:/bin",
    )

    assert values == {
        "PATH": f"{shim_dir}:/usr/bin:/bin",
        provider_boundary.MANIFEST_PATH_ENV: str(manifest_path),
        provider_boundary.MANIFEST_SHA256_ENV: SHA_D,
    }
    assert not any("resume" in value.lower() for value in values.values())
    assert sys.executable not in values.values()


def test_first_publications_fsync_file_and_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = (tmp_path / "candidate").resolve()
    cwd.mkdir()
    real = _write_fake_codex((tmp_path / "real-codex").resolve())
    manifest = _manifest(
        tmp_path,
        (_call(slot="DIRECT.I", prompt=b"alpha", cwd=cwd, real_codex=real),),
    )
    observed_modes: list[int] = []
    real_fsync = os.fsync

    def tracked_fsync(descriptor: int) -> None:
        observed_modes.append(os.fstat(descriptor).st_mode)
        real_fsync(descriptor)

    monkeypatch.setattr(provider_boundary.os, "fsync", tracked_fsync)

    provider_boundary.write_manifest_exclusive(
        (tmp_path / "manifest/boundary.json").resolve(), manifest
    )
    provider_boundary.install_path_shim((tmp_path / "shim").resolve())
    allocation = provider_boundary.publish_allocation(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
        call_slot_id="DIRECT.I",
        static_call_sha256=SHA_C,
    )
    provider_boundary.publish_settlement(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        allocation=allocation,
        receipt_bytes=_receipt_bytes(
            attempt_id=manifest.attempt_id,
            call_slot_id=allocation.call_slot_id,
        ),
        elapsed_ms=1,
    )

    assert sum(stat.S_ISREG(mode) for mode in observed_modes) == 4
    assert sum(stat.S_ISDIR(mode) for mode in observed_modes) == 4
