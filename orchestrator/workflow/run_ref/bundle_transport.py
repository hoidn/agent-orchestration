"""Content-addressed transport for validated mode-1 workflow bundles."""

from __future__ import annotations

import copyreg
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import pickle
import platform
import re
import shutil
import sys
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from orchestrator import __version__ as ORCHESTRATOR_VERSION
from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.workflow.core_ast import (
    validate_core_workflow_ast,
    workflow_core_ast_to_json,
)
from orchestrator.workflow.executable_ir import (
    RunRefStepConfig,
    TrialArmStepConfig,
    TrialStepConfig,
    validate_executable_workflow,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    persisted_surface_sha256,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.runtime_plan import validate_workflow_runtime_plan
from orchestrator.workflow.semantic_ir import (
    validate_workflow_semantic_ir,
    workflow_semantic_ir_to_json,
)
from orchestrator.workflow_lisp.wcc.route import LOWERING_SCHEMA_WCC

from .contracts import canonical_json_bytes, canonical_sha256
from .config import BundleProgram, RunRefBundleCapsuleBinding
from .result_contract import validate_run_ref_result_descriptor


RUN_REF_BUNDLE_CAPSULE_SCHEMA = "run_ref_bundle_capsule.v1"
RUN_REF_BUNDLE_ENCODING = "python-pickle-protocol-5.v1"
RUN_REF_BUNDLE_NORMALIZATION = (
    "run_ref_bundle_unbound_capsule_binding.v1"
)
MAX_BUNDLE_PICKLE_BYTES = 64 * 1024 * 1024
_PICKLE_PROTOCOL = 5
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CLOSURE_ROLES = frozenset({"orc", "prompt_asset", "workflow_asset"})
_SUPPORTED_TARGET_DSL_VERSIONS = frozenset({"2.24", "2.25"})


class BundleCapsuleValidationError(ValueError):
    """Closed capsule-validation failure with stable routing code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class BundleCapsuleClosureBlob:
    """One exact source or asset blob carried by a capsule."""

    path: str
    roles: tuple[str, ...]
    payload: bytes


@dataclass(frozen=True)
class EncodedBundleCapsule:
    """Canonical capsule bytes and their comparison-only local digest."""

    capsule_digest: str
    manifest_bytes: bytes
    pickle_bytes: bytes
    closure: tuple[BundleCapsuleClosureBlob, ...]


@dataclass(frozen=True)
class DecodedBundleCapsule:
    """Verified typed bundle catalog ready for later relocation/injection."""

    capsule_digest: str
    target_workflow_names: tuple[str, ...]
    bundles_by_name: Mapping[str, LoadedWorkflowBundle]
    closure: tuple[BundleCapsuleClosureBlob, ...]
    workflow_closure_paths: Mapping[str, str]


@dataclass(frozen=True)
class _BundleCatalog:
    schema_version: str
    bundles_by_name: Mapping[str, LoadedWorkflowBundle]


def _mapping_proxy_from_items(
    items: tuple[tuple[Any, Any], ...],
) -> Mapping[Any, Any]:
    """Reconstruct one immutable mapping without global copyreg mutation."""

    return MappingProxyType(dict(items))


def _reduce_mapping_proxy(
    value: Mapping[Any, Any],
) -> tuple[Any, tuple[tuple[tuple[Any, Any], ...]]]:
    items = tuple(
        sorted(
            value.items(),
            key=lambda item: (
                f"{type(item[0]).__module__}.{type(item[0]).__qualname__}:".encode(
                    "utf-8"
                )
                + canonical_json_bytes(_json_value(item[0]))
            ),
        )
    )
    return _mapping_proxy_from_items, (items,)


def _pickle_protocol_five(value: object) -> bytes:
    buffer = io.BytesIO()
    pickler = pickle.Pickler(buffer, protocol=_PICKLE_PROTOCOL)
    dispatch_table = copyreg.dispatch_table.copy()
    dispatch_table[_MAPPING_PROXY_TYPE] = _reduce_mapping_proxy
    pickler.dispatch_table = dispatch_table
    pickler.dump(value)
    return buffer.getvalue()


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _fail(code: str, message: str | None = None) -> None:
    raise BundleCapsuleValidationError(code, message)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _canonical_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        _fail("run_ref_bundle_closure_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail("run_ref_bundle_closure_invalid")
    canonical = path.as_posix()
    if canonical != value:
        _fail("run_ref_bundle_closure_invalid")
    return canonical


def _canonical_closure(
    closure: Sequence[BundleCapsuleClosureBlob],
) -> tuple[BundleCapsuleClosureBlob, ...]:
    rows: list[BundleCapsuleClosureBlob] = []
    seen_paths: set[str] = set()
    for blob in closure:
        if type(blob) is not BundleCapsuleClosureBlob:
            _fail("run_ref_bundle_closure_invalid")
        path = _canonical_relative_path(blob.path)
        if path in seen_paths:
            _fail("run_ref_bundle_closure_invalid")
        seen_paths.add(path)
        if (
            not isinstance(blob.roles, tuple)
            or not blob.roles
            or tuple(sorted(set(blob.roles))) != blob.roles
            or any(role not in _CLOSURE_ROLES for role in blob.roles)
            or not isinstance(blob.payload, bytes)
        ):
            _fail("run_ref_bundle_closure_invalid")
        rows.append(blob)
    if not rows or not any("orc" in blob.roles for blob in rows):
        _fail("run_ref_bundle_closure_invalid")
    return tuple(sorted(rows, key=lambda blob: blob.path))


def _canonical_workflow_closure_paths(
    value: Mapping[str, str],
    *,
    bundle_names: Sequence[str],
    closure: Sequence[BundleCapsuleClosureBlob],
) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(bundle_names):
        _fail("run_ref_bundle_workflow_closure_invalid")
    orc_paths = {
        blob.path
        for blob in closure
        if "orc" in blob.roles
    }
    canonical: dict[str, str] = {}
    for workflow_name, raw_path in value.items():
        if not isinstance(workflow_name, str) or not workflow_name:
            _fail("run_ref_bundle_workflow_closure_invalid")
        try:
            path = _canonical_relative_path(raw_path)
        except BundleCapsuleValidationError as exc:
            raise BundleCapsuleValidationError(
                "run_ref_bundle_workflow_closure_invalid"
            ) from exc
        if path not in orc_paths:
            _fail("run_ref_bundle_workflow_closure_invalid")
        canonical[workflow_name] = path
    return MappingProxyType(
        {name: canonical[name] for name in sorted(canonical)}
    )


def _bundle_name(bundle: LoadedWorkflowBundle) -> str:
    name = bundle.surface.name
    if not isinstance(name, str) or not name:
        _fail("run_ref_bundle_catalog_invalid")
    return name


def _catalog_target_dsl_version(
    bundles_by_name: Mapping[str, LoadedWorkflowBundle],
) -> str:
    versions = [bundle.surface.version for bundle in bundles_by_name.values()]
    if (
        any(not isinstance(version, str) for version in versions)
        or len(set(versions)) != 1
        or versions[0] not in _SUPPORTED_TARGET_DSL_VERSIONS
    ):
        _fail("run_ref_bundle_version_invalid")
    return versions[0]


def _validate_catalog(
    bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    *,
    target_workflow_names: Sequence[str],
    require_mapping_proxy: bool,
) -> tuple[Mapping[str, LoadedWorkflowBundle], tuple[str, ...]]:
    if not isinstance(bundles_by_name, Mapping) or not bundles_by_name:
        _fail("run_ref_bundle_catalog_invalid")
    if require_mapping_proxy and type(bundles_by_name) is not _MAPPING_PROXY_TYPE:
        _fail("run_ref_bundle_catalog_invalid")
    canonical: dict[str, LoadedWorkflowBundle] = {}
    for name, bundle in bundles_by_name.items():
        if not isinstance(name, str) or type(bundle) is not LoadedWorkflowBundle:
            _fail("run_ref_bundle_catalog_invalid")
        if name != _bundle_name(bundle) or name in canonical:
            _fail("run_ref_bundle_catalog_invalid")
        if require_mapping_proxy:
            for mapping in (
                bundle.imports,
                bundle.ir.nodes,
                bundle.projection.entries_by_node_id,
                bundle.runtime_plan.nodes,
            ):
                if type(mapping) is not _MAPPING_PROXY_TYPE:
                    _fail("run_ref_bundle_catalog_invalid")
        canonical[name] = bundle
    if (
        not isinstance(target_workflow_names, (tuple, list))
        or not target_workflow_names
        or any(not isinstance(name, str) or not name for name in target_workflow_names)
        or len(set(target_workflow_names)) != len(target_workflow_names)
    ):
        _fail("run_ref_bundle_catalog_invalid")
    targets = tuple(sorted(target_workflow_names))
    if any(name not in canonical for name in targets):
        _fail("run_ref_bundle_catalog_invalid")

    reachable: set[str] = set()
    pending = list(reversed(targets))
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        bundle = canonical[name]
        for alias, child in sorted(bundle.imports.items()):
            if not isinstance(alias, str) or type(child) is not LoadedWorkflowBundle:
                _fail("run_ref_bundle_catalog_invalid")
            child_name = _bundle_name(child)
            if canonical.get(child_name) is not child:
                _fail("run_ref_bundle_catalog_invalid")
            pending.append(child_name)
    if reachable != set(canonical):
        _fail("run_ref_bundle_catalog_invalid")
    return MappingProxyType(
        {name: canonical[name] for name in sorted(canonical)}
    ), targets


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("run_ref_bundle_manifest_invalid")
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            rows = [
                (_json_value(key), _json_value(item))
                for key, item in value.items()
            ]
            rows.sort(key=lambda row: canonical_json_bytes(row[0]))
            return {"$mapping": [[key, item] for key, item in rows]}
        payload: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda row: str(row[0])):
            payload[key] = _json_value(item)
        return payload
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_value(item) for item in value), key=repr)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            descriptor.name: _json_value(getattr(value, descriptor.name))
            for descriptor in fields(value)
            if not descriptor.name.startswith("_")
        }
    _fail("run_ref_bundle_catalog_invalid")


def _result_contract_digests(bundle: LoadedWorkflowBundle) -> dict[str, str]:
    digests: dict[str, str] = {}
    for node_id, node in sorted(bundle.ir.nodes.items()):
        config = getattr(node, "execution_config", None)
        configs = (
            ((node_id, config),)
            if isinstance(config, RunRefStepConfig)
            else (
                tuple(
                    (
                        f"{node_id}::trial_arm::{arm.arm_id}",
                        arm.run_ref,
                    )
                    for arm in config.arms
                )
                if type(config) is TrialStepConfig
                else ()
            )
        )
        for config_id, run_ref_config in configs:
            validate_run_ref_result_descriptor(
                run_ref_config.run_ref.result_descriptor,
                allow_nested_structures=(
                    run_ref_config.run_ref.target_dsl_version == "2.25"
                ),
            )
            digests[config_id] = run_ref_config.run_ref.result_digest
    return digests


def _require_unbound_capsule_configs(
    bundles_by_name: Mapping[str, LoadedWorkflowBundle],
) -> None:
    for bundle in bundles_by_name.values():
        for node in bundle.ir.nodes.values():
            config = getattr(node, "execution_config", None)
            if (
                isinstance(config, RunRefStepConfig)
                and config.capsule_binding is not None
            ):
                _fail("run_ref_bundle_prebound_config")
            if type(config) is TrialStepConfig and any(
                arm.run_ref.capsule_binding is not None
                for arm in config.arms
            ):
                _fail("run_ref_bundle_prebound_config")


def _rewrite_run_ref_step_config(
    config: RunRefStepConfig,
    *,
    binding: RunRefBundleCapsuleBinding | None,
) -> RunRefStepConfig:
    return replace(
        config,
        capsule_binding=(
            binding
            if isinstance(config.run_ref.program, BundleProgram)
            else None
        ),
    )


def _rewrite_execution_capsule_binding(
    config: object,
    *,
    binding: RunRefBundleCapsuleBinding | None,
) -> object:
    if isinstance(config, RunRefStepConfig):
        return _rewrite_run_ref_step_config(config, binding=binding)
    if type(config) is not TrialStepConfig:
        return config
    return replace(
        config,
        arms=tuple(
            TrialArmStepConfig(
                arm_id=arm.arm_id,
                run_ref=_rewrite_run_ref_step_config(
                    arm.run_ref,
                    binding=binding,
                ),
            )
            for arm in config.arms
        ),
    )


def _rewrite_catalog_capsule_binding(
    bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    *,
    binding: RunRefBundleCapsuleBinding | None,
) -> Mapping[str, LoadedWorkflowBundle]:
    """Rebuild one closed catalog with one uniform operational binding."""
    canonical, _targets = _validate_catalog(
        bundles_by_name,
        target_workflow_names=tuple(sorted(bundles_by_name)),
        require_mapping_proxy=False,
    )
    import_storage_by_name: dict[str, dict[str, LoadedWorkflowBundle]] = {
        name: {} for name in canonical
    }
    rebuilt: dict[str, LoadedWorkflowBundle] = {}
    for name, original in canonical.items():
        nodes = MappingProxyType(
            {
                node_id: replace(
                    node,
                    execution_config=_rewrite_execution_capsule_binding(
                        node.execution_config,
                        binding=binding,
                    ),
                )
                for node_id, node in sorted(original.ir.nodes.items())
            }
        )
        rebuilt[name] = replace(
            original,
            ir=replace(original.ir, nodes=nodes),
            imports=MappingProxyType(import_storage_by_name[name]),
        )
    for name, original in canonical.items():
        import_storage = import_storage_by_name[name]
        for alias, child in sorted(original.imports.items()):
            child_name = _bundle_name(child)
            if canonical.get(child_name) is not child:
                _fail("run_ref_bundle_catalog_invalid")
            import_storage[alias] = rebuilt[child_name]
    return MappingProxyType(
        {name: rebuilt[name] for name in sorted(rebuilt)}
    )


def bind_bundle_catalog_capsule(
    bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    *,
    binding: RunRefBundleCapsuleBinding,
) -> Mapping[str, LoadedWorkflowBundle]:
    """Bind one verified capsule identity across a closed controller graph."""

    if type(binding) is not RunRefBundleCapsuleBinding:
        _fail("run_ref_bundle_binding_invalid")
    return _rewrite_catalog_capsule_binding(
        bundles_by_name,
        binding=binding,
    )


def _bundle_digest_vector(bundle: LoadedWorkflowBundle) -> dict[str, Any]:
    persisted = serialize_persisted_workflow_surface_graph(bundle)
    persisted_bytes = canonical_persisted_surface_bytes(persisted)
    signature = {
        "workflow_name": bundle.surface.name,
        "inputs": _json_value(bundle.surface.inputs),
        "outputs": _json_value(bundle.surface.outputs),
        "result_guidance": _json_value(bundle.surface.result_guidance),
    }
    import_graph = {
        alias: child.surface.name
        for alias, child in sorted(bundle.imports.items())
    }
    return {
        "core_ast": canonical_sha256(
            workflow_core_ast_to_json(bundle.core_workflow_ast)
        ),
        "executable_ir": canonical_sha256(
            workflow_executable_ir_to_json(bundle.ir)
        ),
        "semantic_ir": canonical_sha256(
            workflow_semantic_ir_to_json(bundle.semantic_ir)
        ),
        "runtime_plan": canonical_sha256(_json_value(bundle.runtime_plan)),
        "projection": canonical_sha256(_json_value(bundle.projection)),
        "persisted_surface": persisted_surface_sha256(persisted_bytes),
        "signature": canonical_sha256(signature),
        "import_graph": canonical_sha256(import_graph),
        "result_contracts": _result_contract_digests(bundle),
    }


def _closure_manifest_rows(
    closure: Sequence[BundleCapsuleClosureBlob],
) -> list[dict[str, Any]]:
    return [
        {
            "path": blob.path,
            "roles": list(blob.roles),
            "size_bytes": len(blob.payload),
            "sha256": _sha256_bytes(blob.payload),
        }
        for blob in closure
    ]


def _manifest_payload(
    *,
    pickle_bytes: bytes,
    closure: Sequence[BundleCapsuleClosureBlob],
    bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    target_workflow_names: Sequence[str],
    workflow_closure_paths: Mapping[str, str],
    compiler_runtime_identity_digest: str,
    lowering_schema_version: int,
) -> dict[str, Any]:
    return {
        "schema_version": RUN_REF_BUNDLE_CAPSULE_SCHEMA,
        "encoding": RUN_REF_BUNDLE_ENCODING,
        "normalization": RUN_REF_BUNDLE_NORMALIZATION,
        "python": {
            "implementation": platform.python_implementation(),
            "major": sys.version_info.major,
            "minor": sys.version_info.minor,
        },
        "orchestrator_version": ORCHESTRATOR_VERSION,
        "compiler_runtime_identity_digest": compiler_runtime_identity_digest,
        "lowering_schema_version": lowering_schema_version,
        "target_dsl_versions": sorted(
            {bundle.surface.version for bundle in bundles_by_name.values()}
        ),
        "target_workflow_names": list(target_workflow_names),
        "bundle_names": list(bundles_by_name),
        "workflow_closure_paths": dict(workflow_closure_paths),
        "pickle": {
            "protocol": _PICKLE_PROTOCOL,
            "size_bytes": len(pickle_bytes),
            "sha256": _sha256_bytes(pickle_bytes),
        },
        "closure": _closure_manifest_rows(closure),
        "bundle_digests": {
            name: _bundle_digest_vector(bundle)
            for name, bundle in bundles_by_name.items()
        },
    }


def encode_bundle_capsule(
    bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    *,
    target_workflow_names: tuple[str, ...],
    closure: tuple[BundleCapsuleClosureBlob, ...],
    workflow_closure_paths: Mapping[str, str],
    compiler_runtime_identity_digest: str,
    lowering_schema_version: int,
) -> EncodedBundleCapsule:
    """Encode one canonical, already-validated target bundle catalog."""

    catalog, targets = _validate_catalog(
        bundles_by_name,
        target_workflow_names=target_workflow_names,
        require_mapping_proxy=False,
    )
    canonical_closure = _canonical_closure(closure)
    canonical_workflow_paths = _canonical_workflow_closure_paths(
        workflow_closure_paths,
        bundle_names=tuple(catalog),
        closure=canonical_closure,
    )
    if not _is_sha256(compiler_runtime_identity_digest):
        _fail("run_ref_bundle_compiler_identity_invalid")
    if (
        isinstance(lowering_schema_version, bool)
        or not isinstance(lowering_schema_version, int)
        or lowering_schema_version != LOWERING_SCHEMA_WCC
    ):
        _fail("run_ref_bundle_lowering_schema_invalid")
    _catalog_target_dsl_version(catalog)
    _require_unbound_capsule_configs(catalog)
    for bundle in catalog.values():
        _validate_bundle(bundle)
    payload = _BundleCatalog(
        schema_version=RUN_REF_BUNDLE_CAPSULE_SCHEMA,
        bundles_by_name=catalog,
    )
    try:
        pickle_bytes = _pickle_protocol_five(payload)
    except Exception as exc:
        raise BundleCapsuleValidationError(
            "run_ref_bundle_pickle_encode_failed"
        ) from exc
    if len(pickle_bytes) > MAX_BUNDLE_PICKLE_BYTES:
        _fail("run_ref_bundle_pickle_oversize")
    manifest_bytes = canonical_json_bytes(
        _manifest_payload(
            pickle_bytes=pickle_bytes,
            closure=canonical_closure,
            bundles_by_name=catalog,
            target_workflow_names=targets,
            workflow_closure_paths=canonical_workflow_paths,
            compiler_runtime_identity_digest=(
                compiler_runtime_identity_digest
            ),
            lowering_schema_version=lowering_schema_version,
        )
    )
    return EncodedBundleCapsule(
        capsule_digest=_sha256_bytes(manifest_bytes),
        manifest_bytes=manifest_bytes,
        pickle_bytes=pickle_bytes,
        closure=canonical_closure,
    )


def _strict_manifest(manifest_bytes: bytes) -> Mapping[str, Any]:
    if not isinstance(manifest_bytes, bytes):
        _fail("run_ref_bundle_manifest_invalid")

    def object_pairs(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("run_ref_bundle_manifest_invalid")
            result[key] = value
        return result

    try:
        manifest = json.loads(
            manifest_bytes.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=lambda _value: _fail(
                "run_ref_bundle_manifest_invalid"
            ),
        )
    except BundleCapsuleValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleCapsuleValidationError(
            "run_ref_bundle_manifest_invalid"
        ) from exc
    if not isinstance(manifest, dict):
        _fail("run_ref_bundle_manifest_invalid")
    try:
        canonical = canonical_json_bytes(manifest)
    except (TypeError, ValueError) as exc:
        raise BundleCapsuleValidationError(
            "run_ref_bundle_manifest_invalid"
        ) from exc
    if canonical != manifest_bytes:
        _fail("run_ref_bundle_manifest_invalid")
    return manifest


def _validate_manifest_shape(manifest: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema_version",
        "encoding",
        "normalization",
        "python",
        "orchestrator_version",
        "compiler_runtime_identity_digest",
        "lowering_schema_version",
        "target_dsl_versions",
        "target_workflow_names",
        "bundle_names",
        "workflow_closure_paths",
        "pickle",
        "closure",
        "bundle_digests",
    }
    if set(manifest) != expected_keys:
        _fail("run_ref_bundle_manifest_invalid")
    if manifest.get("schema_version") != RUN_REF_BUNDLE_CAPSULE_SCHEMA:
        _fail("run_ref_bundle_manifest_invalid")
    if manifest.get("encoding") != RUN_REF_BUNDLE_ENCODING:
        _fail("run_ref_bundle_encoding_invalid")
    if manifest.get("normalization") != RUN_REF_BUNDLE_NORMALIZATION:
        _fail("run_ref_bundle_normalization_invalid")
    if manifest.get("orchestrator_version") != ORCHESTRATOR_VERSION:
        _fail("run_ref_bundle_version_invalid")
    python_identity = manifest.get("python")
    if python_identity != {
        "implementation": platform.python_implementation(),
        "major": sys.version_info.major,
        "minor": sys.version_info.minor,
    }:
        _fail("run_ref_bundle_version_invalid")
    if not _is_sha256(manifest.get("compiler_runtime_identity_digest")):
        _fail("run_ref_bundle_compiler_identity_invalid")
    lowering = manifest.get("lowering_schema_version")
    if (
        isinstance(lowering, bool)
        or not isinstance(lowering, int)
        or lowering != LOWERING_SCHEMA_WCC
    ):
        _fail("run_ref_bundle_lowering_schema_invalid")
    target_dsl_versions = manifest.get("target_dsl_versions")
    if (
        not isinstance(target_dsl_versions, list)
        or len(target_dsl_versions) != 1
        or not isinstance(target_dsl_versions[0], str)
        or target_dsl_versions[0] not in _SUPPORTED_TARGET_DSL_VERSIONS
    ):
        _fail("run_ref_bundle_version_invalid")
    for key in ("target_workflow_names", "bundle_names"):
        names = manifest.get(key)
        if (
            not isinstance(names, list)
            or not names
            or any(not isinstance(name, str) or not name for name in names)
            or names != sorted(set(names))
        ):
            _fail("run_ref_bundle_manifest_invalid")
    targets = manifest["target_workflow_names"]
    bundle_names = manifest["bundle_names"]
    if not set(targets).issubset(bundle_names):
        _fail("run_ref_bundle_manifest_invalid")
    if not isinstance(manifest.get("closure"), list):
        _fail("run_ref_bundle_manifest_invalid")
    bundle_digests = manifest.get("bundle_digests")
    if (
        not isinstance(bundle_digests, dict)
        or set(bundle_digests) != set(bundle_names)
    ):
        _fail("run_ref_bundle_manifest_invalid")
    if not isinstance(manifest.get("workflow_closure_paths"), dict):
        _fail("run_ref_bundle_workflow_closure_invalid")
    pickle_row = manifest.get("pickle")
    if not isinstance(pickle_row, dict) or set(pickle_row) != {
        "protocol",
        "size_bytes",
        "sha256",
    }:
        _fail("run_ref_bundle_manifest_invalid")


def _validate_closure_against_manifest(
    closure: tuple[BundleCapsuleClosureBlob, ...],
    manifest_rows: object,
) -> None:
    if not isinstance(manifest_rows, list):
        _fail("run_ref_bundle_manifest_invalid")
    if _closure_manifest_rows(closure) != manifest_rows:
        _fail("run_ref_bundle_closure_mismatch")


def _validate_bundle(bundle: LoadedWorkflowBundle) -> None:
    validate_core_workflow_ast(
        bundle.core_workflow_ast,
        imports=bundle.imports,
    )
    validate_executable_workflow(bundle.ir)
    validate_workflow_runtime_plan(
        bundle.runtime_plan,
        bundle.ir,
        bundle.projection,
    )
    validate_workflow_semantic_ir(
        bundle.semantic_ir,
        ir=bundle.ir,
        projection=bundle.projection,
        runtime_plan=bundle.runtime_plan,
        surface=bundle.surface,
        imports=bundle.imports,
    )
    persisted = serialize_persisted_workflow_surface_graph(bundle)
    decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(persisted)
    )
    _result_contract_digests(bundle)


def decode_bundle_capsule(
    *,
    manifest_bytes: bytes,
    pickle_bytes: bytes,
    closure: tuple[BundleCapsuleClosureBlob, ...],
    expected_capsule_digest: str,
    expected_compiler_runtime_identity_digest: str,
) -> DecodedBundleCapsule:
    """Verify the external binding and capsule envelope before decoding."""

    if not _is_sha256(expected_capsule_digest) or (
        _sha256_bytes(manifest_bytes) != expected_capsule_digest
    ):
        _fail("run_ref_bundle_pickle_digest_mismatch")
    manifest = _strict_manifest(manifest_bytes)
    _validate_manifest_shape(manifest)
    if (
        manifest.get("compiler_runtime_identity_digest")
        != expected_compiler_runtime_identity_digest
    ):
        _fail("run_ref_bundle_compiler_identity_invalid")
    canonical_closure = _canonical_closure(closure)
    _validate_closure_against_manifest(
        canonical_closure,
        manifest.get("closure"),
    )
    workflow_closure_paths = _canonical_workflow_closure_paths(
        manifest.get("workflow_closure_paths"),
        bundle_names=manifest["bundle_names"],
        closure=canonical_closure,
    )
    pickle_row = manifest["pickle"]
    if len(pickle_bytes) > MAX_BUNDLE_PICKLE_BYTES:
        _fail("run_ref_bundle_pickle_oversize")
    if (
        pickle_row.get("size_bytes") != len(pickle_bytes)
        or pickle_row.get("sha256") != _sha256_bytes(pickle_bytes)
    ):
        _fail("run_ref_bundle_pickle_digest_mismatch")
    if (
        pickle_row.get("protocol") != _PICKLE_PROTOCOL
        or not pickle_bytes.startswith(b"\x80\x05")
    ):
        _fail("run_ref_bundle_pickle_protocol_invalid")
    try:
        decoded = pickle.loads(pickle_bytes)
    except Exception as exc:
        raise BundleCapsuleValidationError(
            "run_ref_bundle_pickle_decode_failed"
        ) from exc
    if (
        type(decoded) is not _BundleCatalog
        or decoded.schema_version != RUN_REF_BUNDLE_CAPSULE_SCHEMA
    ):
        _fail("run_ref_bundle_catalog_invalid")
    targets_value = manifest.get("target_workflow_names")
    bundle_names = manifest.get("bundle_names")
    if (
        not isinstance(targets_value, list)
        or not isinstance(bundle_names, list)
        or any(not isinstance(name, str) for name in targets_value)
        or any(not isinstance(name, str) for name in bundle_names)
        or targets_value != sorted(set(targets_value))
        or bundle_names != sorted(set(bundle_names))
    ):
        _fail("run_ref_bundle_manifest_invalid")
    catalog, targets = _validate_catalog(
        decoded.bundles_by_name,
        target_workflow_names=tuple(targets_value),
        require_mapping_proxy=True,
    )
    if _catalog_target_dsl_version(catalog) != manifest[
        "target_dsl_versions"
    ][0]:
        _fail("run_ref_bundle_version_invalid")
    if list(catalog) != bundle_names:
        _fail("run_ref_bundle_catalog_invalid")
    _require_unbound_capsule_configs(catalog)
    expected_digests = manifest.get("bundle_digests")
    if not isinstance(expected_digests, dict) or set(expected_digests) != set(catalog):
        _fail("run_ref_bundle_manifest_invalid")
    for name, bundle in catalog.items():
        _validate_bundle(bundle)
        if _bundle_digest_vector(bundle) != expected_digests.get(name):
            _fail("run_ref_bundle_digest_mismatch")
    binding = RunRefBundleCapsuleBinding(expected_capsule_digest)
    bound_catalog = _rewrite_catalog_capsule_binding(
        catalog,
        binding=binding,
    )
    bound_catalog, bound_targets = _validate_catalog(
        bound_catalog,
        target_workflow_names=targets,
        require_mapping_proxy=True,
    )
    normalized_catalog = _rewrite_catalog_capsule_binding(
        bound_catalog,
        binding=None,
    )
    for name, bundle in bound_catalog.items():
        _validate_bundle(bundle)
        if (
            _bundle_digest_vector(normalized_catalog[name])
            != expected_digests.get(name)
        ):
            _fail("run_ref_bundle_digest_mismatch")
    return DecodedBundleCapsule(
        capsule_digest=expected_capsule_digest,
        target_workflow_names=bound_targets,
        bundles_by_name=bound_catalog,
        closure=canonical_closure,
        workflow_closure_paths=workflow_closure_paths,
    )


def _validated_encoded_capsule(
    encoded: EncodedBundleCapsule,
) -> tuple[Mapping[str, Any], tuple[BundleCapsuleClosureBlob, ...]]:
    if type(encoded) is not EncodedBundleCapsule or (
        _sha256_bytes(encoded.manifest_bytes) != encoded.capsule_digest
    ):
        _fail("run_ref_bundle_directory_invalid")
    manifest = _strict_manifest(encoded.manifest_bytes)
    _validate_manifest_shape(manifest)
    closure = _canonical_closure(encoded.closure)
    _validate_closure_against_manifest(closure, manifest.get("closure"))
    pickle_row = manifest["pickle"]
    if (
        pickle_row.get("protocol") != _PICKLE_PROTOCOL
        or pickle_row.get("size_bytes") != len(encoded.pickle_bytes)
        or pickle_row.get("sha256") != _sha256_bytes(encoded.pickle_bytes)
    ):
        _fail("run_ref_bundle_directory_invalid")
    return manifest, closure


def write_bundle_capsule_directory(
    capsule_root: Path,
    encoded: EncodedBundleCapsule,
) -> None:
    """Durably materialize one exact build-produced capsule directory."""

    _manifest, closure = _validated_encoded_capsule(encoded)
    root = Path(capsule_root)
    if root.exists():
        if not root.is_dir():
            _fail("run_ref_bundle_directory_invalid")
        shutil.rmtree(root)
    root.mkdir(parents=True)
    durable_atomic_write(root / "manifest.json", encoded.manifest_bytes)
    durable_atomic_write(root / "bundles.pkl", encoded.pickle_bytes)
    for blob in closure:
        durable_atomic_write(root / "closure" / blob.path, blob.payload)
    if (
        read_bundle_capsule_directory(
            root,
            expected_capsule_digest=encoded.capsule_digest,
        )
        != encoded
    ):
        _fail("run_ref_bundle_directory_invalid")


def read_bundle_capsule_directory(
    capsule_root: Path,
    *,
    expected_capsule_digest: str,
) -> EncodedBundleCapsule:
    """Read one exact capsule directory under its parent-carried identity."""

    root = Path(capsule_root)
    try:
        manifest_bytes = (root / "manifest.json").read_bytes()
    except OSError as exc:
        raise BundleCapsuleValidationError(
            "run_ref_bundle_directory_invalid"
        ) from exc
    if (
        not _is_sha256(expected_capsule_digest)
        or _sha256_bytes(manifest_bytes) != expected_capsule_digest
    ):
        _fail("run_ref_bundle_pickle_digest_mismatch")
    manifest = _strict_manifest(manifest_bytes)
    _validate_manifest_shape(manifest)
    manifest_rows = manifest.get("closure")
    if not isinstance(manifest_rows, list):
        _fail("run_ref_bundle_directory_invalid")
    closure: list[BundleCapsuleClosureBlob] = []
    expected_files = {"manifest.json", "bundles.pkl"}
    for row in manifest_rows:
        if not isinstance(row, dict) or set(row) != {
            "path",
            "roles",
            "size_bytes",
            "sha256",
        }:
            _fail("run_ref_bundle_directory_invalid")
        path = _canonical_relative_path(row.get("path"))
        roles = row.get("roles")
        if not isinstance(roles, list) or any(
            not isinstance(role, str) for role in roles
        ):
            _fail("run_ref_bundle_directory_invalid")
        relative_file = f"closure/{path}"
        expected_files.add(relative_file)
        try:
            payload = (root / relative_file).read_bytes()
        except OSError as exc:
            raise BundleCapsuleValidationError(
                "run_ref_bundle_directory_invalid"
            ) from exc
        closure.append(
            BundleCapsuleClosureBlob(
                path=path,
                roles=tuple(roles),
                payload=payload,
            )
        )
    try:
        pickle_bytes = (root / "bundles.pkl").read_bytes()
        actual_files = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        }
    except OSError as exc:
        raise BundleCapsuleValidationError(
            "run_ref_bundle_directory_invalid"
        ) from exc
    if actual_files != expected_files:
        _fail("run_ref_bundle_directory_invalid")
    encoded = EncodedBundleCapsule(
        capsule_digest=expected_capsule_digest,
        manifest_bytes=manifest_bytes,
        pickle_bytes=pickle_bytes,
        closure=tuple(closure),
    )
    _validated_encoded_capsule(encoded)
    return encoded
