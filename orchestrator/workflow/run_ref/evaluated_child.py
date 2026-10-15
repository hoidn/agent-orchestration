"""Terminal/value proofs for checked evaluated children, and the confined child run.

The path profile keeps its sole-terminal witness over `<clone>/.orchestrate/runs/<id>`.
The confined profile (`run_ref_confinement.v1`) reads the external control root that
the child header's `result_root` records and replays its committed memo.
"""

from collections.abc import Mapping
from hashlib import sha256
import os
from pathlib import Path

from orchestrator.run_lock import run_root_matches_fd
from orchestrator.workflow.evaluated.authority import load_run_authority_from_bytes, _validate_run_ref_root
from orchestrator.workflow.evaluated.machine import evaluate_closed_program, site_classes
from orchestrator.workflow.evaluated.memo import reduce_memo
from orchestrator.workflow.evaluated.replay import discover_prefix
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.type_descriptor import validate_transport_value

from .path_contracts import validate_recorded_closed_path_facts
from .contracts import canonical_json_bytes, canonical_sha256


RESULT_SCHEMA = "run_ref_path_child_result.v2"
CONFINED_TERMINAL_SCHEMA = "run_ref_confined_child_terminal.v1"
AUTHORITY_FILES = ("run.json", "closed_program.json", "memo.jsonl")


def _captured_child_authority(root, names=AUTHORITY_FILES):
    files = WorkspaceFiles(root)
    try:
        if not run_root_matches_fd(root, files.root_fd):
            raise ValueError("child root and retained descriptor disagree")
        captured = tuple(files.read(root / name) for name in names)
        if not run_root_matches_fd(root, files.root_fd):
            raise ValueError("child root changed during authority capture")
    finally:
        files.close()
    return captured


def _pure_input_value(value, descriptor):
    normalized = validate_transport_value(value, descriptor, allow_nested_structures=True)
    return coerce_evaluated_value(normalized, descriptor, context="recorded child input").json_value()


def _pure_bound_inputs(program, overrides):
    params = dict(program.tree["params"])
    if not isinstance(overrides, Mapping) or set(overrides) - set(params):
        raise ValueError("child override names differ from checked parameters")
    values = {**program.tree.get("defaults", {}), **overrides}
    if set(values) != set(params):
        raise ValueError("required child inputs are missing")
    return {name: _pure_input_value(values[name], descriptor)
            for name, descriptor in params.items()}


def _validate_child_recipe(authority, child_request, step_config, workspace, child_run_id):
    from .launch_authority import PATH_REQUEST_V2

    header = authority.header
    program = step_config.run_ref.program
    expected = {"source_roots": ["."], "entry_workflow": program.entry_name,
        "provider_externs_path": None, "prompt_externs_path": None,
        "imported_workflow_bundles_path": None, "command_boundaries_path": None,
        "input_file": None, "input_overrides": child_request["inputs"]}
    if (child_request["schema_version"], child_request["clone_root"], child_request["child_state_dir"],
        child_request["child_run_id"], child_request["expected_step_config_digest"]) != (
        PATH_REQUEST_V2, workspace.as_posix(), (workspace / ".orchestrate" / "runs").as_posix(),
        child_run_id, step_config.step_config_digest):
        raise ValueError("child request disagrees with bound workspace/config")
    _validate_run_ref_root(header.get("run_ref_root"))
    if header["workflow_file"] != program.path or canonical_json_bytes(header.get("resume_request")) != canonical_json_bytes(expected):
        raise ValueError("child own recipe differs from the complete explicit request")
    bound = _pure_bound_inputs(authority.program, child_request["inputs"])
    if canonical_json_bytes(bound) != canonical_json_bytes(header["bound_inputs"]):
        raise ValueError("child defaults and overrides differ from checked bound inputs")


def _validate_child_result(authority, child_result, step_config, child_run_id):
    expected = {"schema_version", "status", "step_config_digest", "target_workflow_name",
                "child_run_id", "workflow_outputs", "path_compile"}
    if not isinstance(child_result, Mapping) or set(child_result) != expected:
        raise ValueError("closed child result shape is invalid")
    if (child_result["schema_version"], child_result["status"], child_result["step_config_digest"],
        child_result["target_workflow_name"], child_result["child_run_id"]) != (
        RESULT_SCHEMA, "completed", step_config.step_config_digest, authority.program.tree["entry"], child_run_id):
        raise ValueError("closed child result binding is invalid")
    outputs = child_result["workflow_outputs"]
    if not isinstance(outputs, Mapping) or set(outputs) != {"__result__"}:
        raise ValueError("closed child requires one direct result")


