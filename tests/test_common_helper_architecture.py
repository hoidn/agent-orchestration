from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMMON_CANONICAL_MODULE = "orchestrator._common.canonical"
COMMON_CANONICAL_PATH = REPO_ROOT / "orchestrator/_common/canonical.py"


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
                "running|completed|failed",
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
