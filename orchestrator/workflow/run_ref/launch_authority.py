"""Readonly live authority for one checked parent path-child launch."""

import base64
from collections.abc import Mapping
import os
from pathlib import Path
import stat

from orchestrator.run_lock import run_root_matches_fd
from orchestrator.workflow.evaluated.authority import _validate_run_ref_root, load_run_authority
from orchestrator.workflow.evaluated.machine import site_nodes
from orchestrator.workflow.evaluated.memo import _DYNAMIC_INDEX, read_memo
from orchestrator.workflow.workspace_files import WorkspaceFiles

from .config import PathProgram, encode_run_ref_static_config
from .contracts import RepositoryRevisionId, canonical_sha256
from .ledger import RunRefVisitKey, load_attempt_ledger
from .source import canonical_source_request


PATH_REQUEST_V2 = "run_ref_path_child_request.v2"


def checked_parent_authority(document):
    """Validate the exact durable triple without claiming launch permission."""
    value = document.get("parent_authority")
    if not isinstance(value, Mapping) or set(value) != {"run_root", "identity", "attempt"}:
        raise ValueError("parent authority shape is invalid")
    _validate_run_ref_root(value["run_root"])
    identity, attempt = value["identity"], value["attempt"]
    if not isinstance(identity, str) or not identity or "\0" in identity:
        raise ValueError("parent authority identity is invalid")
    if type(attempt) is not int or attempt < 1:
        raise ValueError("parent authority attempt is invalid")
    return dict(value)


def _require_root_pair(root, descriptor):
    if type(descriptor) is not int or descriptor < 0:
        raise ValueError("parent root descriptor is invalid")
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode) or not run_root_matches_fd(root, descriptor):
        raise ValueError("parent root and descriptor disagree")


def _checked_pending_site(authority, triple, step_config, files):
    nodes = site_nodes(authority.program)
    classes = {identity: node["class"] for identity, node in nodes.items()}
    memo = read_memo(authority.memo_path, classes, run_files=files)
    identity = triple["identity"]
    pending = memo.pending_starts.get(identity)
    if memo.tail or memo.terminal is not None or identity in memo.active_commits:
        raise ValueError("parent memo cannot authorize a launch")
    if pending is None or pending.data["attempt"] != triple["attempt"]:
        raise ValueError("parent started attempt disagrees")
    node = nodes.get(identity) or nodes.get(_DYNAMIC_INDEX.sub("[*]", identity))
    encoded = base64.b64encode(encode_run_ref_static_config(step_config.run_ref)).decode("ascii")
    if node is None or node["class"] != "run_ref" or node["config"] != encoded:
        raise ValueError("parent checked run-ref config disagrees")


def _validate_materialized_bindings(authority, row, document, step_config, materialized):
    from .runtime import _policy_digest

    static = step_config.run_ref
    if not isinstance(static.program, PathProgram):
        raise ValueError("checked launch requires a path program")
    source = canonical_source_request(static.source)
    revision_fields = ("normalized_locator", "resolved_commit_sha", "materializer_version",
                       "submodule_policy", "lfs_policy", "authored_setup_identity")
    revision = RepositoryRevisionId.build(**{name: source[name] for name in revision_fields})
    if materialized.repository_revision_id != revision:
        raise ValueError("checked materialized source disagrees")
    expected = {
        "run_ref_root": Path(authority.header["run_ref_root"]),
        "workspace_path": materialized.workspace_path,
        "source_digest": canonical_sha256(source),
        "program_digest": canonical_sha256(static.program.record),
        "policy_digest": _policy_digest(step_config),
        "step_config_digest": step_config.step_config_digest,
        "capsule_or_compiler_digest": static.compiler_runtime_identity_digest,
        "child_run_id": document["child_run_id"],
        "result_contract_digest": static.result_digest,
        "verified_git_tree_id": materialized.verified_git_tree.value,
        "setup_evidence_digest": materialized.setup_evidence_digest,
        "post_setup_baseline_digest": materialized.post_setup_baseline_identity.digest,
        "child_launch_digest": canonical_sha256(document),
    }
    if {name: getattr(row.bindings, name) for name in expected} != expected:
        raise ValueError("current launched bindings disagree")
    workspace = materialized.workspace_path
    if (document["clone_root"], document["child_state_dir"]) != (
        workspace.as_posix(), (workspace / ".orchestrate" / "runs").as_posix(),
    ):
        raise ValueError("child workspace or state root disagrees")


def validate_parent_launch(document, *, parent_root_fd, step_config,
                           materialized_source, expected_row_digest=None):
    """Authorize only the current checked pending start and launched ledger head."""
    if document.get("schema_version") != PATH_REQUEST_V2:
        raise ValueError("checked launch request schema is invalid")
    triple = checked_parent_authority(document)
    root = Path(triple["run_root"])
    _require_root_pair(root, parent_root_fd)
    files = WorkspaceFiles(root, root_fd=parent_root_fd)
    try:
        authority = load_run_authority(root, run_files=files)
        _validate_run_ref_root(authority.header.get("run_ref_root"))
        _checked_pending_site(authority, triple, step_config, files)
        ledger = load_attempt_ledger(root / "run-ref-attempts.jsonl", run_files=files)
        if not ledger.rows:
            raise ValueError("parent launched ledger is absent")
        row = ledger.rows[-1]
        visit = RunRefVisitKey(parent_run_id=root.name, execution_frame_id="root", call_frame_id=None,
                              step_id="root." + canonical_sha256(triple["identity"]).removeprefix("sha256:"),
                              visit_count=1)
        if (row.stage, row.status, row.visit) != ("launched", "in_progress", visit):
            raise ValueError("parent current head is not this launched visit")
        if expected_row_digest is not None and row.row_digest != expected_row_digest:
            raise ValueError("parent current head differs from acknowledged row")
        _validate_materialized_bindings(authority, row, document, step_config, materialized_source)
        _require_root_pair(root, parent_root_fd)
        return row
    finally:
        files.close()
