"""Phase 3b T6: `resume` under an edited program refuses as before and prints the plan an acceptance would apply.

The plan (Edit And Continue §3, §5, §6) is computed read-only after the refusal is decided: what is kept, what is
cancelled from the cut, what is asked again and retried, then a `plan token:` line. No command accepts the token yet
(T7). Every test drives the public command line with local stand-ins (commands are Python scripts; providers are the
suite's fake CLIs on a closed PATH); no model is called. Every refusal and every printed plan is checked to leave the
run tree byte for byte as it was.
"""
from __future__ import annotations

import json
import re
import shlex
import shutil
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests import rebased_fixture as fx
from tests.test_workflow_run_ref_confined_child import world  # noqa: F401 - the confined child fixture
from tests.workflow_inprocess_cli_helpers import cli_inprocess

P = "workflow:pipe::run / "
STEP = '''import json, os, sys
from pathlib import Path
Path("log.txt").open("a").write(sys.argv[1] + "\\n")
if Path("dirty-" + sys.argv[1]).exists():
    Path(sys.argv[0]).open("a").write("# changed by its own attempt\\n")
if Path("fail-" + sys.argv[1]).exists():
    sys.exit(1)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(sys.argv[2]) + 1))
'''
TARGET = '(:target-dsl "2.40")'          # every source here; the refusal case "target" edits this one literal
HEAD = f'(workflow-lisp (:language "0.1") {TARGET}\n  (defmodule pipe) IMPORTS (export run)\n'
COMMANDS = {"step": {"stable_command": ["python", "t.py"], "closure": ["t.py"]},
            "shell": {"stable_command": ["sh", "s.sh"], "closure": ["s.sh"]}}


def cmd(tag: str, arg: str, tool: str = "step") -> str:
    script = {"step": '"python" "t.py"', "shell": '"sh" "s.sh"'}[tool]
    return f'(command-result {tool} :argv ({script} "{tag}" {arg}) :returns Int)'


def lets(*bindings: tuple[str, str]) -> str:
    return "\n           ".join(f"({name} {value})" for name, value in bindings)


def body(bindings, result: str) -> str:
    return f'''  (defworkflow run ((n Int :default 0)) -> Int
    (let* ({lets(*bindings)})
      {result}))'''


SERIAL = [("s1", cmd("s1", "n")), ("s2", cmd("s2", "s1")), ("s3", cmd("s3", "s2")), ("s4", cmd("s4", "s3"))]


def source(text: str, imports: str = "") -> str:
    return HEAD.replace("IMPORTS", imports) + text + ")\n"


def workspace(root: Path, text: str, *, imports: str = "", extra: dict[str, str] | None = None,
              commands: dict | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "t.py").write_text(STEP)
    (root / "s.sh").write_text('echo $(( $2 + 1 )) > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n')
    (root / "commands.json").write_text(json.dumps(commands or COMMANDS))
    for name, content in (extra or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)
    (root / "pipe.orc").write_text(source(text, imports))
    return root


RUN_ARGS = ("pipe.orc", "--command-boundaries-file", "commands.json")


def run(root: Path, *, code: int = 0) -> Path:
    done = cli_inprocess(root, "run", *RUN_ARGS)
    assert done.returncode == code, done.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root


def edit(root: Path, old: str, new: str, name: str = "pipe.orc") -> None:
    text = (root / name).read_text()
    assert old in text, old
    (root / name).write_text(text.replace(old, new))


def tree(root: Path) -> dict[str, bytes]:
    """Every file under the workspace's `.orchestrate` (the run root, its state and its locks), by path."""
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted((root / ".orchestrate").rglob("*")) if path.is_file()}


LOCKS = {"run.lock", "workspace.lock", "workspace.guard"}


def assert_unchanged(root: Path, before: dict[str, bytes]) -> None:
    """Every file is as it was. The one exception: a lock file that did not exist yet (a recorded fixture has none),
    which taking the run writer lock creates in any `resume`, before and without this task."""
    after = tree(root)
    assert {name: after[name] for name in before} == before
    assert all(Path(name).name in LOCKS for name in set(after) - set(before)), sorted(set(after) - set(before))


def refused(root: Path, run_root: Path, code: str = "resume_program_changed", *flags: str):
    """`resume`, which must exit 2 with `code` on its first line and leave every byte of the run tree as it was."""
    before = tree(root)
    done = cli_inprocess(root, "resume", run_root.name, *flags)
    assert done.returncode == 2, done.stderr
    assert done.stderr.splitlines()[0].startswith(f"[{code}] "), done.stderr
    assert_unchanged(root, before)
    return done


def short(identity: str) -> str:
    return identity.split(" / ", 1)[1]


def printed_plan(stderr: str) -> dict[str, list[str]]:
    """The sections of the printed plan: `kept`, `cancelled`, `retired` (identities, without the prefix), `cut`,
    `asked again`, `unfinished`, `runs first` and `token`."""
    lines = stderr.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("if accepted, "))
    plan: dict[str, list[str]] = {"unfinished": []}
    section = None
    for line in lines[start + 1:]:
        if line.startswith("plan token: "):
            plan["token"] = [line.removeprefix("plan token: ")]
            break
        if line.startswith("    ... and "):
            continue
        if line.startswith("    ") and section is not None:
            plan[section].append(short(line.strip().split("   (")[0].split(": ")[0]))
            continue
        heading = re.match(r"  (kept|cancelled|retired)\s+(.*)$", line)
        if heading:
            section = heading[1]
            plan[section] = []
            continue
        section = "unfinished" if line.startswith("  unfinished steps retried:") else None
        for key in ("the cut is at", "asked again", "runs first"):
            if line.startswith(f"  {key}"):
                plan[key.removeprefix("the ")] = [line.split(key, 1)[1].lstrip(": ")]
    return plan


def kept_and_cancelled(stderr: str) -> tuple[list[str], list[str]]:
    plan = printed_plan(stderr)
    return plan["kept"], plan["cancelled"]


def offsets(run_root: Path) -> dict[str, int]:
    """identity (short) -> offset of its active commit, for a journal without cancellations."""
    return {short(row["identity"]): at for at, row in zip(fx.offsets(run_root), fx.rows(run_root))
            if row["record"] == "committed"}


# ---- each edit kind (design §3, both tables) --------------------------------------------------------------------

def serial(root):
    return workspace(root, body(SERIAL, "s4"))


def independent(root):
    return workspace(root, body([SERIAL[0], ("s2", cmd("s2", "s1")), ("s3", cmd("s3", "s1")),
                                 ("s4", cmd("s4", "(+ s2 s3)"))], "s4"))


def loop(root):
    return workspace(root, f'''  (defworkflow run ((n Int :default 0)) -> Int
    (let* ((pre {cmd("pre", "n")})
           (acc (loop/recur :max 3 :state pre :on-exhausted s
                  (fn (s) (let* ((a {cmd("a", "s")})
                                 (b {cmd("b", "a")}))
                      (if (>= b 100) (done b) (continue b))))))
           (post {cmd("post", "acc")}))
      post))''')


