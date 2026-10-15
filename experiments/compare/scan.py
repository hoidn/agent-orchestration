"""Contamination scan (design D5 as amended by rulings R20, R22, R23): find every hit, decide nothing.

patterns(...) -> {name: regex}; find_hits(calls_root, tree, since, home, patterns) -> [{"file", "line",
"pattern", "text"}]. The same scan serves an agent run (calls_root = its records directory, tree = its
agents' tree) and a judge (calls_root = its records under the pool, tree = its working directory).

Sources: the shims' calls/<n>/stdout.txt and stderr.txt under calls_root; the Claude CLI's session
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
.codex/sessions, .codex/history, claude-tmux-sockets), which stay readable on disk (R35). Paths
match as typed: absolute, or under ~, $HOME or ${HOME} (R23).

Model policy (owner, 2026-10-15): no experiment call may use a Fable model. The same Claude sessions are
also read for each assistant message's message.model metadata (only there: printed text naming a model is
not an answer); a Fable one is a "Fable model" hit, which cannot be cleared and excludes the run or judge
(model_policy). Standard library only.
"""

import json
import re
from pathlib import Path

ARMS = "best_of_n|reviewed_change|design_review_execute|direct_task"
FABLE = "Fable model"
POOL_FILES = r"records/(?:mapping\.json|patches/|score-inputs-|(?:score|resume)-\S*\.sh|results\.(?:json|md)|judges/)"


def spelled(path, home):
    """A regex for `path` absolute, or written under ~, $HOME or ${HOME} when it lies in `home`."""
    path, home = str(path), str(home).rstrip("/")
    if path.startswith(home + "/"):
        return r"(?:" + re.escape(home) + r"|~|\$HOME|\$\{HOME\})" + re.escape(path[len(home):])
    return re.escape(path)


def patterns(*, main, runtime, solution, home, others=(), roots=()):
    """`roots` are (name, path) pairs matched as a prefix wherever the path is written."""
    found = {"main checkout prefix": spelled(main, home),
             "frozen checkout": spelled(runtime, home) + r"(?![\w.-])",
             "records layout": rf"records/(?:{ARMS})/run-\d+\b", "pool record files": POOL_FILES,
             "github.com": r"github\.com", "gh": r"(?<![\w./-])gh\s", "git fetch": r"git\s+fetch",
             "solution hash": re.escape(solution[:7]),
             "other sessions' files": r"\.claude/projects|\.codex/(?:sessions|history)|claude-tmux-sockets"}
    for name, path in roots:
        found[name] = spelled(path, home)
    if others:
        found["other tree or judge"] = "|".join(re.escape(name) for name in others)
    return found


def claude_actions(row):
    content = (row.get("message") or {}).get("content")
    return [json.dumps(c["input"], ensure_ascii=False)
            for c in content or [] if isinstance(c, dict) and c.get("type") == "tool_use"]


def answering_model(row):
    """The model that answered, from an assistant row's message.model metadata."""
    model = (row.get("message") or {}).get("model") if row.get("type") == "assistant" else None
    return [model] if isinstance(model, str) else []


def model_policy(hits):
    """Why Fable answers in the scanned sessions exclude the run or judge, or None (they cannot be cleared)."""
    fable = sum(hit["pattern"] == FABLE for hit in hits)
    return f"Fable model used in {fable} assistant message(s): no experiment call may use Fable" if fable else None


def refuse_clearing(verdict, hits, subject):
    """A controller may not clear Fable answers: they break the model policy, whatever the reason."""
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
            yield path, number, line
    for path in claude_sessions(tree, home):
        yield from json_actions(path, claude_actions)
    for path in sorted((home / ".codex" / "sessions").glob("*/*/*/rollout-*.jsonl")):
        if path.stat().st_mtime >= since and (codex_cwd(path) + "/").startswith(f"{tree}/"):
            yield from json_actions(path, codex_actions)


def claude_sessions(tree, home):
    """The Claude CLI's session files for the tree and every directory under it."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(tree))
    for project in sorted((home / ".claude" / "projects").glob(slug + "*")):
        if project.name == slug or project.name.startswith(slug + "-"):
            yield from sorted(project.rglob("*.jsonl"))


def siblings(tree):
    return sorted(p.name for p in Path(tree).parent.iterdir() if p.name != Path(tree).name)


def find_hits(calls_root, tree, since, home, compiled):
    hits = []
    for path, number, text in sources(Path(calls_root), Path(tree), since, Path(home)):
        for name, pattern in compiled.items():
            found = re.search(pattern, text)
            if found:
                hits.append({"file": str(path), "line": number, "pattern": name,
                             "text": text[max(0, found.start() - 80):found.end() + 80]})
    for path in claude_sessions(Path(tree), Path(home)):  # the model policy reads metadata, never printed text
        for _, number, model in json_actions(path, answering_model):
            if "fable" in model.lower():
                hits.append({"file": str(path), "line": number, "pattern": FABLE, "text": f"message.model: {model}"})
    return hits
