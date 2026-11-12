"""The difficulty ladder's pure rules (plan, "Probable calibration failures and the response to each": Difficulty
ladder, Check-withheld form, Ladder probe, If the whole ladder misses, Bisection instead of the flat probe).

A rung is a tier in one form: `T0` to `T6` in the tier's own form (T5 and T6 check-withheld, the others in-tree)
or `T1w` to `T4w` (T1 to T4 in the check-withheld form). The ladder is ordered from easy to hard. Probe results are
{rung: passes} over the rung's four probe tasks (its first four tasks in seed order); a pass is a run whose
final patch passes the task's whole hidden set.

`table` applies the flat probe's table, `next_rung` the bisection; both return an answer: {"probe": [rungs]},
{"chosen": rung}, {"split": [easier, harder]}, or {"miss": "all_easy" | "all_hard"}. `choose` turns a chosen or
split answer into the calibration's 20 tasks, by rung and seed order only. `ran_visible_test` is the detector of
an agent running the visible test itself. Depends on nothing outside the standard library.
"""

import fnmatch
import json
import re
import shlex
from pathlib import Path

LADDER = ("T0", "T1", "T2", "T3", "T4", "T5", "T6")
FLAT = ("T1", "T2", "T3", "T4", "T5")
EASY_EXTENSION = ("T1w", "T2w", "T3w", "T4w", "T6")  # every rung too easy: the agent loses its test, or T6
HARD_EXTENSION = ("T0", "T1")  # every rung too hard: the hinted T0, and T1 again
IN_TREE, WITHHELD = "in-tree", "check-withheld"
PROBE_TASKS, CALIBRATION_TASKS, SPLIT = 4, 20, 10
SELF_CHECK_SHARE = 0.80
BISECT_WALL_SEC, BISECT_COST_USD = 15 * 60, 0.50  # a median direct run above either: bisect from the start


def tier_form(rung):
    tier = rung.rstrip("w")
    return tier, WITHHELD if rung.endswith("w") or tier in ("T5", "T6") else IN_TREE


def rung_tasks(rows, rung):
    """The rung's task ids in seed order (the order of tasks.jsonl)."""
    tier, form = tier_form(rung)
    return [row["id"] for row in rows if row.get("tier") == tier and row.get("form") == form]


def probe_tasks(rows, rung):
    return rung_tasks(rows, rung)[:PROBE_TASKS]


def order(rungs):
    """Rungs from easy to hard: by tier, the in-tree form before the withheld one."""
    return sorted(rungs, key=lambda rung: (LADDER.index(rung.rstrip("w")), rung.endswith("w")))


def table(results):
    """The flat probe's table over every probed rung (easy to hard)."""
    rungs = order(results)
    if all(results[r] >= PROBE_TASKS - 1 for r in rungs):
        return {"miss": "all_easy"}
    if all(results[r] <= 1 for r in rungs):
        return {"miss": "all_hard"}
    band = [r for r in rungs if 1 <= results[r] <= PROBE_TASKS - 1]
    if band:  # nearest to 2 passes of 4; a tie goes to the harder rung
        return {"chosen": min(band, key=lambda r: (abs(results[r] - 2), -rungs.index(r)))}
    easy = [r for r in rungs if results[r] >= PROBE_TASKS - 1][-1]
    hard = [r for r in rungs if results[r] <= 1][0]
    return {"split": [easy, hard]}


