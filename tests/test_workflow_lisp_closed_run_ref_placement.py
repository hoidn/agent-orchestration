from __future__ import annotations

import json
import base64

import pytest

from orchestrator.workflow.evaluated.machine import site_nodes
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_run_ref_child import _build_path_fixture, _git
from tests.workflow_lisp_closed_program_helpers import install


def _path_form(revision):
    return f'''(run-ref
      :source (:repo {json.dumps(revision.normalized_locator)} :commit "{revision.resolved_commit_sha}")
      :program (:path "candidate.orc" :entry run) :inputs (:payload payload) :returns String
      :policy (:environment :deterministic-effect-free :setup ()))'''


def _placement_source(root, position, locality, *, twice=False, map_shape="single"):
    fixture = _build_path_fixture(root, case="placement")
    revision = fixture.materialized_source.repository_revision_id
    perform = f'''(run-ref
      :source (:repo {json.dumps(revision.normalized_locator)} :commit "{revision.resolved_commit_sha}")
      :program (:path "candidate.orc" :entry run)
      :inputs (:payload payload) :returns String
      :policy (:environment :deterministic-effect-free :setup ()))'''
    helper_body = f'(let* ((child {perform})) child.value)'
    if twice:
        helper_body = f'(let* ((first {perform}) (second {perform})) second.value)'
    helper = f'''(defproc invoke ((payload String)) -> String
      :effects ((runs-ref run)) :lowering inline {helper_body})'''
    imports = ""
    sources = {}
    if locality == "imported":
        imports = '(import placement/helper :only (invoke))'
        sources["placement/helper.orc"] = f'''(workflow-lisp
          (:language "0.1") (:target-dsl "2.34")
          (defmodule placement/helper) (export invoke) {helper})'''
        helper = ""
    elif locality == "direct":
        helper = ""
    value = f'(let* ((child {perform})) child.value)' if locality == "direct" else '(invoke payload)'
    bodies = {
        "body": f'''(loop/recur :max 1 :state (loop-state (current String payload))
          :on-exhausted "exhausted" (fn (state) (done {value})))''',
        "budget": f'''(loop/recur :max (let* ((limit {value})) 1)
          :state (loop-state (current String payload))
          :on-exhausted "exhausted" (fn (state) (done state.current)))''',
        "seed": f'''(loop/recur :max 1 :state (loop-state (current String {value}))
          :on-exhausted "exhausted" (fn (state) (done state.current)))''',
        "match": f'''(match (let* ((child-value {value}))
          (variant Choice YES :value child-value)) ((YES chosen) chosen.value))''',
        "map": f'''(let* ((children (list/map-effect ((item (list payload))) :max 1
          {perform.replace(":payload payload", ":payload item") if locality == "direct" else "(invoke item)"})))
          (list/map ((child children)) {"child.value" if locality == "direct" else "child"}))''',
    }
    if map_shape != "single":
        effect_map = f'''(list/map-effect ((item (list payload))) :max 1
          {perform.replace(":payload payload", ":payload item")})'''
        second = effect_map
        if map_shape == "carrier":
            second = second.replace("(list payload)", "first").replace(
                ":payload item", ":payload item.value")
        bodies["map"] = f'''(let* ((first {effect_map}) (second {second}))
          (list/map ((child second)) child.value))'''
    result = "List[String]" if position == "map" else "String"
    sources["placement/entry.orc"] = f'''(workflow-lisp
      (:language "0.1") (:target-dsl "2.35")
      (defmodule placement/entry) {imports} (export run)
      (defunion Choice (YES (value String))) {helper}
      (defworkflow run ((payload String)) -> {result} {bodies[position]}))'''
    return install(root, sources, entry_path="placement/entry.orc"), revision


