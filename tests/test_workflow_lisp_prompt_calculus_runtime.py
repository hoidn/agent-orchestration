"""Pure runtime rendering checks for Workflow Lisp prompt fragments."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.deps.content_snapshot import (
    AuthoredDependencyRow,
    DependencyContent,
    build_content_snapshot,
)
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import RunState, StateManager
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.prompt_dependency_evidence import (
    evidence_relative_path,
)
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyOriginKind,
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
    CompilerPromptFragmentContract,
    CompilerPromptFragmentContractV2,
    CompilerPromptFragmentOutputPosition,
    CompilerPromptFragmentRenderedSlot,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
import orchestrator.workflow_lisp as workflow_lisp
from tests.workflow_bundle_helpers import bundle_context_dict


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
    manager.initialize("workflow.orc")
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


def _compile_runtime_fragment(
    workspace: Path,
    *,
    lowering_route: str = "legacy",
    with_downstream_command: bool = False,
    target_dsl: str = "2.20",
    with_output_position: bool = False,
):
    source_path = workspace / "prompt_runtime.orc"
    provider_form = """
    (provider-result providers.review
      :prompt
        (review
          :target_doc target_doc
          :message message
          :score score
          :report_path report_path))
""".strip()
    workflow_body = provider_form
    command_boundaries = {}
    if with_downstream_command:
        workflow_body = f"""
    (let* ((decision
             {provider_form})
           (continued
             (command-result finish
               :argv ("python" "finish.py")
               :returns Bool)))
      decision)
""".strip()
        (workspace / "finish.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            'target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
            "target.parent.mkdir(parents=True, exist_ok=True)\n"
            'target.write_text("true\\n", encoding="utf-8")\n',
            encoding="utf-8",
        )
        command_boundaries = {
            "finish": ExternalToolBinding(
                name="finish",
                stable_command=("python", "finish.py"),
            )
        }
    source_path.write_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "__TARGET_DSL__")
  (defmodule demo/prompt-runtime)
  (export run-review)
  (defpath DesignDocPath
    :kind relpath
    :under "docs/design"
    :must-exist true)
  (defpath WorkReportPath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defprompt review
    (:fills
      (target_doc :doc DesignDocPath)
      (message :text)
      (score :value Int)
      (report_path :path__OUTPUT_POSITION__ WorkReportPath))
    -> Bool
    "Message={message}; score={score}; report={report_path}; again={message}")
  (defworkflow run-review
    ((target_doc DesignDocPath)
     (message String)
     (score Int)
     (report_path WorkReportPath))
    -> Bool
    __WORKFLOW_BODY__))
""".replace(
            "__TARGET_DSL__",
            target_dsl,
        ).replace(
            "__OUTPUT_POSITION__",
            " :out" if with_output_position else "",
        ).replace(
            "__WORKFLOW_BODY__",
            workflow_body,
        ).lstrip(),
        encoding="utf-8",
    )
    result = workflow_lisp.compile_stage3_module(
        source_path,
        provider_externs={"providers.review": "capturing-provider"},
        prompt_externs={},
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=workspace,
        lowering_route=lowering_route,
    )
    return source_path, result.validated_bundles["run-review"]


def _runtime_fragment_manager(
    workspace: Path,
    source_path: Path,
    bundle,
    *,
    run_id: str,
) -> StateManager:
    document = workspace / "docs" / "design" / "target.md"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("DOCUMENT_SENTINEL\n", encoding="utf-8")
    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        contracts,
        {
            "target_doc": "docs/design/target.md",
            "message": "MESSAGE_SENTINEL",
            "score": 7,
            "report_path": "artifacts/work/review.md",
        },
        workspace,
    )
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        source_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return manager


def _counter_only_evidence_path(
    manager: StateManager,
    allocation: dict,
    ordinal: int,
) -> Path:
    assert "events" not in allocation
    last_ordinal = allocation["last_allocated_ordinal"]
    assert isinstance(last_ordinal, int)
    assert not isinstance(last_ordinal, bool)
    assert 1 <= ordinal <= last_ordinal
    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    return manager.run_root / evidence_relative_path(scope, ordinal)


