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


def test_public_policy_api_exports_immutable_types_and_loader() -> None:
    api = _public_api()

    policy = _load()

    assert isinstance(policy, api.ProviderPhaseIsolationPolicy)
    assert isinstance(policy.provider_environment, api.ProviderEnvironmentIdentity)
    assert isinstance(policy.history_retrieval, api.HistoryRetrievalPolicy)
    assert policy.credential_env == ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    with pytest.raises((AttributeError, TypeError)):
        policy.mode = "optional"
    with pytest.raises((AttributeError, TypeError)):
        policy.provider_environment.digest = f"sha256:{'c' * 64}"


def test_policy_schema_and_model_have_exact_closed_top_level_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    api = _api()

    schema = api.load_provider_isolation_schema(
        "provider-phase-isolation-v1.schema.json"
    )
    policy = _load()

    assert set(schema["properties"]) == POLICY_FIELDS
    assert set(schema["required"]) == POLICY_FIELDS
    assert schema["additionalProperties"] is False
    assert set(policy.to_dict()) == POLICY_FIELDS
    assert policy.to_dict() == VALID_POLICY


def test_unknown_fields_and_versions_are_rejected_recursively() -> None:
    document = deepcopy(VALID_POLICY)
    document["unexpected"] = True
    document["workspace"]["unexpected"] = True
    document["history_retrieval"]["unexpected"] = True
    document["schema_version"] = "provider_phase_isolation.v2"

    _assert_issue_paths(
        document,
        "$.history_retrieval.unexpected",
        "$.schema_version",
        "$.unexpected",
        "$.workspace.unexpected",
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("mode",), "optional"),
        (("backend",), "other.v1"),
        (("session_mode",), "resume"),
        (("workspace", "access"), "read_only"),
        (("workspace", "masked_runtime_roots"), []),
        (("workspace", "masked_runtime_roots"), [".orchestrate", ".git"]),
    ],
)
def test_v1_fixed_policy_modes_are_closed(
    path: tuple[str, ...], value: object
) -> None:
    document = deepcopy(VALID_POLICY)
    target: dict[str, Any] = document
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value

    _assert_issue_paths(document, "$." + ".".join(path))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("root", "relative/provider-rootfs"),
        ("provider_prefix", "relative/provider-prefix"),
    ],
)
def test_provider_environment_paths_are_absolute(field: str, value: str) -> None:
    document = deepcopy(VALID_POLICY)
    document["provider_environment"][field] = value

    _assert_issue_paths(document, f"$.provider_environment.{field}")


@pytest.mark.parametrize(
    "prefix",
    [
        "/",
        "/home/provider",
        "/workspace/provider",
        "/tmp/provider",
        "/run/provider",
        "/proc/provider",
        "/dev/provider",
        "/sys/provider",
        "/bin",
        "/sbin",
        "/usr",
        "/lib",
        "/lib64",
        "/etc",
        "/opt",
        "/var",
    ],
)
def test_provider_prefix_rejects_runtime_overlay_kernel_and_reserved_destinations(
    prefix: str,
) -> None:
    document = deepcopy(VALID_POLICY)
    document["provider_environment"]["provider_prefix"] = prefix

    _assert_issue_paths(document, "$.provider_environment.provider_prefix")


def test_provider_prefix_uses_path_components_not_string_prefixes() -> None:
    document = deepcopy(VALID_POLICY)
    document["provider_environment"][
        "provider_prefix"
    ] = "/workspace-tools/orchestrator-provider"

    assert _load(document).provider_environment.provider_prefix == (
        "/workspace-tools/orchestrator-provider"
    )


@pytest.mark.parametrize(
    "digest",
    [
        "a" * 64,
        f"sha256:{'A' * 64}",
        f"sha256:{'a' * 63}",
        f"sha512:{'a' * 64}",
        f"sha256:{'g' * 64}",
        f"sha256:{'a' * 64}\n",
    ],
)
def test_provider_environment_digest_is_canonical_sha256(digest: str) -> None:
    document = deepcopy(VALID_POLICY)
    document["provider_environment"]["digest"] = digest

    _assert_issue_paths(document, "$.provider_environment.digest")


def test_credential_names_are_unique_ordered_and_valid() -> None:
    document = deepcopy(VALID_POLICY)
    document["process_environment"]["credential_env"] = [
        "Z_SERVICE_TOKEN",
        "A_SERVICE_TOKEN_2",
    ]

    policy = _load(document)

    assert policy.credential_env == ("Z_SERVICE_TOKEN", "A_SERVICE_TOKEN_2")

    duplicate = deepcopy(document)
    duplicate["process_environment"]["credential_env"].append("Z_SERVICE_TOKEN")
    _assert_issue_paths(
        duplicate,
        "$.process_environment.credential_env",
    )

    invalid = deepcopy(document)
    invalid["process_environment"]["credential_env"] = ["NOT-AN-ENV-NAME"]
    _assert_issue_paths(
        invalid,
        "$.process_environment.credential_env[0]",
    )


