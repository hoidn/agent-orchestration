from __future__ import annotations

from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
from orchestrator.workflow_lisp.wcc.defunctionalize import (
    _wcc_continuation_binding_demands,
)
from orchestrator.workflow_lisp.wcc.model import (
    WccHalt,
    WccIdentityFactory,
    WccIf,
    WccLet,
    WccNameAtom,
    WccPerform,
)


def test_continuation_demand_scan_shares_unchanged_prefix_and_selects_operands() -> None:
    span = SourceSpan(
        start=SourcePosition(path="demand.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="demand.orc", line=1, column=2, offset=1),
    )
    value_type = PrimitiveTypeRef(name="String")
    scope = WccIdentityFactory(owner_name="demand-test")

    def metadata(role: str, *, body: bool):
        maker = scope.body_metadata if body else scope.value_metadata
        return maker(
            role=role,
            type_ref=value_type,
            source_span=span,
            form_path=("test", role),
        )

    def name(value: str) -> WccNameAtom:
        return WccNameAtom(metadata=metadata(f"name:{value}", body=False), name=value)

    halt = WccHalt(metadata=metadata("halt", body=True), result=name("result"))
    request = WccLet(
        metadata=metadata("let:request", body=True),
        bound_name="request",
        bound_type_ref=value_type,
        bound_value=WccPerform(
            metadata=metadata("perform:request", body=False),
            perform_kind="request_input",
            target_name="request-input",
            prompt_name=None,
            positional_args=(name("question_only"),),
            keyword_args=(("ignored", name("request_keyword_ignored")),),
            returns_type_name="HumanReply",
        ),
        body=halt,
    )
    branch = WccIf(
        metadata=metadata("if", body=True),
        condition=name("condition"),
        condition_shape=object(),
        then_body=request,
        else_body=halt,
    )
    provider = WccLet(
        metadata=metadata("let:provider", body=True),
        bound_name="provider",
        bound_type_ref=value_type,
        bound_value=WccPerform(
            metadata=metadata("perform:provider", body=False),
            perform_kind="provider_result",
            target_name="providers.ask",
            prompt_name="prompts.ask",
            positional_args=(name("provider_positional_ignored"),),
            keyword_args=(),
            returns_type_name="String",
            operation_payload={
                "context_expr": name("context_only"),
                "ignored": name("provider_payload_ignored"),
            },
        ),
        body=branch,
    )
    run_ref = WccLet(
        metadata=metadata("let:run-ref", body=True),
        bound_name="run_ref",
        bound_type_ref=value_type,
        bound_value=WccPerform(
            metadata=metadata("perform:run-ref", body=False),
            perform_kind="run_ref",
            target_name="run-ref",
            prompt_name=None,
            positional_args=(name("run_ref_positional_ignored"),),
            keyword_args=(("input", name("run_ref_only")),),
            returns_type_name="String",
        ),
        body=provider,
    )
    prefix = WccLet(
        metadata=metadata("let:prefix", body=True),
        bound_name="prefix",
        bound_type_ref=value_type,
        bound_value=name("ordinary_value"),
        body=run_ref,
    )

    demands = _wcc_continuation_binding_demands(prefix)

    assert demands[id(prefix)] is demands[id(run_ref)]
    assert demands[id(prefix)] == (
        frozenset({"run_ref_only"}),
        frozenset({"context_only"}),
        frozenset({"question_only"}),
    )
    assert demands[id(branch.else_body)] == (frozenset(), frozenset(), frozenset())
    assert demands[id(branch.then_body)][2] == frozenset({"question_only"})