def _provider_success(
    workspace: Path,
    captured: dict[str, object],
):
    def prepare(_self, *_args, **kwargs):
        captured["preparations"] = int(captured["preparations"]) + 1
        captured["prompt"] = str(kwargs.get("prompt_content", ""))
        return SimpleNamespace(
            input_mode="stdin",
            prompt=captured["prompt"],
            env=kwargs.get("env") or {},
            prepared_prompt=captured["prompt"],
            prepared_provider_policy=SimpleNamespace(
                to_dict=lambda: {
                    "provider_name": kwargs["provider_name"],
                    "model": None,
                    "effort": None,
                    "timeout_sec": kwargs.get("timeout_sec"),
                    "input_mode": "stdin",
                }
            ),
        ), None

    def execute(_self, invocation, **_kwargs):
        captured["executions"] = int(captured["executions"]) + 1
        output = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("true\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    return prepare, execute


def _upgrade_runtime_fragment_bundle_to_q2(
    bundle,
    *,
    identity: str = "sha256:" + "4" * 64,
    literal_report_path: str | None = None,
):
    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    )
    config = provider_node.execution_config
    q1_contract = config.compiler_prompt_fragment_contract
    rendered_slots = q1_contract.rendered_slots
    if literal_report_path is not None:
        rendered_slots = tuple(
            replace(
                slot,
                value_source={
                    "kind": "typed_binding_ref",
                    "binding": literal_report_path,
                },
            )
            if slot.name == "report_path"
            else slot
            for slot in rendered_slots
        )
    expected_output = {
        "name": "report_path",
        "path": (
            literal_report_path
            if literal_report_path is not None
            else "${inputs.report_path}"
        ),
        "type": "string",
        "required": True,
    }
    q2_contract = CompilerPromptFragmentContractV2(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
        template_utf8=q1_contract.template_utf8,
        rendered_slots=rendered_slots,
        output_positions=(
            CompilerPromptFragmentOutputPosition(
                slot_name="report_path",
                output_role="required_string_file",
                expected_output=expected_output,
            ),
        ),
        compiled_prompt_fragment_identity=identity,
    )
    q2_common = replace(
        config.common,
        expected_outputs=(expected_output,),
    )
    q2_config = replace(
        config,
        common=q2_common,
        compiler_prompt_fragment_contract=q2_contract,
        compiled_prompt_fragment_identity=identity,
    )
    q2_node = replace(provider_node, execution_config=q2_config)

    surface_step = next(
        step
        for step in bundle.surface.steps
        if step.step_id == provider_node.step_id
    )
    q2_surface_step = replace(
        surface_step,
        common=replace(
            surface_step.common,
            expected_outputs=(expected_output,),
        ),
        compiler_prompt_fragment_contract=q2_contract,
        compiled_prompt_fragment_identity=identity,
    )
    core_step = next(
        step
        for step in bundle.core_workflow_ast.body
        if step.meta.id == provider_node.node_id
    )
    q2_core_step = replace(
        core_step,
        common=replace(
            core_step.common,
            expected_outputs=(expected_output,),
        ),
        compiler_prompt_fragment_contract=q2_contract,
        compiled_prompt_fragment_identity=identity,
    )
    prompt_surface_id, prompt_surface = next(
        iter(bundle.semantic_ir.prompt_surfaces.items())
    )
    q2_prompt_surface = replace(
        prompt_surface,
        compiler_prompt_fragment_contract=q2_contract,
        compiled_prompt_fragment_identity=identity,
    )
    q2_bundle = replace(
        bundle,
        surface=replace(
            bundle.surface,
            steps=tuple(
                q2_surface_step
                if step.step_id == provider_node.step_id
                else step
                for step in bundle.surface.steps
            ),
        ),
        core_workflow_ast=replace(
            bundle.core_workflow_ast,
            body=tuple(
                q2_core_step
                if step.meta.id == provider_node.node_id
                else step
                for step in bundle.core_workflow_ast.body
            ),
        ),
        semantic_ir=replace(
            bundle.semantic_ir,
            prompt_surfaces=MappingProxyType(
                {
                    **bundle.semantic_ir.prompt_surfaces,
                    prompt_surface_id: q2_prompt_surface,
                }
            ),
        ),
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **bundle.ir.nodes,
                    provider_node.node_id: q2_node,
                }
            ),
        ),
    )
    return q2_bundle, q2_node, q2_contract, expected_output


