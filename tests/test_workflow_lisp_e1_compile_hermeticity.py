"""E1 preacceptance characterization of the ordinary full compiler path.

These tests deliberately derive no E1 identity from the current frontend build
fingerprint.  That fingerprint includes ambient source-root paths.  The proof
below establishes the source/configuration evidence that a later E1 identity
must normalize and bind.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    FrontendInMemoryBuildResult,
    build_frontend_bundle_in_memory,
)
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    serialize_diagnostics,
)
from orchestrator.workflow_lisp.reader import SourceReadTrace


_ENTRY_MODULE = "e1_fixture/entry"
_HELPER_MODULE = "e1_fixture/helper"


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _helper_source(*, implementation: str = "argument") -> str:
    body = 'label' if implementation == "argument" else '"helper-b"'
    return f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule {_HELPER_MODULE})
  (export Message make-message)
  (defrecord Message
    (text String))
  (defproc make-message
    ((label String))
    -> Message
    :effects ()
    :lowering inline
    (record Message
      :text {body})))
"""


def _entry_source(*, label: str = "entry-a", invalid: bool = False) -> str:
    return f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule {_ENTRY_MODULE})
  (import {_HELPER_MODULE} :only (Message make-message))
  (export run)
  (defworkflow run
    ()
    -> {"MissingE1Type" if invalid else "Message"}
    (make-message "{label}")))
