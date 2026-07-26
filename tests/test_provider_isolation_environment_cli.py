from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import stat

import pytest


PROVIDER_PREFIX = "/opt/orchestrator-provider"


def _environment_api():
    return importlib.import_module("orchestrator.providers.isolation_environment")


def _main():
    return importlib.import_module("orchestrator.cli.main").main


@pytest.fixture(autouse=True)
def _isolate_fixed_bootstrap_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    monkeypatch.setattr(
        command,
        "validate_fixed_provider_bootstrap_from_fd",
        lambda *_args, **_kwargs: None,
        raising=False,
    )


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    (prefix / "bin").mkdir(parents=True, mode=0o755)
    for directory in (root / "opt", prefix, prefix / "bin"):
        directory.chmod(0o755)
    python = prefix / "bin" / "python"
    python.write_bytes(b"fixture interpreter\n")
    python.chmod(0o755)
    return root


def _private_output(tmp_path: Path) -> Path:
    directory = tmp_path / "controller-output"
    directory.mkdir(mode=0o700)
    return directory / "manifest.json"


def _invoke(source: Path, output: Path) -> int:
    return _main()(
        [
            "provider-isolation-environment-manifest",
            "--root",
            str(source),
            "--provider-prefix",
            PROVIDER_PREFIX,
            "--output",
            str(output),
        ]
    )


def _source_state(root: Path) -> dict[str, tuple[object, ...]]:
    state: dict[str, tuple[object, ...]] = {}
    for path in (root, *sorted(root.rglob("*"))):
        value = os.lstat(path)
        payload: bytes | str | None
        if stat.S_ISREG(value.st_mode):
            fd = os.open(
                path,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NOATIME,
            )
            try:
                chunks: list[bytes] = []
                while chunk := os.read(fd, 64 * 1024):
                    chunks.append(chunk)
                payload = b"".join(chunks)
            finally:
                os.close(fd)
        elif stat.S_ISLNK(value.st_mode):
            payload = os.readlink(path)
        else:
            payload = None
        state[path.relative_to(root).as_posix()] = (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_nlink,
            value.st_uid,
            value.st_gid,
            value.st_size,
            value.st_atime_ns,
            value.st_mtime_ns,
            value.st_ctime_ns,
            payload,
        )
    return state


def test_cli_atomically_writes_same_prospective_manifest_and_prints_digest(
    tmp_path: Path, capsys
) -> None:
    api = _environment_api()
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    source_before = _source_state(source)
    before = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    assert _source_state(source) == source_before

    assert _invoke(source, output) == 0

    assert capsys.readouterr().out == f"{before.digest}\n"
    assert output.read_bytes() == before.canonical_json
    value = output.stat()
    assert value.st_nlink == 1
    assert value.st_mode & 0o777 == 0o600
    assert api.load_provider_environment_manifest(json.loads(output.read_bytes())).digest == (
        before.digest
    )
    assert api.build_provider_environment_manifest(source, PROVIDER_PREFIX).digest == (
        before.digest
    )
    assert _source_state(source) == source_before


def test_cli_validates_fixed_bootstrap_before_manifest_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    events: list[tuple[object, ...]] = []
    real_publish = command._publish_bytes

    def validate(
        root_fd: int,
        manifest,
        provider_prefix: str,
        *,
        shim_materialization: str,
    ) -> None:
        os.fstat(root_fd)
        events.append(
            (
                "validate",
                manifest.digest,
                provider_prefix,
                shim_materialization,
            )
        )

    def publish(*args, **kwargs) -> None:
        events.append(("publish",))
        real_publish(*args, **kwargs)

    monkeypatch.setattr(
        command,
        "validate_fixed_provider_bootstrap_from_fd",
        validate,
    )
    monkeypatch.setattr(command, "_publish_bytes", publish)

    assert _invoke(source, output) == 0
    assert events[0][0] == "validate"
    assert events[0][2:] == (PROVIDER_PREFIX, "virtual_injected")
    assert events[1] == ("publish",)


