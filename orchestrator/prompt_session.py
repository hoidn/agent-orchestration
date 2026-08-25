"""Closed Task 9 session-link, exact-index, and prompt-import domain."""
from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from orchestrator.providers.omp_session import (
    OmpSessionError,
    ParsedJournal,
    path_to_root,
    session_leaf,
    validate_session_graph,
)
from orchestrator.providers.omp_protocol import _is_rfc3339, loads_strict
from orchestrator.providers.omp_launch_contract import (
    POSITIVE_ENV_NAMES,
    build_interactive_argv,
    valid_fresh_child_cwd,
    valid_private_binary_path,
)
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
_LINK_KEYS = frozenset({
    "schema_version", "run_id", "step_id", "visit_key",
    "workflow_workspace", "scaffold_relpath", "paths", "session", "digests",
    "provider", "scaffold_identity", "launch", "confinement",
})
_PATH_KEYS = frozenset({"state", "metadata", "live", "snapshot", "conf"})
_SESSION_KEYS = frozenset({"id", "primary_basename"})
_DIGEST_KEYS = frozenset({
    "live_manifest_sha256", "snapshot_manifest_sha256",
    "conf_manifest_sha256", "scaffold_manifest_sha256",
    "authored_prompt_sha256", "composed_prompt_sha256", "source_sha256",
    "semantic_contract_sha256",
})
_PROVIDER_KEYS = frozenset({"name", "model", "lane"})
_LAUNCH_KEYS = frozenset({"argv", "env_names"})
_CONFINEMENT_KEYS = frozenset({"schema_version", "landlock_abi", "policy_sha256"})
_PUBLIC_PROVIDERS = frozenset({"omp", "omp_no_tools", "omp_unrestricted_workspace", "omp_conf"})
_LANES = {
    "omp": "ambient",
    "omp_no_tools": "no-tools",
    "omp_unrestricted_workspace": "ambient-unrestricted",
    "omp_conf": "conf",
}
_HEX = re.compile(r"^[0-9a-f]{64}$")


