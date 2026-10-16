"""Concrete evaluated phased bindings: captured bytes and safe candidate ownership."""

from dataclasses import replace
from hashlib import sha256

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.workflow_evaluated_phased_helpers import public_phased_cleanup, checked_request


def _candidates(tmp_path):
    from orchestrator.workflow.evaluated.phased_providers import PhasedCandidates
    from orchestrator.workflow.evaluated.providers import resolve_provider_input
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    node, operands, _, reader = checked_request(tmp_path)
    workspace = WorkspaceFiles(tmp_path)
    attempt = workspace.mkdir_exclusive("run/attempt")
    resolved = resolve_provider_input(node, operands, workspace=tmp_path,
        reader=reader, result_path="run/attempt/result.json", delivery_name="file/1")
    candidates = PhasedCandidates(node, resolved, workspace_files=workspace,
        attempt_files=attempt, result_path="run/attempt/result.json",
        runtime_owned_roots=(tmp_path / "run",))
    return candidates


def test_candidate_snapshot_validates_both_contracts_from_captured_bytes(tmp_path):
    candidates = _candidates(tmp_path)
    preflight = candidates.preflight()
    (tmp_path / "outputs/report.md").write_text("original\n")
    (tmp_path / "run/attempt/result.json").write_bytes(b'{"approved":true}\n')
    snapshot = candidates.snapshot(preflight, 1)
    (tmp_path / "outputs/report.md").write_bytes(b'\xff')
    (tmp_path / "run/attempt/result.json").write_bytes(b'invalid')
    assert candidates.validate_outputs(snapshot).valid
    assert candidates.validate_result(snapshot).valid
    with pytest.raises((OSError, ValueError)):
        candidates.freeze(snapshot)


@pytest.mark.parametrize("kind", ["preexisting", "symlink", "traversal", "alias", "runtime", "noncanonical"])
def test_candidate_preflight_refuses_unsafe_or_owned_destinations(tmp_path, kind):
    candidates = _candidates(tmp_path)
    expected = candidates.resolved.expected_outputs
    if kind == "preexisting":
        (tmp_path / "outputs").mkdir()
        (tmp_path / "outputs/report.md").write_text("preserve")
    elif kind == "symlink":
        (tmp_path / "outputs").symlink_to(tmp_path / "docs", target_is_directory=True)
    elif kind == "traversal":
        expected[0]["path"] = "outputs/../report.md"
    elif kind == "alias":
        expected[0]["path"] = "run/attempt/result.json"
    elif kind == "runtime":
        expected[0]["path"] = "run/memo.jsonl"
    else:
        expected[0]["path"] = "outputs//report.md"
    with pytest.raises((OSError, ValueError)):
        candidates.preflight()
    if kind == "preexisting":
        assert (tmp_path / "outputs/report.md").read_text() == "preserve"


def test_candidate_reset_only_removes_stable_owned_regular_files(tmp_path):
    candidates = _candidates(tmp_path)
    preflight = candidates.preflight()
    report = tmp_path / "outputs/report.md"
    report.write_text("invalid submission")
    (tmp_path / "outputs/unrelated").write_text("preserve")
    snapshot = candidates.snapshot(preflight, 1)
    candidates.reset(snapshot)
    assert not report.exists()
    assert (tmp_path / "outputs/unrelated").read_text() == "preserve"
    report.write_text("invalid submission")
    snapshot = candidates.snapshot(preflight, 2)
    report.unlink()
    report.symlink_to(tmp_path / "outputs/unrelated")
    with pytest.raises((OSError, ValueError)):
        candidates.reset(snapshot)
    assert report.is_symlink()


def test_frozen_restore_retains_complete_snapshot_after_natural_shutdown(tmp_path):
    candidates = _candidates(tmp_path)
    preflight = candidates.preflight()
    report = tmp_path / "outputs/report.md"
    result = tmp_path / "run/attempt/result.json"
    report.write_bytes("resultado ñ\r\n".encode())
    result.write_bytes(b'{"approved": true}\n')
    snapshot = candidates.snapshot(preflight, 1)
    frozen = candidates.freeze(snapshot)
    report.write_text("late provider write")
    result.unlink()
    restoration = candidates.restore(frozen)
    assert candidates.verify(frozen, restoration).verified
    assert report.read_bytes() == frozen.files[0].content
    assert result.read_bytes() == frozen.files[1].content


