"""Source-to-runtime coverage for portable provider-context composition."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.main import main as cli_main
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.workflow_bundle_helpers import bundle_context_dict


class _PostCommitInterruption(BaseException):
    pass


def _settled_codex_stdout() -> bytes:
    return b"\n".join(
        json.dumps(event, sort_keys=True).encode("utf-8")
        for event in (
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "id": "message-1",
                    "text": "captured answer",
                },
            },
            {"type": "turn.completed"},
        )
    )


def test_imported_generic_capture_then_bind_executes_with_the_fake_codex_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "first.md").write_text("seed", encoding="utf-8")
    (tmp_path / "second.md").write_text("ask", encoding="utf-8")
    (tmp_path / "library.orc").write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule library)
  (export keep)
  (defproc keep :forall (T) ((value Contextual[T])) -> Contextual[T]
    :effects () :lowering private-workflow value))
""",
        encoding="utf-8",
    )
    source = tmp_path / "entry.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule entry)
  (import library :only (keep))
  (export chain)
  (defworkflow chain () -> Int
    (let* ((first (provider-result providers.first :prompt prompts.first :inputs ()
                    :capture-context :portable :returns Int))
           (selected (keep first))
           (second (provider-result providers.second :prompt prompts.second :inputs ()
                     :context selected.context :returns Int)))
      second)))
""",
        encoding="utf-8",
    )

    compiled = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={"providers.first": "codex", "providers.second": "codex"},
        prompt_externs={"prompts.first": "first.md", "prompts.second": "second.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = compiled.validated_bundles_by_name["entry::chain"]
    manager = StateManager(workspace=tmp_path, run_id="capture-then-bind")
    input_contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    manager.initialize(
        source.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(input_contracts, {}, tmp_path),
    )
    first, second = (
        step for step in bundle.surface.steps if step.kind.value == "provider"
    )
    invocations: list[dict[str, object]] = []

    def prepare(_self, **kwargs):
        invocations.append(dict(kwargs))
        return SimpleNamespace(input_mode="stdin", env=kwargs["env"]), None

    def execute(_self, invocation, **_kwargs):
        output_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "1" if len(invocations) == 1 else "2",
            encoding="utf-8",
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            raw_stdout=_settled_codex_stdout(),
        )

    original_finalize = StateManager.finalize_step_with_dataflow
    interrupted = False

    def interrupt_after_capture_commit(self, step_name, *args, **kwargs):
        nonlocal interrupted
        original_finalize(self, step_name, *args, **kwargs)
        if step_name == first.name and not interrupted:
            interrupted = True
            raise _PostCommitInterruption

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ), patch.object(
        StateManager,
        "finalize_step_with_dataflow",
        interrupt_after_capture_commit,
    ), pytest.raises(_PostCommitInterruption):
        WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert len(invocations) == 1
    resume_manager = StateManager(workspace=tmp_path, run_id="capture-then-bind")
    committed = resume_manager.load().to_dict()["steps"][first.name]["artifacts"]

    def resume_prepare(_self, **kwargs):
        output_path = kwargs["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        assert first.name not in output_path
        return prepare(_self, **kwargs)

    with patch.object(ProviderExecutor, "prepare_invocation", resume_prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        state = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            retry_delay_ms=0,
        ).execute(resume=True, on_error="stop")

    assert state["status"] == "completed"
    assert len(invocations) == 2
    assert state["steps"][first.name]["artifacts"] == committed
    assert state["steps"][first.name]["artifacts"]["result"] == 1
    captured = state["steps"][first.name]["artifacts"]["context"]
    assert captured["schema"] == "portable-context.v1"
    assert [event["variant"] for event in captured["events"]] == ["TASK", "ASSISTANT"]
    assert state["steps"][second.name]["artifacts"] == {"__result__": 2}
    prompt = invocations[1]["prompt_content"]
    assert isinstance(prompt, str)
    assert "<orchestrator-portable-context>" in prompt
    assert json.dumps(captured, sort_keys=True, separators=(",", ":")) in prompt



def test_captured_contextual_collection_crosses_the_public_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "capture.md").write_text("capture", encoding="utf-8")
    source = tmp_path / "collection.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule collection)
  (export collect)
  (defworkflow collect () -> List[Contextual[Int]]
    (let* ((captured (provider-result providers.capture :prompt prompts.capture :inputs ()
                       :capture-context :portable :returns Int)))
      (list captured))))
""",
        encoding="utf-8",
    )

    compiled = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={"providers.capture": "codex"},
        prompt_externs={"prompts.capture": "capture.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = compiled.validated_bundles_by_name["collection::collect"]
    manager = StateManager(workspace=tmp_path, run_id="captured-collection")
    input_contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    manager.initialize(
        source.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(input_contracts, {}, tmp_path),
    )

    def prepare(_self, **kwargs):
        return SimpleNamespace(input_mode="stdin", env=kwargs["env"]), None

    def execute(_self, invocation, **_kwargs):
        output_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("1", encoding="utf-8")
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            raw_stdout=_settled_codex_stdout(),
        )

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        state = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert state["status"] == "completed"
    provider_step = next(step for step in bundle.surface.steps if step.kind.value == "provider")
    captured = state["steps"][provider_step.name]["artifacts"]
    assert captured["result"] == 1
    assert state["workflow_outputs"] == {
        "__result__": [{"result": 1, "context": captured["context"]}]
    }


