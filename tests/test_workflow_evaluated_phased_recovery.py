"""Evaluated phased publication and exact-attempt recovery with a local terminal provider."""
from __future__ import annotations

from contextlib import closing, contextmanager
from pathlib import Path
import json

import pytest

from orchestrator.workflow.evaluated import runtime, phased_providers as phased
from orchestrator.workflow.evaluated.authority import publish_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.workflow_evaluated_phased_helpers import checked_request, local_terminal_provider
from tests.test_workflow_lisp_phased_239 import _compile


@contextmanager
def _run(tmp_path, monkeypatch, *, timeout=60, reject_first=False, source_text=None):
    checked_request(tmp_path, timeout=timeout)
    source = tmp_path / "phased239.orc"
    program = _compile(source, source.read_text() if source_text is None else source_text)
    executor = local_terminal_provider(tmp_path, reject_first=reject_first)
    monkeypatch.setattr(runtime, "provider_executor_for_run", lambda *a, **k: (executor, None))
    inputs = {"subject": "Tarea ñ\n", "note": "docs/note.md", "report": "outputs/report.md"}
    with publish_run_authority(tmp_path / ".orchestrate/run", program, run_id="run",
            workflow_file="phased239.orc", workflow_checksum=canonical_sha256(source.read_text()),
            bound_inputs=inputs, resume_request=dict(source_roots=[], entry_workflow=None,
                provider_externs_path=None, prompt_externs_path=None, imported_workflow_bundles_path=None,
                command_boundaries_path=None, input_file=None, input_overrides={})) as authority:
        yield authority, inputs


def _execute(authority, inputs, workspace, *, resume=False):
    method = runtime.execute_pure_resume if resume else runtime.execute_pure_run
    return method(authority, inputs, run_id="run", workspace=workspace)


def _snapshot(authority):
    return read_memo(authority.memo_path, site_classes(authority.program), run_files=authority.run_files)


def test_runtime_phased_commits_then_settles_before_exposing_value(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch, reject_first=True) as (authority, inputs):
        assert _execute(authority, inputs, tmp_path) == (0, {"approved": True})
        snapshot = _snapshot(authority)
        assert [e.data["record"] for e in snapshot.entries] == ["started", "committed", "settled", "terminal"]
        commit = next(iter(snapshot.active_commits.values())).data
        assert commit["effect_class"] == "provider_phased"
        assert commit["proof"]["result_digest"] == canonical_sha256(commit["value"])
        assert len((tmp_path / "task-starts").read_text().splitlines()) == 1
        assert [json.loads(line)["status"] for line in (tmp_path / "receipts.jsonl").read_text().splitlines()] == ["retry_queued", "accepted_closing"]
        before = authority.memo_path.read_bytes()
        assert _execute(authority, inputs, tmp_path, resume=True) == (0, {"approved": True})
        assert authority.memo_path.read_bytes() == before


@pytest.mark.parametrize("receipt", ["prepared", "missing", "torn", "missing-directory", "missing-identity", "missing-effects"])
def test_committed_gap_reconciles_inline_without_provider_or_candidate_reads(tmp_path, monkeypatch, receipt):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def stop(prepared):
            raise RuntimeError("commit-before-settle interruption")
        with monkeypatch.context() as patch:
            patch.setattr(phased, "settle_phased_provider_attempt", stop)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        before = _snapshot(authority)
        assert before.unsettled_coordinators and before.terminal is None
        commit = next(iter(before.active_commits.values())).data
        attempt_dir = authority.run_root / Path(commit["result_path"]).parent
        if receipt == "missing":
            (attempt_dir / "phased-attempt.json").unlink()
        elif receipt == "torn":
            (attempt_dir / "phased-attempt.json").write_bytes(b'{"schema_version":')
        (attempt_dir / "result.json").unlink()
        (tmp_path / "outputs/report.md").unlink()
        for audit in attempt_dir.glob("*jsonl"):
            audit.unlink()
        if receipt in {"missing-directory", "missing-identity", "missing-effects"}:
            import shutil
            shutil.rmtree(attempt_dir if receipt == "missing-directory" else (
                attempt_dir.parent if receipt == "missing-identity" else attempt_dir.parent.parent))
        def forbidden(*args, **kwargs):
            raise AssertionError("K3 consulted external provider/candidate state")
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "provider_executor_for_run", forbidden)
            patch.setattr(phased, "prepare_phased_provider_attempt", forbidden)
            patch.setattr(phased, "recover_phased_provider_attempt", forbidden)
            patch.setattr(phased.PhasedCandidates, "snapshot", forbidden)
            assert _execute(authority, inputs, tmp_path, resume=True) == (0, {"approved": True})
        after = _snapshot(authority)
        assert next(iter(after.active_commits.values())).data == commit
        assert after.entries[-2].data["by"] == "reconcile"
        assert json.loads((attempt_dir / "phased-attempt.json").read_text()) == {
            "schema_version": "evaluated_phased_provider_attempt.v1", "state": "settled", "proof": commit["proof"]}
        assert len((tmp_path / "task-starts").read_text().splitlines()) == 1


