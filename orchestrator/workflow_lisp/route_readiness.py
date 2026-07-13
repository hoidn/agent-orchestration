"""Workflow Lisp route/readiness registry validation."""

from __future__ import annotations

import ast
import json
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.workflow_lisp.wcc.route import (
    DEFAULT_LOWERING_ROUTE,
    LoweringRoute,
    lowering_schema_for_route,
    normalize_lowering_route,
)


ROUTE_READINESS_SCHEMA_VERSION = "workflow_lisp_route_readiness_registry.v1"

SURFACE_KINDS = frozenset(
    {
        "workflow_example",
        "library_workflow",
        "test_fixture",
        "compiler_test",
        "migration_target",
        "migration_evidence",
    }
)

ROUTE_LABELS = frozenset(
    {
        "wcc_default",
        "legacy_schema1_compat",
        "historical_negative",
        "migration_candidate",
        "stale_needs_update",
    }
)

READINESS_LABELS = frozenset(
    {
        "leaf_compile_candidate",
        "leaf_runtime_candidate",
        "parent_callable_candidate",
        "family_non_regressive",
        "promotion_eligible",
    }
)

DEFAULT_REGISTRY_RELPATH = "docs/workflow_lisp_route_readiness_registry.json"
PARITY_TARGETS_RELPATH = "workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json"
PARITY_TARGETS_SCHEMA_VERSION = "workflow_lisp_migration_parity_targets.v1"
LEAF_ONLY_READINESS_LABELS = frozenset({"leaf_compile_candidate", "leaf_runtime_candidate"})
STALE_COPY_SAFETY_VALUES = frozenset({"stale", "not_copy_safe", "not_current_guidance"})
SELF_REFERENTIAL_EVIDENCE_PATHS = frozenset(
    {"tests/test_workflow_lisp_route_readiness.py"}
)
SELF_REFERENTIAL_EVIDENCE_COMMANDS = frozenset(
    {"workflow-lisp-route-readiness"}
)
DIAGNOSTIC_EVIDENCE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


class RouteReadinessError(ValueError):
    """Raised for unreadable or structurally malformed registry input."""


@dataclass(frozen=True)
class RouteReadinessEntry:
    surface_id: str
    path: str
    surface_kind: str
    route_label: str
    evidence: tuple[str, ...]
    lowering_route: str | None = None
    lowering_schema_version: int | None = None
    readiness_label: str | None = None
    entry_workflow: str | None = None
    source_roots: tuple[str, ...] = ()
    copy_safety: str | None = None
    notes: str | None = None
    owner: str | None = None
    replacement_or_retirement_path: str | None = None
    parity_constrained: bool | None = None
    raw: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RouteReadinessRegistry:
    schema_version: str
    updated: str
    surfaces: tuple[RouteReadinessEntry, ...]
    path: Path | None = None


@dataclass(frozen=True)
class RouteReadinessIssue:
    code: str
    message: str
    path: str | None = None
    surface_id: str | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"code": self.code, "message": self.message}
        if self.path is not None:
            payload["path"] = self.path
        if self.surface_id is not None:
            payload["surface_id"] = self.surface_id
        if self.field is not None:
            payload["field"] = self.field
        return payload


@dataclass(frozen=True)
class RouteReadinessValidation:
    registry: RouteReadinessRegistry
    required_surfaces: frozenset[str]
    issues: tuple[RouteReadinessIssue, ...]

    @property
    def overall_pass(self) -> bool:
        return not self.issues

    @property
    def missing_required_surfaces(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                issue.path or ""
                for issue in self.issues
                if issue.code == "route_readiness_surface_missing"
            )
        )


