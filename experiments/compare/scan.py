"""Contamination scan (design D5 as amended by ruling R20): find every hit, decide nothing.

find_hits(records, tree, main, runtime, solution, since, home) -> [{"file", "line", "pattern", "text"}]

Sources: the shims' calls/<n>/stdout.txt and stderr.txt under the run's records directory; the Claude
CLI's session files (~/.claude/projects/<slug>, the slug being the path with every non-alphanumeric
character as "-") for the agents' tree and every directory under it, tool_use inputs only; codex
rollouts (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl) modified since `since` whose session cwd lies
in the tree, function, custom tool and shell call arguments only. Patterns: the main checkout's path
as a prefix (sibling worktrees hold solutions), the frozen checkout's path bounded, the name of any
other agents' tree beside this one (another run's work), github.com, the gh command, git fetch and
the solution commit's first seven characters. Standard library only.
"""

import json
import re
from pathlib import Path


def patterns(main, runtime, solution, others):
    found = {"main checkout prefix": re.escape(str(main)),
             "frozen checkout": re.escape(str(runtime)) + r"(?![\w.-])",
             "github.com": r"github\.com", "gh": r"(?<![\w./-])gh\s", "git fetch": r"git\s+fetch",
             "solution hash": re.escape(solution[:7])}
    return found | ({"other agents' tree": "|".join(re.escape(name) for name in others)} if others else {})


def claude_actions(row):
    content = (row.get("message") or {}).get("content")
    return [json.dumps(c["input"], ensure_ascii=False)
            for c in content or [] if isinstance(c, dict) and c.get("type") == "tool_use"]


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


def sources(records, tree, since, home):
    """(file, line number, text) for every recorded output and structured agent action of the run."""
    for path in sorted(records.glob("calls/*/std*.txt")):
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            yield path, number, line
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(tree))
    for project in sorted((home / ".claude" / "projects").glob(slug + "*")):
        if project.name == slug or project.name.startswith(slug + "-"):
            for path in sorted(project.rglob("*.jsonl")):
                yield from json_actions(path, claude_actions)
    for path in sorted((home / ".codex" / "sessions").glob("*/*/*/rollout-*.jsonl")):
        if path.stat().st_mtime >= since and (codex_cwd(path) + "/").startswith(f"{tree}/"):
            yield from json_actions(path, codex_actions)


def find_hits(records, tree, main, runtime, solution, since, home):
    others = sorted(p.name for p in Path(tree).parent.iterdir() if p.name != Path(tree).name)
    compiled = patterns(main, runtime, solution, others)
    hits = []
    for path, number, text in sources(Path(records), Path(tree), since, Path(home)):
        for name, pattern in compiled.items():
            found = re.search(pattern, text)
            if found:
                hits.append({"file": str(path), "line": number, "pattern": name,
                             "text": text[max(0, found.start() - 80):found.end() + 80]})
    return hits
