"""Task 8: `prompt run` orchestration — capture-before-mutation, closed
inference mapping, snapshot isolation, compile-before-run, and rerun.

Step 8.2 behavior: default/exact modes make no inference call; ``--output``
runs only the internal ``omp_conf_inference`` workflow with typed inputs;
captured prompt/template/model/conf/contract sources are consumed after every
live-source mutation barrier; generated source compiles before the provider
starts; run ids are reserved before scaffold verification; rerun
reconstructs identity inputs from one published scaffold.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.prompt_contract import canonical_json_bytes
from orchestrator.prompt_scaffold import ScaffoldCompileError
from orchestrator.state import StateManager

from tests.test_cli_prompt import (  # noqa: F401  (shared harness)
    INFERENCE_PROVIDER,
    OUTPUT_REQUEST,
    TASK_TEXT,
    _exit,
    _generated_scaffold,
    _rerun_fails_closed,
    _run_roots,
    fake_runtime,
)
# Step 8.2 — orchestration
# ---------------------------------------------------------------------------

def test_default_mode_runs_task_without_inference(
    tmp_path, monkeypatch, fake_runtime, capsys
):
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert fake_runtime.provider_names() == ["omp_no_tools"]
    [invocation] = fake_runtime.executed
    assert TASK_TEXT in invocation.prompt
    # Scaffold path goes to stderr only; stdout stays clean.
    captured = capsys.readouterr()
    scaffold = _generated_scaffold(tmp_path)
    assert f"scaffold: {scaffold}" in captured.err
    assert "scaffold" not in captured.out
    # Exactly one reserved run root with a private snapshot beneath it.
    run_roots = _run_roots(tmp_path)
    assert len(run_roots) == 1
    snapshot = run_roots[0] / "prompt-inputs"
    assert (snapshot / "run.orc").is_file()
    assert (snapshot / "prompt.md").read_bytes() == TASK_TEXT.encode("utf-8")
    assert (snapshot / "output-contract.json").is_file()
    assert (snapshot / "providers.json").is_file()
    assert (snapshot / "prompts.json").is_file()
def test_task_run_materializes_output_bundle_from_transport_text(
    tmp_path, monkeypatch, fake_runtime
):
    fake_runtime.skip_bundle_write = True
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert fake_runtime.provider_names() == ["omp_no_tools"]
    bundles = sorted(
        (tmp_path / ".orchestrate").rglob(
            "__write_root__run_run__result__result_bundle.json"
        )
    )
    assert len(bundles) == 1
    assert json.loads(bundles[0].read_text(encoding="utf-8")) == "fresh-value"

def test_exact_mode_makes_no_inference_call(tmp_path, monkeypatch, fake_runtime):
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools",
         "--returns", '{"mode":"scalar","type":"String"}'],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert fake_runtime.provider_names() == ["omp_no_tools"]
    scaffold = _generated_scaffold(tmp_path)
    manifest = json.loads((scaffold / "scaffold.json").read_text(encoding="utf-8"))
    assert manifest["provider"]["registry_name"] == "omp_no_tools"
    contract_doc = json.loads(
        (scaffold / "output-contract.json").read_text(encoding="utf-8")
    )
    assert contract_doc["semantic"] == {"mode": "scalar", "type": "String"}

def test_output_maps_to_inference_then_task(tmp_path, monkeypatch, fake_runtime):
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools",
         "--output", OUTPUT_REQUEST],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert fake_runtime.provider_names() == [INFERENCE_PROVIDER, "omp_no_tools"]
    inference, task = fake_runtime.executed
    # Typed task-prompt/output-request inputs are in the composed inference prompt.
    assert TASK_TEXT in inference.prompt
    assert OUTPUT_REQUEST in inference.prompt
    assert task.prompt != inference.prompt
    # Neutral isolation: internal conf-inference lane, no session, transient.
    assert "omp_conf_inference" in inference.command
    assert inference.session_request is None
    assert inference.omp_transport_expectation is not None
    assert inference.omp_transport_expectation.lane == "conf-inference"
    assert inference.omp_transport_expectation.persistence == "none"
    # The task run keeps the ordinary fresh session.
    assert task.session_request is not None
    assert task.omp_transport_expectation is not None
    assert task.omp_transport_expectation.persistence == "fresh"
    # The inferred contract and provenance are authored into the scaffold.
    scaffold = _generated_scaffold(tmp_path)
    contract_doc = json.loads(
        (scaffold / "output-contract.json").read_text(encoding="utf-8")
    )
    assert contract_doc["semantic"]["mode"] == "record"
    assert contract_doc["semantic"]["fields"] == [
        {"name": "summary", "type": "String"}
    ]
    assert contract_doc["authoring"]["mode"] == "inferred"
    assert contract_doc["authoring"]["provider"] == INFERENCE_PROVIDER
    assert contract_doc["authoring"]["session_id"] == f"session-{INFERENCE_PROVIDER}"
    assert contract_doc["authoring"]["usage"]["totalTokens"] == 15
    # Two reserved run roots: inference then task.
    assert len(_run_roots(tmp_path)) == 2

def test_output_uses_captured_model_for_inference(tmp_path, monkeypatch, fake_runtime):
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools",
         "--model", "my-model", "--output", OUTPUT_REQUEST],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    inference, task = fake_runtime.executed
    assert "my-model" in inference.command
    assert "my-model" in task.command
    scaffold = _generated_scaffold(tmp_path)
    manifest = json.loads((scaffold / "scaffold.json").read_text(encoding="utf-8"))
    assert manifest["provider"]["concrete_model"] == "my-model"

def test_output_rejects_ambient_providers_before_model_call(
    tmp_path, monkeypatch, fake_runtime
):
    for provider in ("omp", "omp_unrestricted_workspace"):
        code = _exit(
            ["prompt", "run", "--prompt", TASK_TEXT, "--provider", provider,
             "--output", OUTPUT_REQUEST],
            tmp_path,
            monkeypatch,
        )
        assert code == 2, provider
        assert fake_runtime.executed == [], provider
        assert not (tmp_path / ".orchestrate").exists(), provider

def test_inference_invalid_draft_fails_without_fallback(
    tmp_path, monkeypatch, fake_runtime
):
    fake_runtime.draft = {"fields": "not-a-list"}
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools",
         "--output", OUTPUT_REQUEST],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    # Inference ran; the task provider never started; nothing was published.
    assert fake_runtime.provider_names() == [INFERENCE_PROVIDER]
    assert not (tmp_path / "workflows" / "generated").exists()

def test_compile_failure_precedes_provider_start(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.prompt_scaffold as scaffold_service

    def fail_compile(snapshot, provider):
        raise ScaffoldCompileError("boom")

    monkeypatch.setattr(scaffold_service, "compile_snapshot", fail_compile)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []

def test_barrier_swapped_live_scaffold_never_reaches_compiler_or_provider(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.prompt_scaffold as scaffold_service

    original_generate = scaffold_service.generate_scaffold
    original_prompt = TASK_TEXT.encode("utf-8")
    swapped_prompt = b"SWAPPED-PROMPT"
    swapped = {"mode": "scalar", "type": "Int"}

    def generate_and_swap(**kwargs):
        result = original_generate(**kwargs)
        # Barrier: replace every live scaffold input after verification.
        for name, data in (
            ("prompt.md", swapped_prompt),
            ("run.orc", b"(workflow-lisp)\n(swapped)\n"),
            ("output-contract.json", canonical_json_bytes(swapped)),
            ("scaffold.json", b"{}"),
        ):
            (result.path / name).write_bytes(data)
        return result

    monkeypatch.setattr(scaffold_service, "generate_scaffold", generate_and_swap)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    # The private snapshot holds the captured bytes, not the swapped ones.
    [run_root] = _run_roots(tmp_path)
    snapshot = run_root / "prompt-inputs"
    assert (snapshot / "prompt.md").read_bytes() == original_prompt
    assert "SWAPPED-PROMPT" not in (snapshot / "prompt.md").read_bytes().decode()
    assert (snapshot / "run.orc").read_bytes().startswith(b"(workflow-lisp")
    [invocation] = fake_runtime.executed
    assert TASK_TEXT in invocation.prompt
    assert "SWAPPED-PROMPT" not in invocation.prompt

def test_prompt_file_bytes_are_captured_verbatim(tmp_path, monkeypatch, fake_runtime):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_bytes(TASK_TEXT.encode("utf-8") + b"\n\nsecond line\n")
    code = _exit(
        ["prompt", "run", "--prompt-file", str(prompt_file),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    assert (scaffold / "prompt.md").read_bytes() == prompt_file.read_bytes()
    assert "second line" in fake_runtime.executed[0].prompt
    # A missing prompt file is a capture failure (exit 1), not a grammar error.
    code = _exit(
        ["prompt", "run", "--prompt-file", str(tmp_path / "missing.md"),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert _exit(["prompt", "run", "--prompt-file", "",
                  "--provider", "omp_no_tools"], tmp_path, monkeypatch) == 2

def test_omp_conf_task_receives_snapshot_conf_root(tmp_path, monkeypatch, fake_runtime):
    import shutil

    conf = tmp_path / "conf"
    shutil.copytree(
        Path(__file__).parent / "fixtures" / "omp" / "conf" / "neutral", conf
    )
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_conf",
         "--conf", str(conf)],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert fake_runtime.provider_names() == ["omp_conf"]
    [task] = fake_runtime.executed
    assert "--conf-root" in task.command
    # The task sees the private snapshot conf, never the live source conf.
    snapshot = _run_roots(tmp_path)[0] / "prompt-inputs" / "conf"
    assert (snapshot / "config.yml").read_bytes() == (conf / "config.yml").read_bytes()
    assert str(snapshot) in task.command


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Early template capture: the model comes from the captured template default
# and later mutation of the live source objects is inert
# ---------------------------------------------------------------------------

def test_model_derived_from_captured_template_and_late_mutation_inert(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.cli.commands.prompt as prompt_module
    from orchestrator.providers import omp_templates as templates_source
    from orchestrator.providers import registry as registry_module

    original = templates_source.omp_templates
    captured_objects: list[object] = []

    def tracking_templates():
        templates = original()
        templates["omp_no_tools"].defaults["model"] = "captured-template-model"
        captured_objects.append(templates["omp_no_tools"])
        return templates

    # Every consumer sees the same code-owned table: the capture seam, the
    # registry loader, and the identity validator's function-local import.
    monkeypatch.setattr(templates_source, "omp_templates", tracking_templates)
    monkeypatch.setattr(registry_module, "omp_templates", tracking_templates)
    monkeypatch.setattr(
        prompt_module, "omp_templates", tracking_templates, raising=False
    )

    original_capture = prompt_module._capture_generation

    def capture_then_mutate(mode):
        captured = original_capture(mode)
        # Barrier: mutate the source objects the capture read from.
        for template in captured_objects:
            template.defaults["model"] = "MUTATED-AFTER-CAPTURE"
        return captured

    monkeypatch.setattr(prompt_module, "_capture_generation", capture_then_mutate)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    manifest = json.loads((scaffold / "scaffold.json").read_text(encoding="utf-8"))
    assert manifest["provider"]["concrete_model"] == "captured-template-model"
    run_orc = (scaffold / "run.orc").read_text(encoding="utf-8")
    assert 'captured-template-model' in run_orc
    assert "MUTATED-AFTER-CAPTURE" not in run_orc
    [invocation] = fake_runtime.executed
    assert "captured-template-model" in invocation.command

def test_explicit_model_still_wins_over_template_default(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.cli.commands.prompt as prompt_module
    from orchestrator.providers import omp_templates as templates_source
    from orchestrator.providers import registry as registry_module

    original = templates_source.omp_templates

    def tracking_templates():
        templates = original()
        templates["omp_no_tools"].defaults["model"] = "template-default-model"
        return templates

    # Every consumer sees the same code-owned table: the capture seam, the
    # registry loader, and the template-identity validator.
    monkeypatch.setattr(templates_source, "omp_templates", tracking_templates)
    monkeypatch.setattr(registry_module, "omp_templates", tracking_templates)
    monkeypatch.setattr(
        prompt_module, "omp_templates", tracking_templates, raising=False
    )
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools",
         "--model", "explicit-model"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    manifest = json.loads((scaffold / "scaffold.json").read_text(encoding="utf-8"))
    assert manifest["provider"]["concrete_model"] == "explicit-model"
    assert "template-default-model" not in (scaffold / "run.orc").read_text()

def test_inference_model_injection_fails_without_exact_asset_marker(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.cli.commands.prompt as prompt_module

    asset = Path(prompt_module.inference_output_contract_path())
    broken = tmp_path / "infer-broken.orc"
    broken.write_bytes(
        asset.read_bytes().replace(
            b"      :inputs (task_prompt output_request)\n", b""
        )
    )
    monkeypatch.setattr(
        prompt_module, "inference_output_contract_path", lambda: str(broken)
    )
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools",
         "--output", OUTPUT_REQUEST],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []

def test_template_drift_rejected_before_provider_execution(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.cli.commands.prompt as prompt_module
    from orchestrator.providers import omp_templates as templates_source
    from orchestrator.providers import registry as registry_module

    original = templates_source.omp_templates

    def drifting_templates():
        templates = original()
        templates["omp_no_tools"].defaults["model"] = "drifted-model"
        return templates

    # Only the INSTALLED side drifts; the code-owned table stays authoritative.
    monkeypatch.setattr(registry_module, "omp_templates", drifting_templates)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    assert not (tmp_path / "workflows" / "generated").exists()
    assert not (tmp_path / ".orchestrate").exists()

@pytest.mark.parametrize(
    "payload",
    [
        b"\xff\xfe\x00broken",      # malformed UTF-8
        b"{not json",               # malformed JSON
        b'[1, 2, 3]',               # valid JSON, not an object
        b'{"provider": [1, 2]}',   # object with a list provider
        b'{"provider": null}',     # object with a null provider
    ],
)
def test_rerun_invalid_scaffold_manifest_fails_closed(
    tmp_path, monkeypatch, fake_runtime, capsys, payload
):
    _rerun_fails_closed(
        tmp_path, monkeypatch, fake_runtime, capsys,
        "scaffold.json", payload,
    )

@pytest.mark.parametrize(
    "initial, mutate, expected_authoring",
    [
        # default: mutate in an exact --returns after capture
        (None, "returns", "default"),
        # exact: clear --returns after capture -> still exact
        ('{"mode":"scalar","type":"String"}', "clear_returns", "exact"),
        # inferred: clear --output after capture -> inference still runs
        ("output", "clear_output", "inferred"),
    ],
)
def test_contract_mode_and_payload_captured_before_mode_mutation(
    tmp_path, monkeypatch, fake_runtime, initial, mutate, expected_authoring,
):
    import orchestrator.cli.commands.prompt as prompt_module

    argv = ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"]
    if initial == "output":
        argv += ["--output", OUTPUT_REQUEST]
    elif initial is not None:
        argv += ["--returns", initial]
    original_capture = prompt_module._capture_generation

    def capture_then_mutate(mode):
        captured = original_capture(mode)
        if mutate == "returns":
            mode["returns"] = '{"mode":"scalar","type":"String"}'
        elif mutate == "clear_returns":
            mode["returns"] = None
        elif mutate == "clear_output":
            mode["output"] = None
        return captured

    monkeypatch.setattr(prompt_module, "_capture_generation", capture_then_mutate)
    assert _exit(argv, tmp_path, monkeypatch) == 0
    expected = (
        [INFERENCE_PROVIDER, "omp_no_tools"]
        if expected_authoring == "inferred" else ["omp_no_tools"]
    )
    assert fake_runtime.provider_names() == expected
    doc = json.loads(
        (_generated_scaffold(tmp_path) / "output-contract.json").read_text(
            encoding="utf-8")
    )
    assert doc["authoring"]["mode"] == expected_authoring
    if expected_authoring != "inferred":
        assert doc["semantic"] == {"mode": "scalar", "type": "String"}

def test_rerun_invalid_output_contract_fails_closed(
    tmp_path, monkeypatch, fake_runtime, capsys
):
    _rerun_fails_closed(
        tmp_path, monkeypatch, fake_runtime, capsys,
        "output-contract.json", b"\xff\xfe\x00broken",
    )