def test_concrete_bindings_persist_intent_before_adapter_start(tmp_path):
    import json
    import tempfile
    import time
    from orchestrator.workflow.evaluated.phased_providers import EvaluatedPhasedBindings
    from tests.workflow_evaluated_phased_helpers import external_attempt
    attempt = external_attempt(tmp_path)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        bindings = EvaluatedPhasedBindings(attempt, deadline=time.monotonic() + 20,
            transport_root=__import__("pathlib").Path(root))
        allocation = bindings.allocate_attempt()
        composition = bindings.compose_attempt(allocation, deadline=bindings.deadline)
        preflight = bindings.preflight_candidates(composition)
        receipt = json.loads(attempt.attempt_files.read("phased-attempt.json"))
        assert receipt["state"] == "intent"
        assert receipt["identity"] == attempt.identity
        assert receipt["attempt"] == attempt.ordinal
        assert receipt["result_path"] == attempt.result_path
        assert receipt["candidates"] == [row.to_dict() for row in preflight.bindings]
        assert "root" not in receipt["transport"]
        assert bindings.prestart_no_backend_allocation_proof().proof_complete
        assert composition.invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == str(
            attempt.attempt_files.workspace / "result.json")
        assert composition.cut.canonical_composed == attempt.resolved.prompt.encode()
        assert composition.invocation.resolved_command[-1].encode() == composition.task_turn.delivered_turn
        bindings.candidates.close()


def test_concrete_bindings_reject_capability_absence_before_backend_start(tmp_path):
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import EvaluatedPhasedBindings
    from orchestrator.workflow.provider_phased_delivery.bindings import PhasedOperationFailure
    from tests.workflow_evaluated_phased_helpers import external_attempt
    attempt = external_attempt(tmp_path)
    template = attempt.provider_executor.registry.get("test-provider")
    attempt.provider_executor.registry.register(replace(template, interactive_session_support=None))
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        bindings = EvaluatedPhasedBindings(attempt, deadline=time.monotonic() + 20, transport_root=Path(root))
        with pytest.raises(PhasedOperationFailure):
            bindings.compose_attempt(bindings.allocate_attempt(), deadline=bindings.deadline)
        assert not attempt.attempt_files.exists("phased-attempt.json")


@pytest.mark.parametrize("reject_first", [False, True])
def test_real_local_phased_prepare_seals_typed_value_then_settles(tmp_path, reject_first):
    import json
    import shutil
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import (
        prepare_phased_provider_attempt, settle_phased_provider_attempt, verify_phased_precommit,
    )
    from tests.workflow_evaluated_phased_helpers import external_attempt, local_terminal_provider
    if shutil.which("tmux") is None:
        pytest.skip("tmux unavailable")
    attempt = external_attempt(tmp_path)
    attempt.provider_executor = local_terminal_provider(tmp_path, reject_first=reject_first)
    deadline = time.monotonic() + 20
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        prepared = prepare_phased_provider_attempt(attempt, deadline=deadline, transport_root=Path(root))
        assert prepared.value.json_value() == {"approved": True}
        proof = prepared.proof
        assert proof["result_digest"] == canonical_sha256({"approved": True})
        assert proof["result_digest"] != "sha256:" + sha256(attempt.attempt_files.read("result.json")).hexdigest()
        assert proof["result_path"] == attempt.result_path
        assert proof["natural_shutdown"] == {"disposition": "natural_exit", "return_code": 0,
            "pane_absent": True, "server_absent": True, "proof_complete": True}
        assert prepared.deadline == deadline
        starts = (tmp_path / "task-starts").read_text().splitlines()
        assert len(starts) == 1
        assert {str(json.loads(line)["pid"]) for line in (tmp_path / "receipts.jsonl").read_text().splitlines()} == set(starts)
        assert len(prepared.prepared.actual_deliveries) == (3 if reject_first else 2)
        receipt = json.loads(attempt.attempt_files.read("phased-attempt.json"))
        assert receipt["state"] == "prepared" and receipt["proof"] == proof
        verify_phased_precommit(prepared)
        settle_phased_provider_attempt(prepared)
        settle_phased_provider_attempt(prepared)
        assert json.loads(attempt.attempt_files.read("phased-attempt.json")) == {
            "schema_version": "evaluated_phased_provider_attempt.v1", "state": "settled", "proof": proof}


