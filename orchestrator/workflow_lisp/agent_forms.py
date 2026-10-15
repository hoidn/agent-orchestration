"""Elaboration of the target-gated `agent` constructor.

`(agent <provider-extern> [:model String] [:effort String])` elaborates to one
`AgentExpr`. Typing and provider origins live in `typecheck_agents.py`.
"""

from __future__ import annotations

from .compiler_session import ElaborationSessionState
from .expressions import AgentExpr, _elaborate, _keyword_sections, _raise_error
from .syntax import (
    AGENT_SESSIONS_MIN_TARGET_DSL_VERSION,
    SyntaxList,
    target_dsl_supports_agent_sessions,
)

_AGENT_KEYWORDS = (":model", ":effort")


def _elaborate_agent(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> AgentExpr:
    """Elaborate one `agent` form; refuse it below target 2.38 and outside its keywords."""

    if not target_dsl_supports_agent_sessions(session_state.target_dsl_version or ""):
        _raise_error(
            f"`agent` requires target DSL {AGENT_SESSIONS_MIN_TARGET_DSL_VERSION} or newer",
            code="agent_target_dsl_unsupported",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if len(datum.items) < 2:
        _raise_error(
            "`agent` requires a provider extern",
            code="agent_provider_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    def elaborate(node: object):
        return _elaborate(node, form_path=form_path, bound_names=bound_names,
                          procedure_names=procedure_names, session_state=session_state)

    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`agent`")
    for keyword_node in datum.items[2::2]:
        if keyword_node.value not in _AGENT_KEYWORDS:
            _raise_error(
                f"`agent` does not accept keyword `{keyword_node.value}`",
                code="agent_keyword_invalid",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
    model, effort = (sections.get(name) for name in _AGENT_KEYWORDS)
    return AgentExpr(
        provider=elaborate(datum.items[1]),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
        model=None if model is None else elaborate(model),
        effort=None if effort is None else elaborate(effort),
    )


def elaborate_agent_perform(expr: AgentExpr, *, metadata, elaborate):
    """Build the WCC `agent` perform: provider extern target plus inline policy keywords.

    `elaborate(operand, name)` lowers one inline-lowerable policy operand to a WCC atom.
    """

    from .wcc.elaborate import _require_name_expr
    from .wcc.model import WccPerform

    return WccPerform(
        metadata=metadata,
        perform_kind="agent",
        target_name=_require_name_expr(expr.provider),
        prompt_name=None,
        positional_args=(),
        keyword_args=tuple((name, elaborate(value, name))
                           for name, value in (("model", expr.model), ("effort", expr.effort)) if value is not None),
        returns_type_name="Agent",
        operation_payload=None,
    )