def test_runtime_fragment_composes_once_in_the_existing_prompt_order_and_publishes(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_fragment_success_evidence,
    )

    source_path, bundle = _compile_runtime_fragment(tmp_path)
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-runtime",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, execute = _provider_success(tmp_path, captured)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(ProviderExecutor, "execute", execute):
        completed = WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert completed["status"] == "completed"
    assert captured["preparations"] == 1
    assert captured["executions"] == 1
    prompt = str(captured["prompt"])
    assert prompt.count("DOCUMENT_SENTINEL") == 1
    assert prompt.count("MESSAGE_SENTINEL") == 2
    assert prompt.count("7") == 1
    assert prompt.count("artifacts/work/review.md") == 1
    assert prompt.index("DOCUMENT_SENTINEL") < prompt.index("MESSAGE_SENTINEL")
    assert manager.state is not None
    result_bundle_path = next(
        value
        for name, value in manager.state.bound_inputs.items()
        if name.startswith("__write_root__")
    )
    assert prompt.index("artifacts/work/review.md") < prompt.index(
        result_bundle_path
    )

    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    )
    identity = provider_node.execution_config.compiled_prompt_fragment_identity
    allocations = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )["provider_attempt_allocations"]
    (allocation,) = allocations.values()
    assert allocation["last_allocated_ordinal"] == 1
    evidence_path = _counter_only_evidence_path(
        manager,
        allocation,
        1,
    )
    record = validate_fragment_success_evidence(
        json.loads(evidence_path.read_text(encoding="ascii"))
    )
    assert record["compiled_prompt_fragment_identity"] == identity
    assert record["final_prompt"]["sha256"] == (
        "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    )

    typed_evidence_paths = sorted(
        (
            manager.run_root
            / "workflow_lisp"
            / "typed_prompt_inputs"
        ).glob("*.json")
    )
    assert len(typed_evidence_paths) == 1
    typed_evidence = json.loads(
        typed_evidence_paths[0].read_text(encoding="utf-8")
    )
    assert [row["binding_name"] for row in typed_evidence] == [
        "score",
        "report_path",
    ]


def test_q2_receiving_attempt_keeps_functional_v1_evidence_identity(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        FRAGMENT_SUCCESS_SCHEMA,
        validate_fragment_success_evidence,
    )

    source_path, compiled_bundle = _compile_runtime_fragment(tmp_path)
    bundle, _, contract, _ = _upgrade_runtime_fragment_bundle_to_q2(
        compiled_bundle
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q2-runtime",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, base_execute = _provider_success(tmp_path, captured)

    def execute_with_required_file(provider, invocation, **kwargs):
        report = tmp_path / "artifacts" / "work" / "review.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("reviewed\n", encoding="utf-8")
        return base_execute(provider, invocation, **kwargs)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_with_required_file,
    ):
        WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert captured == {
        "preparations": 1,
        "executions": 1,
        "prompt": captured["prompt"],
    }
    allocations = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )["provider_attempt_allocations"]
    (allocation,) = allocations.values()
    assert allocation["last_allocated_ordinal"] == 1
    evidence_path = _counter_only_evidence_path(
        manager,
        allocation,
        1,
    )
    record = validate_fragment_success_evidence(
        json.loads(evidence_path.read_text(encoding="ascii"))
    )
    assert record["schema"] == FRAGMENT_SUCCESS_SCHEMA
    assert FRAGMENT_SUCCESS_SCHEMA == (
        "workflow_prompt_fragment_snapshot.functional.v1"
    )
    assert record["compiled_prompt_fragment_identity"] == (
        contract.compiled_prompt_fragment_identity
    )