def test_interrupted_intent_recovery_cleans_exact_candidates_without_ledger(tmp_path):
    import json
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import EvaluatedPhasedBindings, recover_phased_provider_attempt
    from tests.workflow_evaluated_phased_helpers import external_attempt
    attempt = external_attempt(tmp_path)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        bindings = EvaluatedPhasedBindings(attempt, deadline=time.monotonic() + 5, transport_root=Path(root))
        composition = bindings.compose_attempt(bindings.allocate_attempt(), deadline=bindings.deadline)
        bindings.preflight_candidates(composition)
        (tmp_path / "outputs/report.md").write_text("provisional")
        attempt.attempt_files.create("result.json", b'{"approved":false}')
        attempt.attempt_files.create("phases.jsonl", b'torn optional audit')
        assert recover_phased_provider_attempt(attempt, deadline=time.monotonic() + 5, transport_root=Path(root))
        assert not (tmp_path / "outputs/report.md").exists()
        assert not attempt.attempt_files.exists("result.json")
        assert json.loads(attempt.attempt_files.read("phased-attempt.json"))["state"] == "abandoned"
        assert attempt.attempt_files.read("phases.jsonl") == b'torn optional audit'
        bindings.candidates.close()


@pytest.mark.parametrize("damage", ["extra", "identity", "candidates", "transport", "proof"])
def test_foreign_or_malformed_attempt_receipt_refuses_before_cleanup(tmp_path, damage, monkeypatch):
    import json
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import EvaluatedPhasedBindings, recover_phased_provider_attempt
    from orchestrator.providers.interactive_terminal import InteractiveTerminalTurnQueueAdapter
    from tests.workflow_evaluated_phased_helpers import external_attempt
    attempt = external_attempt(tmp_path)
    called = []
    monkeypatch.setattr(InteractiveTerminalTurnQueueAdapter, "recover_failed", lambda *a, **kw: called.append(1))
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        bindings = EvaluatedPhasedBindings(attempt, deadline=time.monotonic() + 5, transport_root=Path(root))
        composition = bindings.compose_attempt(bindings.allocate_attempt(), deadline=bindings.deadline)
        bindings.preflight_candidates(composition)
        receipt = json.loads(attempt.attempt_files.read("phased-attempt.json"))
        if damage == "extra":
            receipt["extra"] = 1
        elif damage == "identity":
            receipt["identity"] = "foreign"
        elif damage == "candidates":
            receipt["candidates"][0]["workspace_relative_path"] = "outputs/foreign"
        elif damage == "transport":
            receipt["transport"]["root"] = "/tmp"
        else:
            receipt["proof"] = {}
        attempt.attempt_files.write_atomic("phased-attempt.json", json.dumps(receipt).encode())
        (tmp_path / "outputs/report.md").write_text("preserve")
        with pytest.raises((ValueError, OSError, RuntimeError)):
            recover_phased_provider_attempt(attempt, deadline=time.monotonic() + 5, transport_root=Path(root))
        assert called == []
        assert (tmp_path / "outputs/report.md").read_text() == "preserve"
        bindings.candidates.close()


@pytest.mark.parametrize("attempts", [1, 2, 3])
def test_real_invalid_submissions_exhaust_exact_budget_and_abandon_after_cleanup(tmp_path, attempts, monkeypatch):
    import json
    import shutil
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import prepare_phased_provider_attempt, PhasedCandidates
    from orchestrator.workflow.evaluated.providers import ProviderPerformerError
    from tests.workflow_evaluated_phased_helpers import external_attempt, local_terminal_provider
    if shutil.which("tmux") is None:
        pytest.skip("tmux unavailable")
    attempt = external_attempt(tmp_path, attempts=attempts)
    attempt.provider_executor = local_terminal_provider(tmp_path, always_invalid=True)
    calls = []
    for name in ("validate_outputs", "validate_result"):
        original = getattr(PhasedCandidates, name)
        def record(self, snapshot, *, method=original, label=name):
            calls.append((snapshot.submission_ordinal, label))
            return method(self, snapshot)
        monkeypatch.setattr(PhasedCandidates, name, record)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        with pytest.raises(ProviderPerformerError) as excinfo:
            prepare_phased_provider_attempt(attempt, deadline=time.monotonic() + 20, transport_root=Path(root))
        assert excinfo.value.code == "provider_phased_materialization_attempts_exhausted"
        assert calls == [(ordinal, validator) for ordinal in range(1, attempts + 1)
            for validator in ("validate_outputs", "validate_result")]
        receipt = json.loads(attempt.attempt_files.read("phased-attempt.json"))
        assert receipt["state"] == "abandoned"
        assert not attempt.attempt_files.exists("result.json")
        assert not (tmp_path / "outputs/report.md").exists()


