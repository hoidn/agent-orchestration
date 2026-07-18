"""Tests for deterministic output-contract prompt injection on provider steps."""

import json
import hashlib
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest
import yaml

from orchestrator.contracts.prompt_contract import render_output_bundle_contract_block
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow_lisp.compiler import compile_stage3_module


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow))
    return workflow_file


def _enable_v214_loader(monkeypatch) -> None:
    version_order = list(WorkflowLoader.VERSION_ORDER)
    if "2.14" not in version_order:
        version_order.append("2.14")
    monkeypatch.setattr(
        WorkflowLoader,
        "SUPPORTED_VERSIONS",
        WorkflowLoader.SUPPORTED_VERSIONS | {"2.14"},
    )
    monkeypatch.setattr(
        WorkflowLoader,
        "VERSION_ORDER",
        version_order,
    )


def _variant_contract_body_as_yaml(prompt_block: str) -> object:
    return yaml.safe_load("\n".join(prompt_block.splitlines()[2:]))


def _output_contract_body_as_yaml(prompt_block: str) -> object:
    contract_start = next(
        index
        for index, line in enumerate(prompt_block.splitlines())
        if line.startswith("- path:")
    )
    return yaml.safe_load("\n".join(prompt_block.splitlines()[contract_start:]))


def _typed_dependency_runtime(
    tmp_path: Path,
    run_id: str,
    *,
    fixture_name: str = "mixed.orc",
    entry_workflow: str = "mixed",
):
    repo = Path(__file__).resolve().parents[1]
    fixture = repo / "tests/fixtures/workflow_lisp/provider_prompt_dependencies" / fixture_name
    compiled = compile_stage3_module(
        fixture.relative_to(repo),
        entry_workflow=entry_workflow,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=repo,
        lowering_route="wcc_m4",
    )
    bundle = compiled.validated_bundles[entry_workflow]
    (tmp_path / "artifacts/work").mkdir(parents=True)
    (tmp_path / "artifacts/context").mkdir(parents=True)
    (tmp_path / "artifacts/work/required.md").write_text("R\n", encoding="utf-8")
    (tmp_path / "artifacts/context/optional.md").write_text("O\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id=run_id)
    manager.initialize(
        fixture.as_posix(),
        bound_inputs={
            "inputs__required": "artifacts/work/required.md",
            "inputs__optional": "artifacts/context/optional.md",
        },
    )
    return WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0), manager


def _replace_typed_dependency_mapping(
    executor: WorkflowExecutor,
    transform,
) -> None:
    node_id, node = next(
        (node_id, node)
        for node_id, node in executor.executable_ir.nodes.items()
        if getattr(
            node.execution_config,
            "compiler_prompt_dependency_contract",
            None,
        )
        is not None
    )
    config = node.execution_config
    depends_on = transform(
        {
            "required": tuple(config.depends_on["required"]),
            "optional": tuple(config.depends_on["optional"]),
            "inject": dict(config.depends_on["inject"]),
        }
    )
    _replace_typed_depends_on_value(executor, depends_on)


def _replace_typed_depends_on_value(
    executor: WorkflowExecutor,
    depends_on,
) -> None:
    node_id, node = next(
        (node_id, node)
        for node_id, node in executor.executable_ir.nodes.items()
        if getattr(
            node.execution_config,
            "compiler_prompt_dependency_contract",
            None,
        )
        is not None
    )
    config = node.execution_config
    nodes = dict(executor.executable_ir.nodes)
    nodes[node_id] = replace(
        node,
        execution_config=replace(
            config,
            depends_on=(
                MappingProxyType(depends_on)
                if isinstance(depends_on, dict)
                else depends_on
            ),
        ),
    )
    executor.executable_ir = replace(
        executor.executable_ir,
        nodes=MappingProxyType(nodes),
    )


def _replace_typed_prompt_inputs(
    executor: WorkflowExecutor,
    typed_prompt_inputs: tuple[dict[str, object], ...],
) -> None:
    node_id, node = next(
        (node_id, node)
        for node_id, node in executor.executable_ir.nodes.items()
        if getattr(
            node.execution_config,
            "compiler_prompt_dependency_contract",
            None,
        )
        is not None
    )
    nodes = dict(executor.executable_ir.nodes)
    nodes[node_id] = replace(
        node,
        execution_config=replace(
            node.execution_config,
            typed_prompt_inputs=typed_prompt_inputs,
        ),
    )
    executor.executable_ir = replace(
        executor.executable_ir,
        nodes=MappingProxyType(nodes),
    )


