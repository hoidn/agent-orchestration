"""Source-site manifest (docs/design/workflow_lisp_source_site_inspection.md §3, fixtures F-b, F-d, F-e, §9)."""

import json
import shutil
from functools import cache
from pathlib import Path

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle
from orchestrator.workflow_lisp.closed.names import canonical_type_identity
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.repl_expr import LoadedModule, typecheck_repl_expression
from orchestrator.workflow_lisp.source_sites import build_manifest, closed_perform_rows

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "workflows/examples"
FIXTURES = REPO / "tests/fixtures/workflow_lisp/source_sites"
RECORD_KEYS = {"site_id", "span", "file_digest", "owner", "kind", "result_type", "bindings", "dependencies",
    "effects", "executable_sites", "authored_calls", "eligibility"}


def compile_source(source: Path, entry: str, *, root: Path, externs: Path):
    """Compile `source` in process with the extern files found in `externs`; returns the retained build."""
    optional = {"prompt_externs_path": externs / "prompts.json", "command_boundaries_path": externs / "commands.json"}
    return prepare_closed_program_bundle(FrontendBuildRequest(
        source_path=source, source_roots=(root,), entry_workflow=entry,
        provider_externs_path=externs / "providers.json", workspace_root=REPO,
        **{name: path for name, path in optional.items() if path.exists()},
    ), source_read_trace=SourceReadTrace())


@cache
def example(stem: str, entry: str):
    result = compile_source(EXAMPLES / f"{stem}.orc", entry, root=EXAMPLES, externs=EXAMPLES / "inputs" / stem)
    return result, build_manifest(result, root=EXAMPLES, files=[Path(f"{stem}.orc")])


@cache
def fixture(stem: str, entry: str):
    result = compile_source(FIXTURES / f"{stem}.orc", entry, root=FIXTURES, externs=FIXTURES)
    return result, build_manifest(result, root=FIXTURES, files=[Path(f"{stem}.orc")])


def plan_review_execute():
    return example("plan_review_execute", "plan_review_execute::run")


def shared_procedure():
    return fixture("shared_procedure", "shared_procedure::run")


def site_of(manifest: dict, *, kind: str, line: int) -> dict:
    (site,) = [site for site in manifest["sites"].values()
        if site["kind"] == kind and site["span"]["start"]["line"] == line]
    return site


def binding_names(site: dict) -> list[str]:
    return [row["name"] for row in site["bindings"]]


def test_feedback_site_lists_task_and_draft_with_canonical_types():  # F-b
    site = site_of(plan_review_execute()[1], kind="provider-call", line=29)
    types = {row["name"]: row["type"] for row in site["bindings"]}
    assert "task" in types and types["draft"].endswith("Plan")


def test_let_and_bound_value_share_start_but_record_uses_value_node():
    # The `feedback` let and its provider call start at 29:22; the let's own type is the body's (Execution).
    site = site_of(plan_review_execute()[1], kind="provider-call", line=29)
    assert (site["result_type"]["rendered"], "feedback" in binding_names(site)) == ("Feedback", False)


def test_shadowed_name_resolves_to_innermost_identity():  # F-e
    manifest = fixture("shadowing", "shadowing::run")[1]
    outer, inner = (site_of(manifest, kind="provider-call", line=line) for line in (16, 17))
    (outer_x,), (inner_x,) = ([row for row in site["bindings"] if row["name"] == "x"] for site in (outer, inner))
    assert outer_x["identity"] != inner_x["identity"]


def test_shared_procedure_site_reports_exactly_the_closed_rows_with_its_start():  # F-d
    result, manifest = shared_procedure()
    start = site_of(manifest, kind="provider-call", line=16)["span"]["start"]
    sites = [site for site in manifest["sites"].values() if site["span"]["start"] == start]
    rows = sorted([owner, label] for owner, label, (path, line, column) in closed_perform_rows(result.program)
        if (path, line, column) == (str(FIXTURES / "shared_procedure.orc"), start["line"], start["column"]))
    assert [(site["owner"]["name"], site["executable_sites"]) for site in sites] == [
        ("procedure:shared_procedure::consult", rows)]


def test_shared_procedure_closed_rows_are_owned_by_the_procedure_only():  # F-d: no invented caller owner
    result, _ = shared_procedure()
    assert [owner for owner, _, (_, line, _) in closed_perform_rows(result.program) if line == 16] == [
        "procedure:shared_procedure::consult"]


def test_executable_sites_of_pure_composition_is_empty():
    site = site_of(shared_procedure()[1], kind="if", line=27)
    assert (site["eligibility"], site["executable_sites"]) == ("eligible", [])


def test_unprepared_definition_sites_are_marked_unavailable():
    site = site_of(shared_procedure()[1], kind="provider-call", line=32)
    assert (site["eligibility"], site["result_type"]) == ("facts-unavailable", "unavailable")


def test_site_ids_are_relative_to_root(tmp_path):
    ids = []
    for name in ("a", "b"):
        root = tmp_path / name / "nested"
        root.mkdir(parents=True)
        for file in ("shadowing.orc", "providers.json"):
            shutil.copy(FIXTURES / file, root / file)
        result = compile_source(root / "shadowing.orc", "shadowing::run", root=root, externs=root)
        ids.append(sorted(build_manifest(result, root=root, files=[Path("shadowing.orc")])["sites"]))
    assert ids[0] == ids[1] and all("@shadowing.orc:" in site_id for site_id in ids[0])


def test_unnamed_files_contribute_only_dependencies():
    manifest = example("improve_experiment_proposal", "improve_experiment_proposal::run-experiment")[1]
    paths = {site["span"]["start"]["path"] for site in manifest["sites"].values()}
    call = site_of(manifest, kind="procedure-call", line=64)
    assert (paths, call["dependencies"]["modules"]) == ({"improve_experiment_proposal.orc"}, ["std/improve"])


def test_generated_owner_sites_are_excluded_but_keep_their_closed_rows():
    result, manifest = example("improve_experiment_proposal", "improve_experiment_proposal::run-experiment")
    sites = [site for site in manifest["sites"].values() if site["span"]["start"]["line"] == 54]
    rows = [[owner, label] for owner, label, (_, line, _) in closed_perform_rows(result.program) if line == 54]
    assert [(site["eligibility"], site["executable_sites"]) for site in sites] == [("generated-definition", rows)]


def test_every_record_carries_the_contract_keys():
    assert all(set(site) == RECORD_KEYS for site in shared_procedure()[1]["sites"].values())


def test_manifest_is_json_serializable_and_keys_sorted():
    manifest = shared_procedure()[1]
    assert json.loads(json.dumps(manifest)) == manifest and list(manifest["sites"]) == sorted(manifest["sites"])


def test_result_type_equals_repl_type_for_closed_expression():
    result, manifest = shared_procedure()
    site = site_of(manifest, kind="procedure-call", line=22)  # (consult "fixed topic"): literal inputs only
    text = (FIXTURES / "shared_procedure.orc").read_text()
    expression = text[site["span"]["start"]["offset"]:site["span"]["end"]["offset"]]
    typed, _, _ = typecheck_repl_expression(expression, LoadedModule(build=result, source_path=FIXTURES))
    assert site["result_type"]["canonical"] == canonical_type_identity(typed.type_ref, typed=result.typed_program)


def test_inferred_effects_are_unavailable_because_wcc_nodes_carry_the_owner_summary():
    site = site_of(plan_review_execute()[1], kind="provider-call", line=29)
    assert site["effects"] == {"inferred": "unavailable", "restriction": "omitted"}