@pytest.mark.parametrize("extend_context", [False, True])
def test_two_fresh_provider_branches_bind_the_same_captured_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extend_context: bool,
) -> None:
    for prompt_name in ("seed", "left", "right"):
        (tmp_path / f"{prompt_name}.md").write_text(prompt_name, encoding="utf-8")
    source = tmp_path / "branches.orc"
    source_text = """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule branches)
  (export branch)
  (defrecord Pair (left Int) (right Int))
  (defworkflow branch () -> Pair
    (let* ((seed (provider-result providers.seed :prompt prompts.seed :inputs ()
                    :capture-context :portable :returns Int))
           (left (provider-result providers.left :prompt prompts.left :inputs ()
                    :context seed.context :capture-context :portable :returns Int))
           (right (provider-result providers.right :prompt prompts.right :inputs ()
                     :context seed.context :capture-context :portable :returns Int)))
      (record Pair :left left.result :right right.result))))
"""
    if extend_context:
        extension = """
           (extended
             (record-update seed.context
               :events (list/append seed.context.events
                 (variant ContextEvent TASK
                   :origin (variant ContextOrigin AUTHORED :label "operator-note")
                   :sequence 0 :text "Check the retry deadline as well."))
               :coverage (list/append seed.context.coverage
                 (record ContextCoverage
                   :origin (variant ContextOrigin AUTHORED :label "operator-note")
                   :scope "authored-note" :retained_kinds (list "TASK")
                   :omitted_kinds (list) :conversions (list)))
               :lineage (list/append seed.context.lineage
                 (record ContextTransform
                   :sources (list/map ((row seed.context.coverage)) row.origin)
                   :operation "append-note" :loss (list)))))
"""
        source_text = source_text.replace("           (left (provider-result", extension + "           (left (provider-result")
        source_text = source_text.replace(":context seed.context", ":context extended")
    source.write_text(source_text, encoding="utf-8")

    compiled = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={
            "providers.seed": "codex",
            "providers.left": "codex",
            "providers.right": "codex",
        },
        prompt_externs={
            "prompts.seed": "seed.md",
            "prompts.left": "left.md",
            "prompts.right": "right.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = compiled.validated_bundles_by_name["branches::branch"]
    manager = StateManager(workspace=tmp_path, run_id="context-branches")
    input_contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    manager.initialize(
        source.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(input_contracts, {}, tmp_path),
    )
    invocations: list[dict[str, object]] = []

    def prepare(_self, **kwargs):
        invocations.append(dict(kwargs))
        return SimpleNamespace(input_mode="stdin", env=kwargs["env"]), None

    def execute(_self, invocation, **_kwargs):
        output_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(str(len(invocations)), encoding="utf-8")
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            raw_stdout=_settled_codex_stdout(),
        )

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        state = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert state["status"] == "completed"
    provider_steps = [step for step in bundle.surface.steps if step.kind.value == "provider"]
    seed_context = state["steps"][provider_steps[0].name]["artifacts"]["context"]
    left_context = state["steps"][provider_steps[1].name]["artifacts"]["context"]
    right_context = state["steps"][provider_steps[2].name]["artifacts"]["context"]
    assert len(invocations) == 3
    seed_events = seed_context["events"]
    if extend_context:
        authored_note = {
            "variant": "TASK",
            "origin": {"variant": "AUTHORED", "label": "operator-note"},
            "sequence": 0,
            "text": "Check the retry deadline as well.",
        }
        seed_events = [*seed_events, authored_note]
        for continuation in (left_context, right_context):
            assert continuation["lineage"][0] == {
                "sources": [seed_context["coverage"][0]["origin"]],
                "operation": "append-note",
                "loss": [],
            }
            assert continuation["coverage"][1]["origin"] == authored_note["origin"]
    assert left_context["events"][: len(seed_events)] == seed_events
    assert right_context["events"][: len(seed_events)] == seed_events
    left_continuation = left_context["events"][len(seed_events) :]
    right_continuation = right_context["events"][len(seed_events) :]
    assert left_continuation and right_continuation
    left_origins = {
        json.dumps(event["origin"], sort_keys=True)
        for event in left_continuation
    }
    right_origins = {
        json.dumps(event["origin"], sort_keys=True)
        for event in right_continuation
    }
    assert left_origins.isdisjoint(right_origins)
    assert not left_origins & {
        json.dumps(event["origin"], sort_keys=True)
        for event in right_context["events"][: len(seed_events)]
    }
    assert not right_origins & {
        json.dumps(event["origin"], sort_keys=True)
        for event in left_context["events"][: len(seed_events)]
    }
    assert state["workflow_outputs"] == {"return__left": 2, "return__right": 3}


