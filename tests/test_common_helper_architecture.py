from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMMON_CANONICAL_MODULE = "orchestrator._common.canonical"
COMMON_CANONICAL_PATH = REPO_ROOT / "orchestrator/_common/canonical.py"
COMMON_VALIDATION_MODULE = "orchestrator._common.validation"
COMMON_VALIDATION_PATH = REPO_ROOT / "orchestrator/_common/validation.py"
COMMON_STATUS_PATH = REPO_ROOT / "orchestrator/_common/status.py"


@dataclass(frozen=True)
class AdmittedHelperSurface:
    path: str
    symbols: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()


# The reviewed component plan's complete admitted production-path census is
# frozen here. Each task activates only its own category's structural checks.
ADMITTED_HELPER_MANIFEST = {
    "canonical": (
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/lexical_checkpoints.py",
            ("canonical_json_dumps", "_sha256_json"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/lexical_checkpoint_restore.py",
            ("canonical_json_dumps", "_sha256_text", "_sha256_json"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py",
            ("canonical_json_dumps", "_sha256_text", "_sha256_json"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/lexical_checkpoint_transition_resume.py",
            ("canonical_json_dumps", "sha256_json"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/build_artifacts.py",
            patterns=(
                "ast:inline_prefixed_sha256_of_canonical_json:utf8:count=4",
                "import:relative.lexical_checkpoints.canonical_json_dumps",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py",
            patterns=(
                "import:relative.lexical_checkpoints.canonical_json_dumps",
            ),
        ),
    ),
    "provider_scalars": (
        AdmittedHelperSurface(
            "orchestrator/providers/interactive_terminal.py",
            ("_nonempty",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_attempts.py",
            ("_closed_mapping", "_nonempty_string", "_ordinary_integer"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/prompt_identity.py",
            ("_closed", "_integer", "_nonempty_string"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/prompt_dependency_evidence.py",
            ("_closed", "_integer", "_text"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_supervision/bindings.py",
            ("_nonempty",),
            (
                "ast:compact_ascii_json@"
                "WorkflowProviderSupervisionBindings.allocate_attempt."
                "compose_final_prompt:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_supervision/contracts.py",
            patterns=(
                "ast:compact_ascii_json@derive_result_bundle_contract:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_supervision/models.py",
            ("_closed_mapping", "_nonempty_string", "_canonical_json"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_supervision/paths.py",
            ("_closed_mapping", "_nonempty_string"),
            (
                "ast:compact_ascii_json@"
                "ProviderSupervisionPaths.canonical_json:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_supervision/directive.py",
            (
                "ProviderSteeringDirectiveTypeDescriptor.canonical_json",
                "ProviderSteeringDirective.canonical_json",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/bindings.py",
            ("_nonempty",),
            (
                "ast:compact_ascii_json@"
                "WorkflowProviderPeerGroupBindings._publish_terminal_evidence:"
                "count=2",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/ledger.py",
            (
                "_canonical_row_bytes",
                "_nonempty_string",
                "_positive_int",
                "_nonnegative_int",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/models.py",
            ("_closed", "_nonempty", "_positive_integer"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/paths.py",
            (
                "_closed_mapping",
                "_nonempty_string",
                "_positive_int",
                "_canonical_json",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/protocol.py",
            ("_canonical_frame", "_nonempty"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/coordinator.py",
            ("ProviderPeerGroupCoordinator._canonical_request",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_phased_delivery/bindings.py",
            ("_canonical_sha256",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_phased_delivery/models.py",
            ("_canonical_sha256",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_phased_delivery/frames.py",
            ("_canonical_json_bytes",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_phased_delivery/ledger.py",
            ("_canonical_jsonl",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_phased_delivery/protocol.py",
            ("_canonical",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_phased_delivery/coordinator.py",
            patterns=(
                "ast:compact_ascii_json@_close_projection.submit_keys:count=1",
            ),
        ),
    ),
    "status": (
        AdmittedHelperSurface(
            "orchestrator/providers/session_transport.py",
            ("SessionIdentitySnapshot",),
        ),
        AdmittedHelperSurface(
            "orchestrator/providers/executor.py",
            patterns=(
                "ast:session_snapshot_eligibility_ladder@"
                "ProviderExecutor._execute_controlled_invocation."
                "_emit_assistant_text:count=1",
                "ast:session_snapshot_eligibility_ladder@"
                "ProviderExecutor._execute_session_invocation."
                "_emit_assistant_text:count=1",
                "ast:session_snapshot_eligibility_ladder@"
                "ProviderExecutor._stream_codex_jsonl_chunk."
                "_emit_if_valid:count=1",
                "ast:session_snapshot_eligibility_ladder@"
                "ProviderExecutor._stream_codex_jsonl_chunk.post_feed:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/state.py",
            patterns=(
                "ast:literal_type_alias@StateStatus:"
                "running|suspended|completed|failed",
                "ast:literal_type_alias@StepStatus:"
                "pending|running|completed|failed|skipped",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/cli/commands/resume.py",
            patterns=(
                "ast:status_membership@"
                "_resume_workflow_with_writer_lock_held:"
                "completed|skipped:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/resume_planner.py",
            ("ResumePlanner.entry_is_terminal",),
            (
                "ast:step_settled_membership@"
                "ResumePlanner._interrupted_provider_result_relation:"
                "completed|failed|skipped:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/call_frame_state.py",
            patterns=(
                "ast:run_terminal_membership@"
                "_CallFrameStateManager._snapshot:"
                "completed|failed:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/executor.py",
            patterns=(
                "ast:step_settled_membership@"
                "WorkflowExecutor._reconstruct_legacy_interrupted_provider_guard:"
                "completed|failed|skipped:count=1",
                "ast:step_settled_membership@"
                "WorkflowExecutor._interrupted_provider_rerun_context:"
                "completed|failed|skipped:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/loops.py",
            patterns=(
                "ast:step_settled_membership@"
                "LoopExecutor.resume_for_each_state:"
                "completed|failed|skipped:count=1",
                "ast:step_settled_membership@"
                "LoopExecutor.typed_resume_for_each_state:"
                "completed|failed|skipped:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/prompt_dependency_evidence.py",
            patterns=(
                "ast:run_terminal_membership@validate_terminal_evidence:"
                "completed|failed:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/lexical_checkpoints.py",
            patterns=(
                "ast:run_terminal_membership@assert_runtime_shadow_emission:"
                "completed|failed:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/observability/report.py",
            patterns=(
                "ast:step_settled_membership@_coerce_step_status:"
                "completed|failed|skipped:count=2",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/monitor/classifier.py",
            patterns=(
                "ast:run_terminal_membership@_refresh_terminal_state:"
                "completed|failed:count=1",
            ),
        ),
    ),
    "timeout": (
        AdmittedHelperSurface(
            "orchestrator/providers/types.py",
            patterns=(
                "ast:finite_positive_timeout@"
                "PreparedProviderPolicy.__post_init__.timeout_sec:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/providers/interactive_terminal.py",
            patterns=(
                "ast:finite_positive_timeout@"
                "InteractiveTerminalTurnQueueAdapter.__init__."
                "poll_interval_sec:count=1",
                "ast:finite_positive_timeout@"
                "InteractiveTerminalTurnQueueAdapter.__init__."
                "operation_timeout_sec:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/models.py",
            patterns=(
                "ast:finite_positive_timeout@"
                "PeerMemberRuntimeBinding.__post_init__.timeout_sec:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/protocol.py",
            patterns=(
                "ast:finite_positive_timeout@"
                "PeerProtocolListener.receive_event.timeout_sec:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_phased_delivery/runtime_bindings.py",
            patterns=(
                "ast:finite_positive_timeout@"
                "_WorkflowPhasedProviderAttemptBindings."
                "derive_attempt_deadline.timeout:count=1",
            ),
        ),
    ),
    "atomic": (
        AdmittedHelperSurface(
            "orchestrator/state_locking.py",
            ("durable_atomic_write",),
        ),
        AdmittedHelperSurface(
            "orchestrator/state.py",
            ("StateManager._write_state", "StateManager._write_json_atomic"),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/executor.py",
            (
                "WorkflowExecutor._atomic_write_text",
                "WorkflowExecutor._atomic_write_bytes",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_supervision/bindings.py",
            patterns=(
                "ast:executor_atomic_write_bytes@"
                "WorkflowProviderSupervisionBindings.allocate_attempt:"
                "turn.evidence_path|publication.payload:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_peer_group/bindings.py",
            patterns=(
                "ast:executor_atomic_write_bytes@"
                "WorkflowProviderPeerGroupBindings._write_no_replace:"
                "path|payload:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/steps/runtime.py",
            (
                "StepRuntime._atomic_write_bytes",
                "StepRuntime._atomic_write_text",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/steps/materialize_view.py",
            patterns=(
                "ast:runtime_atomic_write_bytes@execute_materialize_view:"
                "target_path|rendered:count=1",
                "ast:runtime_atomic_write_bytes@execute_materialize_view:"
                "evidence_path|evidence_bytes:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/steps/pure_projection.py",
            patterns=(
                "ast:runtime_atomic_write_text@execute_pure_projection:"
                "bundle_path|canonical_json_for_pure_value(bundle_record):count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/adjudication/utils.py",
            ("_atomic_write_text",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/provider_phased_delivery/runtime_bindings.py",
            patterns=(
                "ast:durable_atomic_write@"
                "_WorkflowPhasedProviderAttemptBindings."
                "_restore_frozen_candidate:path|item.content:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/observability/live_notes.py",
            ("LiveAgentNoteObserver._write_text_atomic",),
        ),
        AdmittedHelperSurface(
            "orchestrator/observability/summary.py",
            patterns=(
                "ast:path_replace@SummaryObserver._append_index_entry:"
                "tmp_path|index_path:count=1",
                "ast:path_replace@SummaryObserver._upsert_index_entry:"
                "tmp_path|index_path:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/monitor/ledger.py",
            patterns=(
                "ast:path_replace@NotificationLedger.save:"
                "tmp|self.path:count=1",
            ),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow/transition_executor.py",
            ("_write_pending_replay",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/adapters/apply_resource_transition.py",
            ("_write_output_bundle",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/adapters/reusable_phase_state_common.py",
            ("emit_structured_result",),
        ),
        AdmittedHelperSurface(
            "orchestrator/workflow_lisp/adapters/write_reusable_phase_state_v1.py",
            ("main",),
        ),
    ),
}

CANONICAL_COMMON_IMPORTS = {
    "orchestrator/workflow_lisp/lexical_checkpoints.py": {
        ("canonical_json_dumps", None),
        ("sha256_json", "_sha256_json"),
    },
    "orchestrator/workflow_lisp/lexical_checkpoint_restore.py": {
        ("sha256_json", "_sha256_json"),
    },
    "orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py": {
        ("sha256_json", "_sha256_json"),
    },
    "orchestrator/workflow_lisp/lexical_checkpoint_transition_resume.py": {
        ("sha256_json", None),
    },
    "orchestrator/workflow_lisp/build_artifacts.py": {
        ("sha256_json", None),
    },
    "orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py": {
        ("canonical_json_dumps", None),
    },
}

FORBIDDEN_LEXICAL_OWNER_IMPORTS = {
    "orchestrator/workflow_lisp/build_artifacts.py": {"canonical_json_dumps"},
    "orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py": {
        "canonical_json_dumps"
    },
}


def _module(path: str | Path) -> ast.Module:
    source_path = path if isinstance(path, Path) else REPO_ROOT / path
    return ast.parse(
        source_path.read_text(encoding="utf-8"),
        filename=str(source_path),
    )


def _top_level_function_names(path: str | Path) -> set[str]:
    return {
        node.name
        for node in _module(path).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _qualified_functions(path: str | Path) -> dict[str, ast.AST]:
    functions: dict[str, ast.AST] = {}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            qualified = ".".join((*self.scope, node.name))
            functions[qualified] = node
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            qualified = ".".join((*self.scope, node.name))
            functions[qualified] = node
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

    Visitor().visit(_module(path))
    return functions


def _imports_from(
    path: str,
    module_name: str,
    *,
    level: int = 0,
) -> set[tuple[str, str | None]]:
    return {
        (alias.name, alias.asname)
        for node in _module(path).body
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == module_name
            and node.level == level
        )
        for alias in node.names
    }


def _is_inline_prefixed_sha256_of_canonical_json(node: ast.AST) -> bool:
    if (
        not isinstance(node, ast.Call)
        or node.args
        or node.keywords
        or not isinstance(node.func, ast.Attribute)
        or node.func.attr != "hexdigest"
    ):
        return False
    digest_call = node.func.value
    if (
        not isinstance(digest_call, ast.Call)
        or len(digest_call.args) != 1
        or digest_call.keywords
        or not isinstance(digest_call.func, ast.Attribute)
        or digest_call.func.attr != "sha256"
        or not isinstance(digest_call.func.value, ast.Name)
        or digest_call.func.value.id != "hashlib"
    ):
        return False
    encoded = digest_call.args[0]
    if (
        not isinstance(encoded, ast.Call)
        or len(encoded.args) != 1
        or encoded.keywords
        or not isinstance(encoded.func, ast.Attribute)
        or encoded.func.attr != "encode"
        or not isinstance(encoded.args[0], ast.Constant)
        or encoded.args[0].value != "utf-8"
    ):
        return False
    canonical_call = encoded.func.value
    return (
        isinstance(canonical_call, ast.Call)
        and len(canonical_call.args) == 1
        and not canonical_call.keywords
        and isinstance(canonical_call.func, ast.Name)
        and canonical_call.func.id == "canonical_json_dumps"
    )


def _inline_prefixed_json_digest_count(path: str) -> int:
    return sum(
        _is_inline_prefixed_sha256_of_canonical_json(node)
        for node in ast.walk(_module(path))
    )


_VALIDATION_HELPER_NAMES = {
    "_closed",
    "_closed_mapping",
    "_integer",
    "_nonempty",
    "_nonempty_string",
    "_nonnegative_int",
    "_ordinary_integer",
    "_positive_int",
    "_positive_integer",
    "_text",
}
_CANONICAL_HELPER_NAMES = {
    "_canonical",
    "_canonical_frame",
    "_canonical_json",
    "_canonical_json_bytes",
    "_canonical_jsonl",
    "_canonical_request",
    "_canonical_row_bytes",
    "_canonical_sha256",
    "canonical_json",
}


def _retains_direct_validation_mechanics(node: ast.AST) -> bool:
    return any(
        isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Name)
        and candidate.func.id in {"isinstance", "set", "type"}
        for candidate in ast.walk(node)
    )


def _calls_common_validation(
    node: ast.AST,
    imported_names: set[str],
) -> bool:
    return any(
        isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Name)
        and candidate.func.id in imported_names
        for candidate in ast.walk(node)
    )


def _is_compact_ascii_json_call(node: ast.AST) -> bool:
    if (
        not isinstance(node, ast.Call)
        or not isinstance(node.func, ast.Attribute)
        or node.func.attr != "dumps"
        or not isinstance(node.func.value, ast.Name)
        or node.func.value.id != "json"
    ):
        return False
    keywords = {
        keyword.arg: keyword.value
        for keyword in node.keywords
        if keyword.arg is not None
    }
    separators = keywords.get("separators")
    return (
        isinstance(keywords.get("ensure_ascii"), ast.Constant)
        and keywords["ensure_ascii"].value is True
        and isinstance(keywords.get("sort_keys"), ast.Constant)
        and keywords["sort_keys"].value is True
        and isinstance(separators, (ast.Tuple, ast.List))
        and [
            element.value
            for element in separators.elts
            if isinstance(element, ast.Constant)
        ]
        == [",", ":"]
        and "default" not in keywords
    )


def _direct_compact_ascii_json_count(node: ast.AST) -> int:
    return sum(_is_compact_ascii_json_call(candidate) for candidate in ast.walk(node))


def _compact_ascii_pattern_target(pattern: str) -> str | None:
    prefix = "ast:compact_ascii_json@"
    if not pattern.startswith(prefix):
        return None
    return pattern[len(prefix) :].rsplit(":count=", 1)[0]


def _pattern_function_scope(
    functions: dict[str, ast.AST],
    target: str,
) -> ast.AST | None:
    candidate = target
    while candidate:
        node = functions.get(candidate)
        if node is not None:
            return node
        candidate = candidate.rpartition(".")[0]
    return None


def _literal_string_values(node: ast.AST) -> tuple[str, ...] | None:
    if not isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return None
    if not all(
        isinstance(element, ast.Constant)
        and isinstance(element.value, str)
        for element in node.elts
    ):
        return None
    return tuple(element.value for element in node.elts)


def _literal_type_alias_values(path: str, name: str) -> tuple[str, ...] | None:
    for node in _module(path).body:
        value: ast.AST | None = None
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
        ):
            value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            value = node.value
        if (
            isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Name)
            and value.value.id == "Literal"
        ):
            slice_node = value.slice
            if isinstance(slice_node, ast.Tuple):
                return _literal_string_values(slice_node)
            if (
                isinstance(slice_node, ast.Constant)
                and isinstance(slice_node.value, str)
            ):
                return (slice_node.value,)
    return None


def _status_pattern(
    pattern: str,
    kind: str,
) -> tuple[str, tuple[str, ...], int] | None:
    prefix = f"ast:{kind}@"
    if not pattern.startswith(prefix):
        return None
    target_and_values, count_text = pattern[len(prefix) :].rsplit(
        ":count=",
        1,
    )
    target, values_text = target_and_values.rsplit(":", 1)
    return target, tuple(values_text.split("|")), int(count_text)


def _literal_alias_pattern(
    pattern: str,
) -> tuple[str, tuple[str, ...]] | None:
    prefix = "ast:literal_type_alias@"
    if not pattern.startswith(prefix):
        return None
    name, values_text = pattern[len(prefix) :].split(":", 1)
    return name, tuple(values_text.split("|"))


def _membership_count(node: ast.AST, values: tuple[str, ...]) -> int:
    expected = frozenset(values)
    count = 0
    for candidate in _walk_function_scope(node):
        if (
            not isinstance(candidate, ast.Compare)
            or len(candidate.ops) != 1
            or not isinstance(candidate.ops[0], (ast.In, ast.NotIn))
            or len(candidate.comparators) != 1
        ):
            continue
        actual = _literal_string_values(candidate.comparators[0])
        if actual is not None and frozenset(actual) == expected:
            count += 1
    return count


def _walk_function_scope(node: ast.AST):
    """Walk one function body without admitting nested function bodies."""
    stack = list(reversed(list(ast.iter_child_nodes(node))))
    while stack:
        candidate = stack.pop()
        if isinstance(
            candidate,
            (
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.FunctionDef,
                ast.Lambda,
            ),
        ):
            continue
        yield candidate
        stack.extend(reversed(list(ast.iter_child_nodes(candidate))))


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


def _module_matches(
    *,
    imported_module: str | None,
    level: int,
    absolute_module: str,
) -> bool:
    if imported_module is None:
        return False
    if level == 0:
        return imported_module == absolute_module
    return imported_module == absolute_module.removeprefix("orchestrator.")


def _imported_symbol_names(
    path: str,
    module_name: str,
    symbol: str,
) -> set[str]:
    names: set[str] = set()
    for node in _module(path).body:
        if not isinstance(node, ast.ImportFrom) or not _module_matches(
            imported_module=node.module,
            level=node.level,
            absolute_module=module_name,
        ):
            continue
        for alias in node.names:
            if alias.name == symbol:
                names.add(alias.asname or alias.name)
    return names


def _imported_module_names(path: str, module_name: str) -> set[str]:
    names: set[str] = set()
    for node in _module(path).body:
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            if alias.name == module_name:
                names.add(alias.asname or alias.name)
    return names


def _imported_symbol_call_count(
    path: str,
    node: ast.AST,
    *,
    module_name: str,
    symbol: str,
) -> int:
    direct_names = _imported_symbol_names(path, module_name, symbol)
    qualified_names = {
        f"{module_alias}.{symbol}"
        for module_alias in _imported_module_names(path, module_name)
    }
    return sum(
        isinstance(candidate, ast.Call)
        and (
            _dotted_name(candidate.func) in direct_names
            or _dotted_name(candidate.func) in qualified_names
        )
        for candidate in _walk_function_scope(node)
    )


def _imported_owner_method_call_count(
    path: str,
    node: ast.AST,
    *,
    module_name: str,
    owner_symbol: str,
    method_name: str,
) -> int:
    owner_names = _imported_symbol_names(path, module_name, owner_symbol)
    qualified_names = {
        f"{owner_name}.{method_name}"
        for owner_name in owner_names
    }
    qualified_names.update(
        f"{module_alias}.{owner_symbol}.{method_name}"
        for module_alias in _imported_module_names(path, module_name)
    )
    return sum(
        isinstance(candidate, ast.Call)
        and _dotted_name(candidate.func) in qualified_names
        for candidate in _walk_function_scope(node)
    )


def _method_call_count(
    node: ast.AST,
    method_name: str,
    *,
    receiver_name: str | None = None,
) -> int:
    return sum(
        isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Attribute)
        and candidate.func.attr == method_name
        and (
            receiver_name is None
            or (
                isinstance(candidate.func.value, ast.Name)
                and candidate.func.value.id == receiver_name
            )
        )
        for candidate in _walk_function_scope(node)
    )


def _session_ladder_pattern(
    pattern: str,
) -> tuple[str, int] | None:
    prefix = "ast:session_snapshot_eligibility_ladder@"
    if not pattern.startswith(prefix):
        return None
    target, count_text = pattern[len(prefix) :].rsplit(":count=", 1)
    return target, int(count_text)


def _retains_session_snapshot_eligibility_ladder(node: ast.AST) -> bool:
    scoped_nodes = tuple(_walk_function_scope(node))
    names = {
        candidate.id
        for candidate in scoped_nodes
        if isinstance(candidate, ast.Name)
    }
    attributes = {
        candidate.attr
        for candidate in scoped_nodes
        if isinstance(candidate, ast.Attribute)
    }
    constants = {
        candidate.value
        for candidate in scoped_nodes
        if isinstance(candidate, ast.Constant)
        and isinstance(candidate.value, str)
    }
    return (
        _membership_count(node, ("ambiguous", "invalid")) >= 1
        and "expected_session_id" in names
        and "session_ids" in attributes
        and "unique" in constants
    )


def test_admitted_helper_manifest_is_exact_and_machine_addressable() -> None:
    assert set(ADMITTED_HELPER_MANIFEST) == {
        "canonical",
        "provider_scalars",
        "status",
        "timeout",
        "atomic",
    }
    for category, surfaces in ADMITTED_HELPER_MANIFEST.items():
        assert surfaces, category
        for surface in surfaces:
            assert surface.path.endswith(".py"), (category, surface)
            assert surface.symbols or surface.patterns, (category, surface.path)
            assert len(surface.symbols) == len(set(surface.symbols)), (
                category,
                surface.path,
            )
            assert len(surface.patterns) == len(set(surface.patterns)), (
                category,
                surface.path,
            )
            assert all(
                pattern.startswith(("ast:", "import:"))
                for pattern in surface.patterns
            ), (category, surface.path, surface.patterns)


def test_canonical_helpers_have_one_common_owner() -> None:
    findings: list[str] = []
    if not COMMON_CANONICAL_PATH.is_file():
        findings.append("missing orchestrator/_common/canonical.py")
    else:
        common_definitions = _top_level_function_names(COMMON_CANONICAL_PATH)
        missing = {"canonical_json_dumps", "sha256_json"} - common_definitions
        if missing:
            findings.append(f"common owner missing definitions: {sorted(missing)}")

    for surface in ADMITTED_HELPER_MANIFEST["canonical"][:4]:
        surviving = set(surface.symbols) & _top_level_function_names(surface.path)
        if surviving:
            findings.append(f"{surface.path} retains {sorted(surviving)}")

    for path, required_imports in CANONICAL_COMMON_IMPORTS.items():
        missing = required_imports - _imports_from(path, COMMON_CANONICAL_MODULE)
        if missing:
            findings.append(f"{path} missing common imports {sorted(missing)}")

    for path, forbidden_names in FORBIDDEN_LEXICAL_OWNER_IMPORTS.items():
        imported_names = {
            name
            for name, _alias in _imports_from(
                path,
                "lexical_checkpoints",
                level=1,
            )
        }
        surviving = forbidden_names & imported_names
        if surviving:
            findings.append(
                f"{path} retains accidental lexical imports {sorted(surviving)}"
            )

    build_artifacts_path = "orchestrator/workflow_lisp/build_artifacts.py"
    inline_digest_count = _inline_prefixed_json_digest_count(
        build_artifacts_path
    )
    if inline_digest_count:
        findings.append(
            f"{build_artifacts_path} retains {inline_digest_count} "
            "inline prefixed canonical-JSON digests"
        )

    assert not findings, "\n".join(findings)


def test_provider_scalar_helpers_use_common_mechanics() -> None:
    findings: list[str] = []
    if not COMMON_VALIDATION_PATH.is_file():
        findings.append("missing orchestrator/_common/validation.py")
    else:
        common_validation_definitions = _top_level_function_names(
            COMMON_VALIDATION_PATH
        )
        missing_validation = {
            "closed_mapping",
            "nonempty_string",
            "ordinary_integer",
        } - common_validation_definitions
        if missing_validation:
            findings.append(
                "common validation owner missing definitions: "
                f"{sorted(missing_validation)}"
            )

    common_canonical_definitions = _top_level_function_names(
        COMMON_CANONICAL_PATH
    )
    missing_canonical = {
        "compact_ascii_json_dumps",
        "sha256_compact_ascii_json",
    } - common_canonical_definitions
    if missing_canonical:
        findings.append(
            "common canonical owner missing provider definitions: "
            f"{sorted(missing_canonical)}"
        )

    for surface in ADMITTED_HELPER_MANIFEST["provider_scalars"]:
        qualified_functions = _qualified_functions(surface.path)
        imported_validation_names = {
            alias or name
            for name, alias in _imports_from(
                surface.path,
                COMMON_VALIDATION_MODULE,
            )
            if name
            in {"closed_mapping", "nonempty_string", "ordinary_integer"}
        }
        for symbol in surface.symbols:
            node = qualified_functions.get(symbol)
            if node is None:
                continue
            helper_name = symbol.rsplit(".", 1)[-1]
            if (
                helper_name in _VALIDATION_HELPER_NAMES
                and _retains_direct_validation_mechanics(node)
                and not _calls_common_validation(
                    node,
                    imported_validation_names,
                )
            ):
                findings.append(
                    f"{surface.path}:{symbol} retains direct validation mechanics"
                )
            elif helper_name in _CANONICAL_HELPER_NAMES:
                count = _direct_compact_ascii_json_count(node)
                if count:
                    findings.append(
                        f"{surface.path}:{symbol} retains {count} direct "
                        "compact ASCII JSON call(s)"
                    )

        for pattern in surface.patterns:
            target = _compact_ascii_pattern_target(pattern)
            if target is None:
                continue
            node = _pattern_function_scope(qualified_functions, target)
            if node is None:
                findings.append(
                    f"{surface.path}:{target} compact-JSON scope is missing"
                )
                continue
            count = _direct_compact_ascii_json_count(node)
            if count:
                findings.append(
                    f"{surface.path}:{target} retains {count} direct "
                    "compact ASCII JSON call(s)"
                )

    assert not findings, "\n".join(findings)


def test_status_helpers_have_one_common_owner() -> None:
    findings: list[str] = []
    if not COMMON_STATUS_PATH.is_file():
        findings.append("missing orchestrator/_common/status.py")
    else:
        common_definitions = _top_level_function_names(COMMON_STATUS_PATH)
        missing = {
            "is_run_terminal",
            "is_step_settled",
        } - common_definitions
        if missing:
            findings.append(
                f"common status owner missing definitions: {sorted(missing)}"
            )

    for surface in ADMITTED_HELPER_MANIFEST["status"]:
        qualified_functions = _qualified_functions(surface.path)
        if "SessionIdentitySnapshot" in surface.symbols:
            owner = qualified_functions.get(
                "SessionIdentitySnapshot.assistant_text_is_eligible"
            )
            if owner is None:
                findings.append(
                    f"{surface.path} missing "
                    "SessionIdentitySnapshot.assistant_text_is_eligible"
                )
            elif not _retains_session_snapshot_eligibility_ladder(owner):
                findings.append(
                    f"{surface.path}:SessionIdentitySnapshot."
                    "assistant_text_is_eligible lost its exact owned ladder"
                )
        if "ResumePlanner.entry_is_terminal" in surface.symbols:
            recursive_owner = qualified_functions.get(
                "ResumePlanner.entry_is_terminal"
            )
            scalar_owner = qualified_functions.get(
                "ResumePlanner.entry_status_is_terminal"
            )
            if recursive_owner is None:
                findings.append(
                    f"{surface.path} missing resume terminality owner"
                )
            elif (
                _method_call_count(
                    recursive_owner,
                    "entry_status_is_terminal",
                    receiver_name="self",
                )
                != 1
            ):
                findings.append(
                    f"{surface.path}:ResumePlanner.entry_is_terminal must "
                    "call its scalar owner exactly once"
                )
            if scalar_owner is None:
                findings.append(
                    f"{surface.path} missing "
                    "ResumePlanner.entry_status_is_terminal"
                )
            elif _membership_count(
                scalar_owner,
                ("completed", "skipped"),
            ) != 1:
                findings.append(
                    f"{surface.path}:ResumePlanner.entry_status_is_terminal "
                    "must retain the distinct completed|skipped rule"
                )

        for pattern in surface.patterns:
            alias_pattern = _literal_alias_pattern(pattern)
            if alias_pattern is not None:
                name, expected = alias_pattern
                actual = _literal_type_alias_values(surface.path, name)
                if actual != expected:
                    findings.append(
                        f"{surface.path}:{name} is {actual!r}, "
                        f"expected {expected!r}"
                    )
                continue

            ladder_pattern = _session_ladder_pattern(pattern)
            if ladder_pattern is not None:
                target, expected_count = ladder_pattern
                node = _pattern_function_scope(qualified_functions, target)
                if node is None:
                    findings.append(
                        f"{surface.path}:{target} snapshot-ladder scope is missing"
                    )
                elif _retains_session_snapshot_eligibility_ladder(node):
                    findings.append(
                        f"{surface.path}:{target} retains a direct "
                        "session-snapshot eligibility ladder"
                    )
                elif (
                    _method_call_count(
                        node,
                        "assistant_text_is_eligible",
                        receiver_name="snapshot",
                    )
                    != expected_count
                ):
                    findings.append(
                        f"{surface.path}:{target} must call "
                        "snapshot.assistant_text_is_eligible exactly "
                        f"{expected_count} time(s)"
                    )
                continue

            membership_kind: str | None = None
            membership_pattern = None
            for candidate_kind in (
                "run_terminal_membership",
                "step_settled_membership",
                "status_membership",
            ):
                membership_pattern = _status_pattern(
                    pattern,
                    candidate_kind,
                )
                if membership_pattern is not None:
                    membership_kind = candidate_kind
                    break
            if membership_pattern is None:
                continue
            target, values, expected_count = membership_pattern
            node = _pattern_function_scope(qualified_functions, target)
            if node is None:
                findings.append(
                    f"{surface.path}:{target} status-membership scope is missing"
                )
                continue
            count = _membership_count(node, values)
            if count:
                findings.append(
                    f"{surface.path}:{target} retains {count} direct "
                    f"{'|'.join(values)} membership check(s)"
                )
                continue
            if membership_kind == "run_terminal_membership":
                owner_count = _imported_symbol_call_count(
                    surface.path,
                    node,
                    module_name="orchestrator._common.status",
                    symbol="is_run_terminal",
                )
                owner_description = "is_run_terminal"
            elif membership_kind == "step_settled_membership":
                owner_count = _imported_symbol_call_count(
                    surface.path,
                    node,
                    module_name="orchestrator._common.status",
                    symbol="is_step_settled",
                )
                owner_description = "is_step_settled"
            else:
                owner_count = _imported_owner_method_call_count(
                    surface.path,
                    node,
                    module_name="orchestrator.workflow.resume_planner",
                    owner_symbol="ResumePlanner",
                    method_name="entry_status_is_terminal",
                )
                owner_description = (
                    "ResumePlanner.entry_status_is_terminal"
                )
            if owner_count != expected_count:
                findings.append(
                    f"{surface.path}:{target} must call "
                    f"{owner_description} exactly {expected_count} time(s); "
                    f"found {owner_count}"
                )

    assert not findings, "\n".join(findings)


def test_excluded_wcc_canonical_helper_and_output_remain_local() -> None:
    from orchestrator.workflow_lisp.wcc.defunctionalize import _sha256_json

    path = "orchestrator/workflow_lisp/wcc/defunctionalize.py"
    definitions = _top_level_function_names(path)

    assert {"_sha256_text", "_sha256_json"} <= definitions
    assert not _imports_from(path, COMMON_CANONICAL_MODULE)
    assert (
        _sha256_json({"z": [Path("α/β"), float("nan")], "a": "café"})
        == "sha256:eda480331ef59eaade0fd6d970eac069ccf4ac98926402449b1c282a722f0640"
    )
