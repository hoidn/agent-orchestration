"""Resolve the file inputs captured by one checked provider effect."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from orchestrator.deps.content_snapshot import (
    DependencyContentSnapshot,
    snapshot_content_dependencies_with_sha256,
)
from orchestrator.deps.resolver import DependencyResolver
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow.evaluated.values import EvaluatedValue
from orchestrator.workflow.evaluated.provider_io import WorkflowIOReader
from orchestrator.workflow_lisp.closed.sites import _effect_value_children
from orchestrator.workflow_lisp.closed.program import strip_provenance
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import ProviderParams, ProviderSessionMetadataMode
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.contracts.output_contract import (
    ContractViolation, OutputContractError, validate_expected_outputs,
)

from .commands import (
    CommandPerformerError,
    _require_native_result_contract,
    validate_effect_result,
)
from .prompts import provider_expected_outputs


DELIVERY_SELECTORS = {"legacy": "legacy", "file/1": "file", "file/2": "file/2"}
FILE_DELIVERY_NAME = "file/2"
DELIVERY_NAMES_BY_DIGEST = {canonical_sha256(name): name for name in DELIVERY_SELECTORS}


def current_provider_delivery_name(provider_name: str, registry=None) -> str:
    """Match the command variant prepared with session_request=None in both runtimes."""
    template = (registry if registry is not None else ProviderRegistry()).get(provider_name)
    if template is None:
        raise ValueError(f"provider template unavailable: {provider_name}")
    if template.command_metadata_mode == ProviderSessionMetadataMode.OMP_JSON_STDOUT.value:
        return "legacy"
    return FILE_DELIVERY_NAME


class ProviderPerformerError(RuntimeError):
    def __init__(self, code: str, message: str, *, exit_info=None, violations=None):
        self.code = code
        self.exit_info = exit_info
        self.violations = violations
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedProviderInput:
    prompt: str
    policy: Mapping[str, Any]
    input_parts: Mapping[str, str]
    expected_outputs: list[dict[str, Any]]


@dataclass(frozen=True)
class ProviderIOReads:
    """C6 text and raw-byte evidence, without the physical reader root."""

    source_kind: str | None
    source_path: str | None
    source_text: str | None
    source_sha256: str | None
    dependency_snapshot: DependencyContentSnapshot | None
    dependency_sha256s: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dependency_sha256s", MappingProxyType(dict(self.dependency_sha256s))
        )


def resolve_provider_io(
    node: Mapping[str, Any],
    operands: Sequence[EvaluatedValue],
    *,
    workspace: Path,
    reader: WorkflowIOReader | None,
) -> ProviderIOReads:
    """Read one checked provider's source and dependency snapshot exactly once."""
    values = _checked_provider_values(node, operands)
    return _resolve_provider_io_values(
        node,
        values,
        workspace=workspace,
        reader=reader,
    )


def _checked_provider_values(
    node: Mapping[str, Any], operands: Sequence[EvaluatedValue]
) -> tuple[Any, ...]:
    """Keep the legacy checked-node/value guard at the typed entry point."""
    if node.get("class") != "provider":
        raise TypeError("checked provider effect required")
    children = _effect_value_children(dict(node))
    if len(children) != len(operands) or not all(
        isinstance(value, EvaluatedValue) for value in operands
    ):
        raise ValueError("provider operands do not match the checked effect node")
    return tuple(value.json_value() for value in operands)


def _resolve_provider_io_values(
    node: Mapping[str, Any],
    values: Sequence[Any],
    *,
    workspace: Path,
    reader: WorkflowIOReader | None,
) -> ProviderIOReads:
    """Prepare captured source/dependency evidence from already-validated values."""
    prompt = node.get("prompt")
    if not isinstance(prompt, Mapping):
        raise ValueError("checked provider prompt shape is invalid")

    source_kind, source_path, source_text, source_sha256 = _read_source(
        node, prompt, workspace=workspace, reader=reader
    )
    snapshot, digests = _snapshot_dependencies(node, values, Path(workspace))
    return ProviderIOReads(
        source_kind,
        source_path,
        source_text,
        source_sha256,
        snapshot,
        digests,
    )


