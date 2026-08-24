"""Closed OMP conf-tree admission, manifest snapshot, and revalidation (X5).

Reads an `omp_conf_root` with descriptor-relative no-follow traversal, admits
exactly ``config.yml``, ``agent/WATCHDOG.yml`` (optional), and one level of
``agent/agents/*.md``, validates every YAML with a closed SafeLoader, and
returns an immutable content-addressed snapshot whose manifest digests the
admitted bytes.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Hashable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import yaml
from yaml.composer import ComposerError

from .._common.safe_tree import SafeTreeError, read_regular_file, walk_regular_files

SCHEMA_VERSION = "omp_conf_manifest.v1"

BUNDLED_AGENT_NAMES = ("designer", "librarian", "reviewer", "scout", "security-reviewer", "sonic", "task")
ADMITTED_AGENT_TOOLS = frozenset({"read", "grep", "glob", "bash", "edit", "write", "task", "hub"})
ADMITTED_ADVISOR_TOOLS = frozenset({"read", "grep", "glob"})

_CONFIG_KEYS = frozenset({"advisor", "memory", "task"})
_ADVISOR_KEYS = frozenset({"enabled"})
_MEMORY_KEYS = frozenset({"backend"})
_TASK_KEYS = frozenset({"maxConcurrency", "maxRecursionDepth", "disabledAgents"})
_WATCHDOG_KEYS = frozenset({"instructions", "advisors"})
_WATCHDOG_ADVISOR_KEYS = frozenset({"name", "model", "tools", "instructions", "enabled"})
_AGENT_KEYS = frozenset({"name", "description", "model", "tools", "spawns"})
_AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_AGENT_FILE_RE = re.compile(r"^agent/agents/[^/]+\.md$")
_AT_IMPORT_RE = re.compile(r"(^|[ \t])@([./~A-Za-z0-9_-][^\s]*)")


class OmpConfError(Exception):
    """A conf tree failed a closed parse, schema, membership, or identity check."""


@dataclass(frozen=True, slots=True)
class ConfFileRecord:
    """One admitted file: manifest fields plus private no-follow identity."""

    relative_path: str
    size_bytes: int
    sha256: str
    content: bytes
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class ConfSnapshot:
    """Immutable admitted conf tree: ordered records and canonical manifest."""

    files: Mapping[str, ConfFileRecord]
    manifest_bytes: bytes
    manifest_sha256: str


class _ClosedSafeLoader(yaml.SafeLoader):
    """SafeLoader that fails on aliases, anchors, merge keys, and duplicate keys."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.events.AliasEvent):
            raise ComposerError(None, None, "YAML aliases are not allowed")
        event = self.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise ComposerError(None, None, "YAML anchors are not allowed")
        if not isinstance(
            event,
            (yaml.events.ScalarEvent, yaml.events.SequenceStartEvent, yaml.events.MappingStartEvent),
        ):
            raise ComposerError(None, None, f"expected a node, found {event.id}")
        return super().compose_node(parent, index)

    def flatten_mapping(self, node):
        for key_node, _value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise yaml.constructor.ConstructorError(None, None, "YAML merge keys are not allowed")
        return super().flatten_mapping(node)

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, yaml.nodes.MappingNode):
            raise yaml.constructor.ConstructorError(None, None, "expected a mapping node")
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, Hashable):
                raise yaml.constructor.ConstructorError(None, None, f"unhashable key {key!r}")
            if key in mapping:
                raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_yaml_document(payload: bytes, *, source: str):
    """Parse one closed YAML document; unsafe constructs fail as OmpConfError."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OmpConfError(f"{source}: not valid UTF-8") from exc
    try:
        document = yaml.load(text, Loader=_ClosedSafeLoader)
    except yaml.YAMLError as exc:
        raise OmpConfError(f"{source}: {exc}") from exc
    if document is None:
        raise OmpConfError(f"{source}: empty YAML document")
    return document


def _closed_keys(mapping, allowed, context):
    unknown = set(mapping) - allowed
    if unknown:
        raise OmpConfError(f"{context}: unknown key(s) {sorted(unknown)!r}")


def _validate_model(value, context):
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value) or "," in value:
        raise OmpConfError(f"{context}: model must be one non-empty pinned selector")


def _validate_tools(value, allowed, context):
    if not isinstance(value, list) or not all(isinstance(tool, str) for tool in value):
        raise OmpConfError(f"{context}: tools must be a list of strings")
    if len(set(value)) != len(value):
        raise OmpConfError(f"{context}: duplicate tools")
    if not set(value) <= allowed:
        raise OmpConfError(f"{context}: tool outside the admitted set")


def _validate_config(document, source):
    if not isinstance(document, dict) or set(document) != _CONFIG_KEYS:
        raise OmpConfError(f"{source}: must be exactly {{advisor, memory, task}}")
    advisor = document["advisor"]
    if not isinstance(advisor, dict) or set(advisor) != _ADVISOR_KEYS:
        raise OmpConfError(f"{source}: advisor must be exactly {{enabled}}")
    enabled = advisor["enabled"]
    if not isinstance(enabled, bool):
        raise OmpConfError(f"{source}: advisor.enabled must be a literal boolean")
    memory = document["memory"]
    if not isinstance(memory, dict) or set(memory) != _MEMORY_KEYS:
        raise OmpConfError(f"{source}: memory must be exactly {{backend}}")
    if not isinstance(memory["backend"], str) or memory["backend"] != "off":
        raise OmpConfError(f"{source}: memory.backend must be the literal string \"off\"")
    task = document["task"]
    if not isinstance(task, dict) or set(task) != _TASK_KEYS:
        raise OmpConfError(
            f"{source}: task must be exactly {{maxConcurrency, maxRecursionDepth, disabledAgents}}"
        )
    concurrency = task["maxConcurrency"]
    if not isinstance(concurrency, int) or isinstance(concurrency, bool) or not 1 <= concurrency <= 32:
        raise OmpConfError(f"{source}: task.maxConcurrency must be an integer 1..32")
    depth = task["maxRecursionDepth"]
    if not isinstance(depth, int) or isinstance(depth, bool) or not 0 <= depth <= 2:
        raise OmpConfError(f"{source}: task.maxRecursionDepth must be an integer 0..2")
    if task["disabledAgents"] != list(BUNDLED_AGENT_NAMES):
        raise OmpConfError(f"{source}: task.disabledAgents must equal the pinned bundled list")
    return enabled


def _inside_inline_code(line: str, position: int) -> bool:
    """True when `position` falls in an unclosed inline-code span (OMP parity scan)."""
    in_span = False
    index = 0
    while index < position:
        if line[index] == "`":
            in_span = not in_span
            while index < position and line[index] == "`":
                index += 1
        else:
            index += 1
    return in_span


def _match_fence(line: str):
    """Return (char, run) when the first non-whitespace run is >=3 marks, else None (OMP matchFence)."""
    index = 0
    while index < len(line) and line[index] in " \t":
        index += 1
    if index >= len(line) or line[index] not in "`~":
        return None
    char = line[index]
    run = 0
    while index + run < len(line) and line[index + run] == char:
        run += 1
    if run < 3:
        return None
    return char, run


def _has_at_import_candidate(text: str) -> bool:
    """True when a line holds an @-candidate outside fenced or inline code."""
    in_code = False
    fence_char = ""
    fence_run = 0
    for line in text.split("\n"):
        fence = _match_fence(line)
        if fence is not None:
            if not in_code:
                in_code = True
                fence_char, fence_run = fence
            elif fence[0] == fence_char and fence[1] >= fence_run:
                in_code = False
                fence_char = ""
                fence_run = 0
            continue
        if in_code or "@" not in line:
            continue
        for match in _AT_IMPORT_RE.finditer(line):
            at = match.start(1) + len(match.group(1))
            if not _inside_inline_code(line, at):
                return True
    return False


def _validate_watchdog(document, source):
    if not isinstance(document, dict):
        raise OmpConfError(f"{source}: must be a mapping")
    _closed_keys(document, _WATCHDOG_KEYS, source)
    if "instructions" in document:
        instructions = document["instructions"]
        if not isinstance(instructions, str) or not instructions:
            raise OmpConfError(f"{source}: instructions must be a non-empty string")
        if _has_at_import_candidate(instructions):
            raise OmpConfError(f"{source}: @-import candidate in instructions")
    advisors = document.get("advisors")
    if not isinstance(advisors, list) or not advisors:
        raise OmpConfError(f"{source}: advisors must be a non-empty list")
    names = set()
    for advisor in advisors:
        if not isinstance(advisor, dict) or set(advisor) != _WATCHDOG_ADVISOR_KEYS:
            raise OmpConfError(
                f"{source}: each advisor must be exactly {{name, model, tools, instructions, enabled}}"
            )
        name = advisor["name"]
        if not isinstance(name, str) or not name:
            raise OmpConfError(f"{source}: advisor name must be a non-empty string")
        if name in names:
            raise OmpConfError(f"{source}: duplicate advisor name {name!r}")
        names.add(name)
        _validate_model(advisor["model"], f"{source}: advisor model")
        _validate_tools(advisor["tools"], ADMITTED_ADVISOR_TOOLS, f"{source}: advisor tools")
        instructions = advisor["instructions"]
        if not isinstance(instructions, str) or not instructions:
            raise OmpConfError(f"{source}: advisor instructions must be a non-empty string")
        if _has_at_import_candidate(instructions):
            raise OmpConfError(f"{source}: @-import candidate in advisor instructions")
        if advisor["enabled"] is not True:
            raise OmpConfError(f"{source}: advisor enabled must be the literal true")


def _split_frontmatter(text, source):
    view = text.replace("\r\n", "\n").replace("\r", "\n")  # pinned parseFrontmatter normalizes CRLF/CR
    if not view.startswith("---\n"):
        raise OmpConfError(f"{source}: frontmatter must open the file")
    lines = view.split("\n")
    close = None
    for index in range(1, len(lines)):
        if lines[index] == "---":
            close = index
            break
    if close is None:
        raise OmpConfError(f"{source}: unclosed frontmatter")
    body = "\n".join(lines[close + 1 :])
    if not body.strip():
        raise OmpConfError(f"{source}: instruction body must be non-empty")
    frontmatter = "\n".join(lines[1:close]).encode("utf-8")
    document = load_yaml_document(frontmatter, source=source)
    if not isinstance(document, dict):
        raise OmpConfError(f"{source}: frontmatter must be a mapping")
    return document, body


def _validate_agent_file(content, source):
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OmpConfError(f"{source}: not valid UTF-8") from exc
    frontmatter, body = _split_frontmatter(text, source)
    _closed_keys(frontmatter, _AGENT_KEYS, source)
    if not {"name", "description"} <= set(frontmatter):
        raise OmpConfError(f"{source}: frontmatter requires name and description")
    name = frontmatter["name"]
    if not isinstance(name, str) or _AGENT_NAME_RE.fullmatch(name) is None:
        raise OmpConfError(f"{source}: invalid agent name {name!r}")
    if name.startswith("__") or name in BUNDLED_AGENT_NAMES:
        raise OmpConfError(f"{source}: reserved agent name {name!r}")
    description = frontmatter["description"]
    if not isinstance(description, str) or not description:
        raise OmpConfError(f"{source}: description must be a non-empty string")
    if "model" in frontmatter:
        _validate_model(frontmatter["model"], f"{source}: model")
    if "tools" in frontmatter:
        _validate_tools(frontmatter["tools"], ADMITTED_AGENT_TOOLS, f"{source}: tools")
    spawns = frontmatter.get("spawns", [])
    if "task" in frontmatter.get("tools", []) and (not isinstance(spawns, list) or not spawns):
        raise OmpConfError(f"{source}: tools include task; spawns must be a non-empty list (empty normalizes to wildcard)")
    if not isinstance(spawns, list) or not all(isinstance(spawn, str) for spawn in spawns):
        raise OmpConfError(f"{source}: spawns must be a list of strings")
    if len(set(spawns)) != len(spawns):
        raise OmpConfError(f"{source}: duplicate spawns")
    if _has_at_import_candidate(body):
        raise OmpConfError(f"{source}: @-import candidate in body")
    return name, description, spawns


def _check_membership(paths):
    if "config.yml" not in paths:
        raise OmpConfError("conf tree is missing config.yml")
    for path in paths:
        if path in ("config.yml", "agent/WATCHDOG.yml") or _AGENT_FILE_RE.fullmatch(path):
            continue
        raise OmpConfError(f"unadmitted conf tree path: {path!r}")


def _reject_executable(row) -> None:
    """Reject a source file carrying any executable bit (X5 319-320)."""
    if row.mode & 0o111:
        raise OmpConfError(f"conf tree source must not be executable: {row.relative_path!r}")


def admit_conf_tree(root_fd: int) -> ConfSnapshot:
    """Admit one conf tree through the closed parser and snapshot its bytes."""
    try:
        rows = list(walk_regular_files(root_fd))
        content = {
            row.relative_path: read_regular_file(root_fd, row.relative_path, expected=row)
            for row in rows
        }
    except SafeTreeError as exc:
        raise OmpConfError(str(exc)) from exc
    _check_membership(content)
    config = load_yaml_document(content["config.yml"], source="config.yml")
    advisor_enabled = _validate_config(config, "config.yml")
    watchdog_present = "agent/WATCHDOG.yml" in content
    if watchdog_present:
        watchdog = load_yaml_document(content["agent/WATCHDOG.yml"], source="agent/WATCHDOG.yml")
        _validate_watchdog(watchdog, "agent/WATCHDOG.yml")
    if advisor_enabled is not watchdog_present:
        raise OmpConfError("advisor.enabled must match the presence of agent/WATCHDOG.yml")
    agents = {}
    for path in sorted(content):
        if not _AGENT_FILE_RE.fullmatch(path):
            continue
        name, description, spawns = _validate_agent_file(content[path], path)
        if name in agents:
            raise OmpConfError(f"duplicate agent name {name!r}")
        agents[name] = (path, description, spawns)
    descriptions = {entry[1] for entry in agents.values()}
    if len(descriptions) != len(agents):
        raise OmpConfError("agent descriptions must be unique")
    for name, (_path, _description, spawns) in agents.items():
        undeclared = set(spawns) - set(agents)
        if undeclared:
            raise OmpConfError(f"agent {name!r} spawns undeclared agent(s) {sorted(undeclared)!r}")
    ordered = sorted(content, key=lambda path: path.encode("utf-8"))
    records = {}
    for path in ordered:
        data = content[path]
        row = next(row for row in rows if row.relative_path == path)
        _reject_executable(row)
        records[path] = ConfFileRecord(
            path,
            len(data),
            hashlib.sha256(data).hexdigest(),
            data,
            row.device,
            row.inode,
        )
    file_rows = [
        {"mode": "0644", "path": path, "sha256": records[path].sha256, "size": records[path].size_bytes}
        for path in ordered
    ]
    manifest_bytes = json.dumps(
        {"schema_version": SCHEMA_VERSION, "files": file_rows},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return ConfSnapshot(
        files=MappingProxyType(records),
        manifest_bytes=manifest_bytes,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def revalidate_conf_tree(root_fd: int, snapshot: ConfSnapshot) -> None:
    """Re-check the tree against a snapshot; membership/identity/content drift fails."""
    try:
        rows = list(walk_regular_files(root_fd))
    except SafeTreeError as exc:
        raise OmpConfError(str(exc)) from exc
    if {row.relative_path for row in rows} != set(snapshot.files):
        raise OmpConfError("conf tree membership changed")
    for row in rows:
        record = snapshot.files[row.relative_path]
        _reject_executable(row)
        if (row.device, row.inode) != (record.device, record.inode):
            raise OmpConfError(f"conf tree entry changed identity: {row.relative_path!r}")
        try:
            data = read_regular_file(root_fd, row.relative_path, expected=row)
        except SafeTreeError as exc:
            raise OmpConfError(str(exc)) from exc
        if hashlib.sha256(data).hexdigest() != record.sha256:
            raise OmpConfError(f"conf tree entry changed content: {row.relative_path!r}")
