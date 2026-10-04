"""Public target2.35 admission and execution, separate from the historical matrix."""

import json
from collections import Counter

import pytest

from tests.workflow_evaluated_totality_helpers import assert_source_refusal, cell_refusal, compile_public, exercise, native_cell_value, prepare_cell, prepare_control, prepare_union, public_run
from tests.workflow_lisp_totality_matrix_sources import KNOWN_DEFECTS, RULES, SKIPPED, cells, expected
from tests.workflow_lisp_totality_matrix_locality import axes
from tests.test_workflow_lisp_closed_program_compile_cli import _compile
from tests.workflow_evaluated_totality_helpers import exercise_placement, prepare_placement, prepare_restricted_placement
from tests.test_workflow_lisp_closed_run_ref_placement import _PURE_REFUSALS
from tests.test_workflow_lisp_generic_unions_runtime import _write_probe, _write_sources
from tests.workflow_evaluated_totality_helpers import public_files


PROJECTED = [(form, position) for form, position in cells() if axes(form)[0] == "2.34"]
ADMITTED = [(form, position) for form, position in PROJECTED if cell_refusal(form, position) is None]
REFUSED = [(form, position) for form, position in PROJECTED if cell_refusal(form, position) is not None]
CONTROL_EXPECTED = {
    "effectful_if_branches": (11, ["arm-prefix 11", "arm-value 11"]),
    "pure_select_prefixes": (13, []),
    "effectful_block": (33, ["body-val 31", "after-val 33"]),
    "join_body_and_continuation": (True, ["check 1", "check 2", "check 4"]),
    "if_nested_in_if": (True, ["check 0", "check 4"]),
    "match_nested_in_if": (17, ["arm-value 17"]),
    "loop_nested_in_if": (2, ["seed 0", "next-val 0", "next-val 1", "done-val 2"]),
    "loop_budget_before_seed": (0, ["budget 3", "seed 0", "done-val 0"]),
    "loop_seed_before_budget": (0, ["seed 0", "budget 3", "done-val 0"]),
    "loop_continue_and_done": (2, ["next-val 0", "next-val 1", "done-val 2"]),
    "nested_loop_in_done": (True, ["seed 0", "budget 3", "check 1"]),
    "list_map_value_block": ([3, 4], []),
}
LEFT = {"variant": "LEFT", "payload": {"n": 7, "label": "á雪"}}
RIGHT = {"variant": "RIGHT", "count": 9}


def _historical_row(form, position):
    target, locality, base = axes(form)
    classification = "working"
    for kind, table in (("rule", RULES), ("known defect", KNOWN_DEFECTS), ("skipped", SKIPPED)):
        if (form, position) in table:
            classification = kind
    return {"id": f"{form}/{position}", "target": target, "form": base,
            "position": position, "locality": locality, "classification": classification}


def _projected_row(form, position):
    historical = _historical_row(form, position)
    refusal = cell_refusal(form, position)
    classification = "type-incompatibility" if refusal == "match_subject_not_union" else "source-rule" if refusal else "admitted"
    return dict(historical, id=f"2.35/{historical['form']}/{position}/{historical['locality']}",
                generator_id=historical["id"], historical_classification=historical["classification"],
                historical_target=historical["target"], target="2.35", classification=classification,
                helper_target="2.34" if historical["locality"] == "imported" or
                historical["form"] == "imported-wrapper-call" else None, refusal=refusal)


def test_projection_keeps_every_historical_shape_and_names_only_source_refusals(tmp_path):
    historical = [_historical_row(form, position) for form, position in cells()]
    projected = [_projected_row(form, position) for form, position in PROJECTED]
    (tmp_path / "historical-census.json").write_text(json.dumps(historical, indent=2))
    (tmp_path / "entry-235-projection.json").write_text(json.dumps(projected, indent=2))
    counts = {"historical": dict(Counter(row["classification"] for row in historical)),
              "projected": dict(Counter(row["classification"] for row in projected))}
    (tmp_path / "classification-counts.json").write_text(json.dumps(counts, indent=2))
    assert len(historical) == 530
    assert len(PROJECTED) == 275
    assert len(set(PROJECTED)) == len(PROJECTED)
    assert len(ADMITTED) + len(REFUSED) == len(PROJECTED)
    assert {row["refusal"] for row in projected} == {
        None, "match_subject_not_union", "effect_not_permitted", "loop_recur_contract_invalid"}


