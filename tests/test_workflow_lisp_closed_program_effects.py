from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow_lisp.closed.names import canonical_run_ref_signature
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import PromptExtern
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from tests.workflow_lisp_closed_program_helpers import install


TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION


def _provider_nodes(body: dict) -> list[dict]:
    return [node for node in _ast_nodes(body) if node.get("k") == "perform" and node.get("class") == "provider"]


def _provider_input_value_path(value: dict) -> str:
    if value["k"] == "name":
        return value["n"]
    assert value["k"] == "field"
    return f"{_provider_input_value_path(value['base'])}.{'.'.join(value['path'])}"


def _without_provenance(value):
    if isinstance(value, dict):
        return {key: _without_provenance(row) for key, row in value.items() if key != "@"}
    if isinstance(value, list):
        return [_without_provenance(row) for row in value]
    return value


def _build_source_free(typed):
    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    return closed


def _upgrade_gap_fixture(source: str, entry: str, relative: str) -> str:
    source, replaced = re.subn(
        r'\(:target-dsl "[^"]+"\)',
        f'(:target-dsl "{TARGET}")',
        source,
        count=1,
    )
    assert replaced == 1, relative
    if "(defmodule " not in source:
        target = re.search(r"^  \(:target-dsl [^\n]*\)\s*$", source, re.M)
        assert target is not None, relative
        source = source[:target.end()] + f"  (defmodule {Path(relative).stem})\n" + source[target.end():]
    if not re.search(rf"\(export[^)]*\b{re.escape(entry)}\b", source):
        imports = list(re.finditer(r"^  \(import [^\n]*\)\s*$", source, re.M))
        if imports:
            at = imports[-1].end()
        else:
            target = re.search(r"^  \(:target-dsl [^\n]*\)\s*$", source, re.M)
            assert target is not None, relative
            at = target.end()
        source = source[:at] + f"  (export {entry})\n" + source[at:]
    if relative == "valid/resource_stdlib_finalize_selected_item.orc":
        source = source.replace(
            "     (selected SelectedItem))\n    -> SelectedItemResult",
            "     (selected SelectedItem)\n"
            "     (queue-transition ResourceTransitionResult))\n    -> SelectedItemResult",
            1,
        )
        source, replaced = re.subn(
            r"\(let\* \(\(queue-transition\n.*?:event SELECTED\)\)\n\s+\(roadmap",
            "(let* ((roadmap",
            source,
            count=1,
            flags=re.S,
        )
        assert replaced == 1, relative
    return source


def _compile_gap_fixture(path: Path, entry: str, root: Path, source: str):
    provider_names = set(re.findall(r"\bproviders\.[a-zA-Z_][\w.]*", source))
    prompt_names = set(re.findall(r"\bprompts\.[a-zA-Z_][\w.]*", source))
    boundaries = {
        name: ExternalToolBinding(
            name=name,
            stable_command=("python", command_path),
            closure=(),
        )
        for name, command_path in re.findall(
            r'\(command-result\s+([^\s()]+)\s+:argv\s+\("python"\s+"([^"]+)"',
            source,
        )
    }
    if "(trial" in source:
        provider_names.add("scorer")
        prompt_names.add("trial-rubric")
    return compile_typed_program(
        path,
        entry_workflow=entry,
        source_roots=(root,),
        workspace_root=root,
        command_boundaries=boundaries,
        provider_externs={name: name for name in provider_names},
        prompt_externs={
            name: ("rubrics/trial.md" if name == "trial-rubric" else "prompt.md")
            for name in prompt_names
        },
    )