@pytest.mark.parametrize("position", ["body", "budget", "seed", "match", "map"])
@pytest.mark.parametrize("locality", ["direct", "same", "imported"])
def test_closed_path_run_ref_placement_round_trip(tmp_path, position, locality):
    source, revision = _placement_source(tmp_path, position, locality)
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    restored = ClosedProgram.from_artifact(built.artifact_path.read_text())
    assert (restored.digest, restored.tree, restored.sites) == (
        built.program.digest, built.program.tree, built.program.sites)
    [(identity, node)] = site_nodes(restored).items()
    config = decode_run_ref_static_config(base64.b64decode(node["config"]))
    assert config.source.commit == revision.resolved_commit_sha
    assert [row.name for row in config.inputs] == ["payload"]
    assert config.inputs[0].type_descriptor == {"kind": "primitive", "name": "String"}
    assert config.generated_result_type.startswith("RunRefResult$")
    assert ("[*]" in identity) == (position in {"body", "map"})
    _assert_placement_call_frame(restored, locality, identity)


def _assert_placement_call_frame(program, locality, identity):
    calls = [node for node in _ast_nodes(program.tree["body"]) if node.get("k") == "call"]
    if locality == "direct":
        assert calls == []
        return
    [call] = calls
    module = "placement/helper" if locality == "imported" else "placement/entry"
    assert program.tree["definitions"][call["callee"]]["key"][:3] == [module, "procedure", "invoke"]
    assert call["frame"] in identity


@pytest.mark.parametrize("position", ["budget", "seed"])
@pytest.mark.parametrize("in_map", [False, True])
def test_inline_inner_loop_run_ref_keeps_specialized_boundary(tmp_path, position, in_map):
    fixture = _build_path_fixture(tmp_path, case="inline-inner-loop")
    revision = fixture.materialized_source.repository_revision_id
    projected = f'(let* ((child {_path_form(revision)})) child.value)'
    budget = f'(let* ((ignored {projected})) 1)' if position == "budget" else "1"
    seed = projected if position == "seed" else "payload"
    helper = f'''(defproc invoke ((payload String)) -> String
      :effects ((runs-ref run)) :lowering inline
      (loop/recur :max {budget} :state (loop-state (current String {seed}))
        :on-exhausted "exhausted" (fn (state) (done state.current))))'''
    body = '(list/map-effect ((item (list payload))) :max 1 (invoke item))' if in_map else '(invoke payload)'
    result = "List[String]" if in_map else "String"
    source = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule placement/inline_loop) (export run) {helper}
      (defworkflow run ((payload String)) -> {result} {body}))''')
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    restored = ClosedProgram.from_artifact(built.artifact_path.read_text())
    assert (restored.digest, restored.tree, restored.sites) == (
        built.program.digest, built.program.tree, built.program.sites)
    [(identity, node)] = site_nodes(restored).items()
    config = decode_run_ref_static_config(base64.b64decode(node["config"]))
    assert config.source.commit == revision.resolved_commit_sha
    assert ("[*]" in identity) == in_map


@pytest.mark.parametrize("twice", [False, True])
def test_imported_inline_chain_keeps_inner_loop_effect_cardinality(tmp_path, twice):
    source, revision = _placement_source(tmp_path, "map", "imported")
    projected = f'(let* ((child {_path_form(revision)})) child.value)'
    result = projected if twice else 'state.current'
    helper = tmp_path / "placement" / "helper.orc"
    helper.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule placement/helper) (export invoke)
      (defproc leaf ((payload String)) -> String :effects ((runs-ref run)) :lowering inline
        (loop/recur :max 1 :state (loop-state (current String {projected}))
          :on-exhausted "exhausted" (fn (state) (done {result}))))
      (defproc invoke ((payload String)) -> String :effects ((runs-ref run))
        :lowering inline (leaf payload)))''')
    request = FrontendBuildRequest(
        source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path)
    if twice:
        with pytest.raises(LispFrontendCompileError) as caught:
            build_closed_program_bundle(request)
        assert caught.value.diagnostics[0].code == "list_map_effect_body_unsupported"
        return
    built = build_closed_program_bundle(request)
    restored = ClosedProgram.from_artifact(built.artifact_path.read_text())
    assert (restored.digest, restored.tree, restored.sites) == (
        built.program.digest, built.program.tree, built.program.sites)
    [(identity, node)] = site_nodes(restored).items()
    config = decode_run_ref_static_config(base64.b64decode(node["config"]))
    assert config.source.commit == revision.resolved_commit_sha
    assert "[*]" in identity
    _assert_imported_inline_chain_frames(restored, identity)


