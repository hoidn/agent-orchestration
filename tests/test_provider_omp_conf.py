"""RED behavioral tests for orchestrator.providers.omp_conf (Task 4).

Covers (brief 4.2 + X5): closed SafeLoader (dup keys, aliases, anchors,
merge keys, custom tags, multi-doc, empty all fail); closed config.yml /
WATCHDOG.yml / agent frontmatter schemas; @-import lexing; tree membership;
safe-tree rejections; canonical immutable manifest; drift revalidation.
"""
import contextlib
import hashlib
import json
import os
import tempfile
from types import SimpleNamespace

import pytest

from orchestrator.providers.omp_conf import (
    ADMITTED_ADVISOR_TOOLS,
    ADMITTED_AGENT_TOOLS,
    BUNDLED_AGENT_NAMES,
    ConfFileRecord,
    ConfSnapshot,
    OmpConfError,
    admit_conf_tree,
    load_yaml_document,
    materialize_conf_at_discovery_path,
    revalidate_conf_tree,
    revalidate_materialized_conf,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "omp", "conf")

NEUTRAL = ("designer", "librarian", "reviewer", "scout", "security-reviewer", "sonic", "task")


@contextlib.contextmanager
def _root(path):
    """Open one directory descriptor for a tree and always close it."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        yield fd
    finally:
        os.close(fd)


def _tree(tmp_path, files):
    """Write {relative_path: text} under a fresh tmp_path/tree-<n> dir; return its path."""
    root = tempfile.mkdtemp(dir=str(tmp_path))
    for relative, text in files.items():
        target = os.path.join(root, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)
    return root


def _config(*, enabled=False, backend='"off"', concurrency=4, recursion=1, disabled=NEUTRAL, extra=""):
    lines = [
        "advisor:",
        f"  enabled: {str(enabled).lower()}",
        "memory:",
        f"  backend: {backend}",
        "task:",
        f"  maxConcurrency: {concurrency}",
        f"  maxRecursionDepth: {recursion}",
        "  disabledAgents:",
    ]
    lines += [f"    - {name}" for name in disabled]
    if extra:
        lines.append(extra)
    return "\n".join(lines) + "\n"


def _agent_md(name="alpha", description="Worker agent", body="Do the work.\n", **frontmatter):
    keys = [("name", name), ("description", description)]
    keys += sorted(frontmatter.items())
    lines = ["---"]
    lines += [f"{key}: {value}" for key, value in keys]
    lines += ["---", ""]
    return "\n".join(lines) + body


def _watchdog(advisors=None, instructions='"Watch the primary."'):
    if advisors is None:
        advisors = ['  - name: code-reviewer\n    model: "x-ai/grok-code-fast:high"\n    tools: [read, grep, glob]\n    instructions: "Review each primary turn."\n    enabled: true']
    return "instructions: " + instructions + "\nadvisors:\n" + "\n".join(advisors) + "\n"


def _reject(tmp_path, files):
    """Assert admit_conf_tree rejects files written under tmp_path/tree."""
    with _root(_tree(tmp_path, files)) as fd:
        with pytest.raises(OmpConfError):
            admit_conf_tree(fd)


# ---------------------------------------------------------------- loader


def test_loader_admits_single_closed_document():
    doc = load_yaml_document(_config().encode("utf-8"), source="config.yml")
    assert doc["task"]["maxConcurrency"] == 4
    assert doc["memory"]["backend"] == "off"
    assert doc["advisor"]["enabled"] is False


@pytest.mark.parametrize(
    "fixture_name",
    ["dup-keys-config.yml", "alias-config.yml", "merge-config.yml", "tag-config.yml"],
)
def test_loader_rejects_unsafe_yaml_constructs(fixture_name):
    with open(os.path.join(FIXTURES, "invalid", fixture_name), "rb") as handle:
        payload = handle.read()
    with pytest.raises(OmpConfError):
        load_yaml_document(payload, source=fixture_name)


def test_loader_rejects_empty_or_multiple_documents():
    for payload in (b"", b"---\n", (_config() + "---\nother: 1\n").encode("utf-8")):
        with pytest.raises(OmpConfError):
            load_yaml_document(payload, source="config.yml")


# ---------------------------------------------------------- config domain


def test_admits_neutral_fixture():
    with _root(os.path.join(FIXTURES, "neutral")) as fd:
        snapshot = admit_conf_tree(fd)
    assert tuple(snapshot.files) == ("config.yml",)
    assert len(snapshot.manifest_sha256) == 64
    record = snapshot.files["config.yml"]
    assert isinstance(record, ConfFileRecord)
    assert record.relative_path == "config.yml"
    assert record.content.startswith(b"advisor:")


def test_admits_config_boundaries(tmp_path):
    for config_text in (
        _config(concurrency=1, recursion=0),
        _config(concurrency=32, recursion=2),
    ):
        with _root(_tree(tmp_path, {"config.yml": config_text})) as fd:
            admit_conf_tree(fd)


def test_admits_exact_noninteractive_task_approval(tmp_path):
    config = _config(extra="tools:\n  approval:\n    task: allow")
    files = {"config.yml": config, "agent/agents/a.md": _agent_md()}
    with _root(_tree(tmp_path, files)) as fd:
        admit_conf_tree(fd)


@pytest.mark.parametrize("policy", ["deny", "prompt", "allow\n    bash: allow"])
def test_rejects_wider_task_approval_policy(tmp_path, policy):
    config = _config(extra=f"tools:\n  approval:\n    task: {policy}")
    files = {"config.yml": config, "agent/agents/a.md": _agent_md()}
    _reject(tmp_path, files)


@pytest.mark.parametrize(
    "config_text",
    [
        _config(enabled=1),                            # non-literal bool
        _config(backend="local"),                      # closed backend
        _config(backend="off"),                        # unquoted off parses as bool
        _config(concurrency=0),
        _config(concurrency=33),
        _config(concurrency='"4"'),
        _config(concurrency="true"),
        _config(recursion=-1),
        _config(recursion=3),
        _config(disabled=NEUTRAL[:-1]),                # missing a required agent
        _config(disabled=NEUTRAL + ("task",)),         # duplicate entry
        _config(disabled=("builder",) + NEUTRAL[1:]),  # renamed entry
        _config(disabled=tuple(reversed(NEUTRAL))),    # unsorted order
        _config(extra="worktree:\n  base: /tmp/wt"),   # unknown top-level key
        _config(extra="task:\n  maxRecursionDepth: 1"),  # duplicate task key (loader rejects)
        "memory:\n  backend: \"off\"\n",               # missing advisor and task
        "advisor:\n  enabled: false\nmemory:\n  backend: \"off\"\ntask:\n  maxConcurrency: 4\n  maxRecursionDepth: 1\n",  # missing disabledAgents
        _config().replace("advisor:\n  enabled: false", "advisor:\n  enabled: false\n  syncBacklog: 1"),  # unknown nested key
        "- not\n- a\n- mapping\n",                     # config.yml must be a mapping
    ],
)
def test_config_domain_rejections(tmp_path, config_text):
    _reject(tmp_path, {"config.yml": config_text})


# ---------------------------------------------------------------- watchdog


def test_admits_advised_fixture():
    with _root(os.path.join(FIXTURES, "advised")) as fd:
        snapshot = admit_conf_tree(fd)
    assert tuple(snapshot.files) == ("agent/WATCHDOG.yml", "config.yml")


def test_watchdog_enabled_present_must_be_literal_true(tmp_path):
    for enabled in ("enabled: false", 'enabled: "true"'):
        advisor = '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    tools: [read]\n    instructions: "i"\n    ' + enabled
        _reject(tmp_path, {"config.yml": _config(enabled=True), "agent/WATCHDOG.yml": _watchdog(advisors=[advisor])})


@pytest.mark.parametrize(
    "advisor",
    [
        '  - model: "x-ai/grok-code-fast:high"\n    tools: [read]\n    instructions: "i"\n    enabled: true',  # missing name
        '  - name: w\n    tools: [read]\n    instructions: "i"\n    enabled: true',  # missing model
        '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    instructions: "i"\n    enabled: true',  # missing tools
        '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    tools: [read]\n    enabled: true',  # missing instructions
        '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    tools: [read]\n    instructions: "i"',  # missing enabled
        '  - name: w\n    model: ""\n    tools: [read]\n    instructions: "i"\n    enabled: true',  # empty model
        '  - name: w\n    model: "x-ai/grok-code-fast: turbo"\n    tools: [read]\n    instructions: "i"\n    enabled: true',  # bad selector
        '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    tools: [read, write]\n    instructions: "i"\n    enabled: true',  # tool outside set
        '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    tools: [read, read]\n    instructions: "i"\n    enabled: true',  # duplicate tools
        '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    tools: [read]\n    instructions: ""\n    enabled: true',  # empty instructions
        '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    tools: [read]\n    instructions: "See @../secret.md first."\n    enabled: true',  # @-import
        '  - name: w\n    model: "x-ai/grok-code-fast:high"\n    tools: [read]\n    instructions: "i"\n    enabled: true\n    unknown: 1',  # unknown key
    ],
)
def test_watchdog_advisor_rejections(tmp_path, advisor):
    _reject(tmp_path, {"config.yml": _config(enabled=True), "agent/WATCHDOG.yml": _watchdog(advisors=[advisor])})


@pytest.mark.parametrize(
    "watchdog_text",
    [
        _watchdog(advisors=[]),                                            # empty advisors
        _watchdog(advisors=['  - name: w\n    model: "x"\n    tools: [read]\n    instructions: "i"\n    enabled: true', '  - name: w\n    model: "x"\n    tools: [read]\n    instructions: "i"\n    enabled: true']),  # duplicate names
        _watchdog() + "intervalMs: 500\n",                                 # unknown top-level key
        "advisors: 5\n",                                                   # advisors not a list
        'instructions: "watch"\n',                                         # missing advisors
        _watchdog(instructions='"See @../secret.md first."'),              # @-import in instructions
    ],
)
def test_watchdog_closed_rejections(tmp_path, watchdog_text):
    _reject(tmp_path, {"config.yml": _config(enabled=True), "agent/WATCHDOG.yml": watchdog_text})


def test_advisor_enabled_pairing(tmp_path):
    _reject(tmp_path, {"config.yml": _config(enabled=True)})  # enabled true without WATCHDOG.yml
    _reject(tmp_path, {"config.yml": _config(enabled=False), "agent/WATCHDOG.yml": _watchdog()})  # enabled false with file


# ------------------------------------------------------------- agent files


def test_admits_fanout_fixture():
    with _root(os.path.join(FIXTURES, "fanout")) as fd:
        snapshot = admit_conf_tree(fd)
    assert tuple(snapshot.files) == ("agent/agents/alpha.md", "agent/agents/beta.md", "config.yml")
    alpha = snapshot.files["agent/agents/alpha.md"].content.decode("utf-8")
    assert alpha.startswith("---\nname: alpha\n")


@pytest.mark.parametrize(
    "frontmatter",
    [
        {"description": ""},                       # empty description
        {"name": "", "description": "x"},          # empty name
        {"name": "Alpha", "description": "x"},     # uppercase start
        {"name": "1alpha", "description": "x"},    # leading digit
        {"name": "a" * 65, "description": "x"},    # too long
        {"name": "a b", "description": "x"},       # whitespace
        {"name": "a/b", "description": "x"},       # slash
        {"name": "__advisor", "description": "x"},  # reserved name
        {"name": "scout", "description": "x"},     # bundled name
        {"name": "alpha", "description": "x", "output": "on"},          # unknown key
        {"name": "alpha", "description": "x", "thinkingLevel": "high"}, # unknown key
        {"name": "alpha", "description": "x", "advisor": True},         # unknown key
        {"name": "alpha", "description": "x", "blocking": False},       # unknown key
        {"name": "alpha", "description": "x", "autoloadSkills": True},  # unknown key
        {"name": "alpha", "description": "x", "prewalk": True},         # unknown key
        {"name": "alpha", "description": "x", "tools": '[bash2]'},      # tool outside pinned set
        {"name": "alpha", "description": "x", "tools": "[read, read]"}, # duplicate tools
        {"name": "alpha", "description": "x", "tools": "[read, task]"}, # task tool implies spawns: * in OMP; omitted is forbidden
        {"name": "alpha", "description": "x", "tools": "[read, task]", "spawns": "[]"},  # empty spawns with task
        {"name": "alpha", "description": "x", "model": '"x-ai/grok-code-fast: turbo"'},  # bad suffix
        {"name": "alpha", "description": "x", "model": '""'},           # empty model
        {"name": "alpha", "description": "x", "model": '"a\tb"'},       # control char
        {"name": "alpha", "description": "x", "model": '"a,b"'},        # comma implies a list
        {"name": "alpha", "description": "x", "model": '","'},          # bare comma
        {"name": "alpha", "description": "x", "spawns": '["*"]'},       # wildcard spawn
        {"name": "alpha", "description": "x", "spawns": "[missing]"},   # undeclared spawn
        {"name": "alpha", "description": "x", "spawns": "[alpha, alpha]"},  # duplicate spawn
    ],
)
def test_agent_frontmatter_rejections(tmp_path, frontmatter):
    text = _agent_md(**frontmatter)
    _reject(tmp_path, {"config.yml": _config(), "agent/agents/a.md": text})


def test_agent_empty_body_or_missing_fence_rejected(tmp_path):
    for text in (
        "---\nname: alpha\ndescription: x\n---\n",
        "---\nname: alpha\ndescription: x\n---\n   \n",
        "---\nname: alpha\ndescription: x\n",
        "name: alpha\ndescription: x\n---\nbody\n",
    ):
        _reject(tmp_path, {"config.yml": _config(), "agent/agents/a.md": text})


def test_agent_crlf_frontmatter_admitted(tmp_path):
    text = "---\r\nname: alpha\r\ndescription: Worker agent\r\n---\r\nDo the work.\r\n"
    with _root(_tree(tmp_path, {"config.yml": _config(), "agent/agents/a.md": text})) as fd:
        snapshot = admit_conf_tree(fd)
    assert snapshot.files["agent/agents/a.md"].content == text.encode("utf-8")


def test_agent_unique_names_and_descriptions(tmp_path):
    _reject(tmp_path, {"config.yml": _config(), "agent/agents/a.md": _agent_md(name="alpha"),
                       "agent/agents/b.md": _agent_md(name="alpha", description="other")})
    _reject(tmp_path, {"config.yml": _config(), "agent/agents/a.md": _agent_md(name="alpha", description="same"),
                       "agent/agents/b.md": _agent_md(name="beta", description="same")})


def test_agent_spawns_same_tree_ok_and_self_ok(tmp_path):
    files = {
        "config.yml": _config(),
        "agent/agents/a.md": _agent_md(name="alpha", tools="[read, task]", spawns="[beta, alpha]"),
        "agent/agents/b.md": _agent_md(name="beta", description="Beta worker"),
    }
    with _root(_tree(tmp_path, files)) as fd:
        admit_conf_tree(fd)


@pytest.mark.parametrize(
    "body,should_fail",
    [
        ("@../escape.md", True),              # bare @-import
        ("\t@foo", True),                     # leading tab
        ("lead @x/y z", True),                # space before @
        ("@.", True),                         # dot after @
        ("legal user@example.com", False),    # email: legal
        ("legal `@../in.md`", False),         # inline code: legal
        ("legal\n```text\n@../in.md\n```", False),  # leading backtick fence: legal
        ("legal\n~~~text\n@../in.md\n~~~", False),  # leading tilde fence: legal
        ("legal ```text\n@../in.md\n```", True),    # mid-line fence is not a fence
        ("legal ~~~text\n@../in.md\n~~~", True),    # mid-line tilde is not a fence
        ("```\n@../in.md\n````\n@../escape.md", True),  # longer close closes; trailing @ is live
        ("just an @", False),                 # bare @ with no path: legal
        ("user@example.com trailing", False),  # mid-token @: legal
    ],
)
def test_agent_at_import_lexing(tmp_path, body, should_fail):
    text = _agent_md(body=body + "\n")
    if should_fail:
        _reject(tmp_path, {"config.yml": _config(), "agent/agents/a.md": text})
    else:
        with _root(_tree(tmp_path, {"config.yml": _config(), "agent/agents/a.md": text})) as fd:
            admit_conf_tree(fd)


# -------------------------------------------------------- tree membership


@pytest.mark.parametrize("fixture_name", ["at-import", "extra-file", "nested-agents", "watchdog-both"])
def test_invalid_fixture_trees_rejected(fixture_name):
    with _root(os.path.join(FIXTURES, "invalid", fixture_name)) as fd:
        with pytest.raises(OmpConfError):
            admit_conf_tree(fd)


def test_unadmitted_layouts_rejected(tmp_path):
    layouts = [
        {"config.yml": _config(), "agent/skills/s.md": "skill"},               # skills dir
        {"config.yml": _config(), "agent/agents/a.md/x": "not a file"},        # file under agent file
        {"config.yml": _config(), "agent/agents/a.md": "x", "agent/WATCHDOG.yaml": _watchdog()},  # yaml twin only
        {"config.yml": _config(), "agent/WATCHDOG.yml": _watchdog(), "agent/WATCHDOG.yaml": _watchdog()},  # both twins
        {"config.yml": _config(), "agent/foo.md": "x"},                        # file directly under agent/
        {"config.yml": _config(), "agents.md": "x"},                           # agent file at root
        {"config.yml": _config(), "agent/agents/a.md": "x", "config.yml.bak": _config()},  # backup twin
    ]
    for files in layouts: _reject(tmp_path, files)

# ------------------------------------------------------------- safe tree


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "undecodable", "executable"])
def test_unsafe_tree_entry_rejected(tmp_path, kind):
    root = _tree(tmp_path, {"config.yml": _config()})
    agents = os.path.join(root, "agent", "agents")
    os.makedirs(agents, exist_ok=True)
    if kind == "symlink":
        os.symlink("/etc/hostname", os.path.join(agents, "link.md"))
    elif kind == "hardlink":
        os.link(os.path.join(root, "config.yml"), os.path.join(agents, "linked.md"))
    elif kind == "fifo":
        os.mkfifo(os.path.join(agents, "pipe.md"))
    elif kind == "executable":
        agent = os.path.join(agents, "exec.md")
        with open(agent, "w") as handle:
            handle.write("---\nname: exec\ndescription: x\n---\nDo work.\n")
        os.chmod(agent, 0o755)
    else:  # undecodable name
        raw = os.path.join(root, "agent", "agents").encode("utf-8") + b"\xff\xfe_name.md"
        fd = os.open(raw, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        os.close(fd)
    with _root(root) as fd:
        with pytest.raises(OmpConfError):
            admit_conf_tree(fd)


# ---------------------------------------------------------------- manifest


def test_manifest_bytes_are_canonical_spec_encoding():
    with _root(os.path.join(FIXTURES, "fanout")) as fd:
        snapshot = admit_conf_tree(fd)
    expected_rows = [
        {"mode": "0644", "path": path, "sha256": snapshot.files[path].sha256, "size": snapshot.files[path].size_bytes}
        for path in ("agent/agents/alpha.md", "agent/agents/beta.md", "config.yml")
    ]
    expected = json.dumps({"schema_version": "omp_conf_manifest.v1", "files": expected_rows}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert snapshot.manifest_bytes == expected
    assert snapshot.manifest_sha256 == hashlib.sha256(expected).hexdigest()


def test_manifest_records_and_digests_match_files():
    with _root(os.path.join(FIXTURES, "fanout")) as fd:
        snapshot = admit_conf_tree(fd)
    for relative_path, record in snapshot.files.items():
        assert isinstance(record, ConfFileRecord)
        assert record.size_bytes == len(record.content)
        assert record.sha256 == hashlib.sha256(record.content).hexdigest()
        with open(os.path.join(FIXTURES, "fanout", relative_path), "rb") as handle:
            assert handle.read() == record.content


def test_manifest_preserves_utf8_paths_raw(tmp_path):
    root = _tree(tmp_path, {"config.yml": _config()})
    agents = os.path.join(root, "agent", "agents")
    os.makedirs(agents, exist_ok=True)
    with open(os.path.join(agents, "caf\u00e9.md"), "w", encoding="utf-8") as handle:
        handle.write(_agent_md(name="alpha"))
    with _root(root) as fd:
        snapshot = admit_conf_tree(fd)
    # ensure_ascii=False: the encoded manifest carries raw UTF-8, not \u escapes
    assert "caf\u00e9.md".encode("utf-8") in snapshot.manifest_bytes
    assert b"\\u00e9" not in snapshot.manifest_bytes


def test_manifest_stable_across_runs():
    with _root(os.path.join(FIXTURES, "neutral")) as fd:
        first = admit_conf_tree(fd)
    with _root(os.path.join(FIXTURES, "neutral")) as fd:
        second = admit_conf_tree(fd)
    assert first.manifest_bytes == second.manifest_bytes
    assert first.manifest_sha256 == second.manifest_sha256


def test_manifest_changes_with_content(tmp_path):
    root = _tree(tmp_path, {"config.yml": _config()})
    with _root(root) as fd:
        first = admit_conf_tree(fd)
    with open(os.path.join(root, "config.yml"), "a", encoding="utf-8") as handle:
        handle.write("# changed\n")
    with _root(root) as fd:
        second = admit_conf_tree(fd)
    assert first.manifest_sha256 != second.manifest_sha256


def test_snapshot_is_immutable():
    with _root(os.path.join(FIXTURES, "neutral")) as fd:
        snapshot = admit_conf_tree(fd)
    with pytest.raises(TypeError):
        snapshot.files["other.yml"] = snapshot.files["config.yml"]
    with pytest.raises(AttributeError):
        snapshot.manifest_sha256 = "x"  # frozen dataclass


def test_revalidate_detects_drift(tmp_path):
    root = _tree(
        tmp_path,
        {"config.yml": _config(), "agent/agents/a.md": _agent_md(name="alpha")},
    )
    with _root(root) as fd:
        snapshot = admit_conf_tree(fd)
        revalidate_conf_tree(fd, snapshot)

    def reject():
        with _root(root) as fd:
            with pytest.raises(OmpConfError):
                revalidate_conf_tree(fd, snapshot)

    agent_path = os.path.join(root, "agent/agents/a.md")
    original = _agent_md(name="alpha")
    # content mutation
    with open(agent_path, "a", encoding="utf-8") as handle:
        handle.write("extra\n")
    reject()
    with open(agent_path, "w", encoding="utf-8") as handle:
        handle.write(original)
    with _root(root) as fd:
        revalidate_conf_tree(fd, snapshot)
    # extra file
    stray = os.path.join(root, "stray.txt")
    with open(stray, "w", encoding="utf-8") as handle:
        handle.write("x")
    reject()
    os.remove(stray)
    with _root(root) as fd:
        revalidate_conf_tree(fd, snapshot)
    # Allocate the replacement outside the admitted tree while its original
    # inode is live, guaranteeing a distinct identity on inode-reusing filesystems.
    tmp_copy = os.path.join(tmp_path, ".a.md.tmp")
    with open(tmp_copy, "w", encoding="utf-8") as handle:
        handle.write(original)
    # deletion
    os.remove(agent_path)
    reject()
    # same-content inode swap via atomic rename
    os.rename(tmp_copy, agent_path)
    reject()


def test_revalidate_materialized_conf_detects_same_inventory_content_drift(tmp_path):
    source = _tree(tmp_path, {"config.yml": _config()})
    with _root(source) as source_fd:
        snapshot = admit_conf_tree(source_fd)
    destination = tmp_path / "agent"
    destination.mkdir()
    with _root(destination) as destination_fd:
        authority = SimpleNamespace(agent_fd=destination_fd)
        materialize_conf_at_discovery_path(authority, snapshot)
        revalidate_materialized_conf(authority, snapshot)
        config = destination / "config.yml"
        original = config.read_bytes()
        config.write_bytes(b"X" + original[1:])
        with pytest.raises(OmpConfError, match="bytes changed"):
            revalidate_materialized_conf(authority, snapshot)
        config.write_bytes(original)
        os.link(config, tmp_path / "external-link")
        with pytest.raises(OmpConfError, match="authority changed"):
            revalidate_materialized_conf(authority, snapshot)


def test_pinned_agent_tool_sets_are_exact():
    assert BUNDLED_AGENT_NAMES == ("designer", "librarian", "reviewer", "scout", "security-reviewer", "sonic", "task")
    assert set(ADMITTED_AGENT_TOOLS) == {"read", "grep", "glob", "bash", "edit", "write", "task", "hub"}
    assert set(ADMITTED_ADVISOR_TOOLS) == {"read", "grep", "glob"}