def test_original_deadline_expiry_after_prepare_cannot_commit(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        real_prepare = phased.prepare_phased_provider_attempt
        from dataclasses import replace
        def expire(*args, **kwargs):
            prepared = real_prepare(*args, **kwargs)
            return replace(prepared, prepared=replace(prepared.prepared, deadline=0.0))
        monkeypatch.setattr(phased, "prepare_phased_provider_attempt", expire)
        assert _execute(authority, inputs, tmp_path) == (1, None)
        snapshot = _snapshot(authority)
        assert not snapshot.active_commits
        assert any(e.data.get("code") == "provider_timeout" for e in snapshot.entries)


def test_deadline_expiry_after_durable_commit_allows_settlement(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        original = runtime._append_effect_commit
        original_monotonic = phased.time.monotonic
        def append(*args, **kwargs):
            original(*args, **kwargs)
            monkeypatch.setattr(phased.time, "monotonic", lambda: original_monotonic() + 10000)
        monkeypatch.setattr(runtime, "_append_effect_commit", append)
        assert _execute(authority, inputs, tmp_path) == (0, {"approved": True})
        assert not _snapshot(authority).unsettled_coordinators


@pytest.mark.parametrize("pending", [False, True])
def test_uncommitted_prepared_attempt_is_cleaned_before_new_whole_visit(tmp_path, monkeypatch, pending, caplog):
    class Interrupted(BaseException):
        pass
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def stop(*args, **kwargs):
            if pending:
                raise Interrupted()
            raise RuntimeError("prepared-before-commit interruption")
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "_append_effect_commit", stop)
            if pending:
                with pytest.raises(Interrupted):
                    _execute(authority, inputs, tmp_path)
            else:
                assert _execute(authority, inputs, tmp_path) == (1, None)
        before = _snapshot(authority)
        assert not before.active_commits
        start = next(iter(before.latest_starts.values())).data
        old_dir = authority.run_root / Path(start["result_path"]).parent
        assert json.loads((old_dir / "phased-attempt.json").read_text())["state"] == "prepared"
        events = []
        real_cleanup = phased.recover_phased_provider_attempt
        real_deadline = phased.capture_phased_deadline
        def cleanup(*args, **kwargs):
            events.append("cleanup")
            return real_cleanup(*args, **kwargs)
        def deadline(*args, **kwargs):
            events.append("live-budget")
            return real_deadline(*args, **kwargs)
        monkeypatch.setattr(phased, "recover_phased_provider_attempt", cleanup)
        monkeypatch.setattr(phased, "capture_phased_deadline", deadline)
        assert _execute(authority, inputs, tmp_path, resume=True) == (0, {"approved": True})
        after = _snapshot(authority)
        assert next(iter(after.active_commits.values())).data["attempt"] == 2
        assert json.loads((old_dir / "phased-attempt.json").read_text())["state"] == "abandoned"
        assert not (old_dir / "result.json").exists()
        assert events == ["cleanup", "live-budget"]
        assert sum(record.getMessage().startswith("[provider_attempt_interrupted_rerun]")
            for record in caplog.records) == 1
        assert len((tmp_path / "task-starts").read_text().splitlines()) == 2


@pytest.mark.parametrize("corruption", ["torn", "foreign-binding", "symlink", "foreign-proof"])
def test_uncommitted_unprovable_receipt_refuses_without_writes_or_new_start(tmp_path, monkeypatch, corruption):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def stop(*args, **kwargs):
            raise RuntimeError("prepared-before-commit interruption")
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "_append_effect_commit", stop)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        start = next(iter(_snapshot(authority).latest_starts.values())).data
        receipt = authority.run_root / Path(start["result_path"]).parent / "phased-attempt.json"
        if corruption == "torn":
            receipt.write_bytes(b'{"schema_version":')
        elif corruption == "symlink":
            receipt.rename(receipt.with_suffix(".saved"))
            receipt.symlink_to(receipt.with_suffix(".saved").name)
        else:
            row = json.loads(receipt.read_text())
            if corruption == "foreign-binding":
                row["attempt"] = 3
            elif corruption == "candidate-numeric-alias":
                row["candidates"][0]["contract_ordinal"] = False
            else:
                row["proof"]["natural_shutdown"]["return_code"] = False
            receipt.write_text(json.dumps(row))
        before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        assert _execute(authority, inputs, tmp_path, resume=True) == (2, None)
        after = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        assert after == before
        assert len((tmp_path / "task-starts").read_text().splitlines()) == 1


