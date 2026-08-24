"""Code-owned OMP launch provider templates (Task 5, OMP-I1).

Five registry templates cover the pinned OMP lanes. Every template wraps the
pinned binary exclusively through ``orchestrator.providers.omp_launch``; the
binary path, pin digest, positive environment, and Landlock confinement are
owned by the adapter, never authored per workflow. No template exposes a
binary path, lane, or approval flag: ``--lane`` carries the registry name and
the adapter maps it to the code-owned policy lane.
"""

from __future__ import annotations

import sys
from typing import Dict

from .types import (
    CallPolicyBinding,
    InputMode,
    ProviderSessionMetadataMode,
    ProviderSessionSupport,
    ProviderTemplate,
)

DEFAULT_OMP_MODEL = "openai-codex/gpt-5.6-sol"

_WRAPPER = [sys.executable, "-m", "orchestrator.providers.omp_launch"]


def _omp_template(
    name: str,
    *,
    conf_root: bool = False,
) -> ProviderTemplate:
    """One OMP template: wrapper argv + model, optional conf root."""
    command = [*_WRAPPER, "run", "--lane", name, "--model", "${model}"]
    if conf_root:
        command += ["--conf-root", "${omp_conf_root}"]
    fresh_command = command + [
        "--provider-session-dir",
        "${PROVIDER_SESSION_DIR}",
    ]
    return ProviderTemplate(
        name=name,
        command=command,
        defaults={"model": DEFAULT_OMP_MODEL},
        input_mode=InputMode.STDIN,
        session_support=ProviderSessionSupport(
            metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
            fresh_command=fresh_command,
            resume_command=None,
            turn_boundary_resume=False,
        ),
        call_policy_bindings={"model": CallPolicyBinding(target_param="model")},
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )


def omp_templates() -> Dict[str, ProviderTemplate]:
    """Return the five pinned OMP provider templates keyed by registry name."""
    return {
        "omp": _omp_template("omp"),
        "omp_unrestricted_workspace": _omp_template(
            "omp_unrestricted_workspace"
        ),
        "omp_no_tools": _omp_template("omp_no_tools"),
        "omp_conf": _omp_template("omp_conf", conf_root=True),
        "omp_conf_inference": _omp_template("omp_conf_inference"),
    }
