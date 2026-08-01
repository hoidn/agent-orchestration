"""Build reachable mode-1 run-ref bundle capsules from compiler artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from orchestrator.workflow.executable_ir import (
    AdjudicatedProviderStepConfig,
    ProviderStepConfig,
    RunRefStepConfig,
)
from orchestrator.workflow.assets import AssetResolutionError, WorkflowAssetResolver
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle

from .bundle_transport import (
    BundleCapsuleClosureBlob,
    EncodedBundleCapsule,
    bind_bundle_catalog_capsule,
    encode_bundle_capsule,
)
from .config import BundleProgram, RunRefBundleCapsuleBinding


class CapsuleBuildError(ValueError):
    """Closed capsule-assembly failure with a stable routing code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class AssembledBundleCapsule:
    """One encoded capsule and the controller graph bound to its identity."""

    encoded: EncodedBundleCapsule
    bound_controller: LoadedWorkflowBundle


def _fail(code: str, message: str | None = None) -> None:
    raise CapsuleBuildError(code, message)


def _bundle_name(bundle: object) -> str:
    if type(bundle) is not LoadedWorkflowBundle:
        _fail("run_ref_capsule_catalog_invalid")
    name = bundle.surface.name
    if not isinstance(name, str) or not name:
        _fail("run_ref_capsule_catalog_invalid")
    return name


def _run_ref_configs(
    bundle: LoadedWorkflowBundle,
) -> tuple[RunRefStepConfig, ...]:
    configs: list[RunRefStepConfig] = []
    for node in bundle.ir.nodes.values():
        config = getattr(node, "execution_config", None)
        if isinstance(config, RunRefStepConfig):
            configs.append(config)
    return tuple(configs)


def _closed_graph_from_root(
    root: LoadedWorkflowBundle,
) -> Mapping[str, LoadedWorkflowBundle]:
    """Index one ordinary-import graph while preserving exact object identity."""

    root_name = _bundle_name(root)
    catalog: dict[str, LoadedWorkflowBundle] = {}
    pending = [root]
    while pending:
        bundle = pending.pop()
        name = _bundle_name(bundle)
        known = catalog.get(name)
        if known is not None:
            if known is not bundle:
                _fail("run_ref_capsule_catalog_conflict")
            continue
        catalog[name] = bundle
        if not isinstance(bundle.imports, Mapping):
            _fail("run_ref_capsule_catalog_invalid")
        for alias, child in sorted(bundle.imports.items()):
            if not isinstance(alias, str) or type(child) is not LoadedWorkflowBundle:
                _fail("run_ref_capsule_catalog_invalid")
            pending.append(child)
    if root_name not in catalog:
        raise AssertionError("controller graph traversal lost its root")
    return MappingProxyType(
        {name: catalog[name] for name in sorted(catalog)}
    )


def _add_catalog_rows(
    destination: dict[str, LoadedWorkflowBundle],
    rows: object,
) -> None:
    if not isinstance(rows, Mapping):
        _fail("run_ref_capsule_catalog_invalid")
    for canonical_name, bundle in rows.items():
        if (
            not isinstance(canonical_name, str)
            or type(bundle) is not LoadedWorkflowBundle
            or _bundle_name(bundle) != canonical_name
        ):
            _fail("run_ref_capsule_catalog_invalid")
        if canonical_name in destination:
            _fail("run_ref_capsule_catalog_conflict")
        destination[canonical_name] = bundle


def _flatten_local_catalog(value: object) -> Mapping[str, LoadedWorkflowBundle]:
    """Accept a neutral mapping or structurally flatten a linked compile result."""

    if isinstance(value, Mapping):
        destination: dict[str, LoadedWorkflowBundle] = {}
        _add_catalog_rows(destination, value)
        return MappingProxyType(
            {name: destination[name] for name in sorted(destination)}
        )

    compiled_results = getattr(value, "compiled_results_by_name", None)
    entry_result = getattr(value, "entry_result", None)
    if not isinstance(compiled_results, Mapping) or entry_result is None:
        _fail("run_ref_capsule_catalog_invalid")
    current_results = dict(compiled_results)
    graph = getattr(value, "graph", None)
    entry_module_name = getattr(graph, "entry_module_name", None)
    if isinstance(entry_module_name, str):
        current_results[entry_module_name] = entry_result
    elif not any(result is entry_result for result in current_results.values()):
        current_results["<entry>"] = entry_result

    destination = {}
    for module_name in sorted(current_results):
        result = current_results[module_name]
        _add_catalog_rows(
            destination,
            getattr(result, "validated_bundles", None),
        )
    return MappingProxyType(
        {name: destination[name] for name in sorted(destination)}
    )


