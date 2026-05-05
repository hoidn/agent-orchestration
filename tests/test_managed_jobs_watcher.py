from pathlib import Path

from orchestrator.managed_jobs.classifier import classify_path
from orchestrator.managed_jobs.models import ManagedJobMetadata, ManagedJobPolicy, ManagedJobPolicyEntry
from orchestrator.managed_jobs.pending_policy import read_pending_records
from orchestrator.managed_jobs.watcher import PollingManagedJobWatcher


def _metadata() -> ManagedJobMetadata:
    return ManagedJobMetadata(
        name_template="{script_stem}",
        state_root_template="state/managed_jobs/{entry_id}/{job_identity_hash}",
        output_root_arg="--output-root",
        verify_files=("{output_root}/metrics.json",),
        snapshot_roots=("scripts",),
        config_globs=(),
    )


def _policy() -> ManagedJobPolicy:
    return ManagedJobPolicy(
        entries=(
            ManagedJobPolicyEntry(
                id="train",
                mode="force_managed",
                path="scripts/training/train.py",
                metadata=_metadata(),
            ),
        )
    )


def test_watcher_records_new_managed_file_under_watch_root(tmp_path: Path) -> None:
    pending_path = tmp_path / "state" / "managed_job_policy" / "pending.jsonl"
    watcher = PollingManagedJobWatcher(
        workspace=tmp_path,
        watch_roots=("scripts/training",),
        policy=_policy(),
        pending_path=pending_path,
    )
    watcher.snapshot()

    target = tmp_path / "scripts" / "training" / "train.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('train')\n", encoding="utf-8")

    watcher.poll_once()

    records = read_pending_records(pending_path)
    assert len(records) == 1
    assert records[0]["path"] == "scripts/training/train.py"
    assert records[0]["decision"] == "managed"
    assert records[0]["entry_id"] == "train"


def test_watcher_ignores_files_outside_watch_roots(tmp_path: Path) -> None:
    pending_path = tmp_path / "pending.jsonl"
    watcher = PollingManagedJobWatcher(
        workspace=tmp_path,
        watch_roots=("scripts/training",),
        policy=_policy(),
        pending_path=pending_path,
    )
    watcher.snapshot()

    target = tmp_path / "scripts" / "other" / "train.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('train')\n", encoding="utf-8")

    watcher.poll_once()

    assert read_pending_records(pending_path) == []


def test_classifier_returns_invalid_when_managed_metadata_is_missing() -> None:
    policy = ManagedJobPolicy(
        entries=(
            ManagedJobPolicyEntry(
                id="train",
                mode="force_managed",
                path="scripts/training/train.py",
                metadata=None,
            ),
        )
    )

    decision = classify_path(Path("scripts/training/train.py"), policy)

    assert decision.decision == "invalid"
    assert "metadata" in decision.reason
