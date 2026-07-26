from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import hashlib
import inspect
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    compile_stage1_entrypoint,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.modules import resolve_module_graph
from orchestrator.workflow_lisp import reader


read_sexpr_file = reader.read_sexpr_file
FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"


def _new_trace():
    trace_type = getattr(reader, "SourceReadTrace", None)
    assert trace_type is not None, "SourceReadTrace is missing"
    return trace_type()


def _revision(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _module_source(module_name: str, *, imported_module: str | None = None) -> bytes:
    import_form = f"  (import {imported_module})\n" if imported_module is not None else ""
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.18")\n'
        f"  (defmodule {module_name})\n"
        f"{import_form}"
        "  (export Result)\n"
        "  (defrecord Result\n"
        "    (value String)))\n"
    ).encode("utf-8")


def _workflow_module_source(module_name: str) -> bytes:
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.18")\n'
        f"  (defmodule {module_name})\n"
        "  (export entry Result)\n"
        "  (defpath Report\n"
        "    :kind relpath\n"
        '    :under "artifacts/reports"\n'
        "    :must-exist true)\n"
        "  (defrecord Result\n"
        "    (report Report))\n"
        "  (defworkflow entry\n"
        "    ((report Report))\n"
        "    -> Result\n"
        "    (record Result\n"
        "      :report report)))\n"
    ).encode("utf-8")


def _single_file_workflow_source() -> bytes:
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.18")\n'
        "  (defpath Report\n"
        "    :kind relpath\n"
        '    :under "artifacts/reports"\n'
        "    :must-exist true)\n"
        "  (defrecord Result\n"
        "    (report Report))\n"
        "  (defworkflow entry\n"
        "    ((report Report))\n"
        "    -> Result\n"
        "    (record Result\n"
        "      :report report)))\n"
    ).encode("utf-8")


def _wcc_effect_workflow_source() -> bytes:
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.18")\n'
        "  (defpath Report\n"
        "    :kind relpath\n"
        '    :under "artifacts/reports"\n'
        "    :must-exist true)\n"
        "  (defrecord Result\n"
        "    (report Report))\n"
        "  (defworkflow helper\n"
        "    ((report Report))\n"
        "    -> Result\n"
        "    (record Result\n"
        "      :report report))\n"
        "  (defworkflow entry\n"
        "    ((report Report))\n"
        "    -> Result\n"
        "    (call helper\n"
        "      :report report)))\n"
    ).encode("utf-8")


def _nominal_guidance_workflow_source() -> bytes:
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.18")\n'
        "  (defmodule nominal_guidance)\n"
        "  (export entry Decision)\n"
        "  (defrecord Decision\n"
        "    (approved Bool))\n"
        "  (defworkflow entry ()\n"
        "    -> (result Decision\n"
        "         :example (record Decision :approved true))\n"
        "    (provider-result providers.decide\n"
        "      :prompt prompts.decide\n"
        "      :inputs ()\n"
        "      :returns (result Decision\n"
        "        :example (record Decision :approved true)))))\n"
    ).encode("utf-8")


