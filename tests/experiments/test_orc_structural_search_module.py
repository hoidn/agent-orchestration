"""Whole-module admission against real compiled children; no provider runs."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from experiments.orc_structural_search import acceptance, driver, records
from experiments.orc_structural_search.candidates import compile_candidate, validate_frozen_surfaces
from experiments.orc_structural_search.config import ExperimentConfig, load_config

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "experiments/orc_structural_search/three_arm/orc"
SOURCE = (SEED / "direct.orc").read_text()
CONFIG = dict(mutable_files=("direct.orc",), mutable_definitions=("run",), condition="module", interface="I1",
              entry_workflow="direct::run", source_root=".", providers_file="providers.json",
              command_boundaries_file="commands.json", episode_wall_clock_sec=600, criterion_sha256=None,
              models={"gpt-6.1-sol": ["high", "low"]}, per_call_timeout_sec=5400)
PRIVATE = '''
  (defunion Review (ACCEPT) (REVISE (reason String)))
  (defprompt review-prompt (:fills (summary :text)) -> Review "Review {summary}")
  (defproc review ((summary String)) -> Review
    (provider-result providers.coder :prompt (review-prompt :summary summary)
      :model "gpt-6.1-sol" :effort "low" :timeout-sec 120))
'''


def cfg(**changes):
    return ExperimentConfig(**{**CONFIG, **changes})


def pair(tmp_path, child_source=SOURCE):
    roots = (tmp_path / "parent", tmp_path / "child")
    for root in roots:
        shutil.copytree(SEED, root)
    (roots[1] / "direct.orc").write_text(child_source)
    return roots


def program(root, config):
    checked = compile_candidate(root, config, runtime=REPO)
    assert checked.status == "accepted", checked
    return json.loads((root / ".orchestrate/build" / checked.build_key / "closed_program.json").read_text())


def test_module_config_loads_policy_and_legacy_needs_none(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG))
    assert load_config(path).models == CONFIG["models"]
    assert cfg(condition="joint", models=None, per_call_timeout_sec=None).models is None


@pytest.mark.parametrize("changes", [dict(models=None), dict(models={}), dict(models={"model": []}),
                                    dict(models={"model": "high"}), dict(per_call_timeout_sec=None),
                                    dict(per_call_timeout_sec=0), dict(per_call_timeout_sec=True),
                                    dict(per_call_timeout_sec=float("inf"))])
def test_module_requires_usable_call_policy(changes):
    with pytest.raises(ValueError):
        cfg(**changes)


def test_module_accepts_coordinated_private_declarations_and_routing_joint_refuses(tmp_path):
    source = SOURCE.replace("  (defworkflow run", PRIVATE + "\n  (defworkflow run")
    source = source.replace("(variant Outcome DONE :summary change.summary)",
                            '''(match (review change.summary)
                              ((ACCEPT accepted) (variant Outcome DONE :summary change.summary))
                              ((REVISE revision) (variant Outcome BLOCKED :reason revision.reason)))''')
    parent, child = pair(tmp_path, source)
    result = acceptance.judge_child(parent, child, cfg(mutable_definitions=()), runtime=REPO)
    assert result["outcome"] == "accepted", result
    assert not validate_frozen_surfaces(parent, child, cfg(condition="joint")).accepted


@pytest.mark.parametrize("declaration", ["(defunion Outcome (OTHER))", "(defproc Outcome () -> String \"x\")",
                                       "(defrecord run (value String))", "(defenum Review A B)\n(defunion Review (C))"])
def test_module_collisions_are_refused_before_compile(tmp_path, declaration, monkeypatch):
    parent, child = pair(tmp_path, SOURCE.replace("  (defworkflow run", declaration + "\n  (defworkflow run"))
    monkeypatch.setattr(acceptance, "compile_candidate", lambda *a, **k: pytest.fail("collision reached compiler"))
    result = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
    assert result["refusal_code"] == "declaration_collision", result


@pytest.mark.parametrize("before,after,code", [
    ("((task String)", "((task Bool)", "frozen_surface_changed"),
    ("  (export run)", "  (export run)\n  (import std/improve :only (Decision))", "frozen_surface_changed"),
])
def test_module_keeps_entry_contract_and_imports_frozen(tmp_path, before, after, code):
    parent, child = pair(tmp_path, SOURCE.replace(before, after))
    assert validate_frozen_surfaces(parent, child, cfg()).code == code


@pytest.mark.parametrize("file,edit,code", [
    ("common.orc", lambda s: s.replace("(summary String)", "(summary Bool)"), "frozen_surface_changed"),
    ("common.orc", lambda s: s.replace("  (defrecord Change", '(defproc extra () -> String "x")\n  (defrecord Change'), "scope_exceeded"),
    ("providers.json", lambda s: s + " ", "frozen_surface_changed"),
    ("commands.json", lambda s: s + " ", "frozen_surface_changed"),
    ("dev_check.py", lambda s: s + "\n# edited\n", "scope_exceeded"),
])
def test_module_freezes_other_files(tmp_path, file, edit, code):
    parent, child = pair(tmp_path)
    path = child / file
    path.write_text(edit(path.read_text()))
    assert validate_frozen_surfaces(parent, child, cfg()).code == code


@pytest.mark.parametrize("before,after,code", [
    ('"gpt-6.1-sol"', '"outside"', "model_not_allowed"),
    ('"gpt-6.1-sol"', 'intent', "model_not_allowed"),
    (':effort "high"', ':effort intent', "model_not_allowed"),
    (':effort "high"', ':effort "max"', "model_not_allowed"),
    (':timeout-sec 5400', ':timeout-sec 5401', "per_call_ceiling_exceeded"),
])
def test_module_checks_compiled_call_policy(tmp_path, before, after, code):
    parent, child = pair(tmp_path, SOURCE.replace(before, after))
    program(child, cfg())  # all are valid language; admission owns the restriction
    result = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
    assert result.get("refusal_code") == code, result


def test_module_refuses_fable_even_when_allowlisted(tmp_path):
    parent, child = pair(tmp_path, SOURCE.replace('"gpt-6.1-sol"', '"claude-fable-5-1"'))
    config = cfg(models={"gpt-6.1-sol": ["high"], "claude-fable-5-1": ["high"]})
    result = acceptance.judge_child(parent, child, config, runtime=REPO)
    assert result.get("refusal_code") == "model_not_allowed", result


def test_module_metrics_include_helper_body_and_provider_allocation(tmp_path):
    helper = '''(defproc helper ((task String) (repo String)) -> Change
      (loop/recur :max 2 :state (loop-state (i Int 0))
        :on-exhausted (record Change :summary "exhausted" :account "exhausted")
        (fn (state) (done (provider-result providers.coder
          :prompt (implement-prompt :task task :repo repo)
          :model "gpt-6.1-sol" :effort "high" :timeout-sec 5400)))))'''
    source = SOURCE.replace("  (defworkflow run", helper + "\n  (defworkflow run")
    start = source.index("(provider-result providers.coder", source.index("(defworkflow run"))
    stop = source.index(":timeout-sec 5400)", start) + len(":timeout-sec 5400)")
    source = source[:start] + "(helper task repo)" + source[stop:]
    parent, child = pair(tmp_path, source)
    config = cfg()
    assert acceptance.judge_child(parent, child, config, runtime=REPO)["outcome"] == "accepted"
    assert driver.skeleton(child, config) == records.skeleton_hash(source, definitions=("run", "helper"))
    assert driver.skeleton(child, config) != records.skeleton_hash(source, definitions=("run",))
    assert driver.allocation(child, config)["helper"] == ["providers.coder"]
    assert driver.skeleton(parent, config) == records.skeleton_hash(SOURCE, definitions=("run",))
    assert driver.skeleton(child, replace(config, condition="joint")) == records.skeleton_hash(source, definitions=("run",))


def test_module_removes_and_rewrites_private_definitions_without_mutable_name_list(tmp_path):
    parent, child = pair(tmp_path, SOURCE.replace("implement-prompt", "new-prompt"))
    assert validate_frozen_surfaces(parent, child, cfg()).accepted
    source = SOURCE.replace("  (defworkflow run", PRIVATE + "\n  (defworkflow run")
    (parent / "direct.orc").write_text(source)
    (child / "direct.orc").write_text(SOURCE)
    assert validate_frozen_surfaces(parent, child, cfg()).accepted


def test_module_backstop_compares_resolved_entry_params_and_result_directly(tmp_path):
    # Current source grammar requires a result annotation; exercise the postcompile backstop directly.
    parent, child = pair(tmp_path)
    before, after = program(parent, cfg()), program(child, cfg())
    assert acceptance.compiled_refusal(before, after, cfg()) is None
    for field, value in [("params", [["task", {"kind": "primitive", "name": "Bool"}]]),
                         ("result", {"kind": "primitive", "name": "String"})]:
        result = acceptance.compiled_refusal(before, {**after, field: value}, cfg())
        assert result["refusal_code"] == "frozen_surface_changed", result


def test_module_compiled_graph_comparison_ignores_own_private_types(tmp_path):
    parent, child = pair(tmp_path)
    before = program(parent, cfg())
    assert acceptance.compiled_refusal(before, {**before, "types": {**before["types"], "direct::Private": {}}}, cfg()) is None
    assert acceptance.compiled_refusal(before, {**before, "definitions": {"procedure:direct::helper": {}}}, cfg()) is None
    for key in ("definitions", "types"):
        name = "procedure:new_module::extra" if key == "definitions" else "new_module::extra"
        after = {**before, key: {**before[key], name: {}}}
        assert acceptance.compiled_refusal(before, after, cfg())["refusal_code"] == "frozen_surface_changed"


@pytest.mark.parametrize("effect", ["provider_phased", "agent", "agent_turn"])
def test_module_compiled_unsupported_effects_are_refused(tmp_path, effect):
    parent, _ = pair(tmp_path)
    before = program(parent, cfg())
    after = {**before, "body": {"k": "perform", "class": effect}}
    assert acceptance.compiled_refusal(before, after, cfg())["refusal_code"] == "unsupported_effect_shape"


def test_module_refuses_real_compiled_agent_child(tmp_path):
    source = SOURCE.replace("(let* ((change", '(let* ((session (agent providers.coder :model "gpt-6.1-sol" :effort "high"))\n (change')
    parent, child = pair(tmp_path, source)
    program(child, cfg())
    result = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
    assert result.get("refusal_code") == "unsupported_effect_shape", result


@pytest.mark.parametrize("omitted,code", [(':model "gpt-6.1-sol"', "model_not_allowed"),
                                         (':effort "high"', "model_not_allowed"),
                                         (':timeout-sec 5400', "per_call_ceiling_exceeded")])
def test_module_requires_provable_call_literals(tmp_path, omitted, code):
    parent, child = pair(tmp_path, SOURCE.replace(omitted, ""))
    result = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
    assert result.get("refusal_code") == code, result


def test_module_refuses_nonliteral_timeout_and_unknown_ceiling(tmp_path):
    parent, _ = pair(tmp_path)
    before = program(parent, cfg())
    policy = {"model": {"k": "lit", "v": "gpt-6.1-sol"}, "effort": {"k": "lit", "v": "high"},
              "timeout_sec": {"k": "lit", "v": 10}}
    for changes in [{"timeout_sec": {"k": "name", "n": "timeout"}}, {"future_ceiling": {"k": "lit", "v": 1}}]:
        after = {**before, "body": {"k": "perform", "class": "provider", "policy": {**policy, **changes}}}
        assert acceptance.compiled_refusal(before, after, cfg())["refusal_code"] == "per_call_ceiling_exceeded"


def test_module_nonliteral_loop_max_still_refused(tmp_path):
    call = '''(loop/recur :max (+ 1 1) :state (loop-state (i Int 0))
      :on-exhausted (record Change :summary "exhausted" :account "exhausted")
      (fn (state) (done (provider-result providers.coder
        :prompt (implement-prompt :task task :repo repo)
        :model "gpt-6.1-sol" :effort "high" :timeout-sec 5400))))'''
    start = SOURCE.index("(provider-result providers.coder")
    stop = SOURCE.index(":timeout-sec 5400)", start) + len(":timeout-sec 5400)")
    parent, child = pair(tmp_path, SOURCE[:start] + call + SOURCE[stop:])
    program(child, cfg())
    result = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
    assert result.get("refusal_code") == "unbounded_calls", result


def test_legacy_unbounded_refusal_still_precedes_resolved_result_check(tmp_path):
    source = SOURCE.replace("  (export run)\n", "")
    parent, child = pair(tmp_path, source.replace("    -> Outcome\n", "    -> Change\n").replace(
        "(variant Outcome DONE :summary change.summary)", "change"))
    (parent / "direct.orc").write_text(source)
    changed = (child / "direct.orc").read_text()
    start = changed.index("(provider-result providers.coder")
    stop = changed.index(":timeout-sec 5400)", start) + len(":timeout-sec 5400)")
    call = changed[start:stop]
    loop = '(loop/recur :max (+ 1 1) :state (loop-state (i Int 0)) :on-exhausted '
    loop += '(record Change :summary "exhausted" :account "exhausted") (fn (state) (done ' + call + ')))'
    (child / "direct.orc").write_text(changed[:start] + loop + changed[stop:])
    result = acceptance.judge_child(parent, child, cfg(condition="joint"), runtime=REPO)
    assert result.get("refusal_code") == "unbounded_calls", result


def test_compiler_crash_is_an_incident_but_diagnostics_are_rejection(tmp_path, monkeypatch):
    from experiments.orc_structural_search.candidates import CompileOutcome
    parent, child = pair(tmp_path)
    incidents = ["compiler_crash", "compiler_defect", "compiler_defect_loop_control_value",
                 "compiler_defect_hoisted_binding_rename", "compiler_defect_constructor_type_dropped"]
    for code, outcome in [(code, "incident") for code in incidents] + [("type_mismatch", "rejected")]:
        monkeypatch.setattr(acceptance, "compile_candidate", lambda *a, **k: CompileOutcome(
            "rejected", None, None, ({"code": code, "message": "test failure"},)))
        result = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
        assert (result["outcome"], result["diagnostics_class"]) == (outcome, code)
        assert result["diagnostics"] == [{"code": code, "message": "test failure"}]
        assert result["receipt"] is None


def test_real_compiler_defect_is_an_incident_with_complete_diagnostics(tmp_path):
    source = SOURCE.replace(":timeout-sec 5400", f":timeout-sec {10**400}")
    parent, child = pair(tmp_path, source)
    compiled = compile_candidate(child, cfg(), runtime=REPO)
    assert compiled.status == "rejected"
    assert compiled.diagnostics[0]["code"] == "compiler_defect"
    result = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
    assert (result["outcome"], result["diagnostics_class"]) == ("incident", "compiler_defect")
    assert result["diagnostics"] == list(compiled.diagnostics)
    assert result["receipt"] is None


def test_module_preserves_all_compile_diagnostics_for_repair(tmp_path):
    parent, child = pair(tmp_path, SOURCE.replace(":summary change.summary", ":summary true"))
    compiled = compile_candidate(child, cfg(), runtime=REPO)
    assert compiled.status == "rejected"
    result = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
    assert result["outcome"] == "rejected"
    assert result["diagnostics"] == list(compiled.diagnostics)


def test_module_metrics_cover_private_types_too(tmp_path):
    source = SOURCE.replace("  (defworkflow run", PRIVATE + "\n  (defworkflow run")
    _, child = pair(tmp_path, source)
    assert driver.skeleton(child, cfg()) == records.skeleton_hash(source, definitions=("run", "Review", "review"))
    assert tuple(driver.allocation(child, cfg())) == ("run", "Review", "review")


def test_module_keeps_plain_files_frozen_even_if_listed_as_mutable(tmp_path):
    parent, child = pair(tmp_path)
    (child / "dev_check.py").write_text("# edited\n")
    assert validate_frozen_surfaces(parent, child, cfg(mutable_files=("direct.orc", "dev_check.py"))).code == "scope_exceeded"


@pytest.mark.parametrize("document", ["[]", '{"status":"accepted"}', '{"status":"rejected"}',
                                     '{"status":"unexpected"}'])
def test_malformed_compiler_protocol_is_incident(tmp_path, document):
    runtime = tmp_path / "runtime" / "orchestrator"
    runtime.mkdir(parents=True)
    (runtime / "__init__.py").write_text("")
    (runtime / "__main__.py").write_text(f"print({document!r})\n")
    parent, child = pair(tmp_path)
    result = acceptance.judge_child(parent, child, cfg(), runtime=runtime.parent)
    assert (result["outcome"], result["diagnostics_class"]) == ("incident", "compiler_crash")