def test_imported_generic_contextual_value_crosses_a_loop_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "capture.md").write_text("capture", encoding="utf-8")
    (tmp_path / "library.orc").write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule library)
  (export keep)
  (defproc keep :forall (T) ((value Contextual[T])) -> Contextual[T]
    :effects () :lowering private-workflow value))
""",
        encoding="utf-8",
    )
    source = tmp_path / "looped.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule looped)
  (import library :only (keep))
  (export looped)
  (defworkflow looped () -> Contextual[Int]
    (let* ((captured (provider-result providers.capture :prompt prompts.capture :inputs ()
                       :capture-context :portable :returns Int)))
      (loop/recur :max 1 :state captured
        (fn (state)
          (let* ((copied (keep state)))
            (done copied)))))))
""",
        encoding="utf-8",
    )

    compiled = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={"providers.capture": "codex"},
        prompt_externs={"prompts.capture": "capture.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = compiled.validated_bundles_by_name["looped::looped"]
    manager = StateManager(workspace=tmp_path, run_id="looped-contextual")
    input_contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    manager.initialize(
        source.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(input_contracts, {}, tmp_path),
    )
    calls = 0

    def prepare(_self, **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(input_mode="stdin", env=kwargs["env"]), None

    def execute(_self, invocation, **_kwargs):
        output_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("1", encoding="utf-8")
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            raw_stdout=_settled_codex_stdout(),
        )

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        state = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert state["status"] == "completed"
    assert calls == 1


def test_public_cli_compile_run_and_resume_preserve_a_captured_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public command path resumes after committing the capture step."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "first.md").write_text("seed", encoding="utf-8")
    (tmp_path / "second.md").write_text("ask", encoding="utf-8")
    source = tmp_path / "entry.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule entry)
  (export chain)
  (defworkflow chain () -> Int
    (let* ((first (provider-result providers.first :prompt prompts.first :inputs ()
                    :capture-context :portable :returns Int))
           (second (provider-result providers.second :prompt prompts.second :inputs ()
                     :context first.context :returns Int)))
      second)))