def test_read_sexpr_file_reads_once_and_retains_exact_and_parser_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.orc"
    payload = (
        b"(workflow-lisp\r\n"
        b'  (:language "0.1")\r\n'
        b'  (:target-dsl "2.18"))\r\n'
    )
    calls: list[Path] = []

    def read_bytes_once(self: Path) -> bytes:
        calls.append(self)
        return payload

    monkeypatch.setattr(Path, "read_bytes", read_bytes_once)
    parsed_text: list[str] = []
    real_read_sexpr_text = reader.read_sexpr_text

    def capture_parser_text(source: str, *, source_path: str):
        parsed_text.append(source)
        return real_read_sexpr_text(source, source_path=source_path)

    monkeypatch.setattr(reader, "read_sexpr_text", capture_parser_text)
    trace = _new_trace()

    tree = read_sexpr_file(path, source_read_trace=trace)

    assert calls == [path.resolve()]
    assert parsed_text == [payload.decode("utf-8").replace("\r\n", "\n")]
    assert tree.span.start.path == str(path)
    assert trace.records[0].canonical_path == path.resolve()
    assert trace.records[0].revision == _revision(payload)
    assert tuple(field.name for field in fields(trace.records[0])) == (
        "canonical_path",
        "revision",
        "ordinal",
    )


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_read_sexpr_file_preserves_legacy_universal_newline_ast_and_spans(
    tmp_path: Path,
    newline: bytes,
) -> None:
    path = tmp_path / "source.orc"
    payload = newline.join(
        (
            b"(workflow-lisp",
            b'  (:language "0.1")',
            b'  (:target-dsl "2.18"))',
            b"",
        )
    )
    path.write_bytes(payload)
    legacy_text = path.read_text(encoding="utf-8")
    legacy_tree = reader.read_sexpr_text(legacy_text, source_path=str(path))
    trace = _new_trace()

    tree = read_sexpr_file(path, source_read_trace=trace)

    assert tree == legacy_tree
    assert tree.span.end.line == 3
    assert tree.span.end.column == 24
    assert tree.span.end.offset == len(legacy_text.rstrip("\n"))
    assert trace.records[0].revision == _revision(payload)


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_read_sexpr_file_preserves_legacy_universal_newline_diagnostics(
    tmp_path: Path,
    newline: bytes,
) -> None:
    path = tmp_path / "invalid.orc"
    payload = newline.join(
        (
            b"(workflow-lisp",
            b'  (:language "0.1")',
            b'  (:target-dsl "2.18")',
            b"",
        )
    )
    path.write_bytes(payload)
    legacy_text = path.read_text(encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as legacy_exc:
        reader.read_sexpr_text(legacy_text, source_path=str(path))
    trace = _new_trace()
    with pytest.raises(LispFrontendCompileError) as traced_exc:
        read_sexpr_file(path, source_read_trace=trace)

    assert traced_exc.value.diagnostics == legacy_exc.value.diagnostics
    assert trace.records[0].revision == _revision(payload)


def test_trace_keeps_exact_editor_equality_separate_from_parser_normalization(
    tmp_path: Path,
) -> None:
    crlf_path = tmp_path / "crlf.orc"
    lf_path = tmp_path / "lf.orc"
    crlf_path.write_bytes(b"(item\r\n  value)\r\n")
    lf_path.write_bytes(b"(item\n  value)\n")
    trace = _new_trace()

    crlf_views = reader._read_source_file_views(crlf_path, source_read_trace=trace)
    lf_views = reader._read_source_file_views(lf_path, source_read_trace=trace)
    crlf_record, lf_record = trace.records

    assert crlf_views.parser_text == lf_views.parser_text
    assert crlf_views.raw_decoded_text != lf_views.raw_decoded_text
    assert crlf_views.raw_decoded_text != lf_views.parser_text
    assert lf_views.raw_decoded_text != crlf_views.raw_decoded_text
    assert crlf_record.revision != lf_record.revision


def test_trace_accepts_identical_rereads_and_rejects_changed_rereads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_a = (tmp_path / "a.orc").resolve()
    path_b = (tmp_path / "b.orc").resolve()
    payloads = {
        path_a: [b"(a)", b"(a)"],
        path_b: [b"(b)"],
    }

    def stable_read(self: Path) -> bytes:
        return payloads[self].pop(0)

    monkeypatch.setattr(Path, "read_bytes", stable_read)
    stable_trace = _new_trace()
    read_sexpr_file(path_a, source_read_trace=stable_trace)
    read_sexpr_file(path_b, source_read_trace=stable_trace)
    read_sexpr_file(path_a, source_read_trace=stable_trace)

    assert tuple(record.ordinal for record in stable_trace.records) == (0, 1, 2)
    assert tuple(record.canonical_path for record in stable_trace.records) == (
        path_a,
        path_b,
        path_a,
    )
    assert stable_trace.revision_vector == (
        (path_a, _revision(b"(a)")),
        (path_b, _revision(b"(b)")),
    )
    with pytest.raises(FrozenInstanceError):
        stable_trace.records[0].revision = "changed"  # type: ignore[misc]

    payloads = {
        path_a: [b"(a)", b"(changed)"],
        path_b: [b"(b)"],
    }
    changed_trace = _new_trace()
    read_sexpr_file(path_a, source_read_trace=changed_trace)
    read_sexpr_file(path_b, source_read_trace=changed_trace)

    with pytest.raises(RuntimeError, match="changed during one compiler read trace"):
        read_sexpr_file(path_a, source_read_trace=changed_trace)


def test_trace_distinguishes_missing_unreadable_and_invalid_utf8(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = (tmp_path / "missing.orc").resolve()
    unreadable = (tmp_path / "unreadable.orc").resolve()
    invalid = (tmp_path / "invalid.orc").resolve()

    def failing_read(self: Path) -> bytes:
        if self == missing:
            raise FileNotFoundError(self)
        if self == unreadable:
            raise PermissionError(self)
        if self == invalid:
            return b"\xff"
        raise AssertionError(self)

    monkeypatch.setattr(Path, "read_bytes", failing_read)
    trace = _new_trace()

    with pytest.raises(FileNotFoundError):
        read_sexpr_file(missing, source_read_trace=trace)
    with pytest.raises(PermissionError):
        read_sexpr_file(unreadable, source_read_trace=trace)
    with pytest.raises(UnicodeDecodeError):
        read_sexpr_file(invalid, source_read_trace=trace)

    assert tuple(record.revision for record in trace.records) == (
        "missing",
        "unreadable",
        _revision(b"\xff"),
    )


def test_module_graph_uses_one_collector_for_imports_and_final_entry_reread(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    entry_path = source_root / "demo" / "entry.orc"
    dependency_path = source_root / "demo" / "dependency.orc"
    entry_path.parent.mkdir(parents=True)
    entry_path.write_bytes(_module_source("demo/entry", imported_module="demo/dependency"))
    dependency_path.write_bytes(_module_source("demo/dependency"))
    trace = _new_trace()

    result = resolve_module_graph(
        entry_path,
        source_roots=(source_root,),
        source_read_trace=trace,
    )

    assert result.topological_order == ("demo/dependency", "demo/entry")
    assert tuple(record.canonical_path for record in trace.records) == (
        entry_path.resolve(),
        dependency_path.resolve(),
        entry_path.resolve(),
    )
    assert trace.revision_vector == (
        (dependency_path.resolve(), _revision(dependency_path.read_bytes())),
        (entry_path.resolve(), _revision(entry_path.read_bytes())),
    )


def test_stage1_entrypoint_has_no_source_read_trace_surface() -> None:
    assert "source_read_trace" not in inspect.signature(compile_stage1_entrypoint).parameters


def test_stage3_entrypoint_traces_every_orc_read_without_using_read_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "src"
    path = source_root / "demo" / "entry.orc"
    path.parent.mkdir(parents=True)
    source_payload = _workflow_module_source("demo/entry")
    path.write_bytes(source_payload)
    canonical_path = path.resolve()
    physical_orc_reads: list[Path] = []
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text

    def counted_read_bytes(self: Path) -> bytes:
        if self.suffix == ".orc":
            physical_orc_reads.append(self.resolve())
        return real_read_bytes(self)

    def reject_orc_read_text(self: Path, *args, **kwargs) -> str:
        if self.suffix == ".orc":
            raise AssertionError("Stage 3 must route .orc reads through exact-byte tracing")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    monkeypatch.setattr(Path, "read_text", reject_orc_read_text)
    trace = _new_trace()

    result = compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
        entry_workflow="entry",
        workspace_root=tmp_path,
        validation_profile="frontend_only",
        lowering_route="legacy",
        source_read_trace=trace,
    )

    assert result.entry_result.module.module_name == "demo/entry"
    assert physical_orc_reads
    assert tuple(record.canonical_path for record in trace.records) == tuple(
        physical_orc_reads
    )
    assert trace.revision_vector == ((canonical_path, _revision(source_payload)),)


def test_stage3_single_file_traces_lowering_source_rereads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "entry.orc"
    path.write_bytes(_single_file_workflow_source())
    physical_orc_reads: list[Path] = []
    real_read_bytes = Path.read_bytes

    def counted_read_bytes(self: Path) -> bytes:
        if self.suffix == ".orc":
            physical_orc_reads.append(self.resolve())
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    trace = _new_trace()

    result = compile_stage3_module(
        path,
        entry_workflow="entry",
        workspace_root=tmp_path,
        validation_profile="frontend_only",
        lowering_route="legacy",
        source_read_trace=trace,
    )

    assert result.typed_workflows[0].definition.name == "entry"
    assert len(physical_orc_reads) >= 3
    assert tuple(record.canonical_path for record in trace.records) == tuple(
        physical_orc_reads
    )


def test_stage3_default_wcc_route_traces_source_dependent_lowering_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "entry.orc"
    source_payload = _wcc_effect_workflow_source()
    path.write_bytes(source_payload)
    physical_orc_reads: list[Path] = []
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text

    def counted_read_bytes(self: Path) -> bytes:
        if self.suffix == ".orc":
            physical_orc_reads.append(self.resolve())
        return real_read_bytes(self)

    def reject_orc_read_text(self: Path, *args, **kwargs) -> str:
        if self.suffix == ".orc":
            raise AssertionError("WCC lowering must use the exact-byte trace seam")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    monkeypatch.setattr(Path, "read_text", reject_orc_read_text)
    trace = _new_trace()

    result = compile_stage3_module(
        path,
        entry_workflow="entry",
        workspace_root=tmp_path,
        validation_profile="frontend_only",
        source_read_trace=trace,
    )

    assert {workflow.definition.name for workflow in result.typed_workflows} == {
        "entry",
        "helper",
    }
    assert len(physical_orc_reads) >= 4
    assert tuple(record.canonical_path for record in trace.records) == tuple(
        physical_orc_reads
    )
    assert trace.revision_vector == ((path.resolve(), _revision(source_payload)),)


@pytest.mark.parametrize(
    ("fixture_path", "provider_externs", "prompt_externs"),
    (
        (
            FIXTURES / "valid" / "materialize_view_runtime.orc",
            {},
            {},
        ),
        (
            FIXTURES
            / "provider_peer_group"
            / "provider_peer_group_three.orc",
            {
                "providers.planner": "planner-provider",
                "providers.reviewer": "reviewer-provider",
                "providers.builder": "builder-provider",
            },
            {
                "prompts.planner": "prompts/planner.md",
                "prompts.reviewer": "prompts/reviewer.md",
                "prompts.builder": "prompts/builder.md",
            },
        ),
    ),
    ids=("materialize-view", "provider-peer-group"),
)
def test_default_wcc_nominal_lowering_reads_join_the_active_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture_path: Path,
    provider_externs: dict[str, str],
    prompt_externs: dict[str, str],
) -> None:
    workflow_path = tmp_path / fixture_path.name
    workflow_path.write_bytes(fixture_path.read_bytes())
    physical_orc_reads: list[Path] = []
    real_read_bytes = Path.read_bytes

    def counted_read_bytes(self: Path) -> bytes:
        if self.suffix == ".orc":
            physical_orc_reads.append(self.resolve())
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    trace = _new_trace()

    result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(tmp_path,),
        entry_workflow="orchestrate",
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries={},
        validation_profile="frontend_only",
        workspace_root=tmp_path,
        source_read_trace=trace,
    )

    assert result.entry_result.module.module_name == fixture_path.stem
    assert physical_orc_reads
    assert tuple(record.canonical_path for record in trace.records) == tuple(
        physical_orc_reads
    )


def test_stage3_nominal_guidance_reads_join_the_active_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_path = tmp_path / "nominal_guidance.orc"
    workflow_path.write_bytes(_nominal_guidance_workflow_source())
    physical_orc_reads: list[Path] = []
    real_read_bytes = Path.read_bytes

    def counted_read_bytes(self: Path) -> bytes:
        if self.suffix == ".orc":
            physical_orc_reads.append(self.resolve())
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    trace = _new_trace()

    result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(tmp_path,),
        entry_workflow="entry",
        provider_externs={"providers.decide": "decision-provider"},
        prompt_externs={"prompts.decide": "prompts/decide.md"},
        command_boundaries={},
        validation_profile="frontend_only",
        workspace_root=tmp_path,
        source_read_trace=trace,
    )

    assert result.entry_result.module.module_name == "nominal_guidance"
    assert physical_orc_reads
    assert tuple(record.canonical_path for record in trace.records) == tuple(
        physical_orc_reads
    )