def _assert_imported_inline_chain_frames(program, identity):
    definitions = program.tree["definitions"]
    bodies = [program.tree["body"], *(definition["body"] for definition in definitions.values())]
    calls = [node for body in bodies for node in _ast_nodes(body) if node.get("k") == "call"]
    assert {tuple(definitions[call["callee"]]["key"][:3]) for call in calls} == {
        ("placement/helper", "procedure", "invoke"), ("placement/helper", "procedure", "leaf")}
    assert all(call["frame"] in identity for call in calls)


def test_closed_effect_map_rejects_two_run_refs_after_specialization(tmp_path):
    source, _ = _placement_source(tmp_path, "map", "same", twice=True)
    with pytest.raises(LispFrontendCompileError) as caught:
        build_closed_program_bundle(FrontendBuildRequest(
            source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    assert caught.value.diagnostics[0].code == "list_map_effect_body_unsupported"


@pytest.mark.parametrize("shape", ["repeated", "carrier"])
def test_direct_map_result_keeps_each_lexical_producer(tmp_path, shape):
    source, _ = _placement_source(tmp_path, "map", "direct", map_shape=shape)
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    restored = ClosedProgram.from_artifact(built.artifact_path.read_text())
    nodes = list(site_nodes(restored).values())
    assert len(nodes) == 2
    configs = [decode_run_ref_static_config(base64.b64decode(node["config"]))
               for node in nodes]
    assert len({config.generated_result_type for config in configs}) == 2
    assert len({config.site_digest for config in configs}) == 2


@pytest.mark.parametrize("kind", ["command", "provider"])
def test_closed_effect_map_keeps_existing_effect_boundaries(tmp_path, kind):
    from tests.test_workflow_lisp_closed_program_compile_cli import _write_workspace

    files = _write_workspace(tmp_path)
    effects = {
        "command": '(command-result probe_revise :argv ("python" "probe_revise.py" item "tidy" "fb") :returns String)',
        "provider": '(provider-result reviewer :prompt prompt :inputs (item) :returns String)',
    }
    source = install(tmp_path, f'''(workflow-lisp
      (:language "0.1") (:target-dsl "2.35") (defmodule placement/existing) (export run)
      (defworkflow run () -> List[String]
        (list/map-effect ((item (list "payload"))) :max 1 {effects[kind]})))''')
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=source, workspace_root=tmp_path,
        provider_externs_path=files["providers"], prompt_externs_path=files["prompts"],
        command_boundaries_path=files["commands"]))
    restored = ClosedProgram.from_artifact(built.artifact_path.read_text())
    assert [node["class"] for node in site_nodes(restored).values()] == [kind]


def test_closed_effect_map_keeps_workflow_call_as_one_boundary(tmp_path):
    source, _ = _placement_source(tmp_path, "map", "same", twice=True)
    text = source.read_text().replace(
        "(defproc invoke ((payload String)) -> String\n      :effects ((runs-ref run)) :lowering inline",
        "(defworkflow invoke ((payload String)) -> String",
    ).replace("(invoke item)", "(call invoke :payload item)")
    source.write_text(text)
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    assert len(site_nodes(ClosedProgram.from_artifact(built.artifact_path.read_text()))) == 2