def test_real_early_provider_exit_publishes_no_result(tmp_path):
    import json
    import shutil
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import prepare_phased_provider_attempt
    from orchestrator.workflow.evaluated.providers import ProviderPerformerError
    from tests.workflow_evaluated_phased_helpers import external_attempt, local_terminal_provider
    if shutil.which("tmux") is None:
        pytest.skip("tmux unavailable")
    attempt = external_attempt(tmp_path)
    attempt.provider_executor = local_terminal_provider(tmp_path, early_exit=True)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        with pytest.raises(ProviderPerformerError):
            prepare_phased_provider_attempt(attempt, deadline=time.monotonic() + 10, transport_root=Path(root))
        assert not attempt.attempt_files.exists("result.json")
        assert json.loads(attempt.attempt_files.read("phased-attempt.json"))["state"] == "abandoned"


def test_precommit_rejects_mutated_bindings_and_expired_original_deadline(tmp_path):
    from copy import deepcopy
    import shutil
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import (prepare_phased_provider_attempt,
        verify_phased_precommit, settle_phased_provider_attempt, settle_phased_receipt)
    from orchestrator.workflow.evaluated.providers import ProviderPerformerError
    from tests.workflow_evaluated_phased_helpers import external_attempt, local_terminal_provider
    if shutil.which("tmux") is None:
        pytest.skip("tmux unavailable")
    attempt = external_attempt(tmp_path)
    attempt.provider_executor = local_terminal_provider(tmp_path)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        prepared = prepare_phased_provider_attempt(attempt, deadline=time.monotonic() + 20, transport_root=Path(root))
        for key in ("identity", "attempt", "input_digest", "result_path", "result_digest",
                "canonical_prompt_sha256", "actual_deliveries_sha256"):
            proof = deepcopy(prepared.proof)
            proof[key] = proof[key] + 1 if key == "attempt" else (
                "sha256:" + "0" * 64 if key.endswith("digest") or key.endswith("sha256") else "foreign")
            with pytest.raises((ValueError, ProviderPerformerError)):
                verify_phased_precommit(replace(prepared, proof=proof))
        expired = replace(prepared, prepared=replace(prepared.prepared, deadline=time.monotonic() - 1))
        with pytest.raises(ProviderPerformerError, match="expired"):
            verify_phased_precommit(expired)
        attempt.attempt_files.write_atomic("result.json", b'{"approved":false}')
        with pytest.raises((ValueError, OSError)):
            verify_phased_precommit(prepared)
        # After memo commit, inline proof alone owns settlement, even with lost candidates/audit.
        (tmp_path / "outputs/report.md").unlink()
        attempt.attempt_files.unlink("result.json")
        attempt.attempt_files.unlink("phases.jsonl")
        settle_phased_provider_attempt(prepared)
        attempt.attempt_files.write_atomic("phased-attempt.json", b'{')
        settle_phased_receipt(attempt.attempt_files, prepared.proof)
        attempt.attempt_files.write_atomic("phased-attempt.json", b'{"schema_version":"evaluated_phased_provider_attempt.v1","state":"intent","identity":"foreign"}')
        with pytest.raises(ValueError):
            settle_phased_receipt(attempt.attempt_files, prepared.proof)


