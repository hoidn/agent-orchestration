"""Shared source-free child document and materialization wire contracts."""

from __future__ import annotations

import math
import re
from pathlib import PurePosixPath
from typing import Any, Mapping

from orchestrator.contracts.closed_program.targets import (
    EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
    target_dsl_uses_evaluated_execution,
)

from orchestrator.workflow.type_descriptor import validate_transport_value

from .config import RunRefConfinedStaticConfig
from .contracts import RepositoryRevisionId, canonical_sha256
from .source import (
    MaterializedSource,
    canonical_repository_revision_result,
    validate_commit_sha,
)
from .workspace import TreeEntry, TreeManifest, manifest_from_entries


RUN_REF_CHILD_DIAGNOSTIC_SCHEMA = "run_ref_child_diagnostic.v1"
RUN_REF_MATERIALIZED_SOURCE_SCHEMA = "run_ref_materialized_source.v1"
RUN_REF_CONFINED_CHILD_REQUEST_SCHEMA = "run_ref_confined_child_request.v1"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_STRUCTURAL_REFUSAL_CODES = frozenset(
    {
        "trial_program_missing",
        "trial_program_compile_rejected",
        "trial_program_signature_mismatch",
        "trial_candidate_environment_not_admissible",
    }
)
_RUNTIME_FAILURE_REASONS = {
    "workflow_execution_target_retired": frozenset({"staged_execution_retired", "flat_execution_retired"}),
    "run_ref_capsule_invalid": frozenset(
        {"capsule_validation_failed", "target_not_declared"}
    ),
    "run_ref_child_launch_failed": frozenset(
        {
            "request_invalid",
            "input_binding_rejected",
            "workflow_execution_failed",
        }
    ),
    "run_ref_child_result_invalid": frozenset(
        {"workflow_outputs_invalid", "child_failure_authority_invalid"}
    ),
    "evaluated_execution_unavailable": frozenset(
        {"flat_execution_unavailable"}
    ),
}
_COMPILE_DIAGNOSTIC_KEYS = frozenset(
    {
        "code",
        "diagnostic_kind",
        "severity",
        "message",
        "path",
        "line",
        "column",
        "form_path",
        "expansion_stack",
        "notes",
        "phase",
        "validation_pass",
        "authority_layer",
    }
)


def _plain_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite JSON number")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    raise TypeError("value is not JSON-transportable")


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value


def _validate_source_location(value: object) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "line", "column"}
        or not _nonempty_string(value.get("path"))
        or type(value.get("line")) is not int
        or value["line"] < 1
        or type(value.get("column")) is not int
        or value["column"] < 1
    ):
        raise ValueError("compile diagnostic expansion location is invalid")


def _validate_expansion_frame(value: object) -> None:
    base = {"macro_name", "function_name", "expansion_id"}
    if not isinstance(value, dict) or frozenset(value) not in {
        frozenset(base),
        frozenset(base | {"call"}),
        frozenset(base | {"definition"}),
        frozenset(base | {"call", "definition"}),
    }:
        raise ValueError("compile diagnostic expansion frame is invalid")
    for field in base:
        item = value[field]
        if item is not None and not _nonempty_string(item):
            raise ValueError("compile diagnostic expansion frame is invalid")
    if value["macro_name"] is None and value["function_name"] is None:
        raise ValueError("compile diagnostic expansion frame is invalid")
    for field in ("call", "definition"):
        if field in value:
            _validate_source_location(value[field])


def _validate_compile_diagnostic_row(value: object) -> None:
    if not isinstance(value, dict) or frozenset(value) not in {
        _COMPILE_DIAGNOSTIC_KEYS,
        _COMPILE_DIAGNOSTIC_KEYS | {"phased_delivery_diagnostic"},
    }:
        raise ValueError("compile diagnostic row shape is invalid")
    for field in ("code", "severity", "message", "path"):
        if not _nonempty_string(value[field]):
            raise ValueError("compile diagnostic scalar is invalid")
    for field in (
        "diagnostic_kind",
        "phase",
        "validation_pass",
        "authority_layer",
    ):
        item = value[field]
        if item is not None and not _nonempty_string(item):
            raise ValueError("compile diagnostic scalar is invalid")
    if (
        type(value["line"]) is not int
        or value["line"] < 1
        or type(value["column"]) is not int
        or value["column"] < 1
    ):
        raise ValueError("compile diagnostic position is invalid")
    for field in ("form_path", "notes"):
        items = value[field]
        if not isinstance(items, list) or any(
            not _nonempty_string(item) for item in items
        ):
            raise ValueError("compile diagnostic string vector is invalid")
    expansion_stack = value["expansion_stack"]
    if not isinstance(expansion_stack, list):
        raise ValueError("compile diagnostic expansion stack is invalid")
    for frame in expansion_stack:
        _validate_expansion_frame(frame)
    if "phased_delivery_diagnostic" in value:
        from orchestrator.workflow.provider_phased_delivery.protocol import (
            diagnostic_from_dict,
            diagnostic_to_dict,
        )

        diagnostic = diagnostic_from_dict(value["phased_delivery_diagnostic"])
        if diagnostic_to_dict(diagnostic) != value["phased_delivery_diagnostic"]:
            raise ValueError("nested phased diagnostic is not canonical")