@pytest.mark.parametrize("position", ["budget", "match"])
def test_placement_projects_actual_typed_child_result(tmp_path, position):
    fixture = _build_path_fixture(tmp_path, case="typed")
    repository = tmp_path / "repository-typed"
    result_type = {"budget": "Int", "match": "Choice"}[position]
    child_body = {"budget": "count", "match": '(variant Choice YES :value payload)'}[position]
    child_source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule placement/child) (export run Choice)
      (defunion Choice (YES (value String)))
      (defworkflow run ((payload String) (count Int :default 1)) -> {result_type}
        {child_body}))'''
    (repository / "candidate.orc").write_text(child_source)
    _git(repository, "add", "candidate.orc")
    _git(repository, "-c", "user.name=Run Ref Child Test", "-c",
         "user.email=run-ref-child@example.invalid", "commit", "--quiet", "-m", "typed child")
    commit = _git(repository, "rev-parse", "HEAD")
    locator = fixture.materialized_source.repository_revision_id.normalized_locator
    perform = f'''(run-ref :source (:repo {json.dumps(locator)} :commit "{commit}")
      :program (:path "candidate.orc" :entry run)
      :inputs (:count count :payload payload) :returns {result_type}
      :policy (:environment :deterministic-effect-free :setup ()))'''
    projected = f'(let* ((child {perform})) child.value)'
    bodies = {
        "budget": f'''(loop/recur :max {projected}
          :state (loop-state (current String payload)) :on-exhausted "exhausted"
          (fn (state) (done state.current)))''',
        "match": f'(match {projected} ((YES chosen) chosen.value))',
    }
    source = install(tmp_path, {
        "placement/child.orc": child_source,
        "placement/typed.orc": f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule placement/typed) (import placement/child :only (Choice)) (export run)
          (defworkflow run ((payload String) (count Int :default 1)) -> String {bodies[position]}))''',
    }, entry_path="placement/typed.orc")
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    restored = ClosedProgram.from_artifact(built.artifact_path.read_text())
    [(identity, node)] = site_nodes(restored).items()
    config = decode_run_ref_static_config(base64.b64decode(node["config"]))
    assert "[*]" not in identity
    assert config.source.commit == commit
    assert [row.name for row in config.inputs] == ["count", "payload"]
    assert [row.binding.record for row in config.inputs] == [
        {"kind": "reference", "reference": "inputs.count"},
        {"kind": "reference", "reference": "inputs.payload"},
    ]
    assert [name for name, _value in node["inputs"]] == ["count", "payload"]
    expected = {
        "budget": {"kind": "primitive", "name": "Int"},
        "match": {"kind": "union", "name": "placement/child::Choice", "variants": [{
            "name": "YES", "fields": [{"name": "value", "type": {"kind": "primitive", "name": "String"}}]}]},
    }[position]
    assert config.program.return_refinement == expected
    assert restored.tree["defaults"] == {"count": 1}
    assert [(name, value["k"], value["n"]) for name, value in node["inputs"]] == [
        ("count", "name", "count"), ("payload", "name", "payload")]
    assert config.program.path == "candidate.orc" and config.program.entry_name == "run"
    assert config.program.environment == "deterministic-effect-free"