_WREF_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
  (defmodule cp/wrefs) (export run)
  (defrecord Box (n Int))
  (defworkflow helper ((input Box)) -> Box
    (provider-result providers.execute :prompt prompts.execute :inputs (input.n) :returns Box))
  (defproc invoke ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box
    :effects ((calls-workflow runner)) :lowering inline (call runner :input input))
  (defworkflow run ((input Box)) -> Box (invoke (workflow-ref helper) input)))'''


@pytest.mark.parametrize("source_kind", ("asset_file", "input_file"))
def test_selected_workflow_reference_body_uses_its_exact_provider_owner(
    tmp_path: Path, source_kind: str
) -> None:
    digests = []
    for location in ("original", "relocated/deeper"):
        root = tmp_path / location
        path = install(root, _WREF_SOURCE)
        typed = compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
            provider_externs={"providers.execute": "selected-provider"},
            prompt_externs={"prompts.execute": {source_kind: "prompts/selected.md"}},
        )
        (root / "cp" / "prompts").mkdir(parents=True)
        (root / "cp" / "prompts" / "selected.md").write_text(
            "asset source sentinel", encoding="utf-8"
        )
        (root / "prompts").mkdir()
        (root / "prompts" / "selected.md").write_text(
            "workspace input sentinel", encoding="utf-8"
        )
        asset_resolver = WorkflowAssetResolver(path)
        path.unlink()

        closed = _build_source_free(typed)
        (invoke,) = [
            definition
            for definition in closed.tree["definitions"].values()
            if definition["key"][:3] == ["cp/wrefs", "procedure", "invoke"]
        ]
        reference = dict(invoke["key"][5])["runner"]
        expected_prompt = {"source_kind": source_kind, "path": "prompts/selected.md"}
        if source_kind == "asset_file":
            expected_prompt["asset_base"] = "cp"
        assert reference["target"][:3] == ["cp/wrefs", "workflow", "helper"]
        assert reference["externs"] == {
            "providers": [["providers.execute", {"provider_id": "selected-provider"}]],
            "prompts": [["prompts.execute", expected_prompt]],
        }

        (helper,) = [
            definition
            for definition in closed.tree["definitions"].values()
            if definition["key"][:3] == ["cp/wrefs", "workflow", "helper"]
        ]
        (provider,) = _provider_nodes(helper["body"])
        assert provider["provider"] == "selected-provider"
        assert provider["prompt"] == expected_prompt
        selected_content = (
            asset_resolver.read_text(provider["prompt"]["path"])
            if source_kind == "asset_file"
            else (root / provider["prompt"]["path"]).read_text(encoding="utf-8")
        )
        assert selected_content == (
            "asset source sentinel"
            if source_kind == "asset_file"
            else "workspace input sentinel"
        )
        digests.append(closed.digest)

    assert digests[0] == digests[1]


def test_imported_provider_body_keeps_its_extern_scope_when_caller_conflicts(
    tmp_path: Path,
) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule cp/producer) (export run)
      (defworkflow run () -> Int
        (provider-result shared-provider :prompt shared-prompt :inputs () :returns Int)))'''
    owner = tmp_path / "owner"
    path = install(owner, source)
    compiled = compile_stage3_entrypoint(
        path,
        source_roots=(owner,),
        workspace_root=owner,
        command_boundaries={},
        provider_externs={"shared-provider": "producer-id"},
        prompt_externs={"shared-prompt": {"asset_file": "producer.md"}},
        validate_shared=True,
    )
    bundle = compiled.validated_bundles_by_name["cp/producer::run"]
    path.unlink()

    caller = tmp_path / "caller"
    path = install(
        caller,
        '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
          (defmodule caller) (export run)
          (defworkflow run () -> Int (call dep)))''',
    )
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(caller,),
        workspace_root=caller,
        command_boundaries={},
        provider_externs={"shared-provider": "caller-id"},
        prompt_externs={"shared-prompt": {"input_file": "caller.md"}},
        imported_workflow_bundles={"dep": bundle},
    )
    path.unlink()

    closed = _build_source_free(typed)
    definition = closed.tree["definitions"]["workflow:cp/producer::run"]
    selected_scope = closed.tree["configuration"]["imports"][definition["configuration"]]
    assert selected_scope["providers"]["shared-provider"] == {"provider_id": "producer-id"}
    assert selected_scope["prompts"]["shared-prompt"] == {
        "source_kind": "asset_file",
        "path": "producer.md",
        "asset_base": "cp",
    }
    assert closed.tree["configuration"]["providers"]["shared-provider"] == {
        "provider_id": "caller-id"
    }
    (provider,) = _provider_nodes(definition["body"])
    assert provider["provider"] == "producer-id"
    assert provider["prompt"] == {
        "source_kind": "asset_file",
        "path": "producer.md",
        "asset_base": "cp",
    }


def test_imported_nominals_keep_variant_contract_placement_for_commands_and_providers(
    tmp_path: Path,
) -> None:
    root = tmp_path / "nested-nominals"
    sources = {
        "nominal/left.orc": '''(workflow-lisp
          (:language "0.1") (:target-dsl "TARGET")
          (defmodule nominal/left) (export Parameter)
          (defrecord Parameter (code String)))''',
        "nominal/right.orc": '''(workflow-lisp
          (:language "0.1") (:target-dsl "TARGET")
          (defmodule nominal/right) (export Parameter)
          (defrecord Parameter (code String)))''',
        "nominal/entry.orc": '''(workflow-lisp
          (:language "0.1") (:target-dsl "TARGET")
          (defmodule nominal/entry)
          (import nominal/left :as left)
          (import nominal/right :as right)
          (export run)
          (defunion Choice
            (LEFT (payload List[left.Parameter] :description "Use left parameters."))
            (RIGHT (payload List[right.Parameter] :description "Use right parameters.")))
          (defworkflow run () -> Choice
            (let* ((first (command-result tool :argv ("python" "tool.py")
                            :returns Choice)))
              (provider-result providers.ask :prompt prompts.ask :inputs (first)
                :returns Choice))))''',
    }
    entry = install(root, sources, entry_path="nominal/entry.orc")
    (root / "tool.py").write_text("raise RuntimeError('compile-only')\n", encoding="utf-8")
    typed = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={
            "tool": ExternalToolBinding(
                name="tool",
                stable_command=("python", "tool.py"),
                closure=("tool.py",),
            )
        },
        provider_externs={"providers.ask": "ask"},
        prompt_externs={"prompts.ask": "prompt.md"},
    )
    for source_path in root.rglob("*.orc"):
        source_path.unlink()

    closed = _build_source_free(typed)
    bodies = [
        closed.tree["body"],
        *(definition["body"] for definition in closed.tree["definitions"].values()),
    ]
    effects = [
        node
        for body in bodies
        for node in _ast_nodes(body)
        if node.get("k") == "perform"
    ]
    assert {effect["class"] for effect in effects} == {"command", "provider"}
    for effect in effects:
        contract = effect["contract"]
        assert contract["kind"] == "variant_output"
        payload = contract["payload"]
        assert payload["shared_fields"] == []
        for variant, module in (("LEFT", "left"), ("RIGHT", "right")):
            (field,) = payload["variants"][variant]["fields"]
            assert field["name"] == "payload"
            assert field["description"] == f"Use {module} parameters."
            assert field["type"] == "list"
            assert field["items"] == {
                "type": "record",
                "record_name": f"nominal/{module}::Parameter",
                "fields": [{"name": "code", "type": "string"}],
            }


@pytest.mark.parametrize("effect_kind", ("command", "provider"))
def test_nested_run_ref_contract_uses_actual_producers_after_finalization(
    tmp_path: Path,
    effect_kind: str,
) -> None:
    run_ref = '''(run-ref
      :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
      :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
      :policy (:environment :deterministic-effect-free :setup ()))'''
    if effect_kind == "command":
        effect_declaration = ":effects ((uses-command tool))"
        effect_expression = '''(command-result tool
          :argv ("python" "tool.py") :returns Choice[A B])'''
    else:
        effect_declaration = ":effects ((uses-provider provider))"
        effect_expression = '''(provider-result provider :prompt prompt :inputs (a b)
          :returns Choice[A B])'''
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/generated_contract) (export run)
      (defunion Choice :forall (A B)
        (LEFT (payload List[A] :description "left result guidance"))
        (RIGHT (payload List[B] :description "right result guidance")))
      (defproc produce :forall (A B) ((a A) (b B)) -> Choice[A B]
        {effect_declaration} :lowering inline
        {effect_expression})
      (defworkflow run () -> Int
        (let* ((first {run_ref})
               (second {run_ref})
               (answer (produce first second)))
          0)))'''
    root = tmp_path / effect_kind
    path = install(root, source)
    if effect_kind == "command":
        (root / "tool.py").write_text("raise RuntimeError('compile only')\n", encoding="utf-8")
        boundaries = {
            "tool": ExternalToolBinding(
                name="tool",
                stable_command=("python", "tool.py"),
                closure=("tool.py",),
            )
        }
        provider_externs = {}
        prompt_externs = {}
    else:
        boundaries = {}
        provider_externs = {"provider": "selected-provider"}
        prompt_externs = {"prompt": {"input_file": "prompts/source.md"}}
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries=boundaries,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
    )
    for authored in root.rglob("*.orc"):
        authored.unlink()

    closed = _build_source_free(typed)
    bodies = [
        closed.tree["body"],
        *(row["body"] for row in closed.tree["definitions"].values()),
    ]
    effects = [
        node
        for body in bodies
        for node in _ast_nodes(body)
        if node.get("k") == "perform"
    ]
    (result_effect,) = [node for node in effects if node["class"] == effect_kind]
    run_ref_effects = [node for node in effects if node["class"] == "run_ref"]
    assert len(run_ref_effects) == 2
    run_ref_names = {
        node["result"]["name"] for node in run_ref_effects
    }

    result_names = {
        variant["name"]: variant["fields"][0]["type"]["item"]["name"]
        for variant in result_effect["result"]["variants"]
    }
    assert result_names == {
        "LEFT": run_ref_effects[0]["result"]["name"],
        "RIGHT": run_ref_effects[1]["result"]["name"],
    }
    contract = result_effect["contract"]
    assert contract["kind"] == "variant_output"
    payload = contract["payload"]
    assert payload["shared_fields"] == []
    contract_names = {}
    for variant, description in (
        ("LEFT", "left result guidance"),
        ("RIGHT", "right result guidance"),
    ):
        (field,) = payload["variants"][variant]["fields"]
        assert field["name"] == "payload"
        assert field["description"] == description
        assert field["type"] == "list"
        assert field["items"]["type"] == "record"
        contract_names[variant] = field["items"]["record_name"]
        assert contract_names[variant] == result_names[variant]
    assert len(set(contract_names.values())) == 2
    assert set(contract_names.values()) == run_ref_names
    subjects = result_effect.get("@", {}).get("source_map_subject", [])
    subject_names = {
        row["value"]["subject_name"]
        for row in subjects
        if row.get("field") == "source_map_subject"
    }
    assert len(subject_names) == 2
    assert {
        tuple(row["path"])
        for row in subjects
        if row.get("field") == "source_map_subject"
    } == {
        ("variants", "LEFT", "fields", "0"),
        ("variants", "RIGHT", "fields", "0"),
    }
    assert {
        variant
        for variant in ("LEFT", "RIGHT")
        if any(name.endswith(f"::{variant}::payload") for name in subject_names)
    } == {"LEFT", "RIGHT"}
    assert all(name.startswith("effect::Choice[") for name in subject_names)