def _read_source(node, prompt, *, workspace, reader):
    source_kind = prompt.get("source_kind")
    source_path = prompt.get("path")
    if source_kind == "asset_file":
        if reader is None:
            raise ValueError("provider file read requires its checked reader")
        text, digest = WorkflowAssetResolver(reader.workflow_path).read_text_with_sha256(
            source_path
        )
    elif source_kind == "input_file":
        text, digest, error = PromptComposer(
            workspace=Path(workspace), asset_resolver=None
        ).read_prompt_source_with_sha256(
            {"input_file": source_path},
            step_name=str(node.get("provider", "provider")),
            contract_violation_result=lambda message, context: {
                "message": message,
                "context": context,
            },
        )
        if error is not None:
            raise ValueError(error)
    elif source_kind is None and "template" in prompt:
        return None, None, None, None
    else:
        raise ValueError("checked provider has no prompt source")
    return source_kind, source_path, text, digest


def _snapshot_dependencies(node, values, workspace):
    prompt = node["prompt"]
    fills = prompt.get("fills", ())
    dependencies = node.get("dependencies") or {}
    required = dependencies.get("required", ())
    optional = dependencies.get("optional", ())
    cursor = len(node.get("inputs", ()))
    fill_values = values[cursor : cursor + len(fills)]
    cursor += len(fills)
    required_values = values[cursor : cursor + len(required)]
    cursor += len(required)
    optional_values = values[cursor : cursor + len(optional)]
    required_rows = [
        (fill["name"], path)
        for fill, path in zip(fills, fill_values, strict=True)
        if fill.get("kind") == "doc"
    ]
    required_rows.extend(
        (f"required:{index}", path) for index, path in enumerate(required_values)
    )
    optional_rows = [
        (f"optional:{index}", path) for index, path in enumerate(optional_values)
    ]
    if not required_rows and not optional_rows:
        return None, {}
    resolved = DependencyResolver(str(workspace)).resolve_exact(
        required=required_rows, optional=optional_rows
    )
    return snapshot_content_dependencies_with_sha256(
        workspace, resolved.classified_rows
    )


def resolve_provider_input(node, operands, *, workspace, reader, result_path, delivery_name=None):
    """Capture the request with its rendering identity; None preserves pre-versioned rows."""
    values = _checked_provider_values(node, operands)
    return _resolve_provider_input_values(
        node,
        values,
        workspace=workspace,
        reader=reader,
        result_path=result_path,
        delivery_name=delivery_name,
    )


def _resolve_provider_input_values(
    node,
    values: Sequence[Any],
    *,
    workspace,
    reader,
    result_path,
    delivery_name=None,
):
    """Prepare a provider request from plain values checked at its caller boundary."""
    reads = _resolve_provider_io_values(
        node,
        values,
        workspace=workspace,
        reader=reader,
    )
    fills = node["prompt"].get("fills", ())
    cursor = len(node["inputs"])
    fill_values = values[cursor : cursor + len(fills)]
    policy_count = len(node["policy"])
    policy_values = values[-policy_count:] if policy_count else ()
    policy = dict(zip(node["policy"], policy_values, strict=True))
    from .prompts import _assemble_provider_prompt_values

    prompt = _assemble_provider_prompt_values(
        node, values, source_text=reads.source_text,
        dependency_snapshot=reads.dependency_snapshot, result_path=result_path,
        delivery=DELIVERY_SELECTORS["legacy" if delivery_name is None else delivery_name],
    )
    dependency_rows = (
        [] if reads.dependency_snapshot is None
        else [asdict(row) for row in reads.dependency_snapshot.authored_rows]
    )
    parts = {
        "declaration": canonical_sha256(strip_provenance({"body": dict(node)})["body"]),
        "values": canonical_sha256(values),
        "policy": canonical_sha256(policy),
        "params": canonical_sha256({}),
        "prompt": "sha256:" + sha256(prompt.encode("utf-8")).hexdigest(),
        "dependency_rows": canonical_sha256(dependency_rows),
    }
    if delivery_name is not None:
        parts["delivery"] = canonical_sha256(delivery_name)
    if reads.source_kind is not None:
        parts[f"source:{reads.source_kind}:{reads.source_path}"] = (
            reads.source_sha256 or canonical_sha256(None)
        )
    parts.update({
        f"dependency:{path}": digest
        for path, digest in reads.dependency_sha256s.items()
    })
    return ResolvedProviderInput(
        prompt, policy, parts, provider_expected_outputs(fills, fill_values)
    )