def test_phased_binding_translates_model_effort_without_forwarding_runtime_policy(tmp_path):
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.providers import CallPolicyBinding
    from orchestrator.workflow.evaluated.phased_providers import EvaluatedPhasedBindings
    from tests.workflow_evaluated_phased_helpers import external_attempt
    attempt = external_attempt(tmp_path, policy=':model "chosen-model" :effort "high"')
    template = attempt.provider_executor.registry.get("test-provider")
    command = ("local-provider", "--model", "${model}", "--effort", "${reasoning}", "${PROMPT}")
    template = replace(template, command=list(command),
        interactive_session_support=replace(template.interactive_session_support, command=command),
        call_policy_bindings={"model": CallPolicyBinding(target_param="model"),
            "effort": CallPolicyBinding(target_param="reasoning")})
    attempt.provider_executor.registry.register(template)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        bindings = EvaluatedPhasedBindings(attempt, deadline=time.monotonic() + 5, transport_root=Path(root))
        composition = bindings.compose_attempt(bindings.allocate_attempt(), deadline=bindings.deadline)
        assert composition.invocation.resolved_command[1:5] == ("--model", "chosen-model", "--effort", "high")
        assert composition.invocation.prepared_provider_policy.timeout_sec == 60
        assert composition.invocation.prepared_provider_policy.model == "chosen-model"
        assert composition.invocation.prepared_provider_policy.effort == "high"


@pytest.mark.parametrize("damage", ["malformed", "drift"])
def test_phased_capability_boundary_refuses_malformed_or_drifted_template(tmp_path, damage, monkeypatch):
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import EvaluatedPhasedBindings
    from orchestrator.workflow.provider_phased_delivery.bindings import PhasedOperationFailure
    from tests.workflow_evaluated_phased_helpers import external_attempt
    attempt = external_attempt(tmp_path)
    template = attempt.provider_executor.registry.get("test-provider")
    if damage == "malformed":
        template.interactive_session_support = object()
    else:
        original = attempt.provider_executor.prepare_interactive_invocation
        def drift(**kwargs):
            invocation, error = original(**kwargs)
            return replace(invocation, support=replace(invocation.support, graceful_close_text="/changed")), error
        monkeypatch.setattr(attempt.provider_executor, "prepare_interactive_invocation", drift)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        bindings = EvaluatedPhasedBindings(attempt, deadline=time.monotonic() + 5, transport_root=Path(root))
        with pytest.raises(PhasedOperationFailure):
            bindings.compose_attempt(bindings.allocate_attempt(), deadline=bindings.deadline)
        assert bindings.prestart_no_backend_allocation_proof().proof_complete
        assert not attempt.attempt_files.exists("phased-attempt.json")


def test_precommit_revalidates_typed_artifact_freshness_after_natural_shutdown(tmp_path):
    import shutil
    import tempfile
    import time
    from pathlib import Path
    from orchestrator.workflow.evaluated.phased_providers import prepare_phased_provider_attempt, verify_phased_precommit
    from orchestrator.workflow.evaluated.providers import ProviderPerformerError
    from tests.workflow_evaluated_phased_helpers import external_attempt, local_terminal_provider
    if shutil.which("tmux") is None:
        pytest.skip("tmux unavailable")
    attempt = external_attempt(tmp_path, typed_artifact=True)
    attempt.provider_executor = local_terminal_provider(tmp_path, typed_artifact=True)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        prepared = prepare_phased_provider_attempt(attempt, deadline=time.monotonic() + 20, transport_root=Path(root))
        (tmp_path / "docs/note.md").unlink()
        try:
            with pytest.raises(ProviderPerformerError, match="contract"):
                verify_phased_precommit(prepared)
        finally:
            prepared.coordinator.close()
            prepared.bindings.candidates.close()


