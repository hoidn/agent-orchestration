from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from orchestrator.deps.injector import DependencyInjector
from orchestrator.deps.resolver import DependencyResolver
from orchestrator.deps.content_snapshot import (
    MAX_INJECTION_BYTES,
    MAX_INSTRUCTION_BYTES,
    TRUNCATION_SUMMARY_RESERVE_BYTES,
    AuthoredDependencyRow,
    CanonicalDependencyGroup,
    DependencyContent,
    DependencyContentSnapshot,
    DependencyGroupTruncation,
    build_content_snapshot,
    render_content_snapshot,
)


def _row(
    role: str,
    index: int,
    binding: str,
    relpath: str,
    target: str | None,
) -> AuthoredDependencyRow:
    return AuthoredDependencyRow(
        role=role,
        authored_index=index,
        binding_ref=binding,
        evaluated_relpath=relpath,
        canonical_target=target,
    )


def _snapshot(*items: tuple[AuthoredDependencyRow, bytes]):
    rows = tuple(row for row, _ in items)
    payloads = tuple(
        DependencyContent(canonical_target=row.canonical_target, normalized_bytes=content)
        for row, content in items
        if row.canonical_target is not None
    )
    return build_content_snapshot(rows, payloads)


def test_snapshot_groups_aliases_without_losing_authored_evidence() -> None:
    rows = (
        _row("optional", 0, "optional_ref", "alias.txt", "real/a.txt"),
        _row("required", 0, "required_ref", "real/a.txt", "real/a.txt"),
        _row("optional", 1, "missing_ref", "missing.txt", None),
        _row("required", 1, "z_ref", "z.txt", "z.txt"),
    )
    snapshot = build_content_snapshot(
        rows,
        (
            DependencyContent("z.txt", b"z"),
            DependencyContent("real/a.txt", b"a"),
        ),
    )

    assert snapshot.authored_rows == (rows[1], rows[3], rows[0], rows[2])
    assert snapshot.absent_rows == (rows[2],)
    assert tuple(group.canonical_target for group in snapshot.canonical_groups) == (
        "real/a.txt",
        "z.txt",
    )
    aliased = snapshot.canonical_groups[0]
    assert aliased.effective_role == "required"
    assert aliased.authored_rows == (rows[1], rows[0])
    assert aliased.normalized_bytes == b"a"

    with pytest.raises(FrozenInstanceError):
        aliased.effective_role = "optional"  # type: ignore[misc]


def test_snapshot_optional_only_absence_selects_optional_default() -> None:
    snapshot = build_content_snapshot(
        (_row("optional", 0, "maybe", "missing.txt", None),),
        (),
    )
    calls: list[tuple[str, bool]] = []

    rendered = render_content_snapshot(
        snapshot,
        instruction=None,
        default_instruction=lambda mode, required: calls.append((mode, required)) or "sentinel",
    )

    assert rendered.block == b"sentinel"
    assert calls == [("content", False)]


def test_renderable_snapshot_rejects_absent_required_rows_in_builder_and_constructor() -> None:
    required_absent = _row("required", 0, "required", "missing.txt", None)

    with pytest.raises(ValueError, match="absent dependency rows must be optional"):
        build_content_snapshot((required_absent,), ())
    with pytest.raises(ValueError, match="absent dependency rows must be optional"):
        DependencyContentSnapshot(
            authored_rows=(required_absent,),
            absent_rows=(required_absent,),
            canonical_groups=(),
            retained_content_bytes=0,
        )