def test_closed_loop_run_ref_keeps_path_defaults(tmp_path):
    fixture = _build_path_fixture(tmp_path, case="defaults")
    revision = fixture.materialized_source.repository_revision_id
    perform = _path_form(revision).replace(':returns String', '')
    source = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule placement/defaults) (export run)
      (defworkflow run ((payload String)) -> String
        (loop/recur :max 1 :state (loop-state (current String payload))
          :on-exhausted "exhausted"
          (fn (state) (let* ((child {perform})) (done payload))))))''')
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=source, workspace_root=tmp_path))
    restored = ClosedProgram.from_artifact(built.artifact_path.read_text())
    [node] = site_nodes(restored).values()
    config = decode_run_ref_static_config(base64.b64decode(node["config"]))
    assert config.program.return_refinement is None
    assert config.program.environment == "deterministic-effect-free"
    assert config.source.setup.commands == ()
    assert node["result"]["fields"][0] == {
        "name": "value", "type": {"kind": "primitive", "name": "Value"}}


_PURE_REFUSALS = {
    "exhaustion": "run_ref_placement_invalid",
    "map_source": "run_ref_placement_invalid",
    "map_args": "list_map_effect_body_unsupported",
    "pure_map": "list_map_body_effect_forbidden",
    "pure_function": "run_ref_placement_invalid",
    "map_let": "list_map_effect_body_unsupported",
    "map_control": "list_map_effect_body_unsupported",
    "map_nested": "list_map_effect_body_unsupported",
}


def _restricted_source(root, position, locality):
    source, revision = _placement_source(root, "body", locality)
    prefix = source.read_text().split("(defworkflow run ", 1)[0]
    value = f'(let* ((child {_path_form(revision)})) child.value)' if locality == "direct" else '(invoke payload)'
    bodies = {
        "exhaustion": f'''(loop/recur :max 0 :state (loop-state (current String payload))
          :on-exhausted {value} (fn (state) (done state.current)))''',
        "map_source": f'(list/map-effect ((item (let* ((ignored {value})) (list payload)))) :max 1 (call echo :payload item))',
        "map_args": f'(list/map-effect ((item (list payload))) :max 1 (call echo :payload {value}))',
        "pure_map": f'(list/map ((item (list payload))) {value})',
        "pure_function": '(bad payload)',
        "map_let": f'(list/map-effect ((item (list payload))) :max 1 (let* ((ignored {value})) payload))',
        "map_control": f'(list/map-effect ((item (list payload))) :max 1 (if true {value} payload))',
        "map_nested": f'(list/map-effect ((item (list payload))) :max 1 (list/map-effect ((other (list item))) :max 1 (call echo :payload {value})))',
    }
    definitions = '(defworkflow echo ((payload String)) -> String payload)'
    if position == "pure_function":
        definitions += f'(defun bad ((payload String)) -> String {value})'
    source.write_text(prefix + definitions + f'''(defworkflow run ((payload String)) -> String
      (let* ((ignored {bodies[position]})) "parent")))''')
    return source


@pytest.mark.parametrize("locality", ["direct", "same", "imported"])
@pytest.mark.parametrize("position", list(_PURE_REFUSALS))
def test_closed_permission_keeps_pure_and_shape_refusals(tmp_path, locality, position):
    source = _restricted_source(tmp_path, position, locality)
    with pytest.raises(LispFrontendCompileError) as caught:
        build_closed_program_bundle(FrontendBuildRequest(
            source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    assert caught.value.diagnostics[0].code == _PURE_REFUSALS[position]


def test_closed_entry_keeps_imported_old_if_condition_pure(tmp_path):
    source, revision = _placement_source(tmp_path, "body", "imported")
    helper = tmp_path / "placement" / "helper.orc"
    helper.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.24")
      (defmodule placement/helper) (export invoke)
      (defproc invoke ((payload String)) -> String :effects ((runs-ref run)) :lowering inline
        (if (let* ((child {_path_form(revision)})) true) payload payload)))''')
    with pytest.raises(LispFrontendCompileError) as caught:
        build_closed_program_bundle(FrontendBuildRequest(
            source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "run_ref_placement_invalid"
    assert diagnostic.span.start.path == str(helper)


@pytest.mark.parametrize("position", ["body", "budget", "seed", "match", "map", "exhaustion"])
@pytest.mark.parametrize("transitive", [False, True])
def test_closed_ordinary_positions_still_refuse_trial(tmp_path, position, transitive):
    from tests.test_workflow_lisp_trial import _trial_source

    fixture = _build_path_fixture(tmp_path, case="trial")
    trial = _trial_source(arm_a=_path_form(fixture.materialized_source.repository_revision_id),
                          arm_b=_path_form(fixture.materialized_source.repository_revision_id))
    helper = f'''(defproc invoke ((payload String)) -> String :effects ((runs-trial))
      :lowering inline (let* ((trial {trial})) payload))''' if transitive else ""
    value = '(invoke payload)' if transitive else f'(let* ((trial {trial})) payload)'
    bodies = {
        "body": f'''(loop/recur :max 1 :state (loop-state (current String payload))
          :on-exhausted "exhausted" (fn (state) (done {value})))''',
        "budget": f'''(loop/recur :max (let* ((ignored {value})) 1)
          :state (loop-state (current String payload)) :on-exhausted "exhausted"
          (fn (state) (done state.current)))''',
        "seed": f'''(loop/recur :max 1 :state (loop-state (current String {value}))
          :on-exhausted "exhausted" (fn (state) (done state.current)))''',
        "match": f'(match (let* ((ignored {value})) (variant Choice YES :value payload)) ((YES chosen) chosen.value))',
        "map": f'(let* ((ignored (list/map-effect ((item (list payload))) :max 1 {"(invoke item)" if transitive else trial}))) payload)',
        "exhaustion": f'''(loop/recur :max 0 :state (loop-state (current String payload))
          :on-exhausted {value} (fn (state) (done state.current)))''',
    }
    source = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule placement/trial) (export run) (defunion Choice (YES (value String)))
      {helper} (defworkflow run ((payload String)) -> String {bodies[position]}))''')
    providers = tmp_path / "providers.json"
    providers.write_text('{"scorer":"codex"}')
    prompts = tmp_path / "prompts.json"
    prompts.write_text('{"trial-rubric":{"asset_file":"rubrics/trial.md"}}')
    with pytest.raises(LispFrontendCompileError) as caught:
        build_closed_program_bundle(FrontendBuildRequest(
            source_path=source, workspace_root=tmp_path,
            provider_externs_path=providers, prompt_externs_path=prompts))
    assert caught.value.diagnostics[0].code == "trial_nested_unsupported"


@pytest.mark.parametrize("locality", ["direct", "same", "imported"])
def test_closed_loop_permission_still_refuses_bundle_mode(tmp_path, locality):
    source, _ = _placement_source(tmp_path, "body", locality)
    owner = tmp_path / "placement" / "helper.orc" if locality == "imported" else source
    text = owner.read_text().replace(
        ':program (:path "candidate.orc" :entry run)', ':program (:bundle child)'
    ).replace(':returns String', '').replace(
        ':policy (:environment :deterministic-effect-free :setup ())', ':policy (:setup ())')
    module = "placement/helper" if locality == "imported" else "placement/entry"
    text = text.replace(':effects ((runs-ref run))', f':effects ((runs-ref {module}::child))')
    at = text.index('(defproc invoke ' if locality != "direct" else '(defworkflow run ')
    owner.write_text(text[:at] + '(defworkflow child ((payload String)) -> String payload)\n' + text[at:])
    with pytest.raises(LispFrontendCompileError) as caught:
        build_closed_program_bundle(FrontendBuildRequest(
            source_path=source, source_roots=(tmp_path,), workspace_root=tmp_path))
    assert caught.value.diagnostics[0].code == "closed_program_gap", str(caught.value)


def test_path_run_ref_is_admitted_in_evaluated_loop_body(tmp_path) -> None:
    fixture = _build_path_fixture(tmp_path, case="placement-loop")
    revision = fixture.materialized_source.repository_revision_id
    source = tmp_path / "placement" / "loop_entry.orc"
    source.parent.mkdir()
    run_ref = f'''(run-ref
      :source (:repo {json.dumps(revision.normalized_locator)} :commit "{revision.resolved_commit_sha}")
      :program (:path "candidate.orc" :entry run)
      :inputs (:payload state.current) :returns String
      :policy (:environment :deterministic-effect-free :setup ()))'''
    source.write_text(f'''(workflow-lisp
      (:language "0.1") (:target-dsl "2.35")
      (defmodule placement/loop_entry) (export run)
      (defworkflow run ((payload String)) -> String
        (loop/recur :max 1
          :state (loop-state (current String payload))
          :on-exhausted "exhausted"
          (fn (state)
            (let* ((child {run_ref}))
              (done "parent"))))))''', encoding="utf-8")

    built = build_closed_program_bundle(
        FrontendBuildRequest(source_path=source, workspace_root=tmp_path)
    )
    read_back = ClosedProgram.from_artifact(built.artifact_path.read_text())

    assert read_back.digest == built.program.digest
    assert len(site_nodes(read_back)) == 1