def _validate_accepted_compile_identity(document: Mapping[str, Any]) -> None:
    selected_entry = document.get("selected_entry")
    identity = document.get("normalized_program_identity")
    if not isinstance(selected_entry, Mapping) or not isinstance(identity, Mapping):
        raise ValueError("accepted compile authority is invalid")
    identity_schema = identity.get("schema_version")
    expected_identity_fields = {
        "schema_version",
        "digest",
        "compiler_runtime_identity",
        "module_source_revisions",
        "compiler_source_revisions",
        "imported_bundle_bindings",
        "selected_entry_sha256",
        "lowering_route",
        "lowering_schema_version",
        "configuration_payload_digests",
        "configuration_revisions",
    }
    if identity_schema == "workflow_lisp_program_identity.v2":
        expected_identity_fields.add("boundary_admission_profile")
    elif identity_schema != "workflow_lisp_program_identity.v1":
        raise ValueError("accepted compile identity version is invalid")
    if set(identity) != expected_identity_fields:
        raise ValueError("accepted compile identity shape is invalid")
    from orchestrator.contracts.program_identity import (
        build_normalized_program_identity,
    )

    rebuilt = build_normalized_program_identity(
        compiler_runtime_identity=identity["compiler_runtime_identity"],
        module_source_revisions=identity["module_source_revisions"],
        compiler_source_revisions=identity["compiler_source_revisions"],
        imported_bundle_bindings=identity["imported_bundle_bindings"],
        selected_entry=selected_entry,
        lowering_route=identity["lowering_route"],
        lowering_schema_version=identity["lowering_schema_version"],
        configuration_payload_digests=identity[
            "configuration_payload_digests"
        ],
        configuration_revisions=identity["configuration_revisions"],
        boundary_admission_profile=(
            identity.get("boundary_admission_profile")
            if identity_schema == "workflow_lisp_program_identity.v2"
            else None
        ),
    )
    if rebuilt != identity:
        raise ValueError("accepted compile identity is not canonical")


def _validated_compile_diagnostics(value: object) -> dict[str, Any]:
    document = _plain_json(value)
    if not isinstance(document, dict):
        raise ValueError("compile diagnostics must be an object")
    status = document.get("status")
    expected = {"schema_version", "status", "diagnostics"}
    if status == "accepted":
        expected |= {"selected_entry", "normalized_program_identity"}
    elif status != "rejected":
        raise ValueError("compile diagnostics status is invalid")
    if (
        set(document) != expected
        or document.get("schema_version")
        != "workflow_lisp_compile_diagnostics.v1"
        or not isinstance(document.get("diagnostics"), list)
    ):
        raise ValueError("compile diagnostics shape is invalid")
    diagnostics = document["diagnostics"]
    if status == "rejected" and not diagnostics:
        raise ValueError("rejected compile diagnostics must be non-empty")
    for row in diagnostics:
        _validate_compile_diagnostic_row(row)
    if status == "accepted":
        _validate_accepted_compile_identity(document)
    return document