def test_cli_fails_closed_before_publication_when_bootstrap_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    output = _private_output(tmp_path)

    def reject(*_args, **_kwargs) -> None:
        raise ValueError("fixed bootstrap invalid")

    monkeypatch.setattr(
        command,
        "validate_fixed_provider_bootstrap_from_fd",
        reject,
    )

    assert _invoke(source, output) == 2
    assert not output.exists()
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_manifest_does_not_create_an_accepted_runtime_snapshot(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    assert _invoke(source, output) == 0
    assert not (tmp_path / "provider_environment_snapshots").exists()


@pytest.mark.parametrize("which", ["root", "provider_prefix", "output"])
def test_cli_requires_absolute_paths(
    tmp_path: Path, monkeypatch, capsys, which: str
) -> None:
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    args = {
        "root": str(source),
        "provider_prefix": PROVIDER_PREFIX,
        "output": str(output),
    }
    args[which] = "relative"
    monkeypatch.chdir(tmp_path)

    assert _main()(
        [
            "provider-isolation-environment-manifest",
            "--root",
            args["root"],
            "--provider-prefix",
            args["provider_prefix"],
            "--output",
            args["output"],
        ]
    ) != 0
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_rejects_existing_output_without_replacing_it(
    tmp_path: Path, capsys
) -> None:
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    output.write_bytes(b"keep")
    output.chmod(0o600)
    assert _invoke(source, output) != 0
    assert output.read_bytes() == b"keep"
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_rejects_symlink_output_without_following_it(
    tmp_path: Path, capsys
) -> None:
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    target = tmp_path / "target"
    target.write_bytes(b"keep")
    output.symlink_to(target)
    assert _invoke(source, output) != 0
    assert output.is_symlink()
    assert target.read_bytes() == b"keep"
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


@pytest.mark.parametrize("mode", [0o755, 0o770, 0o777])
def test_cli_requires_preexisting_controller_owned_0700_output_directory(
    tmp_path: Path, capsys, mode: int
) -> None:
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    output.parent.chmod(mode)
    assert _invoke(source, output) != 0
    assert not output.exists()
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_rejects_output_directory_xattrs(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    os.setxattr(output.parent, "user.task1a", b"value")
    assert _invoke(source, output) != 0
    assert not output.exists()
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_rejects_untrusted_or_symlinked_ancestor(
    tmp_path: Path, capsys
) -> None:
    source = _source(tmp_path)
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)
    output = link / "manifest.json"
    assert _invoke(source, output) != 0
    assert not (real / "manifest.json").exists()
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


@pytest.mark.parametrize("mode", [0o770, 0o707])
def test_cli_rejects_nonsticky_group_or_world_writable_output_ancestor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mode: int,
) -> None:
    source = _source(tmp_path)
    ancestor = tmp_path / "untrusted-ancestor"
    ancestor.mkdir(mode=0o700)
    output_parent = ancestor / "controller-output"
    output_parent.mkdir(mode=0o700)
    ancestor.chmod(mode)
    output = output_parent / "manifest.json"

    assert _invoke(source, output) != 0
    assert not output.exists()
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_revalidates_every_output_ancestor_edge_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    ancestor = tmp_path / "output-ancestor"
    ancestor.mkdir(mode=0o700)
    output_parent = ancestor / "controller-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "manifest.json"
    held_ancestor = tmp_path / "held-output-ancestor"
    replacement_ancestor = tmp_path / "replacement-output-ancestor"
    replacement_ancestor.mkdir(mode=0o700)
    real_build = command._build_manifest_from_pinned_source
    exchanged = False

    def exchange_ancestor_after_build(*args, **kwargs):
        nonlocal exchanged
        manifest = real_build(*args, **kwargs)
        ancestor.rename(held_ancestor)
        (held_ancestor / output_parent.name).rename(
            replacement_ancestor / output_parent.name
        )
        replacement_ancestor.rename(ancestor)
        exchanged = True
        return manifest

    monkeypatch.setattr(
        command,
        "_build_manifest_from_pinned_source",
        exchange_ancestor_after_build,
    )

    assert _invoke(source, output) != 0
    assert exchanged
    assert not output.exists()
    assert held_ancestor.is_dir()
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