def load_route_readiness_registry(path: Path) -> RouteReadinessRegistry:
    """Load and parse a route/readiness registry JSON document."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RouteReadinessError(f"invalid JSON in route readiness registry `{path}`: {exc}") from exc
    except OSError as exc:
        raise RouteReadinessError(f"unable to read route readiness registry `{path}`: {exc}") from exc

    if not isinstance(payload, Mapping):
        raise RouteReadinessError("route readiness registry must be a JSON object")
    if payload.get("schema_version") != ROUTE_READINESS_SCHEMA_VERSION:
        raise RouteReadinessError(f"expected schema_version {ROUTE_READINESS_SCHEMA_VERSION}")
    updated = payload.get("updated")
    raw_surfaces = payload.get("surfaces")
    if not isinstance(updated, str) or not updated:
        raise RouteReadinessError("route readiness registry must declare non-empty `updated`")
    if not isinstance(raw_surfaces, list):
        raise RouteReadinessError("route readiness registry must declare `surfaces` as an array")

    surfaces: list[RouteReadinessEntry] = []
    for index, raw_entry in enumerate(raw_surfaces):
        if not isinstance(raw_entry, Mapping):
            raise RouteReadinessError(f"surfaces[{index}] must be a JSON object")
        surfaces.append(_parse_entry(raw_entry, index=index))

    return RouteReadinessRegistry(
        schema_version=ROUTE_READINESS_SCHEMA_VERSION,
        updated=updated,
        surfaces=tuple(surfaces),
        path=path.resolve(),
    )


def validate_route_readiness_registry(
    registry: RouteReadinessRegistry,
    repo_root: Path,
) -> RouteReadinessValidation:
    """Validate registry content against the current checkout."""

    required_surfaces = frozenset(discover_required_orc_surfaces(repo_root))
    issues: list[RouteReadinessIssue] = []
    if registry.schema_version != ROUTE_READINESS_SCHEMA_VERSION:
        issues.append(
            RouteReadinessIssue(
                code="route_readiness_registry_schema_invalid",
                message=f"schema_version must be {ROUTE_READINESS_SCHEMA_VERSION}",
            )
        )

    seen_ids: dict[str, RouteReadinessEntry] = {}
    seen_paths: dict[str, RouteReadinessEntry] = {}
    for entry in registry.surfaces:
        if entry.surface_id in seen_ids:
            issues.append(
                _issue(
                    "route_readiness_duplicate_surface_id",
                    entry,
                    f"duplicate surface_id `{entry.surface_id}`",
                    field="surface_id",
                )
            )
        else:
            seen_ids[entry.surface_id] = entry
        if entry.path in seen_paths:
            issues.append(
                _issue(
                    "route_readiness_duplicate_path",
                    entry,
                    f"duplicate path `{entry.path}`",
                    field="path",
                )
            )
        else:
            seen_paths[entry.path] = entry

        issues.extend(_validate_entry(entry, repo_root=repo_root))

    covered_paths = set(seen_paths)
    for required_path in sorted(required_surfaces - covered_paths):
        issues.append(
            RouteReadinessIssue(
                code="route_readiness_surface_missing",
                message=f"required `.orc` surface `{required_path}` is missing from route/readiness registry",
                path=required_path,
            )
        )

    return RouteReadinessValidation(
        registry=registry,
        required_surfaces=required_surfaces,
        issues=tuple(issues),
    )


def discover_required_orc_surfaces(repo_root: Path) -> set[str]:
    """Discover registry-required `.orc` surfaces in the current checkout."""

    repo_root = repo_root.resolve()
    required: set[str] = set()

    for path in (repo_root / "workflows/examples").glob("*.orc"):
        required.add(_repo_relative(path, repo_root))

    design_delta_library = repo_root / "workflows/library/lisp_frontend_design_delta"
    for path in design_delta_library.rglob("*.orc"):
        required.add(_repo_relative(path, repo_root))

    parity_targets_path = repo_root / PARITY_TARGETS_RELPATH
    if parity_targets_path.exists():
        try:
            payload = json.loads(parity_targets_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        for target in payload.get("targets", []) if isinstance(payload, Mapping) else []:
            if not isinstance(target, Mapping):
                continue
            candidate = target.get("candidate")
            if isinstance(candidate, str) and candidate.endswith(".orc"):
                required.add(_normalize_path(candidate))

    characterization_sources = repo_root / "tests/fixtures/workflow_lisp/characterization/sources"
    for path in characterization_sources.glob("*.orc"):
        required.add(_repo_relative(path, repo_root))

    valid_fixtures = repo_root / "tests/fixtures/workflow_lisp/valid"
    for path in valid_fixtures.glob("design_delta*.orc"):
        required.add(_repo_relative(path, repo_root))
    for path in (valid_fixtures / "design_delta_work_item_runtime").rglob("*.orc"):
        required.add(_repo_relative(path, repo_root))

    return required


def registry_entry_for_path(
    registry: RouteReadinessRegistry,
    path: str,
) -> RouteReadinessEntry | None:
    normalized = _normalize_path(path)
    for entry in registry.surfaces:
        if entry.path == normalized:
            return entry
    return None


def validate_migration_targets_against_route_readiness(
    targets: Sequence[object],
    registry: RouteReadinessRegistry,
    repo_root: Path,
) -> list[Mapping[str, object]]:
    """Compare migration-parity target identity fields with registry entries."""

    issues: list[dict[str, object]] = []
    for target in targets:
        candidate = getattr(target, "candidate", None)
        if not isinstance(candidate, str):
            continue
        entry = registry_entry_for_path(registry, candidate)
        workflow_family = getattr(target, "workflow_family", None)
        if entry is None:
            issues.append(
                {
                    "code": "route_readiness_migration_target_missing",
                    "message": f"migration target candidate `{candidate}` is missing from route/readiness registry",
                    "path": _normalize_path(candidate),
                    "workflow_family": workflow_family,
                }
            )
            continue

        mismatch_fields: list[str] = []
        target_readiness = getattr(target, "readiness_label", None)
        if target_readiness is not None and target_readiness != entry.readiness_label:
            mismatch_fields.append("readiness_label")
        target_route = getattr(target, "lowering_route", None)
        if target_route is not None and target_route != entry.lowering_route:
            mismatch_fields.append("lowering_route")
        target_schema = getattr(target, "lowering_schema_version", None)
        if target_schema is not None and target_schema != entry.lowering_schema_version:
            mismatch_fields.append("lowering_schema_version")

        family_roles = tuple(getattr(target, "required_family_evidence_roles", ()) or ())
        if family_roles and entry.readiness_label in LEAF_ONLY_READINESS_LABELS:
            mismatch_fields.append("required_family_evidence_roles")

        promotion = getattr(target, "promotion_eligibility", {}) or {}
        if (
            entry.readiness_label == "promotion_eligible"
            and isinstance(promotion, Mapping)
            and promotion.get("eligible_for_primary_surface") is not True
        ):
            mismatch_fields.append("promotion_eligibility.eligible_for_primary_surface")

        if mismatch_fields:
            issues.append(
                {
                    "code": "route_readiness_migration_target_mismatch",
                    "message": (
                        f"migration target `{candidate}` route/readiness identity disagrees with registry: "
                        + ", ".join(sorted(set(mismatch_fields)))
                    ),
                    "path": entry.path,
                    "surface_id": entry.surface_id,
                    "workflow_family": workflow_family,
                    "fields": sorted(set(mismatch_fields)),
                }
            )

    return issues


def compile_registered_route_case(
    registry_id: str,
    *,
    source_path: Path,
    repo_root: Path,
    default_route_check: bool = False,
    compile_func=None,
    registry_path: Path | None = None,
    **compile_kwargs: Any,
):
    """Compile a registry-covered source using its registered route."""

    registry = load_route_readiness_registry(registry_path or (repo_root / DEFAULT_REGISTRY_RELPATH))
    entry = next((entry for entry in registry.surfaces if entry.surface_id == registry_id), None)
    if entry is None:
        raise AssertionError(f"registry entry `{registry_id}` not found")

    source_relpath = _repo_relative(source_path, repo_root)
    if source_relpath != entry.path:
        raise AssertionError(
            f"registry entry `{registry_id}` points at `{entry.path}`, not `{source_relpath}`"
        )
    if entry.lowering_route is None or entry.lowering_schema_version is None:
        raise AssertionError(f"registry entry `{registry_id}` has no compile route/schema")

    if compile_func is None:
        from orchestrator.workflow_lisp.compiler import compile_stage3_module

        compile_func = compile_stage3_module

    if default_route_check:
        normalized = normalize_lowering_route(entry.lowering_route)
        if normalized is not DEFAULT_LOWERING_ROUTE:
            raise AssertionError(
                f"registry entry `{registry_id}` is `{entry.lowering_route}`, not the default route"
            )
    else:
        compile_kwargs["lowering_route"] = entry.lowering_route

    compile_result = compile_func(source_path, **compile_kwargs)
    observed_schema = _compile_result_lowering_schema(compile_result)
    if observed_schema != entry.lowering_schema_version:
        raise AssertionError(
            f"registry entry `{registry_id}` expects lowering schema "
            f"{entry.lowering_schema_version}, got {observed_schema}"
        )
    return compile_result, entry


def _parse_entry(raw_entry: Mapping[str, Any], *, index: int) -> RouteReadinessEntry:
    surface_id = _optional_string(raw_entry, "surface_id")
    path = _optional_string(raw_entry, "path")
    surface_kind = _optional_string(raw_entry, "surface_kind")
    route_label = _optional_string(raw_entry, "route_label")
    evidence = raw_entry.get("evidence")
    if surface_id is None or path is None or surface_kind is None or route_label is None:
        raise RouteReadinessError(f"surfaces[{index}] missing required string fields")
    if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
        raise RouteReadinessError(f"surfaces[{index}].evidence must be a non-empty string array")

    source_roots = raw_entry.get("source_roots", ())
    if source_roots is None:
        normalized_source_roots: tuple[str, ...] = ()
    elif isinstance(source_roots, (list, tuple)) and all(isinstance(item, str) for item in source_roots):
        normalized_source_roots = tuple(_normalize_path(item) for item in source_roots)
    else:
        raise RouteReadinessError(f"surfaces[{index}].source_roots must be a string array")

    return RouteReadinessEntry(
        surface_id=surface_id,
        path=_normalize_path(path),
        surface_kind=surface_kind,
        route_label=route_label,
        evidence=tuple(evidence),
        lowering_route=_optional_string(raw_entry, "lowering_route"),
        lowering_schema_version=_optional_int(raw_entry, "lowering_schema_version"),
        readiness_label=_optional_string(raw_entry, "readiness_label"),
        entry_workflow=_optional_string(raw_entry, "entry_workflow"),
        source_roots=normalized_source_roots,
        copy_safety=_optional_string(raw_entry, "copy_safety"),
        notes=_optional_string(raw_entry, "notes"),
        owner=_optional_string(raw_entry, "owner"),
        replacement_or_retirement_path=_optional_string(raw_entry, "replacement_or_retirement_path"),
        parity_constrained=_optional_bool(raw_entry, "parity_constrained"),
        raw=dict(raw_entry),
    )


def _validate_entry(entry: RouteReadinessEntry, *, repo_root: Path) -> list[RouteReadinessIssue]:
    issues: list[RouteReadinessIssue] = []
    if entry.surface_kind not in SURFACE_KINDS:
        issues.append(
            _issue(
                "route_readiness_label_invalid",
                entry,
                f"unknown surface_kind `{entry.surface_kind}`",
                field="surface_kind",
            )
        )
    if entry.route_label not in ROUTE_LABELS:
        issues.append(
            _issue(
                "route_readiness_label_invalid",
                entry,
                f"unknown route_label `{entry.route_label}`",
                field="route_label",
            )
        )
    if entry.readiness_label is not None and entry.readiness_label not in READINESS_LABELS:
        issues.append(
            _issue(
                "route_readiness_label_invalid",
                entry,
                f"unknown readiness_label `{entry.readiness_label}`",
                field="readiness_label",
            )
        )

    if not (repo_root / entry.path).exists():
        issues.append(_issue("route_readiness_path_unknown", entry, f"path `{entry.path}` does not exist"))

    route: LoweringRoute | None = None
    if entry.lowering_route is not None:
        try:
            route = normalize_lowering_route(entry.lowering_route)
        except ValueError:
            issues.append(
                _issue(
                    "route_readiness_route_unknown",
                    entry,
                    f"unknown lowering_route `{entry.lowering_route}`",
                    field="lowering_route",
                )
            )
    elif entry.route_label != "historical_negative":
        issues.append(
            _issue(
                "route_readiness_test_route_unpinned",
                entry,
                "route-bearing registry entries must declare lowering_route",
                field="lowering_route",
            )
        )

    if route is not None:
        if entry.lowering_schema_version is None:
            issues.append(
                _issue(
                    "route_readiness_schema_mismatch",
                    entry,
                    "lowering_schema_version is required when lowering_route is declared",
                    field="lowering_schema_version",
                )
            )
        elif entry.lowering_schema_version != lowering_schema_for_route(route):
            issues.append(
                _issue(
                    "route_readiness_schema_mismatch",
                    entry,
                    (
                        f"route `{route.value}` requires schema {lowering_schema_for_route(route)}, "
                        f"not {entry.lowering_schema_version}"
                    ),
                    field="lowering_schema_version",
                )
            )
        if entry.route_label == "wcc_default" and route is not DEFAULT_LOWERING_ROUTE:
            issues.append(
                _issue(
                    "route_readiness_default_route_mismatch",
                    entry,
                    f"wcc_default entries must use `{DEFAULT_LOWERING_ROUTE.value}`",
                    field="lowering_route",
                )
            )
        if entry.route_label == "legacy_schema1_compat" and route is not LoweringRoute.LEGACY:
            issues.append(
                _issue(
                    "route_readiness_default_route_mismatch",
                    entry,
                    "legacy_schema1_compat entries must use `legacy`",
                    field="lowering_route",
                )
            )

    if entry.route_label == "migration_candidate" and entry.readiness_label is None:
        issues.append(
            _issue(
                "route_readiness_label_invalid",
                entry,
                "migration_candidate entries must declare readiness_label",
                field="readiness_label",
            )
        )
    if entry.route_label == "stale_needs_update" and not (
        entry.owner or entry.replacement_or_retirement_path
    ):
        issues.append(
            _issue(
                "route_readiness_stale_surface_without_owner",
                entry,
                "stale_needs_update entries must declare owner or replacement_or_retirement_path",
            )
        )
    if entry.readiness_label == "promotion_eligible" and entry.copy_safety in STALE_COPY_SAFETY_VALUES:
        issues.append(
            _issue(
                "route_readiness_label_invalid",
                entry,
                "promotion_eligible entries cannot carry stale copy_safety guidance",
                field="copy_safety",
            )
        )
    for evidence in entry.evidence:
        if _is_self_referential_evidence(evidence, repo_root=repo_root):
            issues.append(
                _issue(
                    "route_readiness_evidence_self_referential",
                    entry,
                    "registry entries must cite proving evidence, not the route/readiness validator itself",
                    field="evidence",
                )
            )
        issues.extend(
            _validate_evidence_reference(
                entry,
                evidence=evidence,
                repo_root=repo_root,
            )
        )

    return issues


def _validate_evidence_reference(
    entry: RouteReadinessEntry,
    *,
    evidence: str,
    repo_root: Path,
) -> list[RouteReadinessIssue]:
    evidence_kind, evidence_path_text, selector = _classify_evidence_reference(
        evidence
    )
    if evidence_kind in {"cli_command", "diagnostic_name"}:
        return []
    if evidence_kind == "pytest_selector":
        return _validate_pytest_evidence_reference(
            entry,
            evidence_path_text=evidence_path_text,
            selector=selector or "",
            repo_root=repo_root,
        )
    if evidence_kind == "parity_target_selector":
        return _validate_parity_target_evidence_reference(
            entry,
            evidence_path_text=evidence_path_text,
            selector=selector or "",
            repo_root=repo_root,
        )
    if evidence_kind == "invalid":
        return [
            _issue(
                "route_readiness_evidence_selector_invalid",
                entry,
                f"evidence reference `{evidence}` has unsupported selector syntax",
                field="evidence",
            )
        ]

    canonical_path = _canonical_evidence_path(
        evidence_path_text,
        repo_root=repo_root,
    )
    if canonical_path is None:
        return [_invalid_evidence_path_issue(entry, evidence_path_text)]
    _, evidence_path = canonical_path
    if not evidence_path.is_file():
        return [
            _issue(
                "route_readiness_evidence_path_unknown",
                entry,
                f"evidence path `{evidence_path_text}` does not exist",
                field="evidence",
            )
        ]

    return []


def _classify_evidence_reference(
    evidence: str,
) -> tuple[str, str, str | None]:
    stripped = evidence.strip()
    if _is_supported_cli_command(stripped):
        return "cli_command", stripped, None

    selector_path, separator, selector = stripped.partition("::")
    if separator and Path(selector_path).suffix == ".py":
        return "pytest_selector", selector_path, selector
    if separator and Path(selector_path).suffix == ".json":
        return "parity_target_selector", selector_path, selector
    if separator:
        return "invalid", stripped, None
    if "/" in stripped or Path(stripped).suffix:
        return "file_path", stripped, None
    if DIAGNOSTIC_EVIDENCE_PATTERN.fullmatch(stripped):
        return "diagnostic_name", stripped, None
    return "invalid", stripped, None


def _is_supported_cli_command(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) < 2:
        return False
    if tokens[0] in {"python", "python3"} and len(tokens) >= 4:
        return tokens[1:3] in (["-m", "pytest"], ["-m", "orchestrator"])
    if tokens[0] == "pytest":
        return True
    if tokens[:2] == ["git", "diff"]:
        return True
    if tokens[0] == "orchestrator":
        return True
    return False


def _is_self_referential_evidence(evidence: str, *, repo_root: Path) -> bool:
    try:
        tokens = shlex.split(evidence)
    except ValueError:
        tokens = [evidence]
    if any(token in SELF_REFERENTIAL_EVIDENCE_COMMANDS for token in tokens):
        return True

    evidence_kind, evidence_path_text, _ = _classify_evidence_reference(evidence)
    path_candidates = (
        tokens
        if evidence_kind == "cli_command"
        else [evidence_path_text]
    )
    for candidate in path_candidates:
        path_text = candidate.partition("::")[0]
        if "/" not in path_text and not Path(path_text).suffix:
            continue
        canonical_path = _canonical_evidence_path(path_text, repo_root=repo_root)
        if (
            canonical_path is not None
            and canonical_path[0] in SELF_REFERENTIAL_EVIDENCE_PATHS
        ):
            return True
    return False


def _canonical_evidence_path(
    path_text: str,
    *,
    repo_root: Path,
) -> tuple[str, Path] | None:
    relative_path = Path(path_text)
    if relative_path.is_absolute():
        return None
    try:
        resolved_root = repo_root.resolve()
        resolved_path = (resolved_root / relative_path).resolve()
    except (OSError, RuntimeError):
        return None
    try:
        canonical_relpath = resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return None
    return canonical_relpath, resolved_path


def _invalid_evidence_path_issue(
    entry: RouteReadinessEntry,
    path_text: str,
) -> RouteReadinessIssue:
    return _issue(
        "route_readiness_evidence_path_invalid",
        entry,
        (
            f"evidence path `{path_text}` must resolve within the repository"
        ),
        field="evidence",
    )


def _validate_pytest_evidence_reference(
    entry: RouteReadinessEntry,
    *,
    evidence_path_text: str,
    selector: str,
    repo_root: Path,
) -> list[RouteReadinessIssue]:
    canonical_path = _canonical_evidence_path(
        evidence_path_text,
        repo_root=repo_root,
    )
    if canonical_path is None:
        return [_invalid_evidence_path_issue(entry, evidence_path_text)]
    _, evidence_path = canonical_path
    if not evidence_path.is_file():
        return [
            _issue(
                "route_readiness_evidence_path_unknown",
                entry,
                f"evidence path `{evidence_path_text}` does not exist",
                field="evidence",
            )
        ]

    selector_parts = selector.split("::")
    node_name, parameter_id = _split_pytest_node_name(selector_parts[-1])
    selector_parts[-1] = node_name
    if not all(selector_parts) or len(selector_parts) not in {1, 2}:
        return [
            _issue(
                "route_readiness_evidence_selector_invalid",
                entry,
                f"pytest selector `{selector}` has unsupported node syntax",
                field="evidence",
            )
        ]

    try:
        module = ast.parse(
            evidence_path.read_text(encoding="utf-8"),
            filename=evidence_path.as_posix(),
        )
    except (OSError, SyntaxError):
        return [
            _issue(
                "route_readiness_evidence_selector_invalid",
                entry,
                f"pytest evidence module `{evidence_path_text}` cannot be parsed",
                field="evidence",
            )
        ]

    function_nodes = (ast.FunctionDef, ast.AsyncFunctionDef)
    test_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    if len(selector_parts) == 1:
        if selector_parts[0].startswith("test_"):
            test_node = next(
                (
                    node
                    for node in module.body
                    if isinstance(node, function_nodes)
                    and node.name == selector_parts[0]
                ),
                None,
            )
    else:
        class_name, method_name = selector_parts
        class_node = None
        if class_name.startswith("Test") and method_name.startswith("test_"):
            class_node = next(
                (
                    node
                    for node in module.body
                    if isinstance(node, ast.ClassDef)
                    and node.name == class_name
                ),
                None,
            )
        if class_node is not None:
            test_node = next(
                (
                    child
                    for child in class_node.body
                    if isinstance(child, function_nodes)
                    and child.name == method_name
                ),
                None,
            )
    if test_node is not None and parameter_id is None:
        return []
    if test_node is not None:
        parameter_ids = _static_pytest_parameter_ids(test_node, module)
        if parameter_ids is None:
            return [
                _issue(
                    "route_readiness_evidence_selector_invalid",
                    entry,
                    (
                        f"pytest selector `{selector}` uses unsupported dynamic "
                        "parameter IDs"
                    ),
                    field="evidence",
                )
            ]
        if parameter_id in parameter_ids:
            return []
    return [
        _issue(
            "route_readiness_evidence_selector_unknown",
            entry,
            (
                f"pytest selector `{selector}` does not name a test node in "
                f"`{evidence_path_text}`"
            ),
            field="evidence",
        )
    ]


def _split_pytest_node_name(node_name: str) -> tuple[str, str | None]:
    base_name, separator, parameter_suffix = node_name.partition("[")
    if not separator:
        return node_name, None
    if not parameter_suffix.endswith("]"):
        return "", None
    return base_name, parameter_suffix[:-1]


def _static_pytest_parameter_ids(
    test_node: ast.FunctionDef | ast.AsyncFunctionDef,
    module: ast.Module,
) -> tuple[str, ...] | None:
    parametrizations = [
        decorator
        for decorator in test_node.decorator_list
        if _is_pytest_parametrize_call(decorator)
    ]
    if len(parametrizations) != 1:
        return () if not parametrizations else None

    parametrization = parametrizations[0]
    if len(parametrization.args) < 2:
        return None
    explicit_ids = next(
        (
            keyword.value
            for keyword in parametrization.keywords
            if keyword.arg == "ids"
        ),
        None,
    )
    if explicit_ids is not None:
        parameter_ids = _static_string_sequence(explicit_ids, module)
        case_count = _static_pytest_case_count(
            parametrization.args[1],
            module,
        )
        if (
            parameter_ids is None
            or case_count is None
            or len(parameter_ids) != case_count
        ):
            return None
        return _unique_static_parameter_ids(parameter_ids)

    parameter_names = _static_parameter_names(parametrization.args[0])
    if parameter_names is None or len(parameter_names) != 1:
        return None
    parameter_ids = _static_string_sequence(parametrization.args[1], module)
    return _unique_static_parameter_ids(parameter_ids)


def _static_pytest_case_count(
    node: ast.expr,
    module: ast.Module,
    *,
    resolving: frozenset[str] = frozenset(),
) -> int | None:
    if isinstance(node, (ast.List, ast.Tuple)):
        return len(node.elts)
    if not isinstance(node, ast.Name) or node.id in resolving:
        return None

    assignment_value = next(
        (
            statement.value
            for statement in module.body
            if isinstance(statement, (ast.Assign, ast.AnnAssign))
            and _assignment_names(statement) == {node.id}
        ),
        None,
    )
    if assignment_value is None:
        return None
    return _static_pytest_case_count(
        assignment_value,
        module,
        resolving=resolving | {node.id},
    )


def _unique_static_parameter_ids(
    parameter_ids: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if parameter_ids is None or len(parameter_ids) != len(set(parameter_ids)):
        return None
    return parameter_ids


def _is_pytest_parametrize_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "parametrize"
        and isinstance(function.value, ast.Attribute)
        and function.value.attr == "mark"
        and isinstance(function.value.value, ast.Name)
        and function.value.value.id == "pytest"
    )


def _static_parameter_names(node: ast.expr) -> tuple[str, ...] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return tuple(name.strip() for name in node.value.split(","))
    if isinstance(node, (ast.List, ast.Tuple)) and all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in node.elts
    ):
        return tuple(element.value for element in node.elts)
    return None


def _static_string_sequence(
    node: ast.expr,
    module: ast.Module,
    *,
    resolving: frozenset[str] = frozenset(),
) -> tuple[str, ...] | None:
    if isinstance(node, (ast.List, ast.Tuple)) and all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in node.elts
    ):
        return tuple(element.value for element in node.elts)
    if not isinstance(node, ast.Name) or node.id in resolving:
        return None

    assignment_value = next(
        (
            statement.value
            for statement in module.body
            if isinstance(statement, (ast.Assign, ast.AnnAssign))
            and _assignment_names(statement) == {node.id}
        ),
        None,
    )
    if assignment_value is None:
        return None
    return _static_string_sequence(
        assignment_value,
        module,
        resolving=resolving | {node.id},
    )


def _assignment_names(statement: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = (
        statement.targets
        if isinstance(statement, ast.Assign)
        else [statement.target]
    )
    return {target.id for target in targets if isinstance(target, ast.Name)}


def _validate_parity_target_evidence_reference(
    entry: RouteReadinessEntry,
    *,
    evidence_path_text: str,
    selector: str,
    repo_root: Path,
) -> list[RouteReadinessIssue]:
    canonical_path = _canonical_evidence_path(
        evidence_path_text,
        repo_root=repo_root,
    )
    if canonical_path is None:
        return [_invalid_evidence_path_issue(entry, evidence_path_text)]
    canonical_relpath, evidence_path = canonical_path
    if canonical_relpath != PARITY_TARGETS_RELPATH:
        return [
            _issue(
                "route_readiness_evidence_selector_invalid",
                entry,
                (
                    f"structured evidence selectors are supported only for "
                    f"`{PARITY_TARGETS_RELPATH}`"
                ),
                field="evidence",
            )
        ]
    if not evidence_path.is_file():
        return [
            _issue(
                "route_readiness_evidence_path_unknown",
                entry,
                f"evidence path `{evidence_path_text}` does not exist",
                field="evidence",
            )
        ]

    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [
            _issue(
                "route_readiness_evidence_selector_invalid",
                entry,
                f"structured evidence `{evidence_path_text}` is not valid JSON",
                field="evidence",
            )
        ]

    if not isinstance(payload, Mapping) or payload.get("schema_version") != (
        PARITY_TARGETS_SCHEMA_VERSION
    ):
        return [
            _issue(
                "route_readiness_evidence_selector_invalid",
                entry,
                (
                    f"structured evidence `{evidence_path_text}` must use "
                    f"schema `{PARITY_TARGETS_SCHEMA_VERSION}`"
                ),
                field="evidence",
            )
        ]

    targets = payload.get("targets")
    if not isinstance(targets, list):
        return [
            _issue(
                "route_readiness_evidence_selector_invalid",
                entry,
                f"structured evidence `{evidence_path_text}` must declare `targets`",
                field="evidence",
            )
        ]
    if any(
        isinstance(target, Mapping) and target.get("workflow_family") == selector
        for target in targets
    ):
        return []
    return [
        _issue(
            "route_readiness_evidence_selector_unknown",
            entry,
            (
                f"structured evidence selector `{selector}` does not name a current "
                f"target in `{evidence_path_text}`"
            ),
            field="evidence",
        )
    ]


def _compile_result_lowering_schema(result: object) -> int | None:
    entry_result = getattr(result, "entry_result", None)
    if entry_result is not None and isinstance(getattr(entry_result, "lowering_schema_version", None), int):
        return getattr(entry_result, "lowering_schema_version")
    value = getattr(result, "lowering_schema_version", None)
    if isinstance(value, int):
        return value
    return None


def _issue(
    code: str,
    entry: RouteReadinessEntry,
    message: str,
    *,
    field: str | None = None,
) -> RouteReadinessIssue:
    return RouteReadinessIssue(
        code=code,
        message=message,
        path=entry.path,
        surface_id=entry.surface_id,
        field=field,
    )


def _optional_string(mapping: Mapping[str, Any], field_name: str) -> str | None:
    value = mapping.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    raise RouteReadinessError(f"`{field_name}` must be a non-empty string when present")


def _optional_int(mapping: Mapping[str, Any], field_name: str) -> int | None:
    value = mapping.get(field_name)
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise RouteReadinessError(f"`{field_name}` must be an integer when present")


def _optional_bool(mapping: Mapping[str, Any], field_name: str) -> bool | None:
    value = mapping.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise RouteReadinessError(f"`{field_name}` must be a boolean when present")


def _normalize_path(path: str) -> str:
    return Path(path).as_posix().removeprefix("./")


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return _normalize_path(path.as_posix())