def validate_child_diagnostic_document(value: object) -> dict[str, Any]:
    """Validate and copy one exact child failure authority document."""

    document = _plain_json(value)
    common = {"schema_version", "status", "code", "reason"}
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != RUN_REF_CHILD_DIAGNOSTIC_SCHEMA
        or document.get("status") != "rejected"
        or not _nonempty_string(document.get("code"))
        or not _nonempty_string(document.get("reason"))
    ):
        raise ValueError("child diagnostic common authority is invalid")
    code = document["code"]
    reason = document["reason"]
    if code == "evaluated_execution_unavailable":
        expected = common | {
            "rejected_value",
            "secondary_causes",
            "compile_diagnostics",
        }
        if frozenset(document) != frozenset(expected) or reason != (
            "flat_execution_unavailable"
        ):
            raise ValueError("evaluated execution diagnostic shape is invalid")
        rejected_value = document["rejected_value"]
        if (
            not isinstance(rejected_value, Mapping)
            or set(rejected_value) != {"target_dsl_version"}
            or not _nonempty_string(rejected_value["target_dsl_version"])
            or not target_dsl_uses_evaluated_execution(
                rejected_value["target_dsl_version"]
            )
        ):
            raise ValueError("evaluated execution rejected value is invalid")
        if document["secondary_causes"] != [
            "evaluated_execution_minimum_target_dsl_version:"
            + EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
        ]:
            raise ValueError("evaluated execution limit authority is invalid")
        compile_document = _validated_compile_diagnostics(
            document["compile_diagnostics"]
        )
        diagnostics = compile_document["diagnostics"]
        if (
            compile_document["status"] != "rejected"
            or len(diagnostics) != 1
            or diagnostics[0]["code"] != code
            or diagnostics[0]["phase"] != "lowering"
        ):
            raise ValueError("evaluated execution source location is invalid")
        return document
    if code in _STRUCTURAL_REFUSAL_CODES:
        allowed_shapes = {
            frozenset(common | {"rejected_value", "secondary_causes"}),
            frozenset(
                common
                | {
                    "rejected_value",
                    "secondary_causes",
                    "compile_diagnostics",
                }
            ),
        }
        if (
            frozenset(document) not in allowed_shapes
            or reason != "path_compile_rejected"
        ):
            raise ValueError("structural child diagnostic shape is invalid")
        causes = document["secondary_causes"]
        if (
            not isinstance(causes, list)
            or not causes
            or any(
                not _nonempty_string(cause) or cause.strip() != cause
                for cause in causes
            )
            or len(causes) != len(set(causes))
        ):
            raise ValueError("structural child secondary causes are invalid")
        if "compile_diagnostics" in document:
            compile_document = _validated_compile_diagnostics(
                document["compile_diagnostics"]
            )
            rejected_value = document["rejected_value"]
            if (
                isinstance(rejected_value, Mapping)
                and "compile_diagnostics" in rejected_value
                and rejected_value["compile_diagnostics"] != compile_document
            ):
                raise ValueError("compile diagnostic authority is inconsistent")
        return document
    allowed_reasons = _RUNTIME_FAILURE_REASONS.get(code)
    if (
        allowed_reasons is None
        or reason not in allowed_reasons
        or set(document) != common
    ):
        raise ValueError("runtime child diagnostic authority is invalid")
    return document


def _tree_manifest_record(manifest: TreeManifest) -> dict[str, object]:
    if type(manifest) is not TreeManifest:
        raise TypeError("tree manifest authority must be exact")
    return {
        "schema_version": manifest.schema_version,
        "entries": [
            {
                "path": entry.path,
                "kind": entry.kind,
                "mode": entry.mode,
                "size": entry.size,
                "sha256": entry.sha256,
                "link_target": entry.link_target,
            }
            for entry in manifest.entries
        ],
        "digest": manifest.digest,
    }


