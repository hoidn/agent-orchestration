"""Typed result guidance survives public evaluated execution and completed resume."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from collections.abc import Mapping

from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.result_guidance import normalized_result_guidance_payload
from tests.prompt_contract_test_helpers import parse_prompt_contract_document


FIXTURE = Path(__file__).parent / "fixtures/workflow_lisp/valid/native_bool_return_guidance.orc"
_GUIDANCE_KEYS = ("description", "format_hint", "example", "guidance_context", "guidance_by_variant")
SHIM = '''import json, os, sys
from pathlib import Path
with Path("requests.jsonl").open("a") as stream:
    stream.write(json.dumps({"prompt": sys.stdin.read()}) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(os.environ["GUIDANCE_RESULT"])
print("observability output")
'''


def _guidance_payload(spec: Mapping[str, object]) -> dict[str, object]:
    return {key: spec[key] for key in _GUIDANCE_KEYS if key in spec}


def _variant_guidance_projection(contract: Mapping[str, object]) -> dict[str, object]:
    guidance = contract.get("guidance")
    return {
        "guidance": _guidance_payload(guidance) if isinstance(guidance, Mapping) else {},
        "shared_fields": {field["name"]: _guidance_payload(field)
                          for field in contract.get("shared_fields", ())},
        "variants": {variant: {field["name"]: _guidance_payload(field)
                               for field in payload.get("fields", ())}
                     for variant, payload in contract.get("variants", {}).items()},
    }


def _fixture(root: Path, source: str, *, module: str, result: object, commands=False):
    path = root / f"{module}.orc"
    path.write_text(source)
    (root / "prompt.md").write_text("Review the change.\n")
    providers, prompts = root / "providers.json", root / "prompts.json"
    providers.write_text(json.dumps({"providers.review": "codex"}))
    prompts.write_text(json.dumps({"prompts.review": {"input_file": "prompt.md"}}))
    command_manifest = None
    if commands:
        command_manifest = root / "commands.json"
        scripts = root / "scripts"
        scripts.mkdir()
        bindings = {}
        for name in ("record_approved", "record_revise"):
            script = scripts / f"{name}.py"
            script.write_text('import os\nfrom pathlib import Path\n'
                              'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("true")\n')
            bindings[name] = {"stable_command": ["python", f"scripts/{name}.py"],
                              "closure": [f"scripts/{name}.py"]}
        command_manifest.write_text(json.dumps(bindings))
    binary = root / "bin/codex"
    binary.parent.mkdir()
    binary.write_text(f"#!{sys.executable}\n" + SHIM)
    binary.chmod(0o700)
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]),
           "PYTHONDONTWRITEBYTECODE": "1", "GUIDANCE_RESULT": json.dumps(result),
           "PATH": str(binary.parent) + os.pathsep + os.environ["PATH"]}
    request = FrontendBuildRequest(source_path=path, source_roots=(root,), workspace_root=root,
        provider_externs_path=providers, prompt_externs_path=prompts,
        command_boundaries_path=command_manifest)
    built = build_closed_program_bundle(request)
    arguments = ["run", str(path), "--source-root", str(root),
                 "--provider-externs-file", str(providers), "--prompt-externs-file", str(prompts)]
    if command_manifest is not None:
        arguments += ["--command-boundaries-file", str(command_manifest)]
    return built, arguments, env


def _run_and_resume(root: Path, built, arguments, env):
    first = subprocess.run([sys.executable, "-B", "-m", "orchestrator", *arguments],
        cwd=root, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    (run_root,) = (root / ".orchestrate/runs").iterdir()
    memo = read_memo(run_root / "memo.jsonl", site_classes(built.program))
    assert memo.terminal is not None and memo.terminal.data["outcome"] == "completed"
    requests = (root / "requests.jsonl").read_bytes()
    memo_bytes = (run_root / "memo.jsonl").read_bytes()
    resumed = subprocess.run([sys.executable, "-B", "-m", "orchestrator", "resume", run_root.name],
        cwd=root, env=env, capture_output=True, text=True)
    assert resumed.returncode == 0, resumed.stderr
    assert (root / "requests.jsonl").read_bytes() == requests
    assert (run_root / "memo.jsonl").read_bytes() == memo_bytes
    (request,) = [json.loads(line) for line in requests.splitlines()]
    return memo, parse_prompt_contract_document(request["prompt"])


def _provider(built):
    bodies = [built.program.tree["body"],
              *(row["body"] for row in built.program.tree["definitions"].values())]
    (provider,) = [node for body in bodies for node in _ast_nodes(body)
                  if node.get("class") == "provider"]
    return provider


def test_direct_bool_provider_guidance_executes_without_wrapper_or_overall_prompt_leak(tmp_path: Path) -> None:
    source = FIXTURE.read_text().replace('(:target-dsl "2.15")', '(:target-dsl "2.35")')
    built, arguments, env = _fixture(tmp_path, source,
        module="native_bool_return_guidance", result=True, commands=True)
    provider = _provider(built)
    (occurrence,) = provider["contract"]["payload"]["fields"]
    entry = built.typed_program.entry
    overall = normalized_result_guidance_payload(entry.definition.return_spec.guidance,
        expected_type=entry.signature.return_type_ref,
        type_env=built.typed_program.workflow_type_env(entry.definition.name))
    assert overall
    memo, prompt_contract = _run_and_resume(tmp_path, built, arguments, env)
    assert prompt_contract["type"] == occurrence["type"] == "bool"
    assert _guidance_payload(prompt_contract) == _guidance_payload(occurrence)
    assert _guidance_payload(prompt_contract) != overall
    assert "result_guidance" not in prompt_contract
    assert "guidance" not in provider["contract"]["payload"]
    commits = [entry.data for entry in memo.entries if entry.data["record"] == "committed"]
    assert [row["effect_class"] for row in commits] == ["provider", "command"]
    assert [row["value"] for row in commits] == [True, True]
    assert memo.terminal.data["value"] is True


def test_nested_union_guidance_renders_and_selected_variant_keeps_source_lineage(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule guidance_runtime_neutrality) (export orchestrate)
      (defrecord ReviewMeta (score Float :example 0.9))
      (defunion Decision
        (APPROVE (approved Bool :description "Approval branch flag." :example true)
                 (meta ReviewMeta :description "Approval metrics context."))
        (REVISE (approved Bool :description "Revision branch flag." :example false)
                (reason String :example "fix tests")))
      (defworkflow orchestrate () -> (result Decision :description "Completed routed review result.")
        (provider-result providers.review :prompt prompts.review :inputs ()
          :returns (result Decision :description "Choose the review route." :format-hint "Tagged decision object."))))'''
    value = {"variant": "APPROVE", "approved": True, "meta": {"score": 0.9}}
    built, arguments, env = _fixture(tmp_path, source,
        module="guidance_runtime_neutrality", result=value)
    provider = _provider(built)
    contract = provider["contract"]["payload"]
    subjects = provider["@"]["source_map_subject"]
    approved = next(row for row in subjects if row["field"] == "source_map_subjects_by_variant")
    assert tuple(approved["value"]) == ("APPROVE", "REVISE")
    assert approved["value"]["APPROVE"]["subject_name"].endswith("Decision::APPROVE::approved")
    assert approved["value"]["APPROVE"]["workflow_name"] == "workflow:guidance_runtime_neutrality::orchestrate"
    assert any(row["value"].get("subject_name", "").endswith("Decision::APPROVE::meta__score")
               for row in subjects)
    memo, prompt_contract = _run_and_resume(tmp_path, built, arguments, env)
    assert _variant_guidance_projection(prompt_contract) == _variant_guidance_projection(contract)
    assert contract["guidance"]
    assert any(field.get("guidance_by_variant") for field in contract["shared_fields"])
    assert any(field.get("guidance_context") for variant in contract["variants"].values()
               for field in variant["fields"])
    assert memo.terminal.data["value"] == value