_RESULT_PATH_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
 (defmodule result_path_probe) (export entry)
 (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
 (defrecord Result (text String))
 (defrecord Projection (bundle ResultBundle))
 (defworkflow entry ((seed String)) -> Projection
   (let* ((r (provider-result provider :prompt prompt :inputs (seed) :returns Result)))
     (record Projection :bundle (provider-bundle-path r :as ResultBundle)))))'''


def test_provider_result_and_result_path_build_after_source_deletion_and_relocate(
    tmp_path: Path,
) -> None:
    digests = []
    for location in ("original", "relocated/deeper"):
        root = tmp_path / location
        path = install(root, _RESULT_PATH_SOURCE)
        typed = compile_typed_program(
            path,
            entry_workflow="entry",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
            provider_externs={"provider": "probe-provider"},
            prompt_externs={"prompt": PromptExtern(name="prompt", input_file="inputs/prompt.md")},
        )
        path.unlink()

        closed = _build_source_free(typed)
        (provider,) = _provider_nodes(closed.tree["body"])
        assert provider["provider"] == "probe-provider"
        (binding,) = [
            node for node in _ast_nodes(closed.tree["body"])
            if node.get("k") == "let" and node.get("value") is provider
        ]
        (result_path,) = [
            node for node in _ast_nodes(closed.tree["body"]) if node.get("k") == "result_path"
        ]
        assert result_path["n"] == binding["name"]
        assert result_path["type"] == {
            "kind": "path",
            "name": "result_path_probe::ResultBundle",
            "under": ".orchestrate/runs",
            "must_exist_target": False,
        }
        assert len(closed.sites) == 1
        digests.append(closed.digest)

    assert digests[0] == digests[1]


def test_provider_input_names_do_not_expose_generated_anf_bindings(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
     (defmodule cp/provider_input_identity) (export run)
     (defrecord Box (n Int))
     (defproc worker ((fixed Box) (input Box)) -> Int
       :effects ((uses-provider provider)) :lowering inline
       (provider-result provider :prompt prompt
         :inputs ((if (> input.n 0) input fixed)) :returns Int))
     (defproc invoke ((runner ProcRef[Box -> Int]) (input Box)) -> Int
       :effects () :lowering inline (runner input))
     (defworkflow run ((input Box)) -> Int
       (invoke (bind-proc (proc-ref worker) :fixed (record Box :n 7)) input)))'''
    facts = []
    for location, text in (
        ("original", source),
        ("relocated/deeper", "\n; formatting change\n\n" + source),
    ):
        root = tmp_path / location
        path = install(root, text)
        typed = compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
            provider_externs={"provider": "p"},
            prompt_externs={"prompt": {"input_file": "p.md"}},
        )
        path.unlink()

        closed = _build_source_free(typed)
        effects = [
            node
            for definition in closed.tree["definitions"].values()
            for node in _provider_nodes(definition["body"])
        ]
        assert len(effects) == 1
        names = [row[0] for row in effects[0]["inputs"]]
        assert names == [effects[0]["inputs"][0][2]["n"]]
        assert not names[0].startswith("__wcc_anf_")
        facts.append((closed.digest, closed.sites, names))

    assert facts[0] == facts[1]

    lookalike_root = tmp_path / "authored-lookalike"
    path = install(
        lookalike_root,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
         (defmodule cp/lookalike) (export run)
         (defworkflow run ((__wcc_anf_0123456789 Int)) -> Int
           (provider-result provider :prompt prompt
             :inputs (__wcc_anf_0123456789) :returns Int)))''',
    )
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(lookalike_root,),
        workspace_root=lookalike_root,
        command_boundaries={},
        provider_externs={"provider": "p"},
        prompt_externs={"prompt": {"input_file": "p.md"}},
    )
    path.unlink()
    closed = _build_source_free(typed)
    (provider,) = _provider_nodes(closed.tree["body"])
    assert provider["inputs"][0][0] == "__wcc_anf_0123456789"


@pytest.mark.parametrize(
    ("input_exprs", "expected_names"),
    (
        ("left.value right.value", ["value", "value__2"]),
        ("left.value value", ["value", "value__2"]),
        ("left.value left.value", ["value", "value__2"]),
        (
            "value value value__2 value value__3",
            ["value", "value__4", "value__2", "value__5", "value__3"],
        ),
        ("left.value right", ["value", "right"]),
    ),
)
def test_provider_input_name_collisions_keep_each_ordered_value(
    tmp_path: Path,
    input_exprs: str,
    expected_names: list[str],
) -> None:
    results = []
    for location, prefix in (
        ("original", ""),
        ("relocated/deeper", "\n; formatting-only relocation\n\n"),
    ):
        root = tmp_path / location
        source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule cp/input_collision) (export run)
          (defrecord Box (value Int))
          (defworkflow run ((left Box) (right Box) (value Int) (value__2 Int) (value__3 Int))
            -> Int
            (provider-result provider :prompt prompt :inputs ({input_exprs}) :returns Int)))'''
        path = install(root, prefix + source)
        typed = compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
            provider_externs={"provider": "selected"},
            prompt_externs={"prompt": {"input_file": "p.md"}},
        )
        path.unlink()

        closed = _build_source_free(typed)
        (provider,) = _provider_nodes(closed.tree["body"])
        names = [row[0] for row in provider["inputs"]]
        renderers = [row[1] for row in provider["inputs"]]
        values = [_provider_input_value_path(row[2]) for row in provider["inputs"]]
        assert names == expected_names
        assert renderers == ["canonical-json"] * len(expected_names)
        assert values == input_exprs.split()
        assert len(names) == len(set(names)) == len(values)
        if location == "original":
            from copy import deepcopy

            from orchestrator.workflow_lisp.closed.check import CheckedFormError, validate

            tampered = deepcopy(closed.tree)
            (tampered_provider,) = _provider_nodes(tampered["body"])
            tampered_provider["inputs"][1][0] = tampered_provider["inputs"][0][0]
            with pytest.raises(CheckedFormError) as error:
                validate(tampered)
            assert error.value.rule == "effect_shape"
        results.append((closed.digest, closed.sites, names, values))

    assert results[0] == results[1]


def test_defprompt_doc_slots_keep_intrinsic_fill_semantics(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/prompt_channels) (export run)
      (defpath NotesPath :kind relpath :under "docs" :must-exist true)
      (defpath RequiredPath :kind relpath :under "docs" :must-exist true)
      (defpath OptionalPath :kind relpath :under "docs" :must-exist true)
      (defpath ReportPath :kind relpath :under ".orchestrate/runs" :must-exist false)
      (defrecord Answer (decision String))
      (defprompt review
        (:fills
          (notes :doc NotesPath)
          (message :text)
          (score :value Int)
          (report :path :out ReportPath))
        -> Answer
        "Use {message}, score {score}, report {report}; repeat {message}")
      (defworkflow run
        ((notes NotesPath) (message String) (score Int) (report ReportPath)
         (model String) (effort String))
        -> Answer
        (provider-result providers.review
          :prompt (review :notes notes :message message :score score :report report)
          :model model :effort effort :delivery :composed :timeout-sec 30)))'''
    root = tmp_path / "prompt-owner"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
        provider_externs={"providers.review": "reviewer"},
        prompt_externs={},
    )
    path.unlink()

    closed = _build_source_free(typed)
    (provider,) = _provider_nodes(closed.tree["body"])
    template = provider["prompt"]["template"]
    assert isinstance(template, str) and template
    fills = provider["prompt"]["fills"]
    assert [
        {key: row[key] for key in ("name", "kind", "renderer_id", "output_role", "placeholder_ordinals")}
        for row in fills
    ] == [
        {"name": "notes", "kind": "doc", "renderer_id": None, "output_role": "none", "placeholder_ordinals": []},
        {"name": "message", "kind": "text", "renderer_id": "raw-utf8-string", "output_role": "none", "placeholder_ordinals": [0, 3]},
        {"name": "score", "kind": "value", "renderer_id": "canonical-json", "output_role": "none", "placeholder_ordinals": [1]},
        {"name": "report", "kind": "path", "renderer_id": "posix-path-line", "output_role": "required_string_file", "placeholder_ordinals": [2]},
    ]
    assert fills[0]["type"] == {
        "kind": "path",
        "name": "cp/prompt_channels::NotesPath",
        "under": "docs",
        "must_exist_target": True,
    }
    assert [template.count("{" + row["name"] + "}") for row in fills] == [
        len(row["placeholder_ordinals"]) for row in fills
    ]
    assert provider["dependencies"] is None
    assert _without_provenance(provider["policy"]) == {
        "model": {"k": "name", "n": "model"},
        "effort": {"k": "name", "n": "effort"},
        "delivery": {"k": "lit", "v": "composed", "type": {"kind": "primitive", "name": "String"}},
        "timeout_sec": {"k": "lit", "v": 30, "type": {"kind": "primitive", "name": "Int"}},
    }


def test_external_prompt_keeps_explicit_dependency_channel(tmp_path: Path) -> None:
    dependency_instruction = "extra context"
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/prompt_dependencies) (export run)
      (defpath RequiredPath :kind relpath :under "docs" :must-exist true)
      (defpath OptionalPath :kind relpath :under "docs" :must-exist true)
      (defworkflow run
        ((required RequiredPath) (optional OptionalPath) (model String) (effort String))
        -> Int
        (provider-result providers.review
          :prompt prompts.review :inputs (required optional) :returns Int
          :prompt-dependencies
            (:required (required) :optional (optional) :position append :instruction "INSTRUCTION")
          :model model :effort effort :timeout-sec 30)))'''
    source = source.replace("INSTRUCTION", dependency_instruction)
    root = tmp_path / "external-prompt-owner"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
        provider_externs={"providers.review": "reviewer"},
        prompt_externs={"prompts.review": {"input_file": "prompts/review.md"}},
    )
    path.unlink()

    closed = _build_source_free(typed)
    (provider,) = _provider_nodes(closed.tree["body"])
    assert provider["prompt"] == {"source_kind": "input_file", "path": "prompts/review.md"}
    assert _without_provenance(provider["dependencies"]) == {
        "required": [{"k": "name", "n": "required"}],
        "optional": [{"k": "name", "n": "optional"}],
        "position": "append",
        "instruction": dependency_instruction,
    }
    assert _without_provenance(provider["policy"]) == {
        "model": {"k": "name", "n": "model"},
        "effort": {"k": "name", "n": "effort"},
        "timeout_sec": {"k": "lit", "v": 30, "type": {"kind": "primitive", "name": "Int"}},
    }