def branch(root):
    return workspace(root, f'''  (defworkflow run ((n Int :default 0)) -> Int
    (let* ((s1 {cmd("s1", "n")})
           (mid (if (> s1 0)
                  (let* ((t1 {cmd("t1", "s1")}) (t2 {cmd("t2", "t1")})) t2)
                  (let* ((e1 {cmd("e1", "s1")})) e1)))
           (s4 {cmd("s4", "mid")}))
      s4))''')


def procedure(root):
    return workspace(root, f'''  (defproc twice ((x Int)) -> Int
    (let* ((u {cmd("u", "x")}) (v {cmd("v", "u")})) v))
  (defworkflow run ((n Int :default 0)) -> Int
    (let* ((c1 (twice n))
           (mid {cmd("mid", "c1")})
           (c2 (twice mid)))
      c2))''')


def macro(root):
    return workspace(root, f'''  (defmacro bump (x) (+ x 0))
  (defworkflow run ((n Int :default 0)) -> Int
    (let* ((s1 {cmd("s1", "n")})
           (s2 {cmd("s2", "(bump s1)")})
           (s3 {cmd("s3", "s2")})
           (s4 {cmd("s4", "(bump s3)")}))
      s4))''')


HELPER = f'''(workflow-lisp (:language "0.1") {TARGET}
  (defmodule helper) (export twice)
  (defproc twice ((x Int)) -> Int
    (let* ((u {cmd("u", "x")}) (v {cmd("v", "u")})) v)))
'''


def imported(root):
    return workspace(root, body([SERIAL[0], ("c", "(h.twice s1)"), ("s4", cmd("s4", "c"))], "s4"),
                     imports="(import helper :as h)", extra={"helper.orc": HELPER})


OWN_TOOLS = {f"t{i}": {"stable_command": ["python", f"t{i}.py"], "closure": [f"t{i}.py"]} for i in range(1, 5)}


def own_tools(root):
    """`s1`..`s4`, each with its own script and manifest entry."""
    bindings = [(f"s{i}", cmd(f"s{i}", "n" if i == 1 else f"s{i - 1}").replace("step", f"t{i}")
                 .replace('"t.py"', f'"t{i}.py"')) for i in range(1, 5)]
    return workspace(root, body(bindings, "s4"), commands=OWN_TOOLS,
                     extra={f"t{i}.py": STEP for i in range(1, 5)})


def class_change(root):
    workspace(root, body(SERIAL, "s4"), imports="(import std/host :only (HostReply))")
    return root


S = "pipe.orc"
NEW = cmd("x", "s1")
EDITS = {
    # name: (fixture, [(file, old, new)], kept, cancelled)
    "insert a step before the first": (serial, [(S, "(let* ((s1 ", f"(let* ((x {cmd('x', 'n')})\n           (s1 ")],
                                       [], ["s1", "s2", "s3", "s4"]),
    "insert a step between s1 and s2": (serial, [(S, "           (s2 ", f"           (x {NEW})\n           (s2 ")],
                                        ["s1"], ["s2", "s3", "s4"]),
    "insert a step after the last": (serial, [(S, "      s4))", f"      {cmd('x', 's4')}))")],
                                     ["s1", "s2", "s3", "s4"], []),
    "remove s3": (serial, [(S, f"           (s3 {cmd('s3', 's2')})\n", ""), (S, cmd("s4", "s3"), cmd("s4", "s2"))],
                  ["s1", "s2"], ["s3", "s4"]),
    "reorder independent s2 and s3": (independent, [(S, f"(s2 {cmd('s2', 's1')})\n           (s3 {cmd('s3', 's1')})",
                                                     f"(s3 {cmd('s3', 's1')})\n           (s2 {cmd('s2', 's1')})")],
                                      ["s1"], ["s2", "s3", "s4"]),
    "rename a binder": (serial, [(S, "(s3 ", "(t3 "), (S, cmd("s4", "s3"), cmd("s4", "t3"))],
                        ["s1", "s2"], ["s3", "s4"]),
    "change a literal of s3": (serial, [(S, cmd("s3", "s2"), cmd("s3", "(+ s2 10)"))], ["s1", "s2"], ["s3", "s4"]),
    "rewrite an argument to an equal value": (serial, [(S, cmd("s3", "s2"), cmd("s3", "(+ s2 0)"))],
                                              ["s1", "s2", "s3", "s4"], []),
    "pure edit of the result": (serial, [(S, "      s4))", "      (+ s4 100)))")], ["s1", "s2", "s3", "s4"], []),
    "loop: insert a step in the body": (loop, [(S, "                                 (b ",
                                                f"                                 (q {cmd('q', 'a')})\n"
                                                "                                 (b ")],
                                        ["pre", "a#1"], ["b#1", "a#2", "b#2", "a#3", "b#3", "post"]),
    "loop: change an argument in the body": (loop, [(S, cmd("b", "a"), cmd("b", "(+ a 1)"))],
                                             ["pre", "a#1"], ["b#1", "a#2", "b#2", "a#3", "b#3", "post"]),
    "branch: the arm not taken": (branch, [(S, cmd("e1", "s1"), cmd("e1", "(+ s1 5)"))], ["s1", "t1", "t2", "s4"], []),
    "branch: the second step of the taken arm": (branch, [(S, cmd("t2", "t1"), cmd("t2", "(+ t1 5)"))],
                                                 ["s1", "t1"], ["t2", "s4"]),
    "procedure called from two sites: its second step": (procedure, [(S, cmd("v", "u"), cmd("v", "(+ u 1)"))],
                                                         ["c1/u"], ["c1/v", "mid", "c2/u", "c2/v"]),
    "macro used at two sites: its template": (macro, [(S, "(+ x 0)", "(+ x 1)")], ["s1"], ["s2", "s3", "s4"]),
    "imported module: the helper's second step": (imported, [("helper.orc", cmd("v", "u"), cmd("v", "(+ u 1)"))],
                                                  ["s1", "c/u"], ["c/v", "s4"]),
    "manifest: the closure list of s3": (own_tools, [("commands.json", '"closure": ["t3.py"]',
                                                      '"closure": ["t3.py", "t1.py"]')], ["s1", "s2"], ["s3", "s4"]),
    "manifest: the stable command of s3": (own_tools, [("commands.json", '["python", "t3.py"]', '["python", "-B", "t3.py"]'),
                                                       (S, '"python" "t3.py"', '"python" "-B" "t3.py"')],
                                           ["s1", "s2"], ["s3", "s4"]),
    "manifest: an unused entry": (own_tools, [("commands.json", '{"t1": ',
                                               '{"unused": {"stable_command": ["python", "u.py"], "closure": ["u.py"]}, "t1": ')],
                                  ["s1", "s2", "s3", "s4"], []),
    "a step becomes another class at the same identity": (
        class_change, [(S, cmd("s2", "s1"), '(request-input "go?" :returns String :timeout-sec 60)'),
                       (S, cmd("s3", "s2"), cmd("s3", "s1"))], ["s1"], ["s2", "s3", "s4"]),
}