""",
        encoding="utf-8",
    )
    providers = tmp_path / "providers.json"
    providers.write_text(
        json.dumps({"providers.first": "codex", "providers.second": "codex"}),
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts.json"
    prompts.write_text(
        json.dumps({"prompts.first": "first.md", "prompts.second": "second.md"}),
        encoding="utf-8",
    )
    frontend_args = [
        source.as_posix(),
        "--entry-workflow",
        "chain",
        "--source-root",
        tmp_path.as_posix(),
        "--provider-externs-file",
        providers.as_posix(),
        "--prompt-externs-file",
        prompts.as_posix(),
    ]
    assert cli_main(["compile", *frontend_args]) == 0

    invocations: list[dict[str, object]] = []

    def prepare(_self, **kwargs):
        invocations.append(dict(kwargs))
        return SimpleNamespace(input_mode="stdin", env=kwargs["env"]), None

    def execute(_self, invocation, **_kwargs):
        output_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("1" if len(invocations) == 1 else "2", encoding="utf-8")
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            raw_stdout=_settled_codex_stdout(),
        )

    original_checkpoint = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit
    interrupted = False

    def interrupt_after_first_capture(self, state, step_name, step, finalized):
        nonlocal interrupted
        original_checkpoint(self, state, step_name, step, finalized)
        if step_name == "entry::chain__first" and not interrupted:
            interrupted = True
            raise _PostCommitInterruption

    run_argv = ["orchestrator", "run", *frontend_args, "--retry-delay", "0"]
    with patch.object(sys, "argv", run_argv), patch.object(
        ProviderExecutor, "prepare_invocation", prepare
    ), patch.object(
        ProviderExecutor, "execute", execute
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_first_capture,
    ), pytest.raises(_PostCommitInterruption):
        cli_main(["run", *frontend_args, "--retry-delay", "0"])

    runs_root = tmp_path / ".orchestrate" / "runs"
    (run_root,) = tuple(runs_root.iterdir())
    first_output_path = invocations[0]["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]

    def resume_prepare(_self, **kwargs):
        assert kwargs["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] != first_output_path
        return prepare(_self, **kwargs)

    with patch.object(ProviderExecutor, "prepare_invocation", resume_prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        assert cli_main(
            [
                "resume",
                run_root.name,
                "--state-dir",
                runs_root.as_posix(),
                "--retry-delay",
                "0",
            ]
        ) == 0

    assert len(invocations) == 2
    state = StateManager(workspace=tmp_path, run_id=run_root.name).load().to_dict()
    assert state["status"] == "completed"


def test_target_231_private_workflow_accepts_an_ordinary_nested_collection_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "ordinary_private.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule ordinary_private)
  (export keep)
  (defunion Choice (ONE (value Int)) (TWO (value Int)))
  (defrecord Packet (items List[Choice]))
  (defproc keep ((value Packet)) -> Packet
    :effects () :lowering private-workflow value))
""",
        encoding="utf-8",
    )

    compiled = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    (procedure,) = compiled.entry_result.typed_procedures
    assert procedure.resolved_lowering_mode.value == "private-workflow"


def test_target_230_private_workflow_keeps_the_legacy_nested_collection_refusal(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ordinary_private_230.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.30\")
  (defmodule ordinary_private_230)
  (export keep)
  (defunion Choice (ONE (value Int)) (TWO (value Int)))
  (defrecord Packet (items List[Choice]))
  (defproc keep ((value Packet)) -> Packet
    :effects () :lowering private-workflow value))
""",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as raised:
        compile_stage3_entrypoint(
            source,
            source_roots=(tmp_path,),
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert raised.value.diagnostics[0].code == "proc_private_workflow_boundary_invalid"


def test_private_contextual_collision_is_refused_without_flattening_ambiguously(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing flattened private frames remain closed when paths collide."""
    (tmp_path / "library.orc").write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule library)
  (export keep)
  (defproc keep :forall (T) ((value Contextual[T])) -> Contextual[T]
    :effects () :lowering private-workflow value))
""",
        encoding="utf-8",
    )
    source = tmp_path / "collision.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule collision)
  (import library :only (keep))
  (export chain)
  (defrecord Nested (b Int))
  (defrecord Collision (a__b Int) (a Nested))
  (defworkflow chain () -> Int
    (let* ((captured (provider-result providers.capture :prompt prompts.capture :inputs ()
                       :capture-context :portable :returns Collision))
           (copied (keep captured))
           (result (provider-result providers.consume :prompt prompts.consume :inputs ()
                    :context copied.context :returns Int)))
      result)))
""",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as raised:
        compile_stage3_entrypoint(
            source,
            source_roots=(tmp_path,),
            provider_externs={"providers.capture": "codex", "providers.consume": "codex"},
            prompt_externs={"prompts.capture": "capture.md", "prompts.consume": "consume.md"},
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert raised.value.diagnostics[0].code == "workflow_boundary_projection_collision"