@pytest.mark.parametrize(
    "name",
    [
        "PATH",
        "HOME",
        "PWD",
        "TMPDIR",
        "XDG_CONFIG_HOME",
        "XDG_CUSTOM",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "BASH_ENV",
        "ENV",
        "NODE_OPTIONS",
        "SSH_AUTH_SOCK",
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_TIME",
        "TZ",
        "TZDIR",
    ],
)
def test_credential_allowlist_rejects_runtime_loader_interpreter_shell_locale_and_time_names(
    name: str,
) -> None:
    document = deepcopy(VALID_POLICY)
    document["process_environment"]["credential_env"] = [name]

    _assert_issue_paths(
        document,
        "$.process_environment.credential_env[0]",
    )


@pytest.mark.parametrize("max_bytes", [True, 0, -1, 16_777_217, 1.5])
def test_result_bundle_bound_is_a_positive_v1_bounded_integer(
    max_bytes: object,
) -> None:
    document = deepcopy(VALID_POLICY)
    document["result_bundle"]["max_bytes"] = max_bytes

    _assert_issue_paths(document, "$.result_bundle.max_bytes")


def test_result_bundle_accepts_both_positive_v1_boundaries() -> None:
    for max_bytes in (1, 16_777_216):
        document = deepcopy(VALID_POLICY)
        document["result_bundle"]["max_bytes"] = max_bytes
        assert _load(document).result_bundle_max_bytes == max_bytes


def test_integral_float_is_reported_as_a_stable_policy_issue_before_load() -> None:
    document = deepcopy(VALID_POLICY)
    document["result_bundle"]["max_bytes"] = 1.0

    _assert_issue_paths(document, "$.result_bundle.max_bytes")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("inventory_path", "relative/inventory.json"),
        ("inventory_digest", f"sha256:{'B' * 64}"),
        ("inventory_digest", f"sha256:{'b' * 63}"),
        ("decision", "accept_all_reachability"),
    ],
)
def test_shared_network_review_is_closed_absolute_and_canonical(
    field: str, value: str
) -> None:
    document = deepcopy(VALID_POLICY)
    document["shared_network_review"][field] = value

    _assert_issue_paths(document, f"$.shared_network_review.{field}")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_api_transport", "deny"),
        ("remote_git", "allow"),
        ("browser", "allow"),
        ("source_search", "allow"),
        ("repository_fetch", "allow"),
    ],
)
def test_provider_transport_and_four_history_retrieval_channels_are_independent_and_fixed(
    field: str, value: str
) -> None:
    document = deepcopy(VALID_POLICY)
    document["history_retrieval"][field] = value

    _assert_issue_paths(document, f"$.history_retrieval.{field}")


@pytest.mark.parametrize("requirement", ["classify", "require_causal"])
def test_history_retrieval_accepts_both_v1_eligibility_requirements(
    requirement: str,
) -> None:
    document = deepcopy(VALID_POLICY)
    document["history_retrieval"]["eligibility_requirement"] = requirement

    policy = _load(document)

    assert policy.history_retrieval.eligibility_requirement == requirement


def test_history_retrieval_rejects_other_eligibility_requirements() -> None:
    document = deepcopy(VALID_POLICY)
    document["history_retrieval"]["eligibility_requirement"] = "assume_causal"

    _assert_issue_paths(
        document,
        "$.history_retrieval.eligibility_requirement",
    )


def test_whole_policy_identity_is_canonical_and_independent_of_key_order() -> None:
    reversed_document = {
        key: deepcopy(VALID_POLICY[key]) for key in reversed(tuple(VALID_POLICY))
    }
    reversed_document["workspace"] = {
        key: reversed_document["workspace"][key]
        for key in reversed(tuple(reversed_document["workspace"]))
    }

    original = _load()
    reordered = _load(reversed_document)

    assert original.policy_digest == WHOLE_POLICY_DIGEST
    assert reordered.policy_digest == WHOLE_POLICY_DIGEST
    assert original.canonical_json == reordered.canonical_json
    assert original.canonical_json.endswith(b"\n")
    assert original.policy_digest == (
        "sha256:" + hashlib.sha256(original.canonical_json).hexdigest()
    )


def test_non_environment_change_changes_whole_policy_only() -> None:
    changed = deepcopy(VALID_POLICY)
    changed["history_retrieval"]["eligibility_requirement"] = "require_causal"

    original_policy = _load()
    changed_policy = _load(changed)

    assert original_policy.provider_environment.digest == ENVIRONMENT_DIGEST
    assert changed_policy.provider_environment.digest == ENVIRONMENT_DIGEST
    assert changed_policy.policy_digest != original_policy.policy_digest


def test_environment_digest_cannot_be_substituted_as_whole_policy_identity() -> None:
    api = _api()

    with pytest.raises(api.ProviderIsolationPolicyError) as exc_info:
        _load(expected_policy_digest=ENVIRONMENT_DIGEST)

    assert [(issue.code, issue.path) for issue in exc_info.value.issues] == [
        ("provider_isolation_policy_invalid", "$.policy_digest")
    ]


