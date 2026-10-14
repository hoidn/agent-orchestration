"""Pure runtime rendering checks for Workflow Lisp prompt fragments."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.deps.content_snapshot import (
    AuthoredDependencyRow,
    DependencyContent,
    build_content_snapshot,
)
from orchestrator.state import RunState, StateManager
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyOriginKind,
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.prompt_fragment_contract import COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA, CompilerPromptFragmentContract, CompilerPromptFragmentRenderedSlot
from orchestrator.workflow.provider_attempts import ProviderAttemptScope


_IDENTITY = "sha256:" + "1" * 64


def _slot(
    *,
    name: str,
    kind: str,
    renderer_id: str,
    static_type: dict[str, object],
    placeholder_ordinals: tuple[int, ...],
) -> CompilerPromptFragmentRenderedSlot:
    return CompilerPromptFragmentRenderedSlot(
        name=name,
        kind=kind,
        static_type=static_type,
        renderer_id=renderer_id,
        value_source={
            "kind": "typed_binding_ref",
            "binding": {"ref": f"inputs.{name}"},
        },
        placeholder_ordinals=placeholder_ordinals,
    )


def _contract() -> CompilerPromptFragmentContract:
    return CompilerPromptFragmentContract(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
        template_utf8=(
            "{{request}} {message} | {payload} | {report_path} | {message}"
        ),
        rendered_slots=(
            _slot(
                name="message",
                kind="text",
                renderer_id="raw-utf8-string",
                static_type={"kind": "primitive", "name": "String"},
                placeholder_ordinals=(0, 3),
            ),
            _slot(
                name="payload",
                kind="value",
                renderer_id="canonical-json",
                static_type={"kind": "primitive", "name": "Value"},
                placeholder_ordinals=(1,),
            ),
            _slot(
                name="report_path",
                kind="path",
                renderer_id="posix-path-line",
                static_type={
                    "kind": "path",
                    "name": "WorkReportPath",
                    "under": "artifacts/reports",
                    "must_exist_target": False,
                },
                placeholder_ordinals=(2,),
            ),
        ),
        compiled_prompt_fragment_identity=_IDENTITY,
    )


def test_fragment_base_renders_closed_slots_once_and_reuses_repeated_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import prompting

    actual_render_view = prompting.render_view
    calls: list[tuple[str, int, object]] = []

    def counted_render_view(
        renderer_id: str,
        renderer_version: int,
        value: object,
    ) -> bytes:
        calls.append((renderer_id, renderer_version, value))
        return actual_render_view(renderer_id, renderer_version, value)

    monkeypatch.setattr(prompting, "render_view", counted_render_view)

    rendered = prompting.render_prompt_fragment_base(
        _contract(),
        resolved_slot_values={
            "message": "Inspect carefully",
            "payload": {"score": 2, "ready": True},
            "report_path": "artifacts/review.md",
        },
    )

    assert rendered == (
        '{request} Inspect carefully | {"ready":true,"score":2} | '
        "artifacts/review.md | Inspect carefully"
    )
    assert calls == [
        ("canonical-json", 1, {"score": 2, "ready": True}),
        ("posix-path-line", 1, "artifacts/review.md"),
    ]


@pytest.mark.parametrize("target_dsl_version", ("2.20", "2.21"))
def test_fragment_base_older_targets_keep_string_only_rendering(
    target_dsl_version: str,
) -> None:
    from orchestrator.workflow.prompting import render_prompt_fragment_base

    rendered = render_prompt_fragment_base(
        _contract(),
        resolved_slot_values={
            "message": "Inspect carefully",
            "payload": {"score": 2, "ready": True},
            "report_path": "artifacts/review.md",
        },
        target_dsl_version=target_dsl_version,
    )

    assert type(rendered) is str
    assert rendered == (
        '{request} Inspect carefully | {"ready":true,"score":2} | '
        "artifacts/review.md | Inspect carefully"
    )


def test_fragment_base_without_document_lane_or_slots_is_literal_text() -> None:
    from orchestrator.workflow.prompting import render_prompt_fragment_base

    contract = CompilerPromptFragmentContract(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
        template_utf8="No document injection is required.",
        rendered_slots=(),
        compiled_prompt_fragment_identity=_IDENTITY,
    )

    assert (
        render_prompt_fragment_base(contract, resolved_slot_values={})
        == "No document injection is required."
    )


@pytest.mark.parametrize(
    ("resolved_slot_values", "message"),
    (
        (
            {
                "message": "Inspect",
                "payload": {"ready": True},
            },
            "exactly",
        ),
        (
            {
                "message": "Inspect",
                "payload": {"ready": True},
                "report_path": "artifacts/review.md",
                "extra": "not declared",
            },
            "exactly",
        ),
        (
            {
                "message": 7,
                "payload": {"ready": True},
                "report_path": "artifacts/review.md",
            },
            "raw-utf8-string",
        ),
        (
            {
                "message": "Inspect",
                "payload": object(),
                "report_path": "artifacts/review.md",
            },
            "canonical-json",
        ),
        (
            {
                "message": "Inspect",
                "payload": {"ready": True},
                "report_path": "artifacts/review.md\nother",
            },
            "posix-path-line",
        ),
    ),
)
def test_fragment_base_rejects_missing_extra_or_malformed_slot_values(
    resolved_slot_values: dict[str, object],
    message: str,
) -> None:
    from orchestrator.workflow.prompting import render_prompt_fragment_base

    with pytest.raises((TypeError, ValueError), match=message):
        render_prompt_fragment_base(
            _contract(),
            resolved_slot_values=resolved_slot_values,
        )


def test_fragment_base_revalidates_the_frozen_contract_before_rendering() -> None:
    from orchestrator.workflow.prompting import render_prompt_fragment_base

    contract = replace(_contract())
    object.__setattr__(contract, "template_utf8", "{unknown}")

    with pytest.raises(
        ValueError,
        match="compiler_prompt_fragment_contract_invalid",
    ):
        render_prompt_fragment_base(
            contract,
            resolved_slot_values={
                "message": "Inspect",
                "payload": {"ready": True},
                "report_path": "artifacts/review.md",
            },
        )


def _scope() -> ProviderAttemptScope:
    return ProviderAttemptScope.from_dict(
        {
            "run_id": "20260726T000000Z-q1fragment",
            "resume_scope": {
                "root_workflow_file": "workflow.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "PromptStep",
            "enclosing_step": {
                "step_name": "Prompt",
                "step_id": "PromptStep",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )


def _run_state(root: str | Path = "/tmp/q1-fragment") -> RunState:
    return RunState(
        schema_version="2.1",
        run_id=_scope().run_id,
        workflow_file="workflow.orc",
        workflow_checksum="sha256:" + "2" * 64,
        started_at="2026-07-26T00:00:00+00:00",
        updated_at="2026-07-26T00:00:00+00:00",
        status="running",
        run_root=str(root),
    )


def _dependency_contract(*, fragment: bool, documents: bool):
    return _build_compiler_prompt_dependency_contract(
        required_binding_refs=("inputs.document",) if documents else (),
        optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND,
        instruction=None if fragment else "Read.",
        source_origin_key="prompt-fragment" if fragment else "provider-result",
        source_workflow_bytes=b"(workflow evidence)",
        origin_kind=(
            PromptDependencyOriginKind.WORKFLOW_LISP_PROMPT_FRAGMENT
            if fragment
            else (
                PromptDependencyOriginKind
                .WORKFLOW_LISP_PROVIDER_RESULT_PROMPT_DEPENDENCIES
            )
        ),
    )


def _dependency_snapshot(*, documents: bool):
    if not documents:
        return build_content_snapshot((), ())
    return build_content_snapshot(
        (
            AuthoredDependencyRow(
                "required",
                0,
                "inputs.document",
                "docs/design.md",
                "docs/design.md",
            ),
        ),
        (DependencyContent("docs/design.md", b"alpha\n"),),
    )


def _fragment_success_build(
    *,
    run_state: RunState | None = None,
    ordinal: int = 1,
    documents: bool = False,
):
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence,
    )

    return build_fragment_success_evidence(
        run_state=run_state or _run_state(),
        scope=_scope(),
        ordinal=ordinal,
        compiler_contract=_dependency_contract(
            fragment=True,
            documents=documents,
        ),
        compiled_prompt_fragment_identity=_IDENTITY,
        snapshot=_dependency_snapshot(documents=documents),
        instruction="" if not documents else "Read these inputs.",
        instruction_source="none" if not documents else "default_required",
        compose_final_prompt=lambda rendered: rendered.block + b"fragment base",
    )


def test_fragment_snapshot_zero_document_record_is_closed_and_canonical() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        FRAGMENT_SUCCESS_SCHEMA,
        canonical_record_bytes,
        validate_fragment_success_evidence,
    )

    build = _fragment_success_build()
    record = build.evidence

    assert set(record) == {
        "schema",
        "record_kind",
        "run",
        "compiler_contract",
        "attempt",
        "authored_rows",
        "canonical_groups",
        "instruction",
        "injection",
        "final_prompt",
        "compiled_prompt_fragment_identity",
        "record_sha256",
    }
    assert record["schema"] == FRAGMENT_SUCCESS_SCHEMA
    assert record["record_kind"] == "prompt_snapshot"
    assert record["compiled_prompt_fragment_identity"] == _IDENTITY
    assert record["authored_rows"] == []
    assert record["canonical_groups"] == []
    assert record["instruction"]["source"] == "none"
    assert record["injection"]["files_total"] == 0
    assert build.rendered.block == b""
    payload = canonical_record_bytes(record)
    assert payload == json.dumps(
        record,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    assert validate_fragment_success_evidence(record) == record


def test_fragment_snapshot_rejects_a_non_fragment_compiler_origin() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence,
    )

    with pytest.raises(ValueError, match="origin"):
        build_fragment_success_evidence(
            run_state=_run_state(),
            scope=_scope(),
            ordinal=1,
            compiler_contract=_dependency_contract(
                fragment=False,
                documents=True,
            ),
            compiled_prompt_fragment_identity=_IDENTITY,
            snapshot=_dependency_snapshot(documents=True),
            instruction="Read.",
            instruction_source="authored",
            compose_final_prompt=lambda rendered: rendered.block + b"base",
        )


@pytest.mark.parametrize("fault", ("missing", "extra", "malformed", "tampered"))
def test_fragment_snapshot_rejects_identity_or_closed_key_tampering(
    fault: str,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_fragment_success_evidence,
    )

    record = deepcopy(_fragment_success_build().evidence)
    if fault == "missing":
        record.pop("compiled_prompt_fragment_identity")
    elif fault == "extra":
        record["unexpected"] = True
    elif fault == "malformed":
        record["compiled_prompt_fragment_identity"] = "sha256:ABC"
    else:
        record["compiled_prompt_fragment_identity"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError):
        validate_fragment_success_evidence(record)


def test_fragment_snapshot_publication_and_terminal_index_accept_sibling(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        publish_evidence_file,
        validate_terminal_evidence,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "workflow.orc").write_text(
        "(workflow evidence)\n",
        encoding="utf-8",
    )
    manager = StateManager(
        workspace,
        run_id=_scope().run_id,
        state_dir=tmp_path / "runs",
    )
    manager.run_root.mkdir(parents=True, exist_ok=True)
    manager.state = _run_state(manager.run_root)
    manager._write_state()
    assert manager.state is not None
    manager.state.step_visits["Prompt"] = 1
    manager.state.current_step = {
        "name": "Prompt",
        "step_id": "PromptStep",
        "visit_count": 1,
    }
    manager._write_state()
    assert manager.allocate_provider_attempt(_scope()) == 1

    build = _fragment_success_build(run_state=manager.state)
    publication = publish_evidence_file(
        manager,
        _scope(),
        1,
        build.evidence,
    )
    assert publication.record_kind == "prompt_snapshot"
    assert (
        manager.run_root / publication.relative_path
    ).read_bytes() == publication.payload

    assert manager.state is not None
    manager.state.status = "completed"
    manager._write_state()
    terminal = validate_terminal_evidence(
        manager.run_root,
        manager.state_file,
    )
    assert terminal.index["publications"] == [
        {
            "scope_sha256": _scope().key,
            "runtime_step_id": "PromptStep",
            "visit_key": _scope().key[7:31],
            "attempt_ordinal": 1,
            "record_kind": "prompt_snapshot",
            "relative_path": str(publication.relative_path),
            "record_sha256": build.evidence["record_sha256"],
            "record_file_sha256": publication.file_sha256,
        }
    ]
    assert terminal.index["allocation_only_gaps"] == []


def test_existing_success_record_bytes_remain_exactly_unchanged() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_success_evidence,
        canonical_record_bytes,
    )

    snapshot = _dependency_snapshot(documents=True)
    build = build_success_evidence(
        run_state=_run_state(),
        scope=_scope(),
        ordinal=1,
        compiler_contract=_dependency_contract(
            fragment=False,
            documents=True,
        ),
        snapshot=snapshot,
        instruction="Read.",
        instruction_source="authored",
        compose_final_prompt=lambda rendered: rendered.block + b"\n\nbase",
    )
    payload = canonical_record_bytes(build.evidence)

    assert len(payload) == 2883
    assert hashlib.sha256(payload).hexdigest() == (
        "304fc900b541bb5ce96c9d43e006144ee105c17bca2d58c7259967134badbc4c"
    )
    assert build.evidence["record_sha256"] == (
        "sha256:3675bbd39bd84b7c986d17bc3ec1935111362a9f556fc6f94fe1778316a54d73"
    )