def perform_provider(
    node, resolved, identity, *, executor: ProviderExecutor,
    attempt_files: WorkspaceFiles, workspace_files: WorkspaceFiles,
    result_path: str,
    native_result: bool = False,
):
    """Prepare once, dispatch at most once, and keep exclusive attempt evidence."""
    if type(native_result) is not bool:
        raise TypeError("native_result must be a boolean")
    if native_result:
        try:
            _require_native_result_contract(node)
        except CommandPerformerError as exc:
            raise ProviderPerformerError(
                "provider_result_contract", str(exc), exit_info=exc.exit_info
            ) from exc
    attempt_files.create("prompt.txt", resolved.prompt.encode("utf-8"), exclusive=True)
    stdout, stderr = b"", b""
    try:
        invocation, error = _prepare_provider_invocation(
            node, resolved, str(attempt_files.workspace / "result.json"), executor)
        if error is not None or invocation is None:
            raise ProviderPerformerError(
                "provider_preparation_failed", str(error or "provider invocation missing"),
                exit_info={"error": error},
            )
        execution = executor.execute(
            invocation, cwd=workspace_files.workspace, stream_output=False,
            session_runtime=None, execution_env_overlay={
                "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY": (
                    "sha256:" + sha256(identity.encode("utf-8")).hexdigest()
                )
            },
        )
        stdout = execution.raw_stdout if execution.raw_stdout is not None else execution.stdout
        stderr = execution.stderr
        if execution.exit_code != 0 or execution.error is not None:
            code = (
                "provider_timeout" if (execution.error or {}).get("type") == "timeout"
                else "provider_exit_nonzero"
            )
            raise ProviderPerformerError(
                code, f"evaluated provider failed: {execution.error or execution.exit_code}",
                exit_info={"exit_code": execution.exit_code, "error": execution.error},
            )
    finally:
        attempt_files.create("stdout.txt", stdout, exclusive=True)
        attempt_files.create("stderr.txt", stderr, exclusive=True)
    if invocation.metadata_mode == ProviderSessionMetadataMode.OMP_JSON_STDOUT.value:
        if not execution.normalized_stdout:
            raise ProviderPerformerError(
                "provider_result_missing", f"provider did not provide normalized output for {result_path}"
            )
        attempt_files.create("result.json", execution.normalized_stdout, exclusive=True)
    return _provider_result(
        node,
        resolved,
        attempt_files,
        workspace_files,
        result_path,
        native_result=native_result,
    )


def _prepare_provider_invocation(node, resolved, result_path, executor):
    input_file = (
        node["prompt"].get("path")
        if node["prompt"].get("source_kind") == "input_file" else None
    )
    return executor.prepare_invocation(
        provider_name=node["provider"],
        params=ProviderParams(params={}, input_file=input_file),
        context={},
        prompt_content=resolved.prompt,
        session_request=None,
        env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": result_path},
        secrets=None,
        timeout_sec=resolved.policy.get("timeout_sec"),
        provider_call_policy={
            key: resolved.policy[key] for key in ("model", "effort")
            if key in resolved.policy
        },
        provider_session_dir=None,
        provider_session_identity=None,
    )


def _provider_result(
    node, resolved, attempt_files, workspace_files, result_path, *, native_result=False
):
    try:
        result_bytes = attempt_files.read("result.json")
    except FileNotFoundError as exc:
        raise ProviderPerformerError(
            "provider_result_missing", f"provider did not create {result_path}"
        ) from exc
    except (OSError, ValueError) as exc:
        raise ProviderPerformerError("provider_result_unreadable", str(exc)) from exc
    try:
        expected = validate_expected_outputs(
            resolved.expected_outputs, workspace=workspace_files.workspace,
            workspace_files=workspace_files, finite_floats=True,
        )
        result, digest, artifacts = validate_effect_result(
            node,
            result_bytes,
            result_path,
            workspace_files,
            native_result=native_result,
        )
        overlap = sorted(set(expected) & set(artifacts))
        if overlap:
            raise OutputContractError([ContractViolation(
                type="duplicate_artifact_name",
                message="Expected and structured output contracts must publish disjoint artifact names",
                context={"names": overlap},
            )])
        return result, digest
    except OutputContractError as exc:
        raise ProviderPerformerError(
            "provider_result_invalid", str(exc), violations=exc.violations
        ) from exc
    except CommandPerformerError as exc:
        raise ProviderPerformerError(
            exc.code.replace("command_", "provider_", 1), str(exc), exit_info=exc.exit_info
        ) from exc
