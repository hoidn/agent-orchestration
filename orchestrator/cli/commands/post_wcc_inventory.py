"""CLI wrapper for Workflow Lisp post-WCC inventory validation."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from orchestrator.workflow_lisp.post_wcc_inventory import (
    PostWccInventoryError,
    collect_inventory_evidence,
    load_post_wcc_inventory,
    validate_post_wcc_inventory,
    validate_selector_done_preconditions,
)


def post_wcc_inventory_workflow(args: Namespace) -> int:
    inventory_path = Path(args.inventory).resolve()
    repo_root = Path.cwd()

    try:
        inventory = load_post_wcc_inventory(inventory_path)
        validation = validate_post_wcc_inventory(inventory, repo_root)
        evidence = collect_inventory_evidence(repo_root)
        done_validation = validate_selector_done_preconditions(inventory, evidence)
    except (OSError, ValueError, json.JSONDecodeError, PostWccInventoryError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    issues = [issue.to_dict() for issue in validation.issues]
    done_allowed = done_validation.overall_pass
    summary = {
        "schema_version": inventory.schema_version,
        "inventory_path": str(inventory_path),
        "surfaces_checked": len(inventory.surfaces),
        "blocking_remaining_surfaces": sum(
            1
            for surface in inventory.surfaces
            if surface.status == "remaining_post_wcc"
        ),
        "status_conflict_issues": sum(
            1
            for issue in issues
            if issue.get("code") == "post_wcc_inventory_status_conflict"
        ),
        "missing_evidence_issues": sum(
            1
            for issue in issues
            if issue.get("code") == "post_wcc_inventory_evidence_missing"
        ),
        "done_allowed": done_allowed,
        "overall_pass": validation.overall_pass and done_allowed,
        "issues": issues,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["overall_pass"] else 1