@pytest.mark.parametrize(("form", "position"), ADMITTED, ids=[f"{f}/{p}" for f, p in ADMITTED])
def test_public_projected_cell_returns_native_value_once(tmp_path, monkeypatch, form, position):
    files, probe = prepare_cell(tmp_path, form, position)
    _, calls = expected(form, position)
    exercise(tmp_path, files, probe, native_cell_value(form, position), calls, monkeypatch)


@pytest.mark.parametrize(("form", "position"), REFUSED, ids=[f"{f}/{p}" for f, p in REFUSED])
def test_public_projected_source_refusal_has_no_dispatch(tmp_path, form, position):
    files, probe = prepare_cell(tmp_path, form, position)
    result = _compile(files)
    assert_source_refusal(files, result, cell_refusal(form, position))
    assert not probe.with_suffix(".log").exists()
    assert not (tmp_path / ".orchestrate" / "runs").exists()


@pytest.mark.parametrize("route", ["direct", "same_module", "imported_old_source"])
@pytest.mark.parametrize("case", CONTROL_EXPECTED)
def test_public_control_keeps_selected_order_and_native_value(tmp_path, monkeypatch, case, route):
    files, probe = prepare_control(tmp_path, case, route)
    value, calls = CONTROL_EXPECTED[case]
    exercise(tmp_path, files, probe, value, calls, monkeypatch)


@pytest.mark.parametrize("route", ["direct", "same_module", "imported_old_source"])
@pytest.mark.parametrize(("case", "before", "after", "value", "calls"), [
    ("effectful_if_branches", "(if true", "(if false", 22, ["arm-prefix 22", "arm-value 22"]),
    ("join_body_and_continuation", "(check 1) (check 2) (check 3)",
     "(check 0) (check 2) (check 0)", False, ["check 0", "check 0"]),
    ("loop_budget_before_seed", "(budget 3)", "(budget 0)", 0, ["budget 0", "seed 0"]),
], ids=["other-lazy-arm", "short-circuit", "zero-budget-pure-exhaustion"])
def test_public_control_alternative_does_not_evaluate_unselected_work(tmp_path, monkeypatch, route, case, before, after, value, calls):
    files, probe = prepare_control(tmp_path, case, route, replacement=(before, after))
    exercise(tmp_path, files, probe, value, calls, monkeypatch)


@pytest.mark.parametrize("route", ["direct", "same_module", "imported_old_source"])
@pytest.mark.parametrize(("case", "code"), [
    ("effectful_loop_exhaustion", "loop_recur_contract_invalid"),
    ("effectful_list_map_body", "list_map_body_effect_forbidden"),
])
def test_public_control_refuses_pure_context_before_dispatch(tmp_path, case, code, route):
    files, probe = prepare_control(tmp_path, case, route)
    result = _compile(files)
    assert_source_refusal(files, result, code)
    assert not probe.with_suffix(".log").exists()
    assert not (tmp_path / ".orchestrate" / "runs").exists()


@pytest.mark.parametrize("imported", [False, True], ids=["same", "imported234"])
@pytest.mark.parametrize("choice", [LEFT, RIGHT], ids=["left-record", "right-scalar"])
@pytest.mark.parametrize("generic", [False, True], ids=["concrete", "applied-generic"])
def test_public_union_input_keeps_active_fields_nested_values_and_owner(tmp_path, monkeypatch, imported, choice, generic):
    inputs = {"choice": choice, "nested": [RIGHT, LEFT]}
    files, probe, input_file = prepare_union(tmp_path, imported, inputs, generic=generic)
    authority, snapshot = exercise(tmp_path, files, probe, choice,
                                  ["reflect " + choice["variant"]], monkeypatch, input_file)
    assert json.loads(probe.with_suffix(".document.json").read_text()) == inputs
    (commit,) = snapshot.active_commits.values()
    assert commit.data["value"] == inputs["choice"]
    owner = "grt/helper" if imported else "grt/entry"
    name = owner + "::Choice"
    if generic:
        name += "[" + owner + "::Payload]"
    assert authority.program.tree["result"]["name"] == name


@pytest.mark.parametrize("imported", [False, True], ids=["same", "imported234"])
@pytest.mark.parametrize("choice", [
    {"variant": "LEFT"},
    {"variant": "RIGHT", "count": "9"},
    {"variant": "UNKNOWN"},
    {"variant": "LEFT", "payload": {"n": 7, "label": "ok"}, "count": 9},
], ids=["missing-active", "wrong-scalar", "unknown-tag", "inactive-field"])
def test_public_union_input_refusal_precedes_any_dispatch(tmp_path, monkeypatch, imported, choice):
    files, probe, input_file = prepare_union(tmp_path, imported, {"choice": choice, "nested": [LEFT]})
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    result = public_run(files, input_file)
    assert result.exit_code != 0
    assert not probe.with_suffix(".log").exists()
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_public_union_owner_mismatch_refuses_before_dispatch(tmp_path):
    files, probe, _ = prepare_union(tmp_path, True, {"choice": LEFT, "nested": [LEFT]})
    source = files["source"]
    source.write_text(source.read_text().replace(
        '(call old.echo :value choice)',
        '(call old.echo :value (variant Choice LEFT :payload (record Payload :n 7 :label "local")))'))
    result = _compile(files)
    assert_source_refusal(files, result, "type_mismatch")
    assert not probe.with_suffix(".log").exists()