def test_fragment_prompt_still_refuses_redeclared_dependency_source_syntax(
    tmp_path: Path,
) -> None:
    root = tmp_path / "refused-fragment-dependencies"
    path = install(
        root,
        '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
          (defmodule cp/refused_dependencies) (export run)
          (defprompt review
            (:fills (message :text))
            -> String
            "Review {message}")
          (defworkflow run ((message String)) -> String
            (provider-result provider
              :prompt (review :message message)
              :prompt-dependencies
                (:required (message) :optional () :position prepend :instruction "instruction"))))''',
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
            provider_externs={"provider": "reviewer"},
            prompt_externs={},
        )

    assert any(
        diagnostic.code == "prompt_dependency_redeclaration_forbidden"
        for diagnostic in excinfo.value.diagnostics
    )


def test_unportable_selected_provider_parts_and_trial_are_located_before_keying(
    tmp_path: Path,
) -> None:
    from tests.test_workflow_lisp_trial import _trial_source

    cases = (
        (
            "session-artifact",
            '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
              (defmodule cp/session_gap) (export run)
              (defworkflow run () -> String
                (provider-result providers.run :prompt prompts.run :inputs ()
                  :session-artifact session :returns String)))''',
            "run",
            {"providers.run": "provider"},
            {"prompts.run": "prompt.md"},
        ),
        (
            "context-capture",
            '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
              (defmodule cp/context_gap) (export run)
              (defworkflow run () -> Contextual[Int]
                (provider-result providers.run :prompt prompts.run :inputs ()
                  :capture-context :portable :returns Int)))''',
            "run",
            {"providers.run": "provider"},
            {"prompts.run": "prompt.md"},
        ),
        (
            "trial",
            '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
              (defmodule cp/trial_gap) (export compare first second)
              (defworkflow first () -> String "first")
              (defworkflow second () -> String "second")
              (defworkflow compare () -> Value
                TRIAL_SOURCE))'''.replace("TRIAL_SOURCE", _trial_source().strip()),
            "compare",
            {"scorer": "scorer"},
            {"trial-rubric": "rubrics/trial.md"},
        ),
    )
    for name, source, entry_workflow, providers, prompts in cases:
        root = tmp_path / name
        path = install(root, source)
        (root / "rubrics").mkdir(exist_ok=True)
        (root / "rubrics" / "trial.md").write_text("rubric", encoding="utf-8")
        expected_line = next(
            index
            for index, line in enumerate(source.splitlines(), start=1)
            if ("(trial" in line if name == "trial" else "(provider-result" in line)
        )
        typed = compile_typed_program(
            path,
            entry_workflow=entry_workflow,
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
            provider_externs=providers,
            prompt_externs=prompts,
        )
        path.unlink()

        with pytest.raises(LispFrontendCompileError) as excinfo:
            build_closed_program(typed)
        diagnostic, = excinfo.value.diagnostics
        assert diagnostic.code == "closed_program_gap"
        assert diagnostic.span is not None
        assert diagnostic.span.start.line == expected_line
        assert diagnostic.notes == (
            f"form={'trial' if name == 'trial' else 'provider-result'}",
        )
        assert (
            "trial" in diagnostic.message
            if name == "trial"
            else "session" in diagnostic.message
            if name == "session-artifact"
            else "context" in diagnostic.message
        )


def test_each_selected_effect_outside_the_release_is_a_located_gap(
    tmp_path: Path,
) -> None:
    from tests.test_workflow_lisp_trial import _trial_source

    fixture_cases = (
        ("materialize-view", "valid/materialize_view_runtime.orc", "orchestrate"),
        ("resource-transition", "valid/resource_transition_effects.orc", "move-selected-item"),
        ("run-provider-phase", "valid/phase_stdlib_run_provider_phase.orc", "run-provider-phase-demo"),
        ("produce-one-of", "valid/phase_stdlib_run_provider_phase.orc", "produce-one-of-demo"),
        ("resume-or-start", "valid/phase_stdlib_resume_or_start.orc", "resume-record-phase"),
        ("finalize-selected-item", "valid/resource_stdlib_finalize_selected_item.orc", "run-selected-item"),
        ("with-live-providers", "provider_supervision/provider_supervision_continue.orc", "orchestrate"),
        ("with-live-provider-peers", "provider_peer_group/provider_peer_group_three.orc", "orchestrate"),
        ("provider-result", "session_artifact/root.orc", "run"),
    )
    cases = []
    fixture_root = Path(__file__).parent / "fixtures" / "workflow_lisp"
    for form, relative, entry in fixture_cases:
        source = _upgrade_gap_fixture(
            (fixture_root / relative).read_text(encoding="utf-8"),
            entry,
            relative,
        )
        cases.append((form, form, entry, source))

    trial_source = f'''(workflow-lisp
      (:language "0.1")
      (:target-dsl "{TARGET}")
      (defmodule cp/trial_gap) (export compare first second)
      (defworkflow first () -> String "first")
      (defworkflow second () -> String "second")
      (defworkflow compare () -> Value
        {_trial_source().strip()}))'''
    cases.extend(
        (
            (
                "request-input",
                "request-input",
                "ask",
                f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
                  (defmodule cp/request_gap) (export ask)
                  (defworkflow ask ((question String)) -> HumanReply
                    (request-input question)))''',
            ),
            ("trial", "trial", "compare", trial_source),
            (
                "provider-result",
                "capture-context",
                "capture",
                f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
                  (defmodule cp/capture_gap) (export capture)
                  (defworkflow capture () -> Contextual[Int]
                    (provider-result providers.execute :prompt prompts.execute :inputs ()
                      :capture-context :portable :returns Int)))''',
            ),
            (
                "provider-result",
                "context-parameter",
                "ask",
                f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
                  (defmodule cp/context_gap) (export ask)
                  (defworkflow ask ((seed Context)) -> Int
                    (provider-result providers.ask :prompt prompts.ask :inputs ()
                      :context seed :returns Int)))''',
            ),
            (
                "run-ref",
                "bundle-run-ref",
                "entry",
                f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
                  (defmodule cp/bundle_gap) (export entry)
                  (defrecord ProjectedInput (value String))
                  (defworkflow child ((payload ProjectedInput)) -> String payload.value)
                  (defworkflow entry () -> String
                    (let* ((trial (run-ref
                      :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
                      :program (:bundle child)
                      :inputs (:payload (record ProjectedInput :value (string/concat "child-" "result")))
                      :policy (:setup ()))))
                      trial.value)))''',
            ),
        )
    )

    for form, case_name, entry, source in cases:
        root = tmp_path / case_name
        module = re.search(r"\(defmodule\s+([^\s)]+)", source)
        assert module is not None, case_name
        path = root / Path(*module.group(1).split("/")).with_suffix(".orc")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        (root / "rubrics").mkdir(exist_ok=True)
        (root / "rubrics" / "trial.md").write_text("trial rubric", encoding="utf-8")
        selected_lines = [
            number
            for number, line in enumerate(source.splitlines(), start=1)
            if f"({form}" in line
        ]
        assert selected_lines, (case_name, form)
        typed = _compile_gap_fixture(path, entry, root, source)

        with pytest.raises(LispFrontendCompileError) as excinfo:
            build_closed_program(typed)
        diagnostic, = excinfo.value.diagnostics
        assert diagnostic.code == "closed_program_gap", (case_name, diagnostic)
        assert diagnostic.notes == (f"form={form}",), (case_name, diagnostic)
        assert diagnostic.span is not None
        assert diagnostic.span.start.line in selected_lines, (
            case_name,
            selected_lines,
            diagnostic,
        )
        if form == "provider-result":
            part = "session" if ":session-artifact" in source else "context"
            assert part in diagnostic.message, (case_name, part, diagnostic)


