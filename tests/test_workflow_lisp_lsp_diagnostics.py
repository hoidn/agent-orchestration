from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendDiagnostic
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import ExpansionFrame, HelperExpansionFrame


def _surface():
    try:
        module = import_module("orchestrator.lsp.diagnostics")
    except ModuleNotFoundError:
        pytest.fail("orchestrator.lsp.diagnostics is not implemented")
    contribution_type = getattr(module, "DiagnosticContribution", None)
    translate = getattr(module, "translate_frontend_diagnostics", None)
    aggregate = getattr(module, "aggregate_diagnostic_contributions", None)
    if not isinstance(contribution_type, type):
        pytest.fail("DiagnosticContribution is not implemented")
    if not callable(translate):
        pytest.fail("translate_frontend_diagnostics is not implemented")
    if not callable(aggregate):
        pytest.fail("aggregate_diagnostic_contributions is not implemented")
    return contribution_type, translate, aggregate


def _position(
    path: str,
    *,
    line: int,
    column: int,
    offset: int,
) -> SourcePosition:
    return SourcePosition(
        path=path,
        line=line,
        column=column,
        offset=offset,
    )


def _span(
    path: str,
    *,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> SourceSpan:
    return SourceSpan(
        start=_position(
            path,
            line=start[0],
            column=start[1],
            offset=start[2],
        ),
        end=_position(
            path,
            line=end[0],
            column=end[1],
            offset=end[2],
        ),
    )


def _diagnostic(
    path: Path | str,
    *,
    message: str = "display wording",
    notes: tuple[str, ...] = ("display note",),
    expansion_stack: tuple[object, ...] = (),
) -> LispFrontendDiagnostic:
    return LispFrontendDiagnostic(
        code="record_field_missing",
        message=message,
        span=_span(
            str(path),
            start=(1, 2, 1),
            end=(1, 4, 3),
        ),
        form_path=("workflow-lisp", "body"),
        expansion_stack=expansion_stack,
        notes=notes,
    )


def test_translate_readable_diagnostic_to_one_immutable_structural_contribution(
    tmp_path: Path,
) -> None:
    contribution_type, translate, _aggregate = _surface()
    source_path = (tmp_path / "source.orc").resolve()
    source_text = "a😀bc\n"
    entry_uri = (tmp_path / "entry.orc").resolve().as_uri()

    contributions = translate(
        (_diagnostic(source_path),),
        compile_entry_uri=entry_uri,
        accepted_generation=7,
        accepted_text_by_path={source_path: source_text},
    )

    assert len(contributions) == 1
    contribution = contributions[0]
    assert isinstance(contribution, contribution_type)
    assert contribution.target_uri == source_path.as_uri()
    assert contribution.compile_entry_uri == entry_uri
    assert contribution.accepted_generation == 7
    assert contribution.range == {
        "start": {"line": 0, "character": 1},
        "end": {"line": 0, "character": 4},
    }
    assert contribution.code == "record_field_missing"
    assert contribution.severity == 1
    assert contribution.source == "orc"
    assert contribution.message == "display wording"
    assert contribution.data["diagnostic_kind"] == "validation"
    assert contribution.data["phase"] == "typecheck"
    assert contribution.data["validation_pass"] == "type"
    assert contribution.data["authority_layer"] == "frontend"
    assert contribution.data["raw_span"] == {
        "path": str(source_path),
        "start": {"line": 1, "column": 2, "offset": 1},
        "end": {"line": 1, "column": 4, "offset": 3},
    }
    assert contribution.data["form_path"] == ("workflow-lisp", "body")
    assert contribution.data["notes"] == ("display note",)
    assert contribution.data["compile_entry_uri"] == entry_uri
    assert contribution.data["accepted_generation"] == 7
    assert contribution.related_information == ()
    assert contribution.parity_identity
    with pytest.raises(FrozenInstanceError):
        contribution.message = "mutated"
    with pytest.raises(TypeError):
        contribution.data["phase"] = "mutated"
    with pytest.raises(TypeError):
        contribution.range["start"]["line"] = 99

    warning = replace(_diagnostic(source_path), severity="warn")
    warning_contribution = translate(
        (warning,),
        compile_entry_uri=entry_uri,
        accepted_generation=7,
        accepted_text_by_path={source_path: source_text},
    )[0]
    assert warning_contribution.severity == 2


def test_related_information_uses_only_readable_structured_frame_spans(
    tmp_path: Path,
) -> None:
    _contribution_type, translate, _aggregate = _surface()
    source_path = (tmp_path / "source.orc").resolve()
    call_path = (tmp_path / "call.orc").resolve()
    helper_path = (tmp_path / "helper.orc").resolve()
    missing_definition = (tmp_path / "missing-definition.orc").resolve()
    text = "abcd\n"
    macro = ExpansionFrame(
        macro_name="expand",
        expansion_id="exp-1",
        call_span=_span(
            str(call_path),
            start=(1, 1, 0),
            end=(1, 2, 1),
        ),
        definition_span=_span(
            str(missing_definition),
            start=(1, 1, 0),
            end=(1, 2, 1),
        ),
        template_path=("body",),
    )
    helper = HelperExpansionFrame(
        function_name="normalize",
        call_span=_span(
            str(helper_path),
            start=(1, 2, 1),
            end=(1, 3, 2),
        ),
        definition_span=_span(
            str(helper_path),
            start=(1, 3, 2),
            end=(1, 4, 3),
        ),
    )

    contribution = translate(
        (
            _diagnostic(
                source_path,
                expansion_stack=(macro, helper),
            ),
        ),
        compile_entry_uri=(tmp_path / "entry.orc").resolve().as_uri(),
        accepted_generation=2,
        accepted_text_by_path={
            source_path: "a😀bc\n",
            call_path: text,
            helper_path: text,
        },
    )[0]

    related = contribution.related_information
    assert tuple(tuple(item) for item in related) == (
        (
            "frame_role",
            "location_role",
            "name",
            "expansion_id",
            "location",
        ),
        (
            "frame_role",
            "location_role",
            "name",
            "expansion_id",
            "location",
        ),
        (
            "frame_role",
            "location_role",
            "name",
            "expansion_id",
            "location",
        ),
    )
    assert tuple(
        (
            item["frame_role"],
            item["location_role"],
            item["name"],
            item["expansion_id"],
        )
        for item in related
    ) == (
        ("macro", "call", "expand", "exp-1"),
        ("helper", "call", "normalize", None),
        ("helper", "definition", "normalize", None),
    )
    assert tuple(item["location"]["uri"] for item in related) == (
        call_path.as_uri(),
        helper_path.as_uri(),
        helper_path.as_uri(),
    )
    assert missing_definition.as_uri() not in {
        item["location"]["uri"] for item in related
    }
    assert tuple(
        frame["kind"] for frame in contribution.data["expansion_frames"]
    ) == ("macro", "helper")


def test_unreadable_primary_path_falls_back_without_losing_raw_coordinates(
    tmp_path: Path,
) -> None:
    _contribution_type, translate, _aggregate = _surface()
    missing_path = (tmp_path / "missing.orc").resolve()
    entry_uri = (tmp_path / "entry.orc").resolve().as_uri()

    contribution = translate(
        (_diagnostic(missing_path),),
        compile_entry_uri=entry_uri,
        accepted_generation=4,
        accepted_text_by_path={},
    )[0]

    assert contribution.target_uri == entry_uri
    assert contribution.range == {
        "start": {"line": 0, "character": 0},
        "end": {"line": 0, "character": 0},
    }
    assert contribution.data["raw_span"] == {
        "path": str(missing_path),
        "start": {"line": 1, "column": 2, "offset": 1},
        "end": {"line": 1, "column": 4, "offset": 3},
    }
    assert contribution.related_information == ()


def test_aggregation_deduplicates_by_parity_and_retains_remaining_owner(
    tmp_path: Path,
) -> None:
    _contribution_type, translate, aggregate = _surface()
    source_path = (tmp_path / "shared.orc").resolve()
    text_by_path = MappingProxyType({source_path: "a😀bc\n"})
    first_uri = (tmp_path / "a-entry.orc").resolve().as_uri()
    second_uri = (tmp_path / "z-entry.orc").resolve().as_uri()
    first = translate(
        (
            _diagnostic(
                source_path,
                message="lexical owner wording",
                notes=("first note",),
            ),
        ),
        compile_entry_uri=first_uri,
        accepted_generation=3,
        accepted_text_by_path=text_by_path,
    )
    second = translate(
        (
            _diagnostic(
                source_path,
                message="later owner wording",
                notes=("second note",),
            ),
        ),
        compile_entry_uri=second_uri,
        accepted_generation=8,
        accepted_text_by_path=text_by_path,
    )

    aggregated = aggregate({second_uri: second, first_uri: first})

    assert tuple(aggregated) == (source_path.as_uri(),)
    assert len(aggregated[source_path.as_uri()]) == 1
    representative = aggregated[source_path.as_uri()][0]
    assert representative.compile_entry_uri == first_uri
    assert representative.message == "lexical owner wording"
    assert representative.data["notes"] == ("first note",)

    remaining = aggregate({second_uri: second})

    assert len(remaining[source_path.as_uri()]) == 1
    assert remaining[source_path.as_uri()][0].compile_entry_uri == second_uri
    assert remaining[source_path.as_uri()][0].message == "later owner wording"


def test_current_projection_hides_one_owner_without_erasing_other_owner(
    tmp_path: Path,
) -> None:
    from orchestrator.lsp.compile_driver import probe_disk_source
    from orchestrator.lsp.state import (
        AcceptedCompileSnapshot,
        accept_compile_success,
        change_entry,
        initialize_lsp_state,
        open_entry,
    )
    import orchestrator.lsp.state as state_module

    projection = getattr(
        state_module,
        "current_diagnostic_contributions",
        None,
    )
    if not callable(projection):
        pytest.fail("current_diagnostic_contributions is not implemented")

    _contribution_type, translate, aggregate = _surface()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_path = workspace / "shared.orc"
    first_path = workspace / "a-entry.orc"
    second_path = workspace / "z-entry.orc"
    for path in (source_path, first_path, second_path):
        path.write_text("a😀bc\n", encoding="utf-8")
    state = initialize_lsp_state(root_uri=workspace.as_uri())
    contributions_by_path = {}
    for generation, entry_path in enumerate((first_path, second_path), 1):
        opened = open_entry(
            state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_path.read_text(encoding="utf-8"),
            disk_snapshot=probe_disk_source(entry_path),
        )
        actual_generation = opened.state.entries[-1].generation
        contributions = translate(
            (_diagnostic(source_path),),
            compile_entry_uri=entry_path.as_uri(),
            accepted_generation=actual_generation,
            accepted_text_by_path={source_path: source_path.read_text()},
        )
        contributions_by_path[entry_path] = contributions
        state = accept_compile_success(
            opened.state,
            document_uri=entry_path.as_uri(),
            generation=actual_generation,
            snapshot=AcceptedCompileSnapshot(
                build_value=("accepted", generation),
                source_revision_vector=(
                    (
                        entry_path.resolve(),
                        probe_disk_source(entry_path).revision,
                    ),
                ),
            ),
            dependency_closure=frozenset({entry_path.resolve()}),
            diagnostic_contributions=contributions,
        ).state

    first_hidden = change_entry(
        state,
        document_uri=first_path.as_uri(),
        editor_text="edited\n",
    )
    aggregate_after_first = aggregate(
        projection(first_hidden.state)
    )

    assert len(aggregate_after_first[source_path.as_uri()]) == 1
    assert (
        aggregate_after_first[source_path.as_uri()][0].compile_entry_uri
        == second_path.as_uri()
    )
    assert (
        first_hidden.state.entries[0].diagnostic_contributions
        is contributions_by_path[first_path]
    )

    second_hidden = change_entry(
        first_hidden.state,
        document_uri=second_path.as_uri(),
        editor_text="edited\n",
    )

    assert aggregate(projection(second_hidden.state)) == {}
    assert (
        second_hidden.state.entries[1].diagnostic_contributions
        is contributions_by_path[second_path]
    )


def test_direct_contribution_construction_copies_and_deep_freezes_payloads(
    tmp_path: Path,
) -> None:
    contribution_type, _translate, _aggregate = _surface()
    entry_uri = (tmp_path / "entry.orc").resolve().as_uri()
    range_payload = {
        "start": {"line": 0, "character": 1},
        "end": {"line": 0, "character": 2},
    }
    identity_tail = ["identity"]
    data_payload = {
        "notes": ["note"],
        "nested": {"values": [1]},
    }
    related_payload = {
        "frame_role": "macro",
        "location_role": "call",
        "name": "expand",
        "expansion_id": "exp-1",
        "location": {
            "uri": entry_uri,
            "range": range_payload,
        },
    }

    contribution = contribution_type(
        target_uri=entry_uri,
        compile_entry_uri=entry_uri,
        accepted_generation=1,
        parity_identity=("code", identity_tail),
        range=range_payload,
        code="code",
        severity=1,
        source="orc",
        message="message",
        data=data_payload,
        related_information=(related_payload,),
    )
    range_payload["start"]["line"] = 9
    identity_tail.append("mutated")
    data_payload["notes"].append("mutated")
    data_payload["nested"]["values"].append(2)
    related_payload["frame_role"] = "mutated"

    assert contribution.range["start"]["line"] == 0
    assert contribution.parity_identity == ("code", ("identity",))
    assert contribution.data["notes"] == ("note",)
    assert contribution.data["nested"]["values"] == (1,)
    assert contribution.related_information[0]["frame_role"] == "macro"
    with pytest.raises(TypeError):
        contribution.data["nested"]["values"] += (2,)
    with pytest.raises(TypeError):
        contribution.related_information[0]["frame_role"] = "mutated"


def test_aggregation_rejects_duplicate_canonical_owner_keys(
    tmp_path: Path,
) -> None:
    _contribution_type, translate, aggregate = _surface()
    entry_uri = (tmp_path / "entry.orc").resolve().as_uri()
    localhost_uri = entry_uri.replace("file:///", "file://localhost/", 1)
    source_path = (tmp_path / "source.orc").resolve()
    contributions = translate(
        (_diagnostic(source_path),),
        compile_entry_uri=entry_uri,
        accepted_generation=1,
        accepted_text_by_path={source_path: "a😀bc\n"},
    )

    for duplicate_map in (
        {entry_uri: contributions, localhost_uri: contributions},
        {localhost_uri: contributions, entry_uri: contributions},
    ):
        with pytest.raises(ValueError, match="duplicate canonical"):
            aggregate(duplicate_map)


@pytest.mark.parametrize(
    "entry_uri",
    (
        "file:relative.orc",
        "file:///tmp/entry.orc?query=1",
        "file:///tmp/entry.orc#fragment",
        "file:///tmp/%FF.orc",
        "file://remote.example/tmp/entry.orc",
        "https://example.test/entry.orc",
    ),
)
def test_translation_rejects_noncanonical_or_nonlocal_entry_uris(
    entry_uri: str,
) -> None:
    _contribution_type, translate, _aggregate = _surface()

    with pytest.raises(ValueError):
        translate(
            (),
            compile_entry_uri=entry_uri,
            accepted_generation=1,
            accepted_text_by_path={},
        )


def test_translation_canonicalizes_absolute_percent_encoded_local_uri(
    tmp_path: Path,
) -> None:
    _contribution_type, translate, _aggregate = _surface()
    entry_path = (tmp_path / "entry with space;part.orc").resolve()
    entry_uri = entry_path.as_uri()

    contribution = translate(
        (_diagnostic(tmp_path / "missing.orc"),),
        compile_entry_uri=entry_uri,
        accepted_generation=1,
        accepted_text_by_path={},
    )[0]

    assert contribution.compile_entry_uri == entry_uri
    assert contribution.target_uri == entry_uri