def _available_catalog(
    local_catalog: object,
    imported_catalogs: Sequence[object],
) -> Mapping[str, LoadedWorkflowBundle]:
    destination = dict(_flatten_local_catalog(local_catalog))
    for item in imported_catalogs:
        rows = item if isinstance(item, Mapping) else getattr(
            item,
            "bundle_catalog",
            None,
        )
        _add_catalog_rows(destination, rows)
    return MappingProxyType(
        {name: destination[name] for name in sorted(destination)}
    )


def _require_unbound_mode_one(config: RunRefStepConfig) -> None:
    if (
        isinstance(config.run_ref.program, BundleProgram)
        and config.capsule_binding is not None
    ):
        _fail("run_ref_capsule_prebound_config")


def _reachable_capsule_catalog(
    *,
    selected_bundle: LoadedWorkflowBundle,
    controller_catalog: Mapping[str, LoadedWorkflowBundle],
    available: Mapping[str, LoadedWorkflowBundle],
) -> tuple[
    Mapping[str, LoadedWorkflowBundle],
    tuple[str, ...],
    str,
]:
    target_names: set[str] = set()
    compiler_identities: set[str] = set()
    pending: list[str] = []

    def observe(config: RunRefStepConfig) -> None:
        _require_unbound_mode_one(config)
        program = config.run_ref.program
        if not isinstance(program, BundleProgram):
            return
        target_names.add(program.workflow_name)
        compiler_identities.add(
            config.run_ref.compiler_runtime_identity_digest
        )
        pending.append(program.workflow_name)

    for bundle in controller_catalog.values():
        for config in _run_ref_configs(bundle):
            observe(config)
    if not target_names:
        raise AssertionError("reachable-catalog assembly requires a mode-1 target")

    reached: dict[str, LoadedWorkflowBundle] = {}
    selected_name = _bundle_name(selected_bundle)
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        if name == selected_name:
            if available.get(name) is None:
                _fail("run_ref_capsule_workflow_missing")
            bundle = selected_bundle
        else:
            bundle = available.get(name)
        if bundle is None:
            _fail("run_ref_capsule_workflow_missing")
        if type(bundle) is not LoadedWorkflowBundle or _bundle_name(bundle) != name:
            _fail("run_ref_capsule_catalog_invalid")
        reached[name] = bundle

        for alias, child in sorted(bundle.imports.items()):
            if not isinstance(alias, str) or type(child) is not LoadedWorkflowBundle:
                _fail("run_ref_capsule_catalog_invalid")
            child_name = _bundle_name(child)
            available_child = (
                selected_bundle
                if child_name == selected_name
                else available.get(child_name)
            )
            if available_child is None:
                _fail("run_ref_capsule_workflow_missing")
            if available_child is not child:
                original_selected = available.get(selected_name)
                if not (
                    child_name == selected_name
                    and original_selected is child
                ):
                    _fail("run_ref_capsule_catalog_conflict")
            pending.append(child_name)
        for config in _run_ref_configs(bundle):
            observe(config)

    if len(compiler_identities) != 1:
        _fail("run_ref_capsule_compiler_identity_conflict")

    import_storage_by_name: dict[str, dict[str, LoadedWorkflowBundle]] = {
        name: {} for name in reached
    }
    rebuilt: dict[str, LoadedWorkflowBundle] = {
        name: replace(
            bundle,
            imports=MappingProxyType(import_storage_by_name[name]),
        )
        for name, bundle in reached.items()
    }
    for name, bundle in reached.items():
        for alias, child in sorted(bundle.imports.items()):
            child_name = _bundle_name(child)
            if child_name not in rebuilt:
                _fail("run_ref_capsule_workflow_missing")
            import_storage_by_name[name][alias] = rebuilt[child_name]
    canonical = MappingProxyType(
        {name: rebuilt[name] for name in sorted(rebuilt)}
    )
    return (
        canonical,
        tuple(sorted(target_names)),
        next(iter(compiler_identities)),
    )