def _validate_recorded_source(child_request, repository_revision_digest, verified_git_tree):
    from .wire import _repository_revision_from_payload

    materialized = child_request["materialized_source"]
    revision = _repository_revision_from_payload(materialized["repository_revision"])
    if revision.digest != repository_revision_digest or materialized["verified_git_tree"] != verified_git_tree:
        raise ValueError("recorded child source differs from bound revision/tree")
    if (materialized["normalized_locator"], materialized["resolved_commit_sha"]) != (
        revision.normalized_locator, revision.resolved_commit_sha):
        raise ValueError("recorded child source revision is inconsistent")


def _terminal_value(authority, memo_bytes, child_result, step_config, child_run_id):
    snapshot = reduce_memo(memo_bytes, {})
    terminal = snapshot.terminal
    if len(snapshot.entries) != 1 or terminal is None or terminal.data["outcome"] != "completed":
        raise ValueError("closed child requires its sole completed terminal")
    value = terminal.data["value"]
    descriptor = step_config.run_ref.result_descriptor["envelope"]["fields"][0]["type"]
    checked_values = (
        coerce_evaluated_value(value, authority.program.tree["result"], context="child terminal").json_value(),
        coerce_evaluated_value(value, descriptor, context="static child result").json_value(),
        evaluate_closed_program(authority.program, authority.header["bound_inputs"], run_id=child_run_id).json_value(),
        child_result["workflow_outputs"]["__result__"],
    )
    encoded = canonical_json_bytes(value)
    if any(canonical_json_bytes(other) != encoded for other in checked_values):
        raise ValueError("child terminal, checked halt and direct result disagree")
    return value, snapshot.complete_bytes


def validate_evaluated_child_terminal(*, workspace, child_run_id, child_request, child_result,
                                      step_config, repository_revision_digest, verified_git_tree):
    """Return direct checked value, logical header path and exact three-file digest."""
    workspace = Path(workspace)
    root = workspace / ".orchestrate" / "runs" / child_run_id
    header_bytes, program_bytes, memo_bytes = _captured_child_authority(root)
    authority = load_run_authority_from_bytes(root, header_bytes=header_bytes, program_bytes=program_bytes)
    _validate_child_recipe(authority, child_request, step_config, workspace, child_run_id)
    _validate_child_result(authority, child_result, step_config, child_run_id)
    _validate_recorded_source(child_request, repository_revision_digest, verified_git_tree)
    validate_recorded_closed_path_facts(child_result["path_compile"], program=authority.program, step_config=step_config,
        repository_revision_digest=repository_revision_digest, verified_git_tree=verified_git_tree)
    value, complete_bytes = _terminal_value(authority, memo_bytes, child_result, step_config, child_run_id)
    hashed = lambda payload: "sha256:" + sha256(payload).hexdigest()
    digest = canonical_sha256({"domain": "run_ref_evaluated_child_terminal.v1",
        "header_sha256": hashed(header_bytes), "program_sha256": hashed(program_bytes),
        "memo_sha256": hashed(memo_bytes[:complete_bytes])})
    return value, root / "run.json", digest


