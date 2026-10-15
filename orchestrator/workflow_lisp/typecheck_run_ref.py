"""Narrow type owner for isolated target-2.24 ``run-ref`` expressions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from .definitions import RecordDef, RecordField, UnionDef, UnionVariant
from .effects import (
    CapturesSnapshotEffect,
    EffectSummary,
    HostInputEffect,
    LivePeerMessagingEffect,
    LiveSupervisionEffect,
    MaterializesPointerEffect,
    MovesResourceEffect,
    RunsRefEffect,
    RunsTrialEffect,
    UpdatesLedgerEffect,
    UpdatesStateEffect,
    UsesProviderEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from . import expressions as ex
from .expressions import RunRefBundleProgram, RunRefExpr, RunRefPathProgram, RunRefWorkflowProgram
from .spans import SourcePosition, SourceSpan
from .type_env import (
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    TypeParamRef,
    UnionTypeRef,
    VariantCaseTypeRef,
    WorkflowRefTypeRef,
    type_refs_compatible,
)
from .expression_traversal import walk_expr
from .typecheck_context import (
    TypedExpr,
    TypecheckSessionStateCollisionError,
    raise_error,
)


RUN_REF_FIXED_TYPE_NAMES = (
    "RepositoryRevisionId",
    "WorkspaceEntryDelta",
    "NormalizedTextDiffEntry",
    "NormalizedWorkspaceDiff",
    "DeclaredWorkspaceArtifact",
    "WorkspaceDelta",
    "RunRefAccounting",
)
_COMPILER_SPAN = SourceSpan(
    start=SourcePosition(
        path="<compiler:run-ref-types>", line=1, column=1, offset=0
    ),
    end=SourcePosition(
        path="<compiler:run-ref-types>", line=1, column=1, offset=0
    ),
)


@dataclass(frozen=True)
class RunRefSiteMetadata:
    """Compiler-owned result carrier metadata for one stable run-ref site."""

    generated_type_name: str
    site_digest: str
    expression_key: str
    type_signature: str
    value_type_ref: TypeRef
    input_types: tuple[tuple[str, TypeRef], ...]
    type_ref: RecordTypeRef
    compiler_owned_types: tuple[tuple[str, TypeRef], ...]
    # Workflow mode only: the site's type, `RunRefOutcome$<digest16>` with arms
    # COMPLETED (result <type_ref>) and FAILED (code, detail, accounting).
    outcome_type_ref: UnionTypeRef | None = None

    @property
    def site_type_ref(self) -> TypeRef:
        """The type of the run-ref expression itself."""

        return self.outcome_type_ref or self.type_ref


@dataclass(frozen=True)
class _RunRefTypecheckDetails:
    """Typed run-ref plus the summaries computed for its input expressions."""

    typed_expr: TypedExpr
    input_effect_summaries: tuple[EffectSummary, ...]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _type_identity(type_ref: TypeRef) -> object:
    if isinstance(type_ref, PrimitiveTypeRef):
        return ["primitive", type_ref.name, list(type_ref.allowed_values)]
    if isinstance(type_ref, PathTypeRef):
        return [
            "path",
            type_ref.name,
            type_ref.definition.kind,
            type_ref.definition.under,
            type_ref.definition.must_exist,
        ]
    if isinstance(type_ref, RecordTypeRef):
        return [
            "record",
            type_ref.name,
            [
                [field.name, _type_identity(type_ref.field_types[field.name])]
                for field in type_ref.definition.fields
            ],
        ]
    if isinstance(type_ref, UnionTypeRef):
        return [
            "union",
            type_ref.name,
            [
                [
                    variant.name,
                    [
                        [
                            field.name,
                            _type_identity(
                                type_ref.variant_field_types[variant.name][
                                    field.name
                                ]
                            ),
                        ]
                        for field in variant.fields
                    ],
                ]
                for variant in type_ref.definition.variants
            ],
        ]
    if isinstance(type_ref, OptionalTypeRef):
        return ["optional", _type_identity(type_ref.item_type_ref)]
    if isinstance(type_ref, ListTypeRef):
        return ["list", _type_identity(type_ref.item_type_ref)]
    if isinstance(type_ref, MapTypeRef):
        return [
            "map",
            _type_identity(type_ref.key_type_ref),
            _type_identity(type_ref.value_type_ref),
        ]
    if isinstance(type_ref, VariantCaseTypeRef):
        return ["variant-case", type_ref.union_name, type_ref.variant_name]
    if isinstance(type_ref, (WorkflowRefTypeRef, ProcRefTypeRef, TypeParamRef)):
        return [type(type_ref).__name__, type_ref.name]
    raise TypeError(f"unsupported run-ref type identity: {type(type_ref)!r}")


def _record_type(
    name: str,
    fields: tuple[tuple[str, TypeRef], ...],
) -> RecordTypeRef:
    definition = RecordDef(
        name=name,
        fields=tuple(
            RecordField(
                name=field_name,
                type_name=field_type.name,
                span=_COMPILER_SPAN,
            )
            for field_name, field_type in fields
        ),
        span=_COMPILER_SPAN,
    )
    return RecordTypeRef(
        name=name,
        definition=definition,
        field_types=dict(fields),
    )


def _union_type(
    name: str,
    variants: tuple[tuple[str, tuple[tuple[str, TypeRef], ...]], ...],
) -> UnionTypeRef:
    definition = UnionDef(
        name=name,
        variants=tuple(
            UnionVariant(
                name=variant_name,
                fields=tuple(
                    RecordField(name=field_name, type_name=field_type.name, span=_COMPILER_SPAN)
                    for field_name, field_type in fields
                ),
                span=_COMPILER_SPAN,
            )
            for variant_name, fields in variants
        ),
        span=_COMPILER_SPAN,
    )
    return UnionTypeRef(
        name=name,
        definition=definition,
        variant_field_types={variant_name: dict(fields) for variant_name, fields in variants},
    )


def _install_type(type_env, type_ref: TypeRef) -> None:
    compiler_owned_names = getattr(
        type_env,
        "_compiler_owned_type_names",
        None,
    )
    if compiler_owned_names is None:
        compiler_owned_names = set()
        type_env._compiler_owned_type_names = compiler_owned_names
    existing = type_env._type_refs.get(type_ref.name)
    if existing is None:
        type_env._type_refs[type_ref.name] = type_ref
        compiler_owned_names.add(type_ref.name)
        return
    if type_ref.name not in compiler_owned_names:
        raise TypecheckSessionStateCollisionError(
            f"run-ref compiler type name is already bound by non-compiler type {type_ref.name!r}"
        )
    if _type_identity(existing) != _type_identity(type_ref):
        raise TypecheckSessionStateCollisionError(
            f"run-ref compiler type collision for {type_ref.name!r}"
        )


def _validate_staged_type(type_env, type_ref: TypeRef) -> None:
    existing = type_env._type_refs.get(type_ref.name)
    if existing is None:
        return
    compiler_owned_names = getattr(
        type_env,
        "_compiler_owned_type_names",
        set(),
    )
    if type_ref.name not in compiler_owned_names:
        raise TypecheckSessionStateCollisionError(
            f"run-ref compiler type name is already bound by non-compiler type {type_ref.name!r}"
        )
    if _type_identity(existing) != _type_identity(type_ref):
        raise TypecheckSessionStateCollisionError(
            f"run-ref compiler type collision for {type_ref.name!r}"
        )


def compiler_run_ref_fixed_types(
    type_env,
) -> tuple[tuple[str, TypeRef], ...]:
    """Build and validate the fixed compiler-owned ``run-ref`` type vector."""

    def primitive(name: str) -> PrimitiveTypeRef:
        existing = type_env._type_refs.get(name)
        if (
            type(existing) is PrimitiveTypeRef
            and existing.name == name
            and existing.allowed_values == ()
        ):
            return existing
        raise TypecheckSessionStateCollisionError(
            f"run-ref requires target primitive {name!r}"
        )

    string_type = primitive("String")
    int_type = primitive("Int")
    bool_type = primitive("Bool")
    value_type = primitive("Value")
    run_id_type = primitive("RunId")
    optional_string = OptionalTypeRef("Optional[String]", string_type)

    repository_revision = _record_type(
        "RepositoryRevisionId",
        tuple(
            (name, string_type)
            for name in (
                "digest",
                "normalized_locator",
                "resolved_commit_sha",
                "materializer_version",
                "submodule_policy",
                "lfs_policy",
                "authored_setup_identity",
            )
        ),
    )
    entry_delta = _record_type(
        "WorkspaceEntryDelta",
        (
            ("path", string_type),
            ("kind", string_type),
            ("mode", int_type),
            ("size", int_type),
            ("old_sha256", optional_string),
            ("new_sha256", optional_string),
            ("link_target", optional_string),
        ),
    )
    text_diff = _record_type(
        "NormalizedTextDiffEntry",
        (
            ("path", string_type),
            ("text", string_type),
            ("truncated", bool_type),
            ("omitted_bytes", int_type),
        ),
    )
    normalized_diff = _record_type(
        "NormalizedWorkspaceDiff",
        (
            ("entries", ListTypeRef("List[NormalizedTextDiffEntry]", text_diff)),
            ("catalog_digest", string_type),
            ("truncated", bool_type),
            ("omitted_bytes", int_type),
            ("omitted_entries", int_type),
        ),
    )
    declared_artifact = _record_type(
        "DeclaredWorkspaceArtifact",
        (
            ("name", string_type),
            ("path", string_type),
            ("kind", string_type),
            ("mode", int_type),
            ("size", int_type),
            ("sha256", optional_string),
            ("link_target", optional_string),
        ),
    )
    workspace_delta = _record_type(
        "WorkspaceDelta",
        (
            ("base", repository_revision),
            ("changed_files", ListTypeRef("List[WorkspaceEntryDelta]", entry_delta)),
            ("deleted_files", ListTypeRef("List[WorkspaceEntryDelta]", entry_delta)),
            ("untracked_files", ListTypeRef("List[WorkspaceEntryDelta]", entry_delta)),
            ("normalized_diff", normalized_diff),
            (
                "declared_artifacts",
                ListTypeRef("List[DeclaredWorkspaceArtifact]", declared_artifact),
            ),
        ),
    )
    accounting = _record_type(
        "RunRefAccounting",
        (
            ("child_run_id", run_id_type),
            ("attempt_ordinal", int_type),
            ("terminal_status", string_type),
            ("elapsed_ms", int_type),
            ("setup_ms", int_type),
            ("compile_ms", int_type),
            ("provider_attempts", value_type),
            ("token_usage", value_type),
            ("cost", value_type),
        ),
    )
    fixed = (
        repository_revision,
        entry_delta,
        text_diff,
        normalized_diff,
        declared_artifact,
        workspace_delta,
        accounting,
    )
    for type_ref in fixed:
        _validate_staged_type(type_env, type_ref)
    return tuple((type_ref.name, type_ref) for type_ref in fixed)


def _expression_payload(expr: RunRefExpr) -> dict[str, object]:
    # The workflow-mode commit is a parent operand that WCC rebinds like the
    # inputs, so (like input values) it stays out of the expression key.
    workflow_mode = isinstance(expr.program, RunRefWorkflowProgram)
    commit = None if workflow_mode else expr.source.commit
    if isinstance(expr.program, RunRefBundleProgram):
        program = {"mode": "bundle", "workflow": expr.program.workflow_name}
    elif workflow_mode:
        policy = expr.program.policy
        program = {
            "mode": "workflow",
            "workflow": expr.program.workflow_name,
            "policy": {
                "image": policy.image,
                "network": policy.network,
                "limits": [list(row) for row in policy.limits],
            },
        }
    else:
        program = {
            "mode": "path",
            "path": expr.program.path,
            "entry": expr.program.entry_name,
        }
    return {
        "position": {
            "start": [expr.span.start.line, expr.span.start.column],
            "end": [expr.span.end.line, expr.span.end.column],
        },
        "form_path": list(expr.form_path),
        "source": {"repo": expr.source.repo, "commit": commit},
        "program": program,
        "setup": [
            {
                "argv": list(command.argv),
                "env": [[name, value] for name, value in command.env],
            }
            for command in expr.setup.commands
        ],
        "environment": expr.environment,
        "returns": expr.returns_type_name,
        "input_names": [name for name, _ in expr.inputs],
    }


def _register_result_metadata(
    expr: RunRefExpr,
    *,
    context,
    value_type,
    input_types: tuple[tuple[str, TypeRef], ...],
) -> RunRefSiteMetadata:
    fixed_types = compiler_run_ref_fixed_types(context.type_env)
    fixed_by_name = dict(fixed_types)
    expression_key = _sha256(_expression_payload(expr))
    type_payload = {
        "inputs": [
            [name, _type_identity(type_ref)] for name, type_ref in input_types
        ],
        "value": _type_identity(value_type),
    }
    type_signature = _sha256(type_payload)
    caller_identity = getattr(
        context.session_state.workflow_signature,
        "name",
        None,
    ) or "::".join(expr.form_path)
    site_digest = _sha256(
        {
            "caller": caller_identity,
            "expression": _expression_payload(expr),
            "types": type_payload,
        }
    )
    generated_name = f"RunRefResult${site_digest[:16]}"
    result_type = _record_type(
        generated_name,
        (
            ("value", value_type),
            ("workspace_delta", fixed_by_name["WorkspaceDelta"]),
            ("accounting", fixed_by_name["RunRefAccounting"]),
        ),
    )
    source_key = (context.type_env.module_name, expression_key)
    origin = context.session_state.run_ref_origins_by_source_key.setdefault(
        source_key,
        bytes.fromhex(_sha256(["run-ref-origin", *source_key])),
    )
    result_type = replace(result_type, run_ref_origin=(origin, input_types))
    _validate_staged_type(context.type_env, result_type)
    owned = (*fixed_types, (generated_name, result_type))
    outcome = None
    if isinstance(expr.program, RunRefWorkflowProgram):
        string_type = context.type_env._type_refs["String"]
        outcome = _union_type(
            f"RunRefOutcome${site_digest[:16]}",
            (
                ("COMPLETED", (("result", result_type),)),
                (
                    "FAILED",
                    (
                        ("code", string_type),
                        ("detail", string_type),
                        ("accounting", fixed_by_name["RunRefAccounting"]),
                    ),
                ),
            ),
        )
        _validate_staged_type(context.type_env, outcome)
        owned = (*owned, (outcome.name, outcome))
    metadata = RunRefSiteMetadata(
        generated_type_name=generated_name,
        site_digest=site_digest,
        expression_key=expression_key,
        type_signature=type_signature,
        value_type_ref=value_type,
        input_types=input_types,
        type_ref=result_type,
        compiler_owned_types=owned,
        outcome_type_ref=outcome,
    )
    existing = context.session_state.run_ref_metadata_by_name.get(generated_name)
    if existing is not None and not run_ref_metadata_equivalent(existing, metadata):
        raise TypecheckSessionStateCollisionError(
            f"run-ref metadata collision for {generated_name!r}"
        )
    metadata_by_signature = context.session_state.run_ref_metadata_by_expr_key.setdefault(
        expression_key,
        {},
    )
    existing = metadata_by_signature.get(type_signature)
    if existing is not None and not run_ref_metadata_equivalent(existing, metadata):
        raise TypecheckSessionStateCollisionError(
            f"run-ref expression metadata collision for {expression_key!r}"
        )
    context.session_state.run_ref_metadata_by_name[generated_name] = metadata
    metadata_by_signature[type_signature] = metadata
    return metadata


def run_ref_metadata_equivalent(left: object, right: object) -> bool:
    if not isinstance(left, RunRefSiteMetadata) or not isinstance(
        right,
        RunRefSiteMetadata,
    ):
        return False
    return (
        left.generated_type_name,
        left.site_digest,
        left.expression_key,
        left.type_signature,
        _type_identity(left.value_type_ref),
        tuple((name, _type_identity(type_ref)) for name, type_ref in left.input_types),
        _type_identity(left.type_ref),
        tuple(
            (name, _type_identity(type_ref))
            for name, type_ref in left.compiler_owned_types
        ),
    ) == (
        right.generated_type_name,
        right.site_digest,
        right.expression_key,
        right.type_signature,
        _type_identity(right.value_type_ref),
        tuple((name, _type_identity(type_ref)) for name, type_ref in right.input_types),
        _type_identity(right.type_ref),
        tuple(
            (name, _type_identity(type_ref))
            for name, type_ref in right.compiler_owned_types
        ),
    )


def metadata_for_run_ref_expr(
    expr: RunRefExpr,
    *,
    result_type,
    session_state,
) -> RunRefSiteMetadata | None:
    metadata = session_state.run_ref_metadata_by_name.get(
        getattr(result_type, "name", "")
    )
    if metadata is None:
        return None
    return metadata if metadata.expression_key == _sha256(_expression_payload(expr)) else None


def resolve_run_ref_site_metadata(
    expr: RunRefExpr,
    *,
    result_type: TypeRef,
    session_state,
) -> RunRefSiteMetadata:
    """Resolve one exact run-ref site while cross-checking both session indexes."""

    if not isinstance(expr, RunRefExpr):
        raise TypeError("run-ref metadata resolution requires RunRefExpr")
    if session_state is None:
        raise TypecheckSessionStateCollisionError(
            "run-ref metadata session is unavailable"
        )
    expression_key = _sha256(_expression_payload(expr))
    generated_name = getattr(result_type, "name", None)
    if not isinstance(generated_name, str) or not generated_name:
        raise TypecheckSessionStateCollisionError(
            "run-ref result type has no generated metadata identity"
        )
    named = session_state.run_ref_metadata_by_name.get(generated_name)
    if not isinstance(named, RunRefSiteMetadata):
        raise TypecheckSessionStateCollisionError(
            f"run-ref metadata is missing for {generated_name!r}"
        )
    if (
        named.expression_key != expression_key
        or named.generated_type_name != generated_name
        or _type_identity(named.type_ref) != _type_identity(result_type)
    ):
        raise TypecheckSessionStateCollisionError(
            f"run-ref named metadata is inconsistent for {generated_name!r}"
        )

    signature_rows = session_state.run_ref_metadata_by_expr_key.get(
        expression_key
    )
    if not isinstance(signature_rows, dict):
        raise TypecheckSessionStateCollisionError(
            f"run-ref expression metadata is missing for {generated_name!r}"
        )
    matching = tuple(
        candidate
        for signature, candidate in signature_rows.items()
        if (
            isinstance(signature, str)
            and isinstance(candidate, RunRefSiteMetadata)
            and signature == candidate.type_signature
            and candidate.generated_type_name == generated_name
            and _type_identity(candidate.type_ref) == _type_identity(result_type)
        )
    )
    if len(matching) != 1:
        raise TypecheckSessionStateCollisionError(
            f"run-ref expression metadata is ambiguous for {generated_name!r}"
        )
    if not run_ref_metadata_equivalent(named, matching[0]):
        raise TypecheckSessionStateCollisionError(
            f"run-ref metadata indexes disagree for {generated_name!r}"
        )
    return named


def resolve_unique_run_ref_site_metadata(
    expr: RunRefExpr,
    *,
    session_state,
    prefer_retained: bool = False,
    source_module: str | None = None,
) -> RunRefSiteMetadata:
    """Resolve the sole typed result for an expression during WCC inference."""

    if not isinstance(expr, RunRefExpr):
        raise TypeError("run-ref metadata resolution requires RunRefExpr")
    if session_state is None:
        raise TypecheckSessionStateCollisionError(
            "run-ref metadata session is unavailable during WCC inference"
        )
    expression_key = _sha256(_expression_payload(expr))
    retained = expr.run_ref_metadata
    if prefer_retained and retained is not None:
        if not isinstance(retained, RunRefSiteMetadata):
            raise TypecheckSessionStateCollisionError(
                "run-ref expression carries invalid retained metadata"
            )
        if (
            not isinstance(retained.site_digest, str)
            or len(retained.site_digest) != 64
            or any(char not in "0123456789abcdef" for char in retained.site_digest)
            or retained.expression_key != expression_key
            or retained.generated_type_name
            != f"RunRefResult${retained.site_digest[:16]}"
        ):
            raise TypecheckSessionStateCollisionError(
                "run-ref retained metadata does not match its expression identity"
            )
        type_payload = {
            "inputs": [
                [name, _type_identity(type_ref)]
                for name, type_ref in retained.input_types
            ],
            "value": _type_identity(retained.value_type_ref),
        }
        if (
            retained.type_signature != _sha256(type_payload)
            or retained.type_ref.name != retained.generated_type_name
            or retained.type_ref.field_types.get("value")
            is not retained.value_type_ref
        ):
            raise TypecheckSessionStateCollisionError(
                "run-ref retained metadata has inconsistent checked type facts"
            )
        outcome = retained.outcome_type_ref
        if outcome is not None and (
            outcome.name != f"RunRefOutcome${retained.site_digest[:16]}"
            or set(outcome.variant_field_types) != {"COMPLETED", "FAILED"}
            or outcome.variant_field_types["COMPLETED"].get("result") is not retained.type_ref
        ):
            raise TypecheckSessionStateCollisionError(
                "run-ref retained outcome union does not match its site"
            )
        origin = retained.type_ref.run_ref_origin
        if (
            not isinstance(origin, tuple)
            or len(origin) != 2
            or not isinstance(origin[1], tuple)
            or len(origin[1]) != len(retained.input_types)
            or any(
                actual_name != expected_name or actual_ref is not expected_ref
                for (actual_name, actual_ref), (expected_name, expected_ref)
                in zip(origin[1], retained.input_types)
            )
        ):
            raise TypecheckSessionStateCollisionError(
                "run-ref retained metadata lost its exact input type origins"
            )
        if source_module is not None:
            origin_is_current = (
                session_state.run_ref_origins_by_source_key.get(
                    (source_module, expression_key)
                )
                == origin[0]
            )
        else:
            origin_is_current = any(
                key[1] == expression_key and token == origin[0]
                for key, token in (
                    session_state.run_ref_origins_by_source_key.items()
                )
            )
        if not origin_is_current:
            raise TypecheckSessionStateCollisionError(
                "run-ref retained metadata has no matching source-origin token"
            )
        return retained
    signature_rows = session_state.run_ref_metadata_by_expr_key.get(
        expression_key
    )
    if not isinstance(signature_rows, dict):
        raise TypecheckSessionStateCollisionError(
            "run-ref expression metadata is missing during WCC inference"
        )
    candidates = tuple(
        candidate
        for signature, candidate in signature_rows.items()
        if (
            isinstance(signature, str)
            and isinstance(candidate, RunRefSiteMetadata)
            and signature == candidate.type_signature
        )
    )
    if len(candidates) != 1:
        raise TypecheckSessionStateCollisionError(
            "run-ref expression metadata is ambiguous during WCC inference"
        )
    return resolve_run_ref_site_metadata(
        expr,
        result_type=candidates[0].type_ref,
        session_state=session_state,
    )


def register_all_known_run_ref_types(type_env, *, session_state) -> None:
    """Hydrate another type environment with every known run-ref carrier."""

    staged: dict[str, TypeRef] = {}
    for metadata in session_state.run_ref_metadata_by_name.values():
        for type_name, type_ref in metadata.compiler_owned_types:
            existing = staged.get(type_name)
            if existing is not None and _type_identity(existing) != _type_identity(
                type_ref
            ):
                raise TypecheckSessionStateCollisionError(
                    f"ambiguous staged run-ref compiler type {type_name!r}"
                )
            staged[type_name] = type_ref
    for type_ref in staged.values():
        _validate_staged_type(type_env, type_ref)
    for type_ref in staged.values():
        _install_type(type_env, type_ref)


def known_run_ref_type(type_name: str, *, session_state) -> TypeRef | None:
    """Return one staged run-ref compiler type without mutating a type env."""

    matched: TypeRef | None = None
    for metadata in session_state.run_ref_metadata_by_name.values():
        for known_name, type_ref in metadata.compiler_owned_types:
            if known_name != type_name:
                continue
            if matched is not None and _type_identity(matched) != _type_identity(
                type_ref
            ):
                raise TypecheckSessionStateCollisionError(
                    f"ambiguous staged run-ref compiler type {type_name!r}"
                )
            matched = type_ref
    return matched


def _require_transportable(
    type_ref, *, expr, role: str, type_env, code: str = "workflow_boundary_type_invalid"
) -> None:
    # Import lazily: contracts owns workflow-signature projection and therefore
    # reaches this dispatch module through the workflow compiler at import time.
    from .contracts import is_transportable_result_type

    if is_transportable_result_type(type_ref, type_env=type_env) and (
        code == "workflow_boundary_type_invalid" or not _carries_authority(type_ref)
    ):
        return
    raise_error(
        f"`run-ref` {role} type `{type_ref.name}` is not transportable",
        code=code,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _type_leaves(type_ref, seen=None):
    """Yield every nested TypeRef of one type, records and unions included."""

    seen = set() if seen is None else seen
    if id(type_ref) in seen:
        return
    seen.add(id(type_ref))
    yield type_ref
    if isinstance(type_ref, RecordTypeRef):
        children = tuple(type_ref.field_types.values())
    elif isinstance(type_ref, UnionTypeRef):
        children = tuple(
            field_type
            for fields in type_ref.variant_field_types.values()
            for field_type in fields.values()
        )
    elif isinstance(type_ref, (OptionalTypeRef, ListTypeRef)):
        children = (type_ref.item_type_ref,)
    elif isinstance(type_ref, MapTypeRef):
        children = (type_ref.key_type_ref, type_ref.value_type_ref)
    else:
        children = ()
    for child in children:
        yield from _type_leaves(child, seen)


def _carries_authority(type_ref) -> bool:
    """Whether a value of this type would carry parent authority into a child."""

    from .context_types import is_contextual_type, is_fixed_context_type

    return any(
        isinstance(leaf, (ProcRefTypeRef, WorkflowRefTypeRef))
        or (isinstance(leaf, PrimitiveTypeRef) and leaf.name in {"Provider", "Prompt"})
        or is_contextual_type(leaf)
        or is_fixed_context_type(leaf)
        for leaf in _type_leaves(type_ref)
    )


def _typecheck_mode_one(expr, *, context, recurse):
    if context.workflow_catalog is None:
        raise TypeError("workflow_catalog is required for bundle-mode run-ref")
    confined = isinstance(expr.program, RunRefWorkflowProgram)
    transport_code = (
        "run_ref_child_transport_unsupported"
        if confined
        else "workflow_boundary_type_invalid"
    )
    signature = context.workflow_catalog.signatures_by_name.get(
        expr.program.workflow_name
    )
    if signature is None:
        mode = "confined workflow-mode" if confined else "bundle"
        raise_error(
            f"unknown run-ref {mode} workflow `{expr.program.workflow_name}`",
            code="workflow_call_unknown",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )

    hidden_boundary_state = (
        signature.private_compatibility_bridge_types
        or signature.hidden_context_requirements
        or signature.hidden_context_ambiguities
    )
    if hidden_boundary_state:
        raise_error(
            "run-ref bundle workflows must expose a complete public-only input signature",
            code=transport_code if confined else "workflow_signature_mismatch",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )

    expected_inputs = dict(signature.params)
    defaulted = frozenset(signature.param_defaults)
    seen: set[str] = set()
    typed_inputs = []
    input_effects = []
    input_types = []
    for name, value_expr in expr.inputs:
        if name in seen:
            raise_error(
                f"duplicate run-ref input `:{name}`",
                code="workflow_signature_mismatch",
                span=value_expr.span,
                form_path=value_expr.form_path,
                expansion_stack=value_expr.expansion_stack,
            )
        seen.add(name)
        expected = expected_inputs.get(name)
        if expected is None:
            raise_error(
                f"run-ref input `:{name}` does not match the child signature",
                code="workflow_signature_mismatch",
                span=value_expr.span,
                form_path=value_expr.form_path,
                expansion_stack=value_expr.expansion_stack,
            )
        _require_transportable(
            expected,
            expr=value_expr,
            role=f"input `:{name}`",
            type_env=context.type_env,
            code=transport_code,
        )
        typed = recurse(value_expr, expected_type=expected)
        _require_transportable(
            typed.type_ref,
            expr=value_expr,
            role=f"input `:{name}`",
            type_env=context.type_env,
            code=transport_code,
        )
        if not type_refs_compatible(expected, typed.type_ref):
            raise_error(
                f"run-ref input `:{name}` expected `{expected.name}` but got `{typed.type_ref.name}`",
                code="type_mismatch",
                span=value_expr.span,
                form_path=value_expr.form_path,
                expansion_stack=value_expr.expansion_stack,
            )
        typed_inputs.append((name, typed.expr))
        input_effects.append(typed.effect_summary)
        input_types.append((name, typed.type_ref))

    missing = [
        name
        for name in expected_inputs
        if name not in seen and name not in defaulted
    ]
    if missing:
        raise_error(
            f"run-ref is missing required child input `:{missing[0]}`",
            code="workflow_signature_mismatch",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    _require_transportable(
        signature.return_type_ref,
        expr=expr,
        role="child return",
        type_env=context.type_env,
        code=transport_code,
    )
    if confined:
        _refuse_unexportable_child_result(expr, signature)
    return (
        signature.return_type_ref,
        tuple(typed_inputs),
        tuple(input_effects),
        tuple(input_types),
    )


_FORBIDDEN_CHILD_ATOMS = (
    RunsRefEffect,
    RunsTrialEffect,
    HostInputEffect,
    LiveSupervisionEffect,
    LivePeerMessagingEffect,
    UpdatesStateEffect,
    MovesResourceEffect,
    UpdatesLedgerEffect,
    CapturesSnapshotEffect,
    MaterializesPointerEffect,
)
_PROVIDER_ATOMS = (UsesProviderEffect, LiveSupervisionEffect, LivePeerMessagingEffect)
# Effect forms a confined child cannot perform (design: nested run-ref, trial,
# parallel effects, human input, sessions/context, resources).  The language
# has no dynamic-evaluation form at this target, so there is none to list.
_FORBIDDEN_CHILD_FORMS = {
    ex.RunRefExpr: "nested run-ref",
    ex.TrialExpr: "trial",
    ex.WithLiveProvidersExpr: "parallel live providers",
    ex.WithLiveProviderPeersExpr: "parallel live provider peers",
    ex.RequestInputExpr: "human input",
    ex.WithPhaseExpr: "phase context",
    ex.RunProviderPhaseExpr: "provider session phase",
    ex.ResumeOrStartExpr: "session resume",
    ex.ProduceOneOfExpr: "provider session selection",
    ex.ResourceTransitionExpr: "resource transition",
    ex.MaterializeViewExpr: "resource view",
    ex.FinalizeSelectedItemExpr: "resource finalization",
}


def _child_form_refusal(node, *, network_none: bool) -> tuple[str, str] | None:
    """Return (code, reason) when one reachable child form is refused."""

    if isinstance(node, ex.ProviderBundlePathExpr):
        return "run_ref_child_transport_unsupported", "provider-bundle-path"
    reason = _FORBIDDEN_CHILD_FORMS.get(type(node))
    if isinstance(node, ex.ListMapEffectExpr) and node.parallel_count is not None:
        reason = "parallel list/map-effect"
    if isinstance(node, ex.ProviderResultExpr) and (
        node.context_expr is not None
        or node.capture_context is not None
        or node.session_artifact is not None
    ):
        reason = "provider session/context"
    if reason is None and network_none and isinstance(node, ex.ProviderResultExpr):
        reason = "a provider effect under :network :none"
    return None if reason is None else ("run_ref_environment_effect_unsupported", reason)


def _refuse_unexportable_child_result(expr, signature) -> None:
    """Refuse a confined child whose result path cannot be exported (site-local)."""

    if any(
        isinstance(leaf, PathTypeRef) and not leaf.definition.must_exist
        for leaf in _type_leaves(signature.return_type_ref)
    ):
        raise_error(
            f"confined `run-ref` child `{expr.program.workflow_name}` returns a "
            "`:must-exist false` path",
            code="run_ref_child_transport_unsupported",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )


def _typed_body(definition):
    typed_body = definition.typed_body
    return getattr(typed_body, "expr", typed_body)


def _callees(body, program):
    """Yield the (kind, name) of every workflow or named procedure one body reaches directly."""

    for node in walk_expr(body):
        if isinstance(node, ex.CallExpr):
            yield "workflow", node.callee_name
        elif isinstance(node, ex.WorkflowRefLiteralExpr):
            yield "workflow", node.target_name
        # Local let-proc bodies are inline in this body; named and
        # specialized (hook) procedures live in the program table.
        elif isinstance(node, ex.ProcedureCallExpr) and node.callee_name in program.procedures:
            yield "procedure", node.callee_name
        elif isinstance(node, ex.ProcRefLiteralExpr) and node.target_name in program.procedures:
            yield "procedure", node.target_name


def _reachable(roots, program, *, strict: bool = True):
    """Yield (effect summary, typed body) of every callable reachable from `roots`.

    `strict` refuses an unresolved workflow callee; otherwise it is skipped,
    because only workflow-bundle and lookup-alias callees resolve outside the
    program's workflow and imported-program tables.
    """

    pending, seen = list(roots), set()
    while pending:
        kind, callee = pending.pop()
        if (kind, callee) in seen:
            continue
        seen.add((kind, callee))
        table = program.workflows if kind == "workflow" else program.procedures
        definition = table.get(callee)
        imported = program.imported_programs.get(callee) if kind == "workflow" else None
        if definition is None and imported is not None:
            # A call by import alias runs that compiled program's entry.
            yield from _reachable([("workflow", imported.entry.definition.name)], imported, strict=strict)
            continue
        if definition is None and not strict and kind == "workflow":
            continue
        if definition is None:
            raise TypecheckSessionStateCollisionError(
                f"confined run-ref check reaches unresolved {kind} {callee!r}"
            )
        summary = getattr(definition, "transitive_effect_summary", None) or definition.effect_summary
        yield summary, _typed_body(definition)
        pending.extend(_callees(_typed_body(definition), program))


def _reachable_child(name: str, program):
    return _reachable([("workflow", name)], program)


def _is_confined_site(node) -> bool:
    return isinstance(node, RunRefExpr) and isinstance(node.program, RunRefWorkflowProgram)


def _contains_confined_site(program) -> bool:
    """Whether a confined site exists in the program or any program it imports."""

    return any(
        _is_confined_site(node)
        for definition in (*program.workflows.values(), *program.procedures.values())
        for node in walk_expr(_typed_body(definition))
    ) or any(_contains_confined_site(imported) for imported in program.imported_programs.values())


def _map_frame_body(node):
    """Return the body of a `list/map-effect` frame, serial or parallel, else None."""

    if isinstance(node, ex.ListMapEffectExpr):
        return node.body_expr
    # A serial `list/map-effect` is typed as a synthetic loop stamped with this
    # exhaustion code (typecheck_structural_values); authored loops never carry it.
    if isinstance(node, ex.LoopRecurExpr) and node.exhaustion_diagnostic_code == "list_map_effect_cap_exceeded":
        return node.body_expr
    return None


def _refuse_confined_site_in_map_frame(body, program) -> None:
    """Ruling P12: no confined site in a `list/map-effect` body, directly or through calls."""

    bodies = (body, *(reached for _, reached in _reachable(_callees(body, program), program, strict=False)))
    site = next((node for row in bodies for node in walk_expr(row) if _is_confined_site(node)), None)
    if site is not None:
        raise_error(
            f"confined `run-ref` child `{site.program.workflow_name}` is not permitted in a "
            "`list/map-effect` body",
            code="run_ref_placement_invalid",
            span=body.span,
            form_path=body.form_path,
            expansion_stack=body.expansion_stack,
        )


def _child_refusal(site, program) -> tuple[str, str] | None:
    network_none = site.program.policy.network == "none"
    for summary, body in _reachable_child(site.program.workflow_name, program):
        for effect in (*summary.direct_effects, *summary.transitive_effects):
            if isinstance(effect, _FORBIDDEN_CHILD_ATOMS):
                return "run_ref_environment_effect_unsupported", f"the effect {type(effect).__name__}"
            if network_none and isinstance(effect, _PROVIDER_ATOMS):
                return "run_ref_environment_effect_unsupported", "a provider effect under :network :none"
        for node in walk_expr(body):
            refusal = _child_form_refusal(node, network_none=network_none)
            if refusal is not None:
                return refusal
    return None


def refuse_unsupported_confined_children(program) -> None:
    """Refuse every confined run-ref site whose child reaches an unsupported effect,
    and every confined site placed in a `list/map-effect` frame (Ruling P12).

    Runs over a finished typed program (workflows and procedures typed, effect
    summaries at their fixpoint), so the walk follows workflow calls, procedure
    calls and procedure-reference hooks transitively, local and imported.
    """

    if not _contains_confined_site(program):
        return
    for definition in (*program.workflows.values(), *program.procedures.values()):
        for site in walk_expr(_typed_body(definition)):
            frame_body = _map_frame_body(site)
            if frame_body is not None:
                _refuse_confined_site_in_map_frame(frame_body, program)
            if not _is_confined_site(site):
                continue
            refusal = _child_refusal(site, program)
            if refusal is not None:
                raise_error(
                    f"confined `run-ref` child `{site.program.workflow_name}` uses {refusal[1]}",
                    code=refusal[0],
                    span=site.span,
                    form_path=site.form_path,
                    expansion_stack=site.expansion_stack,
                )


def _typecheck_commit(expr, *, context, recurse):
    """Type the parent `:commit` operand as one pure String."""

    commit = expr.source.commit
    string_type = context.type_env._type_refs["String"]
    typed = recurse(commit, expected_type=string_type)
    if not type_refs_compatible(string_type, typed.type_ref):
        raise_error(
            f"run-ref `:commit` expected `String` but got `{typed.type_ref.name}`",
            code="type_mismatch",
            span=commit.span,
            form_path=commit.form_path,
            expansion_stack=commit.expansion_stack,
        )
    if typed.effect_summary.direct_effects or typed.effect_summary.transitive_effects:
        raise_error(
            "run-ref `:commit` must be a pure expression",
            code="effect_not_permitted",
            span=commit.span,
            form_path=commit.form_path,
            expansion_stack=commit.expansion_stack,
        )
    return typed


def _typecheck_mode_two(expr, *, context, recurse):
    assert isinstance(expr.program, RunRefPathProgram)
    if expr.returns_type_name is None:
        value_type = context.type_env.resolve_type(
            "Value",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            session_state=context.session_state,
        )
    else:
        value_type = context.type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            session_state=context.session_state,
        )
    _require_transportable(
        value_type,
        expr=expr,
        role="return refinement",
        type_env=context.type_env,
    )

    seen: set[str] = set()
    typed_inputs = []
    input_effects = []
    input_types = []
    for name, value_expr in expr.inputs:
        if name in seen:
            raise_error(
                f"duplicate run-ref input `:{name}`",
                code="workflow_signature_mismatch",
                span=value_expr.span,
                form_path=value_expr.form_path,
                expansion_stack=value_expr.expansion_stack,
            )
        seen.add(name)
        typed = recurse(value_expr)
        _require_transportable(
            typed.type_ref,
            expr=value_expr,
            role=f"input `:{name}`",
            type_env=context.type_env,
        )
        typed_inputs.append((name, typed.expr))
        input_effects.append(typed.effect_summary)
        input_types.append((name, typed.type_ref))
    return value_type, tuple(typed_inputs), tuple(input_effects), tuple(input_types)


def _typecheck_run_ref_expr_with_details(
    expr,
    *,
    context,
    recurse,
    typed_factory,
) -> _RunRefTypecheckDetails:
    """Type one run-ref and retain its already-computed input summaries."""

    typed_expr = expr
    if isinstance(expr.program, RunRefWorkflowProgram):
        commit = _typecheck_commit(expr, context=context, recurse=recurse)
        typed_expr = replace(expr, source=replace(expr.source, commit=commit.expr))
    if isinstance(expr.program, (RunRefBundleProgram, RunRefWorkflowProgram)):
        value_type, typed_inputs, input_effects, input_types = _typecheck_mode_one(
            expr,
            context=context,
            recurse=recurse,
        )
        effect_subject = expr.program.workflow_name
    else:
        value_type, typed_inputs, input_effects, input_types = _typecheck_mode_two(
            expr,
            context=context,
            recurse=recurse,
        )
        effect_subject = expr.program.entry_name

    run_effect = effect_summary_from_direct(
        direct_effects=(
            RunsRefEffect(subject=(effect_subject,)),
        )
    )
    typed_expr = replace(typed_expr, inputs=typed_inputs)
    metadata = _register_result_metadata(
        typed_expr,
        context=context,
        value_type=value_type,
        input_types=input_types,
    )
    typed_expr = typed_factory(
        expr=replace(typed_expr, run_ref_metadata=metadata),
        type_ref=metadata.site_type_ref,
        effect=merge_effect_summaries(*input_effects, run_effect),
    )
    return _RunRefTypecheckDetails(
        typed_expr=typed_expr,
        input_effect_summaries=input_effects,
    )


def typecheck_run_ref_expr(expr, *, context, recurse, typed_factory):
    """Type one isolated run-ref without registering it as a live form."""

    return _typecheck_run_ref_expr_with_details(
        expr,
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    ).typed_expr