def test_runtime_parallel_guard_refuses_forged_phased_before_any_preparation():
    from orchestrator.workflow.evaluated.parallel import ParallelCoordinator
    from orchestrator.workflow.evaluated.memo import MemoError
    coordinator = object.__new__(ParallelCoordinator)
    with pytest.raises(MemoError, match="parallel_provider_boundary"):
        coordinator._prepare(None, {"class": "provider_phased"}, (), "forged", None, None, {})


@pytest.mark.parametrize("corruption", ["symlink-directory", "foreign-binding", "numeric-alias", "candidate-numeric-alias"])
def test_committed_receipt_ambiguity_refuses_readonly(tmp_path, monkeypatch, corruption):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def stop(*args, **kwargs):
            raise RuntimeError("commit-before-settle interruption")
        with monkeypatch.context() as patch:
            patch.setattr(phased, "settle_phased_provider_attempt", stop)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        commit = next(iter(_snapshot(authority).active_commits.values())).data
        directory = authority.run_root / Path(commit["result_path"]).parent
        receipt = directory / "phased-attempt.json"
        if corruption == "symlink-directory":
            directory.rename(directory.with_name(directory.name + "-saved"))
            directory.symlink_to(directory.name + "-saved", target_is_directory=True)
        else:
            row = json.loads(receipt.read_text())
            if corruption == "foreign-binding":
                row["identity"] += "foreign"
            elif corruption == "candidate-numeric-alias":
                row["candidates"][0]["contract_ordinal"] = False
            else:
                row["proof"]["natural_shutdown"]["return_code"] = False
            receipt.write_text(json.dumps(row))
        before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        assert _execute(authority, inputs, tmp_path, resume=True) == (2, None)
        assert {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_durable_commit_is_reread_before_local_settlement(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        original = runtime._append_effect_commit
        def replace_commit(*args, **kwargs):
            original(*args, **kwargs)
            rows = [json.loads(line) for line in authority.memo_path.read_bytes().splitlines()]
            row = rows[-1]
            row["value"] = {"approved": False}
            row["result_digest"] = canonical_sha256(row["value"])
            row["proof"]["result_digest"] = row["result_digest"]
            authority.run_files.write_atomic("memo.jsonl", b"".join(json.dumps(r).encode() + b"\n" for r in rows))
        monkeypatch.setattr(runtime, "_append_effect_commit", replace_commit)
        assert _execute(authority, inputs, tmp_path) == (1, None)
        snapshot = _snapshot(authority)
        assert snapshot.unsettled_coordinators and snapshot.terminal is None


@pytest.mark.parametrize("missing", ["receipt", "directory"])
def test_initial_absence_preserves_unpublished_files_and_starts_fresh_attempt(tmp_path, monkeypatch, missing):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def nondispatched(*args, **kwargs):
            raise RuntimeError("before initial receipt publication")
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "perform_external", nondispatched)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        start = next(iter(_snapshot(authority).latest_starts.values())).data
        directory = authority.run_root / Path(start["result_path"]).parent
        if missing == "directory":
            directory.rmdir()
        else:
            (directory / "prompt.txt").write_bytes(b"unpublished diagnostic")
            (directory / ".phased-attempt.tmp").write_bytes(b"unpublished receipt temp")
        assert _execute(authority, inputs, tmp_path, resume=True) == (0, {"approved": True})
        assert next(iter(_snapshot(authority).active_commits.values())).data["attempt"] == 2
        assert not (directory / "phased-attempt.json").exists()
        if missing == "receipt":
            assert (directory / "prompt.txt").read_bytes() == b"unpublished diagnostic"
            assert (directory / ".phased-attempt.tmp").read_bytes() == b"unpublished receipt temp"
        assert len((tmp_path / "task-starts").read_text().splitlines()) == 1


def test_k3_observed_attempt_directory_replacement_refuses_without_overwrite(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def stop(*args, **kwargs):
            raise RuntimeError("commit-before-settle interruption")
        with monkeypatch.context() as patch:
            patch.setattr(phased, "settle_phased_provider_attempt", stop)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        before = authority.memo_path.read_bytes()
        original = phased._store_receipt
        replaced = []
        def replace_root(files, receipt):
            directory = files.workspace
            directory.rename(directory.with_name(directory.name + "-saved"))
            directory.mkdir()
            (directory / "phased-attempt.json").write_bytes(b"foreign replacement")
            replaced.append(directory)
            return original(files, receipt)
        monkeypatch.setattr(phased, "_store_receipt", replace_root)
        assert _execute(authority, inputs, tmp_path, resume=True) == (1, None)
        assert authority.memo_path.read_bytes() == before
        assert (replaced[0] / "phased-attempt.json").read_bytes() == b"foreign replacement"


def test_original_budget_is_captured_before_live_input_read(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        events = []
        original_capture = phased.capture_phased_deadline
        original_resolve = runtime.effect_inputs._resolve_effect_input
        def capture(*args, **kwargs):
            events.append("deadline")
            return original_capture(*args, **kwargs)
        def resolve(*args, **kwargs):
            events.append("input")
            return original_resolve(*args, **kwargs)
        monkeypatch.setattr(phased, "capture_phased_deadline", capture)
        monkeypatch.setattr(runtime.effect_inputs, "_resolve_effect_input", resolve)
        assert _execute(authority, inputs, tmp_path) == (0, {"approved": True})
        assert events == ["deadline", "input"]


@pytest.mark.parametrize("missing_parent", ["effects", "identity"])
def test_kill_after_started_with_uncreated_canonical_parents_can_retry_readonly_preflight(tmp_path, monkeypatch, missing_parent):
    from orchestrator.workflow.evaluated import effect_inputs
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        class Killed(BaseException):
            pass
        def kill_after_started(run_files, memo_path, started_record, **kwargs):
            runtime.append_record(memo_path, started_record, run_files=run_files, checked_authority=authority)
            if missing_parent == "identity":
                with closing(run_files.mkdir_exclusive("effects")):
                    pass
            raise Killed()
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "allocate_attempt", kill_after_started)
            with pytest.raises(Killed):
                _execute(authority, inputs, tmp_path)
        start = next(iter(_snapshot(authority).latest_starts.values())).data
        before = authority.memo_path.read_bytes()
        assert effect_inputs.open_phased_attempt(authority, start) is None
        assert authority.memo_path.read_bytes() == before
        assert not (authority.run_root / Path(start["result_path"]).parent).exists()
        assert _execute(authority, inputs, tmp_path, resume=True) == (0, {"approved": True})
        assert next(iter(_snapshot(authority).active_commits.values())).data["attempt"] == 2
        assert len((tmp_path / "task-starts").read_text().splitlines()) == 1


def test_initial_absence_revalidates_every_opened_parent(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated import effect_inputs
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def nondispatched(*args, **kwargs):
            raise RuntimeError("before initial receipt publication")
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "perform_external", nondispatched)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        start = next(iter(_snapshot(authority).latest_starts.values())).data
        directory = authority.run_root / Path(start["result_path"]).parent
        directory.rmdir()
        identity_directory = directory.parent.name
        original = WorkspaceFiles.subroot
        changed = []
        def replace_parent(files, path):
            child = original(files, path)
            if str(path) == identity_directory and not changed:
                effects = authority.run_root / "effects"
                effects.rename(effects.with_name("effects-saved"))
                (effects / identity_directory).mkdir(parents=True)
                changed.append(True)
            return child
        monkeypatch.setattr(WorkspaceFiles, "subroot", replace_parent)
        before = authority.memo_path.read_bytes()
        with pytest.raises(ValueError, match="ancestor replaced"):
            effect_inputs.open_phased_attempt(authority, start)
        assert authority.memo_path.read_bytes() == before
        assert not directory.exists()


def test_phased_outcome_requires_its_concrete_prepared_carrier():
    from types import SimpleNamespace
    from orchestrator.workflow.evaluated.effect_execution import ExternalOutcome
    with pytest.raises(ValueError, match="concrete prepared outcome"):
        runtime._validate_attempt_outcome(SimpleNamespace(node={"class": "provider_phased"}), ExternalOutcome())


def test_receipt_absence_refuses_replaced_ancestor_even_when_attempt_inode_survives(tmp_path, monkeypatch):
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def nondispatched(*args, **kwargs):
            raise RuntimeError("before initial receipt publication")
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "perform_external", nondispatched)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        start = next(iter(_snapshot(authority).latest_starts.values())).data
        directory = authority.run_root / Path(start["result_path"]).parent
        original = WorkspaceFiles.stat
        changed = []
        def replace_ancestor(files, path):
            if str(path) == "phased-attempt.json" and files.workspace == directory and not changed:
                effects = authority.run_root / "effects"
                saved = effects.with_name("effects-saved")
                effects.rename(saved)
                effects.mkdir()
                (saved / directory.parent.name).rename(effects / directory.parent.name)
                changed.append(True)
            return original(files, path)
        monkeypatch.setattr(WorkspaceFiles, "stat", replace_ancestor)
        before = authority.memo_path.read_bytes()
        assert _execute(authority, inputs, tmp_path, resume=True) == (2, None)
        assert changed
        assert authority.memo_path.read_bytes() == before
        assert not (directory / "phased-attempt.json").exists()


@pytest.mark.parametrize("unsafe", ["effects-symlink", "effects-file", "identity-symlink", "attempt-file", "permission"])
def test_initial_absence_never_hides_unsafe_canonical_components(tmp_path, monkeypatch, unsafe):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def nondispatched(*args, **kwargs):
            raise RuntimeError("before initial receipt publication")
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "perform_external", nondispatched)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        start = next(iter(_snapshot(authority).latest_starts.values())).data
        directory = authority.run_root / Path(start["result_path"]).parent
        effects = authority.run_root / "effects"
        target = effects if unsafe.startswith("effects") or unsafe == "permission" else (
            directory.parent if unsafe == "identity-symlink" else directory)
        if unsafe == "permission":
            target.chmod(0)
        else:
            target.rename(target.with_name(target.name + "-saved"))
            if unsafe.endswith("symlink"):
                target.symlink_to(target.name + "-saved", target_is_directory=True)
            else:
                target.write_bytes(b"foreign non-directory")
        before = authority.memo_path.read_bytes()
        try:
            assert _execute(authority, inputs, tmp_path, resume=True) == (2, None)
            assert authority.memo_path.read_bytes() == before
            assert not (tmp_path / "task-starts").exists()
            if unsafe.endswith("file"):
                assert target.read_bytes() == b"foreign non-directory"
        finally:
            if unsafe == "permission":
                target.chmod(0o755)


