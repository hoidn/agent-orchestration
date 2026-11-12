"""The difficulty ladder's pure rules (plan, "Probable calibration failures and the response to each": Difficulty
ladder, Check-withheld form, Ladder probe, If the whole ladder misses, Bisection instead of the flat probe).

A rung is a tier in one form: `T0` to `T5` in the tier's own form (T5 check-withheld, the others in-tree) or `T1w`
to `T4w` (T1 to T4 in the check-withheld form). T6 is dropped as a rung (coordinator ruling 2, 2026-11-12: its one
task cannot be probed with four), so the extension upward ends at T5. The ladder is ordered from easy to hard.

`packages` reads the manifest (`tasks.jsonl`: per row `tier`, `form` "in_tree" | "withheld", `withheld_id`,
`probe`, `set`, `rejected`, `commit`, `commits`) into one entry per usable package in seed order: a rejected row,
the smoke's row (`set` "smoke") and every package sharing a commit with the smoke are left out. A rung's probe
tasks are its packages whose row carries `probe` (the builder flags the first four of each tier in seed order).
Probe results are {rung: passes} over the rung's four probe tasks; a pass is a run whose final patch passes the
task's whole hidden set.

`table` applies the flat probe's table, `next_rung` the bisection; both return an answer: {"probe": [rungs]},
{"chosen": rung}, {"split": [easier, harder]}, or {"miss": "all_easy" | "all_hard"}. `choose` turns a chosen or
split answer into the calibration's tasks, by rung and seed order only, never the same commit twice; a draw that
does not reach 20 is a stop (coordinator ruling, 2026-11-12: the calibration runs at 20 tasks with the plan's
frozen thresholds, or not at all). `ran_visible_test` is the detector of an agent running the visible test
itself. Depends on nothing outside the standard library.
"""

import fnmatch
import json
import re
import shlex
from pathlib import Path

LADDER = ("T0", "T1", "T2", "T3", "T4", "T5")
FLAT = ("T1", "T2", "T3", "T4", "T5")
EASY_EXTENSION = ("T1w", "T2w", "T3w", "T4w")  # every rung too easy: the agent loses its test
HARD_EXTENSION = ("T0", "T1")  # every rung too hard: the hinted T0, and T1 again
IN_TREE, WITHHELD = "in-tree", "check-withheld"
WITHHELD_TIERS = ("T5",)  # built in the check-withheld form only
PROBE_TASKS, CALIBRATION_TASKS, SPLIT = 4, 20, 10
SELF_CHECK_SHARE = 0.80
BISECT_WALL_SEC, BISECT_COST_USD = 15 * 60, 0.50  # a median direct run above either: bisect from the start
HINTED = ("T0", "T1")  # T0 is T1 with its failing assertion quoted: the same commits


def commits(row):
    return set(row.get("commits") or [row["commit"]])


def packages(rows):
    """[{"id", "rung", "commits", "probe"}] of every usable package in seed order (both forms of a row)."""
    smoke = set().union(*(commits(row) for row in rows if row.get("set") == "smoke"))
    found = []
    for row in rows:
        if row.get("tier") not in LADDER or row.get("rejected") or row.get("set") == "smoke" or commits(row) & smoke:
            continue
        own = row["tier"] + ("w" if row["form"] == "withheld" and row["tier"] not in WITHHELD_TIERS else "")
        found.append({"id": row["id"], "rung": own, "commits": commits(row), "probe": bool(row.get("probe"))})
        if row.get("withheld_id"):
            found.append({"id": row["withheld_id"], "rung": f"{row['tier']}w", "commits": commits(row),
                          "probe": bool(row.get("probe"))})
    return found


def fix_commits(rows):
    """{package id: the fix's (last) commit} over both forms of every row."""
    return {pid: row["commit"] for row in rows for pid in (row["id"], row.get("withheld_id")) if pid}


def tier_form(rung):
    tier = rung.rstrip("w")
    return tier, WITHHELD if rung.endswith("w") or tier in WITHHELD_TIERS else IN_TREE


def rung_tasks(rows, rung):
    """The rung's package ids in seed order (the order of tasks.jsonl)."""
    return [p["id"] for p in packages(rows) if p["rung"] == rung]


def probe_tasks(rows, rung):
    return [p["id"] for p in packages(rows) if p["rung"] == rung and p["probe"]]


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


def rung_counts(rungs):
    """{rung: how many} over a draw's rungs, easy to hard."""
    return {rung: rungs.count(rung) for rung in order(set(rungs))}


def adjacent(rung, rungs, results):
    """The neighbour of `rung` in the phase's ladder `rungs` that fills it (plan: "filled from the adjacent tier whose
    count is nearer to 2"): an unprobed neighbour counts as farthest; a tie goes to the EASIER neighbour (coordinator
    ruling on review2 M1, 2026-11-12: the easier side is the larger tier, so the tie no longer stops T4 filled from
    T5 at 11 tasks). Choosing a rung (`table`) keeps its own tie rule, the harder."""
    ladder = order(set(rungs) | {rung})
    at = ladder.index(rung)
    near = [ladder[k] for k in (at - 1, at + 1) if 0 <= k < len(ladder)]
    return min(near, key=lambda r: (abs(results[r] - 2) if r in results else PROBE_TASKS, ladder.index(r)),
               default=None)


def draw_plan(answer, rungs, results):
    """[(rung, quota or None)] in the order they are drawn (coordinator rulings, 2026-11-12). A split: ten from each
    side, then the rest of each side in turn, so a side shorter than ten is topped up from the other; a split of
    T0 and T1 (one set of commits) continues from T2. A chosen rung: its tasks, then its adjacent rung, or T2 when
    that rung is the chosen one's hinted twin (T0 for T1, T1 for T0), which adds no new commit."""
    if "split" in answer:
        sides = answer["split"]
        extra = [("T2", None)] if set(sides) == set(HINTED) else []
        return [(rung, SPLIT) for rung in sides] + [(rung, None) for rung in sides] + extra
    chosen, fill = answer["chosen"], adjacent(answer["chosen"], rungs, results)
    if {chosen, fill} == set(HINTED):
        fill = "T2"
    return [(chosen, None)] + ([(fill, None)] if fill else [])


def choose(rows, answer, results, self_share, rungs):
    """[(task, rung)] the calibration draws for a chosen or split answer: at most 20, in seed order within each rung,
    never two packages of one commit, from the rungs `draw_plan` names and nowhere else (tier sizes are what they
    are). Fewer than 20 means the ladder is too short there: the caller stops. With the agent running the visible
    test in 80% or more of the in-tree probe runs and a T1 to T4 rung in the answer, every drawn rung is used in
    the check-withheld form."""
    first = answer.get("split") or [answer["chosen"]]
    switch = (self_share is not None and self_share >= SELF_CHECK_SHARE
              and any(r in ("T1", "T2", "T3", "T4") for r in first))
    by_id, picked, seen = {p["id"]: p for p in packages(rows)}, [], set()
    for rung, quota in draw_plan(answer, rungs, results):
        used, taken = withheld_rung(rung) if switch else rung, 0
        for task in rung_tasks(rows, used):
            if taken != quota and not by_id[task]["commits"] & seen:
                picked.append((task, used))
                seen |= by_id[task]["commits"]
                taken += 1
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