def test_snapshot_retains_one_attempt_wide_content_budget_across_many_groups() -> None:
    group_count = 80
    rows = tuple(
        _row("required", index, f"ref-{index}", f"f-{index:03}.txt", f"f-{index:03}.txt")
        for index in range(group_count)
    )
    payloads = tuple(
        DependencyContent(row.canonical_target, b"x" * (MAX_INJECTION_BYTES // 2))
        for row in rows
    )

    snapshot = build_content_snapshot(rows, payloads)

    assert sum(len(group.normalized_bytes) for group in snapshot.canonical_groups) <= MAX_INJECTION_BYTES
    assert sum(group.normalized_total_bytes for group in snapshot.canonical_groups) > 30 * MAX_INJECTION_BYTES
    assert snapshot.retained_content_bytes == MAX_INJECTION_BYTES


@pytest.mark.parametrize("length", [261629, 261630])
def test_render_accepts_instruction_cap_boundary(length: int) -> None:
    rendered = render_content_snapshot(
        build_content_snapshot((_row("optional", 0, "missing", "missing", None),), ()),
        instruction="i" * length,
    )
    assert len(rendered.block) == length


def test_render_rejects_instruction_over_cap_in_encoded_bytes() -> None:
    snapshot = build_content_snapshot((_row("optional", 0, "missing", "missing", None),), ())
    with pytest.raises(ValueError, match="dependency_instruction_exceeds_byte_limit"):
        render_content_snapshot(snapshot, instruction="i" * 261631)
    with pytest.raises(ValueError, match="dependency_instruction_exceeds_byte_limit"):
        render_content_snapshot(snapshot, instruction="é" * 130816)


def test_render_uses_strict_utf8_prefix_and_exact_markers() -> None:
    target = "multibyte.txt"
    instruction = "inspect"
    content = ("é" * MAX_INJECTION_BYTES).encode()
    snapshot = _snapshot((_row("required", 0, "ref", target, target), content))

    rendered = render_content_snapshot(snapshot, instruction=instruction)
    truncation = rendered.group_truncations[0]

    assert len(rendered.block) <= MAX_INJECTION_BYTES
    assert rendered.block.decode("utf-8")
    assert truncation.status == "truncated"
    assert truncation.shown_bytes > 0
    assert truncation.shown_bytes % 2 == 0
    assert b"\n... (truncated)" in rendered.block
    assert rendered.block.endswith(rendered.summary)


@pytest.mark.parametrize("delta, expected", [(-1, False), (0, False), (1, True)])
def test_render_cap_uses_exact_pre_truncation_bytes(delta: int, expected: bool) -> None:
    target = "a"
    instruction = "i"
    overhead = len(f"\n\n=== File: {target} (0/0 bytes) ===\n".encode())
    # Digit widths affect the header, so find a content size with the requested exact total.
    requested = MAX_INJECTION_BYTES + delta
    content_size = requested - len(instruction.encode()) - overhead
    while True:
        header = f"\n\n=== File: {target} ({content_size}/{content_size} bytes) ===\n".encode()
        adjusted = requested - len(instruction.encode()) - len(header)
        if adjusted == content_size:
            break
        content_size = adjusted
    snapshot = _snapshot((_row("required", 0, "ref", target, target), b"x" * content_size))

    rendered = render_content_snapshot(snapshot, instruction=instruction)

    assert rendered.pre_truncation_bytes == requested
    assert rendered.was_truncated is expected
    assert len(rendered.block) <= MAX_INJECTION_BYTES


def test_render_first_partial_stops_all_later_groups() -> None:
    snapshot = _snapshot(
        (_row("required", 0, "a", "a", "a"), b"a" * MAX_INJECTION_BYTES),
        (_row("required", 1, "b", "b", "b"), b"later"),
        (_row("required", 2, "c", "c", "c"), b"latest"),
    )

    rendered = render_content_snapshot(snapshot, instruction="i")

    assert tuple(row.status for row in rendered.group_truncations) == (
        "truncated",
        "omitted",
        "omitted",
    )
    assert b"=== File: b " not in rendered.block
    assert b"=== File: c " not in rendered.block


def test_render_omits_first_group_when_no_positive_prefix_fits() -> None:
    import orchestrator.deps.content_snapshot as owner

    total_bytes = MAX_INJECTION_BYTES
    instruction = "i" * MAX_INSTRUCTION_BYTES
    marker = b"\n... (truncated)"
    target = next(
        "a" * length
        for length in range(1, 1000)
        if MAX_INJECTION_BYTES
        - len(instruction)
        - len(
            owner._render_truncation_summary(
                (DependencyGroupTruncation("a" * length, "truncated", 1, total_bytes),)
            )
        )
        - len(marker)
        - len(f"\n\n=== File: {'a' * length} (1/{total_bytes} bytes) ===\n".encode())
        == 0
    )
    snapshot = _snapshot(
        (_row("required", 0, "a", target, target), b"a" * total_bytes)
    )

    rendered = render_content_snapshot(snapshot, instruction=instruction)

    assert rendered.group_truncations[0].status == "omitted"
    assert b"=== File:" not in rendered.block
    assert rendered.block.endswith(rendered.summary)


def test_render_validates_truncation_summary_reserve(monkeypatch: pytest.MonkeyPatch) -> None:
    import orchestrator.deps.content_snapshot as owner

    snapshot = _snapshot((_row("required", 0, "a", "a", "a"), b"x" * MAX_INJECTION_BYTES))
    monkeypatch.setattr(owner, "_render_truncation_summary", lambda *_: b"s" * TRUNCATION_SUMMARY_RESERVE_BYTES)
    rendered = render_content_snapshot(snapshot, instruction="i")
    assert len(rendered.summary) == 512

    monkeypatch.setattr(owner, "_render_truncation_summary", lambda *_: b"s" * (TRUNCATION_SUMMARY_RESERVE_BYTES + 1))
    with pytest.raises(ValueError, match="dependency_truncation_summary_exceeds_reserve"):
        render_content_snapshot(snapshot, instruction="i")


def test_render_uses_largest_prefix_allowed_by_actual_summary() -> None:
    target = "large.txt"
    total_bytes = MAX_INJECTION_BYTES * 2
    snapshot = _snapshot(
        (_row("required", 0, "large", target, target), b"x" * total_bytes)
    )

    rendered = render_content_snapshot(snapshot, instruction="i")
    truncation = rendered.group_truncations[0]
    marker = b"\n... (truncated)"
    available = (
        MAX_INJECTION_BYTES
        - 1
        - len(rendered.summary)
        - len(marker)
    )

    def fits(shown: int) -> bool:
        header = f"\n\n=== File: {target} ({shown}/{total_bytes} bytes) ===\n".encode()
        return len(header) + shown <= available

    largest = max(shown for shown in range(available + 1) if fits(shown))
    assert truncation.status == "truncated"
    assert truncation.shown_bytes == largest
    assert len(rendered.block) == MAX_INJECTION_BYTES
    assert not fits(largest + 1)


def test_render_truncates_when_one_byte_fits_with_actual_summary() -> None:
    import orchestrator.deps.content_snapshot as owner

    total_bytes = MAX_INJECTION_BYTES
    instruction = "i" * MAX_INSTRUCTION_BYTES
    target = next(
        "a" * length
        for length in range(1, 1000)
        if MAX_INJECTION_BYTES
        - len(instruction)
        - len(
            owner._render_truncation_summary(
                (DependencyGroupTruncation("a" * length, "truncated", 1, total_bytes),)
            )
        )
        - len(b"\n... (truncated)")
        - len(f"\n\n=== File: {'a' * length} (1/{total_bytes} bytes) ===\n".encode())
        == 1
    )
    expected_summary = owner._render_truncation_summary(
        (DependencyGroupTruncation(target, "truncated", 1, total_bytes),)
    )
    snapshot = _snapshot(
        (_row("required", 0, "a", target, target), b"x" * total_bytes)
    )

    rendered = render_content_snapshot(snapshot, instruction=instruction)

    assert rendered.group_truncations[0].status == "truncated"
    assert rendered.group_truncations[0].shown_bytes == 1
    assert rendered.summary == expected_summary
    assert len(rendered.block) == MAX_INJECTION_BYTES


def test_render_resolves_summary_budget_two_cycle_to_feasible_omission() -> None:
    import orchestrator.deps.content_snapshot as owner

    targets = tuple(
        ("00" + "a" * 110) if index == 0 else f"{index:02d}"
        for index in range(59)
    )
    rows = tuple(
        _row("required", index, f"ref-{index}", target, target)
        for index, target in enumerate(targets)
    )
    payloads = tuple(
        DependencyContent(target, b"x" * 100 if index == 9 else b"")
        for index, target in enumerate(targets)
    )
    snapshot = build_content_snapshot(rows, payloads)
    instruction = "i" * 261622

    rendered = render_content_snapshot(snapshot, instruction=instruction)

    assert tuple(row.status for row in rendered.group_truncations[:10]) == (
        *("complete" for _ in range(9)),
        "omitted",
    )
    assert len(rendered.block) <= MAX_INJECTION_BYTES

    truncated_candidate = (
        tuple(
            DependencyGroupTruncation(target, "complete", 0, 0)
            for target in targets[:9]
        )
        + (DependencyGroupTruncation(targets[9], "truncated", 1, 100),)
        + tuple(
            DependencyGroupTruncation(target, "omitted", 0, 0)
            for target in targets[10:]
        )
    )
    truncated_summary = owner._render_truncation_summary(truncated_candidate)
    first_nine_bytes = sum(
        len(f"\n\n=== File: {target} (0/0 bytes) ===\n".encode())
        for target in targets[:9]
    )
    one_byte_section = (
        len(f"\n\n=== File: {targets[9]} (1/100 bytes) ===\n".encode())
        + 1
        + len(b"\n... (truncated)")
    )
    assert len(truncated_summary) == 84
    assert (
        len(instruction) + first_nine_bytes + one_byte_section + len(truncated_summary)
        > MAX_INJECTION_BYTES
    )


def test_render_exact_complete_block() -> None:
    snapshot = _snapshot(
        (_row("required", 0, "b", "b.txt", "b.txt"), b"B\n"),
        (_row("required", 1, "a", "a.txt", "a.txt"), b"A"),
    )
    rendered = render_content_snapshot(snapshot, instruction="Read these:")
    assert rendered.block == (
        b"Read these:\n\n=== File: a.txt (1/1 bytes) ===\nA"
        b"\n\n=== File: b.txt (2/2 bytes) ===\nB\n"
    )
    assert rendered.group_truncations[0].status == "complete"
    assert rendered.summary == b""


def test_snapshot_rejects_non_contiguous_role_indices() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        build_content_snapshot(
            (_row("required", 1, "ref", "a.txt", "a.txt"),),
            (DependencyContent("a.txt", b"a"),),
        )


@pytest.mark.parametrize(
    "target",
    ("/absolute.txt", "../parent.txt", "a/../b.txt", "a\\b.txt", "./a.txt"),
)
def test_snapshot_rejects_noncanonical_posix_targets(target: str) -> None:
    with pytest.raises(ValueError, match="canonical POSIX target"):
        _row("required", 0, "ref", target, target)


def test_snapshot_rejects_missing_duplicate_and_unreferenced_payloads() -> None:
    rows = (_row("required", 0, "ref", "a.txt", "a.txt"),)
    with pytest.raises(ValueError, match="payload membership"):
        build_content_snapshot(rows, ())
    with pytest.raises(ValueError, match="unique"):
        build_content_snapshot(
            rows,
            (DependencyContent("a.txt", b"a"), DependencyContent("a.txt", b"a")),
        )
    with pytest.raises(ValueError, match="payload membership"):
        build_content_snapshot(rows, (DependencyContent("b.txt", b"b"),))


def test_public_group_rejects_duplicate_authored_row_membership() -> None:
    row = _row("required", 0, "ref", "a.txt", "a.txt")
    with pytest.raises(ValueError, match="unique"):
        CanonicalDependencyGroup(
            canonical_target="a.txt",
            effective_role="required",
            authored_rows=(row, row),
            normalized_bytes=b"a",
            normalized_total_bytes=1,
        )


def test_public_snapshot_rejects_present_row_missing_from_groups() -> None:
    row = _row("required", 0, "ref", "a.txt", "a.txt")
    with pytest.raises(ValueError, match="group membership"):
        DependencyContentSnapshot(
            authored_rows=(row,),
            absent_rows=(),
            canonical_groups=(),
            retained_content_bytes=0,
        )


def test_snapshot_copies_mutable_payload_input_to_immutable_bytes() -> None:
    mutable = bytearray(b"original")
    snapshot = build_content_snapshot(
        (_row("required", 0, "ref", "a.txt", "a.txt"),),
        (DependencyContent("a.txt", mutable),),  # type: ignore[arg-type]
    )
    mutable[:] = b"mutated!"

    assert snapshot.canonical_groups[0].normalized_bytes == b"original"
    assert isinstance(snapshot.canonical_groups[0].normalized_bytes, bytes)


def test_snapshot_many_groups_after_content_budget_are_retained_as_metadata() -> None:
    rows = tuple(
        _row("required", index, f"ref-{index}", f"f-{index:03}.txt", f"f-{index:03}.txt")
        for index in range(300)
    )
    snapshot = build_content_snapshot(
        rows,
        tuple(DependencyContent(row.canonical_target, b"x" * 4096) for row in rows),
    )

    assert len(snapshot.canonical_groups) == len(rows)
    assert snapshot.canonical_groups[-1].normalized_bytes == b""
    assert snapshot.canonical_groups[-1].normalized_total_bytes == 4096
    assert snapshot.retained_content_bytes == MAX_INJECTION_BYTES


def _old_successful_content_renderer(
    workspace: Path,
    files: list[str],
    instruction: str,
) -> str:
    """Characterization copy of the pre-Task-5 below-cap content renderer."""
    sections = [instruction]
    for file_path in files:
        full_path = workspace / file_path
        if not full_path.exists():
            continue
        content = full_path.read_text(encoding="utf-8")
        file_size = len(content.encode("utf-8"))
        sections.append(f"\n=== File: {file_path} ({file_size}/{file_size} bytes) ===")
        sections.append(content)
    return "\n".join(sections)


@pytest.mark.parametrize(
    "case, depends_on, files, inject_config, prompt, expected_default_call",
    (
        (
            "required-only",
            {"required": ["required.txt"]},
            {"required.txt": b"required"},
            {"mode": "content"},
            "prompt",
            ("content", True),
        ),
        (
            "optional-only",
            {"optional": ["optional.txt"]},
            {"optional.txt": b"optional"},
            {"mode": "content"},
            "prompt",
            ("content", False),
        ),
        (
            "mixed",
            {"required": ["required.txt"], "optional": ["optional.txt"]},
            {"required.txt": b"required", "optional.txt": b"optional"},
            {"mode": "content"},
            "prompt",
            ("content", True),
        ),
        (
            "lexicographic-order",
            {"required": ["*.txt"]},
            {"z.txt": b"z", "a.txt": b"a"},
            {"mode": "content"},
            "prompt",
            ("content", True),
        ),
        (
            "custom-instruction",
            {"required": ["required.txt"]},
            {"required.txt": b"required"},
            {"mode": "content", "instruction": "custom"},
            "prompt",
            ("content", True),
        ),
        (
            "prepend",
            {"required": ["required.txt"]},
            {"required.txt": b"required"},
            {"mode": "content", "position": "prepend"},
            "prompt",
            ("content", True),
        ),
        (
            "append",
            {"required": ["required.txt"]},
            {"required.txt": b"required"},
            {"mode": "content", "position": "append"},
            "prompt",
            ("content", True),
        ),
        (
            "optional-no-match",
            {"optional": ["missing.txt"]},
            {},
            {"mode": "content"},
            "prompt",
            ("content", False),
        ),
        (
            "crlf",
            {"required": ["newlines.txt"]},
            {"newlines.txt": b"one\r\ntwo\r\n"},
            {"mode": "content"},
            "prompt",
            ("content", True),
        ),
        (
            "lone-cr",
            {"required": ["newlines.txt"]},
            {"newlines.txt": b"one\rtwo\r"},
            {"mode": "content"},
            "prompt",
            ("content", True),
        ),
    ),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_legacy_content_compatibility_below_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    depends_on: dict[str, list[str]],
    files: dict[str, bytes],
    inject_config: dict[str, str],
    prompt: str,
    expected_default_call: tuple[str, bool],
) -> None:
    del case
    for relpath, payload in files.items():
        (tmp_path / relpath).write_bytes(payload)

    resolution = DependencyResolver(str(tmp_path)).resolve(depends_on)
    injector = DependencyInjector(str(tmp_path))
    default_calls: list[tuple[str, bool]] = []

    def select_default(mode: str, required: bool) -> str:
        default_calls.append((mode, required))
        return "default instruction sentinel"

    monkeypatch.setattr(injector, "_get_default_instruction", select_default)
    is_required = bool(depends_on.get("required"))
    result = injector.inject(
        prompt,
        resolution.files,
        inject_config,
        is_required=is_required,
    )

    instruction = inject_config.get("instruction", "default instruction sentinel")
    old_injection = _old_successful_content_renderer(tmp_path, resolution.files, instruction)
    if inject_config.get("position", "prepend") == "prepend":
        expected = old_injection + "\n\n" + prompt if prompt else old_injection
    else:
        expected = prompt + "\n\n" + old_injection if prompt else old_injection

    assert result.modified_prompt.encode("utf-8") == expected.encode("utf-8")
    assert default_calls == [expected_default_call]