_COPIED_CAPTURE_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/copied_capture) (export entry)
  (defproc invoke ((runner ProcRef[Int -> Int]) (n Int)) -> Int
    :effects () :lowering inline (runner n))
  (defproc forward ((runner ProcRef[Int -> Int]) (n Int)) -> Int
    :effects () :lowering inline (invoke runner n))
  (defproc outer ((flag Bool) (n Int)) -> Int :effects ((runs-ref child)) :lowering inline
    (let* ((first
             (run-ref
               :source (:repo "file:///workspace"
                        :commit "0123456789abcdef0123456789abcdef01234567")
               :program (:path "child.orc" :entry child)
               :inputs (:n n)
               :returns Int
               :policy (:environment :deterministic-effect-free :setup ())))
           (second
             (run-ref
               :source (:repo "file:///workspace"
                        :commit "0123456789abcdef0123456789abcdef01234567")
               :program (:path "child.orc" :entry child)
               :inputs (:n n)
               :returns Int
               :policy (:environment :deterministic-effect-free :setup ()))))
      (let-proc (saved ((n Int)) -> Int
                  :captures (first)
                  (let* ((check (run-ref
                                 :source (:repo "file:///workspace"
                                          :commit "0123456789abcdef0123456789abcdef01234567")
                                 :program (:path "child.orc" :entry child)
                                 :inputs (:n 0)
                                 :returns Int
                                 :policy (:environment :deterministic-effect-free :setup ()))))
                    (+ first.value n)))
        (let* ((hook (proc-ref saved))
               (left (forward hook 0))
               (right (forward hook 1)))
          (+ left right)))))
 (defworkflow entry ((n Int)) -> Int
   (let* ((a (invoke (bind-proc (proc-ref outer) :flag true) n))
          (b (invoke (bind-proc (proc-ref outer) :flag false) n))) (+ a b))))'''


def test_copied_specializations_capture_their_actual_same_signature_producer(
    tmp_path: Path,
) -> None:
    digests = []
    for location, prefix in (
        ("original", ""),
        ("relocated/deeper", "\n; moved copied caller\n\n"),
    ):
        root = tmp_path / location
        path = install(root, prefix + _COPIED_CAPTURE_SOURCE)
        typed = compile_typed_program(
            path,
            entry_workflow="entry",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
        )
        path.unlink()

        closed = _build_source_free(typed)
        definitions = closed.tree["definitions"]
        outers = [
            definition
            for definition in definitions.values()
            if definition["key"][1:3] == ["procedure", "outer"]
        ]
        assert len(outers) == 2
        first_producer_names = []
        for definition in outers:
            env = {}
            producers = []
            forwarded_arguments = []
            body = definition["body"]
            while body.get("k") == "let":
                value = body["value"]
                if value.get("k") == "perform":
                    producers.append(value)
                if (
                    value.get("k") == "call"
                    and definitions[value["callee"]]["key"][1:3]
                    == ["procedure", "forward"]
                ):
                    argument = value["args"][0]
                    while argument.get("k") == "name":
                        argument = env[argument["n"]]
                    forwarded_arguments.append(argument)
                env[body["name"]] = value
                body = body["body"]
            assert len(producers) == len(forwarded_arguments) == 2
            assert all(argument is producers[0] for argument in forwarded_arguments)
            first_producer_names.append(producers[0]["result"]["name"])

        assert len(set(first_producer_names)) == 2
        effects = [
            node
            for body in [closed.tree["body"], *(row["body"] for row in definitions.values())]
            for node in _ast_nodes(body)
            if node.get("k") == "perform"
        ]
        assert len(effects) >= 5
        assert all(effect["class"] == "run_ref" for effect in effects)
        configs = [
            decode_run_ref_static_config(base64.b64decode(effect["config"], validate=True))
            for effect in effects
        ]
        assert len({config.generated_result_type for config in configs}) == len(configs)
        signatures = [
            canonical_run_ref_signature(
                [(row.name, row.type_descriptor) for row in config.inputs],
                config.result_descriptor,
                run_ref_signatures={},
            )
            for config in configs
        ]
        assert all(signature == signatures[0] for signature in signatures)
        digests.append(closed.digest)

    assert digests[0] == digests[1]


_CARRIER_RUN_REF_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/carrier_refs) (export run)
      (defunion Wrapper :forall (T) (WRAP (value Int)))
      (defproc wrap :forall (T) ((value T)) -> Wrapper[T]
        :effects () :lowering inline (variant Wrapper[T] WRAP :value 0))
      (defproc carry :forall (T) ((value T)) -> Int
        :effects ((runs-ref child)) :lowering inline
        (let* ((state (loop-state (payload T value)))
               (check (run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
                 :program (:path "child.orc" :entry child) :inputs (:n 0) :returns Int
                 :policy (:environment :deterministic-effect-free :setup ())))) 0))
      (defworkflow run () -> Int
        (let* ((first (run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
                       :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
                       :policy (:environment :deterministic-effect-free :setup ())))
                   (second (run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
                            :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
                        :policy (:environment :deterministic-effect-free :setup ())))
               (a (carry first)) (b (carry second))
               (c (carry (list first))) (d (carry (list second)))
               (e (carry (wrap first))) (f (carry (wrap second)))) 0)))'''


def test_same_signature_run_refs_finalize_inside_phantom_loop_carriers(
    tmp_path: Path,
) -> None:
    digests = []
    for location, prefix in (
        ("original", ""),
        ("relocated/deeper", "\n; moved same-S carrier specimen\n\n"),
    ):
        root = tmp_path / location
        path = install(root, prefix + _CARRIER_RUN_REF_SOURCE)
        typed = compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
        )
        path.unlink()

        closed = _build_source_free(typed)
        effects = [
            node
            for body in [closed.tree["body"], *(row["body"] for row in closed.tree["definitions"].values())]
            for node in _ast_nodes(body)
            if node.get("k") == "perform"
        ]
        assert len(effects) == len(closed.sites)
        configs = [
            decode_run_ref_static_config(base64.b64decode(effect["config"], validate=True))
            for effect in effects
        ]
        assert len({config.generated_result_type for config in configs}) == len(configs)
        signatures = [
            canonical_run_ref_signature(
                [(row.name, row.type_descriptor) for row in config.inputs],
                config.result_descriptor,
                run_ref_signatures={},
            )
            for config in configs
        ]
        assert all(signature == signatures[0] for signature in signatures)
        carrier_types = [
            descriptor
            for name, descriptor in closed.tree["types"].items()
            if name.startswith("workflow_lisp/private::loop-state-carrier$")
        ]
        assert len(carrier_types) >= 3
        assert all("RunRefResult$" in descriptor["name"] for descriptor in carrier_types)
        digests.append(closed.digest)

    assert digests[0] == digests[1]


