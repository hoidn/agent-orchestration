"""Typed expression validation for the Workflow Lisp MVP."""

from __future__ import annotations

from dataclasses import dataclass

from .definition_validation import DefinitionCheckedModule
from .definitions import (
    DefinitionTypeRef,
    ProcedureDefinition,
    RecordDefinition,
    UnionDefinition,
    WorkflowDefinition,
)
from .expressions import (
    CallExpression,
    CommandResultExpression,
    ExpressionNode,
    FieldAccessExpression,
    LetStarExpression,
    LiteralExpression,
    MatchExpression,
    ProviderResultExpression,
    RecordExpression,
    ReferenceExpression,
    WithPhaseExpression,
    shape_expression,
)
from .parser import WorkflowLispSyntaxError
from .syntax import SourceSpan, SyntaxDiagnostic


@dataclass(frozen=True)
class ExpressionCheckedWorkflow:
    """One defworkflow body after expression typing."""

    name: str
    expression: ExpressionNode
    inferred_return_type: str


@dataclass(frozen=True)
class ExpressionCheckedProcedure:
    """One defproc body after expression typing."""

    name: str
    expression: ExpressionNode
    inferred_return_type: str


@dataclass(frozen=True)
class ExpressionCheckedModule:
    """Definition-checked module with typed workflow expressions."""

    source_path: str
    workflows: tuple[ExpressionCheckedWorkflow, ...]
    procedures: tuple[ExpressionCheckedProcedure, ...] = ()


@dataclass(frozen=True)
class _ScalarType:
    name: str


@dataclass(frozen=True)
class _RecordType:
    name: str
    fields: dict[str, str]


@dataclass(frozen=True)
class _UnionType:
    name: str
    variants: dict[str, dict[str, str]]


@dataclass(frozen=True)
class _UnionVariantType:
    union_name: str
    variant_name: str
    fields: dict[str, str]


_ValueType = _ScalarType | _RecordType | _UnionType | _UnionVariantType


def _raise_expression_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    enclosing_form_name: str | None = None,
    generated_core_node_id: str | None = None,
) -> None:
    raise WorkflowLispSyntaxError(
        SyntaxDiagnostic(
            code=code,
            message=message,
            span=span,
            source_file=span.source_file,
            line=span.line_start,
            column=span.column_start,
            enclosing_form_name=enclosing_form_name,
            generated_core_node_id=generated_core_node_id,
        )
    )


def validate_expression_module(module: DefinitionCheckedModule) -> ExpressionCheckedModule:
    """Type-check workflow body expressions for one definition-checked module."""

    imported_only_names, import_aliases = _collect_import_type_resolution(module)
    type_catalog = _build_type_catalog(module, imported_only_names=imported_only_names)
    callable_catalog: dict[str, WorkflowDefinition | ProcedureDefinition] = {
        workflow.name: workflow for workflow in module.workflow_definitions
    }
    callable_catalog.update({procedure.name: procedure for procedure in module.procedure_definitions})
    workflows: list[ExpressionCheckedWorkflow] = []
    procedures: list[ExpressionCheckedProcedure] = []

    for workflow in module.workflow_definitions:
        assert isinstance(workflow, WorkflowDefinition)
        generated_core_node_id = f"{workflow.name}.result"
        if len(workflow.body_forms) != 1:
            _raise_expression_error(
                code="frontend_parse_error",
                message=f"defworkflow {workflow.name} requires exactly one body expression in MVP",
                span=workflow.form_span,
                enclosing_form_name="defworkflow",
                generated_core_node_id=generated_core_node_id,
            )

        expression = shape_expression(workflow.body_forms[0])
        env: dict[str, _ValueType] = {}
        for parameter in workflow.parameters:
            env[parameter.name] = _resolve_type_ref(
                parameter.type_ref,
                type_catalog,
                import_aliases=import_aliases,
                generated_core_node_id=generated_core_node_id,
            )

        inferred = _infer_expression_type(
            expression,
            env,
            type_catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )
        if _type_name(inferred) != workflow.return_type.name:
            _raise_expression_error(
                code="return_type_mismatch",
                message=(
                    f"Workflow {workflow.name} returns {_type_name(inferred)} "
                    f"but declares {workflow.return_type.name}"
                ),
                span=workflow.return_type.span,
                enclosing_form_name="defworkflow",
                generated_core_node_id=generated_core_node_id,
            )

        workflows.append(
            ExpressionCheckedWorkflow(
                name=workflow.name,
                expression=expression,
                inferred_return_type=_type_name(inferred),
            )
        )

    for procedure in module.procedure_definitions:
        generated_core_node_id = f"{procedure.name}.result"
        if len(procedure.body_forms) != 1:
            _raise_expression_error(
                code="frontend_parse_error",
                message=f"defproc {procedure.name} requires exactly one body expression in MVP",
                span=procedure.form_span,
                enclosing_form_name="defproc",
                generated_core_node_id=generated_core_node_id,
            )

        expression = shape_expression(procedure.body_forms[0])
        env = {
            parameter.name: _resolve_type_ref(
                parameter.type_ref,
                type_catalog,
                import_aliases=import_aliases,
                generated_core_node_id=generated_core_node_id,
            )
            for parameter in procedure.parameters
        }
        inferred = _infer_expression_type(
            expression,
            env,
            type_catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )
        if _type_name(inferred) != procedure.return_type.name:
            _raise_expression_error(
                code="return_type_mismatch",
                message=(
                    f"Procedure {procedure.name} returns {_type_name(inferred)} "
                    f"but declares {procedure.return_type.name}"
                ),
                span=procedure.return_type.span,
                enclosing_form_name="defproc",
                generated_core_node_id=generated_core_node_id,
            )
        procedures.append(
            ExpressionCheckedProcedure(
                name=procedure.name,
                expression=expression,
                inferred_return_type=_type_name(inferred),
            )
        )

    return ExpressionCheckedModule(
        source_path=module.source_path,
        workflows=tuple(workflows),
        procedures=tuple(procedures),
    )