def _names(run_root: Path) -> dict[str, str]:
    """Short names of committed steps: the identity's last segment; `a#1` for `a` in a loop's first iteration;
    `c1/u` for `u` in the procedure call bound to `c1`."""
    names, visits = {}, {}
    for row in fx.rows(run_root):
        if row["record"] != "committed":
            continue
        path = short(row["identity"])
        name = path.rsplit(" / ", 1)[-1]
        if "loop:" in path:
            visits[name] = visits.get(name, 0) + 1
            name = f"{name}#{visits[name]}"
        elif "=" in path.split(" / ")[0]:
            name = f"{path.split('=')[0]}/{name}"
        names[path] = name
    return names


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    """One completed run per fixture, copied per case."""
    built = {}

    def get(fixture):
        if fixture not in built:
            root = fixture(tmp_path_factory.mktemp(fixture.__name__) / "ws")
            run(root)
            built[fixture] = root
        return built[fixture]
    return get


def _copy(base: Path, tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "ws"
    shutil.copytree(base, root, symlinks=True)
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return root, run_root


@pytest.mark.parametrize("kind", EDITS)
def test_each_edit_kind_prints_its_kept_and_cancelled_steps(completed, tmp_path, kind):
    fixture, edits, kept, cancelled = EDITS[kind]
    root, run_root = _copy(completed(fixture), tmp_path)
    for name, old, new in edits:
        edit(root, old, new, name)

    plan = printed_plan(refused(root, run_root).stderr)

    names = _names(run_root)
    assert ([names[item] for item in plan["kept"]], [names[item] for item in plan["cancelled"]]) == (kept, cancelled)
    at = offsets(run_root)
    assert all(at[item] < at[other] for item in plan["kept"] for other in plan["cancelled"])
    assert plan["token"] and re.fullmatch(r"plan-[0-9a-f]{8}(-[0-9a-f]{8}){3}", plan["token"][0])


def test_a_step_of_another_class_at_the_same_identity_is_not_reused(completed, tmp_path):
    root, run_root = _copy(completed(class_change), tmp_path)
    for name, old, new in EDITS["a step becomes another class at the same identity"][1]:
        edit(root, old, new, name)

    plan = printed_plan(refused(root, run_root).stderr)

    assert plan["cut is at"] == [f"{P}s2: it is a request_input step in the edited program"]


def test_inserted_step_runs_first_and_the_cut_names_what_runs_before_it(completed, tmp_path):
    root, run_root = _copy(completed(serial), tmp_path)
    edit(root, "           (s2 ", f"           (x {NEW})\n           (s2 ")

    plan = printed_plan(refused(root, run_root).stderr)

    assert plan["runs first"] == [P + "x"]
    assert plan["cut is at"] == [f"{P}s2: the edited program runs {P}x before it"]


def test_committed_script_change_under_the_run_program_plans_the_range_invalidate_writes(completed, tmp_path):
    """The prompt-file or script row of §3: the program is unchanged, the plan is C8's from that effect."""
    root, run_root = _copy(completed(own_tools), tmp_path)
    (root / "t3.py").write_text(STEP + "# edited\n")

    done = refused(root, run_root, "effect_input_diverged")

    assert kept_and_cancelled(done.stderr) == (["s1", "s2"], ["s3", "s4"])
    assert "if accepted, this run cancels from the changed step" in done.stderr


@pytest.fixture(scope="module")
def parallel_base(tmp_path_factory):
    root = tmp_path_factory.mktemp("parallel") / "ws"
    workspace(root, f'''  (defworkflow item ((repo String)) -> Int
    (let* ((f (command-result step :argv ("python" "t.py" "f" 1) :returns Int))
           (g (command-result step :argv ("python" "t.py" "g" f) :returns Int)))
      g))
  (defworkflow run () -> Int
    (let* ((pre {cmd("pre", "0")})
           (items (list/map-effect ((repo (list "a" "b" "c"))) :max 4 :parallel 2
                    :workspace (string/concat repo "/work")
                    (call item :repo repo)))
           (post {cmd("post", "pre")}))
      post))''')
    for item in "abcd":
        (root / item / "work").mkdir(parents=True)
        (root / item / "work" / "t.py").write_text(STEP)
    run(root)
    return root


@pytest.mark.parametrize("kind", ["the step after the map", "add an item", "the second body step"])
def test_parallel_map_cut_is_one_journal_offset(parallel_base, tmp_path, kind):
    root, run_root = _copy(parallel_base, tmp_path)
    at = offsets(run_root)
    if kind == "the step after the map":
        edit(root, cmd("post", "pre"), cmd("post", "(+ pre 1)"))
    elif kind == "add an item":
        edit(root, '(list "a" "b" "c")', '(list "a" "b" "c" "d")')
    else:
        edit(root, '"g" f)', '"g" (+ f 1))')

    kept, cancelled = kept_and_cancelled(refused(root, run_root).stderr)

    cut = min(offset for name, offset in at.items() if name.endswith(" / g")) if kind == "the second body step" \
        else at["post"]
    assert (kept, cancelled) == ([name for name in at if at[name] < cut], [name for name in at if at[name] >= cut])


# ---- what the plan binds, and what it says ------------------------------------------------------------------------

def token_of(stderr: str) -> str:
    return printed_plan(stderr)["token"][0]


def test_token_is_stable_and_each_change_moves_its_field(tmp_path):
    from orchestrator.workflow.evaluated.rebase import token_difference
    root = own_tools(tmp_path / "ws")
    (root / "fail-s4").write_text("")
    (root / "dirty-s4").write_text("")                         # s4 fails after changing its own script: unproven
    run_root = run(root, code=1)
    (root / "fail-s4").unlink()
    (root / "dirty-s4").unlink()
    edit(root, cmd("s3", "s2").replace("step", "t3").replace('"t.py"', '"t3.py"'),
         cmd("s3", "(+ s2 0)").replace("step", "t3").replace('"t.py"', '"t3.py"'))
    first = token_of(refused(root, run_root).stderr)
    assert token_of(refused(root, run_root).stderr) == first

    (root / "t2.py").write_text(STEP + "# declared script of a kept commit\n")
    moved = token_of(refused(root, run_root).stderr)
    assert token_difference(first, moved) == ["cut", "sets"]
    (root / "t2.py").write_text(STEP)

    edit(root, "(+ s2 0)", "(+ s2 1)")
    again = token_of(refused(root, run_root).stderr)
    assert token_difference(first, again) == ["program", "cut", "sets"]
    edit(root, "(+ s2 1)", "(+ s2 0)")

    (root / "t4.py").write_text(STEP + "# fixed again\n")
    assert token_difference(first, token_of(refused(root, run_root).stderr)) == ["sets"]


def test_token_journal_field_moves_when_a_record_is_appended(completed, tmp_path):
    from orchestrator.workflow.evaluated.rebase import token_difference
    root, run_root = _copy(completed(own_tools), tmp_path)
    edit(root, "      s4))", "      (+ s4 1)))")
    first = token_of(refused(root, run_root).stderr)
    invalidated = cli_inprocess(root, "invalidate", run_root.name, P + "s4")      # another process's record
    assert invalidated.returncode == 0, invalidated.stderr

    assert "journal" in token_difference(first, token_of(refused(root, run_root).stderr))


def test_two_plans_of_one_journal_never_share_a_token(completed, tmp_path):
    root, run_root = _copy(completed(serial), tmp_path)
    tokens = set()
    for old, new in ((cmd("s3", "s2"), cmd("s3", "(+ s2 10)")), (cmd("s2", "s1"), cmd("s2", "(+ s1 10)"))):
        (root / S).write_text(source(body(SERIAL, "s4")).replace(old, new))
        tokens.add(token_of(refused(root, run_root).stderr))
    assert len(tokens) == 2


def test_token_binds_every_cancelled_step_also_past_the_twentieth_listed(tmp_path):
    """The sets field is the digest of the complete lists of design §6, not of the lines shown."""
    steps = [("s1", cmd("s1", "n"))] + [(f"s{i}", cmd(f"s{i}", f"s{i - 1}")) for i in range(2, 26)]
    root = workspace(tmp_path / "ws", body(steps, "s25"))
    run_root = run(root)
    edit(root, cmd("s2", "s1"), cmd("s2", "(+ s1 1)"))

    done = refused(root, run_root)

    cancelled = [row for row in fx.rows(run_root) if row["record"] == "committed"][1:]
    sets = {"cancelled": [[row["identity"], row["attempt"]] for row in cancelled], "retired": [], "asked_again": [],
            "unproven": []}
    assert token_of(done.stderr).split("-")[4] == canonical_sha256(sets).removeprefix("sha256:")[:8]


def test_plan_lists_stop_at_twenty(tmp_path):
    steps = [("s1", cmd("s1", "n"))] + [(f"s{i}", cmd(f"s{i}", f"s{i - 1}")) for i in range(2, 26)]
    root = workspace(tmp_path / "ws", body(steps, "s25"))
    run_root = run(root)
    edit(root, cmd("s2", "s1"), cmd("s2", "(+ s1 1)"))

    lines = refused(root, run_root).stderr.splitlines()

    heading = lines.index("  cancelled 24 committed steps, which run again when reached:")
    listed = lines[heading + 1:heading + 22]
    assert [line.strip() for line in listed[:20]] == [P + f"s{i}" for i in range(2, 22)]
    assert listed[20] == "    ... and 4 more"


def test_cut_earlier_than_the_edit_names_the_commit_and_what_differed(completed, tmp_path):
    """A file an earlier commit declared changed (as a cancelled later step may have written it): the cut moves to
    that commit, and the plan says which file."""
    root, run_root = _copy(completed(own_tools), tmp_path)
    edit(root, cmd("s4", "s3").replace("step", "t4").replace('"t.py"', '"t4.py"'),
         cmd("s4", "(+ s3 1)").replace("step", "t4").replace('"t.py"', '"t4.py"'))
    (root / "t2.py").write_text(STEP + "# rewritten by a later step\n")

    plan = printed_plan(refused(root, run_root).stderr)

    assert (plan["kept"], plan["cancelled"]) == (["s1"], ["s2", "s3", "s4"])
    assert plan["cut is at"][0].startswith(P + "s2: its input changed") and "t2.py" in plan["cut is at"][0]


def test_committed_divergence_prints_the_plan_beside_invalidate(completed, tmp_path):
    root, run_root = _copy(completed(own_tools), tmp_path)
    (root / "t2.py").write_text(STEP + "# edited\n")

    done = refused(root, run_root, "effect_input_diverged")

    commands = [line.strip() for line in done.stderr.splitlines() if line.startswith("    ") and " invalidate " in line]
    assert len(commands) == 1 and commands[0].endswith(f"invalidate {run_root.name} '{P}s2'")
    assert kept_and_cancelled(done.stderr) == (["s1"], ["s2", "s3", "s4"])
    flagged = refused(root, run_root, "effect_input_diverged", "--accept-changes")
    assert token_of(flagged.stderr) == token_of(done.stderr)


def test_unproven_attempt_is_listed_with_the_files_it_is_retried_with(tmp_path):
    root = own_tools(tmp_path / "ws")
    (root / "fail-s4").write_text("")
    (root / "dirty-s4").write_text("")
    run_root = run(root, code=1)
    (root / "fail-s4").unlink()
    (root / "dirty-s4").unlink()
    edit(root, "      s4))", "      (+ s4 1)))")

    plan = printed_plan(refused(root, run_root).stderr)

    assert plan["kept"] == ["s1", "s2", "s3"] and plan["cancelled"] == []
    assert plan["unfinished"] == ["s4"]
    assert "with its files as they are now" in refused(root, run_root).stderr


def test_plan_lists_cancelled_provider_cost(tmp_path):
    """A metered stand-in: each cancelled provider commit shows its attempt's cost, priced as `report` prices it."""
    from tests.test_workflow_evaluated_report_usage import ONE_CALL
    from tests.test_workflow_evaluated_spend_cap import _capped, _run, _run_id
    from tests.test_workflow_evaluated_provider_usage import _orchestrator
    root = _capped(tmp_path)
    assert _run(root).returncode == 0
    edit(root, '(message) :model "claude-haiku-5-5" :effort "high"', '(message) :model "claude-haiku-5-5" :effort "low"',
         "main.orc")
    before = tree(root)

    done = _orchestrator(root, "resume", _run_id(root))

    assert done.returncode == 2 and done.stderr.startswith("[resume_program_changed] "), done.stderr
    assert_unchanged(root, before)
    lines = done.stderr.splitlines()
    costs = [(line.strip().split("   (")[0], float(line.split()[-1].rstrip(")"))) for line in lines
             if "(provider cost USD " in line]
    assert costs == [("workflow:main::run / first", pytest.approx(ONE_CALL)),
                     ("workflow:main::run / second", pytest.approx(ONE_CALL))]


# ---- refusals (design §5) -----------------------------------------------------------------------------------------

def no_plan(stderr: str) -> str:
    """The code that says why no plan can be accepted; the refusal prints no token then."""
    assert "plan token:" not in stderr and "if accepted, " not in stderr, stderr
    (line,) = [line for line in stderr.splitlines() if line.startswith("no plan can be accepted: [")]
    return line.split("[", 1)[1].split("]", 1)[0]


REFUSALS = {
    "entry workflow": ("resume_program_changed", [(S, "(export run)", "(export main)"),
                                                  (S, "(defworkflow run ", "(defworkflow main ")]),
    "target": ("resume_program_changed", [(S, TARGET, '(:target-dsl "2.39")')]),
    "an added entry input": ("resume_inputs_changed", [(S, "((n Int :default 0))", "((n Int :default 0) (m Int :default 1))")]),
    "an unpinned bare interpreter": ("resume_program_changed", [(S, "      s4))", f"      {cmd('x', 's4', 'shell')}))")]),
    "a pure fault under the edited program": ("pure_expr_division_by_zero", [(S, "      s4))", "      (int/div s4 (- n n))))")]),
}


@pytest.mark.parametrize("case", REFUSALS)
def test_each_refusal_of_section_5_replaces_the_plan_with_its_reason(completed, tmp_path, case):
    code, edits = REFUSALS[case]
    root, run_root = _copy(completed(serial), tmp_path)
    for name, old, new in edits:
        edit(root, old, new, name)

    assert no_plan(refused(root, run_root).stderr) == code


def test_plan_refusal_changes_no_byte_and_keeps_code_and_exit(completed, tmp_path):
    """The plan cannot be shown (its stored program is corrupt): the refusal is still step 7's, with exit 2."""
    root, run_root = _copy(completed(serial), tmp_path)
    edit(root, "      s4))", "      (+ s4 1)))")
    (run_root / "closed_program.json").write_text("corrupt")

    done = refused(root, run_root)

    assert no_plan(done.stderr) == "memo_inconsistent"


def test_a_host_request_whose_recorded_identity_was_altered_refuses_and_is_not_cancelled(host_base, tmp_path):
    """Corruption is not "not reusable": a stored request whose ID does not belong to this run stays a refusal."""
    root, run_root = _copy(host_base, tmp_path)
    (request,) = [row["host_request"] for row in fx.rows(run_root) if "host_request" in row]
    text = (run_root / "memo.jsonl").read_text().replace(request["request_id"], "sha256:" + "0" * 64)
    rows = [json.loads(line) for line in text.splitlines()]
    for row in rows:              # a well-formed request whose ID is not this run's; every digest over it recomputed
        if "host_request" in row:
            row["host_request"]["payload_digest"] = canonical_sha256(
                {k: v for k, v in row["host_request"].items() if k != "payload_digest"})
    (run_root / "memo.jsonl").write_bytes(b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
                                                   + b"\n" for row in rows))
    edit(root, cmd("s3", "s1"), cmd("s3", "(+ s1 1)"))

    assert no_plan(refused(root, run_root).stderr) == "memo_inconsistent"


