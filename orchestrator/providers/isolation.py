"""Versioned provider-phase isolation policy and canonical identity."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from importlib import resources
import json
import posixpath
import re
from typing import Any
import unicodedata

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


POLICY_SCHEMA_RESOURCE = "provider-phase-isolation-v1.schema.json"
POLICY_SCHEMA_VERSION = "provider_phase_isolation.v1"
POLICY_ERROR_CODE = "provider_isolation_policy_invalid"
MAX_RESULT_BUNDLE_BYTES = 16_777_216

_SCHEMA_PACKAGE = "orchestrator.providers.schemas"
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RUNTIME_PROVIDER_PREFIX_ROOTS = (
    "/home",
    "/workspace",
    "/tmp",
    "/run",
    "/proc",
    "/dev",
    "/sys",
)
_RESERVED_PROVIDER_PREFIX_DESTINATIONS = frozenset(
    {
        "/",
        "/bin",
        "/sbin",
        "/usr",
        "/lib",
        "/lib32",
        "/lib64",
        "/etc",
        "/opt",
        "/var",
    }
)
_RESERVED_CREDENTIAL_NAMES = frozenset(
    {
        "BASH_ENV",
        "CONDA_PREFIX",
        "ENV",
        "HOME",
        "LANG",
        "LANGUAGE",
        "NODE_OPTIONS",
        "NODE_PATH",
        "OLDPWD",
        "PATH",
        "PWD",
        "RUBYLIB",
        "RUBYOPT",
        "SHELLOPTS",
        "SHLVL",
        "SSH_AUTH_SOCK",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "TZDIR",
        "VIRTUAL_ENV",
        "_",
    }
)
_RESERVED_CREDENTIAL_PREFIXES = (
    "DYLD_",
    "LC_",
    "LD_",
    "ORCHESTRATOR_",
    "PYTHON",
    "XDG_",
)


@dataclass(frozen=True, order=True, slots=True)
class ProviderIsolationIssue:
    """One deterministic provider-isolation policy validation issue."""

    code: str
    path: str
    message: str


class ProviderIsolationPolicyError(ValueError):
    """Public error raised after all deterministic policy issues are collected."""

    code = POLICY_ERROR_CODE

    def __init__(self, issues: Sequence[ProviderIsolationIssue]):
        self.issues = tuple(issues)
        detail = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(f"{POLICY_ERROR_CODE}: {detail}")


@dataclass(frozen=True, slots=True)
class ProviderEnvironmentIdentity:
    """Immutable identity of the policy-selected sealed provider environment."""

    root: str
    provider_prefix: str
    digest: str


@dataclass(frozen=True, slots=True)
class HistoryRetrievalPolicy:
    """Independently represented provider transport and retrieval capabilities."""

    eligibility_requirement: str
    provider_api_transport: str
    remote_git: str
    browser: str
    source_search: str
    repository_fetch: str


@dataclass(frozen=True, slots=True)
class ProviderPhaseIsolationPolicy:
    """Validated immutable ``provider_phase_isolation.v1`` policy."""

    schema_version: str
    mode: str
    backend: str
    session_mode: str
    workspace_access: str
    masked_runtime_roots: tuple[str, ...]
    provider_environment: ProviderEnvironmentIdentity
    credential_env: tuple[str, ...]
    result_bundle_max_bytes: int
    shared_network_inventory_path: str
    shared_network_inventory_digest: str
    shared_network_decision: str
    history_retrieval: HistoryRetrievalPolicy
    canonical_json: bytes = field(repr=False)
    policy_digest: str

    @property
    def digest(self) -> str:
        """Return the complete policy identity, never the environment identity."""

        return self.policy_digest

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON representation of the validated policy."""

        value = json.loads(self.canonical_json)
        if not isinstance(value, dict):  # pragma: no cover - construction invariant
            raise AssertionError("validated policy canonical JSON is not an object")
        return value


def load_provider_isolation_schema(resource_name: str) -> dict[str, Any]:
    """Load one packaged provider-isolation schema via ``importlib.resources``."""

    if (
        not isinstance(resource_name, str)
        or not resource_name.endswith(".json")
        or "/" in resource_name
        or "\\" in resource_name
        or resource_name in {".json", "..json"}
    ):
        raise ValueError("schema resource name must be one JSON basename")
    schema_resource = resources.files(_SCHEMA_PACKAGE).joinpath(resource_name)
    with schema_resource.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"schema resource {resource_name!r} must contain an object")
    return value