class PromptSessionError(Exception):
    """A stable, non-secret Task 9 session bridge failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class SessionLink:
    """Validated closed ``session_link.v1`` record."""

    document: Mapping[str, Any]
    raw_bytes: bytes

    @property
    def run_id(self) -> str:
        return self.document["run_id"]

    @property
    def visit_key(self) -> str:
        return self.document["visit_key"]

    @property
    def session_id(self) -> str:
        return self.document["session"]["id"]

    @property
    def primary_basename(self) -> str:
        return self.document["session"]["primary_basename"]


@dataclass(frozen=True, slots=True)
class ResolvedPrimary:
    """One exact unblocked active primary journal and its source link."""

    run_id: str
    visit_key: str
    session_id: str
    primary_basename: str
    link: SessionLink
    run_root: Path
    run_identity: tuple[int, int]
    journal_bytes: bytes


def _invalid(detail: str) -> PromptSessionError:
    return PromptSessionError("session_link_invalid", detail)


def _closed(value: object, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise _invalid(f"{label} must contain exactly {sorted(keys)!r}")
    return value


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid(f"{label} must be a non-empty string")
    return value


def _digest(value: object, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX.fullmatch(value) is None:
        raise _invalid(f"{label} must be 64 lowercase hex")
    return value


def _relpath(value: object, label: str) -> str:
    text = _nonempty(value, label)
    try:
        path = PurePosixPath(text)
    except (TypeError, ValueError) as exc:
        raise _invalid(f"{label} is invalid") from exc
    if path.is_absolute() or str(path) != text or any(part in ("", ".", "..") for part in path.parts):
        raise _invalid(f"{label} must be a normalized relative POSIX path")
    return text


def _basename(value: object, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    text = _nonempty(value, label)
    if text in (".", "..") or "/" in text or "\\" in text or "\x00" in text:
        raise _invalid(f"{label} must be one basename component")
    return text


def parse_session_link_bytes(data: bytes) -> SessionLink:
    """Parse the exact closed X8 link shape without touching its paths."""
    if not isinstance(data, bytes):
        raise _invalid("link must be bytes")
    try:
        document = loads_strict(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _invalid("link is not one strict JSON object") from exc
    link = _closed(document, _LINK_KEYS, "link")
    if link["schema_version"] != "session_link.v1":
        raise _invalid("schema_version is unsupported")
    for field in ("run_id", "step_id", "scaffold_identity"):
        _nonempty(link[field], field)
    visit_key = _basename(link["visit_key"], "visit_key")
    _digest(link["scaffold_identity"], "scaffold_identity")
    workspace = _nonempty(link["workflow_workspace"], "workflow_workspace")
    workspace_path = PurePosixPath(workspace)
    if (
        not workspace_path.is_absolute()
        or str(workspace_path) != workspace
        or any(part in (".", "..") for part in workspace_path.parts)
        or "\\" in workspace
        or "\x00" in workspace
    ):
        raise _invalid("workflow_workspace must be normalized absolute POSIX")
    _relpath(link["scaffold_relpath"], "scaffold_relpath")

    paths = _closed(link["paths"], _PATH_KEYS, "paths")
    for field in ("state", "metadata", "live", "snapshot"):
        _relpath(paths[field], f"paths.{field}")
    if paths["conf"] is not None:
        _relpath(paths["conf"], "paths.conf")
    fixed_paths = {
        "state": "state.json",
        "metadata": f"provider_sessions/{visit_key}.json",
        "live": f"provider_sessions/{visit_key}",
        "snapshot": f"provider_sessions/{visit_key}.snapshot",
    }
    if any(paths[field] != expected for field, expected in fixed_paths.items()):
        raise _invalid("paths do not match visit_key")

    session = _closed(link["session"], _SESSION_KEYS, "session")
    _nonempty(session["id"], "session.id")
    basename = _basename(session["primary_basename"], "session.primary_basename")
    if not basename.endswith(".jsonl"):
        raise _invalid("session.primary_basename must end .jsonl")

    digests = _closed(link["digests"], _DIGEST_KEYS, "digests")
    for field in _DIGEST_KEYS - {"conf_manifest_sha256"}:
        _digest(digests[field], f"digests.{field}")
    _digest(digests["conf_manifest_sha256"], "digests.conf_manifest_sha256", nullable=True)
    if (paths["conf"] is None) != (digests["conf_manifest_sha256"] is None):
        raise _invalid("conf path and digest nullability disagree")

    provider = _closed(link["provider"], _PROVIDER_KEYS, "provider")
    name = provider["name"]
    if name not in _PUBLIC_PROVIDERS or provider["lane"] != _LANES.get(name):
        raise _invalid("provider name/lane is unsupported")
    _nonempty(provider["model"], "provider.model")
    expected_conf = (
        f"provider_sessions/{visit_key}.conf"
        if provider["lane"] in ("no-tools", "conf")
        else None
    )
    if paths["conf"] != expected_conf:
        raise _invalid("conf path does not match visit_key/lane")

    launch = _closed(link["launch"], _LAUNCH_KEYS, "launch")
    if not isinstance(launch["argv"], list) or not launch["argv"] or not all(
        isinstance(item, str) and item for item in launch["argv"]
    ):
        raise _invalid("launch.argv must be a non-empty string array")
    env_names = launch["env_names"]
    if not isinstance(env_names, list) or not all(isinstance(item, str) and item for item in env_names) \
            or env_names != sorted(set(env_names)):
        raise _invalid("launch.env_names must be sorted unique non-empty strings")

    confinement = link["confinement"]
    if provider["lane"] in ("ambient", "ambient-unrestricted"):
        if confinement is not None:
            raise _invalid("ambient confinement must be null")
    else:
        conf = _closed(confinement, _CONFINEMENT_KEYS, "confinement")
        if conf["schema_version"] != "omp_write_confinement.v1" \
                or type(conf["landlock_abi"]) is not int or conf["landlock_abi"] < 3:
            raise _invalid("confinement schema/ABI is invalid")
        _digest(conf["policy_sha256"], "confinement.policy_sha256")
    return SessionLink(document=link, raw_bytes=data)


def extract_prompt_bytes(journal: ParsedJournal) -> bytes:
    """Extract the first pre-assistant user prompt on the validated active branch."""
    try:
        validate_session_graph(journal.entries)
        branch = path_to_root(journal.entries, session_leaf(journal.entries).id)
    except OmpSessionError as exc:
        raise PromptSessionError("prompt_import_invalid", "journal graph is invalid") from exc
    if any(entry.type == "session_init" and "agent" in entry.payload for entry in branch):
        raise PromptSessionError("prompt_import_invalid", "active branch is an agent session")
    for entry in branch:
        if entry.type != "message":
            continue
        message = entry.payload["message"]
        if message["role"] == "assistant":
            break
        if message["role"] != "user":
            continue
        content = message["content"]
        if isinstance(content, str):
            if content:
                return content.encode("utf-8")
            break
        if not content:
            break
        texts: list[str] = []
        for block in content:
            if (
                set(block) not in ({"type", "text"}, {"type", "text", "textSignature"})
                or block.get("type") != "text"
                or not isinstance(block.get("text"), str)
                or (
                    "textSignature" in block
                    and not isinstance(block["textSignature"], str)
                )
            ):
                raise PromptSessionError(
                    "prompt_import_invalid", "user prompt is not closed text content"
                )
            texts.append(block["text"])
        if any(texts):
            return "\n".join(texts).encode("utf-8")
        break
    raise PromptSessionError(
        "prompt_import_invalid",
        "active branch has no pre-assistant user prompt",
    )


_CONTINUATION_KEYS = frozenset({
    "schema_version", "sequence", "previous_sha256", "status", "mode",
    "source", "result", "started_at", "ended_at", "child_exit_code", "failure",
    "binary", "conf_manifest_sha256", "launch", "confinement",
    "pre_live_manifest_sha256", "post_live_manifest_sha256",
})
_ENDPOINT_KEYS = frozenset({"session_id", "primary_basename", "journal_sha256"})
_BINARY_KEYS = frozenset({"platform", "arch", "version", "sha256"})


@dataclass(frozen=True, slots=True)
class ContinuationState:
    session_id: str
    primary_basename: str
    journal_sha256: str | None
    live_manifest_sha256: str
    blocked: bool


def _parse_continuation(data: bytes, sequence: int, previous: bytes) -> dict[str, Any]:
    try:
        value = loads_strict(data.decode("utf-8"))
        record = _closed(value, _CONTINUATION_KEYS, "continuation")
        if record["schema_version"] != "session_continuation.v1" \
                or type(record["sequence"]) is not int or record["sequence"] != sequence \
                or record["previous_sha256"] != hashlib.sha256(previous).hexdigest():
            raise _invalid("continuation schema, sequence, or previous digest is invalid")
        if record["status"] not in ("success", "failed") or record["mode"] not in ("fork", "in_place"):
            raise _invalid("continuation status or mode is invalid")
        source = _closed(record["source"], _ENDPOINT_KEYS, "continuation.source")
        result = _closed(record["result"], _ENDPOINT_KEYS, "continuation.result")
        _nonempty(source["session_id"], "continuation.source.session_id")
        source_name = _basename(source["primary_basename"], "continuation.source.primary_basename")
        if not source_name.endswith(".jsonl"):
            raise _invalid("continuation source basename must end .jsonl")
        _digest(source["journal_sha256"], "continuation.source.journal_sha256")
        for field in ("started_at", "ended_at"):
            if not _is_rfc3339(_nonempty(record[field], f"continuation.{field}")):
                raise _invalid(f"continuation.{field} must be RFC3339")
        binary = _closed(record["binary"], _BINARY_KEYS, "continuation.binary")
        if binary["platform"] != "linux" or binary["arch"] != "x86_64" or binary["version"] != "17.3.4":
            raise _invalid("continuation binary is unsupported")
        _digest(binary["sha256"], "continuation.binary.sha256")
        _digest(record["conf_manifest_sha256"], "continuation.conf_manifest_sha256", nullable=True)
        launch = _closed(record["launch"], _LAUNCH_KEYS, "continuation.launch")
        if not isinstance(launch["argv"], list) or not launch["argv"] \
                or not all(isinstance(item, str) and item for item in launch["argv"]):
            raise _invalid("continuation launch argv is invalid")
        if not isinstance(launch["env_names"], list) or launch["env_names"] != sorted(set(launch["env_names"])) \
                or not all(isinstance(item, str) and item for item in launch["env_names"]):
            raise _invalid("continuation launch env_names is invalid")
        _digest(record["pre_live_manifest_sha256"], "continuation.pre_live_manifest_sha256")
        _digest(record["post_live_manifest_sha256"], "continuation.post_live_manifest_sha256", nullable=True)
        if type(record["child_exit_code"]) is not int:
            raise _invalid("continuation child_exit_code must be an integer")
        if record["status"] == "success":
            if record["child_exit_code"] != 0 or record["failure"] is not None \
                    or record["post_live_manifest_sha256"] is None:
                raise _invalid("successful continuation has inconsistent outcome")
            _nonempty(result["session_id"], "continuation.result.session_id")
            result_name = _basename(result["primary_basename"], "continuation.result.primary_basename")
            if not result_name.endswith(".jsonl"):
                raise _invalid("continuation result basename must end .jsonl")
            _digest(result["journal_sha256"], "continuation.result.journal_sha256")
        elif not isinstance(record["failure"], str) or not record["failure"] \
                or any(result[field] is not None for field in _ENDPOINT_KEYS):
            raise _invalid("failed continuation has inconsistent outcome")
        return record
    except (UnicodeDecodeError, ValueError, PromptSessionError) as exc:
        raise PromptSessionError("session_continuation_invalid", str(exc)) from exc


def _validate_continuation_launch(
    record: dict[str, Any],
    link: SessionLink,
    active: ContinuationState,
    run_root: Path,
) -> None:
    expected_binary = {
        "platform": OMP_BINARY_PIN.platform,
        "arch": OMP_BINARY_PIN.arch,
        "version": OMP_BINARY_PIN.version,
        "sha256": OMP_BINARY_PIN.executable_sha256,
    }
    launch = record["launch"]
    argv = launch["argv"]
    provider = link.document["provider"]["name"]
    workspace = link.document["workflow_workspace"]
    if (
        record["binary"] != expected_binary
        or launch["env_names"] != list(POSITIVE_ENV_NAMES)
        or not valid_private_binary_path(argv[0], OMP_BINARY_PIN.executable_sha256)
    ):
        raise PromptSessionError(
            "session_continuation_invalid", "continuation launch authority is invalid"
        )
    empty_cwd = None
    if provider in ("omp_no_tools", "omp_conf"):
        try:
            empty_cwd = argv[argv.index("--cwd") + 1]
        except (ValueError, IndexError):
            raise PromptSessionError(
                "session_continuation_invalid", "profile continuation cwd is missing"
            ) from None
        if not valid_fresh_child_cwd(provider, empty_cwd, workspace):
            raise PromptSessionError(
                "session_continuation_invalid", "profile continuation cwd is invalid"
            )
    try:
        expected = build_interactive_argv(
            provider,
            link.document["provider"]["model"],
            private_binary=argv[0],
            live_dir=str(run_root / link.document["paths"]["live"]),
            mode=record["mode"],
            source_session_id=active.session_id,
            workspace=workspace,
            empty_cwd=empty_cwd,
        )
    except ValueError as exc:
        raise PromptSessionError("session_continuation_invalid", str(exc)) from exc
    if tuple(argv) != expected:
        raise PromptSessionError(
            "session_continuation_invalid", "continuation argv disagrees with link"
        )


def validate_continuation_chain(
    link_bytes: bytes,
    records: list[bytes],
    *,
    initial_journal_sha256: str | None = None,
    run_root: Path | None = None,
) -> ContinuationState:
    """Validate one contiguous append-only chain and return its active primary."""
    link = parse_session_link_bytes(link_bytes)
    if records and _HEX.fullmatch(initial_journal_sha256 or "") is None:
        raise PromptSessionError(
            "session_continuation_invalid", "initial journal digest is required"
        )
    active = ContinuationState(
        link.session_id,
        link.primary_basename,
        initial_journal_sha256,
        link.document["digests"]["live_manifest_sha256"],
        False,
    )
    previous = link_bytes
    for sequence, data in enumerate(records, 1):
        record = _parse_continuation(data, sequence, previous)
        if active.blocked:
            raise PromptSessionError(
                "session_continuation_invalid", "failure is terminal"
            )
        if run_root is None:
            raise PromptSessionError(
                "session_continuation_invalid", "continuation run root is required"
            )
        _validate_continuation_launch(record, link, active, run_root)
        source = record["source"]
        if (
            source["session_id"] != active.session_id
            or source["primary_basename"] != active.primary_basename
            or source["journal_sha256"] != active.journal_sha256
            or record["pre_live_manifest_sha256"] != active.live_manifest_sha256
        ):
            raise PromptSessionError(
                "session_continuation_invalid",
                "source disagrees with active primary",
            )
        if record["conf_manifest_sha256"] != link.document["digests"]["conf_manifest_sha256"] \
                or record["confinement"] != link.document["confinement"]:
            raise PromptSessionError("session_continuation_invalid", "continuation policy disagrees with link")
        if record["status"] == "failed":
            active = ContinuationState(
                active.session_id, active.primary_basename, active.journal_sha256,
                record["post_live_manifest_sha256"] or active.live_manifest_sha256, True,
            )
        else:
            result = record["result"]
            if record["mode"] == "fork" and (
                result["session_id"] == active.session_id
                or result["primary_basename"] == active.primary_basename
            ):
                raise PromptSessionError("session_continuation_invalid", "fork did not create a new primary")
            if record["mode"] == "in_place" and (
                result["session_id"] != active.session_id
                or result["primary_basename"] != active.primary_basename
            ):
                raise PromptSessionError("session_continuation_invalid", "in-place changed primary identity")
            active = ContinuationState(
                result["session_id"], result["primary_basename"], result["journal_sha256"],
                record["post_live_manifest_sha256"], False,
            )
        previous = data
    return active


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value or value in (".", "..") \
            or "/" in value or "\\" in value or "\x00" in value:
        raise PromptSessionError("prompt_session_not_found")
    return value

from orchestrator.prompt_session_publish import (
    publish_prompt_run_link,
    with_private_execution_authority,
)
from orchestrator.prompt_session_lookup import resolve_prompt_session