def test_q2_literal_output_path_matches_before_provider_launch(
    tmp_path: Path,
) -> None:
    source_path, compiled_bundle = _compile_runtime_fragment(tmp_path)
    literal_path = "artifacts/work/literal-review.md"
    bundle, _, _, _ = _upgrade_runtime_fragment_bundle_to_q2(
        compiled_bundle,
        literal_report_path=literal_path,
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q2-literal",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, base_execute = _provider_success(tmp_path, captured)

    def execute_with_required_file(provider, invocation, **kwargs):
        report = tmp_path / literal_path
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("reviewed\n", encoding="utf-8")
        return base_execute(provider, invocation, **kwargs)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_with_required_file,
    ):
        completed = WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert completed["status"] == "completed"
    assert captured["preparations"] == 1
    assert captured["executions"] == 1


def test_q2_rendered_path_mismatch_precedes_provider_launch(
    tmp_path: Path,
) -> None:
    source_path, compiled_bundle = _compile_runtime_fragment(tmp_path)
    bundle, _, _, _ = _upgrade_runtime_fragment_bundle_to_q2(compiled_bundle)
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q2-path-mismatch",
    )
    executor = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, execute = _provider_success(tmp_path, captured)
    original_resolve = executor._resolve_typed_prompt_input_value

    def resolve_with_mismatch(value, state, *, scope=None):
        if value == {"ref": "inputs.report_path"}:
            return "artifacts/work/other.md", None
        return original_resolve(value, state, scope=scope)

    with patch.object(
        executor,
        "_resolve_typed_prompt_input_value",
        resolve_with_mismatch,
    ), patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(ProviderExecutor, "execute", execute):
        state = executor.execute(on_error="continue")

    failed = next(
        value
        for value in state["steps"].values()
        if value.get("status") == "failed"
    )
    assert failed["error"]["context"]["reason"] == (
        "prompt_output_position_contract_mismatch"
    )
    assert captured == {"preparations": 0, "executions": 0}
    assert manager.state is not None
    assert manager.state.provider_attempt_allocations == {}


def test_q2_structured_destination_alias_precedes_provider_launch(
    tmp_path: Path,
) -> None:
    source_path, compiled_bundle = _compile_runtime_fragment(tmp_path)
    bundle, _, _, _ = _upgrade_runtime_fragment_bundle_to_q2(compiled_bundle)
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q2-destination-alias",
    )
    executor = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, execute = _provider_success(tmp_path, captured)
    original_paths = executor._resolve_output_contract_paths
    original_value = executor._resolve_typed_prompt_input_value
    aliased_path: dict[str, str] = {}

    def resolve_aliased_paths(step, state, context=None):
        expected, structured, error = original_paths(
            step,
            state,
            context=context,
        )
        if error is None and expected and structured:
            destination = structured["path"]
            aliased_path["value"] = destination
            expected = [{**expected[0], "path": destination}]
        return expected, structured, error

    def resolve_aliased_value(value, state, *, scope=None):
        if value == {"ref": "inputs.report_path"}:
            return aliased_path["value"], None
        return original_value(value, state, scope=scope)

    with patch.object(
        executor,
        "_resolve_output_contract_paths",
        resolve_aliased_paths,
    ), patch.object(
        executor,
        "_resolve_typed_prompt_input_value",
        resolve_aliased_value,
    ), patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(ProviderExecutor, "execute", execute):
        state = executor.execute(on_error="continue")

    failed = next(
        value
        for value in state["steps"].values()
        if value.get("status") == "failed"
    )
    assert failed["error"]["context"]["reason"] == (
        "prompt_output_position_destination_collision"
    )
    violation = failed["error"]["context"]["violations"][0]
    assert violation["context"]["names"] == [
        "report_path",
        "output_bundle",
    ]
    assert [subject["subject_kind"] for subject in violation["subject_refs"]] == [
        "expected_output",
        "step_id",
    ]
    assert captured == {"preparations": 0, "executions": 0}
    assert manager.state is not None
    assert manager.state.provider_attempt_allocations == {}