def _tree_entry_from_payload(value: object) -> TreeEntry:
    expected = {"path", "kind", "mode", "size", "sha256", "link_target"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("tree manifest entry shape is invalid")
    path = value["path"]
    if not isinstance(path, str) or not path or "\\" in path or "\0" in path:
        raise ValueError("tree manifest path is invalid")
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != path
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise ValueError("tree manifest path is not canonical")
    kind = value["kind"]
    if kind not in {"directory", "file", "symlink"}:
        raise ValueError("tree manifest kind is invalid")
    mode = value["mode"]
    size = value["size"]
    if (
        isinstance(mode, bool)
        or not isinstance(mode, int)
        or mode < 0
        or mode > 0o7777
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise ValueError("tree manifest numeric facts are invalid")
    digest = value["sha256"]
    if digest is not None and (
        not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None
    ):
        raise ValueError("tree manifest digest is invalid")
    link_target = value["link_target"]
    if link_target is not None and (
        not isinstance(link_target, str) or "\0" in link_target
    ):
        raise ValueError("tree manifest link target is invalid")
    if kind == "directory" and (
        size != 0 or digest is not None or link_target is not None
    ):
        raise ValueError("tree directory facts are invalid")
    if kind == "file" and (digest is None or link_target is not None):
        raise ValueError("tree file facts are invalid")
    if kind == "symlink" and (digest is None or link_target is None):
        raise ValueError("tree symlink facts are invalid")
    return TreeEntry(
        path=path,
        kind=kind,
        mode=mode,
        size=size,
        sha256=digest,
        link_target=link_target,
    )


def _tree_manifest_from_payload(value: object) -> TreeManifest:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "entries",
        "digest",
    }:
        raise ValueError("tree manifest shape is invalid")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("tree manifest schema is invalid")
    entries = value["entries"]
    if not isinstance(entries, list):
        raise ValueError("tree manifest entries are invalid")
    manifest = manifest_from_entries(
        _tree_entry_from_payload(entry) for entry in entries
    )
    if _tree_manifest_record(manifest) != value:
        raise ValueError("tree manifest does not match its canonical digest")
    return manifest


def materialized_source_record(source: MaterializedSource) -> dict[str, object]:
    """Encode exact reconstructible materialization facts for the path child."""

    if type(source) is not MaterializedSource:
        raise TypeError("materialized source authority must be exact")
    components: dict[str, object] = {
        "schema_version": RUN_REF_MATERIALIZED_SOURCE_SCHEMA,
        "repository_revision": canonical_repository_revision_result(
            source.repository_revision_id
        ),
        "normalized_locator": source.normalized_locator,
        "resolved_commit_sha": source.resolved_commit_sha,
        "verified_git_tree": source.verified_git_tree.value,
        "mirror_path": source.mirror_path.as_posix(),
        "mirror_seal_path": source.mirror_seal_path.as_posix(),
        "workspace_path": source.workspace_path.as_posix(),
        "source_tree_manifest": _tree_manifest_record(
            source.source_tree_manifest
        ),
        "setup_evidence_path": source.setup_evidence_path.as_posix(),
        "setup_evidence_digest": source.setup_evidence_digest,
        "post_setup_tree_manifest": _tree_manifest_record(
            source.post_setup_tree_manifest
        ),
        "post_setup_baseline_identity": (
            source.post_setup_baseline_identity.digest
        ),
    }
    return {**components, "digest": canonical_sha256(components)}


def _repository_revision_from_payload(value: object) -> RepositoryRevisionId:
    expected = {
        "schema_version",
        "digest",
        "normalized_locator",
        "resolved_commit_sha",
        "materializer_version",
        "submodule_policy",
        "lfs_policy",
        "authored_setup_identity",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("repository revision shape is invalid")
    if value["schema_version"] != "run_ref_repository_revision.v1":
        raise ValueError("repository revision schema is invalid")
    revision = RepositoryRevisionId(
        digest=value["digest"],
        normalized_locator=value["normalized_locator"],
        resolved_commit_sha=value["resolved_commit_sha"],
        materializer_version=value["materializer_version"],
        submodule_policy=value["submodule_policy"],
        lfs_policy=value["lfs_policy"],
        authored_setup_identity=value["authored_setup_identity"],
    )
    if canonical_repository_revision_result(revision) != value:
        raise ValueError("repository revision is not canonical")
    return revision


def confined_child_request(
    config: RunRefConfinedStaticConfig,
    *,
    commit: str,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one confined child's durable request to its parent-resolved operands.

    The request binds the literal repo and the evaluated `:commit`, the checked
    child entry and its owner configuration, the typed ordered inputs, the
    image and the whole confinement policy; its digest covers all of them.
    """

    if type(config) is not RunRefConfinedStaticConfig:
        raise TypeError("confined child request requires RunRefConfinedStaticConfig")
    commit = validate_commit_sha(commit)
    if not isinstance(inputs, Mapping) or list(inputs) != [row.name for row in config.inputs]:
        raise ValueError("confined child request inputs differ from the site's ordered inputs")
    components = {
        "schema_version": RUN_REF_CONFINED_CHILD_REQUEST_SCHEMA,
        "static_config_digest": config.digest,
        "source": {"normalized_locator": config.repo, "resolved_commit_sha": commit},
        "child": config.program.record,
        "environment": config.policy.record,
        "inputs": [
            {
                "name": row.name,
                "type_descriptor": row.type_descriptor,
                "value": validate_transport_value(
                    inputs[row.name], row.type_descriptor, allow_nested_structures=True
                ),
            }
            for row in config.inputs
        ],
    }
    return {**components, "digest": canonical_sha256(components)}


def validate_confined_child_request(
    record: object,
    config: RunRefConfinedStaticConfig,
    *,
    commit: str,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Refuse, before any launch, a request that is not exactly the re-derived one."""

    expected = confined_child_request(config, commit=commit, inputs=inputs)
    try:
        actual = _plain_json(record)
    except TypeError as exc:
        raise ValueError("confined child request is not plain JSON") from exc
    if actual != expected:
        raise ValueError("confined child request does not match its site and resolved operands")
    return expected