def next_rung(results, rungs):
    """The bisection over `rungs` ({rung: tasks available}, easy to hard; a rung with fewer than four tasks is
    skipped). The middle rung first; 4 of 4 moves to the middle of the harder half, 0 of 4 to the easier half,
    1 to 3 stops there; adjacent rungs at 4 and 0 split; a harder rung passing more than an easier one stops the
    search and returns the remaining rungs to probe flat."""
    ladder = [r for r in order(rungs) if rungs[r] >= PROBE_TASKS]
    probed = [r for r in ladder if r in results]
    if any(results[a] < results[b] for i, a in enumerate(probed) for b in probed[i + 1:]):
        rest = [r for r in ladder if r not in results]
        return {"probe": rest} if rest else table({r: results[r] for r in probed})
    lo, hi = 0, len(ladder) - 1
    while lo <= hi:
        middle = ladder[(lo + hi) // 2]
        if middle not in results:
            return {"probe": [middle]}
        if 1 <= results[middle] <= PROBE_TASKS - 1:
            return {"chosen": middle}
        lo, hi = ((lo + hi) // 2 + 1, hi) if results[middle] == PROBE_TASKS else (lo, (lo + hi) // 2 - 1)
    if lo == len(ladder):
        return {"miss": "all_easy"}
    if lo == 0:
        return {"miss": "all_hard"}
    return {"split": [ladder[lo - 1], ladder[lo]]}


def withheld_rung(rung):
    return f"{rung}w" if rung in ("T1", "T2", "T3", "T4") else rung


def choose(rows, answer, results, self_share, rungs=()):
    """[(task, rung)] of the calibration's 20 tasks for a chosen or split answer, in seed order within each rung:
    the chosen rung, then the probed and the searched `rungs` by distance from it (a tie: the one whose probe count is nearer 2, then the
    harder); a split takes ten from each side first. With the agent running the visible test in 80% or more of
    the in-tree probe runs, a chosen T1 to T4 rung is used in the check-withheld form."""
    first = answer.get("split") or [answer["chosen"]]
    switch = (self_share is not None and self_share >= SELF_CHECK_SHARE
              and any(r in ("T1", "T2", "T3", "T4") for r in first))
    ladder = order(set(results) | set(first) | set(rungs))

    def rank(rung):
        distance = min(abs(ladder.index(rung) - ladder.index(f)) for f in first)
        return distance, abs(results[rung] - 2) if rung in results else PROBE_TASKS, -ladder.index(rung)

    picked, taken = [], set()
    for rung, quota in [(r, SPLIT) for r in answer.get("split", [])] + [(r, None) for r in sorted(ladder, key=rank)]:
        used = withheld_rung(rung) if switch else rung
        new = [t for t in rung_tasks(rows, used) if t not in taken][:quota]
        picked += [(t, used) for t in new]
        taken.update(new)
    return picked[:CALIBRATION_TASKS]


OPTIONS_WITH_VALUE = {"-k", "-m", "-p", "-c", "-o", "-n", "-W", "--tb", "--rootdir", "--deselect", "--ignore",
                      "--maxfail", "--dist", "--basetemp", "--timeout", "--log-level", "--confcutdir"}


def visible_targets(package):
    """The visible check's test paths and node ids, from the package's seed/dev-check.json."""
    argv = json.loads((Path(package) / "seed" / "dev-check.json").read_text())["argv"]
    return [arg for arg in argv if not arg.startswith("-") and (".py" in arg or "/" in arg) and "pytest" not in arg
            and not arg.endswith(("python", "python3"))]


def _pytest_paths(words):
    """The path arguments of a pytest invocation in `words`, or None when it does not invoke pytest."""
    starts = [i for i, w in enumerate(words) if w in ("pytest", "py.test") or w.endswith(("/pytest", "/py.test"))]
    if not starts:
        return None
    paths, skip = [], False
    for word in words[starts[0] + 1:]:
        if skip:
            skip = False
        elif word.startswith("-"):
            skip = word in OPTIONS_WITH_VALUE
        else:
            paths.append(word)
    return paths


def _covers(path, file):
    path = path.split("::")[0].removeprefix("./").rstrip("/")
    return (path in ("", ".") or file == path or file.startswith(path + "/") or fnmatch.fnmatch(file, path)
            or Path(file).name == path)


def ran_visible_test(command, targets):
    """Whether a shell command runs the visible test: it runs dev_check.py, or a pytest invocation (`pytest`,
    `py.test`, `python -m pytest`) whose path arguments are absent (the whole suite), or name the visible file or
    node, its basename, a directory holding it, or a glob matching it."""
    if "dev_check.py" in command:
        return True
    files = {target.split("::")[0] for target in targets}
    for part in re.split(r"&&|\|\||[;|\n]", command):
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        paths = _pytest_paths(words)
        if paths is not None and (not paths or any(_covers(p, f) for p in paths for f in files)):
            return True
    return False


def shell_commands(home):
    """Every Bash command in the session transcripts under a private home (subagents' sidechains included)."""
    commands = []
    for path in sorted((Path(home) / ".claude" / "projects").rglob("*.jsonl")):
        for line in path.read_text(errors="replace").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = (entry.get("message") or {}).get("content") if isinstance(entry, dict) else None
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash":
                    commands.append(str((block.get("input") or {}).get("command", "")))
    return commands


def self_checked(home, targets):
    return any(ran_visible_test(command, targets) for command in shell_commands(home))