def test_q2_compatible_completed_boundary_is_reused_without_provider_reexecution(
    tmp_path: Path,
) -> None:
    class Q2BoundaryInterruption(BaseException):
        pass

    source_path, compiled_bundle = _compile_runtime_fragment(
        tmp_path,
        lowering_route="wcc_m4",
        with_downstream_command=True,
    )
    bundle, provider_node, _, _ = _upgrade_runtime_fragment_bundle_to_q2(
        compiled_bundle
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q2-resume",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, base_execute = _provider_success(tmp_path, captured)

    def execute_with_required_file(provider, invocation, **kwargs):
        report = tmp_path / "artifacts" / "work" / "review.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("reviewed\n", encoding="utf-8")
        return base_execute(provider, invocation, **kwargs)

    original_emit = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit

    def interrupt_after_committed_boundary(
        executor,
        state,
        step_name,
        step,
        finalized,
    ):
        original_emit(executor, state, step_name, step, finalized)
        if finalized.get("status") == "completed":
            raise Q2BoundaryInterruption

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_with_required_file,
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_committed_boundary,
    ):
        with pytest.raises(Q2BoundaryInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
                retry_delay_ms=0,
            ).execute(on_error="stop")

    committed = json.loads(manager.state_file.read_text(encoding="utf-8"))
    provider_state = next(
        step
        for step in committed["steps"].values()
        if step["step_id"] == provider_node.step_id
    )
    assert provider_state["status"] == "completed"
    assert (tmp_path / "artifacts" / "work" / "review.md").is_file()
    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_with_required_file,
    ):
        resumed = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            retry_delay_ms=0,
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert captured["preparations"] == 1
    assert captured["executions"] == 1


def test_q3_compatible_completed_boundary_reuses_without_preparation_or_evidence(
    tmp_path: Path,
) -> None:
    class Q3BoundaryInterruption(BaseException):
        pass

    source_path, compiled_bundle = _compile_runtime_fragment(
        tmp_path,
        lowering_route="wcc_m4",
        with_downstream_command=True,
        target_dsl="2.22",
        with_output_position=True,
    )
    bundle = compiled_bundle
    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q3-completed-resume",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, base_execute = _provider_success(tmp_path, captured)

    def execute_with_required_file(provider, invocation, **kwargs):
        report = tmp_path / "artifacts" / "work" / "review.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("reviewed\n", encoding="utf-8")
        return base_execute(provider, invocation, **kwargs)

    original_emit = (
        WorkflowExecutor
        ._emit_lexical_checkpoint_shadow_after_step_commit
    )

    def interrupt_after_committed_boundary(
        executor,
        state,
        step_name,
        step,
        finalized,
    ):
        original_emit(executor, state, step_name, step, finalized)
        if finalized.get("status") == "completed":
            raise Q3BoundaryInterruption

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_with_required_file,
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_committed_boundary,
    ):
        with pytest.raises(Q3BoundaryInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
                retry_delay_ms=0,
            ).execute(on_error="stop")

    committed = json.loads(manager.state_file.read_text(encoding="utf-8"))
    provider_state = next(
        step
        for step in committed["steps"].values()
        if step["step_id"] == provider_node.step_id
    )
    assert provider_state["status"] == "completed"
    committed_binding = provider_state["debug"][
        "prompt_attempt_result_binding"
    ]
    [allocation] = committed["provider_attempt_allocations"].values()
    evidence_path = _counter_only_evidence_path(
        manager,
        allocation,
        committed_binding["attempt_ordinal"],
    )
    evidence_payload = evidence_path.read_bytes()
    assert committed_binding["evidence_relative_path"] == (
        evidence_path.relative_to(manager.run_root).as_posix()
    )
    assert committed_binding["evidence_file_sha256"] == (
        "sha256:" + hashlib.sha256(evidence_payload).hexdigest()
    )
    assert committed_binding["record_kind"] == "prompt_snapshot"
    evidence_path.unlink()

    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        side_effect=AssertionError(
            "compatible completed result must not prepare an invocation"
        ),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError(
            "compatible completed result must not launch a provider"
        ),
    ):
        resumed = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            retry_delay_ms=0,
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    resumed_provider_state = next(
        step
        for step in resumed["steps"].values()
        if step["step_id"] == provider_node.step_id
    )
    assert resumed_provider_state["debug"][
        "prompt_attempt_result_binding"
    ] == committed_binding
    assert captured["preparations"] == 1
    assert captured["executions"] == 1