def _build_type_catalog(
    module: DefinitionCheckedModule,
    *,
    imported_only_names: frozenset[str],
) -> dict[str, _ValueType]:
    catalog: dict[str, _ValueType] = {
        "String": _ScalarType(name="String"),
        "Int": _ScalarType(name="Int"),
        "Float": _ScalarType(name="Float"),
        "Bool": _ScalarType(name="Bool"),
        "Json": _ScalarType(name="Json"),
        "Provider": _ScalarType(name="Provider"),
        "Prompt": _ScalarType(name="Prompt"),
        "PathRel": _ScalarType(name="PathRel"),
    }

    for definition in module.definitions:
        if isinstance(definition, RecordDefinition):
            catalog[definition.name] = _RecordType(
                name=definition.name,
                fields={field.name: field.type_ref.name for field in definition.fields},
            )
        elif isinstance(definition, UnionDefinition):
            catalog[definition.name] = _UnionType(
                name=definition.name,
                variants={
                    variant.name: {field.name: field.type_ref.name for field in variant.fields}
                    for variant in definition.variants
                },
            )
        else:
            # Enums and defpath are treated as scalar types for MVP expression typing.
            catalog[definition.name] = _ScalarType(name=definition.name)

    for imported_name in imported_only_names:
        catalog.setdefault(imported_name, _ScalarType(name=imported_name))

    return catalog


def _collect_import_type_resolution(
    module: DefinitionCheckedModule,
) -> tuple[frozenset[str], frozenset[str]]:
    imported_only_names: set[str] = set()
    import_aliases: set[str] = set()
    for import_definition in module.import_definitions:
        imported_only_names.update(import_definition.only_names)
        if import_definition.alias is None:
            import_aliases.add(import_definition.module_ref)
            continue
        if import_definition.only_names:
            for imported_name in import_definition.only_names:
                imported_only_names.add(f"{import_definition.alias}.{imported_name}")
                imported_only_names.add(f"{import_definition.alias}/{imported_name}")
            continue
        import_aliases.add(import_definition.alias)
    return frozenset(imported_only_names), frozenset(import_aliases)


def _is_imported_workflow_reference(
    workflow_name: str,
    *,
    imported_only_names: frozenset[str],
    import_aliases: frozenset[str],
) -> bool:
    if workflow_name in imported_only_names:
        return True
    return _is_import_qualified_type_name(workflow_name, import_aliases=import_aliases)