ONCE = '(command-result once :argv ("python" "t.py" "s3" s2) :returns Int)'


def repeat_workspace(root: Path, *, declared: bool = True, failing: bool = False) -> tuple[Path, Path]:
    once = {"stable_command": ["python", "t.py"], "closure": ["t.py"], **({"must_not_repeat": True} if declared else {})}
    workspace(root, body([*SERIAL[:2], ("s3", ONCE), SERIAL[3]], "s4"), commands={**COMMANDS, "once": once})
    if failing:
        (root / "fail-s3").write_text("")
    run_root = run(root, code=1 if failing else 0)
    (root / "fail-s3").unlink(missing_ok=True)
    return root, run_root


def manifest(root: Path, declared: bool) -> None:
    data = json.loads((root / "commands.json").read_text())
    data["once"].pop("must_not_repeat", None)
    data["once"].update({"must_not_repeat": True} if declared else {})
    (root / "commands.json").write_text(json.dumps(data))


def test_committed_must_not_repeat_step_in_the_cancelled_range_prints_invalidate(tmp_path):
    root, run_root = repeat_workspace(tmp_path / "ws")
    edit(root, cmd("s2", "s1"), cmd("s2", "(+ s1 1)"))

    done = refused(root, run_root)

    assert no_plan(done.stderr) == "lexical_restore_pending_effect_unsafe"
    (invalidate,) = [line.strip() for line in done.stderr.splitlines() if line.startswith("    ") and "invalidate" in line]
    assert invalidate.endswith(f"invalidate {run_root.name} '{P}s3'")
    words = shlex.split(invalidate)
    assert cli_inprocess(root, *words[words.index("invalidate"):]).returncode == 0
    assert kept_and_cancelled(refused(root, run_root).stderr) == (["s1"], ["s2"])