def test_q3_pending_and_failed_boundaries_carry_pair_into_fresh_attempt(
    tmp_path: Path,
) -> None:
    source_path, compiled_bundle = _compile_runtime_fragment(
        tmp_path,
        lowering_route="wcc_m4",
        target_dsl="2.22",
        with_output_position=True,
    )
    bundle = compiled_bundle
    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    )
    config = provider_node.execution_config
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q3-failed-resume",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    observed_pairs: list[tuple[object, object]] = []
    prepare, base_execute = _provider_success(tmp_path, captured)
    original_provider = WorkflowExecutor._execute_provider_with_context

    def capture_pair(executor, step, *args, **kwargs):
        observed_pairs.append(
            (
                step.prompt_attempt_identity_version,
                step.compiler_prompt_attempt_binding_plan,
            )
        )
        return original_provider(executor, step, *args, **kwargs)

    def fail_then_succeed(provider, invocation, **kwargs):
        if captured["executions"] == 0:
            captured["executions"] = 1
            return SimpleNamespace(
                exit_code=1,
                stdout=b"",
                stderr=b"failed",
                duration_ms=1,
                error=None,
                missing_placeholders=None,
                invalid_prompt_placeholder=False,
                raw_stdout=None,
                normalized_stdout=None,
                provider_session=None,
            )
        report = tmp_path / "artifacts" / "work" / "review.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("reviewed\n", encoding="utf-8")
        return base_execute(provider, invocation, **kwargs)

    with patch.object(
        WorkflowExecutor,
        "_execute_provider_with_context",
        capture_pair,
    ), patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        fail_then_succeed,
    ):
        completed = WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            max_retries=1,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert completed["status"] == "completed"
    assert observed_pairs == [
        (
            config.prompt_attempt_identity_version,
            config.compiler_prompt_attempt_binding_plan,
        ),
    ]
    assert captured["preparations"] == 2
    assert captured["executions"] == 2
    allocation = next(
        iter(completed["provider_attempt_allocations"].values())
    )
    assert allocation["last_allocated_ordinal"] == 2
    assert "events" not in allocation
    failed_evidence_path = _counter_only_evidence_path(
        manager,
        allocation,
        1,
    )
    assert failed_evidence_path.is_file()
    provider_state = next(
        value
        for value in completed["steps"].values()
        if value["step_id"] == provider_node.step_id
    )
    binding = provider_state["debug"]["prompt_attempt_result_binding"]
    successful_evidence_path = _counter_only_evidence_path(
        manager,
        allocation,
        2,
    )
    successful_evidence_payload = successful_evidence_path.read_bytes()
    assert json.loads(successful_evidence_payload)["record_kind"] == (
        "prompt_snapshot"
    )
    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    assert binding == {
        "schema_version": (
            "workflow_prompt_attempt_result_binding.v1"
        ),
        "scope_sha256": scope.key,
        "attempt_ordinal": 2,
        "evidence_relative_path": (
            successful_evidence_path
            .relative_to(manager.run_root)
            .as_posix()
        ),
        "evidence_file_sha256": (
            "sha256:"
            + hashlib.sha256(successful_evidence_payload).hexdigest()
        ),
        "record_kind": "prompt_snapshot",
    }


def test_q3_post_provider_output_failure_commits_no_result_binding(
    tmp_path: Path,
) -> None:
    source_path, bundle = _compile_runtime_fragment(
        tmp_path,
        lowering_route="wcc_m4",
        target_dsl="2.22",
        with_output_position=True,
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q3-output-failure",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, execute = _provider_success(tmp_path, captured)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute,
    ):
        failed = WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert failed["status"] == "failed"
    [failed_step] = failed["steps"].values()
    assert failed_step["status"] == "failed"
    assert "prompt_attempt_result_binding" not in failed_step.get(
        "debug",
        {},
    )
    assert captured["preparations"] == 1
    assert captured["executions"] == 1
    persisted = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    [allocation] = persisted["provider_attempt_allocations"].values()
    assert allocation["last_allocated_ordinal"] == 1
    evidence_path = _counter_only_evidence_path(
        manager,
        allocation,
        1,
    )
    assert json.loads(evidence_path.read_bytes())["record_kind"] == (
        "prompt_snapshot"
    )


