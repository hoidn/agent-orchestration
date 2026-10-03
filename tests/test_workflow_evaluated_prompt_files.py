from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from orchestrator.deps.content_snapshot import (
    MAX_INJECTION_BYTES,
    AuthoredDependencyRow,
    ContentDependencySnapshotError,
    snapshot_content_dependencies,
    snapshot_content_dependencies_with_sha256,
)
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow.prompting import PromptComposer


def _track_reads(monkeypatch: pytest.MonkeyPatch, target: Path) -> list[Path]:
    calls: list[Path] = []
    original = Path.open

    def open_file(path: Path, mode: str = "r", *args, **kwargs):
        if path == target and mode in {"r", "rb"}:
            calls.append(path)
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    return calls


def _dependency_row(
    role: str,
    index: int,
    relpath: str,
    target: str | None,
) -> AuthoredDependencyRow:
    return AuthoredDependencyRow(
        role=role,
        authored_index=index,
        binding_ref=f"binding-{role}-{index}",
        evaluated_relpath=relpath,
        canonical_target=target,
    )


def _contract_error(message: str, context: dict[str, object] | None = None) -> dict[str, object]:
    return {"message": message, "context": context}


def test_raw_text_reader_hashes_one_read_and_keeps_text_mode_newlines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator._common.io_text import read_text_with_sha256

    path = tmp_path / "prompt.md"
    raw = b"alpha\r\nbeta\rgamma\n"
    path.write_bytes(raw)
    expected = path.read_text()
    calls = _track_reads(monkeypatch, path)
    text, digest = read_text_with_sha256(path)

    assert text == expected
    assert digest == "sha256:" + sha256(raw).hexdigest()
    assert calls == [path]


def test_asset_reader_hashes_raw_utf8_and_legacy_read_keeps_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = tmp_path / "workflow.orc"
    workflow.write_text("", encoding="utf-8")
    path = tmp_path / "prompt.md"
    raw = "α\r\nβ\r".encode("utf-8")
    path.write_bytes(raw)
    expected = path.read_text(encoding="utf-8")
    resolver = WorkflowAssetResolver(workflow)
    calls = _track_reads(monkeypatch, path)

    text, digest = resolver.read_text_with_sha256("prompt.md")

    assert text == expected
    assert digest == "sha256:" + sha256(raw).hexdigest()
    assert calls == [path]
    calls.clear()
    assert resolver.read_text("prompt.md") == expected
    assert calls == [path]


def test_prompt_input_absence_empty_and_present_file_have_distinct_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    step = {"input_file": "prompt.md"}
    path = tmp_path / "prompt.md"
    calls = _track_reads(monkeypatch, path)
    absent = composer.read_prompt_source_with_sha256(
        step,
        step_name="provider",
        contract_violation_result=_contract_error,
    )
    assert (absent, calls) == (("", None, None), [])
    legacy_absent = composer.read_prompt_source(
        step, step_name="provider", contract_violation_result=_contract_error
    )
    assert (legacy_absent, calls) == (("", None), [])

    path.write_bytes(b"")
    empty = composer.read_prompt_source_with_sha256(
        step,
        step_name="provider",
        contract_violation_result=_contract_error,
    )
    assert (empty, calls) == (("", "sha256:" + sha256(b"").hexdigest(), None), [path])
    calls.clear()
    legacy_empty = composer.read_prompt_source(
        step, step_name="provider", contract_violation_result=_contract_error
    )
    assert (legacy_empty, calls) == (("", None), [path])
    calls.clear()

    raw = b"first\r\nsecond\r"
    path.write_bytes(raw)
    expected = path.read_text()
    calls.clear()
    present = composer.read_prompt_source_with_sha256(
        step,
        step_name="provider",
        contract_violation_result=_contract_error,
    )
    assert (present, calls) == (
        (expected, "sha256:" + sha256(raw).hexdigest(), None),
        [path],
    )
    calls.clear()
    legacy_present = composer.read_prompt_source(
        step, step_name="provider", contract_violation_result=_contract_error
    )
    assert (legacy_present, calls) == ((expected, None), [path])


def test_prompt_asset_errors_keep_legacy_diagnostic_shape(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.orc"
    workflow.write_text("", encoding="utf-8")
    composer = PromptComposer(
        workspace=tmp_path,
        asset_resolver=WorkflowAssetResolver(workflow),
    )
    step = {"asset_file": "missing.md"}

    captured = composer.read_prompt_source_with_sha256(
        step,
        step_name="provider",
        contract_violation_result=_contract_error,
    )
    legacy = composer.read_prompt_source(
        step,
        step_name="provider",
        contract_violation_result=_contract_error,
    )

    assert captured[0:2] == ("", None)
    assert captured[2] == legacy[1]
    assert captured[2]["context"]["reason"] == "asset_file_read_failed"


def test_dependency_snapshot_hashes_full_raw_bytes_once_per_canonical_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "deps/large.txt"
    path = tmp_path / target
    path.parent.mkdir()
    prefix = b"x" * MAX_INJECTION_BYTES
    first_raw = prefix + b"x" * 32 + b"tail-one"
    path.write_bytes(first_raw)
    rows = (
        _dependency_row("required", 0, target, target),
        _dependency_row("optional", 0, "alias.txt", target),
        _dependency_row("optional", 1, "missing.txt", None),
    )
    calls = _track_reads(monkeypatch, path)

    first, first_digests = snapshot_content_dependencies_with_sha256(tmp_path, rows)

    group = first.canonical_groups[0]
    assert (
        group.normalized_bytes,
        group.normalized_total_bytes,
        first_digests[target],
        set(first_digests),
        group.authored_rows,
        first.absent_rows,
        calls,
    ) == (
        prefix,
        len(first_raw),
        "sha256:" + sha256(first_raw).hexdigest(),
        {target},
        (rows[0], rows[1]),
        (rows[2],),
        [path],
    )

    second_raw = prefix + b"x" * 32 + b"tail-two"
    path.write_bytes(second_raw)
    calls.clear()
    second, second_digests = snapshot_content_dependencies_with_sha256(tmp_path, rows)

    assert (
        second.canonical_groups[0].normalized_bytes,
        second_digests[target],
        second_digests[target] != first_digests[target],
        calls,
    ) == (
        group.normalized_bytes,
        "sha256:" + sha256(second_raw).hexdigest(),
        True,
        [path],
    )


def test_dependency_snapshot_keeps_required_missing_and_utf8_errors(
    tmp_path: Path,
) -> None:
    missing = _dependency_row("required", 0, "missing.txt", "missing.txt")
    with pytest.raises(ContentDependencySnapshotError) as missing_error:
        snapshot_content_dependencies(tmp_path, (missing,))
    assert missing_error.value.category == "unreadable_dependency"
    assert missing_error.value.operation == "read"
    assert missing_error.value.row == missing

    invalid_path = tmp_path / "invalid.txt"
    invalid_path.write_bytes(b"\xff")
    invalid = _dependency_row("required", 0, "invalid.txt", "invalid.txt")
    with pytest.raises(ContentDependencySnapshotError) as decode_error:
        snapshot_content_dependencies(tmp_path, (invalid,))
    assert decode_error.value.category == "invalid_utf8_dependency"
    assert decode_error.value.operation == "decode"
    assert decode_error.value.row == invalid