def test_must_not_repeat_declared_only_by_the_edit_refuses(tmp_path):
    root, run_root = repeat_workspace(tmp_path / "ws", declared=False)
    manifest(root, True)
    edit(root, cmd("s2", "s1"), cmd("s2", "(+ s1 1)"))

    assert no_plan(refused(root, run_root).stderr) == "lexical_restore_pending_effect_unsafe"


@pytest.mark.parametrize("change", ["rename the step", "drop the declaration"])
def test_unfinished_must_not_repeat_attempt_refuses_after_a_rename_or_a_dropped_declaration(tmp_path, change):
    root, run_root = repeat_workspace(tmp_path / "ws", failing=True)
    if change == "rename the step":
        edit(root, "(s3 (command-result once", "(t3 (command-result once")
        edit(root, cmd("s4", "s3"), cmd("s4", "t3"))
    else:
        manifest(root, False)

    assert no_plan(refused(root, run_root).stderr) == "lexical_restore_pending_effect_unsafe"


# ---- host input ----------------------------------------------------------------------------------------------------

HOST = body([("s1", cmd("s1", "n")), ("reply", '(request-input "Approve?" :returns Approval :timeout-sec 3600)'),
             ("s3", cmd("s3", "s1"))],
            "(match reply ((ANSWERED answer) s3) ((CANCELLED _) 0) ((EXPIRED _) 0))")
HOST_IMPORTS = "(import std/host :only (HostReply))"


def host_workspace(root: Path) -> tuple[Path, Path, str]:
    workspace(root, "  (defenum Approval APPROVED DENIED)\n" + HOST, imports=HOST_IMPORTS)
    run_root = run(root)
    request = json.loads(cli_inprocess(root, "input", "get", run_root.name).stdout)["request_id"]
    return root, run_root, request


@pytest.fixture(scope="module")
def host_base(tmp_path_factory):
    root, run_root, request = host_workspace(tmp_path_factory.mktemp("host") / "ws")
    answered = cli_inprocess(root, "input", "answer", run_root.name, request, "--value", '"APPROVED"', "--by", "t")
    assert answered.returncode == 0, answered.stderr
    assert cli_inprocess(root, "resume", run_root.name).returncode == 0
    return root