@pytest.mark.parametrize('mutation', ['none', 'signature', 'catalog'])
def test_projected_union_tag_finalizes_its_phantom_run_ref_owner(tmp_path, mutation):
    from tests.workflow_lisp_closed_program_helpers import BOUNDARIES

    source = _CARRIER_RUN_REF_SOURCE.replace(':effects ((runs-ref child))',
        ':effects ((runs-ref child) (uses-command fetch))').replace(
        ':setup ())))) 0))', ':setup ())))) (command-result fetch :argv ("python" "probe.py" "${inputs.root}") :returns Int)))').replace(
        '(defworkflow run ()', '(defworkflow run ((root Int))')
    assert 'command-result fetch' in source
    path = install(tmp_path, source)
    typed = compile_typed_program(path, entry_workflow='run', source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries=BOUNDARIES)
    path.unlink()
    closed = _build_source_free(typed)
    _assert_projected_run_ref_tag_owner(closed)
    finalized = [row for name, row in closed.tree['types'].items()
        if 'RunRefResult$' in name and row['kind'] == 'enum']
    assert len(finalized) == 1 and finalized[0]['allowed'] == ['WRAP']
    _assert_projected_tag_current_producer(closed, finalized[0])
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert restored.tree == closed.tree
    if mutation != 'none':
        _reject_forged_projected_run_ref_tag(restored, mutation)


def _assert_projected_tag_current_producer(closed, enum):
    (definition,) = [row for row in closed.tree['definitions'].values()
        if any(isinstance(value[0], list) and value[0][3]['path'] == ['variant'] for value in row['key'][6])]
    residual = definition['params'][-1][1]
    assert enum['name'] == residual['name'] + '.variant'
    producers = [node for node in _ast_nodes(closed.tree['body'])
        if node['k'] == 'perform' and node['class'] == 'run_ref']
    assert len(producers) == 2
    config = decode_run_ref_static_config(base64.b64decode(producers[0]['config'], validate=True))
    assert config.generated_result_type in residual['name']


def _reject_forged_projected_run_ref_tag(closed, mutation):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.program import ClosedProgramInvalid
    from tests.test_workflow_lisp_closed_program_artifact import _closed, _refresh_projected_k6_negative_name_and_sites

    tree = deepcopy(closed.tree)
    (old_name, definition), = [(name, row) for name, row in tree['definitions'].items()
        if any(isinstance(value[0], list) and value[0][3]['path'] == ['variant'] for value in row['key'][6])]
    (projection,) = [row for row in definition['key'][6] if row[0][3]['path'] == ['variant']]
    if mutation == 'signature':
        projection[1]['name']['owner']['args'][0]['signature']['inputs'][0][1] = {'kind': 'primitive', 'name': 'Bool'}
        projection[2]['type'] = deepcopy(projection[1])
        _refresh_projected_k6_negative_name_and_sites(tree, old_name, definition)
    else:
        _forge_finalized_run_ref_tag(tree)
    with pytest.raises(ClosedProgramInvalid) as error:
        ClosedProgram.from_artifact(_closed(tree).artifact())
    assert error.value.rule == 'definition_key'


def test_public_run_ref_artifact_rejects_full_digest_and_reserved_type_tampering(
    tmp_path: Path,
) -> None:
    import json
    from copy import deepcopy

    from orchestrator.workflow_lisp.closed.program import ClosedProgramInvalid

    root = tmp_path / "public-run-ref-tamper"
    path = install(root, _CARRIER_RUN_REF_SOURCE)
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
    )
    path.unlink()
    built = build_closed_program(typed)
    artifact = json.loads(built.artifact())
    assert ClosedProgram.from_artifact(built.artifact()).digest == built.digest

    digest_tamper = deepcopy(artifact)
    effects = [
        node
        for body in [
            digest_tamper["body"],
            *(row["body"] for row in digest_tamper["definitions"].values()),
        ]
        for node in _ast_nodes(body)
        if node.get("k") == "perform" and node.get("class") == "run_ref"
    ]
    assert effects
    config = json.loads(base64.b64decode(effects[0]["config"], validate=True))
    config["site_digest"] = config["site_digest"][:16] + "f" * 48
    effects[0]["config"] = base64.b64encode(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(
            json.dumps(digest_tamper, sort_keys=True, separators=(",", ":"))
        )
    assert excinfo.value.rule == "run_ref_digest"

    schema_tamper = deepcopy(artifact)
    schema_tamper["types"]["WorkspaceDelta"]["fields"][0]["name"] = "forged"
    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(
            json.dumps(schema_tamper, sort_keys=True, separators=(",", ":"))
        )
    assert excinfo.value.rule == "nominal_definition"


_LOCAL_RUN_REF_CAPTURE = '''(workflow-lisp
  (:language "0.1") (:target-dsl "TARGET")
  (defproc invoke ((runner ProcRef[Int -> Int]) (n Int)) -> Int
    :effects () :lowering inline (runner n))
  (defproc forward ((runner ProcRef[Int -> Int]) (n Int)) -> Int
    :effects () :lowering inline (invoke runner n))
  (defworkflow entry () -> Int
    (let* ((first
             (run-ref
               :source (:repo "file:///workspace"
                        :commit "0123456789abcdef0123456789abcdef01234567")
               :program (:path "child.orc" :entry child)
               :inputs (:n 1) :returns Int
               :policy (:environment :deterministic-effect-free :setup ())))
           (second
             (run-ref
               :source (:repo "file:///workspace"
                        :commit "0123456789abcdef0123456789abcdef01234567")
               :program (:path "child.orc" :entry child)
               :inputs (:n 1) :returns Int
               :policy (:environment :deterministic-effect-free :setup ()))))
      (let-proc (saved ((n Int)) -> Int
                  :captures (first)
                  (let* ((check (run-ref
                                 :source (:repo "file:///workspace"
                                          :commit "0123456789abcdef0123456789abcdef01234567")
                                 :program (:path "child.orc" :entry child)
                                 :inputs (:n 0) :returns Int
                                 :policy (:environment :deterministic-effect-free :setup ()))))
                    (+ first.value n)))
        (let* ((hook (proc-ref saved))
               (left (forward hook 0))
               (right (forward hook 1)))
          (+ left right))))))'''


def test_local_proc_ref_generated_result_capture_resolves_actual_producer(
    tmp_path: Path,
) -> None:
    root = tmp_path / "local-capture"
    path = install(root, _LOCAL_RUN_REF_CAPTURE)
    typed = compile_typed_program(
        path,
        entry_workflow="entry",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
    )
    path.unlink()

    closed = _build_source_free(typed)
    effects = [
        node
        for owner in [closed.tree["body"], *[row["body"] for row in closed.tree["definitions"].values()]]
        for node in _ast_nodes(owner)
        if node.get("k") == "perform"
    ]
    assert len(effects) == 3
    assert all(node["class"] == "run_ref" for node in effects)
    configs = [
        decode_run_ref_static_config(base64.b64decode(node["config"], validate=True))
        for node in effects
    ]
    signatures = [
        canonical_run_ref_signature(
            [(row.name, row.type_descriptor) for row in config.inputs],
            config.result_descriptor,
            run_ref_signatures={},
        )
        for config in configs
    ]
    assert signatures[0] == signatures[1] == signatures[2]
    assert len({config.generated_result_type for config in configs}) == 3

    environment = {}
    producers = []
    forwarded = []
    body = closed.tree["body"]
    while body.get("k") == "let":
        value = body["value"]
        if value.get("k") == "perform":
            producers.append(value)
        if (
            value.get("k") == "call"
            and closed.tree["definitions"][value["callee"]]["key"][1:3]
            == ["procedure", "forward"]
        ):
            argument = value["args"][0]
            while argument.get("k") == "name":
                argument = environment[argument["n"]]
            forwarded.append(argument)
        environment[body["name"]] = value
        body = body["body"]
    assert len(producers) == 2 and len(forwarded) == 2
    assert all(argument is producers[0] for argument in forwarded)


def test_multiple_local_proc_ref_captures_keep_each_actual_producer(
    tmp_path: Path,
) -> None:
    source = _LOCAL_RUN_REF_CAPTURE.replace(
        ":captures (first)",
        ":captures (first second)",
    ).replace(
        "(+ first.value n)",
        "(+ (+ first.value second.value) n)",
    )
    root = tmp_path / "multiple-captures"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="entry",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
    )
    path.unlink()

    closed = _build_source_free(typed)
    environment = {}
    producers = []
    forwarded = []
    body = closed.tree["body"]

    def resolve(value: dict) -> dict:
        while value.get("k") == "name":
            value = environment[value["n"]]
        return value

    while body.get("k") == "let":
        value = body["value"]
        if value.get("k") == "perform":
            producers.append(value)
        if (
            value.get("k") == "call"
            and closed.tree["definitions"][value["callee"]]["key"][1:3]
            == ["procedure", "forward"]
        ):
            forwarded.append([resolve(arg) for arg in value["args"][:2]])
        environment[body["name"]] = value
        body = body["body"]

    assert len(producers) == 2
    assert len(forwarded) == 2
    assert all(row[0] is producers[0] and row[1] is producers[1] for row in forwarded)