def test_q3_result_binding_failure_precedes_reached_result_commit(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_attempt_result_binding import (
        PromptAttemptResultBindingError,
    )

    source_path, bundle = _compile_runtime_fragment(
        tmp_path,
        lowering_route="wcc_m4",
        target_dsl="2.22",
        with_output_position=True,
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q3-binding-failure",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, base_execute = _provider_success(tmp_path, captured)

    def execute_with_required_file(provider, invocation, **kwargs):
        report = tmp_path / "artifacts" / "work" / "review.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("reviewed\n", encoding="utf-8")
        return base_execute(provider, invocation, **kwargs)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_with_required_file,
    ), patch(
        "orchestrator.workflow.executor."
        "attach_prompt_attempt_result_binding",
        side_effect=PromptAttemptResultBindingError(
            "judgment_result_binding_ambiguous",
            "injected contradictory retained authority",
        ),
    ):
        failed = WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert failed["status"] == "failed"
    [failed_step] = failed["steps"].values()
    assert failed_step["status"] == "failed"
    assert failed_step["error"]["context"]["reason"] == (
        "judgment_result_binding_ambiguous"
    )
    assert "prompt_attempt_result_binding" not in failed_step.get(
        "debug",
        {},
    )
    assert captured["preparations"] == 1
    assert captured["executions"] == 1


def test_q3_precommit_interruption_persists_no_result_binding(
    tmp_path: Path,
) -> None:
    class BeforeReachedCommit(BaseException):
        pass

    source_path, bundle = _compile_runtime_fragment(
        tmp_path,
        lowering_route="wcc_m4",
        target_dsl="2.22",
        with_output_position=True,
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q3-precommit-interruption",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, base_execute = _provider_success(tmp_path, captured)

    def execute_with_required_file(provider, invocation, **kwargs):
        report = tmp_path / "artifacts" / "work" / "review.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("reviewed\n", encoding="utf-8")
        return base_execute(provider, invocation, **kwargs)

    original_update = StateManager.update_step

    def interrupt_binding_commit(
        state_manager,
        step_name,
        result,
    ):
        if (
            result.debug is not None
            and "prompt_attempt_result_binding" in result.debug
        ):
            raise BeforeReachedCommit
        return original_update(state_manager, step_name, result)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_with_required_file,
    ), patch.object(
        StateManager,
        "update_step",
        interrupt_binding_commit,
    ), pytest.raises(BeforeReachedCommit):
        WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    persisted = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    assert persisted["steps"] == {}
    [allocation] = persisted["provider_attempt_allocations"].values()
    assert allocation["last_allocated_ordinal"] == 1
    evidence_path = _counter_only_evidence_path(
        manager,
        allocation,
        1,
    )
    assert json.loads(evidence_path.read_bytes())["record_kind"] == (
        "prompt_snapshot"
    )
    assert "prompt_attempt_result_binding" not in json.dumps(
        persisted,
        sort_keys=True,
    )


def test_q3_complete_pair_loss_refuses_before_provider_launch(
    tmp_path: Path,
) -> None:
    source_path, bundle = _compile_runtime_fragment(
        tmp_path,
        target_dsl="2.22",
        with_output_position=True,
    )
    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    )
    config = provider_node.execution_config
    version = config.prompt_attempt_identity_version
    plan = config.compiler_prompt_attempt_binding_plan
    object.__setattr__(config, "prompt_attempt_identity_version", None)
    object.__setattr__(
        config,
        "compiler_prompt_attempt_binding_plan",
        None,
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q3-complete-pair-loss",
    )
    try:
        with patch.object(
            ProviderExecutor,
            "prepare_invocation",
            side_effect=AssertionError(
                "complete Q3 pair loss must precede provider preparation"
            ),
        ), patch.object(
            ProviderExecutor,
            "execute",
            side_effect=AssertionError(
                "complete Q3 pair loss must precede provider launch"
            ),
        ), pytest.raises(
            ValueError,
            match="prompt_attempt_identity_version_missing",
        ):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
                retry_delay_ms=0,
            ).execute(on_error="stop")
    finally:
        object.__setattr__(
            config,
            "prompt_attempt_identity_version",
            version,
        )
        object.__setattr__(
            config,
            "compiler_prompt_attempt_binding_plan",
            plan,
        )

    assert manager.state is not None
    assert manager.state.provider_attempt_allocations == {}