def test_host_reply_before_the_cut_is_kept_and_one_after_is_asked_again(host_base, tmp_path):
    root, run_root = _copy(host_base, tmp_path)
    edit(root, cmd("s3", "s1"), cmd("s3", "(+ s1 1)"))
    after = printed_plan(refused(root, run_root).stderr)
    edit(root, cmd("s3", "(+ s1 1)"), cmd("s3", "s1"))
    edit(root, cmd("s1", "n"), cmd("s1", "(+ n 1)"))
    before = printed_plan(refused(root, run_root).stderr)

    assert (after["kept"], after["cancelled"], after["asked again"]) == (["s1", "reply"], ["s3"], ["none"])
    assert (before["kept"], before["cancelled"], before["asked again"]) == ([], ["s1", "reply", "s3"], [P + "reply"])


def test_input_answer_under_an_unaccepted_edit_refuses_and_says_why(tmp_path):
    root, run_root, request = host_workspace(tmp_path / "ws")
    edit(root, cmd("s3", "s1"), cmd("s3", "(+ s1 1)"))
    before = tree(root)

    answered = cli_inprocess(root, "input", "answer", run_root.name, request, "--value", '"APPROVED"', "--by", "t")
    plan = refused(root, run_root).stderr

    assert answered.returncode == 2 and "[resume_program_changed]" in answered.stderr, answered.stderr
    assert "until the edit is accepted or the source restored" in answered.stderr
    assert_unchanged(root, before)
    assert f"  question {P}reply cannot be answered until the edit is accepted or the source restored" in plan


# ---- the library entry ---------------------------------------------------------------------------------------------

def test_plan_resume_returns_the_printed_plan_and_writes_nothing(completed, tmp_path):
    from orchestrator.workflow.evaluated.rebase import plan_resume
    root, run_root = _copy(completed(serial), tmp_path)
    edit(root, "           (s2 ", f"           (x {NEW})\n           (s2 ")
    printed = printed_plan(refused(root, run_root).stderr)
    before = tree(root)

    plan = plan_resume(run_root, root)

    assert_unchanged(root, before)
    assert (plan.record, plan.token) == ("rebased", printed["token"][0])
    assert [short(entry.data["identity"]) for entry in plan.cancelled] == printed["cancelled"]
    assert plan.cut == offsets(run_root)["s2"] and plan.runs_first == (P + "x",)


# ---- coordinators: run references, agent turns, phased providers (design §5, claim 3) ------------------------------

def cli(root: Path, *args: str, env: dict[str, str] | None = None):
    """A separate process, as the coordinators' stand-ins and kill points need."""
    return fx.cli(root, *args, env=env)


def refused_process(root: Path, run_root: Path, env: dict[str, str] | None = None, code: str = "resume_program_changed"):
    before = tree(root)
    done = cli(root, "resume", run_root.name, env=env)
    assert done.returncode == 2 and done.stderr.startswith(f"[{code}] "), done.stderr
    assert_unchanged(root, before)
    return done


def agent_run(root: Path) -> tuple[Path, dict[str, str]]:
    from tests.test_workflow_evaluated_declaration_resume import _fresh_run
    return _fresh_run("agent_turns_committed", root)


def test_committed_agent_turns_before_the_cut_are_kept(tmp_path):
    root = tmp_path / "ws"
    run_root, env = agent_run(root)
    edit(root, "      b2)))", "      (let* ((a3 (provider-result designer :prompt (draft :task a2.text) :timeout-sec 60))) b2))))",
         "main.orc")

    plan = printed_plan(refused_process(root, run_root, env).stderr)

    assert plan["cancelled"] == [] and len(plan["kept"]) == 6
    assert plan["runs first"] == ["workflow:main::run / a3"]
    assert not (root / "requests.jsonl").exists()                  # no stand-in was called to plan


def test_committed_agent_turn_after_the_cut_refuses(tmp_path):
    root = tmp_path / "ws"
    run_root, env = agent_run(root)
    edit(root, '"Revise: {text} {notes}"', '"Revise now: {text} {notes}"', "main.orc")

    assert no_plan(refused_process(root, run_root, env).stderr) == "invalidate_coordinator_committed"