_PURE_LOCAL_CAPTURE_ONCE = '''(workflow-lisp
  (:language "0.1") (:target-dsl "TARGET")
  (defmodule entry) (export entry)
  BOX_RECORD
  (defproc identity :forall (T) ((value T)) -> T :effects () :lowering inline value)
  (defworkflow entry ((flag Bool)) -> Int
    (let* ((first EFFECT)
           (second first)
           (selected (identity (if flag first second))))
      (let-proc (saved ((n Int)) -> Int :captures (first second)
                  (+ first.value (+ second.value n)))
        (let* ((hook (proc-ref saved))) (hook selected.value))))))'''


@pytest.mark.parametrize("source_route", ("native-2.35", "imported-2.34"))
@pytest.mark.parametrize("effect_kind", ("run_ref", "command", "provider"))
def test_pure_inline_capture_evaluates_each_effectful_source_once(
    tmp_path: Path,
    source_route: str,
    effect_kind: str,
) -> None:
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint

    effects = {
        "run_ref": '''(run-ref
          :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
          :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
          :policy (:environment :deterministic-effect-free :setup ()))''',
        "command": '(command-result tool :argv ("python" "tool.py") :returns Box)',
        "provider": '(provider-result provider :prompt prompt :inputs () :returns Box)',
    }
    source = _PURE_LOCAL_CAPTURE_ONCE.replace("EFFECT", effects[effect_kind]).replace(
        "BOX_RECORD",
        "(defrecord Box (value Int))" if effect_kind != "run_ref" else "",
    )
    owner = tmp_path / "owner"
    source_target = "2.34" if source_route == "imported-2.34" else TARGET
    path = install(owner, source.replace("TARGET", source_target))
    (owner / "tool.py").write_text("raise RuntimeError('compile only')\n", encoding="utf-8")
    boundaries = {
        "tool": ExternalToolBinding(
            name="tool",
            stable_command=("python", "tool.py"),
            closure=("tool.py",),
        )
    }
    compile_inputs = {
        "source_roots": (owner,),
        "workspace_root": owner,
        "command_boundaries": boundaries,
        "provider_externs": {"provider": "selected-provider"},
        "prompt_externs": {"prompt": {"input_file": "prompts/source.md"}},
    }
    if source_route == "native-2.35":
        typed = compile_typed_program(
            path,
            entry_workflow="entry",
            **compile_inputs,
        )
    else:
        native = compile_stage3_entrypoint(
            path,
            validate_shared=True,
            **compile_inputs,
        )
        bundle = native.validated_bundles_by_name["entry::entry"]
        caller = tmp_path / "caller"
        consumer = install(
            caller,
            '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
              (defmodule consumer) (export run)
              (defworkflow run ((flag Bool)) -> Int (call dep :flag flag)))''',
        )
        typed = compile_typed_program(
            consumer,
            entry_workflow="run",
            source_roots=(caller,),
            workspace_root=caller,
            command_boundaries={},
            imported_workflow_bundles={"dep": bundle},
        )
        consumer.unlink()
    for authored in owner.rglob("*.orc"):
        authored.unlink()

    closed = _build_source_free(typed)
    bodies = [closed.tree["body"], *(row["body"] for row in closed.tree["definitions"].values())]
    selected_effects = [
        node
        for body in bodies
        for node in _ast_nodes(body)
        if node.get("k") == "perform"
    ]
    assert len(selected_effects) == len(closed.sites) == 1
    assert selected_effects[0]["class"] == effect_kind

    captured_values = [
        node
        for value in bodies
        for node in _ast_nodes(value)
        if node.get("k") == "field" and node.get("path") == ["value"]
    ]
    assert len(captured_values) >= 3


_SELECTED_RUN_REF_ALIAS = '''(workflow-lisp
  (:language "0.1") (:target-dsl "TARGET")
  (defproc identity :forall (T) ((value T)) -> T :effects () :lowering inline value)
  (defworkflow entry ((flag Bool)) -> Int
    (let* ((first
             (run-ref
               :source (:repo "file:///workspace"
                        :commit "0123456789abcdef0123456789abcdef01234567")
               :program (:path "child.orc" :entry child)
               :inputs (:n 1) :returns Int
               :policy (:environment :deterministic-effect-free :setup ())))
           (second first)
           (selected (identity (if flag first second))))
      (let-proc (saved ((n Int)) -> Int :captures (first second)
                  (+ first.value (+ second.value n)))
        (let* ((hook (proc-ref saved))) (hook selected.value))))))'''


def test_select_value_prefix_keeps_actual_run_ref_aliases_in_local_proc_capture(
    tmp_path: Path,
) -> None:
    digests = []
    for location, decoration in (
        ("original", ""),
        ("relocated/deeper", "\n; relocated source with extra spacing\n\n"),
    ):
        root = tmp_path / location
        path = install(root, decoration + _SELECTED_RUN_REF_ALIAS)
        typed = compile_typed_program(
            path,
            entry_workflow="entry",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
        )
        path.unlink()

        closed = _build_source_free(typed)
        values = [closed.tree["body"], *(row["body"] for row in closed.tree["definitions"].values())]
        selects = [
            node
            for body in values
            for node in _ast_nodes(body)
            if node.get("k") == "select"
        ]
        effects = [
            node
            for body in values
            for node in _ast_nodes(body)
            if node.get("k") == "perform" and node.get("class") == "run_ref"
        ]
        assert len(selects) == 1
        assert len(effects) == len(closed.sites) == 1
        configs = [
            decode_run_ref_static_config(base64.b64decode(node["config"], validate=True))
            for node in effects
        ]
        assert len({config.generated_result_type for config in configs}) == 1
        signatures = [
            canonical_run_ref_signature(
                [(row.name, row.type_descriptor) for row in config.inputs],
                config.result_descriptor,
                run_ref_signatures={},
            )
            for config in configs
        ]
        assert len(signatures) == 1

        environment = {}
        body = closed.tree["body"]
        while body.get("k") == "let":
            environment[body["name"]] = body["value"]
            body = body["body"]

        def producers_for(value: dict, scope: dict) -> set[int]:
            kind = value.get("k")
            if kind == "name":
                return producers_for(scope[value["n"]], scope)
            if kind == "perform" and value.get("class") == "run_ref":
                return {id(value)}
            if kind == "block":
                local = dict(scope)
                nested = value["body"]
                while nested.get("k") == "let":
                    local[nested["name"]] = nested["value"]
                    nested = nested["body"]
                return producers_for(nested["value"], local)
            if kind == "select":
                result = set()
                for arm_name in ("then", "else"):
                    arm = value[arm_name]
                    local = dict(scope)
                    for row in arm["prefix"]:
                        local[row["name"]] = row["value"]
                    result.update(producers_for(arm["value"], local))
                return result
            return set()

        producer = effects[0]
        captured_values = [
            node
            for body in values
            for node in _ast_nodes(body)
            if node.get("k") == "field" and node.get("path") == ["value"]
        ]
        assert len(captured_values) >= 3
        assert all(
            producers_for(node["base"], environment) == {id(producer)}
            for node in captured_values
        )
        digests.append(closed.digest)

    assert digests[0] == digests[1]


def test_run_ref_compiler_pin_is_independent_of_package_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from orchestrator.workflow.run_ref import contracts as run_ref_contracts

    root = tmp_path / "source"
    path = install(root, _LOCAL_RUN_REF_CAPTURE)
    typed = compile_typed_program(
        path,
        entry_workflow="entry",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
    )
    path.unlink()

    first = _build_source_free(typed)
    package_root = Path(run_ref_contracts.__file__).resolve().parents[2]
    relocated_package = tmp_path / "relocated-package" / "orchestrator"
    shutil.copytree(
        package_root,
        relocated_package,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    monkeypatch.setattr(
        run_ref_contracts,
        "__file__",
        str(relocated_package / "workflow" / "run_ref" / "contracts.py"),
    )
    second = _build_source_free(typed)

    assert first.digest == second.digest
    assert first.sites == second.sites
    first_configs = [
        decode_run_ref_static_config(base64.b64decode(node["config"], validate=True))
        for body in [first.tree["body"], *(row["body"] for row in first.tree["definitions"].values())]
        for node in _ast_nodes(body)
        if node.get("k") == "perform" and node.get("class") == "run_ref"
    ]
    second_configs = [
        decode_run_ref_static_config(base64.b64decode(node["config"], validate=True))
        for body in [second.tree["body"], *(row["body"] for row in second.tree["definitions"].values())]
        for node in _ast_nodes(body)
        if node.get("k") == "perform" and node.get("class") == "run_ref"
    ]
    assert len(first_configs) == len(second_configs) == 3
    assert [row.compiler_runtime_identity_digest for row in first_configs] == [
        row.compiler_runtime_identity_digest for row in second_configs
    ]
    assert [row.site_digest for row in first_configs] == [
        row.site_digest for row in second_configs
    ]


def _rename_compiled_run_ref_results(body, replacements, *, retarget=False):
    from dataclasses import replace
    from orchestrator.workflow_lisp.wcc.model import WccLet, WccHalt, WccPureOp

    if not isinstance(body, WccLet):
        assert isinstance(body, WccHalt)
        return body
    value = body.bound_value
    if retarget and isinstance(value, WccPureOp):
        left, right = value.args
        value = replace(value, args=(replace(left, base=right.base), right))
    replacement = replacements.get(id(value))
    if replacement is not None:
        value = replace(value, metadata=replace(value.metadata, type_ref=replacement.metadata.type_ref),
            returns_type_name=replacement.returns_type_name, operation_payload=replacement.operation_payload)
    return replace(body, bound_value=value,
        bound_type_ref=value.metadata.type_ref if replacement is not None else body.bound_type_ref,
        body=_rename_compiled_run_ref_results(body.body, replacements, retarget=retarget))


@pytest.mark.parametrize('retarget', [False, True])
@pytest.mark.parametrize('nested', [False, True])
def test_preparation_run_ref_generated_names_preserve_actual_producer_wiring(tmp_path, monkeypatch, retarget, nested):
    from tests.test_workflow_lisp_closed_command_transport import _compile
    from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
    from tests.test_workflow_lisp_closed_preparation_integrity import _prepare_other_owner, _registrations, _forbid_emission
    from tests.test_workflow_lisp_command_scopes import _walk
    from orchestrator.workflow_lisp.wcc.model import WccPerform
    from orchestrator.workflow_lisp.closed.names import _key_type_ref, _run_ref_signatures

    run = '(run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567") '
    run += ':program (:path "child.orc" :entry child) :inputs (:n VALUE) :returns Int '
    run += ':policy (:environment :deterministic-effect-free :setup ()))'
    declaration = '(defproc helper () -> Int :effects ((runs-ref child) (uses-command echo)) :lowering inline '
    declaration += '(let* ((first ' + run.replace('VALUE', '1') + ') (second ' + run.replace('VALUE', '2')
    declaration += ') '
    if nested:
        declaration += '(third ' + run.replace('VALUE', 'first') + ') (fourth ' + run.replace('VALUE', 'second') + ') '
    declaration += '(out (command-result echo :argv ("python" "probe.py") :returns Int))) '
    declaration += '(+ third.value fourth.value)))' if nested else '(+ first.value second.value)))'
    first = _compile(tmp_path / 'first', '(helper)', declarations=declaration)
    _, _, builder = _prepared_entry(first)
    second = _compile(tmp_path / 'second', '(helper)', declarations=declaration)
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)

    def mutate(body, call, source):
        if not call.definition.name.endswith('helper'):
            return body
        pair = [node for node in _walk(body) if isinstance(node, WccPerform) and node.perform_kind == 'run_ref']
        assert len(pair) == (4 if nested else 2)
        replacements = {}
        for left, right in zip(pair[::2], pair[1::2], strict=True):
            assert left.returns_type_name != right.returns_type_name
            assert _key_type_ref(left.metadata.type_ref, typed=source, run_ref_signatures=_run_ref_signatures(source)) == _key_type_ref(
                right.metadata.type_ref, typed=source, run_ref_signatures=_run_ref_signatures(source))
            replacements.update({id(left): right, id(right): left})
        return _rename_compiled_run_ref_results(body, replacements, retarget=retarget)

    if retarget:
        with pytest.raises(ValueError, match=r'contradictory prepared.*\.base'):
            _prepare_other_owner(second, builder, monkeypatch, mutate)
    else:
        _prepare_other_owner(second, builder, monkeypatch, mutate)
    assert _registrations(builder) == registrations


def test_repeated_mixed_reference_calls_keep_both_original_materialized_bindings(tmp_path):
    from orchestrator.workflow_lisp.closed.program import ClosedProgram
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes
    from tests.test_workflow_lisp_closed_command_transport import _compile, _command

    declarations = '(defrecord Box (n Int)) (defworkflow child ((input Box)) -> Box '
    declarations += '(command-result echo :argv ("python" "probe.py" input.n) :returns Box))'
    declarations += '(defproc mapper ((n Box)) -> Box :effects () :lowering inline (record Box :n (+ n.n 1)))'
    declarations += '(defproc invoke ((runner WorkflowRef[Box -> Box]) '
    declarations += '(map ProcRef[Box -> Box]) (n Box)) -> Box '
    declarations += ':effects ((calls-workflow runner)) :lowering inline '
    declarations += '(let* ((mapped (map n))) (call runner :input mapped)))'
    source = '(let* ((first (invoke (workflow-ref child) (proc-ref mapper) n))) '
    source += '(invoke (workflow-ref child) (proc-ref mapper) first))'
    program = _compile(tmp_path, source, params='(n Box)', declarations=declarations, returns='Box')
    originals = [row for row in program.procedures.values()
        if getattr(row.specialization, 'base_name', None) == 'cp/transport::invoke'
        and row.specialization.workflow_ref_bindings and row.specialization.proc_ref_bindings]
    assert len(originals) == 1
    assert set(originals[0].specialization.workflow_ref_bindings) == {'runner'}
    assert set(originals[0].specialization.proc_ref_bindings) == {'map'}
    closed = build_closed_program(program)
    _assert_repeated_mixed_reference_bindings(closed)
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


def _assert_projected_run_ref_tag_owner(closed):
    projections = [row for definition in closed.tree['definitions'].values()
        for row in definition['key'][6]
        if isinstance(row[0], list) and row[0][3]['path'] == ['variant']]
    assert len(projections) == 1
    selector, descriptor, literal = projections[0]
    assert selector[:3] == ['projection', 'value', 0]
    assert descriptor['kind'] == 'enum' and literal == {'k': 'lit', 'v': 'WRAP', 'type': descriptor}
    assert descriptor['name']['member'] == 'variant'
    assert descriptor['name']['owner']['args'][0]['kind'] == 'run-ref-result'


def _forge_finalized_run_ref_tag(tree):
    for name, row in tree['types'].items():
        if 'RunRefResult$' in name and row['kind'] == 'enum':
            row['allowed'] = ['FORGED']


def _assert_repeated_mixed_reference_bindings(closed):
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    (invoke,) = [row for row in closed.tree['definitions'].values() if row['key'][2] == 'invoke']
    assert [row[0] for row in invoke['key'][4]] == ['map']
    assert [row[0] for row in invoke['key'][5]] == ['runner']
    assert len(invoke['params']) == 1
    calls = [node for node in _ast_nodes(closed.tree['body']) if node['k'] == 'call']
    assert len(calls) == 2
    assert calls[0]['callee'] == calls[1]['callee']
