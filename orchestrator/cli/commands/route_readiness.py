"""CLI wrapper for Workflow Lisp route/readiness registry validation."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from orchestrator.workflow_lisp.migration_parity import (
    load_parity_targets,
    validate_parity_targets_against_route_readiness,
)
from orchestrator.workflow_lisp.route_readiness import (
    PARITY_TARGETS_RELPATH,
    RouteReadinessError,
    load_route_readiness_registry,
    validate_route_readiness_registry,
)


def route_readiness_workflow(args: Namespace) -> int:
    registry_path = Path(args.registry).resolve()
    repo_root = Path.cwd()
    try:
        registry = load_route_readiness_registry(registry_path)
        validation = validate_route_readiness_registry(registry, repo_root)
        issues = [issue.to_dict() for issue in validation.issues]

        parity_targets_path = repo_root / PARITY_TARGETS_RELPATH
        if parity_targets_path.exists():
            targets = load_parity_targets(parity_targets_path)
            issues.extend(
                validate_parity_targets_against_route_readiness(
                    targets,
                    registry,
                    repo_root,
                )
            )
    except (OSError, ValueError, json.JSONDecodeError, RouteReadinessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    summary = {
        "schema_version": registry.schema_version,
        "registry_path": str(registry_path),
        "surfaces_checked": len(registry.surfaces),
        "missing_required_surfaces": sum(
            1 for issue in issues if issue.get("code") == "route_readiness_surface_missing"
        ),
        "route_schema_mismatches": sum(
            1
            for issue in issues
            if issue.get("code")
            in {
                "route_readiness_schema_mismatch",
                "route_readiness_default_route_mismatch",
            }
        ),
        "migration_target_mismatches": sum(
            1
            for issue in issues
            if issue.get("code")
            in {
                "route_readiness_migration_target_missing",
                "route_readiness_migration_target_mismatch",
            }
        ),
        "overall_pass": not issues,
        "issues": issues,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["overall_pass"] else 1