def test_phased_capture_renders_one_separator_inclusive_cut(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated import providers
    node, operands, _, reader = checked_request(tmp_path)
    captured = providers.resolve_provider_io(node, operands, workspace=tmp_path, reader=reader)
    (tmp_path / "docs/note.md").write_text("changed")
    monkeypatch.setattr(providers, "resolve_provider_io", lambda *a, **kw: captured)
    resolved = providers.resolve_provider_input(node, operands, workspace=tmp_path,
        reader=reader, result_path="run/result.json", delivery_name="file/1")
    cut = resolved.canonical_cut
    assert cut.task_slice + cut.materialization_slice == resolved.prompt.encode()
    assert "capturada ñ".encode() in cut.task_slice
    assert b"changed" not in cut.canonical_composed
    assert cut.materialization_slice.startswith(b"\n\n")
    assert resolved.input_parts["prompt"] == "sha256:" + sha256(cut.canonical_composed).hexdigest()
    assert resolved.input_parts["phased_protocol"] == canonical_sha256("provider_phased_protocol_frame.v1")


@pytest.mark.parametrize("timeout", [0, -1, True, 10**400])
def test_phased_deadline_refuses_invalid_budget_before_transport(tmp_path, timeout):
    from orchestrator.workflow.evaluated.phased_providers import capture_phased_deadline
    node, _, _, _ = checked_request(tmp_path)
    node = {**node, "policy": {**node["policy"], "timeout_sec": {
        **node["policy"]["timeout_sec"], "v": timeout}}}
    with pytest.raises((ValueError, TypeError)):
        capture_phased_deadline(node, now=lambda: 1.0)


def test_phased_deadline_captured_once_and_rejects_unrepresentable_addition(tmp_path):
    from orchestrator.workflow.evaluated.phased_providers import capture_phased_deadline
    node, _, _, _ = checked_request(tmp_path, timeout=7)
    calls = []
    assert capture_phased_deadline(node, now=lambda: calls.append(1) or 4.0) == 11.0
    assert calls == [1]
    with pytest.raises(ValueError):
        capture_phased_deadline(node, now=lambda: 1e308)


@pytest.mark.parametrize("mode,turns", [("success", 1), ("missing-output-once", 2),
    ("bad-result-once", 2), ("both-invalid-once", 2)])
def test_public_phased_cli_joint_validation_and_typed_downstream(tmp_path, mode, turns):
    from tests.workflow_evaluated_phased_helpers import (
        public_case, public_cli, public_events, public_run_root, public_snapshot,
        assert_public_completed, assert_public_readers,
    )
    case = public_case(tmp_path, mode=mode)
    result = public_cli(case, case[0])
    assert result.returncode == 0, result.stdout + result.stderr
    run_root = public_run_root(tmp_path)
    assert_public_completed(case, run_root, ordinal=1, processes=1, turns=turns)
    events = public_events(tmp_path)
    retry = [row for row in events if row["event"] == "turn" and row["phase"] == "retry_materialization"]
    if retry:
        reasons = [row["reason"] for row in retry[0]["diagnostics"]]
        expected = {"missing-output-once": ["output_validation_failed"],
            "bad-result-once": ["structured_result_validation_failed"],
            "both-invalid-once": ["output_validation_failed", "structured_result_validation_failed"]}
        assert reasons == expected[mode]
    assert_public_readers(case, run_root, "completed")


@pytest.mark.parametrize("attempts", [1, 2, 3])
def test_public_phased_cli_exhaustion_never_publishes(tmp_path, attempts):
    import json
    from tests.workflow_evaluated_phased_helpers import (
        public_case, public_cli, public_events, public_run_root, public_snapshot,
        assert_public_readers,
    )
    case = public_case(tmp_path, mode="always-invalid", attempts=attempts)
    result = public_cli(case, case[0])
    assert result.returncode != 0
    run_root = public_run_root(tmp_path)
    snapshot = public_snapshot(run_root)
    assert not snapshot.active_commits and not snapshot.pending_starts
    assert snapshot.terminal.data["outcome"] == "failed"
    events = public_events(tmp_path)
    assert len([row for row in events if row["event"] == "start"]) == 1
    assert len([row for row in events if row["event"] == "task"]) == 1
    receipts = [row for row in events if row["event"] == "submit"]
    assert len([row for row in events if row["event"] == "submit_request"]) == attempts
    assert [row["receipt"]["status"] for row in receipts[:attempts - 1]] == ["retry_queued"] * (attempts - 1)
    (start,) = snapshot.latest_starts.values()
    ledger = [json.loads(line) for line in
        (run_root / start.data["result_path"]).with_name("phases.jsonl").read_text().splitlines()]
    assert [row["payload"]["submission_ordinal"] for row in ledger if row.get("event") == "submit_received"] == list(range(1, attempts + 1))
    assert ledger[-1]["event"] == "terminal_failed"
    assert ledger[-1]["payload"]["diagnostic"]["reason"] == "materialization_attempts_exhausted"
    assert not (tmp_path / "outputs/report.md").exists()
    assert not (tmp_path / "continuations.jsonl").exists()
    assert_public_readers(case, run_root, "failed")