def confined_child_header(*, program, child_run_id, child_root, clone_root, run_ref_root, inputs):
    """The header facts of the child-recipe variant (no `workflow_file` source to rebuild).

    `workflow_file` names the checked child artifact in the control root, the recipe has
    no source roots, and `result_root` is the control root seen from the clone.
    """
    return {
        "run_id": child_run_id,
        "workflow_file": (Path(child_root) / "closed_program.json").as_posix(),
        "workflow_checksum": program.digest,
        "program_digest": program.digest,
        "bound_inputs": _pure_bound_inputs(program, inputs),
        "resume_request": {"source_roots": [], "entry_workflow": program.tree["entry"],
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": dict(inputs)},
        "run_ref_root": Path(run_ref_root).as_posix(),
        "result_root": os.path.relpath(child_root, clone_root),
    }


def require_confined_child_header(header, expected):
    if {name: header.get(name) for name in expected} != expected or set(header) - set(expected) - {
            "schema_version", "result_persistence_profile", "started_at", "input_digest",
            "representation", "interpreters"} or header.get("interpreters"):
        raise ValueError("confined child header differs from its child recipe")


def _confined_terminal_value(authority, memo_bytes, value_descriptor, direct_value):
    """Committed-memo witness: completed terminal, no unfinished effect, replayed halt."""
    snapshot = reduce_memo(memo_bytes, site_classes(authority.program))
    terminal = snapshot.terminal
    if (snapshot.tail or terminal is None or terminal.data["outcome"] != "completed"
            or snapshot.pending_starts or snapshot.unsettled_coordinators):
        raise ValueError("confined child requires a completed terminal with every effect settled")
    prefix = discover_prefix(authority, snapshot)
    if not prefix.halted or prefix.frontiers or prefix.fault is not None:
        raise ValueError("confined child replay does not halt over its committed effects")
    value = terminal.data["value"]
    checked_values = (
        prefix.value,
        coerce_evaluated_value(value, authority.program.tree["result"], context="child terminal").json_value(),
        coerce_evaluated_value(value, value_descriptor, context="static child result").json_value(),
        direct_value,
    )
    encoded = canonical_json_bytes(value)
    if any(canonical_json_bytes(other) != encoded for other in checked_values):
        raise ValueError("child terminal, replayed halt and direct result disagree")
    return value, snapshot.complete_bytes


def validate_confined_child_terminal(*, child_root, clone_root, expected_header, recipe_bytes,
                                     value_descriptor, direct_value):
    """Return the checked value, header path and terminal digest from the external control root."""
    child_root, clone_root = Path(child_root), Path(clone_root)
    header_bytes, program_bytes, memo_bytes, captured_recipe = _captured_child_authority(
        child_root, (*AUTHORITY_FILES, "child-recipe.json"))
    if captured_recipe != recipe_bytes:
        raise ValueError("confined child recipe differs from the provisioned recipe")
    authority = load_run_authority_from_bytes(child_root, header_bytes=header_bytes, program_bytes=program_bytes)
    require_confined_child_header(authority.header, expected_header)
    if Path(os.path.realpath(clone_root / authority.header["result_root"])) != Path(os.path.realpath(child_root)):
        raise ValueError("confined child result_root does not record its control root")
    value, complete_bytes = _confined_terminal_value(authority, memo_bytes, value_descriptor, direct_value)
    hashed = lambda payload: "sha256:" + sha256(payload).hexdigest()  # noqa: E731
    digest = canonical_sha256({"domain": CONFINED_TERMINAL_SCHEMA,
        "header_sha256": hashed(header_bytes), "program_sha256": hashed(program_bytes),
        "memo_sha256": hashed(memo_bytes[:complete_bytes]), "recipe_sha256": hashed(recipe_bytes)})
    return value, child_root / "run.json", digest


def execute_confined_child(admission, provisioned, *, run_ref_root):
    """Run or resume one pure confined child from the parent's checked child artifact.

    Authority lives only in the external control root (`provisioned.layout.child_root`),
    under that root's writer lock: the clone gets no `.orchestrate`, guard or lock entry
    and is never compiled. An existing header is reused only when it matches the child
    recipe; the ordinary memo resume then replays committed effects. Returns the direct
    terminal value.
    """
    from orchestrator.run_lock import run_writer_lock
    from orchestrator.workflow.evaluated.authority import load_run_authority, publish_run_authority
    from orchestrator.workflow.evaluated.runtime import execute_pure_resume, execute_pure_run

    from .runtime import RunRefRuntimeError

    layout = provisioned.layout
    program = admission.program
    header = confined_child_header(program=program, child_run_id=layout.child_run_id,
        child_root=layout.child_root, clone_root=layout.workspace, run_ref_root=run_ref_root,
        inputs=admission.inputs)
    with run_writer_lock(layout.child_root) as root_fd:
        files = WorkspaceFiles(layout.child_root, root_fd=root_fd)
        try:
            if files.read("child-recipe.json") != provisioned.recipe_bytes:
                raise RunRefRuntimeError("run_ref_evidence_invalid", "confined_child_recipe_disagrees")
            if not files.exists("run.json"):
                with publish_run_authority(layout.child_root, program, run_id=layout.child_run_id,
                        workflow_file=header["workflow_file"], workflow_checksum=header["workflow_checksum"],
                        bound_inputs=header["bound_inputs"], resume_request=header["resume_request"],
                        run_ref_root=header["run_ref_root"], run_files=files,
                        result_root=header["result_root"]) as authority:
                    status, value = execute_pure_run(authority, header["bound_inputs"],
                                                     run_id=layout.child_run_id, workspace=layout.workspace)
            else:
                authority = load_run_authority(layout.child_root, run_files=files)
                try:
                    require_confined_child_header(authority.header, header)
                except ValueError as exc:
                    raise RunRefRuntimeError("run_ref_evidence_invalid", "confined_child_header_disagrees") from exc
                status, value = execute_pure_resume(authority, header["bound_inputs"],
                                                    run_id=layout.child_run_id, workspace=layout.workspace)
        finally:
            files.close()
    if status != 0:
        raise RunRefRuntimeError("run_ref_child_launch_failed", "workflow_execution_failed")
    return value

