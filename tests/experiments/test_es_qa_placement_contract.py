"""Structural contract for the ES QA-placement arm module."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from orchestrator.providers import CallPolicyBinding, InputMode, ProviderRegistry
from orchestrator.workflow.executable_ir import (
    ExecutableNodeKind,
    ProviderStepConfig,
)
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
from orchestrator.workflow_lisp.compiler import LoweringRoute
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import (
    SyntaxBool,
    SyntaxFloat,
    SyntaxIdentifier,
    SyntaxInt,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    build_syntax_module,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = (
    REPOSITORY_ROOT / "workflows" / "experiments" / "qa_placement_effectiveness"
)
LIBRARY_ROOT = REPOSITORY_ROOT / "workflows" / "library"
ARMS_SOURCE = WORKFLOW_ROOT / "qa_placement_arms.orc"
DIRECT_SOURCE = LIBRARY_ROOT / "control" / "direct_task.orc"
PROVIDERS_PATH = WORKFLOW_ROOT / "providers.json"
PROMPTS_PATH = WORKFLOW_ROOT / "prompts.json"

ARM_ENTRIES = {
    "DIRECT": "direct",
    "DESIGN_QA": "design-qa",
    "PRODUCT_QA": "product-qa",
    "RICH": "rich",
}
ROLE_BY_PROVIDER = {
    "providers.design": "D",
    "providers.design-review": "DR",
    "providers.design-revision": "DREV",
    "providers.implementation": "I",
    "providers.product-review": "PR",
    "providers.product-fix": "FIX",
}
PROVIDER_WORKFLOW_CONTRACT = {
    "produce-design": ("providers.design", "Bool", "design-prompt"),
    "review-design": ("providers.design-review", "ReviewResult", "design-review-prompt"),
    "revise-design": ("providers.design-revision", "Bool", "design-revision-prompt"),
    "implement-with-design": ("providers.implementation", "Bool", "implementation-prompt"),
    "review-product": ("providers.product-review", "ReviewResult", "product-review-prompt"),
    "fix-product": ("providers.product-fix", "Bool", "product-fix-prompt"),
}
PROMPT_CONTRACT = {
    "design-prompt": (
        "Bool",
        (
            ("task", ":text"),
            ("check_contract", ":text"),
            ("design_target", ":path", ":out", "DesignTarget"),
        ),
    ),
    "design-review-prompt": (
        "ReviewResult",
        (
            ("task", ":text"),
            ("check_contract", ":text"),
            ("design", ":path", "DesignTarget"),
            ("review_target", ":path", ":out", "ReviewTarget"),
        ),
    ),
    "design-revision-prompt": (
        "Bool",
        (
            ("task", ":text"),
            ("check_contract", ":text"),
            ("design", ":path", "DesignTarget"),
            ("review", ":path", "ReviewTarget"),
            ("revision_target", ":path", ":out", "DesignTarget"),
        ),
    ),
    "implementation-prompt": (
        "Bool",
        (
            ("task", ":text"),
            ("check_contract", ":text"),
            ("design", ":path", "DesignTarget"),
        ),
    ),
    "product-review-prompt": (
        "ReviewResult",
        (
            ("task", ":text"),
            ("check_contract", ":text"),
            ("review_target", ":path", ":out", "ReviewTarget"),
        ),
    ),
    "product-fix-prompt": (
        "Bool",
        (
            ("task", ":text"),
            ("check_contract", ":text"),
            ("review", ":path", "ReviewTarget"),
        ),
    ),
}
COMPLETED_SEQUENCES = {
    "DIRECT": {("I",)},
    "DESIGN_QA": {("D", "DR", "I"), ("D", "DR", "DREV", "I")},
    "PRODUCT_QA": {("I", "PR"), ("I", "PR", "FIX")},
    "RICH": {
        ("D", "DR", "I", "PR"),
        ("D", "DR", "I", "PR", "FIX"),
        ("D", "DR", "DREV", "I", "PR"),
        ("D", "DR", "DREV", "I", "PR", "FIX"),
    },
}
COMPLETED_CALL_BOUNDS = {
    "DIRECT": (1, 1),
    "DESIGN_QA": (3, 4),
    "PRODUCT_QA": (2, 3),
    "RICH": (4, 6),
}
LOCKED_PROVIDER_PROFILE = "codex_gpt55_unrestricted_workspace"
LOCKED_PROVIDER_PARAMS = {
    "model": "gpt-5.5",
    "reasoning_effort": "high",
}


def _load_decision_lock() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/experiments/es/decision_lock.py"
    spec = importlib.util.spec_from_file_location("es_qa_decision_lock", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision_lock = _load_decision_lock()


def _plain(value: object) -> Any:
    if isinstance(value, SyntaxNode):
        return _plain(value.datum)
    if isinstance(value, SyntaxList):
        return tuple(_plain(item) for item in value.items)
    if isinstance(value, SyntaxIdentifier):
        return value.display_name
    if isinstance(value, SyntaxKeyword):
        return value.value
    if isinstance(value, (SyntaxString, SyntaxInt, SyntaxFloat, SyntaxBool)):
        return value.value
    raise AssertionError(f"unsupported authored syntax node: {type(value).__name__}")


def _module_forms_and_workflows(path: Path = ARMS_SOURCE):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    forms = tuple(_plain(form) for form in syntax_module.forms)
    workflows = {
        form[1]: form
        for form in forms
        if isinstance(form, tuple) and form and form[0] == "defworkflow"
    }
    return syntax_module, forms, workflows


def _walk_tuples(value: Any):
    if not isinstance(value, tuple):
        return
    yield value
    for item in value:
        yield from _walk_tuples(item)


def _keyword_args(form: tuple[Any, ...], *, offset: int) -> dict[str, Any]:
    tail = form[offset:]
    assert len(tail) % 2 == 0
    assert all(
        isinstance(tail[index], str) and tail[index].startswith(":")
        for index in range(0, len(tail), 2)
    )
    return {tail[index]: tail[index + 1] for index in range(0, len(tail), 2)}


def _return_type(workflow: tuple[Any, ...]) -> str:
    return workflow[workflow.index("->") + 1]


def _body(workflow: tuple[Any, ...]) -> Any:
    return workflow[-1]


def _build_arm(entry: str):
    return build_frontend_bundle(
        FrontendBuildRequest(
            source_path=ARMS_SOURCE,
            source_roots=(WORKFLOW_ROOT.parent, LIBRARY_ROOT),
            entry_workflow=entry,
            provider_externs_path=PROVIDERS_PATH,
            prompt_externs_path=PROMPTS_PATH,
            workspace_root=REPOSITORY_ROOT,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )


@dataclass(frozen=True)
class _ReviewResult:
    decision: str


@dataclass(frozen=True)
class _Evaluation:
    roles: tuple[str, ...]
    value: object
    environment: Mapping[str, object]


_OPAQUE_VALUE = object()


def _resolve_identifier(
    identifier: str,
    *,
    environment: Mapping[str, object],
) -> object:
    if identifier.startswith("ReviewDecision."):
        return identifier.removeprefix("ReviewDecision.")
    base, separator, field = identifier.partition(".")
    value = environment.get(base, _OPAQUE_VALUE)
    if not separator:
        return value
    assert isinstance(value, _ReviewResult)
    assert field == "decision"
    return value.decision


def _evaluate_expr(
    expression: Any,
    *,
    environment: Mapping[str, object],
    workflows: Mapping[str, tuple[Any, ...]],
    expected_type: str | None,
) -> list[_Evaluation]:
    if isinstance(expression, bool):
        return [_Evaluation((), expression, environment)]
    if isinstance(expression, str):
        return [
            _Evaluation(
                (),
                _resolve_identifier(expression, environment=environment),
                environment,
            )
        ]

    assert isinstance(expression, tuple) and expression
    head = expression[0]
    if head == "provider-result":
        role = ROLE_BY_PROVIDER[expression[1]]
        if expected_type == "ReviewResult":
            return [
                _Evaluation((role,), _ReviewResult(decision), environment)
                for decision in ("APPROVE", "REVISE", "BLOCKED")
            ]
        assert expected_type == "Bool"
        return [
            _Evaluation((role,), value, environment)
            for value in (True, False)
        ]

    if head == "call":
        callee = expression[1]
        if callee == "control.direct-task":
            return [
                _Evaluation(("I",), value, environment)
                for value in (True, False)
            ]
        assert callee in workflows, f"non-authored call in arm graph: {callee}"
        call_arguments = _keyword_args(expression, offset=2)
        call_environment = {
            keyword.removeprefix(":"): _resolve_identifier(
                value,
                environment=environment,
            )
            for keyword, value in call_arguments.items()
        }
        return _evaluate_workflow(
            callee,
            workflows=workflows,
            environment=call_environment,
        )

    if head == "=":
        results: list[_Evaluation] = []
        for left in _evaluate_expr(
            expression[1],
            environment=environment,
            workflows=workflows,
            expected_type=None,
        ):
            for right in _evaluate_expr(
                expression[2],
                environment=left.environment,
                workflows=workflows,
                expected_type=None,
            ):
                results.append(
                    _Evaluation(
                        left.roles + right.roles,
                        left.value == right.value,
                        right.environment,
                    )
                )
        return results

    if head == "if":
        results: list[_Evaluation] = []
        for condition in _evaluate_expr(
            expression[1],
            environment=environment,
            workflows=workflows,
            expected_type="Bool",
        ):
            assert isinstance(condition.value, bool)
            selected = expression[2] if condition.value else expression[3]
            for result in _evaluate_expr(
                selected,
                environment=condition.environment,
                workflows=workflows,
                expected_type=expected_type,
            ):
                results.append(
                    _Evaluation(
                        condition.roles + result.roles,
                        result.value,
                        result.environment,
                    )
                )
        return results

    if head == "let*":
        states = [_Evaluation((), _OPAQUE_VALUE, dict(environment))]
        for name, binding_expression in expression[1]:
            next_states: list[_Evaluation] = []
            for state in states:
                for result in _evaluate_expr(
                    binding_expression,
                    environment=state.environment,
                    workflows=workflows,
                    expected_type=None,
                ):
                    updated = dict(state.environment)
                    updated[name] = result.value
                    next_states.append(
                        _Evaluation(state.roles + result.roles, result.value, updated)
                    )
            states = next_states

        results: list[_Evaluation] = []
        for state in states:
            for result in _evaluate_expr(
                expression[2],
                environment=state.environment,
                workflows=workflows,
                expected_type=expected_type,
            ):
                results.append(
                    _Evaluation(
                        state.roles + result.roles,
                        result.value,
                        result.environment,
                    )
                )
        return results

    raise AssertionError(f"non-structural expression in arm graph: {head}")


def _evaluate_workflow(
    name: str,
    *,
    workflows: Mapping[str, tuple[Any, ...]],
    environment: Mapping[str, object] | None = None,
) -> list[_Evaluation]:
    workflow = workflows[name]
    return _evaluate_expr(
        _body(workflow),
        environment=environment or {},
        workflows=workflows,
        expected_type=_return_type(workflow),
    )


def _derived_contract(workflows):
    completed: dict[str, set[tuple[str, ...]]] = {}
    prefixes: dict[tuple[str, tuple[str, ...]], bool] = {}
    terminal_outcomes: dict[tuple[str, tuple[str, ...]], set[bool]] = {}
    for arm, entry in ARM_ENTRIES.items():
        evaluations = _evaluate_workflow(entry, workflows=workflows)
        assert all(isinstance(result.value, bool) for result in evaluations)
        completed[arm] = {result.roles for result in evaluations if result.value is True}
        for result in evaluations:
            assert isinstance(result.value, bool)
            terminal_outcomes.setdefault((arm, result.roles), set()).add(result.value)
        all_prefixes = {
            result.roles[:index]
            for result in evaluations
            for index in range(len(result.roles) + 1)
        }
        prefixes.update(
            ((arm, prefix), prefix in completed[arm]) for prefix in all_prefixes
        )
    return completed, prefixes, terminal_outcomes


def test_public_arms_reuse_canonical_direct_and_compile_to_exact_bool_surface() -> None:
    syntax_module, _, workflows = _module_forms_and_workflows()
    assert syntax_module.export_directive is not None
    assert syntax_module.export_directive.names == tuple(ARM_ENTRIES.values())
    imports = {
        directive.module_name: directive for directive in syntax_module.imports
    }
    assert set(imports) == {"control/direct_task"}
    direct_import = imports["control/direct_task"]
    assert direct_import.alias == "control"
    assert direct_import.only == ("direct-task",)

    direct_calls = [
        form[1]
        for form in _walk_tuples(_body(workflows["direct"]))
        if form and form[0] == "call"
    ]
    product_calls = [
        form[1]
        for form in _walk_tuples(_body(workflows["product-qa"]))
        if form and form[0] == "call"
    ]
    assert direct_calls == ["control.direct-task"]
    assert product_calls[0] == "control.direct-task"

    _, _, direct_workflows = _module_forms_and_workflows(DIRECT_SOURCE)
    canonical_direct = direct_workflows["direct-task"]
    assert _return_type(canonical_direct) == "Bool"
    canonical_expression = _body(canonical_direct)
    assert canonical_expression[:2] == ("provider-result", "providers.direct")
    canonical_arguments = _keyword_args(canonical_expression, offset=2)
    assert canonical_arguments == {
        ":prompt": ("direct-task-prompt", ":task", "task"),
        ":model": "model",
        ":effort": "effort",
        ":delivery": ":composed",
    }

    source_text = ARMS_SOURCE.read_text(encoding="utf-8")
    assert "defworkflow implement-direct" not in source_text
    assert "prompts.implementation" not in source_text
    assert "orchestrator.experiments" not in source_text

    required_workflows = {
        *PROVIDER_WORKFLOW_CONTRACT,
        "run-product-qa",
        *ARM_ENTRIES.values(),
    }
    assert required_workflows <= set(workflows)
    for workflow_name, workflow in workflows.items():
        provider_calls = [
            form
            for form in _walk_tuples(_body(workflow))
            if form and form[0] == "provider-result"
        ]
        assert len(provider_calls) == (
            1 if workflow_name in PROVIDER_WORKFLOW_CONTRACT else 0
        )
        if workflow_name not in PROVIDER_WORKFLOW_CONTRACT:
            assert _return_type(workflow) == "Bool"

    for arm, entry in ARM_ENTRIES.items():
        built = _build_arm(entry)
        result = built.validated_bundle.surface.outputs["__result__"]
        assert result.kind == "scalar", arm
        assert dict(result.definition)["type"] == "bool", arm


def test_provider_calls_use_inline_typed_prompts_and_shared_policy() -> None:
    _, forms, workflows = _module_forms_and_workflows()
    prompts = {
        form[1]: form
        for form in forms
        if isinstance(form, tuple) and form and form[0] == "defprompt"
    }
    assert set(prompts) == set(PROMPT_CONTRACT)
    for prompt_name, (return_type, fills) in PROMPT_CONTRACT.items():
        prompt = prompts[prompt_name]
        assert prompt[2] == (":fills", *fills)
        assert _return_type(prompt) == return_type
        assert isinstance(prompt[-1], str)

    for workflow_name, (provider, return_type, prompt_name) in (
        PROVIDER_WORKFLOW_CONTRACT.items()
    ):
        workflow = workflows[workflow_name]
        expression = _body(workflow)
        assert expression[:2] == ("provider-result", provider)
        arguments = _keyword_args(expression, offset=2)
        prompt_call = arguments[":prompt"]
        assert prompt_call[0] == prompt_name
        assert arguments == {
            ":prompt": prompt_call,
            ":delivery": ":composed",
            ":model": "model",
            ":effort": "effort",
        }
        prompt_arguments = _keyword_args(prompt_call, offset=1)
        assert prompt_arguments == {
            f":{slot[0]}": slot[0]
            for slot in PROMPT_CONTRACT[prompt_name][1]
        }
        assert _return_type(workflow) == return_type

    manifest = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    assert manifest == {"trial-rubric": "prompts/trial_rubric.md"}
    assert sorted(
        path.name for path in (WORKFLOW_ROOT / "prompts").glob("*.md")
    ) == ["trial_rubric.md"]

    providers = json.loads(PROVIDERS_PATH.read_text(encoding="utf-8"))
    assert set(providers) == {
        "providers.direct",
        *ROLE_BY_PROVIDER,
        "scorer",
    }
    assert set(providers.values()) == {LOCKED_PROVIDER_PROFILE}

    registry = ProviderRegistry()
    profile = registry.get(LOCKED_PROVIDER_PROFILE)
    unrestricted = registry.get("codex_unrestricted_workspace")
    assert profile is not None
    assert unrestricted is not None
    assert profile.defaults == LOCKED_PROVIDER_PARAMS
    assert profile.input_mode == InputMode.STDIN
    assert profile.command == unrestricted.command
    assert profile.call_policy_bindings == {
        "model": CallPolicyBinding(target_param="model"),
        "effort": CallPolicyBinding(target_param="reasoning_effort"),
    }
    assert registry.merge_params(LOCKED_PROVIDER_PROFILE) == LOCKED_PROVIDER_PARAMS
    assert registry.merge_params(
        LOCKED_PROVIDER_PROFILE,
        LOCKED_PROVIDER_PARAMS,
    ) == LOCKED_PROVIDER_PARAMS


def test_output_artifacts_are_compiler_owned_and_review_result_is_typed() -> None:
    _, forms, _ = _module_forms_and_workflows()
    definitions = {
        (form[0], form[1]): form
        for form in forms
        if isinstance(form, tuple) and len(form) >= 2
    }
    assert definitions[("defenum", "ReviewDecision")] == (
        "defenum",
        "ReviewDecision",
        "APPROVE",
        "REVISE",
        "BLOCKED",
    )
    assert definitions[("defrecord", "ReviewResult")] == (
        "defrecord",
        "ReviewResult",
        ("decision", "ReviewDecision"),
    )
    assert {
        name for kind, name in definitions if kind == "defpath"
    } == {"DesignTarget", "ReviewTarget"}
    assert not any(kind == "defunion" for kind, _ in definitions)

    prompt_forms = {
        form[1]: form for form in forms if form[0] == "defprompt"
    }
    output_slots = {
        prompt_name: tuple(
            slot for slot in prompt[2][1:] if ":out" in slot
        )
        for prompt_name, prompt in prompt_forms.items()
    }
    assert output_slots == {
        "design-prompt": (("design_target", ":path", ":out", "DesignTarget"),),
        "design-review-prompt": (
            ("review_target", ":path", ":out", "ReviewTarget"),
        ),
        "design-revision-prompt": (
            ("revision_target", ":path", ":out", "DesignTarget"),
        ),
        "implementation-prompt": (),
        "product-review-prompt": (
            ("review_target", ":path", ":out", "ReviewTarget"),
        ),
        "product-fix-prompt": (),
    }

    built = _build_arm("rich")
    compiled_outputs = {}
    for workflow_name in PROVIDER_WORKFLOW_CONTRACT:
        qualified_name = (
            "qa_placement_effectiveness/qa_placement_arms::" + workflow_name
        )
        bundle = built.compile_result.validated_bundles_by_name[qualified_name]
        provider_nodes = [
            node
            for node in bundle.ir.nodes.values()
            if node.kind is ExecutableNodeKind.PROVIDER
        ]
        assert len(provider_nodes) == 1
        config = provider_nodes[0].execution_config
        assert isinstance(config, ProviderStepConfig)
        compiled_outputs[workflow_name] = tuple(
            dict(row) for row in config.common.expected_outputs
        )
    assert compiled_outputs == {
        "produce-design": (
            {
                "name": "design_target",
                "path": "${inputs.design_target}",
                "type": "string",
                "required": True,
            },
        ),
        "review-design": (
            {
                "name": "review_target",
                "path": "${inputs.review_target}",
                "type": "string",
                "required": True,
            },
        ),
        "revise-design": (
            {
                "name": "revision_target",
                "path": "${inputs.revision_target}",
                "type": "string",
                "required": True,
            },
        ),
        "implement-with-design": (),
        "review-product": (
            {
                "name": "review_target",
                "path": "${inputs.review_target}",
                "type": "string",
                "required": True,
            },
        ),
        "fix-product": (),
    }

    _, _, workflows = _module_forms_and_workflows()
    revision_calls = [
        form
        for workflow in workflows.values()
        for form in _walk_tuples(_body(workflow))
        if form[:2] == ("call", "revise-design")
    ]
    assert len(revision_calls) == 2
    assert all(
        _keyword_args(call, offset=2)[":revision_target"] == "revision_target"
        for call in revision_calls
    )
    corrected_design_consumers = [
        form
        for workflow in workflows.values()
        for form in _walk_tuples(_body(workflow))
        if form and form[0] == "call"
        and _keyword_args(form, offset=2).get(":design") == "revision_target"
    ]
    assert len(corrected_design_consumers) == 2


def test_authored_arm_outcomes_equal_the_exact_31_decision_lock_rows() -> None:
    _, _, workflows = _module_forms_and_workflows()
    completed, prefixes, terminal_outcomes = _derived_contract(workflows)
    assert completed == COMPLETED_SEQUENCES
    assert {
        arm: (
            min(len(sequence) for sequence in sequences),
            max(len(sequence) for sequence in sequences),
        )
        for arm, sequences in completed.items()
    } == COMPLETED_CALL_BOUNDS
    locked_rows = decision_lock.derive_terminal_routes()
    assert len(locked_rows) == 31
    locked: dict[tuple[str, tuple[str, ...]], list[dict[str, object]]] = {}
    for row in locked_rows:
        key = (str(row["arm"]), tuple(row["role_sequence"]))
        locked.setdefault(key, []).append(row)
    assert set(locked) == set(prefixes)
    for key, rows in locked.items():
        arm, roles = key
        suffix = "_".join(roles) if roles else "EMPTY"
        expected = {
            "arm": arm,
            "route_id": f"{arm}.{suffix}",
            "role_sequence": list(roles),
            "call_slots": [f"{arm}.{role}" for role in roles],
            "call_count": len(roles),
            "completed": prefixes[key],
        }
        assert rows[0] == expected
        assert rows[1:] == (
            [
                {
                    **expected,
                    "route_id": f"{arm}.{suffix}.FAILED_AT_FINAL_CALL",
                    "completed": False,
                }
            ]
            if prefixes[key]
            else []
        )
        if roles:
            assert terminal_outcomes[key] == {
                bool(row["completed"]) for row in rows
            }