def pending_turn_run(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """`c` committed, then the agent turn `b1` killed after its native turn completed, before `committed`."""
    from tests.agent_session_shims import FAKE_CODEX, closed_path
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT, _stopped
    from tests.test_workflow_evaluated_edit_resume_baseline import _shim
    root = workspace(tmp_path / "ws", '''  (defrecord Feedback (notes List[String]))
  (defprompt review (:fills (text :text)) -> Feedback "Review: {text}")
  (defworkflow run ((task String)) -> Int
    (let* ((reviewer (agent providers.codex :model "reviewer" :effort "high"))
           (c (command-result step :argv ("python" "t.py" "c" 0) :returns Int))
           (b1 (provider-result reviewer :prompt (review :text task) :timeout-sec 60)))
      c))''', extra={"providers.json": '{"providers.codex": "codex"}'})
    _shim(root / "bin" / "codex", FAKE_CODEX)
    env = {"PATH": closed_path(root / "bin"), "CODEX_HOME": str(root / "codex"),
           "AGENT_SHIM_PLAN": json.dumps({"codex": [{"mode": "success", "result": {"notes": ["n"]}}]})}
    _stopped(root, STOP_AFTER_RECEIPT, {**env, "STOP_AT_COMPLETION": "completed", "STOP_TURN": "/ b1"},
             "run", *RUN_ARGS, "--source-root", ".", "--provider-externs-file", "providers.json", "--input", "task=t")
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return root, run_root, env


@pytest.mark.parametrize("edited", ["the step before it", "its own prompt"])
def test_pending_agent_turn_at_or_after_the_cut_refuses(tmp_path, edited):
    """Before it: the cut lies before the pending turn. Its prompt: reached next, but not kept (comparison point 3)."""
    root, run_root, env = pending_turn_run(tmp_path)
    if edited == "the step before it":
        edit(root, '"c" 0)', '"c" 1)')
    else:
        edit(root, '"Review: {text}"', '"Review again: {text}"')

    assert no_plan(refused_process(root, run_root, env).stderr) == "invalidate_agent_session_advanced"


def test_pending_agent_turn_reached_next_with_its_input_unchanged_is_kept(tmp_path):
    root, run_root, env = pending_turn_run(tmp_path)
    edit(root, "      c))", "      (+ c 1)))")

    plan = printed_plan(refused_process(root, run_root, env).stderr)

    assert (plan["cancelled"], plan["retired"], plan["runs first"]) == ([], [], ["workflow:pipe::run / b1"])


def test_pre_change_pending_agent_turn_is_kept_under_an_edit_that_moves_positions():
    """Comparison point 3: the pending `b1` of a run recorded under the earlier `declaration` rule is kept, because
    its digest is compared under the rule it was written with, over its node in the program that wrote it (and so
    are the committed turns before it, at point 1)."""
    from tests.test_workflow_evaluated_edit_resume_baseline import _recorded, _recorded_workspace
    with _recorded_workspace("agent_turn_pending") as root:
        run_root, env = _recorded("agent_turn_pending", root)
        edit(root, "  (defworkflow run", ";; an edit above every turn moves their source positions\n  (defworkflow run",
             "main.orc")
        edit(root, "           (b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60)))\n      b2",
             "           (b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60))\n"
             "           (last b2))\n      last", "main.orc")

        plan = printed_plan(refused_process(root, run_root, {**env, "AGENT_SHIM_PLAN": "{}"}).stderr)

        assert (plan["cancelled"], plan.get("retired")) == ([], [])
        assert "workflow:main::run / b1" in plan["runs first"][0]


def run_ref_run(root: Path, *, pending: bool = False) -> tuple[Path, Path, Path]:
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECORD, _stopped
    from tests.test_workflow_evaluated_run_ref import _public_fixture
    root.mkdir(parents=True)
    run_body = lambda call: (f'(let* ((a {cmd("a", "0")}) (attempt {call}) (b {cmd("b", "a")})) attempt.value)')
    parent, controller, refs = _public_fixture(root, body=run_body)
    (parent / "t.py").write_text(STEP)
    (parent / "commands.json").write_text(json.dumps(COMMANDS))
    args = ("run", "controller.orc", "--run-ref-root", str(refs), "--command-boundaries-file", "commands.json")
    if pending:
        _stopped(parent, STOP_AFTER_RECORD, {"STOP_RECORD": "started", "STOP_TURN": "/ attempt"}, *args)
    else:
        assert cli(parent, *args).returncode == 0
    (run_root,) = (parent / ".orchestrate" / "runs").iterdir()
    return parent, run_root, refs


def test_committed_run_reference_before_the_cut_is_kept_and_one_after_refuses(tmp_path):
    parent, run_root, refs = run_ref_run(tmp_path / "r")
    source = (parent / "controller.orc").read_text()
    edit(parent, cmd("b", "a"), cmd("b", "(+ a 1)"), "controller.orc")
    after = printed_plan(refused_process(parent, run_root).stderr)
    (parent / "controller.orc").write_text(source.replace(cmd("a", "0"), cmd("a", "1")))
    before = refused_process(parent, run_root).stderr

    assert [item.rsplit(" / ", 1)[-1] for item in after["kept"]] == ["a", "attempt"]
    assert [item.rsplit(" / ", 1)[-1] for item in after["cancelled"]] == ["b"]
    assert no_plan(before) == "invalidate_coordinator_committed"


def test_pending_run_reference_that_is_not_kept_refuses(tmp_path):
    parent, run_root, _refs = run_ref_run(tmp_path / "r", pending=True)
    edit(parent, "(attempt (run-ref", f"(x {cmd('x', 'a')}) (attempt (run-ref", "controller.orc")

    assert no_plan(refused_process(parent, run_root).stderr) == "resume_program_changed"


def test_committed_phased_provider_after_the_cut_refuses_and_one_before_it_is_kept(tmp_path):
    from tests.test_workflow_evaluated_edit_resume_baseline import _recorded
    run_root, env = _recorded("phased_committed", tmp_path)
    source = tmp_path / "tests/fixtures/phased_239/main.orc"
    text = source.read_text()
    source.write_text(text.replace('review.approved)', 'review.approved "extra")'))
    kept = printed_plan(refused_process(tmp_path, run_root, env).stderr)
    source.write_text(text.replace(':model "bound-model"', ':model "other-model"'))

    assert (kept["kept"], kept["cancelled"], kept["runs first"]) == (["review"], [], ["workflow:main::run / after"])
    assert no_plan(refused_process(tmp_path, run_root, env).stderr) == "invalidate_coordinator_committed"


@pytest.mark.parametrize("change", ["an edited program", "a committed step's changed script"])
def test_confined_child_with_a_commit_after_the_cut_refuses(world, monkeypatch, change):
    """A confined run-reference child that committed an effect, its parent attempt after the cut: K8 holds."""
    import tests.test_workflow_run_ref_confined_child as fixture
    from tests.test_workflow_run_ref_confined_recovery import InjectedControllerCrash
    from orchestrator.workflow.evaluated import attempts, runtime as child_runtime
    original_write, original_append = fixture._write, child_runtime.append_record

    def write(world, **kwargs):
        original_write(world, **kwargs)
        parent = world["parent"]
        text = (parent / "controller.orc").read_text().replace(
            "(let* ((child (run-ref", '(let* ((pre (command-result pre :argv ("sh" "pre.sh") :returns Int)) (child (run-ref')
        (parent / "controller.orc").write_text(text)
        (parent / "pre.sh").write_text('echo 1 > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n')
        boundaries = json.loads((parent / "boundaries.json").read_text())
        boundaries["pre"] = dict(stable_command=["sh", "pre.sh"], closure=["pre.sh"])
        (parent / "boundaries.json").write_text(json.dumps(boundaries))

    def append(path, record, **kwargs):
        result = original_append(path, record, **kwargs)
        authority = kwargs.get("checked_authority")
        if authority is not None and authority.confined and record["record"] == "committed":
            raise InjectedControllerCrash()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(fixture, "_write", write)
        patch.setattr(child_runtime, "append_record", append)
        patch.setattr(attempts, "append_record", append)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world)
    parent = world["parent"]
    (run_root,) = (parent / ".orchestrate" / "runs").iterdir()
    if change == "an edited program":
        edit(parent, '("sh" "pre.sh")', '("sh" "pre.sh" "again")', "controller.orc")
    else:
        (parent / "pre.sh").write_text('echo 1 > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH" # edited\n')
    before = tree(parent)

    done = cli_inprocess(parent, "resume", run_root.name, "--run-ref-root", str(world["refs"]))

    assert done.returncode == 2, done.stderr
    assert no_plan(done.stderr) == "invalidate_coordinator_committed"
    assert_unchanged(parent, before)


# ---- review fixes: the library entry, an edited stable command, corruption, and the gaps the mutations showed ------

def test_plan_resume_plans_a_run_with_a_parallel_map_without_a_given_file_owner(parallel_base, tmp_path):
    from orchestrator.workflow.evaluated.rebase import plan_resume
    root, run_root = _copy(parallel_base, tmp_path)
    edit(root, cmd("post", "pre"), cmd("post", "(+ pre 1)"))
    before = tree(root)

    plan = plan_resume(run_root, root)

    assert [short(entry.data["identity"]) for entry in plan.cancelled] == ["post"]
    assert_unchanged(root, before)


def test_plan_resume_plans_a_run_whose_committed_run_reference_is_reused(tmp_path):
    from orchestrator.workflow.evaluated.rebase import plan_resume
    parent, run_root, _refs = run_ref_run(tmp_path / "r")
    edit(parent, cmd("b", "a"), cmd("b", "(+ a 1)"), "controller.orc")
    before = tree(parent)

    plan = plan_resume(run_root, parent)

    assert [entry.data["identity"].rsplit(" / ", 1)[-1] for entry in plan.kept] == ["a", "attempt"]
    assert_unchanged(parent, before)