def canonical_isolation_json_bytes(value: Any) -> bytes:
    """Encode one closed isolation record using the shared canonical contract."""

    canonical_value = _canonical_json_value(value, "$")
    if (
        isinstance(canonical_value, dict)
        and canonical_value.get("schema_version")
        == "provider_environment_manifest.v1"
        and "entries" in canonical_value
    ):
        entries = canonical_value["entries"]
        if not isinstance(entries, list):
            raise TypeError("$.entries must be an array")
        for index, row in enumerate(entries):
            if not isinstance(row, dict):
                raise TypeError(f"$.entries[{index}] must be an object")
            relpath = row.get("path")
            _require_normalized_manifest_relpath(relpath, f"$.entries[{index}].path")
        canonical_value["entries"] = sorted(
            entries,
            key=lambda row: row["path"].encode("utf-8"),
        )
    try:
        encoded = json.dumps(
            canonical_value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("canonical isolation JSON strings must be strict UTF-8") from exc
    return encoded + b"\n"


def validate_provider_phase_isolation_policy(
    document: object,
    *,
    expected_policy_digest: str | None = None,
) -> tuple[ProviderIsolationIssue, ...]:
    """Return every deterministic schema, semantic, and identity issue."""

    schema = load_provider_isolation_schema(POLICY_SCHEMA_RESOURCE)
    validator = Draft202012Validator(schema)
    issues = _schema_validation_issues(validator.iter_errors(document))

    if isinstance(document, Mapping):
        issues.extend(_semantic_policy_issues(document))

    if expected_policy_digest is not None:
        if (
            not isinstance(expected_policy_digest, str)
            or _DIGEST_PATTERN.fullmatch(expected_policy_digest) is None
        ):
            issues.append(
                _issue(
                    "$.policy_digest",
                    "expected policy identity must be canonical sha256",
                )
            )
        elif not issues:
            actual_digest = _sha256_identity(
                canonical_isolation_json_bytes(deepcopy(document))
            )
            if actual_digest != expected_policy_digest:
                issues.append(
                    _issue(
                        "$.policy_digest",
                        "complete policy identity does not match expected digest",
                    )
                )

    grouped: dict[tuple[str, str], set[str]] = {}
    for issue in issues:
        grouped.setdefault((issue.code, issue.path), set()).add(issue.message)
    return tuple(
        sorted(
            (
                ProviderIsolationIssue(
                    code=code,
                    path=path,
                    message="; ".join(sorted(messages)),
                )
                for (code, path), messages in grouped.items()
            ),
            key=lambda issue: (issue.path, issue.message, issue.code),
        )
    )


def load_provider_phase_isolation_policy(
    document: Mapping[str, Any],
    *,
    expected_policy_digest: str | None = None,
) -> ProviderPhaseIsolationPolicy:
    """Validate and load one immutable versioned provider-isolation policy."""

    issues = validate_provider_phase_isolation_policy(
        document,
        expected_policy_digest=expected_policy_digest,
    )
    if issues:
        raise ProviderIsolationPolicyError(issues)

    canonical_json = canonical_isolation_json_bytes(document)
    normalized = json.loads(canonical_json)
    environment = normalized["provider_environment"]
    history = normalized["history_retrieval"]
    workspace = normalized["workspace"]
    process_environment = normalized["process_environment"]
    result_bundle = normalized["result_bundle"]
    shared_network_review = normalized["shared_network_review"]
    return ProviderPhaseIsolationPolicy(
        schema_version=normalized["schema_version"],
        mode=normalized["mode"],
        backend=normalized["backend"],
        session_mode=normalized["session_mode"],
        workspace_access=workspace["access"],
        masked_runtime_roots=tuple(workspace["masked_runtime_roots"]),
        provider_environment=ProviderEnvironmentIdentity(
            root=environment["root"],
            provider_prefix=environment["provider_prefix"],
            digest=environment["digest"],
        ),
        credential_env=tuple(process_environment["credential_env"]),
        result_bundle_max_bytes=result_bundle["max_bytes"],
        shared_network_inventory_path=shared_network_review["inventory_path"],
        shared_network_inventory_digest=shared_network_review["inventory_digest"],
        shared_network_decision=shared_network_review["decision"],
        history_retrieval=HistoryRetrievalPolicy(
            eligibility_requirement=history["eligibility_requirement"],
            provider_api_transport=history["provider_api_transport"],
            remote_git=history["remote_git"],
            browser=history["browser"],
            source_search=history["source_search"],
            repository_fetch=history["repository_fetch"],
        ),
        canonical_json=canonical_json,
        policy_digest=_sha256_identity(canonical_json),
    )


def _canonical_json_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError(f"{path} must be strict UTF-8") from exc
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise TypeError(f"{path} contains a float; isolation JSON forbids floats")
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string object key")
            try:
                key.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError(f"{path} contains a non-UTF-8 object key") from exc
            child_path = _append_json_path(path, key)
            canonical_item = _canonical_json_value(item, child_path)
            if isinstance(canonical_item, str) and _is_filesystem_path_field(key):
                _require_nfc(canonical_item, child_path)
            result[key] = canonical_item
        return result
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [
            _canonical_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(
        f"{path} contains unsupported isolation JSON value {type(value).__name__}"
    )


def _schema_validation_issues(
    errors: Iterable[ValidationError],
) -> list[ProviderIsolationIssue]:
    issues: list[ProviderIsolationIssue] = []
    ordered_errors = sorted(
        errors,
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            str(error.validator),
            error.message,
        ),
    )
    for error in ordered_errors:
        parent_path = _json_path(tuple(error.absolute_path))
        if error.validator == "additionalProperties":
            instance = error.instance
            properties = error.schema.get("properties", {})
            if isinstance(instance, Mapping) and isinstance(properties, Mapping):
                for name in sorted(set(instance) - set(properties)):
                    issues.append(
                        _issue(
                            _append_json_path(parent_path, str(name)),
                            "unknown field is not allowed",
                        )
                    )
                continue
        if error.validator == "required":
            instance = error.instance
            required = error.validator_value
            if isinstance(instance, Mapping) and isinstance(required, list):
                for name in required:
                    if name not in instance:
                        issues.append(
                            _issue(
                                _append_json_path(parent_path, str(name)),
                                "required field is missing",
                            )
                        )
                continue
        issues.append(
            _issue(
                parent_path,
                _stable_schema_message(error),
            )
        )
    return issues


def _stable_schema_message(error: ValidationError) -> str:
    validator = error.validator
    if validator == "const":
        expected = json.dumps(error.validator_value, ensure_ascii=False)
        return f"must equal {expected}"
    if validator == "enum":
        expected = json.dumps(error.validator_value, ensure_ascii=False)
        return f"must be one of {expected}"
    if validator == "type":
        return f"must have JSON type {error.validator_value}"
    if validator == "pattern":
        return "must match the required canonical pattern"
    if validator == "uniqueItems":
        return "array items must be unique"
    if validator == "minimum":
        return f"must be at least {error.validator_value}"
    if validator == "maximum":
        return f"must be at most {error.validator_value}"
    if validator == "minLength":
        return f"must have length at least {error.validator_value}"
    if validator == "maxItems":
        return f"must contain at most {error.validator_value} items"
    return f"violates schema constraint {validator}"


def _semantic_policy_issues(
    document: Mapping[str, Any],
) -> list[ProviderIsolationIssue]:
    issues: list[ProviderIsolationIssue] = []
    provider_environment = document.get("provider_environment")
    if isinstance(provider_environment, Mapping):
        root = provider_environment.get("root")
        issues.extend(
            _absolute_policy_path_issues(root, "$.provider_environment.root")
        )
        prefix = provider_environment.get("provider_prefix")
        prefix_issues = _absolute_policy_path_issues(
            prefix,
            "$.provider_environment.provider_prefix",
        )
        issues.extend(prefix_issues)
        if isinstance(prefix, str) and not prefix_issues:
            if prefix in _RESERVED_PROVIDER_PREFIX_DESTINATIONS or any(
                _is_at_or_below(prefix, root)
                for root in _RUNTIME_PROVIDER_PREFIX_ROOTS
            ):
                issues.append(
                    _issue(
                        "$.provider_environment.provider_prefix",
                        "provider prefix overlaps a runtime overlay, kernel, or reserved destination",
                    )
                )

    process_environment = document.get("process_environment")
    if isinstance(process_environment, Mapping):
        credential_env = process_environment.get("credential_env")
        if isinstance(credential_env, list):
            for index, name in enumerate(credential_env):
                if (
                    isinstance(name, str)
                    and _ENVIRONMENT_NAME_PATTERN.fullmatch(name) is not None
                    and _is_reserved_credential_name(name)
                ):
                    issues.append(
                        _issue(
                            f"$.process_environment.credential_env[{index}]",
                            "credential name is reserved by the isolated runtime",
                        )
                    )

    shared_network_review = document.get("shared_network_review")
    if isinstance(shared_network_review, Mapping):
        issues.extend(
            _absolute_policy_path_issues(
                shared_network_review.get("inventory_path"),
                "$.shared_network_review.inventory_path",
            )
        )

    workspace = document.get("workspace")
    if isinstance(workspace, Mapping):
        masked_runtime_roots = workspace.get("masked_runtime_roots")
        if isinstance(masked_runtime_roots, list):
            for index, value in enumerate(masked_runtime_roots):
                if isinstance(value, str) and not _is_nfc(value):
                    issues.append(
                        _issue(
                            f"$.workspace.masked_runtime_roots[{index}]",
                            "filesystem path must already be Unicode NFC",
                        )
                    )
    return issues


def _absolute_policy_path_issues(
    value: object,
    path: str,
) -> list[ProviderIsolationIssue]:
    if not isinstance(value, str):
        return []
    if not _is_nfc(value):
        return [_issue(path, "filesystem path must already be Unicode NFC")]
    if (
        not value.startswith("/")
        or "\x00" in value
        or value.startswith("//")
        or posixpath.normpath(value) != value
    ):
        return [_issue(path, "filesystem path must be canonical and absolute")]
    return []


def _is_reserved_credential_name(name: str) -> bool:
    return name in _RESERVED_CREDENTIAL_NAMES or any(
        name.startswith(prefix) for prefix in _RESERVED_CREDENTIAL_PREFIXES
    )


def _is_filesystem_path_field(name: str) -> bool:
    return (
        name in {"path", "root", "provider_prefix", "relpath"}
        or name.endswith("_path")
        or name.endswith("_relpath")
    )


def _require_nfc(value: str, path: str) -> None:
    if not _is_nfc(value):
        raise ValueError(f"{path} filesystem path must already be Unicode NFC")


def _require_normalized_manifest_relpath(value: object, path: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{path} must be a string")
    _require_nfc(value, path)
    if (
        not value
        or value.startswith("/")
        or value.startswith("../")
        or value == ".."
        or posixpath.normpath(value) != value
    ):
        raise ValueError(f"{path} must be a normalized POSIX relative path")


def _is_nfc(value: str) -> bool:
    return unicodedata.normalize("NFC", value) == value


def _is_at_or_below(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def _sha256_identity(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _issue(path: str, message: str) -> ProviderIsolationIssue:
    return ProviderIsolationIssue(
        code=POLICY_ERROR_CODE,
        path=path,
        message=message,
    )


def _json_path(parts: tuple[object, ...]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result = _append_json_path(result, str(part))
    return result


def _append_json_path(parent: str, name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return f"{parent}.{name}"
    return f"{parent}[{json.dumps(name, ensure_ascii=False)}]"


__all__ = [
    "HistoryRetrievalPolicy",
    "MAX_RESULT_BUNDLE_BYTES",
    "POLICY_ERROR_CODE",
    "POLICY_SCHEMA_RESOURCE",
    "POLICY_SCHEMA_VERSION",
    "ProviderEnvironmentIdentity",
    "ProviderIsolationIssue",
    "ProviderIsolationPolicyError",
    "ProviderPhaseIsolationPolicy",
    "canonical_isolation_json_bytes",
    "load_provider_isolation_schema",
    "load_provider_phase_isolation_policy",
    "validate_provider_phase_isolation_policy",
]
