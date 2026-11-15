"""Real provider reads follow checked workflow-reference activations."""

from hashlib import sha256
import os
from dataclasses import replace

import pytest

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.evaluated.authority import publish_run_authority
from orchestrator.providers.registry import ProviderRegistry
from tests.test_workflow_evaluated_provider_lifecycle import (
    _execute, _fixture, _requests, _snapshot,
)
from tests.test_workflow_evaluated_provider_io import (
    WREF, _checked, _reader_path, _stages, _typed,
)
from tests.agent_session_shims import closed_path


@pytest.mark.parametrize(
    "wrapper", ("alias", "forward", "bound", "nested-bound")
)
def test_provider_reads_follow_alias_and_bound_reference_routes(tmp_path, wrapper):
    _, imports = _stages(tmp_path)
    _reader_path(imports["right"]).with_name("prompt.md").write_text(
        "TARGET RIGHT\n", encoding="utf-8"
    )
    if wrapper in {"alias", "forward"}:
        argument = "runner" if wrapper == "forward" else "alias"
        body = f"(foo {argument} input)"
        if wrapper == "alias":
            body = f"(let* ((alias runner)) {body})"
        declaration = f'''(defproc outer ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box
          {body})'''
        source = WREF.replace("(defworkflow run", declaration + "\n(defworkflow run")
        source = source.replace("(foo (workflow-ref", "(outer (workflow-ref")
    else:
        declaration = '''(defproc invoke ((hook ProcRef[Box -> Box]) (input Box)) -> Box
          (hook input))'''
        source = WREF.replace("(defworkflow run", declaration + "\n(defworkflow run")
        for side in ("left", "right"):
            bound = f"(bind-proc (proc-ref foo) :runner (workflow-ref {side}))"
            if wrapper == "nested-bound":
                bound = f"(bind-proc (proc-ref invoke) :hook {bound})"
            source = source.replace(
                f"(foo (workflow-ref {side})", f"(invoke {bound}"
            )
    checked, provider_io = _checked(_typed(tmp_path, source, imports))
    reads = []

    def handle(node, operands, _identity, owner, reader):
        from orchestrator.workflow.evaluated.providers import resolve_provider_io

        captured = resolve_provider_io(
            node, operands, workspace=tmp_path, reader=reader
        )
        reads.append((owner, reader.workflow_path, captured))
        return coerce_evaluated_value(
            {"n": len(reads)}, node["result"], context="controlled provider result"
        )

    evaluate_closed_program(
        checked,
        {"input": {"n": 0}},
        effect_handler=handle,
        provider_io=provider_io,
    )

    assert [read.source_text for _owner, _path, read in reads] == [
        "PARENT INLINE\n",
        "TARGET LEFT\n",
        "PARENT INLINE\n",
        "TARGET RIGHT\n",
    ]
    assert [read.source_sha256 for _owner, _path, read in reads] == [
        "sha256:" + sha256(content.encode()).hexdigest()
        for content in (
            "PARENT INLINE\n",
            "TARGET LEFT\n",
            "PARENT INLINE\n",
            "TARGET RIGHT\n",
        )
    ]
    assert reads[0][0] == reads[2][0]
    assert reads[1][0] == reads[3][0]


def test_supplied_staged_provider_selection_reaches_real_performer(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tests.test_workflow_evaluated_provider_io import WREF, _checked, _stages, _typed

    _fixture(tmp_path)
    _, imports = _stages(tmp_path)
    _reader_path(imports["right"]).with_name("prompt.md").write_text("TARGET RIGHT\n")
    checked, provider_io = _checked(_typed(tmp_path, WREF, imports))
    original = ProviderRegistry._load_builtin_providers

    def templates(registry):
        providers = original(registry)
        providers["provider-id"] = replace(providers["codex"], name="provider-id")
        return providers

    monkeypatch.setattr(ProviderRegistry, "_load_builtin_providers", templates)
    monkeypatch.setenv("PATH", closed_path(tmp_path / "bin"))
    monkeypatch.setenv("PROVIDER_SHIM_RESULT", '{"n":7}')
    built = SimpleNamespace(program=checked, provider_io=provider_io)
    with publish_run_authority(tmp_path / ".state" / "run-1", checked, run_id="run-1",
        workflow_file="consumer/main.orc", workflow_checksum="sha256:" + sha256(WREF.encode()).hexdigest(),
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs={"input": {"n": 0}}) as authority:
        assert _execute(tmp_path, built, authority, inputs={"input": {"n": 0}}) == (0, {"n": 7})
        requests = _requests(tmp_path)
        assert [row["prompt"].splitlines()[0] for row in requests] == [
            "PARENT INLINE", "TARGET LEFT", "PARENT INLINE", "TARGET RIGHT"]
        assert len(_snapshot(built, authority).active_commits) == 4