def test_canonical_json_bytes_have_one_shared_ascii_and_unicode_contract() -> None:
    canonical = _api().canonical_isolation_json_bytes

    assert canonical({"z": "ok", "a": [True, None, 2]}) == (
        b'{"a":[true,null,2],"z":"ok"}\n'
    )
    assert canonical(
        {
            "\u00e9": "composed",
            "e\u0301": "decomposed",
            "ascii": "\u03bb",
        }
    ) == (
        '{"ascii":"λ","é":"decomposed","é":"composed"}\n'.encode("utf-8")
    )
    assert canonical({"line": "value\n"}) == b'{"line":"value\\n"}\n'


@pytest.mark.parametrize(
    "value",
    [
        {"value": 1.0},
        {"value": float("nan")},
        {"value": float("inf")},
        {"nested": [{"value": -1.25}]},
    ],
)
def test_canonical_json_bytes_reject_all_floats(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="float"):
        _api().canonical_isolation_json_bytes(value)


def test_canonical_json_bytes_sort_future_manifest_rows_by_normalized_utf8_path() -> None:
    canonical = _api().canonical_isolation_json_bytes
    manifest = {
        "schema_version": "provider_environment_manifest.v1",
        "provider_prefix": "/opt/orchestrator-provider",
        "entries": [
            {"path": "é", "kind": "directory"},
            {"path": "z", "kind": "directory"},
            {"path": ".", "kind": "directory"},
            {"path": "alpha", "kind": "directory"},
        ],
    }

    encoded = canonical(manifest)
    rows = json.loads(encoded)["entries"]

    assert [row["path"] for row in rows] == [".", "alpha", "z", "é"]
    assert encoded.endswith(b"\n")
    assert not encoded.endswith(b"\n\n")


@pytest.mark.parametrize(
    ("document", "path"),
    [
        (
            {
                **VALID_POLICY,
                "provider_environment": {
                    **VALID_POLICY["provider_environment"],
                    "root": "/srv/cafe\u0301/rootfs",
                },
            },
            "$.provider_environment.root",
        ),
        (
            {
                **VALID_POLICY,
                "shared_network_review": {
                    **VALID_POLICY["shared_network_review"],
                    "inventory_path": "/srv/cafe\u0301/inventory.json",
                },
            },
            "$.shared_network_review.inventory_path",
        ),
    ],
)
def test_policy_filesystem_paths_must_already_be_unicode_nfc(
    document: dict[str, Any], path: str
) -> None:
    _assert_issue_paths(document, path)


@pytest.mark.parametrize(
    ("container", "field", "path"),
    [
        (
            "provider_environment",
            "root",
            "$.provider_environment.root",
        ),
        (
            "provider_environment",
            "provider_prefix",
            "$.provider_environment.provider_prefix",
        ),
        (
            "shared_network_review",
            "inventory_path",
            "$.shared_network_review.inventory_path",
        ),
    ],
)
def test_lone_surrogate_filesystem_paths_are_stable_policy_issues(
    container: str,
    field: str,
    path: str,
) -> None:
    document = deepcopy(VALID_POLICY)
    document[container][field] = "/sealed/\ud800"

    _assert_issue_paths(document, path)


def test_future_manifest_relpaths_must_already_be_nfc_and_normalized() -> None:
    canonical = _api().canonical_isolation_json_bytes
    base = {
        "schema_version": "provider_environment_manifest.v1",
        "provider_prefix": "/opt/orchestrator-provider",
    }

    with pytest.raises(ValueError, match="NFC"):
        canonical(
            {
                **base,
                "entries": [{"path": "cafe\u0301", "kind": "directory"}],
            }
        )
    with pytest.raises(ValueError, match="normalized POSIX relative path"):
        canonical(
            {
                **base,
                "entries": [{"path": "a/../b", "kind": "directory"}],
            }
        )


def test_future_manifest_relpaths_reject_nul() -> None:
    manifest = {
        "schema_version": "provider_environment_manifest.v1",
        "provider_prefix": "/opt/orchestrator-provider",
        "entries": [{"path": "a\x00b", "kind": "directory"}],
    }

    with pytest.raises(ValueError, match="NUL"):
        _api().canonical_isolation_json_bytes(manifest)


def test_policy_error_returns_all_deterministically_sorted_issues() -> None:
    api = _api()
    document = deepcopy(VALID_POLICY)
    document["mode"] = "optional"
    document["workspace"]["extra"] = "not-allowed"
    document["process_environment"]["credential_env"] = ["PATH", "PATH"]
    document["result_bundle"]["max_bytes"] = 0

    issues = _issues(document)

    assert issues == tuple(sorted(issues, key=lambda issue: (issue.path, issue.message)))
    assert [issue.path for issue in issues] == [
        "$.mode",
        "$.process_environment.credential_env",
        "$.process_environment.credential_env[0]",
        "$.process_environment.credential_env[1]",
        "$.result_bundle.max_bytes",
        "$.workspace.extra",
    ]
    assert all(
        isinstance(issue, api.ProviderIsolationIssue) and issue.path.startswith("$")
        for issue in issues
    )