def _install_typed_success_provider(
    executor: WorkflowExecutor,
    workspace: Path,
    calls: dict[str, int],
) -> None:
    captured: dict[str, str] = {}

    def _prepare(*_args, **kwargs):
        calls["preparation"] += 1
        captured.update(kwargs.get("env") or {})
        prompt = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=prompt), None

    def _execute(_invocation, **_kwargs):
        calls["execution"] += 1
        output = workspace / captured["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "RESULT_SENTINEL"}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare
    executor.provider_executor.execute = _execute


def _published_typed_attempt_records(manager: StateManager) -> list[dict]:
    allocations = json.loads(manager.state_file.read_text(encoding="utf-8"))[
        "provider_attempt_allocations"
    ]
    return [
        json.loads(
            (manager.run_root / event["relative_path"]).read_text(encoding="ascii")
        )
        for allocation in allocations.values()
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    ]


def _assert_typed_projection_failure(
    executor: WorkflowExecutor,
    manager: StateManager,
    workspace: Path,
) -> dict:
    calls = {"preparation": 0, "execution": 0}
    _install_typed_success_provider(executor, workspace, calls)

    state = executor.execute(on_error="stop")

    failed_steps = [
        result
        for result in state["steps"].values()
        if isinstance(result, dict) and result.get("exit_code") == 2
    ]
    assert len(failed_steps) == 1
    assert calls == {"preparation": 0, "execution": 0}
    records = _published_typed_attempt_records(manager)
    assert records and all(record["record_kind"] == "failure" for record in records)
    return failed_steps[0]


def test_typed_dependency_mapping_matching_canonical_contract_projection_succeeds(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-canonical-projection")
    calls = {"preparation": 0, "execution": 0}
    _install_typed_success_provider(executor, tmp_path, calls)

    state = executor.execute(on_error="stop")

    assert state["status"] == "completed"
    assert calls == {"preparation": 1, "execution": 1}
    assert [record["record_kind"] for record in _published_typed_attempt_records(manager)] == [
        "prompt_snapshot"
    ]


def test_typed_dependency_mapping_replaced_template_fails_before_preparation(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-replaced-template")
    _replace_typed_dependency_mapping(
        executor,
        lambda depends_on: {
            **depends_on,
            "required": (
                "${inputs.inputs__optional}",
                depends_on["required"][1],
            ),
        },
    )
    calls = {"preparation": 0, "execution": 0}
    _install_typed_success_provider(executor, tmp_path, calls)

    state = executor.execute(on_error="stop")

    assert state["steps"]["mixed__result"]["exit_code"] == 2
    assert calls == {"preparation": 0, "execution": 0}
    records = _published_typed_attempt_records(manager)
    assert records and all(record["record_kind"] != "prompt_snapshot" for record in records)


def test_typed_dependency_mapping_swapped_required_optional_refs_fails_before_preparation(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-swapped-refs")
    _replace_typed_dependency_mapping(
        executor,
        lambda depends_on: {
            **depends_on,
            "required": depends_on["optional"],
            "optional": depends_on["required"],
        },
    )
    calls = {"preparation": 0, "execution": 0}
    _install_typed_success_provider(executor, tmp_path, calls)

    state = executor.execute(on_error="stop")

    assert state["steps"]["mixed__result"]["exit_code"] == 2
    assert calls == {"preparation": 0, "execution": 0}
    records = _published_typed_attempt_records(manager)
    assert records and all(record["record_kind"] != "prompt_snapshot" for record in records)


def test_typed_dependency_mapping_position_mismatch_fails_before_preparation(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-position-mismatch")

    def _prepend_instead_of_contract(depends_on):
        depends_on["inject"]["position"] = "prepend"
        return depends_on

    _replace_typed_dependency_mapping(executor, _prepend_instead_of_contract)
    calls = {"preparation": 0, "execution": 0}
    _install_typed_success_provider(executor, tmp_path, calls)

    state = executor.execute(on_error="stop")

    assert state["steps"]["mixed__result"]["exit_code"] == 2
    assert calls == {"preparation": 0, "execution": 0}
    records = _published_typed_attempt_records(manager)
    assert records and all(record["record_kind"] != "prompt_snapshot" for record in records)


def test_typed_dependency_mapping_mode_cannot_bypass_allocated_failure_branch(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-mode-bypass")

    def _list_instead_of_content(depends_on):
        depends_on["inject"]["mode"] = "list"
        return depends_on

    _replace_typed_dependency_mapping(executor, _list_instead_of_content)

    _assert_typed_projection_failure(executor, manager, tmp_path)


@pytest.mark.parametrize(
    "projection",
    [pytest.param(["not-a-mapping"], id="list"), pytest.param(None, id="none")],
)
def test_typed_dependency_nonmapping_projection_enters_allocated_failure_branch(
    tmp_path: Path,
    projection,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-nonmapping-projection")
    _replace_typed_depends_on_value(executor, projection)

    _assert_typed_projection_failure(executor, manager, tmp_path)


def test_typed_dependency_mapping_rejects_instruction_when_contract_has_none(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(
        tmp_path,
        "typed-mapping-only-instruction",
        fixture_name="without_instruction.orc",
        entry_workflow="without_instruction",
    )

    def _add_mapping_only_instruction(depends_on):
        depends_on["inject"]["instruction"] = "MAPPING_ONLY_INSTRUCTION_SENTINEL"
        return depends_on

    _replace_typed_dependency_mapping(executor, _add_mapping_only_instruction)

    _assert_typed_projection_failure(executor, manager, tmp_path)


def test_typed_dependency_mapping_rejects_changed_authored_instruction(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-changed-instruction")

    def _change_authored_instruction(depends_on):
        depends_on["inject"]["instruction"] = "CHANGED_INSTRUCTION_SENTINEL"
        return depends_on

    _replace_typed_dependency_mapping(executor, _change_authored_instruction)

    _assert_typed_projection_failure(executor, manager, tmp_path)


@pytest.mark.parametrize(
    "mutate_projection",
    [
        pytest.param(
            lambda depends_on: {**depends_on, "unexpected": True},
            id="extra-top-level-member",
        ),
        pytest.param(
            lambda _depends_on: {},
            id="missing-depends-on-projection",
        ),
        pytest.param(
            lambda depends_on: {
                key: value for key, value in depends_on.items() if key != "optional"
            },
            id="missing-top-level-member",
        ),
        pytest.param(
            lambda depends_on: {
                **depends_on,
                "inject": {**depends_on["inject"], "unexpected": True},
            },
            id="extra-inject-member",
        ),
        pytest.param(
            lambda depends_on: {
                **depends_on,
                "inject": {
                    key: value
                    for key, value in depends_on["inject"].items()
                    if key != "position"
                },
            },
            id="missing-inject-member",
        ),
        pytest.param(
            lambda depends_on: {
                **depends_on,
                "inject": {
                    key: value
                    for key, value in depends_on["inject"].items()
                    if key != "mode"
                },
            },
            id="missing-inject-mode",
        ),
        pytest.param(
            lambda depends_on: {
                **depends_on,
                "inject": {
                    key: value
                    for key, value in depends_on["inject"].items()
                    if key != "instruction"
                },
            },
            id="missing-authored-instruction",
        ),
    ],
)
def test_typed_dependency_mapping_rejects_extra_or_missing_projection_members(
    tmp_path: Path,
    mutate_projection,
) -> None:
    executor, manager = _typed_dependency_runtime(
        tmp_path,
        "typed-closed-projection",
    )
    _replace_typed_dependency_mapping(executor, mutate_projection)

    _assert_typed_projection_failure(executor, manager, tmp_path)


@pytest.mark.parametrize("mode", ["content", "list"])
def test_yaml_dependency_modes_remain_mapping_driven_without_typed_evidence(
    tmp_path: Path,
    mode: str,
) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "prompts/review.md").write_text(
        "BASE_PROMPT_SENTINEL\n",
        encoding="utf-8",
    )
    (tmp_path / "state/context.txt").write_text(
        "YAML_DEPENDENCY_BODY_SENTINEL\n",
        encoding="utf-8",
    )
    workflow = {
        "version": "2.7",
        "name": f"yaml-{mode}-control",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [
            {
                "name": "Review",
                "id": "review",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "depends_on": {
                    "required": ["state/context.txt"],
                    "inject": {"mode": mode, "position": "append"},
                },
            }
        ],
    }
    loaded = WorkflowLoader(tmp_path).load(_write_workflow(tmp_path, workflow))
    manager = StateManager(tmp_path, run_id=f"yaml-{mode}-control")
    manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, manager)
    prompts: list[str] = []

    def _prepare(*_args, **kwargs):
        prompt = kwargs.get("prompt_content") or ""
        prompts.append(prompt)
        return SimpleNamespace(input_mode="stdin", prompt=prompt), None

    executor.provider_executor.prepare_invocation = _prepare
    executor.provider_executor.execute = lambda *_args, **_kwargs: SimpleNamespace(
        exit_code=0,
        stdout=b"ok",
        stderr=b"",
        duration_ms=1,
        error=None,
        missing_placeholders=None,
        invalid_prompt_placeholder=False,
    )

    state = executor.execute(on_error="stop")

    assert state["status"] == "completed"
    assert len(prompts) == 1
    if mode == "content":
        assert "YAML_DEPENDENCY_BODY_SENTINEL" in prompts[0]
    else:
        assert "state/context.txt" in prompts[0]
        assert "YAML_DEPENDENCY_BODY_SENTINEL" not in prompts[0]
    assert manager.load().provider_attempt_allocations == {}
    assert not (manager.run_root / "workflow_lisp/prompt_dependencies").exists()


def test_content_dependency_retry_takes_one_fresh_snapshot_and_render_per_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A content dependency is observed once inside each ordinary retry."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("BASE_PROMPT_SENTINEL\n", encoding="utf-8")
    dependency = tmp_path / "state" / "context.txt"
    dependency.write_text("old-attempt-body\n", encoding="utf-8")
    workflow = {
        "version": "2.7",
        "name": "retry-content-snapshot",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "id": "review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "depends_on": {
                "required": ["state/context.txt"],
                "inject": {
                    "mode": "content",
                    "position": "prepend",
                    "instruction": "INSTRUCTION_SENTINEL",
                },
            },
            "retries": 1,
        }],
    }
    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    manager = StateManager(workspace=tmp_path, run_id="retry-content")
    manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, manager)

    import orchestrator.workflow.prompting as prompting

    original_render = prompting.render_content_snapshot
    render_count = 0

    def _render_once(*args, **kwargs):
        nonlocal render_count
        render_count += 1
        return original_render(*args, **kwargs)

    monkeypatch.setattr(prompting, "render_content_snapshot", _render_once, raising=False)
    prompts: list[str] = []

    def _prepare_invocation(*args, **kwargs):
        prompt = kwargs.get("prompt_content") or ""
        prompts.append(prompt)
        return SimpleNamespace(input_mode="stdin", prompt=prompt), None

    executions = 0

    def _execute(_invocation, **_kwargs):
        nonlocal executions
        executions += 1
        if executions == 1:
            dependency.write_text("new-attempt-body\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=1 if executions == 1 else 0,
            stdout=b"retry" if executions == 1 else b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()

    assert state["steps"]["Review"]["exit_code"] == 0
    assert render_count == 2
    assert len(prompts) == 2
    assert "old-attempt-body" in prompts[0]
    assert "new-attempt-body" not in prompts[0]
    assert "new-attempt-body" in prompts[1]
    assert "old-attempt-body" not in prompts[1]
    assert prompts[0].index("INSTRUCTION_SENTINEL") < prompts[0].index("BASE_PROMPT_SENTINEL")
    assert manager.load().provider_attempt_allocations == {}
    assert not (manager.run_root / "workflow_lisp" / "prompt_dependencies").exists()


def test_typed_content_attempt_publishes_exact_final_prompt_before_preparation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A typed ordinary attempt publishes its one-render record before launch."""
    repo = Path(__file__).resolve().parents[1]
    fixture = repo / "tests/fixtures/workflow_lisp/provider_prompt_dependencies/mixed.orc"
    compiled = compile_stage3_module(
        fixture.relative_to(repo),
        entry_workflow="mixed",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=repo,
        lowering_route="wcc_m4",
    )
    bundle = compiled.validated_bundles["mixed"]
    (tmp_path / "artifacts/work").mkdir(parents=True)
    (tmp_path / "artifacts/context").mkdir(parents=True)
    (tmp_path / "artifacts/work/required.md").write_text(
        "REQUIRED_DEPENDENCY_SENTINEL\n",
        encoding="utf-8",
    )
    (tmp_path / "artifacts/context/optional.md").write_text(
        "OPTIONAL_DEPENDENCY_SENTINEL\n",
        encoding="utf-8",
    )
    bound_inputs = {
        "inputs__required": "artifacts/work/required.md",
        "inputs__optional": "artifacts/context/optional.md",
    }
    assert set(bound_inputs) == {
        name
        for name in workflow_runtime_input_contracts(bundle)
        if not name.startswith("__write_root__")
    }
    manager = StateManager(tmp_path, run_id="typed-content-attempt")
    manager.initialize(fixture.as_posix(), bound_inputs=bound_inputs)
    executor = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0)
    captured: dict[str, object] = {}
    import orchestrator.workflow.prompt_dependency_evidence as evidence_owner

    original_render = evidence_owner.render_content_snapshot
    render_count = 0

    def _render_once(*args, **kwargs):
        nonlocal render_count
        render_count += 1
        return original_render(*args, **kwargs)

    monkeypatch.setattr(evidence_owner, "render_content_snapshot", _render_once)

    def _prepare_invocation(*args, **kwargs):
        prompt = kwargs.get("prompt_content") or ""
        persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))[
            "provider_attempt_allocations"
        ]
        assert len(persisted) == 1
        events = next(iter(persisted.values()))["events"]
        assert [event["event"] for event in events] == ["allocated", "evidence_published"]
        evidence_path = manager.run_root / events[-1]["relative_path"]
        assert evidence_path.is_file()
        captured.update(prompt=prompt, env=dict(kwargs.get("env") or {}), evidence=evidence_path)
        return SimpleNamespace(input_mode="stdin", prompt=prompt), None

    def _execute(_invocation, **_kwargs):
        output = tmp_path / str(captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "RESULT_SENTINEL"}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute(on_error="stop")

    assert captured, json.dumps(state, indent=2, sort_keys=True)
    prompt = str(captured["prompt"])
    evidence = json.loads(Path(captured["evidence"]).read_text(encoding="ascii"))
    assert state["status"] == "completed"
    assert render_count == 1
    assert "REQUIRED_DEPENDENCY_SENTINEL" in prompt
    assert "OPTIONAL_DEPENDENCY_SENTINEL" in prompt
    assert evidence["final_prompt"] == {
        "bytes": len(prompt.encode("utf-8")),
        "sha256": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }
    assert evidence["attempt"]["scope"]["runtime_step_id"] == "root.mixed__result"


def test_typed_failure_row_ids_are_derived_by_the_evidence_owner() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import authored_row_id

    repo = Path(__file__).resolve().parents[1]
    fixture = repo / "tests/fixtures/workflow_lisp/provider_prompt_dependencies/mixed.orc"
    compiled = compile_stage3_module(
        fixture.relative_to(repo),
        entry_workflow="mixed",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=repo,
        lowering_route="wcc_m4",
    )
    contract = next(
        node.execution_config.compiler_prompt_dependency_contract
        for node in compiled.validated_bundles["mixed"].ir.nodes.values()
    )

    first = authored_row_id(contract, role="required", authored_index=0)
    second = authored_row_id(contract, role="required", authored_index=1)

    assert first.startswith("sha256:") and len(first) == 71
    assert first != second


def test_typed_success_publication_failure_stops_before_provider_preparation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    fixture = repo / "tests/fixtures/workflow_lisp/provider_prompt_dependencies/mixed.orc"
    compiled = compile_stage3_module(
        fixture.relative_to(repo),
        entry_workflow="mixed",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=repo,
        lowering_route="wcc_m4",
    )
    bundle = compiled.validated_bundles["mixed"]
    (tmp_path / "artifacts/work").mkdir(parents=True)
    (tmp_path / "artifacts/context").mkdir(parents=True)
    (tmp_path / "artifacts/work/required.md").write_text("R\n", encoding="utf-8")
    (tmp_path / "artifacts/context/optional.md").write_text("O\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="typed-publication-failure")
    manager.initialize(
        fixture.as_posix(),
        bound_inputs={
            "inputs__required": "artifacts/work/required.md",
            "inputs__optional": "artifacts/context/optional.md",
        },
    )
    executor = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0)
    preparation_count = 0
    publication_count = 0

    def _reject_publication(*_args, **_kwargs):
        nonlocal publication_count
        publication_count += 1
        raise OSError("PUBLICATION_FAILURE_SENTINEL")

    def _prepare(*_args, **_kwargs):
        nonlocal preparation_count
        preparation_count += 1
        raise AssertionError("provider preparation must not be reached")

    monkeypatch.setattr(
        "orchestrator.workflow.executor.publish_evidence_file",
        _reject_publication,
    )
    executor.provider_executor.prepare_invocation = _prepare

    state = executor.execute(on_error="stop")

    step = state["steps"]["mixed__result"]
    assert step["exit_code"] == 2
    assert step["error"]["context"]["reason"] == (
        "prompt_dependency_evidence_publication_failed"
    )
    assert preparation_count == 0
    assert publication_count == 1
    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    events = next(iter(persisted["provider_attempt_allocations"].values()))["events"]
    assert [event["event"] for event in events] == ["allocated"]


@pytest.mark.parametrize(
    ("category", "operation"),
    [
        ("unreadable_dependency", "read"),
        ("invalid_utf8_dependency", "decode"),
    ],
)
def test_typed_snapshot_failure_publishes_closed_row_context_before_preparation(
    tmp_path: Path,
    monkeypatch,
    category: str,
    operation: str,
) -> None:
    executor, manager = _typed_dependency_runtime(
        tmp_path,
        f"typed-{category}",
    )
    dependency = tmp_path / "artifacts/work/required.md"
    if category == "invalid_utf8_dependency":
        dependency.write_bytes(b"\xff")
    else:
        original_read_text = Path.read_text

        def _read_text(path: Path, *args, **kwargs):
            if path == dependency:
                raise PermissionError("READ_FAILURE_SENTINEL")
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _read_text)
    executor.provider_executor.prepare_invocation = lambda *_args, **_kwargs: (
        pytest.fail("provider preparation must not be reached")
    )

    state = executor.execute(on_error="stop")

    assert state["steps"]["mixed__result"]["exit_code"] == 2
    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    events = next(iter(persisted["provider_attempt_allocations"].values()))["events"]
    assert [event["event"] for event in events] == ["allocated", "evidence_published"]
    record = json.loads(
        (manager.run_root / events[-1]["relative_path"]).read_text(encoding="ascii")
    )
    assert record["record_kind"] == "failure"
    assert record["failure"]["category"] == category
    assert record["failure"]["operation"] == operation
    assert record["failure"]["evaluated_relpath"] == "artifacts/work/required.md"
    assert record["failure"]["authored_row_id"].startswith("sha256:")
    assert record["provider_calls"] == {"preparation": False, "execution": False}


def test_typed_missing_required_failure_publishes_closed_row_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-missing-required")
    original_prologue = executor._execute_prologue

    def _delete_after_prologue(state, *, resume):
        result = original_prologue(state, resume=resume)
        (tmp_path / "artifacts/work/required.md").unlink()
        return result

    monkeypatch.setattr(executor, "_execute_prologue", _delete_after_prologue)
    executor.provider_executor.prepare_invocation = lambda *_args, **_kwargs: (
        pytest.fail("provider preparation must not be reached")
    )

    state = executor.execute(on_error="stop")

    assert state["steps"]["mixed__result"]["exit_code"] == 2
    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    events = next(iter(persisted["provider_attempt_allocations"].values()))["events"]
    record = json.loads(
        (manager.run_root / events[-1]["relative_path"]).read_text(encoding="ascii")
    )
    assert record["failure"] == {
        "category": "missing_required_dependency",
        "operation": "resolve",
        "authored_row_id": record["failure"]["authored_row_id"],
        "evaluated_relpath": "artifacts/work/required.md",
    }
    assert record["failure"]["authored_row_id"].startswith("sha256:")


def test_typed_invalid_injection_contract_publishes_failure_before_preparation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-invalid-injection")

    def _reject_injection(*_args, **_kwargs):
        raise ValueError("INVALID_INJECTION_SENTINEL")

    monkeypatch.setattr(
        executor.prompt_composer,
        "apply_rendered_content_dependency",
        _reject_injection,
    )
    executor.provider_executor.prepare_invocation = lambda *_args, **_kwargs: (
        pytest.fail("provider preparation must not be reached")
    )

    state = executor.execute(on_error="stop")

    assert state["steps"]["mixed__result"]["exit_code"] == 2
    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    events = next(iter(persisted["provider_attempt_allocations"].values()))["events"]
    assert [event["event"] for event in events] == ["allocated", "evidence_published"]
    record = json.loads(
        (manager.run_root / events[-1]["relative_path"]).read_text(encoding="ascii")
    )
    assert record["record_kind"] == "failure"
    assert record["failure"] == {
        "category": "invalid_injection_contract",
        "operation": "render",
        "authored_row_id": None,
        "evaluated_relpath": None,
    }
    assert record["provider_calls"] == {"preparation": False, "execution": False}


def test_typed_prompt_completion_failures_are_not_dependency_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for failure_kind, sentinel in (
        ("typed-evidence", "TYPED_EVIDENCE_WRITE_SENTINEL"),
        ("later-completion", "PROMPT_COMPLETION_SENTINEL"),
        ("unencodable-completion", None),
        ("non-string-completion", None),
    ):
        workspace = tmp_path / failure_kind
        workspace.mkdir()
        executor, manager = _typed_dependency_runtime(
            workspace,
            f"typed-{failure_kind}-failure",
        )
        if failure_kind == "typed-evidence":
            _replace_typed_prompt_inputs(
                executor,
                (
                    {
                        "binding_name": "context",
                        "value_source": {"ref": "inputs.context"},
                    },
                ),
            )
            monkeypatch.setattr(
                executor,
                "_resolve_typed_prompt_input_value",
                lambda *_args, **_kwargs: ({"focus": "contracts"}, None),
            )
            monkeypatch.setattr(
                executor.prompt_composer,
                "apply_typed_prompt_input_injection",
                lambda *_args, **_kwargs: (
                    "COMPLETED_PROMPT",
                    [{"binding_name": "context"}],
                ),
            )

            def _reject_typed_evidence(**_kwargs):
                raise OSError(sentinel)

            monkeypatch.setattr(
                executor,
                "_write_typed_prompt_input_evidence",
                _reject_typed_evidence,
            )
        elif failure_kind == "later-completion":
            def _reject_completion(*_args, **_kwargs):
                raise ValueError(sentinel)

            monkeypatch.setattr(
                executor.prompt_composer,
                "apply_output_contract_prompt_suffix",
                _reject_completion,
            )
        elif failure_kind == "unencodable-completion":
            monkeypatch.setattr(
                executor.prompt_composer,
                "apply_output_contract_prompt_suffix",
                lambda *_args, **_kwargs: "\ud800",
            )
        else:
            monkeypatch.setattr(
                executor.prompt_composer,
                "apply_output_contract_prompt_suffix",
                lambda *_args, **_kwargs: object(),
            )
        executor.provider_executor.prepare_invocation = lambda *_args, **_kwargs: (
            pytest.fail("provider preparation must not be reached")
        )

        state = executor.execute(on_error="stop")

        step = state["steps"]["mixed__result"]
        assert step["exit_code"] == 2
        assert step["error"]["context"]["reason"] == "prompt_completion_failed"
        if sentinel is not None:
            assert sentinel in step["error"]["context"]["error"]
        persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
        events = next(iter(persisted["provider_attempt_allocations"].values()))[
            "events"
        ]
        assert [event["event"] for event in events] == ["allocated"]


def test_typed_truncation_debug_matches_published_render_metadata(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-truncation-debug")
    (tmp_path / "artifacts/work/required.md").write_text(
        "R" * 262144,
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def _prepare(*_args, **kwargs):
        persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
        events = next(iter(persisted["provider_attempt_allocations"].values()))["events"]
        captured["record"] = json.loads(
            (manager.run_root / events[-1]["relative_path"]).read_text(encoding="ascii")
        )
        captured["env"] = dict(kwargs.get("env") or {})
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content") or ""), None

    def _execute(_invocation, **_kwargs):
        output = tmp_path / str(captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "RESULT_SENTINEL"}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare
    executor.provider_executor.execute = _execute

    state = executor.execute(on_error="stop")

    record = captured["record"]
    injection = record["injection"]
    debug = state["steps"]["mixed__result"]["debug"]["injection"]
    details = debug["truncation_details"]
    assert injection["was_truncated"] is True
    assert debug["injection_truncated"] is True
    assert details == {
        "total_size": injection["normalized_total_bytes"],
        "shown_size": injection["shown_bytes"],
        "files_shown": injection["files_shown"],
        "files_truncated": injection["files_truncated"],
        "files_omitted": injection["files_omitted"],
    }
    assert sum(group["render_status"] == "truncated" for group in record["canonical_groups"]) == 1


def test_typed_retry_allocates_and_publishes_one_fresh_record_per_attempt(
    tmp_path: Path,
) -> None:
    executor, manager = _typed_dependency_runtime(tmp_path, "typed-retry-freshness")
    executor.max_retries = 1
    executor.retry_delay_ms = 0
    dependency = tmp_path / "artifacts/work/required.md"
    dependency.write_text("OLD_TYPED_ATTEMPT_SENTINEL\n", encoding="utf-8")
    prompts: list[str] = []
    environments: list[dict[str, str]] = []

    def _prepare(*_args, **kwargs):
        prompt = kwargs.get("prompt_content") or ""
        prompts.append(prompt)
        environments.append(dict(kwargs.get("env") or {}))
        return SimpleNamespace(input_mode="stdin", prompt=prompt), None

    executions = 0

    def _execute(_invocation, **_kwargs):
        nonlocal executions
        executions += 1
        if executions == 1:
            dependency.write_text("NEW_TYPED_ATTEMPT_SENTINEL\n", encoding="utf-8")
        else:
            output = tmp_path / environments[-1]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps({"approved": True, "summary": "RESULT_SENTINEL"}) + "\n",
                encoding="utf-8",
            )
        return SimpleNamespace(
            exit_code=1 if executions == 1 else 0,
            stdout=b"retry" if executions == 1 else b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare
    executor.provider_executor.execute = _execute

    state = executor.execute(on_error="stop")

    assert state["status"] == "completed"
    assert "OLD_TYPED_ATTEMPT_SENTINEL" in prompts[0]
    assert "NEW_TYPED_ATTEMPT_SENTINEL" not in prompts[0]
    assert "NEW_TYPED_ATTEMPT_SENTINEL" in prompts[1]
    assert "OLD_TYPED_ATTEMPT_SENTINEL" not in prompts[1]
    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    events = next(iter(persisted["provider_attempt_allocations"].values()))["events"]
    assert [(event["ordinal"], event["event"]) for event in events] == [
        (1, "allocated"),
        (1, "evidence_published"),
        (2, "allocated"),
        (2, "evidence_published"),
    ]
    records = [
        json.loads((manager.run_root / event["relative_path"]).read_text(encoding="ascii"))
        for event in events
        if event["event"] == "evidence_published"
    ]
    assert [record["attempt"]["ordinal"] for record in records] == [1, 2]
    required_digests = [
        next(
            group["retained_sha256"]
            for group in record["canonical_groups"]
            if group["canonical_target"] == "artifacts/work/required.md"
        )
        for record in records
    ]
    assert required_digests[0] != required_digests[1]


def test_provider_prompt_injection_renders_collection_consumed_value(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [{"artifact": "context_docs"}],
        },
        "Review the design docs.\n",
        resolved_consumes={
            "root.review": {
                "context_docs": [
                    "docs/design/state-layout.md",
                    "docs/design/runtime-foundation.md",
                ]
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "## Consumed Artifacts" in prompt
    assert '- context_docs: ["docs/design/state-layout.md", "docs/design/runtime-foundation.md"]' in prompt
    assert "Review the design docs." in prompt


def test_prompt_consumes_subset_renders_collection_value(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {"artifact": "context_docs"},
                {"artifact": "review_focus"},
            ],
            "prompt_consumes": ["context_docs"],
        },
        "Review the design docs.\n",
        resolved_consumes={
            "root.review": {
                "context_docs": ["docs/design/state-layout.md"],
                "review_focus": "runtime lane split",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert '- context_docs: ["docs/design/state-layout.md"]' in prompt
    assert "review_focus" not in prompt


def test_adjudicated_provider_prompt_injection_renders_collection_consumed_value(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Judge",
            "adjudicated_provider": {"provider": "mock-provider"},
            "consumes": [{"artifact": "context_docs"}],
            "consumes_injection_position": "append",
        },
        "Judge the candidate output.\n",
        resolved_consumes={
            "root.judge": {
                "context_docs": ["docs/design/runtime-foundation.md"],
            }
        },
        step_name="Judge",
        consume_identity="root.judge",
        uses_qualified_identities=True,
    )

    assert prompt.startswith("Judge the candidate output.")
    assert prompt.rstrip().endswith('Use these consumed artifacts as context for your work.')
    assert '- context_docs: ["docs/design/runtime-foundation.md"]' in prompt


def test_adjudication_consumed_artifacts_for_prompt_keeps_private_collection_values() -> None:
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor.workflow_artifacts = {}
    executor.private_workflow_artifacts = {
        "context_docs": {
            "kind": "collection",
            "type": {"type": "list", "items": "string"},
        }
    }
    executor._uses_qualified_identities = lambda: True

    consumed_artifacts, consumed_relpath_targets = executor._adjudication_consumed_artifacts_for_prompt(
        {
            "name": "Judge",
            "adjudicated_provider": {"provider": "mock-provider"},
            "consumes": [{"artifact": "context_docs"}],
        },
        {
            "_resolved_consumes": {
                "root.judge": {
                    "context_docs": ["docs/design/runtime-foundation.md"],
                }
            }
        },
        step_name="Judge",
        consume_identity="root.judge",
    )

    assert consumed_artifacts == {
        "context_docs": ["docs/design/runtime-foundation.md"],
    }
    assert consumed_relpath_targets == {}


def test_typed_prompt_input_injection_renders_deterministic_block_before_consumes(
    tmp_path: Path,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    prompt, evidence = composer.apply_typed_prompt_input_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [{"artifact": "context_docs"}],
        },
        "## Workspace Dependencies\n- docs/index.md\n\nReview the design docs.\n",
        typed_prompt_inputs=[
            {
                "schema_version": "workflow_lisp_typed_prompt_input.v1",
                "binding_name": "prompt_context",
                "renderer": {
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "accepted_shape": "any_pure_value",
                },
                "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
                "value_type_name": "PromptContext",
                "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
                "u0_row_id": "u0.fixture.prompt_context",
                "c0_row_id": "c0.fixture.prompt_context",
                "injection_order": 0,
            }
        ],
        resolved_typed_values={
            "prompt_context": {
                "design": "docs/design/runtime-foundation.md",
                "focus": "prefer typed values",
            }
        },
        workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
        step_id="root.run-typed-prompt-phase-demo__attempt",
    )
    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [{"artifact": "context_docs"}],
        },
        prompt,
        resolved_consumes={"root.review": {"context_docs": ["docs/index.md"]}},
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )
    prompt = composer.apply_output_contract_prompt_suffix(
        {
            "name": "Review",
            "provider": "mock-provider",
            "output_bundle": {
                "path": "state/review_bundle.json",
                "fields": [
                    {
                        "name": "status",
                        "json_pointer": "/status",
                        "type": "string",
                    }
                ],
            },
        },
        prompt,
    )

    assert "## Workspace Dependencies" in prompt
    assert '"focus":"prefer typed values"' in prompt
    assert prompt.index("## Consumed Artifacts") < prompt.index('"focus":"prefer typed values"')
    assert prompt.index('"focus":"prefer typed values"') < prompt.index("Output Contract")
    assert evidence[0]["rendered_bytes_digest"].startswith("sha256:")


def test_typed_prompt_input_injection_omits_evidence_when_no_typed_rows(
    tmp_path: Path,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    prompt, evidence = composer.apply_typed_prompt_input_injection(
        {"name": "Review", "provider": "mock-provider"},
        "Review the design docs.\n",
        typed_prompt_inputs=[],
        resolved_typed_values={},
        workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
        step_id="root.run-typed-prompt-phase-demo__attempt",
    )

    assert prompt == "Review the design docs.\n"
    assert evidence == []


def test_provider_expected_outputs_appends_contract_block_to_prompt(tmp_path: Path):
    """Provider steps append a deterministic output contract block by default."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review this patch.\n")

    workflow = {
        "version": "1.1.1",
        "name": "prompt-contract-default",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert "Output Contract" in captured["prompt"]
    assert "name: review_decision" in captured["prompt"]
    assert "path: state/review_decision.txt" in captured["prompt"]
    assert "type: enum" in captured["prompt"]


def test_provider_variant_output_appends_variant_contract_block_to_prompt(tmp_path: Path, monkeypatch) -> None:
    """Provider steps append a deterministic variant contract block for experimental v2.14 internals."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "implement.md").write_text("Implement the backlog item.\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "prompt-contract-variant-output",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Implement",
            "id": "implement",
            "provider": "mock_provider",
            "input_file": "prompts/implement.md",
            "variant_output": {
                "path": "state/variant_bundle.json",
                "discriminant": {
                    "name": "implementation_state",
                    "json_pointer": "/implementation_state",
                    "type": "enum",
                    "allowed": ["COMPLETED", "BLOCKED"],
                },
                "variants": {
                    "COMPLETED": {
                        "fields": [
                            {
                                "name": "execution_report_path",
                                "json_pointer": "/execution_report_path",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                    "BLOCKED": {
                        "fields": [
                            {
                                "name": "progress_report_path",
                                "json_pointer": "/progress_report_path",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            },
                            {
                                "name": "blocker_class",
                                "json_pointer": "/blocker_class",
                                "type": "enum",
                                "allowed": [
                                    "missing_resource",
                                    "unavailable_hardware",
                                    "roadmap_conflict",
                                    "external_dependency_outside_authority",
                                    "user_decision_required",
                                    "unrecoverable_after_fix_attempt",
                                ],
                            },
                        ]
                    },
                },
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
        (tmp_path / "artifacts" / "work" / "execution_report.md").write_text("# report\n", encoding="utf-8")
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "variant_bundle.json").write_text(
            json.dumps(
                {
                    "implementation_state": "COMPLETED",
                    "execution_report_path": "artifacts/work/execution_report.md",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Implement"]["exit_code"] == 0
    assert "Variant Output Contract" in captured["prompt"]
    assert "ORCHESTRATOR_OUTPUT_BUNDLE_PATH" in captured["prompt"]
    assert "implementation_state" in captured["prompt"]
    assert "execution_report_path" in captured["prompt"]
    assert "Relpath values are workspace-relative" in captured["prompt"]
    assert "for `under: artifacts/work`, write `artifacts/work/...`" in captured["prompt"]
    assert "for `under: artifacts/review`, write `artifacts/review/...`" in captured["prompt"]


def test_provider_variant_output_receives_runtime_bundle_env(tmp_path: Path, monkeypatch) -> None:
    """Provider variant outputs receive the runtime-owned bundle path out of band."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review this.\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "provider-variant-output-env",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "env": {"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": "state/wrong.json"},
            "variant_output": {
                "path": "state/review.json",
                "discriminant": {
                    "name": "variant",
                    "json_pointer": "/variant",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                },
                "variants": {
                    "APPROVE": {"fields": []},
                    "REVISE": {"fields": []},
                },
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"env": {}}

    def _prepare_invocation(*args, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content") or ""), None

    def _execute(_invocation, **_kwargs):
        bundle_path = tmp_path / captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.write_text(json.dumps({"variant": "REVISE"}) + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == "state/review.json"


def test_provider_variant_output_wrong_bundle_path_fails_contract(tmp_path: Path, monkeypatch) -> None:
    """Provider wrong-path bundles are not normalized into the declared target."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review this.\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "provider-variant-output-wrong-path",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "variant_output": {
                "path": "state/review_result_bundle.json",
                "discriminant": {
                    "name": "variant",
                    "json_pointer": "/variant",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                },
                "variants": {
                    "APPROVE": {"fields": []},
                    "REVISE": {"fields": []},
                },
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    def _prepare_invocation(*args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content") or ""), None

    def _execute(_invocation, **_kwargs):
        wrong_path = tmp_path / "state" / "review_result_bundle" / "result_bundle.json"
        wrong_path.parent.mkdir(parents=True, exist_ok=True)
        wrong_path.write_text(json.dumps({"variant": "REVISE"}) + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    step_state = state["steps"]["Review"]
    assert step_state["exit_code"] == 2
    assert step_state["error"]["type"] == "contract_violation"
    violations = step_state["error"]["context"]["violations"]
    assert violations[0]["type"] == "missing_bundle_file"
    assert violations[0]["context"]["path"] == "state/review_result_bundle.json"
    assert not (tmp_path / "state" / "review_result_bundle.json").exists()


def test_variant_output_prompt_contract_renders_structured_nested_constraints() -> None:
    """Rendered variant contracts must preserve field constraints as parseable structure."""
    from orchestrator.contracts.prompt_contract import render_variant_output_contract_block

    prompt_block = render_variant_output_contract_block({
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "variants": {
            "COMPLETED": {
                "fields": [{
                    "name": "execution_report_path",
                    "json_pointer": "/execution_report_path",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }]
            },
            "BLOCKED": {
                "fields": [{
                    "name": "progress_report_path",
                    "json_pointer": "/progress_report_path",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }]
            },
        },
    })

    rendered = _variant_contract_body_as_yaml(prompt_block)
    bundle = rendered[0]
    completed_field = bundle["variants"]["COMPLETED"]["fields"][0]
    blocked_field = bundle["variants"]["BLOCKED"]["fields"][0]
    assert "for `under: artifacts/work`, write `artifacts/work/...`" in prompt_block
    assert "for `under: artifacts/review`, write `artifacts/review/...`" in prompt_block
    assert completed_field["under"] == "artifacts/work"
    assert completed_field["must_exist_target"] is True
    assert blocked_field["under"] == "artifacts/work"
    assert blocked_field["must_exist_target"] is True


def test_provider_expected_outputs_prompt_uses_resolved_path_templates(tmp_path: Path):
    """Output contract prompt suffix shows runtime-resolved expected output paths."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review this patch.\n")

    workflow = {
        "version": "2.1",
        "name": "prompt-contract-resolved-path",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
                "default": "state/default-root",
            }
        },
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "expected_outputs": [{
                "name": "review_decision",
                "path": "${inputs.state_root}/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(
        "workflow.yaml",
        bound_inputs={"state_root": "state/run-root"},
    )
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "state" / "run-root").mkdir(parents=True, exist_ok=True)
        (tmp_path / "state" / "run-root" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert "path: state/run-root/review_decision.txt" in captured["prompt"]
    assert "path: ${inputs.state_root}/review_decision.txt" not in captured["prompt"]


def test_provider_output_bundle_appends_contract_block_with_resolved_path(tmp_path: Path):
    """Provider steps append concrete JSON output_bundle contracts to prompts."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "docs" / "backlog").mkdir(parents=True)
    (tmp_path / "docs" / "backlog" / "item.md").write_text("# Item\n")
    (tmp_path / "prompts" / "select.md").write_text("Select a backlog item.\n")

    workflow = {
        "version": "2.7",
        "name": "prompt-contract-output-bundle",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
                "default": "state/default-root",
            }
        },
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Select",
            "provider": "mock_provider",
            "input_file": "prompts/select.md",
            "output_bundle": {
                "path": "${inputs.state_root}/${run.id}/selection.json",
                "fields": [
                    {
                        "name": "selection_decision",
                        "json_pointer": "/selection_decision",
                        "type": "enum",
                        "allowed": ["READY", "NONE_READY"],
                    },
                    {
                        "name": "selected_item_path",
                        "json_pointer": "/selected_item_path",
                        "type": "relpath",
                        "under": "docs/backlog",
                        "must_exist_target": True,
                    },
                ],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(
        "workflow.yaml",
        bound_inputs={"state_root": "state/run-root"},
    )
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        bundle_path = tmp_path / "state" / "run-root" / "test-run" / "selection.json"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps({
                "selection_decision": "READY",
                "selected_item_path": "docs/backlog/item.md",
            })
            + "\n"
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Select"]["exit_code"] == 0
    assert state["steps"]["Select"]["artifacts"] == {
        "selection_decision": "READY",
        "selected_item_path": "docs/backlog/item.md",
    }
    assert "Write the following JSON bundle exactly as specified." in captured["prompt"]
    assert "ORCHESTRATOR_OUTPUT_BUNDLE_PATH" in captured["prompt"]
    assert "path: state/run-root/test-run/selection.json" in captured["prompt"]
    assert "path: ${inputs.state_root}/${run.id}/selection.json" not in captured["prompt"]
    assert "name: selection_decision" in captured["prompt"]
    assert "json_pointer: /selection_decision" in captured["prompt"]
    assert "allowed: READY, NONE_READY" in captured["prompt"]
    assert "name: selected_item_path" in captured["prompt"]
    assert "must_exist_target: true" in captured["prompt"]


def test_provider_output_bundle_receives_runtime_bundle_env(tmp_path: Path):
    """Provider output bundles receive the runtime-owned bundle path out of band."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "docs" / "backlog").mkdir(parents=True)
    (tmp_path / "docs" / "backlog" / "item.md").write_text("# Item\n", encoding="utf-8")
    (tmp_path / "prompts" / "select.md").write_text("Select a backlog item.\n", encoding="utf-8")

    workflow = {
        "version": "2.7",
        "name": "provider-output-bundle-env",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
                "default": "state/default-root",
            }
        },
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Select",
            "provider": "mock_provider",
            "input_file": "prompts/select.md",
            "env": {"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": "state/wrong.json"},
            "output_bundle": {
                "path": "${inputs.state_root}/${run.id}/selection.json",
                "fields": [
                    {
                        "name": "selection_decision",
                        "json_pointer": "/selection_decision",
                        "type": "enum",
                        "allowed": ["READY", "NONE_READY"],
                    },
                    {
                        "name": "selected_item_path",
                        "json_pointer": "/selected_item_path",
                        "type": "relpath",
                        "under": "docs/backlog",
                        "must_exist_target": True,
                    },
                ],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(
        "workflow.yaml",
        bound_inputs={"state_root": "state/run-root"},
    )
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"env": {}}

    def _prepare_invocation(*args, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content") or ""), None

    def _execute(_invocation, **_kwargs):
        bundle_path = tmp_path / captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.write_text(
            json.dumps({
                "selection_decision": "READY",
                "selected_item_path": "docs/backlog/item.md",
            })
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Select"]["exit_code"] == 0
    assert captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == "state/run-root/test-run/selection.json"


def test_provider_output_bundle_schema_mismatch(tmp_path: Path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "select.md").write_text("Select a backlog item.\n", encoding="utf-8")

    workflow = {
        "version": "2.7",
        "name": "provider-output-bundle-schema-mismatch",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
                "default": "state/default-root",
            }
        },
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Select",
            "provider": "mock_provider",
            "input_file": "prompts/select.md",
            "output_bundle": {
                "path": "${inputs.state_root}/${run.id}/selection.json",
                "fields": [
                    {
                        "name": "selection_decision",
                        "json_pointer": "/selection_decision",
                        "type": "enum",
                        "allowed": ["READY", "NONE_READY"],
                    },
                ],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml", bound_inputs={"state_root": "state/run-root"})
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"env": {}}

    def _prepare_invocation(*args, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content") or ""), None

    def _execute(_invocation, **_kwargs):
        bundle_path = tmp_path / captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps({"wrong_field": "READY"}) + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    violations = state["steps"]["Select"]["error"]["context"]["violations"]

    assert state["steps"]["Select"]["exit_code"] == 2
    assert any(violation["type"] == "json_pointer_not_found" for violation in violations)


def test_provider_output_bundle_stale_input(tmp_path: Path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "select.md").write_text("Select a backlog item.\n", encoding="utf-8")
    stale_bundle = tmp_path / "state" / "run-root" / "old-run" / "selection.json"
    stale_bundle.parent.mkdir(parents=True, exist_ok=True)
    stale_bundle.write_text(
        json.dumps({"selection_decision": "READY"}) + "\n",
        encoding="utf-8",
    )

    workflow = {
        "version": "2.7",
        "name": "provider-output-bundle-stale-input",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
                "default": "state/default-root",
            }
        },
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Select",
            "provider": "mock_provider",
            "input_file": "prompts/select.md",
            "output_bundle": {
                "path": "${inputs.state_root}/${run.id}/selection.json",
                "fields": [
                    {
                        "name": "selection_decision",
                        "json_pointer": "/selection_decision",
                        "type": "enum",
                        "allowed": ["READY", "NONE_READY"],
                    },
                ],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="fresh-run")
    state_manager.initialize("workflow.yaml", bound_inputs={"state_root": "state/run-root"})
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    def _prepare_invocation(*args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content") or ""), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    violations = state["steps"]["Select"]["error"]["context"]["violations"]

    assert state["steps"]["Select"]["exit_code"] == 2
    assert any(violation["type"] == "missing_bundle_file" for violation in violations)


def test_provider_output_bundle_missing_bundle(tmp_path: Path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "select.md").write_text("Select a backlog item.\n", encoding="utf-8")

    workflow = {
        "version": "2.7",
        "name": "provider-output-bundle-missing-bundle",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
                "default": "state/default-root",
            }
        },
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Select",
            "provider": "mock_provider",
            "input_file": "prompts/select.md",
            "output_bundle": {
                "path": "${inputs.state_root}/${run.id}/selection.json",
                "fields": [
                    {
                        "name": "selection_decision",
                        "json_pointer": "/selection_decision",
                        "type": "enum",
                        "allowed": ["READY", "NONE_READY"],
                    },
                ],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml", bound_inputs={"state_root": "state/run-root"})
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    def _prepare_invocation(*args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content") or ""), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    violations = state["steps"]["Select"]["error"]["context"]["violations"]

    assert state["steps"]["Select"]["exit_code"] == 2
    assert any(violation["type"] == "missing_bundle_file" for violation in violations)


def test_render_output_bundle_contract_block_root_field_renders_json_value_schema() -> None:
    """A single empty-pointer field renders one JSON-value schema, not an object contract."""
    root_bundle = {
        "path": "state/run-root/test-run/result.json",
        "fields": [
            {
                "name": "__result__",
                "json_pointer": "",
                "type": "bool",
            }
        ],
    }

    rendered = render_output_bundle_contract_block(root_bundle)

    assert "format: JSON value" in rendered
    assert "format: JSON object" not in rendered
    assert "fields:" not in rendered
    assert "name: __result__" not in rendered
    assert "json_pointer:" not in rendered
    assert "type: bool" in rendered
    assert "path: state/run-root/test-run/result.json" in rendered


def test_output_bundle_guidance_renders_nested_context_and_canonical_examples() -> None:
    contract = {
        "path": "state/review/result.json",
        "guidance": {
            "description": "Complete review bundle.",
            "format_hint": "One review object.",
            "example": {
                "metrics": {"clarity": None},
                "approved": True,
            },
        },
        "fields": [
            {
                "name": "blocker__details__code",
                "json_pointer": "/blocker/details/code",
                "type": "string",
                "guidance_context": [
                    {
                        "json_pointer": "/blocker",
                        "description": "Blocking condition context.",
                        "example": None,
                    },
                    {
                        "json_pointer": "/blocker/details",
                        "format_hint": "Nested blocker details.",
                        "example": {"owner": None},
                    },
                ],
                "description": "Stable blocker code.",
                "format_hint": "Uppercase token.",
                "example": "MISSING_RESOURCE",
            }
        ],
    }

    rendered = render_output_bundle_contract_block(contract)
    bundle = _output_contract_body_as_yaml(rendered)[0]

    assert list(bundle).index("guidance") < list(bundle).index("fields")
    assert bundle["guidance"] == contract["guidance"]
    field = bundle["fields"][0]
    assert [row["json_pointer"] for row in field["guidance_context"]] == [
        "/blocker",
        "/blocker/details",
    ]
    assert field["description"] == contract["fields"][0]["description"]
    for semantic_value in (
        "Complete review bundle.",
        "One review object.",
        "Blocking condition context.",
        "Nested blocker details.",
        "Stable blocker code.",
        "Uppercase token.",
    ):
        assert rendered.count(semantic_value) == 1
    for example_token in (
        'example: {"approved":true,"metrics":{"clarity":null}}',
        "example: null",
        'example: {"owner":null}',
        'example: "MISSING_RESOURCE"',
    ):
        assert rendered.count(example_token) == 1


def test_typed_guidance_strings_roundtrip_through_structured_prompt_sections() -> None:
    from orchestrator.contracts.prompt_contract import render_variant_output_contract_block

    output_contract = {
        "path": "state/review/result.json",
        "guidance": {
            "description": "Bundle: retain # marker",
            "format_hint": "null",
        },
        "fields": [
            {
                "name": "blocker__code",
                "json_pointer": "/blocker/code",
                "type": "string",
                "guidance_context": [
                    {
                        "json_pointer": "/blocker",
                        "description": "First line\nSecond line: keep # marker",
                        "format_hint": "yes",
                    }
                ],
                "description": "[APPROVE, REVISE]",
                "format_hint": "Résumé ✓",
            }
        ],
    }
    variant_contract = {
        "path": "state/review/decision.json",
        "guidance": {
            "description": "Variant bundle: keep # marker",
            "format_hint": "false",
        },
        "discriminant": {
            "name": "decision",
            "json_pointer": "/decision",
            "type": "enum",
            "allowed": ["APPROVE", "REVISE"],
        },
        "shared_fields": [
            {
                "name": "confidence",
                "json_pointer": "/confidence",
                "type": "float",
                "guidance_by_variant": {
                    "APPROVE": {
                        "description": "Decision: approve # exact",
                        "format_hint": "on",
                    },
                    "REVISE": {
                        "description": "Décision: réviser # exact",
                        "format_hint": "[0, 1]",
                    },
                },
            }
        ],
        "variants": {
            "APPROVE": {"fields": []},
            "REVISE": {
                "fields": [
                    {
                        "name": "reason",
                        "json_pointer": "/reason",
                        "type": "string",
                        "description": "Reason: multiline\nKeep # exactly",
                        "format_hint": "true",
                    }
                ]
            },
        },
    }

    rendered_output = render_output_bundle_contract_block(output_contract)
    rendered_variant = render_variant_output_contract_block(variant_contract)
    output_bundle = _output_contract_body_as_yaml(rendered_output)[0]
    variant_bundle = _variant_contract_body_as_yaml(rendered_variant)[0]

    assert output_bundle["guidance"] == output_contract["guidance"]
    assert output_bundle["fields"][0]["description"] == "[APPROVE, REVISE]"
    assert output_bundle["fields"][0]["format_hint"] == "Résumé ✓"
    assert (
        output_bundle["fields"][0]["guidance_context"]
        == output_contract["fields"][0]["guidance_context"]
    )
    assert variant_bundle["guidance"] == variant_contract["guidance"]
    assert (
        variant_bundle["shared_fields"][0]["guidance_by_variant"]
        == variant_contract["shared_fields"][0]["guidance_by_variant"]
    )
    assert (
        variant_bundle["variants"]["REVISE"]["fields"][0]["description"]
        == "Reason: multiline\nKeep # exactly"
    )
    assert (
        variant_bundle["variants"]["REVISE"]["fields"][0]["format_hint"]
        == "true"
    )

    output_values = (
        *output_contract["guidance"].values(),
        output_contract["fields"][0]["description"],
        output_contract["fields"][0]["format_hint"],
        *(
            value
            for key, value in output_contract["fields"][0]["guidance_context"][0].items()
            if key != "json_pointer"
        ),
    )
    variant_values = (
        *variant_contract["guidance"].values(),
        *(
            value
            for payload in variant_contract["shared_fields"][0]["guidance_by_variant"].values()
            for value in payload.values()
        ),
        variant_contract["variants"]["REVISE"]["fields"][0]["description"],
        variant_contract["variants"]["REVISE"]["fields"][0]["format_hint"],
    )
    for rendered, semantic_values in (
        (rendered_output, output_values),
        (rendered_variant, variant_values),
    ):
        for semantic_value in semantic_values:
            encoded = json.dumps(semantic_value, ensure_ascii=False)
            assert rendered.count(encoded) == 1


def test_variant_output_guidance_uses_discriminant_order_and_canonical_examples() -> None:
    from orchestrator.contracts.prompt_contract import render_variant_output_contract_block

    contract = {
        "path": "state/review/decision.json",
        "guidance": {
            "description": "Choose one review decision.",
            "example": {"owner": None, "decision": "APPROVE"},
        },
        "discriminant": {
            "name": "decision",
            "json_pointer": "/decision",
            "type": "enum",
            "allowed": ["APPROVE", "REVISE"],
        },
        "shared_fields": [
            {
                "name": "report",
                "json_pointer": "/report",
                "type": "optional",
                "item": {"type": "string"},
                "description": "Shared report path.",
                "example": None,
            },
            {
                "name": "confidence",
                "json_pointer": "/confidence",
                "type": "float",
                "guidance_by_variant": {
                    "APPROVE": {
                        "description": "Approval confidence.",
                        "example": 0.95,
                    },
                    "REVISE": {
                        "description": "Revision confidence.",
                        "example": 0.8,
                    },
                },
            },
        ],
        "variants": {
            "APPROVE": {
                "fields": [
                    {
                        "name": "approved",
                        "json_pointer": "/approved",
                        "type": "bool",
                        "description": "Approval state.",
                        "example": True,
                    }
                ]
            },
            "REVISE": {
                "fields": [
                    {
                        "name": "reason",
                        "json_pointer": "/reason",
                        "type": "string",
                        "format_hint": "Concise revision reason.",
                        "example": "Needs tests",
                    }
                ]
            },
        },
    }

    rendered = render_variant_output_contract_block(contract)
    bundle = _variant_contract_body_as_yaml(rendered)[0]

    assert list(bundle).index("guidance") < list(bundle).index("shared_fields")
    confidence = next(
        field for field in bundle["shared_fields"] if field["name"] == "confidence"
    )
    assert list(confidence["guidance_by_variant"]) == ["APPROVE", "REVISE"]
    assert list(bundle["variants"]) == ["APPROVE", "REVISE"]
    for semantic_value in (
        "Choose one review decision.",
        "Shared report path.",
        "Approval confidence.",
        "Revision confidence.",
        "Approval state.",
        "Concise revision reason.",
    ):
        assert rendered.count(semantic_value) == 1
    for example_token in (
        'example: {"decision":"APPROVE","owner":null}',
        "example: null",
        "example: 0.95",
        "example: 0.8",
        "example: true",
    ):
        assert rendered.count(example_token) == 1


def test_compiled_root_guidance_contract_is_the_prompt_renderer_input(tmp_path: Path) -> None:
    """The renderer consumes the production compiler contract, not a hand-built fixture."""
    workflow_path = tmp_path / "compiled_root_guidance_prompt.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defworkflow guided-provider ()",
                '    -> (result Bool :description "Public workflow decision." :example false)',
                "    (provider-result providers.execute",
                "      :prompt prompts.review",
                "      :inputs ()",
                '      :returns (result Bool :description "No blockers remain."',
                '        :format-hint "JSON boolean." :example true))))',
            ]
        ),
        encoding="utf-8",
    )
    compiled = compile_stage3_module(
        workflow_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.review": "prompts/review.md"},
        lowering_route="wcc_m4",
        validate_shared=False,
        workspace_root=tmp_path,
    )
    executable_step = next(
        step
        for step in compiled.lowered_workflows[0].authored_mapping["steps"]
        if "provider" in step
    )

    rendered = PromptComposer(
        workspace=tmp_path,
        asset_resolver=None,
    ).apply_output_contract_prompt_suffix(executable_step, "")

    executable_field = executable_step["output_bundle"]["fields"][0]
    executable_workflow = compiled.lowered_workflows[0].authored_mapping
    assert executable_workflow["result_guidance"] != {
        key: executable_field[key]
        for key in ("description", "format_hint", "example")
    }
    contract_start = next(
        index for index, line in enumerate(rendered.splitlines()) if line.startswith("- path:")
    )
    rendered_contract = yaml.safe_load(
        "\n".join(rendered.splitlines()[contract_start:])
    )[0]
    assert rendered_contract["description"] == executable_field["description"]
    assert rendered_contract["format_hint"] == executable_field["format_hint"]
    assert rendered_contract["example"] == executable_field["example"]
    assert rendered_contract["description"] != executable_workflow["result_guidance"]["description"]
    assert rendered.count(executable_field["description"]) == 1
    assert rendered.count(executable_field["format_hint"]) == 1
    assert executable_workflow["result_guidance"]["description"] not in rendered
    assert rendered.count("example: true") == 1


def test_provider_output_bundle_root_result_appends_json_value_contract_and_persists_result(
    tmp_path: Path,
) -> None:
    """A root output_bundle renders a JSON-value contract and persists `__result__` end to end."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "select.md").write_text("Decide readiness.\n", encoding="utf-8")

    workflow = {
        "version": "2.7",
        "name": "provider-output-bundle-root-result",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
                "default": "state/default-root",
            }
        },
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Decide",
            "provider": "mock_provider",
            "input_file": "prompts/select.md",
            "output_bundle": {
                "path": "${inputs.state_root}/${run.id}/result.json",
                "fields": [
                    {
                        "name": "__result__",
                        "json_pointer": "",
                        "type": "bool",
                    },
                ],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml", bound_inputs={"state_root": "state/run-root"})
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": "", "env": {}}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        captured["env"] = kwargs.get("env") or {}
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        bundle_path = tmp_path / captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text("true\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()

    assert state["steps"]["Decide"]["exit_code"] == 0
    assert state["steps"]["Decide"]["artifacts"] == {"__result__": True}
    assert captured["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == "state/run-root/test-run/result.json"
    assert "Write one JSON value exactly as specified." in captured["prompt"]
    assert "format: JSON value" in captured["prompt"]
    assert "format: JSON object" not in captured["prompt"]
    assert "name: __result__" not in captured["prompt"]
    assert "type: bool" in captured["prompt"]
    assert "path: state/run-root/test-run/result.json" in captured["prompt"]


def test_provider_variant_output_shared_fields_render_once(tmp_path: Path) -> None:
    """variant_output shared_fields should render once outside the variant-specific sections."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "implement.md").write_text("Implement the backlog item.\n", encoding="utf-8")
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "approved-plan.md").write_text("# plan\n", encoding="utf-8")
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "execution_report.md").write_text("# report\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "prompt-contract-variant-shared-fields",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Implement",
            "id": "implement",
            "provider": "mock_provider",
            "input_file": "prompts/implement.md",
            "variant_output": {
                "path": "state/variant_bundle.json",
                "discriminant": {
                    "name": "implementation_state",
                    "json_pointer": "/implementation_state",
                    "type": "enum",
                    "allowed": ["COMPLETED", "BLOCKED"],
                },
                "shared_fields": [
                    {
                        "name": "plan_path",
                        "json_pointer": "/plan_path",
                        "type": "relpath",
                        "under": "docs/plans",
                        "must_exist_target": True,
                    }
                ],
                "variants": {
                    "COMPLETED": {
                        "fields": [
                            {
                                "name": "execution_report_path",
                                "json_pointer": "/execution_report_path",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                    "BLOCKED": {
                        "fields": [
                            {
                                "name": "progress_report_path",
                                "json_pointer": "/progress_report_path",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                },
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "variant_bundle.json").write_text(
            json.dumps(
                {
                    "implementation_state": "COMPLETED",
                    "plan_path": "docs/plans/approved-plan.md",
                    "execution_report_path": "artifacts/work/execution_report.md",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Implement"]["exit_code"] == 0
    assert "shared_fields:" in captured["prompt"]
    assert captured["prompt"].count("name: plan_path") == 1
    assert "execution_report_path" in captured["prompt"]


def test_provider_asset_file_reads_prompt_relative_to_workflow_source(tmp_path: Path):
    """Provider asset_file resolves from the workflow file's source tree."""
    workflow_dir = tmp_path / "workflows" / "library"
    (workflow_dir / "prompts").mkdir(parents=True)
    (workflow_dir / "prompts" / "review.md").write_text("Review from library asset.\n")

    workflow = {
        "version": "2.5",
        "name": "asset-file-prompt",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "asset_file": "prompts/review.md",
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(workflow_dir, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(str(workflow_file.relative_to(tmp_path)))
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert captured["prompt"].startswith("Review from library asset.\n")


def test_provider_asset_depends_on_injects_source_assets_in_declared_order(tmp_path: Path):
    """asset_depends_on injects workflow-source-relative files before the base prompt."""
    workflow_dir = tmp_path / "workflows" / "library"
    (workflow_dir / "prompts").mkdir(parents=True)
    (workflow_dir / "rubrics").mkdir(parents=True)
    (workflow_dir / "schemas").mkdir(parents=True)
    (workflow_dir / "prompts" / "review.md").write_text("Base prompt.\n")
    (workflow_dir / "rubrics" / "review.md").write_text("Rubric body.\n")
    (workflow_dir / "schemas" / "review.json").write_text('{"type":"object"}\n')

    workflow = {
        "version": "2.5",
        "name": "asset-depends-on-prompt",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "asset_file": "prompts/review.md",
            "asset_depends_on": [
                "rubrics/review.md",
                "schemas/review.json",
            ],
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(workflow_dir, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(str(workflow_file.relative_to(tmp_path)))
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert "=== File: rubrics/review.md ===" in captured["prompt"]
    assert "Rubric body.\n" in captured["prompt"]
    assert "=== File: schemas/review.json ===" in captured["prompt"]
    assert captured["prompt"].index("rubrics/review.md") < captured["prompt"].index("schemas/review.json")
    assert "## Output Contract" in captured["prompt"]
    assert captured["prompt"].index("Base prompt.") < captured["prompt"].index("## Output Contract")


def test_provider_asset_depends_on_and_depends_on_inject_compose_in_contract_order(tmp_path: Path):
    """Workspace dependency injection wraps the asset-expanded prompt, not the base prompt."""
    workflow_dir = tmp_path / "workflows" / "library"
    (workflow_dir / "prompts").mkdir(parents=True)
    (workflow_dir / "rubrics").mkdir(parents=True)
    (tmp_path / "state").mkdir(parents=True)
    (workflow_dir / "prompts" / "review.md").write_text("Base prompt.\n")
    (workflow_dir / "rubrics" / "review.md").write_text("Rubric body.\n")
    (tmp_path / "state" / "runtime-manifest.txt").write_text("runtime data\n")

    workflow = {
        "version": "2.7",
        "name": "mixed-injection-order",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "asset_file": "prompts/review.md",
            "asset_depends_on": ["rubrics/review.md"],
            "depends_on": {
                "required": ["state/runtime-manifest.txt"],
                "inject": True,
            },
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(workflow_dir, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(str(workflow_file.relative_to(tmp_path)))
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "state" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()

    dependency_header = "The following required files are available:"
    dependency_path = "  - state/runtime-manifest.txt"
    asset_header = "=== File: rubrics/review.md ==="
    base_prompt = "Base prompt."
    output_contract = "## Output Contract"

    assert state["steps"]["Review"]["exit_code"] == 0
    assert dependency_header in captured["prompt"]
    assert dependency_path in captured["prompt"]
    assert asset_header in captured["prompt"]
    assert base_prompt in captured["prompt"]
    assert output_contract in captured["prompt"]
    assert captured["prompt"].index(dependency_header) < captured["prompt"].index(asset_header)
    assert captured["prompt"].index(asset_header) < captured["prompt"].index(base_prompt)
    assert captured["prompt"].index(base_prompt) < captured["prompt"].index(output_contract)


def test_provider_session_resume_excludes_reserved_session_consume_from_prompt(tmp_path: Path):
    """Resume session handles stay out of prompt injection even when inject_consumes is left on."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "fix.md").write_text("Continue the existing session.\n")

    workflow = {
        "version": "2.10",
        "name": "prompt-contract-session-consume",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
                "session_support": {
                    "metadata_mode": "codex_exec_jsonl_stdout",
                    "fresh_command": ["mock", "--json"],
                    "resume_command": ["mock", "resume", "${SESSION_ID}", "--json"],
                },
            }
        },
        "artifacts": {
            "implementation_session_id": {
                "kind": "scalar",
                "type": "string",
            },
            "review_feedback": {
                "kind": "scalar",
                "type": "string",
            },
        },
        "steps": [
            {
                "name": "PublishSession",
                "set_scalar": {
                    "artifact": "implementation_session_id",
                    "value": "sess-123",
                },
                "publishes": [{"artifact": "implementation_session_id", "from": "implementation_session_id"}],
            },
            {
                "name": "PublishFeedback",
                "set_scalar": {
                    "artifact": "review_feedback",
                    "value": "Address the latest comments.",
                },
                "publishes": [{"artifact": "review_feedback", "from": "review_feedback"}],
            },
            {
                "name": "ResumeImplementation",
                "provider": "mock_provider",
                "input_file": "prompts/fix.md",
                "consumes": [
                    {
                        "artifact": "implementation_session_id",
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                    {
                        "artifact": "review_feedback",
                        "policy": "latest_successful",
                    },
                ],
                "provider_session": {
                    "mode": "resume",
                    "session_id_from": "implementation_session_id",
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ResumeImplementation"]["exit_code"] == 0
    assert "review_feedback" in captured["prompt"]
    assert "Address the latest comments." in captured["prompt"]
    assert "implementation_session_id" not in captured["prompt"]
    assert "sess-123" not in captured["prompt"]


def test_output_contract_block_includes_guidance_fields(tmp_path: Path):
    """Output contract prompt suffix includes optional guidance annotations."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review this patch.\n")

    workflow = {
        "version": "1.1.1",
        "name": "prompt-contract-guidance",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
                "description": "Final review decision token.",
                "format_hint": "Uppercase single token.",
                "example": "APPROVE",
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert "description: Final review decision token." in captured["prompt"]
    assert "format_hint: Uppercase single token." in captured["prompt"]
    assert "example: APPROVE" in captured["prompt"]


def test_inject_output_contract_false_disables_prompt_suffix(tmp_path: Path):
    """Provider steps can disable output contract prompt suffix with inject_output_contract: false."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review this patch.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.1.1",
        "name": "prompt-contract-opt-out",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "inject_output_contract": False,
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert captured["prompt"] == original_prompt
    assert "Output Contract" not in captured["prompt"]


def test_command_steps_ignore_inject_output_contract(tmp_path: Path):
    """inject_output_contract has no effect on command steps."""
    workflow = {
        "version": "1.1.1",
        "name": "command-ignore-inject-flag",
        "steps": [{
            "name": "DraftPlan",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state docs/plans && "
                "printf 'docs/plans/plan-a.md\\n' > state/plan_pointer.txt && "
                "printf '# plan\\n' > docs/plans/plan-a.md",
            ],
            "inject_output_contract": False,
            "expected_outputs": [{
                "name": "plan_path",
                "path": "state/plan_pointer.txt",
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["steps"]["DraftPlan"]["exit_code"] == 0
    assert state["steps"]["DraftPlan"]["artifacts"] == {"plan_path": "docs/plans/plan-a.md"}


def test_provider_consumes_appends_consumed_artifacts_block_by_default(tmp_path: Path):
    """Provider steps inject consumed artifacts block by default for v1.2 consumes."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "consumes-injection-default",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    expected_prefix = (
        "## Consumed Artifacts\n"
        "- execution_log: artifacts/work/execute.log\n"
        "Use these consumed artifacts as context for your work.\n"
    )
    assert captured["prompt"].startswith(expected_prefix)
    assert original_prompt in captured["prompt"]


def test_provider_consumes_injection_still_works_in_v1_4(tmp_path: Path):
    """v1.4 keeps consumed-artifact prompt injection behavior."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.4",
        "name": "consumes-injection-default-v14",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    expected_prefix = (
        "## Consumed Artifacts\n"
        "- execution_log: artifacts/work/execute.log\n"
        "Use these consumed artifacts as context for your work.\n"
    )
    assert captured["prompt"].startswith(expected_prefix)
    assert original_prompt in captured["prompt"]


def test_inject_consumes_false_disables_consumes_block(tmp_path: Path):
    """inject_consumes:false keeps provider prompt unchanged."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "consumes-injection-opt-out",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
                "inject_consumes": False,
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert captured["prompt"] == original_prompt


def test_consumes_injection_position_append_places_block_after_prompt(tmp_path: Path):
    """consumes_injection_position:append adds block after prompt body."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "consumes-injection-append",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
                "consumes_injection_position": "append",
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    expected_suffix = (
        "## Consumed Artifacts\n"
        "- execution_log: artifacts/work/execute.log\n"
        "Use these consumed artifacts as context for your work.\n"
    )
    assert captured["prompt"].startswith(original_prompt)
    assert captured["prompt"].endswith(expected_suffix)


def test_prompt_consumes_injects_only_selected_artifacts(tmp_path: Path):
    """prompt_consumes limits injected consumed-artifact lines to the selected subset."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "prompt-consumes-subset",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            "check_log": {
                "pointer": "state/check_log_path.txt",
                "type": "relpath",
                "under": "artifacts/checks",
                "must_exist_target": True,
            },
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work artifacts/checks && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'artifacts/checks/checks.log\\n' > state/check_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log && "
                        "printf 'checks\\n' > artifacts/checks/checks.log"
                    ),
                ],
                "expected_outputs": [
                    {
                        "name": "execution_log_path",
                        "path": "state/execution_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "check_log_path",
                        "path": "state/check_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/checks",
                        "must_exist_target": True,
                    },
                ],
                "publishes": [
                    {"artifact": "execution_log", "from": "execution_log_path"},
                    {"artifact": "check_log", "from": "check_log_path"},
                ],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                    {
                        "artifact": "check_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                ],
                "prompt_consumes": ["execution_log"],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert "- execution_log: artifacts/work/execute.log" in captured["prompt"]
    assert "- check_log: artifacts/checks/checks.log" not in captured["prompt"]


def test_prompt_consumes_includes_guidance_fields_for_selected_artifacts(tmp_path: Path):
    """Consumes injection includes optional guidance annotations for selected artifacts."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "prompt-consumes-guidance",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            "check_log": {
                "pointer": "state/check_log_path.txt",
                "type": "relpath",
                "under": "artifacts/checks",
                "must_exist_target": True,
            },
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work artifacts/checks && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'artifacts/checks/checks.log\\n' > state/check_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log && "
                        "printf 'checks\\n' > artifacts/checks/checks.log"
                    ),
                ],
                "expected_outputs": [
                    {
                        "name": "execution_log_path",
                        "path": "state/execution_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "check_log_path",
                        "path": "state/check_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/checks",
                        "must_exist_target": True,
                    },
                ],
                "publishes": [
                    {"artifact": "execution_log", "from": "execution_log_path"},
                    {"artifact": "check_log", "from": "check_log_path"},
                ],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                        "description": "Primary execution log for implementation work.",
                        "format_hint": "Workspace-relative .log path.",
                        "example": "artifacts/work/latest-execution.log",
                    },
                    {
                        "artifact": "check_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                        "description": "Targeted checks log.",
                    },
                ],
                "prompt_consumes": ["execution_log"],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert "- execution_log: artifacts/work/execute.log" in captured["prompt"]
    assert "description: Primary execution log for implementation work." in captured["prompt"]
    assert "format_hint: Workspace-relative .log path." in captured["prompt"]
    assert "example: artifacts/work/latest-execution.log" in captured["prompt"]
    assert "description: Targeted checks log." not in captured["prompt"]


def test_missing_prompt_consumes_injects_all_consumed_artifacts(tmp_path: Path):
    """Without prompt_consumes, consumes injection remains backward compatible (all artifacts)."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "prompt-consumes-back-compat",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            "check_log": {
                "pointer": "state/check_log_path.txt",
                "type": "relpath",
                "under": "artifacts/checks",
                "must_exist_target": True,
            },
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work artifacts/checks && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'artifacts/checks/checks.log\\n' > state/check_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log && "
                        "printf 'checks\\n' > artifacts/checks/checks.log"
                    ),
                ],
                "expected_outputs": [
                    {
                        "name": "execution_log_path",
                        "path": "state/execution_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "check_log_path",
                        "path": "state/check_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/checks",
                        "must_exist_target": True,
                    },
                ],
                "publishes": [
                    {"artifact": "execution_log", "from": "execution_log_path"},
                    {"artifact": "check_log", "from": "check_log_path"},
                ],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                    {
                        "artifact": "check_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                ],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert "- execution_log: artifacts/work/execute.log" in captured["prompt"]
    assert "- check_log: artifacts/checks/checks.log" in captured["prompt"]


def test_prompt_consumes_empty_list_injects_no_consumed_artifacts_block(tmp_path: Path):
    """prompt_consumes: [] suppresses consumes prompt injection."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "prompt-consumes-empty",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
                "prompt_consumes": [],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert captured["prompt"] == original_prompt


def test_consume_prompt_modes_render_mixed_content_reference_and_none(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "baseline.md").write_text("baseline body\n", encoding="utf-8")

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "baseline_design",
                    "prompt": {
                        "mode": "reference",
                        "label": "Baseline design",
                        "role": "compatibility_baseline",
                        "description": "Accepted baseline contract.",
                    },
                },
                {
                    "artifact": "execution_log",
                    "prompt": {
                        "mode": "content",
                    },
                },
                {
                    "artifact": "private_notes",
                    "prompt": {
                        "mode": "none",
                    },
                },
            ],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "baseline_design": "docs/baseline.md",
                "execution_log": "artifacts/work/execute.log",
                "private_notes": "state/private_notes.txt",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "## Consumed Artifacts" in prompt
    assert "- execution_log: artifacts/work/execute.log" in prompt
    assert "- baseline_design:" in prompt
    assert "mode: reference" in prompt
    assert "label: Baseline design" in prompt
    assert "role: compatibility_baseline" in prompt
    assert "resolved_value: docs/baseline.md" in prompt
    assert "private_notes" not in prompt
    assert "Use embedded content as context and open referenced artifacts only when needed." in prompt


def test_consume_prompt_nested_guidance_overrides_legacy_row_fields(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "execution_log",
                    "description": "legacy description",
                    "format_hint": "legacy hint",
                    "example": "legacy-example.log",
                    "prompt": {
                        "mode": "reference",
                        "description": "nested description",
                        "format_hint": "nested hint",
                        "example": "nested-example.log",
                    },
                },
            ],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "execution_log": "artifacts/work/execute.log",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "description: nested description" in prompt
    assert "format_hint: nested hint" in prompt
    assert "example: nested-example.log" in prompt
    assert "legacy description" not in prompt
    assert "legacy hint" not in prompt
    assert "legacy-example.log" not in prompt


def test_reference_mode_omits_existing_target_file_body(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "baseline.md").write_text("sensitive baseline body\n", encoding="utf-8")

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "baseline_design",
                    "prompt": {
                        "mode": "reference",
                    },
                },
            ],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "baseline_design": "docs/baseline.md",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "resolved_value: docs/baseline.md" in prompt
    assert "sensitive baseline body" not in prompt
    assert "These references preserve artifact lineage; open them only when needed." in prompt


def test_content_only_consume_prompt_uses_content_footer(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "execution_log",
                },
            ],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "execution_log": "artifacts/work/execute.log",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "- execution_log: artifacts/work/execute.log" in prompt
    assert "Use these consumed artifacts as context for your work." in prompt


def test_prompt_consumes_filter_applies_before_row_modes(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "baseline_design",
                    "prompt": {
                        "mode": "reference",
                    },
                },
                {
                    "artifact": "execution_log",
                    "prompt": {
                        "mode": "content",
                    },
                },
            ],
            "prompt_consumes": ["execution_log"],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "baseline_design": "docs/baseline.md",
                "execution_log": "artifacts/work/execute.log",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "- execution_log: artifacts/work/execute.log" in prompt
    assert "baseline_design" not in prompt
    assert "Use these consumed artifacts as context for your work." in prompt


def test_provider_execute_falls_back_when_stream_output_kwarg_unsupported(tmp_path: Path):
    """Workflow executor should support custom execute(invocation) call shape without kwargs."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review implementation.\n")

    workflow = {
        "version": "1.1.1",
        "name": "provider-exec-compat",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    def _prepare_invocation(*args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt="Review implementation.\n"), None

    def _execute_without_kwargs(_invocation):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute_without_kwargs

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0


def test_provider_prompt_injection_renders_scalar_consumed_value(tmp_path: Path):
    """Scalar consumed artifacts render their values in provider prompt injection."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review check outcomes.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "consumes-scalar-prompt-render",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "failed_count": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": [
            {
                "name": "RunChecks",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf '3\\n' > state/failed_count.txt",
                ],
                "expected_outputs": [{
                    "name": "failed_count",
                    "path": "state/failed_count.txt",
                    "type": "integer",
                }],
                "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "failed_count",
                    "producers": ["RunChecks"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert "- failed_count: 3" in captured["prompt"]


def test_v2_nested_provider_prompt_consumes_uses_iteration_scoped_consume_identity(tmp_path: Path):
    """Looped provider steps inject prompt_consumes from their iteration-qualified consume state."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review check outcomes.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "2.0",
        "name": "nested-provider-prompt-consumes",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "failed_count": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": [
            {
                "name": "SeedCount",
                "id": "seed_count",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": 3,
                },
                "publishes": [{
                    "artifact": "failed_count",
                    "from": "failed_count",
                }],
            },
            {
                "name": "ReviewLoop",
                "id": "review_loop",
                "for_each": {
                    "items": ["one"],
                    "steps": [
                        {
                            "name": "ReviewPlan",
                            "id": "review_plan",
                            "provider": "mock_provider",
                            "input_file": "prompts/review.md",
                            "consumes": [{
                                "artifact": "failed_count",
                                "producers": ["SeedCount"],
                                "policy": "latest_successful",
                                "freshness": "any",
                            }],
                            "prompt_consumes": ["failed_count"],
                        }
                    ],
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewLoop[0].ReviewPlan"]["exit_code"] == 0
    assert "- failed_count: 3" in captured["prompt"]