def _is_import_qualified_type_name(type_name: str, *, import_aliases: frozenset[str]) -> bool:
    for alias in import_aliases:
        for separator in (".", "/"):
            prefix = f"{alias}{separator}"
            if type_name.startswith(prefix) and len(type_name) > len(prefix):
                return True
    return False


def _resolve_type_name(
    type_name: str,
    *,
    catalog: dict[str, _ValueType],
    import_aliases: frozenset[str],
    span: SourceSpan,
    generated_core_node_id: str | None = None,
    enclosing_form_name: str | None = None,
) -> _ValueType:
    resolved = catalog.get(type_name)
    if resolved is not None:
        return resolved
    if _is_import_qualified_type_name(type_name, import_aliases=import_aliases):
        opaque_import_type = _ScalarType(name=type_name)
        catalog[type_name] = opaque_import_type
        return opaque_import_type
    _raise_expression_error(
        code="type_unknown",
        message=f"Unknown type reference: {type_name}",
        span=span,
        enclosing_form_name=enclosing_form_name,
        generated_core_node_id=generated_core_node_id,
    )


def _resolve_type_ref(
    type_ref: DefinitionTypeRef,
    catalog: dict[str, _ValueType],
    *,
    import_aliases: frozenset[str],
    generated_core_node_id: str | None = None,
) -> _ValueType:
    return _resolve_type_name(
        type_ref.name,
        catalog=catalog,
        import_aliases=import_aliases,
        span=type_ref.span,
        generated_core_node_id=generated_core_node_id,
    )