def test_fresh_run_command_printed_for_a_run_reference_run_names_its_root_and_runs(tmp_path):
    parent, run_root, refs = run_ref_run(tmp_path / "r")
    edit(parent, cmd("b", "a"), cmd("b", "(+ a 1)"), "controller.orc")

    (fresh,) = [line.strip() for line in refused_process(parent, run_root).stderr.splitlines()
                if line.startswith("    ") and " run " in line]

    words = shlex.split(fresh)
    assert words[words.index("--run-ref-root") + 1] == str(refs)
    assert cli(parent, *words[words.index("run"):]).returncode == 0


@pytest.mark.parametrize("closure", ["unchanged", "changed"])
def test_a_failed_steps_stable_command_fixed_in_the_manifest_is_planned_as_its_retry(tmp_path, closure):
    """The author fixes the failed `s3` by its manifest's stable command (and argv): its recorded file evidence no
    longer binds, so its files are those of the new command; a clean failure admits them, an unproven one is listed."""
    root = own_tools(tmp_path / "ws")
    (root / "fail-s3").write_text("")
    if closure == "changed":
        (root / "dirty-s3").write_text("")
    run_root = run(root, code=1)
    for marker in ("fail-s3", "dirty-s3"):
        (root / marker).unlink(missing_ok=True)
    edit(root, '["python", "t3.py"]', '["python", "-B", "t3.py"]', "commands.json")
    edit(root, '"python" "t3.py"', '"python" "-B" "t3.py"')

    plan = printed_plan(refused(root, run_root).stderr)

    assert (plan["kept"], plan["cancelled"], plan["runs first"]) == (["s1", "s2"], [], [P + "s3"])
    assert plan["unfinished"] == ([] if closure == "unchanged" else ["s3"])


def test_a_committed_steps_stable_command_that_no_longer_binds_its_evidence_cancels_from_it(tmp_path):
    commands = {**COMMANDS, "d": {"stable_command": ["./d.sh"], "closure": ["d.sh"]}}
    text = body([("s1", cmd("s1", "n", "shell")), ("s2", '(command-result d :argv ("./d.sh" "s2" s1) :returns Int)'),
                 ("s3", cmd("s3", "s2"))], "s3")
    root = workspace(tmp_path / "ws", text, commands=commands,
                     extra={"d.sh": '#!/bin/sh\necho $(( $2 + 1 )) > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n'})
    (root / "d.sh").chmod(0o700)
    run_root = run(root)
    edit(root, '"stable_command": ["./d.sh"]', '"stable_command": ["sh", "./d.sh"]', "commands.json")
    edit(root, '("./d.sh" "s2" s1)', '("sh" "./d.sh" "s2" s1)')

    plan = printed_plan(refused(root, run_root).stderr)

    assert (plan["kept"], plan["cancelled"]) == (["s1"], ["s2", "s3"])
    assert plan["cut is at"][0].startswith(P + "s2: its input changed")


@pytest.mark.parametrize("field", ["depends_on", "value"])
def test_a_corrupt_committed_row_refuses_and_is_never_cancelled(completed, tmp_path, field):
    """A committed row that no replay under the program that wrote it accepts is corruption, not "not reusable"."""
    root, run_root = _copy(completed(serial), tmp_path)
    rows = fx.rows(run_root)
    (s4,) = [row for row in rows if row["record"] == "committed" and row["identity"] == P + "s4"]
    s4[field] = [] if field == "depends_on" else "four"
    (run_root / "memo.jsonl").write_bytes(b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
                                                   + b"\n" for row in rows))
    edit(root, "      s4))", "      (+ s4 1)))")

    assert no_plan(refused(root, run_root).stderr) == "memo_inconsistent"


def test_a_commit_whose_value_no_longer_fits_the_edited_result_type_is_cancelled(completed, tmp_path):
    root, run_root = _copy(completed(serial), tmp_path)
    edit(root, cmd("s2", "s1"), cmd("s2", "s1").replace(":returns Int", ":returns String"))

    plan = printed_plan(refused(root, run_root).stderr)

    assert (plan["kept"], plan["cancelled"]) == (["s1"], ["s2", "s3", "s4"])
    assert plan["cut is at"] == [f"{P}s2: its stored value does not fit the edited step's result type"]


def test_a_retired_pending_request_is_asked_again(tmp_path):
    root, run_root, _request = host_workspace(tmp_path / "ws")
    edit(root, cmd("s1", "n"), cmd("s1", "(+ n 1)"))

    plan = printed_plan(refused(root, run_root).stderr)

    assert (plan["cancelled"], plan["retired"], plan["asked again"]) == (["s1"], ["reply"], [P + "reply"])


APPROVE = '  (defprompt approve (:fills (number :value Int)) -> Approval "Approve {number}?")\n'
PROMPTED = body([("s1", cmd("s1", "n")), ("reply", "(request-input (approve :number s1) :returns Approval)"),
                 ("s3", cmd("s3", "s1"))], "(match reply ((ANSWERED answer) s3) ((CANCELLED _) 0) ((EXPIRED _) 0))")


def test_a_pending_request_whose_prompt_changed_is_retired_and_asked_again(tmp_path):
    """Reached next and of its class, but its question differs from its `started` input: not kept."""
    root = workspace(tmp_path / "ws", "  (defenum Approval APPROVED DENIED)\n" + APPROVE + PROMPTED, imports=HOST_IMPORTS)
    run_root = run(root)
    edit(root, '"Approve {number}?"', '"Approve {number} now?"')

    plan = printed_plan(refused(root, run_root).stderr)

    assert (plan["kept"], plan["retired"], plan["asked again"]) == (["s1"], ["reply"], [P + "reply"])


def test_token_journal_field_binds_the_last_record_not_only_the_length(completed, tmp_path):
    from orchestrator.workflow.evaluated.rebase import token_difference
    root, run_root = _copy(completed(serial), tmp_path)
    edit(root, "      s4))", "      (+ s4 1)))")
    first = token_of(refused(root, run_root).stderr)
    journal = run_root / "memo.jsonl"
    last = b'{"outcome":"completed","record":"terminal","value":4}\n'
    assert journal.read_bytes().endswith(last)
    journal.write_bytes(journal.read_bytes()[:-len(last)] + last.replace(b":4}", b":5}"))     # the same length

    assert token_difference(first, token_of(refused(root, run_root).stderr)) == ["journal"]


def test_pending_phased_attempt_that_is_not_kept_refuses():
    from tests.test_workflow_evaluated_edit_resume_baseline import _recorded, _recorded_workspace
    with _recorded_workspace("phased_pending") as root:
        run_root, env = _recorded("phased_pending", root)
        edit(root, ':model "bound-model"', ':model "other-model"', "tests/fixtures/phased_239/main.orc")

        assert no_plan(refused_process(root, run_root, env).stderr) == "resume_program_changed"
