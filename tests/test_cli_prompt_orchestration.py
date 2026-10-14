"""Historical scaffold verification and immutable native preflight captures."""

import json
import os

import pytest

from orchestrator.prompt_scaffold import ScaffoldVerificationError, verify_scaffold
from orchestrator.prompt_session import PromptSessionError
from orchestrator.prompt_session_scaffold import verify_captured_occupant
from tests.test_prompt_scaffold import _historical_scaffold, _inputs, _admit, CONF_DIR


@pytest.mark.parametrize("mutation", ["files", "manifest-identity"])
def test_historical_verification_capture_rejects_swapped_live_scaffold(tmp_path, mutation):
    result, _inputs_value = _historical_scaffold(tmp_path, b"p")
    verification = result.verification
    original = dict(verification.files)
    original_manifest = verification.manifest_bytes
    descriptor = os.open(result.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        verify_captured_occupant(descriptor, verification, private=False)
        if mutation == "manifest-identity":
            manifest_path = result.path / "scaffold.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["identity"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
        else:
            for name, data in (
                ("prompt.md", b"changed source bytes"),
                ("run.orc", b"(workflow-lisp)\n(changed)\n"),
                ("output-contract.json", b'{"mode":"scalar","type":"Int"}'),
                ("scaffold.json", b"{}"),
            ):
                (result.path / name).write_bytes(data)
        assert dict(verification.files) == original
        assert verification.manifest_bytes == original_manifest
        with pytest.raises(PromptSessionError, match="session_link_invalid"):
            verify_captured_occupant(descriptor, verification, private=False)
    finally:
        os.close(descriptor)


def test_historical_prompt_file_bytes_are_captured_verbatim(tmp_path):
    result, inputs = _historical_scaffold(tmp_path, b"p")
    prompt_file = result.path / "prompt.md"
    original = prompt_file.read_bytes()
    assert result.verification.files["prompt.md"] == original
    prompt_file.unlink()
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, inputs=inputs)
    assert result.verification.files["prompt.md"] == original


def test_historical_omp_conf_capture_retains_private_conf_bytes(tmp_path):
    conf = _admit(CONF_DIR / "neutral")
    result, _inputs_value = _historical_scaffold(tmp_path, b"p", provider="omp_conf", conf=conf)
    captured = result.verification
    assert captured.provider == "omp_conf"
    assert dict(captured.conf_files) == {name: row.content for name, row in conf.files.items()}
    for name, data in captured.conf_files.items():
        assert captured.files["conf/" + name] == data
        assert (result.path / "conf" / name).read_bytes() == data


def test_scaffold_identity_explicit_model_wins_over_template_default(monkeypatch):
    from orchestrator.providers import omp_templates as templates_source
    from orchestrator.providers import registry as registry_module

    original = templates_source.omp_templates

    def tracking_templates():
        templates = original()
        templates["omp_no_tools"].defaults["model"] = "template-default-model"
        return templates

    monkeypatch.setattr(templates_source, "omp_templates", tracking_templates)
    monkeypatch.setattr(registry_module, "omp_templates", tracking_templates)
    inputs = _inputs(b"p", provider="omp_no_tools", model="explicit-model")
    assert inputs.model == "explicit-model"


def test_scaffold_inputs_reject_installed_template_drift(monkeypatch):
    from orchestrator.providers import omp_templates as templates_source
    from orchestrator.providers import registry as registry_module

    original = templates_source.omp_templates

    def drifting_templates():
        templates = original()
        templates["omp_no_tools"].defaults["model"] = "drifted-model"
        return templates

    monkeypatch.setattr(registry_module, "omp_templates", drifting_templates)
    with pytest.raises(ValueError, match="does not match"):
        _inputs(b"p", provider="omp_no_tools")


@pytest.mark.parametrize("payload", [
    b"\xff\xfe\x00broken", b"{not json", b'[1, 2, 3]',
    b'{"provider": [1, 2]}', b'{"provider": null}',
])
def test_historical_scaffold_manifest_verification_fails_closed(tmp_path, payload):
    result, inputs = _historical_scaffold(tmp_path, b"p")
    (result.path / "scaffold.json").write_bytes(payload)
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, inputs=inputs)


def test_historical_output_contract_verification_fails_closed(tmp_path):
    result, inputs = _historical_scaffold(tmp_path, b"p")
    (result.path / "output-contract.json").write_bytes(b"\xff\xfe\x00broken")
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, inputs=inputs)