def _infer_expression_type(
    expression: ExpressionNode,
    env: dict[str, _ValueType],
    catalog: dict[str, _ValueType],
    callable_catalog: dict[str, WorkflowDefinition | ProcedureDefinition],
    *,
    imported_only_names: frozenset[str],
    import_aliases: frozenset[str],
    generated_core_node_id: str | None = None,
) -> _ValueType:
    if isinstance(expression, LiteralExpression):
        if expression.kind.value == "string":
            return catalog["String"]
        if expression.kind.value == "int":
            return catalog["Int"]
        if expression.kind.value == "float":
            return catalog["Float"]
        if expression.kind.value == "bool":
            return catalog["Bool"]
        if expression.kind.value == "nil":
            return catalog["Json"]
        _raise_expression_error(
            code="type_mismatch",
            message=f"Unsupported literal kind in expression typing: {expression.kind.value}",
            span=expression.span,
            generated_core_node_id=generated_core_node_id,
        )

    if isinstance(expression, ReferenceExpression):
        resolved = env.get(expression.name)
        if resolved is None:
            _raise_expression_error(
                code="type_unknown",
                message=f"Unknown reference: {expression.name}",
                span=expression.span,
                generated_core_node_id=generated_core_node_id,
            )
        return resolved

    if isinstance(expression, FieldAccessExpression):
        base_type = _infer_expression_type(
            expression.base,
            env,
            catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )
        if isinstance(base_type, _RecordType):
            field_type_name = base_type.fields.get(expression.field_name)
            if field_type_name is None:
                _raise_expression_error(
                    code="type_mismatch",
                    message=f"Unknown field {expression.field_name} on record type {base_type.name}",
                    span=expression.span,
                    enclosing_form_name="field.access",
                    generated_core_node_id=generated_core_node_id,
                )
            return _resolve_type_name(
                field_type_name,
                catalog=catalog,
                import_aliases=import_aliases,
                span=expression.span,
                enclosing_form_name="field.access",
                generated_core_node_id=generated_core_node_id,
            )
        if isinstance(base_type, _UnionVariantType):
            field_type_name = base_type.fields.get(expression.field_name)
            if field_type_name is None:
                _raise_expression_error(
                    code="type_mismatch",
                    message=(
                        f"Unknown field {expression.field_name} on variant "
                        f"{base_type.union_name}.{base_type.variant_name}"
                    ),
                    span=expression.span,
                    enclosing_form_name="field.access",
                    generated_core_node_id=generated_core_node_id,
                )
            return _resolve_type_name(
                field_type_name,
                catalog=catalog,
                import_aliases=import_aliases,
                span=expression.span,
                enclosing_form_name="field.access",
                generated_core_node_id=generated_core_node_id,
            )
        if isinstance(base_type, _UnionType):
            _raise_expression_error(
                code="variant_ref_unproved",
                message=(
                    f"Field {expression.field_name} on union type {base_type.name} "
                    "requires variant proof"
                ),
                span=expression.span,
                enclosing_form_name="field.access",
                generated_core_node_id=generated_core_node_id,
            )
        _raise_expression_error(
            code="type_mismatch",
            message=f"Type {_type_name(base_type)} does not support field access",
            span=expression.span,
            enclosing_form_name="field.access",
            generated_core_node_id=generated_core_node_id,
        )

    if isinstance(expression, RecordExpression):
        resolved_record = catalog.get(expression.type_name)
        if resolved_record is None:
            _raise_expression_error(
                code="type_unknown",
                message=f"Unknown record type: {expression.type_name}",
                span=expression.type_span,
                enclosing_form_name="record",
                generated_core_node_id=generated_core_node_id,
            )
        if not isinstance(resolved_record, _RecordType):
            _raise_expression_error(
                code="type_mismatch",
                message=f"record constructor requires a record type; got {resolved_record.name}",
                span=expression.type_span,
                enclosing_form_name="record",
                generated_core_node_id=generated_core_node_id,
            )

        provided_fields = {field.field_name for field in expression.fields}
        expected_fields = set(resolved_record.fields)
        missing_fields = sorted(expected_fields - provided_fields)
        if missing_fields:
            _raise_expression_error(
                code="type_mismatch",
                message=(
                    f"Record constructor for {resolved_record.name} "
                    f"is missing required field: {missing_fields[0]}"
                ),
                span=expression.span,
                enclosing_form_name="record",
                generated_core_node_id=generated_core_node_id,
            )

        unexpected_fields = sorted(provided_fields - expected_fields)
        if unexpected_fields:
            _raise_expression_error(
                code="type_mismatch",
                message=(
                    f"Record constructor for {resolved_record.name} "
                    f"has unknown field: {unexpected_fields[0]}"
                ),
                span=expression.span,
                enclosing_form_name="record",
                generated_core_node_id=generated_core_node_id,
            )

        for field in expression.fields:
            expected_type_name = resolved_record.fields[field.field_name]
            value_type = _infer_expression_type(
                field.value,
                env,
                catalog,
                callable_catalog,
                imported_only_names=imported_only_names,
                import_aliases=import_aliases,
                generated_core_node_id=generated_core_node_id,
            )
            actual_type_name = _type_name(value_type)
            if actual_type_name != expected_type_name:
                _raise_expression_error(
                    code="type_mismatch",
                    message=(
                        f"Record field {resolved_record.name}.{field.field_name} "
                        f"expects {expected_type_name} but got {actual_type_name}"
                    ),
                    span=field.form_span,
                    enclosing_form_name="record",
                    generated_core_node_id=generated_core_node_id,
                )
        return resolved_record

    if isinstance(expression, CallExpression):
        callee = callable_catalog.get(expression.callee_name)
        is_imported_reference = _is_imported_workflow_reference(
            expression.callee_name,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
        )
        if callee is None:
            if is_imported_reference:
                if expression.returns_type_name is None or expression.returns_type_span is None:
                    _raise_expression_error(
                        code="workflow_call_signature_erased",
                        message=(
                            f"Imported workflow call {expression.callee_name} requires an explicit "
                            ":returns type"
                        ),
                        span=expression.callee_span,
                        enclosing_form_name="call",
                        generated_core_node_id=generated_core_node_id,
                    )
                for argument in expression.arguments:
                    _infer_expression_type(
                        argument.value,
                        env,
                        catalog,
                        callable_catalog,
                        imported_only_names=imported_only_names,
                        import_aliases=import_aliases,
                        generated_core_node_id=generated_core_node_id,
                    )
                return _resolve_type_name(
                    expression.returns_type_name,
                    catalog=catalog,
                    import_aliases=import_aliases,
                    span=expression.returns_type_span,
                    enclosing_form_name="call",
                    generated_core_node_id=generated_core_node_id,
                )
            _raise_expression_error(
                code="type_unknown",
                message=f"Unknown workflow reference: {expression.callee_name}",
                span=expression.callee_span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )

        if expression.returns_type_name is not None:
            if is_imported_reference:
                _raise_expression_error(
                    code="workflow_call_signature_erased",
                    message=(
                        f"Imported workflow call {expression.callee_name} has a local signature; "
                        "remove explicit :returns"
                    ),
                    span=expression.returns_type_span or expression.span,
                    enclosing_form_name="call",
                    generated_core_node_id=generated_core_node_id,
                )
            _raise_expression_error(
                code="frontend_parse_error",
                message="call :returns is only allowed for imported workflow references",
                span=expression.returns_type_span or expression.span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )

        expected_parameters = {parameter.name: parameter for parameter in callee.parameters}
        provided_names = {argument.parameter_name for argument in expression.arguments}
        missing_names = sorted(set(expected_parameters) - provided_names)
        if missing_names:
            _raise_expression_error(
                code="workflow_signature_mismatch",
                message=(
                    f"Missing call argument for workflow {callee.name}: {missing_names[0]}"
                ),
                span=expression.span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        unexpected_names = sorted(provided_names - set(expected_parameters))
        if unexpected_names:
            _raise_expression_error(
                code="workflow_signature_mismatch",
                message=(
                    f"Unknown call argument for workflow {callee.name}: {unexpected_names[0]}"
                ),
                span=expression.span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        for argument in expression.arguments:
            parameter = expected_parameters[argument.parameter_name]
            expected_type = _resolve_type_ref(
                parameter.type_ref,
                catalog,
                import_aliases=import_aliases,
                generated_core_node_id=generated_core_node_id,
            )
            actual_type = _infer_expression_type(
                argument.value,
                env,
                catalog,
                callable_catalog,
                imported_only_names=imported_only_names,
                import_aliases=import_aliases,
                generated_core_node_id=generated_core_node_id,
            )
            if _type_name(expected_type) != _type_name(actual_type):
                _raise_expression_error(
                    code="type_mismatch",
                    message=(
                        f"Call argument {callee.name}.{argument.parameter_name} "
                        f"expects {_type_name(expected_type)} but got {_type_name(actual_type)}"
                    ),
                    span=argument.form_span,
                    enclosing_form_name="call",
                    generated_core_node_id=generated_core_node_id,
                )
        return _resolve_type_ref(
            callee.return_type,
            catalog,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )

    if isinstance(expression, ProviderResultExpression):
        provider_type = _infer_expression_type(
            expression.provider_reference,
            env,
            catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )
        if _type_name(provider_type) != "Provider":
            _raise_expression_error(
                code="type_mismatch",
                message="provider-result provider reference must have type Provider",
                span=expression.provider_reference.span,
                enclosing_form_name="provider-result",
                generated_core_node_id=generated_core_node_id,
            )
        prompt_type = _infer_expression_type(
            expression.prompt_reference,
            env,
            catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )
        if _type_name(prompt_type) != "Prompt":
            _raise_expression_error(
                code="type_mismatch",
                message="provider-result :prompt value must have type Prompt",
                span=expression.prompt_reference.span,
                enclosing_form_name="provider-result",
                generated_core_node_id=generated_core_node_id,
            )
        for input_expression in expression.inputs:
            _infer_expression_type(
                input_expression,
                env,
                catalog,
                callable_catalog,
                imported_only_names=imported_only_names,
                import_aliases=import_aliases,
                generated_core_node_id=generated_core_node_id,
            )
        returns_type = catalog.get(expression.returns_type_name)
        if returns_type is None:
            _raise_expression_error(
                code="type_unknown",
                message=f"Unknown type reference: {expression.returns_type_name}",
                span=expression.returns_type_span,
                enclosing_form_name="provider-result",
                generated_core_node_id=generated_core_node_id,
            )
        if not isinstance(returns_type, (_RecordType, _UnionType)):
            _raise_expression_error(
                code="type_mismatch",
                message="provider-result :returns must reference a record or union type",
                span=expression.returns_type_span,
                enclosing_form_name="provider-result",
                generated_core_node_id=generated_core_node_id,
            )
        return returns_type

    if isinstance(expression, CommandResultExpression):
        for argument in expression.argv:
            _infer_expression_type(
                argument,
                env,
                catalog,
                callable_catalog,
                imported_only_names=imported_only_names,
                import_aliases=import_aliases,
                generated_core_node_id=generated_core_node_id,
            )
        returns_type = catalog.get(expression.returns_type_name)
        if returns_type is None:
            _raise_expression_error(
                code="type_unknown",
                message=f"Unknown type reference: {expression.returns_type_name}",
                span=expression.returns_type_span,
                enclosing_form_name="command-result",
                generated_core_node_id=generated_core_node_id,
            )
        if not isinstance(returns_type, (_RecordType, _UnionType)):
            _raise_expression_error(
                code="type_mismatch",
                message="command-result :returns must reference a record or union type",
                span=expression.returns_type_span,
                enclosing_form_name="command-result",
                generated_core_node_id=generated_core_node_id,
            )
        return returns_type

    if isinstance(expression, LetStarExpression):
        local_env = dict(env)
        for binding in expression.bindings:
            local_env[binding.name] = _infer_expression_type(
                binding.value,
                local_env,
                catalog,
                callable_catalog,
                imported_only_names=imported_only_names,
                import_aliases=import_aliases,
                generated_core_node_id=generated_core_node_id,
            )
        return _infer_expression_type(
            expression.body,
            local_env,
            catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )

    if isinstance(expression, WithPhaseExpression):
        _infer_expression_type(
            expression.context,
            env,
            catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )
        return _infer_expression_type(
            expression.body,
            env,
            catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )

    if isinstance(expression, MatchExpression):
        subject_type = _infer_expression_type(
            expression.subject,
            env,
            catalog,
            callable_catalog,
            imported_only_names=imported_only_names,
            import_aliases=import_aliases,
            generated_core_node_id=generated_core_node_id,
        )
        if not isinstance(subject_type, _UnionType):
            _raise_expression_error(
                code="type_mismatch",
                message="match subject must be a union type",
                span=expression.subject.span,
                enclosing_form_name="match",
                generated_core_node_id=generated_core_node_id,
            )

        seen_variants: set[str] = set()
        arm_types: list[_ValueType] = []
        for arm in expression.arms:
            variant_fields = subject_type.variants.get(arm.variant_name)
            if variant_fields is None:
                _raise_expression_error(
                    code="union_variant_unknown",
                    message=f"Unknown match variant {arm.variant_name} for union {subject_type.name}",
                    span=arm.variant_span,
                    enclosing_form_name="match",
                    generated_core_node_id=generated_core_node_id,
                )
            if arm.variant_name in seen_variants:
                _raise_expression_error(
                    code="frontend_parse_error",
                    message=f"Duplicate match arm variant: {arm.variant_name}",
                    span=arm.variant_span,
                    enclosing_form_name="match",
                    generated_core_node_id=generated_core_node_id,
                )
            seen_variants.add(arm.variant_name)

            arm_env = dict(env)
            arm_env[arm.binding_name] = _UnionVariantType(
                union_name=subject_type.name,
                variant_name=arm.variant_name,
                fields=variant_fields,
            )
            arm_types.append(
                _infer_expression_type(
                    arm.body,
                    arm_env,
                    catalog,
                    callable_catalog,
                    imported_only_names=imported_only_names,
                    import_aliases=import_aliases,
                    generated_core_node_id=generated_core_node_id,
                )
            )

        expected_variants = set(subject_type.variants)
        if not expression.partial and seen_variants != expected_variants:
            _raise_expression_error(
                code="union_match_non_exhaustive",
                message=f"Non-exhaustive match over {subject_type.name}",
                span=expression.span,
                enclosing_form_name="match",
                generated_core_node_id=generated_core_node_id,
            )

        if not arm_types:
            _raise_expression_error(
                code="frontend_parse_error",
                message="match requires at least one arm",
                span=expression.span,
                enclosing_form_name="match",
                generated_core_node_id=generated_core_node_id,
            )

        first_name = _type_name(arm_types[0])
        for arm_type in arm_types[1:]:
            if _type_name(arm_type) != first_name:
                _raise_expression_error(
                    code="type_mismatch",
                    message=(
                        "All match arms must produce the same type; "
                        f"found {first_name} and {_type_name(arm_type)}"
                    ),
                    span=expression.span,
                    enclosing_form_name="match",
                    generated_core_node_id=generated_core_node_id,
                )
        return arm_types[0]

    _raise_expression_error(
        code="frontend_parse_error",
        message="Unsupported expression node for typing",
        span=expression.span,
        generated_core_node_id=generated_core_node_id,
    )


def _type_name(value_type: _ValueType) -> str:
    if isinstance(value_type, _UnionVariantType):
        return value_type.union_name
    return value_type.name