def test_public_imported_pre215_root_return_keeps_source_target_gate(tmp_path):
    _write_sources(tmp_path, {
        "grt/helper.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.14")
          (defmodule grt/helper) (export echo) (defworkflow echo () -> Int 7))''',
        "grt/entry.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule grt/entry) (import grt/helper :as old) (export run)
          (defworkflow run () -> Int (call old.echo)))''',
    })
    files = public_files(tmp_path, _write_probe(tmp_path, "unused", ""), ())
    result = _compile(files)
    assert_source_refusal(files, result, "workflow_root_return_target_dsl_unsupported")
    assert str(tmp_path / "grt/helper.orc") + ":" in result.stderr
    helper = tmp_path / "grt/helper.orc"
    helper.write_text(helper.read_text().replace('"2.14"', '"2.15"'))
    compile_public(files)


@pytest.mark.parametrize("locality", ["direct", "same", "imported"])
@pytest.mark.parametrize("position", ["body", "budget", "seed", "match", "map", "branch", "loop", "serial-map"])
def test_public_run_ref_placement_commits_and_reuses_exact_child(tmp_path, monkeypatch, position, locality):
    files, input_file = prepare_placement(tmp_path, position, locality)
    expected = ["placement", "second"] if position == "serial-map" else ["placement"] if position == "map" else "placement"
    count = 2 if position == "serial-map" else 1
    exercise_placement(files, input_file, expected, count, monkeypatch)


@pytest.mark.parametrize("locality", ["direct", "same", "imported"])
@pytest.mark.parametrize(("position", "code"), list(_PURE_REFUSALS.items()))
def test_public_run_ref_pure_and_shape_refusals_precede_child_dispatch(tmp_path, position, code, locality):
    files = prepare_restricted_placement(tmp_path, position, locality)
    result = _compile(files)
    assert_source_refusal(files, result, code)
    assert not list(files["workspace"].rglob("child-request.json"))
    assert not files["refs"].exists()


@pytest.mark.parametrize("form", ["t234:plain-variant", "t234:generic-variant"])
@pytest.mark.parametrize("imported", [False, True], ids=["direct", "imported234"])
def test_public_nested_union_return_boundary_keeps_whole_native_value(tmp_path, monkeypatch, form, imported):
    files, probe = prepare_cell(tmp_path, form, "return-boundary")
    if imported:
        source = files["source"]
        helper = source.with_name("helper.orc")
        helper.write_text(source.read_text().replace('"2.35"', '"2.34"')
                          .replace("(defmodule grt/entry)", "(defmodule grt/helper)")
                          .replace("(export run)", "(export Carry run)"))
        source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule grt/entry) (import grt/helper :as old) (export run)
          (defworkflow run () -> old.Carry (call old.run)))''')
    value = {"variant": "HOLD", "v": native_cell_value(form, "workflow-tail")}
    exercise(tmp_path, files, probe, value, [], monkeypatch)


@pytest.mark.parametrize("form", [
    "repro:nested-effectful-argument",
    "t234:imported:repro:nested-effectful-argument",
    "inline:repro:nested-effectful-argument",
])
def test_public_nested_effect_argument_is_once_only(tmp_path, monkeypatch, form):
    files, probe = prepare_cell(tmp_path, form, "effectful-argument")
    legacy_value, calls = expected(form, "effectful-argument")
    assert legacy_value == {"return__n": 27}
    assert calls == ["bump 26", "fetch 27"]
    _, snapshot = exercise(tmp_path, files, probe, {"n": 27}, calls, monkeypatch)
    bump, fetch = snapshot.active_commits.values()
    assert bump.data["value"] == 27
    assert fetch.data["value"] == {"n": 27}
    assert bump.data["depends_on"] == []
    assert fetch.data["depends_on"] == [bump.data["identity"]]
    if "imported" in form:
        assert '(:target-dsl "2.34")' in (tmp_path / "grt" / "helper.orc").read_text()
