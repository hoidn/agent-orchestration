from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest


POLICY_FIELDS = {
    "schema_version",
    "mode",
    "backend",
    "session_mode",
    "workspace",
    "provider_environment",
    "process_environment",
    "result_bundle",
    "shared_network_review",
    "history_retrieval",
}

ENVIRONMENT_DIGEST = f"sha256:{'a' * 64}"
INVENTORY_DIGEST = f"sha256:{'b' * 64}"

VALID_POLICY: dict[str, Any] = {
    "schema_version": "provider_phase_isolation.v1",
    "mode": "required",
    "backend": "bubblewrap.v1",
    "session_mode": "fresh_only",
    "workspace": {
        "access": "read_write",
        "masked_runtime_roots": [".orchestrate"],
    },
    "provider_environment": {
        "root": "/srv/orchestrator/provider-rootfs",
        "provider_prefix": "/opt/orchestrator-provider",
        "digest": ENVIRONMENT_DIGEST,
    },
    "process_environment": {
        "credential_env": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
    },
    "result_bundle": {
        "max_bytes": 16_777_216,
    },
    "shared_network_review": {
        "inventory_path": "/srv/orchestrator/private/network-inventory.json",
        "inventory_digest": INVENTORY_DIGEST,
        "decision": "accept_unlisted_reachability",
    },
    "history_retrieval": {
        "eligibility_requirement": "classify",
        "provider_api_transport": "allow",
        "remote_git": "deny",
        "browser": "deny",
        "source_search": "deny",
        "repository_fetch": "deny",
    },
}

# Independent whole-policy golden. The embedded environment digest is fixed
# above and is intentionally not this digest.
WHOLE_POLICY_DIGEST = (
    "sha256:137412daa8490755250cde3614a865ba74ccbfb1e6a700f287913e2ac1328993"
)


def _api():
    return importlib.import_module("orchestrator.providers.isolation")


def _public_api():
    return importlib.import_module("orchestrator.providers")


def _load(document: dict[str, Any] | None = None, **kwargs: Any):
    return _api().load_provider_phase_isolation_policy(
        deepcopy(VALID_POLICY if document is None else document),
        **kwargs,
    )


def _issues(document: dict[str, Any], **kwargs: Any):
    return _api().validate_provider_phase_isolation_policy(
        deepcopy(document),
        **kwargs,
    )


def _assert_issue_paths(document: dict[str, Any], *paths: str) -> None:
    api = _api()
    issues = _issues(document)
    assert issues
    assert {issue.code for issue in issues} == {
        "provider_isolation_policy_invalid"
    }
    assert tuple(issue.path for issue in issues) == tuple(sorted(paths))
    with pytest.raises(api.ProviderIsolationPolicyError) as exc_info:
        _load(document)
    assert exc_info.value.issues == issues


























@pytest.mark.parametrize("max_bytes", [True, 0, -1, 16_777_217, 1.5])
def test_result_bundle_bound_is_a_positive_v1_bounded_integer(
    max_bytes: object,
) -> None:
    document = deepcopy(VALID_POLICY)
    document["result_bundle"]["max_bytes"] = max_bytes

    _assert_issue_paths(document, "$.result_bundle.max_bytes")


































