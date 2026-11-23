"""Contamination scan (design D5 as amended by rulings R20, R22, R23): find every hit, decide nothing.

patterns(...) -> {name: regex}; find_hits(calls_root, tree, since, home, patterns) -> [{"file", "line",
"pattern", "text"}]. The same scan serves an agent run (calls_root = its records directory, tree = its
agents' tree) and a judge (calls_root = its records under the pool, tree = its working directory).

Sources: the shims' calls/<n>/stdout.txt and stderr.txt under calls_root, the Claude CLI's own `system/init`
events without the paths the CLI fills in itself (`scanned`: its auto-memory path names .claude/projects on
every run); the Claude CLI's session
files (~/.claude/projects/<slug>, the slug being the path with every non-alphanumeric character as "-")
for the tree and every directory under it, tool_use inputs only; codex rollouts
(~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl) modified since `since` whose session cwd lies in the
tree, function, custom tool and shell call arguments only.

Patterns: the main checkout's path as a prefix (sibling worktrees hold solutions); the frozen
runtime's path, bounded; any named records root (the work root's records, a pool's records); the
records layout `records/<arm>/run-<k>` and a pool's record files, wherever they lie (a run's own
state is under its tree's .orchestrate/, so no records path is legitimate); the name of any other tree or judge
directory beside this one; github.com, the gh command, git fetch and the solution commit's first
seven characters; any mention of other sessions' transcripts or tmux sockets (.claude/projects,
.codex/sessions, .codex/history, claude-tmux-sockets). New prepared units supply
their recorded private-home backing; historical callers retain their original home. Paths
match as typed: absolute, or under ~, $HOME or ${HOME} (R23).

Model policy: Sonnet/Terra remain the defaults; an explicitly bound Codex run may use Luna or Sol 6.1 and an
explicitly bound Claude run or judge Haiku (expected_claude_model). Any other answering model is a hit. Read actual
Claude assistant message.model and Codex turn_context.model metadata, never printed model names. A Claude row
answered by `<synthetic>` is the CLI's own message (an API error, a usage limit): no hit where a Claude model is
allowed, a hit where none is.
Fable and every other forbidden/unknown model are non-clearable policy hits. Standard library only.
"""

import json
import re
from pathlib import Path

try:
    from . import sandbox  # imported as experiments.compare.scan
except ImportError:  # run as a script
    import sandbox

ARMS = "best_of_n|reviewed_change|design_review_execute|direct_task"
FABLE = "Fable model"
FORBIDDEN_MODEL = "Forbidden model"
CODEX_MODELS = ("gpt-5.6-terra", "gpt-5.6-luna", "gpt-6.1-sol")
JUDGE_TESTS = r"\bpytest\b|\bdev_check(?:\.py)?\b"
BOUNDARY = r"(?![\w.-])"  # a path ends here: what follows is not part of its last component
POOL_FILES = r"records/(?:mapping\.json|patches/|score-inputs-|(?:score|resume)-\S*\.sh|results\.(?:json|md)|judges/)"


def spelled(path, home):
    """A regex for `path` absolute, or written under ~, $HOME or ${HOME} when it lies in `home`."""
    path, home = str(path), str(home).rstrip("/")
    if path.startswith(home + "/"):
        return r"(?:" + re.escape(home) + r"|~|\$HOME|\$\{HOME\})" + re.escape(path[len(home):])
    return re.escape(path)


def patterns(*, main, runtime, solution, home, others=(), roots=()):
    """`roots` are (name, path) pairs matched wherever the path is written, as itself or a prefix ending at a
    path boundary (a root /a/ss matches /a/ss/t, not /a/ss-work); roots sharing a name (two holdout roots, the
    records roots of several runs) all match under it."""
    found = {"main checkout prefix": spelled(main, home),
             "frozen checkout": spelled(runtime, home) + BOUNDARY,
             "records layout": rf"records/(?:{ARMS})/run-\d+\b", "pool record files": POOL_FILES,
             "github.com": r"github\.com", "gh": r"(?<![\w./-])gh\s", "git fetch": r"git\s+fetch",
             "solution hash": re.escape(solution[:7]),
             "other sessions' files": r"\.claude/projects|\.codex/(?:sessions|history)|claude-tmux-sockets"}
    for name, path in roots:
        bounded = spelled(path, home) + BOUNDARY
        found[name] = f"{found[name]}|{bounded}" if name in found else bounded
    if others:
        found["other tree or judge"] = "|".join(re.escape(name) + BOUNDARY for name in others)  # not episode-10
    return found


def claude_actions(row):
    content = (row.get("message") or {}).get("content")
    return [json.dumps(c["input"], ensure_ascii=False)
            for c in content or [] if isinstance(c, dict) and c.get("type") == "tool_use"]


def answering_model(row):
    """Actual answering-model metadata from a Claude assistant or a Codex turn context."""
    if row.get("type") == "assistant":
        model = (row.get("message") or {}).get("model")
    elif row.get("type") == "turn_context":
        model = (row.get("payload") or {}).get("model")
    else:
        model = None
    return [model] if isinstance(model, str) else []