"""


def _write_tree(
    root: Path,
    *,
    entry_label: str = "entry-a",
    helper_implementation: str = "argument",
    invalid: bool = False,
    with_configuration: bool = False,
) -> tuple[Path, dict[str, Path]]:
    module_root = root / "e1_fixture"
    module_root.mkdir(parents=True)
    entry = module_root / "entry.orc"
    helper = module_root / "helper.orc"
    entry.write_text(
        _entry_source(label=entry_label, invalid=invalid),
        encoding="utf-8",
    )
    helper.write_text(
        _helper_source(implementation=helper_implementation),
        encoding="utf-8",
    )

    configuration: dict[str, Path] = {}
    if with_configuration:
        for name in ("providers", "prompts", "commands"):
            path = root / f"{name}.json"
            path.write_text("{}\n", encoding="utf-8")
            configuration[name] = path
    return entry, configuration


def _request(
    root: Path,
    entry: Path,
    configuration: Mapping[str, Path] | None = None,
) -> FrontendBuildRequest:
    configured = configuration or {}
    return FrontendBuildRequest(
        source_path=entry,
        source_roots=(root,),
        entry_workflow="run",
        provider_externs_path=configured.get("providers"),
        prompt_externs_path=configured.get("prompts"),
        command_boundaries_path=configured.get("commands"),
        workspace_root=root,
    )


def _normalize_paths(
    value: Any,
    root: Path,
    *,
    build_root: Path | None = None,
    fingerprint: str | None = None,
) -> Any:
    """Normalize only clone-root spelling; retain every semantic payload."""

    if isinstance(value, Mapping):
        return {
            str(key): _normalize_paths(
                item,
                root,
                build_root=build_root,
                fingerprint=fingerprint,
            )
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [
            _normalize_paths(
                item,
                root,
                build_root=build_root,
                fingerprint=fingerprint,
            )
            for item in value
        ]
    if isinstance(value, Path):
        value = value.as_posix()
    if isinstance(value, str):
        if build_root is not None:
            value = value.replace(
                build_root.resolve().as_posix(),
                "<AMBIENT_BUILD_ROOT>",
            )
        if fingerprint is not None:
            value = value.replace(fingerprint, "<AMBIENT_FINGERPRINT>")
        return value.replace(root.resolve().as_posix(), "<CLONE_ROOT>")
    return value


def _normalized_compiler_payload(
    result: FrontendInMemoryBuildResult,
    root: Path,
) -> dict[str, Any]:
    normalized = _normalize_paths(
        {
            "selected_workflow_name": result.selected_workflow_name,
            "core_workflow_ast": result.core_workflow_ast_payload,
            "semantic_ir": result.semantic_ir_payload,
            "executable_ir": result.executable_ir_payload,
            "runtime_plan": result.runtime_plan_payload,
            "workflow_boundary_projection": (
                result.workflow_boundary_projection_payload
            ),
            "persisted_surface": result.persisted_surface_payload,
        },
        root,
        build_root=result.build_root,
        fingerprint=result.fingerprint,
    )
    persisted_bytes = (
        json.dumps(
            normalized["persisted_surface"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    normalized["executable_ir"]["provenance"][
        "frontend_persisted_surface_sha256"
    ] = f"sha256:{hashlib.sha256(persisted_bytes).hexdigest()}"
    return normalized


def _normalized_revision_vector(
    vector: tuple[tuple[Path, str], ...],
    root: Path,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (path.resolve().relative_to(root.resolve()).as_posix(), revision)
        for path, revision in vector
    )


def _module_revision_vector(
    result: FrontendInMemoryBuildResult,
) -> tuple[tuple[str, str], ...]:
    revisions_by_path = dict(result.source_read_trace.revision_vector)
    return tuple(
        (
            module_name,
            revisions_by_path[module_source.path.resolve()],
        )
        for module_name, module_source in sorted(
            result.compile_result.graph.modules_by_name.items()
        )
    )


@pytest.mark.parametrize("mutation", ("entry", "dependency"))
def test_same_canonical_paths_are_reread_after_source_bytes_change(
    tmp_path: Path,
    mutation: str,
) -> None:
    entry, _ = _write_tree(tmp_path)
    request = _request(tmp_path, entry)

    first = build_frontend_bundle_in_memory(request)
    first_payload = _normalized_compiler_payload(first, tmp_path)
    first_revisions = dict(first.source_read_trace.revision_vector)

    mutated_path = (
        entry if mutation == "entry" else tmp_path / "e1_fixture" / "helper.orc"
    )
    if mutation == "entry":
        mutated_path.write_text(_entry_source(label="entry-b"), encoding="utf-8")
    else:
        mutated_path.write_text(
            _helper_source(implementation="constant"),
            encoding="utf-8",
        )

    second = build_frontend_bundle_in_memory(request)
    second_payload = _normalized_compiler_payload(second, tmp_path)
    second_revisions = dict(second.source_read_trace.revision_vector)

    assert first_revisions.keys() == second_revisions.keys()
    assert first_revisions[mutated_path.resolve()] != second_revisions[
        mutated_path.resolve()
    ]
    assert first.source_read_trace.revision_vector != (
        second.source_read_trace.revision_vector
    )
    assert first_payload != second_payload


def test_identical_trees_in_distinct_roots_compile_equivalently_after_root_normalization(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "clone-a"
    second_root = tmp_path / "clone-b"
    first_entry, first_configuration = _write_tree(
        first_root,
        with_configuration=True,
    )
    second_entry, second_configuration = _write_tree(
        second_root,
        with_configuration=True,
    )

    first = build_frontend_bundle_in_memory(
        _request(first_root, first_entry, first_configuration)
    )
    second = build_frontend_bundle_in_memory(
        _request(second_root, second_entry, second_configuration)
    )

    assert _normalized_compiler_payload(first, first_root) == (
        _normalized_compiler_payload(second, second_root)
    )
    assert _normalized_revision_vector(
        first.source_read_trace.revision_vector,
        first_root,
    ) == _normalized_revision_vector(
        second.source_read_trace.revision_vector,
        second_root,
    )
    assert _module_revision_vector(first) == _module_revision_vector(second)
    assert tuple(name for name, _digest in _module_revision_vector(first)) == (
        _ENTRY_MODULE,
        _HELPER_MODULE,
    )
    assert _normalized_revision_vector(
        first.configuration_trace.revision_vector,
        first_root,
    ) == _normalized_revision_vector(
        second.configuration_trace.revision_vector,
        second_root,
    )

    # The existing build fingerprint includes absolute source-root spelling.
    # It is useful build-cache metadata, but is therefore not an E1 identity.
    assert first.fingerprint != second.fingerprint


def test_revision_vectors_exactly_enumerate_compiler_read_source_and_configuration(
    tmp_path: Path,
) -> None:
    entry, configuration = _write_tree(
        tmp_path,
        with_configuration=True,
    )
    helper = tmp_path / "e1_fixture" / "helper.orc"

    result = build_frontend_bundle_in_memory(
        _request(tmp_path, entry, configuration)
    )

    expected_sources = tuple(
        sorted(
            ((path.resolve(), _sha256(path)) for path in (entry, helper)),
            key=lambda item: item[0].as_posix(),
        )
    )
    expected_configuration = tuple(
        sorted(
            (
                (path.resolve(), _sha256(path))
                for path in configuration.values()
            ),
            key=lambda item: item[0].as_posix(),
        )
    )

    assert result.source_read_trace.revision_vector == expected_sources
    assert result.configuration_trace.revision_vector == expected_configuration
    assert {
        record.canonical_path for record in result.source_read_trace.records
    } == {path for path, _revision in expected_sources}
    assert {
        record.canonical_path for record in result.configuration_trace.records
    } == {path for path, _revision in expected_configuration}


def test_structured_rejection_is_emitted_by_the_ordinary_full_compiler(
    tmp_path: Path,
) -> None:
    entry, configuration = _write_tree(
        tmp_path,
        invalid=True,
        with_configuration=True,
    )
    source_trace = SourceReadTrace()

    with pytest.raises(LispFrontendCompileError) as caught:
        build_frontend_bundle_in_memory(
            _request(tmp_path, entry, configuration),
            source_read_trace=source_trace,
        )

    serialized = serialize_diagnostics(caught.value.diagnostics)
    assert serialized
    assert serialized[0]["code"] == "type_unknown"
    assert serialized[0]["phase"] == "typecheck"
    assert serialized[0]["validation_pass"] == "type"
    assert serialized[0]["path"].endswith("e1_fixture/entry.orc")
    assert caught.value.compile_request_capture.source_path == entry.resolve()
    assert source_trace.revision_vector
    assert caught.value.configuration_revision_vector == tuple(
        sorted(
            (
                (path.resolve(), _sha256(path))
                for path in configuration.values()
            ),
            key=lambda item: item[0].as_posix(),
        )
    )