def _source_inputs(
    value: object,
) -> tuple[Mapping[Path, bytes], Mapping[Path, str] | None]:
    if isinstance(value, Mapping):
        raw_value = value
        revision_value = None
    else:
        raw_value = getattr(value, "raw_bytes_by_path", None)
        revision_value = getattr(value, "revision_vector", None)
    if not isinstance(raw_value, Mapping):
        _fail("run_ref_capsule_source_invalid")

    raw: dict[Path, bytes] = {}
    for path_value, payload in raw_value.items():
        if not isinstance(path_value, (str, Path)) or not isinstance(payload, bytes):
            _fail("run_ref_capsule_source_invalid")
        path = Path(path_value).resolve()
        previous = raw.get(path)
        if previous is not None and previous != payload:
            _fail("run_ref_capsule_source_conflict")
        raw[path] = payload

    if revision_value is None:
        revisions = None
    else:
        if not isinstance(revision_value, (tuple, list)):
            _fail("run_ref_capsule_source_invalid")
        mutable_revisions: dict[Path, str] = {}
        for row in revision_value:
            if (
                not isinstance(row, (tuple, list))
                or len(row) != 2
                or not isinstance(row[0], (str, Path))
                or not isinstance(row[1], str)
            ):
                _fail("run_ref_capsule_source_invalid")
            path = Path(row[0]).resolve()
            previous = mutable_revisions.get(path)
            if previous is not None and previous != row[1]:
                _fail("run_ref_capsule_source_conflict")
            mutable_revisions[path] = row[1]
        revisions = MappingProxyType(mutable_revisions)
    return MappingProxyType(raw), revisions


