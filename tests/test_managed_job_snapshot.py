from pathlib import Path

from orchestrator.managed_jobs.snapshot import file_sha256, materialize_snapshot


def test_materialize_snapshot_copies_roots_and_records_hashes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "scripts" / "train.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('train')\n", encoding="utf-8")
    config = workspace / "configs" / "train.yaml"
    config.parent.mkdir()
    config.write_text("epochs: 1\n", encoding="utf-8")

    manifest = materialize_snapshot(
        workspace=workspace,
        snapshot_root=tmp_path / "snapshot",
        roots=("scripts",),
        config_globs=("configs/*.yaml",),
    )

    assert (Path(manifest["snapshot_workspace"]) / "scripts" / "train.py").is_file()
    assert manifest["inputs"]["scripts/train.py"] == file_sha256(source)
    assert manifest["configs"]["configs/train.yaml"] == file_sha256(config)
    assert Path(manifest["manifest_path"]).is_file()


def test_materialize_snapshot_manifest_changes_when_source_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "scripts" / "train.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('one')\n", encoding="utf-8")

    first = materialize_snapshot(workspace=workspace, snapshot_root=tmp_path / "snapshot1", roots=("scripts",))
    source.write_text("print('two')\n", encoding="utf-8")
    second = materialize_snapshot(workspace=workspace, snapshot_root=tmp_path / "snapshot2", roots=("scripts",))

    assert first["inputs"]["scripts/train.py"] != second["inputs"]["scripts/train.py"]