@pytest.mark.parametrize("direction", ["inside", "contains"])
def test_cli_output_and_source_overlap_is_denied_both_directions(
    tmp_path: Path, capsys, direction: str
) -> None:
    if direction == "inside":
        source = _source(tmp_path)
        directory = source / "controller-output"
        directory.mkdir(mode=0o700)
        output = directory / "manifest.json"
    else:
        authority = tmp_path / "authority"
        authority.mkdir(mode=0o700)
        source = _source(authority)
        output = authority / "manifest.json"
    assert _invoke(source, output) != 0
    assert not output.exists()
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_rejects_output_basename_already_scanned_as_source_entry(
    tmp_path: Path, capsys
) -> None:
    source = _source(tmp_path)
    existing = source / "opt" / "manifest.json"
    existing.write_bytes(b"source member")
    existing.chmod(0o600)
    output = _private_output(tmp_path)
    assert _invoke(source, output) != 0
    assert existing.read_bytes() == b"source member"
    assert not output.exists()
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_fsyncs_file_before_atomic_publish_then_fsyncs_parent(
    tmp_path: Path, monkeypatch
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    observed: list[str] = []
    real_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        observed.append(
            "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "regular"
        )
        real_fsync(fd)

    monkeypatch.setattr(command.os, "fsync", recording_fsync)
    assert _invoke(source, output) == 0
    assert observed == ["regular", "directory"]


def test_cli_file_fsync_failure_leaves_no_output_or_temporary_entry(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    real_fsync = os.fsync

    def failing_file_fsync(fd: int) -> None:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("injected file sync failure")
        real_fsync(fd)

    monkeypatch.setattr(command.os, "fsync", failing_file_fsync)
    assert _invoke(source, output) != 0
    assert list(output.parent.iterdir()) == []
    assert "injected file sync failure" not in capsys.readouterr().err


def test_cli_atomic_publish_race_never_replaces_competing_output(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    real_link = getattr(command, "_link_unnamed_noreplace", None)

    def create_competitor_then_link(
        manifest_fd: int, parent_fd: int, destination_name: str
    ) -> None:
        competitor_fd = os.open(
            destination_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            os.write(competitor_fd, b"competing controller output")
        finally:
            os.close(competitor_fd)
        assert real_link is not None
        real_link(manifest_fd, parent_fd, destination_name)

    monkeypatch.setattr(
        command,
        "_link_unnamed_noreplace",
        create_competitor_then_link,
        raising=False,
    )
    assert _invoke(source, output) != 0
    assert output.read_bytes() == b"competing controller output"
    assert [entry.name for entry in output.parent.iterdir()] == [output.name]
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_invalid_diagnostic_is_deterministic_and_redacted(
    tmp_path: Path, capsys
) -> None:
    source = _source(tmp_path)
    first = _private_output(tmp_path)
    first.write_bytes(b"first")
    first.chmod(0o600)
    assert _invoke(source, first) != 0
    first_error = capsys.readouterr().err

    second_directory = tmp_path / "controller-output-secret-omega"
    second_directory.mkdir(mode=0o700)
    second = second_directory / "secret-beta.json"
    second.write_bytes(b"second")
    second.chmod(0o600)
    assert _invoke(source, second) != 0
    second_error = capsys.readouterr().err

    assert first_error == second_error
    assert "provider_isolation_environment_invalid" in first_error
    assert "secret" not in second_error
    assert str(tmp_path) not in second_error


def test_runtime_assembly_requires_exact_digest_printed_by_cli(
    tmp_path: Path, capsys
) -> None:
    api = _environment_api()
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    assert _invoke(source, output) == 0
    digest = capsys.readouterr().out.strip()
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=digest,
    )
    snapshot.close()

    source_file = source / PROVIDER_PREFIX.lstrip("/") / "bin" / "python"
    source_file.write_bytes(b"changed")
    source_file.chmod(0o755)
    with pytest.raises(api.ProviderIsolationEnvironmentError) as exc_info:
        api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            tmp_path / "different-run",
            expected_digest=digest,
        )
    assert exc_info.value.code == "provider_isolation_environment_mismatch"


def test_cli_output_parent_exchange_never_publishes_to_detached_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    held_parent = tmp_path / "held-output-parent"
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    sentinel = external / "must-not-touch"
    sentinel.write_bytes(b"external")
    sentinel.chmod(0o640)
    sentinel_state = _source_state(external)
    real_build = command._build_manifest_from_pinned_source

    def exchange_after_build(*args, **kwargs):
        manifest = real_build(*args, **kwargs)
        output.parent.rename(held_parent)
        output.parent.symlink_to(external, target_is_directory=True)
        return manifest

    monkeypatch.setattr(
        command,
        "_build_manifest_from_pinned_source",
        exchange_after_build,
        raising=False,
    )

    assert _invoke(source, output) != 0
    assert not (held_parent / output.name).exists()
    assert not (external / output.name).exists()
    assert _source_state(external) == sentinel_state
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_source_root_exchange_invalidates_manifest_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    held_source = tmp_path / "held-source"
    replacement_parent = tmp_path / "replacement-parent"
    replacement_parent.mkdir(mode=0o700)
    replacement = _source(replacement_parent)
    replacement_state = _source_state(replacement)
    real_build = command._build_manifest_from_pinned_source

    def exchange_source_after_build(*args, **kwargs):
        manifest = real_build(*args, **kwargs)
        source.rename(held_source)
        source.symlink_to(replacement, target_is_directory=True)
        return manifest

    monkeypatch.setattr(
        command,
        "_build_manifest_from_pinned_source",
        exchange_source_after_build,
    )

    assert _invoke(source, output) != 0
    assert not output.exists()
    assert _source_state(replacement) == replacement_state
    assert "provider_isolation_environment_invalid" in capsys.readouterr().err


def test_cli_unnamed_temp_has_no_directory_entry_and_publishes_exact_held_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    real_link = getattr(command, "_link_unnamed_noreplace", None)
    entries_before_link: list[str] | None = None
    held_identity: tuple[int, int] | None = None
    held_payload: bytes | None = None

    def inspect_then_link(
        manifest_fd: int,
        parent_fd: int,
        destination_name: str,
    ) -> None:
        nonlocal entries_before_link, held_identity, held_payload
        entries_before_link = os.listdir(parent_fd)
        held = os.fstat(manifest_fd)
        held_identity = (held.st_dev, held.st_ino)
        held_payload = os.pread(manifest_fd, held.st_size, 0)
        assert held.st_nlink == 0
        assert real_link is not None
        real_link(manifest_fd, parent_fd, destination_name)

    monkeypatch.setattr(
        command,
        "_link_unnamed_noreplace",
        inspect_then_link,
        raising=False,
    )

    assert _invoke(source, output) == 0
    assert entries_before_link == []
    assert held_identity is not None
    assert held_payload == output.read_bytes()
    linked = output.stat()
    assert (linked.st_dev, linked.st_ino) == held_identity
    assert [entry.name for entry in output.parent.iterdir()] == [output.name]


def test_cli_final_authority_recheck_detects_output_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    api = _environment_api()
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    expected = api.build_provider_environment_manifest(
        source,
        PROVIDER_PREFIX,
    ).canonical_json
    held_original = output.parent / ".held-original-manifest"
    foreign_payload = b"foreign controller output"
    real_require_parent = command._require_output_parent_binding
    authority_checks = 0
    substituted = False

    def substitute_during_final_authority_check(
        requested_path: Path,
        parent_fd: int,
        expected_stat: os.stat_result,
    ) -> None:
        nonlocal authority_checks, substituted
        real_require_parent(requested_path, parent_fd, expected_stat)
        authority_checks += 1
        if substituted:
            return
        try:
            os.stat(
                output.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        os.rename(
            output.name,
            held_original.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        foreign_fd = os.open(
            output.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            os.write(foreign_fd, foreign_payload)
        finally:
            os.close(foreign_fd)
        substituted = True

    monkeypatch.setattr(
        command,
        "_require_output_parent_binding",
        substitute_during_final_authority_check,
    )

    assert _invoke(source, output) != 0
    assert authority_checks >= 1
    assert substituted
    assert held_original.read_bytes() == expected
    assert output.read_bytes() == foreign_payload
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "provider_isolation_environment_invalid" in captured.err


def test_cli_parent_fsync_failure_deletes_nothing_and_makes_no_name_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = importlib.import_module(
        "orchestrator.cli.commands.provider_isolation_environment_manifest"
    )
    api = _environment_api()
    source = _source(tmp_path)
    output = _private_output(tmp_path)
    expected = api.build_provider_environment_manifest(
        source,
        PROVIDER_PREFIX,
    ).canonical_json
    held_original = output.parent / ".held-original-manifest"
    foreign_payload = b"foreign controller output"
    real_fsync = os.fsync
    failed_once = False

    def fail_first_parent_fsync(fd: int) -> None:
        nonlocal failed_once
        if stat.S_ISDIR(os.fstat(fd).st_mode) and not failed_once:
            failed_once = True
            os.rename(
                output.name,
                held_original.name,
                src_dir_fd=fd,
                dst_dir_fd=fd,
            )
            foreign_fd = os.open(
                output.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
                dir_fd=fd,
            )
            try:
                os.write(foreign_fd, foreign_payload)
            finally:
                os.close(foreign_fd)
            raise OSError("injected parent fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(command.os, "fsync", fail_first_parent_fsync)

    assert _invoke(source, output) != 0
    assert failed_once
    assert held_original.read_bytes() == expected
    assert output.read_bytes() == foreign_payload
    assert sorted(entry.name for entry in output.parent.iterdir()) == sorted(
        [held_original.name, output.name]
    )
    first_error = capsys.readouterr().err
    assert "injected parent fsync failure" not in first_error

    assert _invoke(source, output) != 0
    assert held_original.read_bytes() == expected
    assert output.read_bytes() == foreign_payload
    assert sorted(entry.name for entry in output.parent.iterdir()) == sorted(
        [held_original.name, output.name]
    )
    assert capsys.readouterr().err == first_error