def _canonical_source_relative_path(
    *,
    physical_path: Path,
    source_root: Path,
) -> str:
    try:
        relative = physical_path.relative_to(source_root)
    except ValueError as exc:
        raise CapsuleBuildError("run_ref_capsule_source_outside_root") from exc
    value = relative.as_posix()
    parsed = PurePosixPath(value)
    if (
        not value
        or parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        _fail("run_ref_capsule_source_invalid")
    return f"source/{value}"


def _asset_paths(bundle: LoadedWorkflowBundle) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for node in bundle.ir.nodes.values():
        for config in _nested_provider_configs(
            getattr(node, "execution_config", None)
        ):
            if config.asset_file is not None:
                if not isinstance(config.asset_file, str):
                    _fail("run_ref_capsule_asset_invalid")
                rows.append((config.asset_file, "prompt_asset"))
            depends_on = config.asset_depends_on
            if not isinstance(depends_on, (tuple, list)):
                _fail("run_ref_capsule_asset_invalid")
            for value in depends_on:
                if not isinstance(value, str):
                    _fail("run_ref_capsule_asset_invalid")
                rows.append((value, "workflow_asset"))
    return tuple(rows)


def _nested_provider_configs(
    value: object,
) -> tuple[ProviderStepConfig | AdjudicatedProviderStepConfig, ...]:
    """Find direct and member-carried provider configs without prompt schemas."""

    found: list[ProviderStepConfig | AdjudicatedProviderStepConfig] = []
    pending = [value]
    seen: set[int] = set()
    while pending:
        candidate = pending.pop()
        identity = id(candidate)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(
            candidate,
            (ProviderStepConfig, AdjudicatedProviderStepConfig),
        ):
            found.append(candidate)
            continue
        if isinstance(candidate, Mapping):
            pending.extend(candidate.values())
            continue
        if isinstance(candidate, (tuple, list)):
            pending.extend(candidate)
            continue
        for attribute in (
            "provider_config",
            "worker",
            "supervisor",
            "members",
        ):
            nested = getattr(candidate, attribute, None)
            if nested is not None:
                pending.append(nested)
    return tuple(found)


def _resolve_asset(
    *,
    authored_path: str,
    workflow_path: Path,
    source_root: Path,
) -> tuple[Path, str]:
    if "\\" in authored_path:
        _fail("run_ref_capsule_asset_invalid")
    try:
        physical = WorkflowAssetResolver(workflow_path).resolve(authored_path)
    except AssetResolutionError as exc:
        raise CapsuleBuildError("run_ref_capsule_asset_invalid") from exc
    closure_path = _canonical_source_relative_path(
        physical_path=physical,
        source_root=source_root,
    )
    return physical, closure_path


def _build_closure(
    bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    *,
    source_input: object,
) -> tuple[
    tuple[BundleCapsuleClosureBlob, ...],
    Mapping[str, str],
]:
    raw_bytes, revisions = _source_inputs(source_input)
    blobs: dict[str, tuple[bytes, set[str]]] = {}
    workflow_paths: dict[str, str] = {}
    asset_cache: dict[Path, bytes] = {}

    def add_blob(path: str, payload: bytes, role: str) -> None:
        previous = blobs.get(path)
        if previous is None:
            blobs[path] = (payload, {role})
            return
        if previous[0] != payload:
            _fail("run_ref_capsule_closure_collision")
        previous[1].add(role)

    for name, bundle in sorted(bundles_by_name.items()):
        workflow_path = Path(bundle.provenance.workflow_path).resolve()
        source_root = Path(bundle.provenance.source_root).resolve()
        payload = raw_bytes.get(workflow_path)
        if payload is None:
            _fail("run_ref_capsule_source_missing")
        if revisions is not None:
            expected = revisions.get(workflow_path)
            observed = f"sha256:{hashlib.sha256(payload).hexdigest()}"
            if expected is None or expected != observed:
                _fail("run_ref_capsule_source_digest_mismatch")
        closure_path = _canonical_source_relative_path(
            physical_path=workflow_path,
            source_root=source_root,
        )
        add_blob(closure_path, payload, "orc")
        workflow_paths[name] = closure_path

        for authored_path, role in _asset_paths(bundle):
            physical, asset_closure_path = _resolve_asset(
                authored_path=authored_path,
                workflow_path=workflow_path,
                source_root=source_root,
            )
            asset_payload = asset_cache.get(physical)
            if asset_payload is None:
                try:
                    asset_payload = physical.read_bytes()
                except OSError as exc:
                    raise CapsuleBuildError(
                        "run_ref_capsule_asset_read_failed"
                    ) from exc
                asset_cache[physical] = asset_payload
            add_blob(asset_closure_path, asset_payload, role)

    closure = tuple(
        BundleCapsuleClosureBlob(
            path=path,
            roles=tuple(sorted(roles)),
            payload=payload,
        )
        for path, (payload, roles) in sorted(blobs.items())
    )
    return closure, MappingProxyType(
        {name: workflow_paths[name] for name in sorted(workflow_paths)}
    )


def assemble_bundle_capsule(
    selected_bundle: LoadedWorkflowBundle,
    *,
    local_catalog: object,
    imported_catalogs: tuple[object, ...] = (),
    raw_bytes_by_path: object,
    lowering_schema_version: int,
) -> AssembledBundleCapsule | None:
    """Assemble the exact mode-1 closure reachable from ``selected_bundle``."""

    if type(selected_bundle) is not LoadedWorkflowBundle:
        _fail("run_ref_capsule_catalog_invalid")
    controller_catalog = _closed_graph_from_root(selected_bundle)
    if not any(
        isinstance(config.run_ref.program, BundleProgram)
        for bundle in controller_catalog.values()
        for config in _run_ref_configs(bundle)
    ):
        return None
    if not isinstance(imported_catalogs, Sequence) or isinstance(
        imported_catalogs,
        (str, bytes),
    ):
        _fail("run_ref_capsule_catalog_invalid")
    available = _available_catalog(local_catalog, imported_catalogs)
    capsule_catalog, target_names, compiler_identity = (
        _reachable_capsule_catalog(
            selected_bundle=selected_bundle,
            controller_catalog=controller_catalog,
            available=available,
        )
    )
    closure, workflow_closure_paths = _build_closure(
        capsule_catalog,
        source_input=raw_bytes_by_path,
    )
    encoded = encode_bundle_capsule(
        capsule_catalog,
        target_workflow_names=target_names,
        closure=closure,
        workflow_closure_paths=workflow_closure_paths,
        compiler_runtime_identity_digest=compiler_identity,
        lowering_schema_version=lowering_schema_version,
    )
    binding = RunRefBundleCapsuleBinding(encoded.capsule_digest)
    bound_controller_catalog = bind_bundle_catalog_capsule(
        controller_catalog,
        binding=binding,
    )
    return AssembledBundleCapsule(
        encoded=encoded,
        bound_controller=bound_controller_catalog[
            _bundle_name(selected_bundle)
        ],
    )
