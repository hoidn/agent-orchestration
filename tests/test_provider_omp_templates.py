"""Registry OMP template contract (Task 5, OMP-I1)."""

from __future__ import annotations

import sys

from orchestrator.providers.omp_templates import DEFAULT_OMP_MODEL, omp_templates
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import (
    InputMode,
    ProviderSessionMetadataMode,
)

_WRAPPER = [sys.executable, "-m", "orchestrator.providers.omp_launch"]


def _expected_command(name: str) -> list[str]:
    return [*_WRAPPER, "run", "--lane", name, "--model", "${model}"]


def test_five_pinned_templates_are_registered() -> None:
    registry = ProviderRegistry()
    for name in (
        "omp",
        "omp_unrestricted_workspace",
        "omp_no_tools",
        "omp_conf",
        "omp_conf_inference",
    ):
        template = registry.get(name)
        assert template is not None, name
        assert template.name == name


def test_each_template_has_exact_common_contract() -> None:
    for name, template in omp_templates().items():
        assert template.input_mode == InputMode.STDIN
        assert template.defaults == {"model": DEFAULT_OMP_MODEL}
        assert template.command_metadata_mode == (
            ProviderSessionMetadataMode.OMP_JSON_STDOUT.value
        )
        assert template.call_policy_bindings["model"].target_param == "model"
        support = template.session_support
        assert support is not None
        assert support.metadata_mode == (
            ProviderSessionMetadataMode.OMP_JSON_STDOUT.value
        )
        assert support.resume_command is None
        assert support.turn_boundary_resume is False
        assert template.interactive_session_support is None
        assert template.validate() == []


def test_omp_command_argv_exact() -> None:
    template = omp_templates()["omp"]
    assert template.command == _expected_command("omp")
    assert template.session_support.fresh_command == _expected_command(
        "omp"
    ) + ["--provider-session-dir", "${PROVIDER_SESSION_DIR}"]


def test_conf_template_carries_conf_root_placeholder() -> None:
    template = omp_templates()["omp_conf"]
    assert template.command == _expected_command("omp_conf") + [
        "--conf-root",
        "${omp_conf_root}",
    ]
    assert template.session_support.fresh_command == _expected_command(
        "omp_conf"
    ) + ["--conf-root", "${omp_conf_root}", "--provider-session-dir", "${PROVIDER_SESSION_DIR}"]


def test_no_tools_uses_reserved_conf_carrier_and_inference_uses_neutral_default() -> None:
    no_tools = omp_templates()["omp_no_tools"]
    prefix = _expected_command("omp_no_tools") + [
        "--conf-root", "${PROVIDER_CONF_ROOT}"
    ]
    assert no_tools.command == prefix
    assert no_tools.session_support.fresh_command == prefix + [
        "--provider-session-dir", "${PROVIDER_SESSION_DIR}"
    ]
    inference = omp_templates()["omp_conf_inference"]
    assert inference.command == _expected_command("omp_conf_inference")


def test_templates_expose_no_authorable_binary_or_approval_flags() -> None:
    for name, template in omp_templates().items():
        tokens = set(template.command) | set(template.session_support.fresh_command)
        assert "--session-dir" not in tokens
        assert "--yolo" not in tokens
        assert "--no-tools" not in tokens
        assert "--add-dir" not in tokens
        assert not any(
            token.startswith("/") and token != sys.executable
            for token in tokens
        )
        assert not any("dist-omp" in token for token in tokens)
        if name not in ("omp_conf", "omp_no_tools"):
            assert "--conf-root" not in tokens
        conf_tokens = (
            {"--conf-root", "${omp_conf_root}"} if name == "omp_conf"
            else {"--conf-root", "${PROVIDER_CONF_ROOT}"}
            if name == "omp_no_tools" else set()
        )
        assert tokens == set(_expected_command(name)) | conf_tokens | {
            "--provider-session-dir", "${PROVIDER_SESSION_DIR}"
        }


def test_omp_unrestricted_workspace_is_ambient_without_flags() -> None:
    template = omp_templates()["omp_unrestricted_workspace"]
    assert template.command == _expected_command("omp_unrestricted_workspace")
