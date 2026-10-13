"""Target admission, authored clauses and pure workspace typing for parallel maps."""

from .syntax import SyntaxInt, SyntaxKeyword, target_dsl_supports_parallel_map
from .type_env import PathTypeRef, PrimitiveTypeRef
from .typecheck_context import raise_error


def _refuse(datum, message, code, *, form_path, raise_error):
    raise_error(
        message, code=code, span=datum.span, form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _clauses(datum, *, form_path, raise_error):
    values = {}
    if len(datum.items) < 3 or len(datum.items[2:-1]) % 2:
        _refuse(
            datum, "`list/map-effect` requires keyword/value pairs and one body",
            "list_map_effect_body_unsupported",
            form_path=form_path, raise_error=raise_error,
        )
    for index in range(2, len(datum.items) - 1, 2):
        key, value = datum.items[index:index + 2]
        if not isinstance(key, SyntaxKeyword) or key.value not in {":max", ":parallel", ":workspace"}:
            _refuse(
                key, "unknown `list/map-effect` clause",
                "list_map_effect_body_unsupported",
                form_path=form_path, raise_error=raise_error,
            )
        if key.value in values:
            _refuse(
                key, f"duplicate `list/map-effect` clause `{key.value}`",
                "list_map_effect_body_unsupported",
                form_path=form_path, raise_error=raise_error,
            )
        values[key.value] = value
    return values


def _positive_literal(datum, value, *, name, form_path, raise_error):
    if not isinstance(value, SyntaxInt) or type(value.value) is not int or value.value <= 0:
        _refuse(
            datum,
            f"`list/map-effect` requires `{name}` followed by a positive integer literal; minimum=1",
            f"list_map_effect_{name[1:]}_invalid",
            form_path=form_path, raise_error=raise_error,
        )
    return value.value


def parallel_map_options(datum, *, target, form_path, raise_error):
    if not target_dsl_supports_parallel_map(target):
        _refuse(
            datum, "parallel `list/map-effect` requires target DSL 2.37 or newer",
            "list_traversal_target_dsl_unsupported",
            form_path=form_path, raise_error=raise_error,
        )
    values = _clauses(datum, form_path=form_path, raise_error=raise_error)
    cap = _positive_literal(
        datum, values.get(":max"), name=":max",
        form_path=form_path, raise_error=raise_error,
    )
    count = _positive_literal(
        datum, values.get(":parallel"), name=":parallel",
        form_path=form_path, raise_error=raise_error,
    )
    workspace = values.get(":workspace")
    if workspace is None:
        _refuse(
            datum, "parallel `list/map-effect` requires an explicit `:workspace`",
            "list_map_effect_workspace_invalid",
            form_path=form_path, raise_error=raise_error,
        )
    return cap, count, workspace, datum.items[-1]


def typecheck_parallel_workspace(expr, *, context, recurse, value_env, binding_env):
    from .typecheck_structural_values import _is_pure_or_provisional_procedure_call

    workspace = expr.workspace_expr
    if workspace is None:
        raise_error(
            "parallel `list/map-effect` requires an explicit workspace",
            code="list_map_effect_workspace_invalid", span=expr.span,
            form_path=expr.form_path, expansion_stack=expr.expansion_stack,
        )
    typed = recurse(workspace, value_env=value_env, binding_env=binding_env)
    if not _is_pure_or_provisional_procedure_call(typed.effect_summary, context=context):
        raise_error(
            "parallel `list/map-effect` workspace must be pure",
            code="list_map_effect_workspace_invalid", span=workspace.span,
            form_path=workspace.form_path, expansion_stack=workspace.expansion_stack,
        )
    valid_type = isinstance(typed.type_ref, PathTypeRef) or (
        isinstance(typed.type_ref, PrimitiveTypeRef) and typed.type_ref.name == "String"
    )
    if not valid_type:
        raise_error(
            "parallel `list/map-effect` workspace must have String or path type",
            code="pure_expr_operand_type_mismatch", span=workspace.span,
            form_path=workspace.form_path, expansion_stack=workspace.expansion_stack,
        )
    return typed.expr