def model_policy(hits):
    """Policy violations exclude a run or judge regardless of an operator verdict."""
    violations = [hit for hit in hits if hit["pattern"] in (FABLE, FORBIDDEN_MODEL)]
    return (f"{violations[0]['pattern']} used in {len(violations)} model record(s): "
            "answering model violates the frozen run policy; Fable is forbidden") if violations else None


def refuse_clearing(verdict, hits, subject):
    """A controller may not clear answers outside the owner model cap."""
    if verdict == "cleared" and model_policy(hits):
        raise SystemExit(f"{subject}: {model_policy(hits)}; it cannot be cleared")


def codex_actions(row):
    payload = row.get("payload") or {}
    if payload.get("type") not in ("function_call", "custom_tool_call", "local_shell_call"):
        return []
    return [json.dumps(payload.get("arguments") or payload.get("input") or payload.get("action"), ensure_ascii=False)]


def json_actions(path, actions):
    with path.open(errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except ValueError as error:
                raise SystemExit(f"{path}:{number}: not JSON ({error})")
            for text in actions(row):
                yield path, number, text


def codex_cwd(path):
    with path.open(errors="replace") as handle:
        return ((json.loads(handle.readline() or "{}").get("payload") or {}).get("cwd")) or ""


def sources(calls_root, tree, since, home):
    """(file, line number, text) for every recorded output and structured agent action."""
    for path in sorted(calls_root.glob("calls/*/std*.txt")):
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            yield path, number, scanned(line)
    for path in claude_sessions(tree, home):
        yield from json_actions(path, claude_actions)
    for path in codex_sessions(tree, since, home):
        yield from json_actions(path, codex_actions)


CLI_PATHS = ("memory_paths", "messaging_socket_path")  # init event fields holding the CLI's own paths


def scanned(line):
    """A stdout line as the scan reads it: the Claude CLI's `system/init` event without `CLI_PATHS` (its
    auto-memory directory under .claude/projects, its messaging socket), which no agent writes; else the line."""
    if '"init"' not in line:
        return line
    try:
        event = json.loads(line)
    except ValueError:
        return line
    if not (isinstance(event, dict) and event.get("type") == "system" and event.get("subtype") == "init"):
        return line
    return json.dumps({key: value for key, value in event.items() if key not in CLI_PATHS}, ensure_ascii=False)


def claude_sessions(tree, home):
    """The Claude CLI's session files for the tree and every directory under it."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(tree))
    for project in sorted((home / ".claude" / "projects").glob(slug + "*")):
        if project.name == slug or project.name.startswith(slug + "-"):
            yield from sorted(project.rglob("*.jsonl"))


def codex_sessions(tree, since, home):
    """Rollouts modified since launch whose recorded cwd belongs to this tree."""
    for path in sorted((home / ".codex" / "sessions").glob("*/*/*/rollout-*.jsonl")):
        if path.stat().st_mtime >= since and (codex_cwd(path) + "/").startswith(f"{tree}/"):
            yield path


SYNTHETIC = "<synthetic>"  # the Claude CLI's own messages (an API error, a usage limit): no model answered them


def claude_synthetic(row):
    """[(answering model, whether it is a Claude assistant row answered by `<synthetic>`)] of one session row."""
    return [(model, row.get("type") == "assistant" and model == SYNTHETIC) for model in answering_model(row)]


def model_hits(paths, allowed):
    """Every answering model other than `allowed`; a Claude assistant row answered by `<synthetic>` is a hit only
    where no model is allowed, and any other `<synthetic>` row is always one."""
    for path in paths:
        for _, number, (model, synthetic) in json_actions(path, claude_synthetic):
            if model != allowed and not (allowed and synthetic):
                pattern = FABLE if "fable" in model.lower() else FORBIDDEN_MODEL
                yield {"file": str(path), "line": number, "pattern": pattern, "text": f"model: {model}"}


def siblings(tree):
    return sorted(p.name for p in Path(tree).parent.iterdir() if p.name != Path(tree).name)


def refuse_publication_errors(calls_root):
    """A pending or failed apparatus delivery is never an adjudicable natural outcome."""
    for call in Path(calls_root).glob('calls/*'):
        marker = call / 'publication-error.json'
        if marker.exists() or marker.is_symlink():
            raise SystemExit(f'{marker}: incomplete or failed sandbox result publication')


def find_hits(calls_root, tree, since, home, compiled, *, expected_codex_model="gpt-5.6-terra",
              expected_claude_model=sandbox.SONNET):
    refuse_publication_errors(calls_root)
    if expected_codex_model not in CODEX_MODELS:
        raise SystemExit("expected Codex model must be an exact known Codex ID")
    if expected_claude_model not in sandbox.CLAUDE_MODELS:
        raise SystemExit("expected Claude model must be the exact Sonnet or Haiku ID")
    hits = []
    for path, number, text in sources(Path(calls_root), Path(tree), since, Path(home)):
        for name, pattern in compiled.items():
            found = re.search(pattern, text)
            if found:
                hits.append({"file": str(path), "line": number, "pattern": name,
                             "text": text[max(0, found.start() - 80):found.end() + 80]})
    hits.extend(model_hits(claude_sessions(Path(tree), Path(home)), expected_claude_model))
    hits.extend(model_hits(codex_sessions(Path(tree), since, Path(home)), expected_codex_model))
    return hits