def test_valid_submission_without_natural_success_cannot_publish(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        script = tmp_path / "local-terminal.py"
        script.write_text(script.read_text().replace('if line.strip() == "/exit":\n        break',
            'if line.strip() == "/exit":\n        raise SystemExit(9)'))
        assert _execute(authority, inputs, tmp_path) == (1, None)
        snapshot = _snapshot(authority)
        assert not snapshot.active_commits
        assert not snapshot.unsettled_coordinators
        assert [json.loads(line)["status"] for line in (tmp_path / "receipts.jsonl").read_text().splitlines()] == ["accepted_closing"]
        assert len((tmp_path / "task-starts").read_text().splitlines()) == 1


def test_directory_absence_revalidates_after_last_negative_lookup(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated import effect_inputs
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def nondispatched(*args, **kwargs):
            raise RuntimeError("before initial receipt publication")
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "perform_external", nondispatched)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        start = next(iter(_snapshot(authority).latest_starts.values())).data
        directory = authority.run_root / Path(start["result_path"]).parent
        directory.rmdir()
        original = WorkspaceFiles.stat
        changed = []
        def replace_parent(files, path):
            if files.workspace == directory.parent and str(path) == directory.name and not changed:
                effects = authority.run_root / "effects"
                saved = effects.with_name("effects-saved")
                effects.rename(saved)
                effects.mkdir()
                (saved / directory.parent.name).rename(effects / directory.parent.name)
                changed.append(True)
            return original(files, path)
        monkeypatch.setattr(WorkspaceFiles, "stat", replace_parent)
        before = authority.memo_path.read_bytes()
        with pytest.raises(ValueError, match="ancestor replaced"):
            effect_inputs.open_phased_attempt(authority, start)
        assert changed and authority.memo_path.read_bytes() == before


@pytest.mark.parametrize("receipt_state", ["missing", "torn"])
def test_k3_missing_receipt_revalidates_owner_after_negative_read(tmp_path, monkeypatch, receipt_state):
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        def stop(*args, **kwargs):
            raise RuntimeError("commit-before-settle interruption")
        with monkeypatch.context() as patch:
            patch.setattr(phased, "settle_phased_provider_attempt", stop)
            assert _execute(authority, inputs, tmp_path) == (1, None)
        commit = next(iter(_snapshot(authority).active_commits.values())).data
        directory = authority.run_root / Path(commit["result_path"]).parent
        if receipt_state == "missing":
            (directory / "phased-attempt.json").unlink()
        else:
            (directory / "phased-attempt.json").write_bytes(b'{"schema_version":')
        original = WorkspaceFiles.stat
        changed = []
        def replace_parent(files, path):
            if files.workspace == directory and str(path) == "phased-attempt.json" and not changed:
                effects = authority.run_root / "effects"
                saved = effects.with_name("effects-saved")
                effects.rename(saved)
                effects.mkdir()
                (saved / directory.parent.name).rename(effects / directory.parent.name)
                changed.append(True)
            return original(files, path)
        monkeypatch.setattr(WorkspaceFiles, "stat", replace_parent)
        before = authority.memo_path.read_bytes()
        assert _execute(authority, inputs, tmp_path, resume=True) == (2, None)
        assert changed and authority.memo_path.read_bytes() == before
        if receipt_state == "missing":
            assert not (directory / "phased-attempt.json").exists()
        else:
            assert (directory / "phased-attempt.json").read_bytes() == b'{"schema_version":'



def test_sequential_helper_in_bounded_loop_commits_each_activation(tmp_path, monkeypatch):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule phased239) (export run)
      (defpath Note :kind relpath :under "docs" :must-exist true)
      (defpath Report :kind relpath :under "outputs" :must-exist false)
      (defrecord Review (approved Bool))
      (defprompt review (:fills (subject :text)) -> Review "{subject}")
      (defworkflow worker ((subject String)) -> Review
        (provider-result providers.review :prompt (review :subject subject)
          :delivery :phased :timeout-sec 60))
      (defworkflow run ((subject String) (note Note) (report Report)) -> Int
        (loop/recur :max 2 :state (loop-state (i Int 0)) :on-exhausted state.i
          (fn (state)
            (let* ((review (call worker :subject subject)))
              (if (= state.i 1)
                (done (+ state.i 1))
                (continue (loop-state :like state :i (+ state.i 1)))))))))'''
    with _run(tmp_path, monkeypatch, source_text=source) as (authority, inputs):
        script = tmp_path / "local-terminal.py"
        lines = script.read_text().replace("if output.exists() or bundle.exists():", "if bundle.exists():").splitlines()
        script.write_text("\n".join("        pass" if "output.write_bytes" in line else line for line in lines) + "\n")
        assert _execute(authority, inputs, tmp_path) == (0, 2)
        snapshot = _snapshot(authority)
        commits = list(snapshot.active_commits.values())
        assert len(commits) == 2
        assert len({entry.data["identity"] for entry in commits}) == 2
        assert all(entry.data["attempt"] == 1 and entry.data["effect_class"] == "provider_phased"
            and entry.data["value"] == {"approved": True} for entry in commits)
        assert [entry.data["record"] for entry in snapshot.entries] == [
            "started", "committed", "settled", "started", "committed", "settled", "terminal"]
        assert len(snapshot.settlements) == 2
        assert len((tmp_path / "task-starts").read_text().splitlines()) == 2
        before = authority.memo_path.read_bytes()
        assert _execute(authority, inputs, tmp_path, resume=True) == (0, 2)
        assert authority.memo_path.read_bytes() == before



def test_tampered_prepared_receipt_cannot_commit_even_with_numeric_alias(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (authority, inputs):
        original = phased.prepare_phased_provider_attempt
        def tamper(*args, **kwargs):
            prepared = original(*args, **kwargs)
            receipt_path = prepared.bindings.attempt.attempt_files.workspace / "phased-attempt.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["proof"]["natural_shutdown"]["return_code"] = False
            receipt_path.write_text(json.dumps(receipt))
            return prepared
        monkeypatch.setattr(phased, "prepare_phased_provider_attempt", tamper)
        assert _execute(authority, inputs, tmp_path) == (1, None)
        assert not _snapshot(authority).active_commits
