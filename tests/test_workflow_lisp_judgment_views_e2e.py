"""Deterministic runtime acceptance for the Q4 judgment-panel consumer."""

from __future__ import annotations

import builtins
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import (
    ProviderExecutionResult,
    ProviderExecutor,
)
from orchestrator.providers.types import (
    InputMode,
    PreparedProviderPolicy,
    ProviderInvocation,
)
from orchestrator.runtime_observability import (
    record_compiled_frontend_provenance,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.judgment_views import project_judgment_views
from orchestrator.workflow.loaded_bundle import (
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.prompt_attempt_result_binding import (
    PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY,
)
from orchestrator.workflow.prompt_dependency_evidence import (
    evidence_relative_path,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows" / "examples"
PANEL = WORKFLOWS / "review_revise_design_docs_judgment_panel.orc"
PANEL_INPUTS = (
    WORKFLOWS
    / "inputs"
    / "review_revise_design_docs_judgment_panel"
)
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "judgment_views"
    / "review_revise_design_docs_judgment_panel_case.json"
)
ENTRY = (
    "review_revise_design_docs_judgment_panel"
    "::review-revise-design-docs-judgment-panel"
)
SYNTHESIS_PROMPT = Path(
    "prompts/workflows/review_revise_design_docs/synthesize.md"
)
REPO_SYNTHESIS_PROMPT = (
    REPO_ROOT
    / "prompts"
    / "workflows"
    / "review_revise_design_docs"
    / "synthesize.md"
)
FIX_PROMPT = "prompts/workflows/review_revise_design_docs/fix.md"
SYNTHESIS_PATH = "artifacts/review/q4-panel/synthesis.md"
_TYPED_INPUT_HEADING = re.compile(
    r"^## Typed Prompt Input: (?P<name>[A-Za-z_][A-Za-z0-9_]*)$",
    re.MULTILINE,
)


def _compile_panel(workspace: Path):
    panel_source = workspace / PANEL.name
    panel_source.parent.mkdir(parents=True, exist_ok=True)
    panel_source.write_bytes(PANEL.read_bytes())
    synthesis_prompt = workspace / SYNTHESIS_PROMPT
    synthesis_prompt.parent.mkdir(parents=True, exist_ok=True)
    synthesis_prompt.write_bytes(REPO_SYNTHESIS_PROMPT.read_bytes())
    providers_path = workspace / "providers.json"
    providers_path.write_bytes(
        (PANEL_INPUTS / "providers.json").read_bytes()
    )
    prompts_path = workspace / "prompts.json"
    prompts_path.write_text(
        json.dumps(
            {
                "prompts.design-docs.fix": FIX_PROMPT,
                "prompts.design-docs.synthesize": {
                    "input_file": SYNTHESIS_PROMPT.as_posix()
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=panel_source,
            source_roots=(workspace, WORKFLOWS),
            entry_workflow=(
                "review-revise-design-docs-judgment-panel"
            ),
            provider_externs_path=providers_path,
            prompt_externs_path=prompts_path,
            workspace_root=workspace,
            lowering_route="wcc_m4",
        )
    )
    assert result.validated_bundle.surface.name == ENTRY
    return result, result.validated_bundle, panel_source


def _fixture_payload() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == (
        "workflow_lisp_judgment_panel_fixture.v1"
    )
    return payload


def _write_required_inputs(
    workspace: Path,
    inputs: dict[str, Any],
) -> None:
    required_files = {
        str(inputs["target_doc"]): "panel target\n",
        str(inputs["checks_report"]): "checks passed\n",
        **{
            str(path): f"context: {path}\n"
            for path in inputs["context_docs"]
        },
    }
    for relpath, content in required_files.items():
        path = workspace / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _typed_prompt_input(prompt: str, name: str) -> Any:
    marker = f"## Typed Prompt Input: {name}\n"
    assert prompt.count(marker) == 1
    rendered = prompt.split(marker, 1)[1].splitlines()[0]
    return json.loads(rendered)


def _typed_path_input(prompt: str, name: str) -> str:
    marker = f"## Typed Prompt Input: {name}\n"
    assert prompt.count(marker) == 1
    return prompt.split(marker, 1)[1].splitlines()[0]


def _typed_prompt_input_names(prompt: str) -> tuple[str, ...]:
    return tuple(
        match.group("name")
        for match in _TYPED_INPUT_HEADING.finditer(prompt)
    )


def _output_bundle_path(
    workspace: Path,
    invocation: ProviderInvocation,
) -> Path:
    path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
    return path if path.is_absolute() else workspace / path


def _deterministic_provider_hooks(
    workspace: Path,
    *,
    lens_ids: list[str],
    events: list[dict[str, Any]],
):
    prepared_prompts: list[str] = []
    provider_files: list[dict[str, str]] = []

    def prepare(
        _self: ProviderExecutor,
        provider_name: str,
        *_args: Any,
        **kwargs: Any,
    ):
        prompt = str(kwargs.get("prompt_content") or "")
        policy = kwargs.get("provider_call_policy") or {}
        prepared_prompts.append(prompt)
        return (
            ProviderInvocation(
                command=["deterministic-panel-provider"],
                input_mode=InputMode.STDIN,
                prompt=prompt,
                env=dict(kwargs.get("env") or {}),
                timeout_sec=kwargs.get("timeout_sec"),
                prepared_prompt=prompt,
                prepared_provider_policy=PreparedProviderPolicy(
                    provider_name=provider_name,
                    model=policy.get("model"),
                    effort=policy.get("effort"),
                    timeout_sec=kwargs.get("timeout_sec"),
                    input_mode="stdin",
                ),
            ),
            None,
        )

    def execute(
        _self: ProviderExecutor,
        invocation: ProviderInvocation,
        **_kwargs: Any,
    ) -> ProviderExecutionResult:
        ordinal = len(events)
        output_path = _output_bundle_path(workspace, invocation)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if ordinal < len(lens_ids):
            lens = lens_ids[ordinal]
            report_path = f"artifacts/review/{lens}"
            findings_path = (
                f"artifacts/work/q4-panel/findings-{ordinal + 1}.json"
            )
            report = workspace / report_path
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                f"review-{ordinal + 1}:{lens}\n",
                encoding="utf-8",
            )
            findings = workspace / findings_path
            findings.parent.mkdir(parents=True, exist_ok=True)
            findings.write_text('{"items":[]}\n', encoding="utf-8")
            variant = ("APPROVE", "REVISE", "BLOCKED")[ordinal % 3]
            payload: dict[str, Any] = {
                "variant": variant,
                "review_report": report_path,
                "findings": {
                    "schema_version": "ReviewFindings.v1",
                    "items_path": findings_path,
                },
            }
            if variant == "BLOCKED":
                payload["blocker_class"] = "user_decision_required"
            event = {
                "kind": "review",
                "lens": lens,
                "report": report_path,
                "typed_input_names": _typed_prompt_input_names(
                    invocation.prompt or ""
                ),
            }
            provider_files.append(
                {
                    "output_bundle": output_path.as_posix(),
                    "report": report.as_posix(),
                    "findings": findings.as_posix(),
                }
            )
        else:
            assert ordinal == len(lens_ids)
            prompt = invocation.prompt or ""
            reports = _typed_prompt_input(prompt, "reports")
            target_doc = _typed_path_input(prompt, "target_doc")
            assert reports == [
                f"artifacts/review/{lens}" for lens in lens_ids
            ]
            synthesis = workspace / SYNTHESIS_PATH
            synthesis.parent.mkdir(parents=True, exist_ok=True)
            synthesis.write_text(
                "\n".join(str(path) for path in reports) + "\n",
                encoding="utf-8",
            )
            payload = SYNTHESIS_PATH
            event = {
                "kind": "synthesis",
                "reports": reports,
                "target_doc": target_doc,
                "typed_input_names": _typed_prompt_input_names(prompt),
            }
            provider_files.append(
                {
                    "output_bundle": output_path.as_posix(),
                    "report": synthesis.as_posix(),
                }
            )

        output_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        events.append(event)
        return ProviderExecutionResult(0, b"", b"", 1)

    return prepare, execute, prepared_prompts, provider_files


def _initialize_panel(
    workspace: Path,
    *,
    lens_ids: list[str],
    run_id: str,
):
    result, bundle, panel_source = _compile_panel(workspace)
    fixture = _fixture_payload()
    inputs = dict(fixture["inputs"])
    inputs["lens_ids"] = list(lens_ids)
    _write_required_inputs(workspace, inputs)
    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(contracts, inputs, workspace)
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        panel_source.name,
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return result, bundle, manager


def _run_panel(
    workspace: Path,
    *,
    lens_ids: list[str],
    run_id: str,
):
    result, bundle, manager = _initialize_panel(
        workspace,
        lens_ids=lens_ids,
        run_id=run_id,
    )
    events: list[dict[str, Any]] = []
    (
        prepare,
        execute,
        prepared_prompts,
        _,
    ) = _deterministic_provider_hooks(
        workspace,
        lens_ids=lens_ids,
        events=events,
    )
    with (
        patch.object(ProviderExecutor, "prepare_invocation", prepare),
        patch.object(ProviderExecutor, "execute", execute),
    ):
        state = WorkflowExecutor(
            bundle,
            workspace,
            manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(on_error="stop")
    return result, bundle, manager, state, events, prepared_prompts


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _provider_attempt_identity_bytes(
    state: dict[str, Any],
    manager: StateManager,
) -> tuple[bytes, ...]:
    rows: list[bytes] = []
    allocations = state["provider_attempt_allocations"]
    for locator in _result_locators(state):
        allocation = allocations[locator["scope_sha256"]]
        scope = ProviderAttemptScope.from_dict(allocation["scope"])
        ordinal = locator["attempt_ordinal"]
        relative_path = evidence_relative_path(scope, ordinal)
        assert scope.key == locator["scope_sha256"]
        assert ordinal <= allocation["last_allocated_ordinal"]
        assert locator["evidence_relative_path"] == (
            relative_path.as_posix()
        )
        payload = (manager.run_root / relative_path).read_bytes()
        assert locator["evidence_file_sha256"] == (
            "sha256:" + hashlib.sha256(payload).hexdigest()
        )
        assert locator["record_kind"] == "prompt_snapshot"
        record = json.loads(payload)
        rows.append(
            _canonical_bytes(
                {
                    "scope": allocation["scope"],
                    "attempt_ordinal": ordinal,
                    "prompt_attempt_identity": record[
                        "prompt_attempt_identity"
                    ],
                }
            )
        )
    return tuple(sorted(rows))


def _result_locator_bytes(
    state: dict[str, Any],
) -> tuple[bytes, ...]:
    return tuple(
        sorted(
            _canonical_bytes(binding)
            for binding in _result_locators(state)
        )
    )


def _result_locators(
    state: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for frame in state["call_frames"].values():
        for result in frame["state"]["steps"].values():
            debug = result.get("debug", {})
            if PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY in debug:
                rows.append(
                    dict(
                        debug[
                            PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY
                        ]
                    )
                )
    return tuple(
        sorted(rows, key=lambda row: row["scope_sha256"])
    )


def _panel_artifact_bytes(
    workspace: Path,
    state: dict[str, Any],
) -> dict[str, bytes]:
    paths = [
        *state["workflow_outputs"]["return__reports"],
        state["workflow_outputs"]["return__synthesis"],
    ]
    return {
        str(path): (workspace / str(path)).read_bytes()
        for path in paths
    }


@contextmanager
def _guard_committed_child_file_reads(
    paths: set[Path],
    *,
    evidence_path: Path,
):
    protected = {
        path.resolve(strict=False)
        for path in paths
    }
    evidence_enumeration_roots: set[Path] = set()
    parent = evidence_path.parent.resolve(strict=False)
    while True:
        evidence_enumeration_roots.add(parent)
        if parent.name == "prompt_dependencies":
            break
        if parent.parent == parent:
            raise AssertionError(
                "evidence path is outside prompt_dependencies"
            )
        parent = parent.parent

    attempted: list[str] = []

    def absolute(value: Any) -> Path | None:
        if not isinstance(value, (str, bytes, os.PathLike)):
            return None
        return Path(os.fsdecode(value)).resolve(strict=False)

    def reject_read(value: Any) -> None:
        candidate = absolute(value)
        if candidate in protected:
            attempted.append(candidate.as_posix())
            raise AssertionError(
                f"committed child file read: {candidate}"
            )

    def reject_enumeration(value: Any) -> None:
        candidate = absolute(value)
        if candidate in evidence_enumeration_roots:
            attempted.append(candidate.as_posix())
            raise AssertionError(
                f"committed child evidence enumeration: {candidate}"
            )

    original_path_open = Path.open
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    original_iterdir = Path.iterdir
    original_glob = Path.glob
    original_rglob = Path.rglob
    original_builtin_open = builtins.open
    original_os_open = os.open
    original_listdir = os.listdir
    original_scandir = os.scandir

    def path_open(path: Path, *args: Any, **kwargs: Any):
        mode = args[0] if args else kwargs.get("mode", "r")
        if "r" in mode or "+" in mode:
            reject_read(path)
        return original_path_open(path, *args, **kwargs)

    def read_bytes(path: Path) -> bytes:
        reject_read(path)
        return original_read_bytes(path)

    def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        reject_read(path)
        return original_read_text(path, *args, **kwargs)

    def iterdir(path: Path):
        reject_enumeration(path)
        return original_iterdir(path)

    def glob(path: Path, *args: Any, **kwargs: Any):
        reject_enumeration(path)
        return original_glob(path, *args, **kwargs)

    def rglob(path: Path, *args: Any, **kwargs: Any):
        reject_enumeration(path)
        return original_rglob(path, *args, **kwargs)

    def builtin_open(file: Any, *args: Any, **kwargs: Any):
        mode = args[0] if args else kwargs.get("mode", "r")
        if "r" in mode or "+" in mode:
            reject_read(file)
        return original_builtin_open(file, *args, **kwargs)

    def os_open(path: Any, flags: int, *args: Any, **kwargs: Any):
        if flags & os.O_ACCMODE != os.O_WRONLY:
            reject_read(path)
        return original_os_open(path, flags, *args, **kwargs)

    def listdir(path: Any = "."):
        reject_enumeration(path)
        return original_listdir(path)

    def scandir(path: Any = "."):
        reject_enumeration(path)
        return original_scandir(path)

    with ExitStack() as stack:
        stack.enter_context(patch.object(Path, "open", path_open))
        stack.enter_context(
            patch.object(Path, "read_bytes", read_bytes)
        )
        stack.enter_context(
            patch.object(Path, "read_text", read_text)
        )
        stack.enter_context(patch.object(Path, "iterdir", iterdir))
        stack.enter_context(patch.object(Path, "glob", glob))
        stack.enter_context(patch.object(Path, "rglob", rglob))
        stack.enter_context(
            patch.object(builtins, "open", builtin_open)
        )
        stack.enter_context(patch.object(os, "open", os_open))
        stack.enter_context(patch.object(os, "listdir", listdir))
        stack.enter_context(patch.object(os, "scandir", scandir))
        yield attempted


def test_panel_executes_ordered_reviews_then_one_ineligible_synthesis(
    tmp_path: Path,
) -> None:
    fixture = _fixture_payload()
    lens_ids = list(fixture["inputs"]["lens_ids"])
    _, bundle, manager, state, events, prepared_prompts = _run_panel(
        tmp_path,
        lens_ids=lens_ids,
        run_id="q4-panel-clean",
    )
    reports = [f"artifacts/review/{lens}" for lens in lens_ids]

    assert state["status"] == "completed", state.get("error")
    assert state["workflow_outputs"] == {
        "return__reports": reports,
        "return__synthesis": SYNTHESIS_PATH,
    }
    assert [event["kind"] for event in events] == [
        "review",
        "review",
        "review",
        "synthesis",
    ]
    assert [event["report"] for event in events[:3]] == reports
    assert events[3] == {
        "kind": "synthesis",
        "reports": reports,
        "target_doc": fixture["inputs"]["target_doc"],
        "typed_input_names": ("target_doc", "reports"),
    }
    assert len(prepared_prompts) == 4
    review_results = [
        frame["state"]["steps"][
            "review_revise_design_docs_judgment_panel::review-one__decision"
        ]
        for frame in state["call_frames"].values()
    ]
    assert len(review_results) == 3
    assert all(
        PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY
        in result["debug"]
        for result in review_results
    )
    synthesis_result = state["steps"][f"{ENTRY}__synthesis"]
    assert (
        PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY
        not in synthesis_result.get("debug", {})
    )

    record_compiled_frontend_provenance(state, bundle.provenance)
    projection = project_judgment_views(
        state,
        manager.run_root,
        workspace_root=tmp_path,
    )
    assert len(projection["judgments"]) == 3
    assert all(
        judgment["status"] == "available"
        for judgment in projection["judgments"]
    )
    assert len(projection["matrices"]) == 1
    assert len(projection["matrices"][0]["members"]) == 3
    assert len(projection["iteration_series"]) == 3
    assert all(
        judgment.get("result", {}).get("value") != SYNTHESIS_PATH
        for judgment in projection["judgments"]
    )


@pytest.mark.parametrize(
    ("lens", "diagnostic"),
    (
        ("", "path_join_under_child_invalid"),
        ("../escape.md", "path_join_under_escape"),
    ),
)
def test_panel_rejects_unsafe_lens_before_provider_launch(
    tmp_path: Path,
    lens: str,
    diagnostic: str,
) -> None:
    _, _, _, state, events, prepared_prompts = _run_panel(
        tmp_path,
        lens_ids=[lens],
        run_id=f"q4-panel-unsafe-{diagnostic}",
    )

    assert state["status"] == "failed"
    assert diagnostic in json.dumps(state, sort_keys=True)
    assert events == []
    assert prepared_prompts == []


def test_panel_duplicate_hits_write_root_guard_without_uniqueness_claim(
    tmp_path: Path,
) -> None:
    duplicate = "q4-panel/duplicate.md"
    _, _, _, state, events, prepared_prompts = _run_panel(
        tmp_path,
        lens_ids=[duplicate, duplicate],
        run_id="q4-panel-duplicate-destination",
    )
    duplicate_report = f"artifacts/review/{duplicate}"

    assert state["status"] == "failed"
    assert "colliding_write_root_binding" in json.dumps(
        state,
        sort_keys=True,
    )
    assert state["workflow_outputs"] == {}
    assert events == [
        {
            "kind": "review",
            "lens": duplicate,
            "report": duplicate_report,
            "typed_input_names": (),
        }
    ]
    assert len(prepared_prompts) == 1
    assert (tmp_path / duplicate_report).read_text(
        encoding="utf-8"
    ) == f"review-1:{duplicate}\n"


def test_panel_committed_child_resume_matches_clean_exact_authorities(
    tmp_path: Path,
) -> None:
    lens_ids = list(_fixture_payload()["inputs"]["lens_ids"])
    clean_root = tmp_path / "clean"
    interrupted_root = tmp_path / "interrupted"
    run_id = "q4-panel-deterministic-parity"
    (
        _,
        clean_bundle,
        clean_manager,
        clean_state,
        clean_events,
        _,
    ) = _run_panel(
        clean_root,
        lens_ids=lens_ids,
        run_id=run_id,
    )
    (
        _,
        interrupted_bundle,
        interrupted_manager,
    ) = _initialize_panel(
        interrupted_root,
        lens_ids=lens_ids,
        run_id=run_id,
    )
    resumed_events: list[dict[str, Any]] = []
    (
        prepare,
        execute,
        prepared_prompts,
        provider_files,
    ) = _deterministic_provider_hooks(
        interrupted_root,
        lens_ids=lens_ids,
        events=resumed_events,
    )
    original_nested = WorkflowExecutor._execute_nested_loop_step
    interrupted = {"done": False}

    class _InjectedPostChildCommitInterruption(BaseException):
        pass

    def interrupt_after_committed_child(
        current_executor: WorkflowExecutor,
        step: dict[str, Any],
        context: dict[str, Any],
        state: dict[str, Any],
        iteration_state: dict[str, Any],
        parent_scope_steps: dict[str, Any],
        **kwargs: Any,
    ):
        result = original_nested(
            current_executor,
            step,
            context,
            state,
            iteration_state,
            parent_scope_steps,
            **kwargs,
        )
        if (
            not interrupted["done"]
            and isinstance(step.get("call"), str)
            and result.get("status") == "completed"
            and kwargs.get("iteration_index") == 0
        ):
            interrupted["done"] = True
            raise _InjectedPostChildCommitInterruption
        return result

    with (
        patch.object(ProviderExecutor, "prepare_invocation", prepare),
        patch.object(ProviderExecutor, "execute", execute),
        patch.object(
            WorkflowExecutor,
            "_execute_nested_loop_step",
            interrupt_after_committed_child,
        ),
    ):
        with pytest.raises(_InjectedPostChildCommitInterruption):
            WorkflowExecutor(
                interrupted_bundle,
                interrupted_root,
                interrupted_manager,
                max_retries=0,
                retry_delay_ms=0,
            ).execute(on_error="stop")

    interrupted_state = interrupted_manager.load().to_dict()
    assert interrupted_state["status"] == "running"
    assert [event["lens"] for event in resumed_events] == [lens_ids[0]]
    assert len(provider_files) == 1
    committed_locators = _result_locators(interrupted_state)
    assert len(committed_locators) == 1
    committed_evidence = (
        interrupted_manager.run_root
        / committed_locators[0]["evidence_relative_path"]
    )
    protected_child_files = {
        *(Path(path) for path in provider_files[0].values()),
        committed_evidence,
    }

    resume_manager = StateManager(
        interrupted_root,
        run_id=run_id,
    )
    resume_manager.load()
    with (
        _guard_committed_child_file_reads(
            protected_child_files,
            evidence_path=committed_evidence,
        ) as guarded_read_attempts,
        patch.object(ProviderExecutor, "prepare_invocation", prepare),
        patch.object(ProviderExecutor, "execute", execute),
    ):
        resumed_state = WorkflowExecutor(
            interrupted_bundle,
            interrupted_root,
            resume_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(resume=True, on_error="stop")

    assert guarded_read_attempts == []
    assert resumed_state["status"] == "completed", resumed_state.get(
        "error"
    )
    assert resumed_events == clean_events
    assert len(prepared_prompts) == 4
    assert (
        sum(
            event.get("lens") == lens_ids[0]
            for event in resumed_events
        )
        == 1
    )
    assert (
        sum(event["kind"] == "synthesis" for event in resumed_events)
        == 1
    )
    record_compiled_frontend_provenance(
        clean_state,
        clean_bundle.provenance,
    )
    record_compiled_frontend_provenance(
        resumed_state,
        interrupted_bundle.provenance,
    )

    assert resumed_state["workflow_outputs"] == clean_state[
        "workflow_outputs"
    ]
    assert _panel_artifact_bytes(
        interrupted_root,
        resumed_state,
    ) == _panel_artifact_bytes(clean_root, clean_state)
    assert _provider_attempt_identity_bytes(
        resumed_state,
        resume_manager,
    ) == _provider_attempt_identity_bytes(
        clean_state,
        clean_manager,
    )
    assert _result_locator_bytes(
        resumed_state
    ) == _result_locator_bytes(clean_state)
    assert len(_result_locator_bytes(resumed_state)) == 3
    assert (
        resumed_state["provider_attempt_allocations"]
        == clean_state["provider_attempt_allocations"]
    )
    assert project_judgment_views(
        clean_state,
        clean_manager.run_root,
        workspace_root=clean_root,
    ) == project_judgment_views(
        resumed_state,
        resume_manager.run_root,
        workspace_root=interrupted_root,
    )
    default_resume = json.loads(
        resume_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )
    assert default_resume["selection_reason"] == (
        "validated_prior_boundary"
    )


def test_panel_missing_bound_evidence_changes_only_affected_view(
    tmp_path: Path,
) -> None:
    lens_ids = list(_fixture_payload()["inputs"]["lens_ids"])
    (
        _,
        bundle,
        manager,
        completed_state,
        _,
        _,
    ) = _run_panel(
        tmp_path,
        lens_ids=lens_ids,
        run_id="q4-panel-evidence-loss",
    )
    record_compiled_frontend_provenance(
        completed_state,
        bundle.provenance,
    )
    before = project_judgment_views(
        completed_state,
        manager.run_root,
        workspace_root=tmp_path,
    )
    completed_outputs = _canonical_bytes(
        completed_state["workflow_outputs"]
    )
    completed_artifacts = _panel_artifact_bytes(
        tmp_path,
        completed_state,
    )
    locators = _result_locators(completed_state)
    assert len(locators) == 3
    removed_locator = locators[0]
    removed_allocation = completed_state[
        "provider_attempt_allocations"
    ][removed_locator["scope_sha256"]]
    removed_scope = removed_allocation["scope"]
    evidence_path = (
        manager.run_root
        / removed_locator["evidence_relative_path"]
    )
    evidence_path.unlink()

    provider_calls: list[str] = []

    def prepare_synthesis_only(
        _self: ProviderExecutor,
        provider_name: str,
        *_args: Any,
        **kwargs: Any,
    ):
        prompt = str(kwargs.get("prompt_content") or "")
        assert _typed_prompt_input_names(prompt) == (
            "target_doc",
            "reports",
        )
        policy = kwargs.get("provider_call_policy") or {}
        provider_calls.append("prepare:synthesis")
        return (
            ProviderInvocation(
                command=["deterministic-panel-provider"],
                input_mode=InputMode.STDIN,
                prompt=prompt,
                env=dict(kwargs.get("env") or {}),
                timeout_sec=kwargs.get("timeout_sec"),
                prepared_prompt=prompt,
                prepared_provider_policy=PreparedProviderPolicy(
                    provider_name=provider_name,
                    model=policy.get("model"),
                    effort=policy.get("effort"),
                    timeout_sec=kwargs.get("timeout_sec"),
                    input_mode="stdin",
                ),
            ),
            None,
        )

    def execute_synthesis_only(
        _self: ProviderExecutor,
        invocation: ProviderInvocation,
        **_kwargs: Any,
    ) -> ProviderExecutionResult:
        assert _typed_prompt_input_names(
            invocation.prompt or ""
        ) == ("target_doc", "reports")
        provider_calls.append("execute:synthesis")
        output = _output_bundle_path(tmp_path, invocation)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(SYNTHESIS_PATH) + "\n",
            encoding="utf-8",
        )
        return ProviderExecutionResult(0, b"", b"", 1)

    resume_manager = StateManager(
        tmp_path,
        run_id=manager.run_id,
    )
    resume_manager.load()
    with (
        _guard_committed_child_file_reads(
            {evidence_path},
            evidence_path=evidence_path,
        ) as guarded_read_attempts,
        patch.object(
            ProviderExecutor,
            "prepare_invocation",
            prepare_synthesis_only,
        ),
        patch.object(
            ProviderExecutor,
            "execute",
            execute_synthesis_only,
        ),
    ):
        resumed_state = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(resume=True, on_error="stop")

    assert guarded_read_attempts == []
    assert provider_calls == [
        "prepare:synthesis",
        "execute:synthesis",
    ]
    assert resumed_state["status"] == "completed"
    assert _canonical_bytes(
        resumed_state["workflow_outputs"]
    ) == completed_outputs
    assert _panel_artifact_bytes(
        tmp_path,
        resumed_state,
    ) == completed_artifacts

    record_compiled_frontend_provenance(
        resumed_state,
        bundle.provenance,
    )
    after = project_judgment_views(
        resumed_state,
        resume_manager.run_root,
        workspace_root=tmp_path,
    )

    def by_coordinate(rows: list[dict[str, Any]]):
        return {
            _canonical_bytes(row["coordinate"]): row
            for row in rows
        }

    before_judgments = by_coordinate(before["judgments"])
    after_judgments = by_coordinate(after["judgments"])
    assert set(before_judgments) == set(after_judgments)
    changed_coordinates = {
        coordinate
        for coordinate in before_judgments
        if before_judgments[coordinate]
        != after_judgments[coordinate]
    }
    assert len(changed_coordinates) == 1
    affected_coordinate = changed_coordinates.pop()
    affected_before = before_judgments[affected_coordinate]
    affected_after = after_judgments[affected_coordinate]
    assert affected_before["status"] == "available"
    assert affected_after == {
        "schema_version": "workflow_judgment_inspection.v1",
        "status": "unavailable",
        "coordinate": affected_before["coordinate"],
        "reason": "judgment_result_evidence_invalid",
    }
    assert affected_before["coordinate"]["call_frame_path"] == (
        removed_scope["resume_scope"]["call_frame_ids"]
    )
    assert affected_before["coordinate"]["runtime_step_id"] == (
        removed_scope["runtime_step_id"]
    )

    before_members = by_coordinate(before["matrices"][0]["members"])
    after_members = by_coordinate(after["matrices"][0]["members"])
    assert set(before_members) == set(after_members)
    assert {
        coordinate
        for coordinate in before_members
        if before_members[coordinate] != after_members[coordinate]
    } == {affected_coordinate}
    assert after_members[affected_coordinate]["status"] == "unavailable"
    assert after_members[affected_coordinate]["reason"] == (
        "judgment_result_evidence_invalid"
    )

    before_series = by_coordinate(before["iteration_series"])
    after_series = by_coordinate(after["iteration_series"])
    assert set(before_series) - set(after_series) == {affected_coordinate}
    assert all(
        before_series[coordinate] == after_series[coordinate]
        for coordinate in after_series
    )