def test_q2_receiving_mismatch_has_no_attempt_or_provider_side_effects(
    tmp_path: Path,
) -> None:
    source_path, compiled_bundle = _compile_runtime_fragment(tmp_path)
    bundle, provider_node, _, _ = _upgrade_runtime_fragment_bundle_to_q2(
        compiled_bundle
    )
    config = provider_node.execution_config
    object.__setattr__(
        config,
        "common",
        replace(config.common, expected_outputs=()),
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id="prompt-fragment-q2-mismatch",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, execute = _provider_success(tmp_path, captured)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute,
    ), patch.object(
        WorkflowExecutor,
        "_resolve_typed_prompt_input_value",
        side_effect=AssertionError(
            "carrier mismatch must precede resolved-path validation"
        ),
    ), pytest.raises(
        ValueError,
        match="prompt_output_position_contract_mismatch",
    ):
        WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert captured == {"preparations": 0, "executions": 0}
    assert manager.state is not None
    assert manager.state.provider_attempt_allocations == {}


@pytest.mark.parametrize(
    ("fault", "reason"),
    (
        ("missing_identity", "compiled_prompt_fragment_identity_missing"),
        ("malformed_identity", "compiled_prompt_fragment_identity_invalid"),
        ("mismatched_identity", "compiled_prompt_fragment_identity_mismatch"),
        ("dependency_origin", "prompt_fragment_dependency_origin_invalid"),
        ("unavailable_slot", "prompt_fragment_slot_value_unavailable"),
    ),
)
def test_runtime_fragment_refuses_invalid_carriage_before_provider_preparation(
    tmp_path: Path,
    fault: str,
    reason: str,
) -> None:
    source_path, bundle = _compile_runtime_fragment(tmp_path)
    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    )
    config = provider_node.execution_config
    fragment_contract = config.compiler_prompt_fragment_contract
    assert fragment_contract is not None
    if fault == "missing_identity":
        object.__setattr__(
            config,
            "compiled_prompt_fragment_identity",
            None,
        )
    elif fault == "malformed_identity":
        object.__setattr__(
            config,
            "compiled_prompt_fragment_identity",
            "sha256:ABC",
        )
    elif fault == "mismatched_identity":
        object.__setattr__(
            config,
            "compiled_prompt_fragment_identity",
            "sha256:" + "0" * 64,
        )
    elif fault == "dependency_origin":
        object.__setattr__(
            config,
            "compiler_prompt_dependency_contract",
            _build_compiler_prompt_dependency_contract(
                required_binding_refs=("inputs.target_doc",),
                optional_binding_refs=(),
                position=PromptDependencyPosition.PREPEND,
                instruction=None,
                source_origin_key="provider-result",
                source_workflow_bytes=source_path.read_bytes(),
            ),
        )
    else:
        rendered_slots = tuple(
            (
                replace(
                    slot,
                    value_source={
                        "kind": "typed_binding_ref",
                        "binding": {
                            "ref": "root.steps.Missing.value",
                        },
                    },
                )
                if slot.name == "message"
                else slot
            )
            for slot in fragment_contract.rendered_slots
        )
        object.__setattr__(
            config,
            "compiler_prompt_fragment_contract",
            replace(
                fragment_contract,
                rendered_slots=rendered_slots,
            ),
        )

    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id=f"prompt-fragment-{fault}",
    )
    captured: dict[str, object] = {
        "preparations": 0,
        "executions": 0,
    }
    prepare, execute = _provider_success(tmp_path, captured)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(ProviderExecutor, "execute", execute):
        failed = WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert failed["status"] == "failed"
    (failed_step,) = failed["steps"].values()
    assert failed_step["error"]["context"]["reason"] == reason
    assert captured == {
        "preparations": 0,
        "executions": 0,
    }
    assert manager.state is not None
    assert manager.state.provider_attempt_allocations == {}
