"""The compile check of mechanical mutants: each one builds, is refused with codes, or crashes.

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md (Task T2).

A seed directory holds one `NAME.orc` per program, whose entry is `NAME::run`, beside
`providers.json` and `commands.json` when the programs use them. The directory is copied once to a
temporary work directory, which is removed afterwards; each mutant is written over its program
there and compiled in process with `prepare_closed_program_bundle`, which writes nothing. The seed
directory is never written. The compile check runs nothing: no workflow, provider or command is
started. The module loads none of the runtime's dispatch entry points at import; the reuse figures
below start one process per scenario (the seed's own stand-in run), and planning (`plan_resume`)
loads the `run` command, the evaluated runtime and the effect dispatcher without calling anything
in them. Sources are read as UTF-8 with `\\r\\n`
and `\\r` turned into `\\n` before any operator or digest sees them.

An outcome is classified by `build_outcome` of `tests/workflow_lisp_closed_program_helpers.py`, the
classifier of the defect backlog's test module, so one crash has one key in both. A crash's key is
`crash_signature`'s pair (the exception class and a function under `orchestrator/`) without the
kind: a `compiler_defect` and an exception that left the build uncaught at one place share a key.
A refusal that holds a code that is or starts with `compiler_defect`, alone or beside other codes,
is a crash too (the mutant "ends in `compiler_defect`", roadmap item R3): its key is the crash key
of the first such diagnostic's cause, or that diagnostic's code when it carries no cause. A key is
a location, not a defect, and this module reads no list of known defects: every crash is reported,
per key, with its count, its operators and its shortest mutant.

The readout, a JSON object (Task T3 reads it):

- `sample`: what was drawn: `programs` (in name order), `operators` (in `OPERATORS` order), `cap`,
  `number`, `python` (the version that drew it) and `mutants` (how many were drawn).
- `operators`: per operator drawn, in `OPERATORS` order: `mutants`; `compiles`; `refused`, the
  count per refusal, keyed by its codes joined by a space; `crash_keys`, the count per crash key,
  keyed by the key's parts joined by a space; `lines_50_or_more`, the mutants of 50 lines or more
  (counted beside the outcomes, not among them). `compiles`, the `refused` counts and the
  `crash_keys` counts add up to `mutants`.
- `distinct_digests`: the number of distinct program digests among the mutants that compile.
- `equal_to_seed`: the mutants that compile to their seed's digest.
- `crashes`: one record per crash key, in key order: `key` (the class and the place, or the one
  code); `kinds` (`crash`, `traceback`); `mutants`; `operators`; `pairs`, each `[operator,
  program]`; `smallest`, the shortest crashing mutant as `{name, source}`, `name` being
  `program/operator/params` and `source` its whole text; `cause`, the first line of the smallest
  mutant's cause; `causes`, every distinct first line under the key with its count.

Reuse figures (Task T3): how much of a completed run of a seed `resume` would keep if the program
were replaced by each mutant. One stand-in run of the seed is recorded per program and scenario
(`recorded_run`: the fake `claude` of `tests/agent_session_shims.py` on `closed_path`, nothing
spent); then each sampled mutant that compiled in the compile check, with a digest other than the
seed's, is written over the program and `plan_resume`, the read-only library entry, gives its plan
(`plan_outcome`). The only compile left in this step is the one inside `plan_resume`. A mutant is
never run and `resume` is never called. With `--standin`, the readout gains the key `reuse`
(absent otherwise), a list with one section per program and scenario holding:

  `program`, `scenario`; `steps`, the committed rows of the run's journal; `provider_calls`, the
  lines of the fake's request log, one per invocation that logged a request; `priced_usd`, the run's
  priced cost, null when its calls report no usage (every stand-in run), so a share of priced tokens
  kept is not given and never shown as zero, and `priced_reason`, why it is null (null when it is
  not); `operators`, per operator in `OPERATORS` order with a mutant that compiled: `measured`
  (mutants that compiled), `same_program` (their digest is the seed's: not planned), `plans`,
  `steps_kept` and `calls_kept` (`min`, `median`, `max` over the plans, of `steps` and of
  `provider_calls`; null without a plan), `no_plan` (count per refusal code: a coded refusal is
  counted, never averaged in) and `sites`, the same figures per site (the role, loop, `let*`
  binding, prompt or `graft` target the params name).

How a provider call is counted. `calls_kept` is `provider_calls` less `len(plan.costs)`, the
cancelled committed journal entries of class `provider`, `provider_phased` or `agent_turn`. Every
logged attempt counts in the total and only committed effects are subtracted, so the recorded run
is refused (exit 2) unless its request-log lines equal its committed provider-class effects: a run
with a retry or an uncommitted attempt is not clean. On a clean run a call is one committed
provider-class effect: a call inside a loop counts once per iteration (each iteration is its own
commit), a call inside a map once per item, an agent turn counts, and opening or closing an agent
session is not provider class and logs no request. A completed run has no pending start to retire.

The stand-in file (`--standin`) is `{"inputs": {...}, "files": {...}, "answers": {program:
{scenario: [answer, ...]}}}`: the run's inputs (`repo` is set to the workspace when the entry
declares that input), the workspace's files (the token `{python}` in a file's text becomes the
running interpreter), and the fake's answers in call order (`tests/agent_session_shims.py`'s plan
steps).

Command: `python -m experiments.mutants.check SEED_DIR --programs a,b [--operators x,y] [--cap 100]
[--number 0] [--out PATH] [--standin FILE.json [--scenarios a,b]]`. It prints a table and every
crash record, writes the readout (by default `experiments/mutants/readout.json`), and exits 1 when
any mutant crashed, else 0; an exception from the planner that carries no code also ends the
command with exit 1, a traceback and no readout. Every problem with its input exits 2 with one line
and writes no readout, before any mutant compiles: a missing seed directory or program file, an
unreadable or undecodable one, no program, an unknown operator, a negative cap, an empty sample, a
model or effort literal outside the closed sets, a seed that does not build, an `--out` whose
directory is missing or not writable, an `--out` that is an existing file of a git working tree
other than the default readout, `--scenarios` without `--standin`, a stand-in file that is
unreadable, lacks a key or whose `answers` is not an object of objects, a named scenario that no
named program has, no scenario to run, and a stand-in run that times out, does not exit 0 (the
line gives its cause), leaves answers unused or is not clean.
"""

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path

from experiments.mutants.operators import OPERATORS, Mutation, apply, entry_inputs, sample
from orchestrator.providers.pricing import load_price_table
from orchestrator.providers.usage import summed_usage
from orchestrator.workflow.evaluated.rebase import _PROVIDER_CLASSES as PROVIDER_CLASSES  # what `plan.costs` counts
from orchestrator.workflow.evaluated.rebase import plan_resume
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle
from tests.agent_session_shims import FAKE_CLAUDE, closed_path
from tests.workflow_lisp_closed_program_helpers import build_outcome, crash_signature

ROOT = Path(__file__).resolve().parents[2]
READOUT = Path(__file__).with_name("readout.json")
CRASH_KINDS = ("crash", "traceback")
DEFECT = "compiler_defect"
LONG = 50  # lines: a mutant this long is over the seeds' line limit
PROG = "python -m experiments.mutants.check"
STANDIN_TIMEOUT = 600  # seconds for one stand-in run of a seed; 4 to 19 s measured (plan, probe P11)


def read_source(path: Path) -> str:
    """A program's text: UTF-8, line ends normalised to `\\n`."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _first_line(text: object) -> str:
    return next(iter(str(text).splitlines()), "")


class _Witness:
    """Keeps the exception that leaves its block and lets it go on, for `build_outcome` to classify."""

    error: BaseException | None = None

    def __enter__(self):
        return self

    def __exit__(self, kind, error, trace):
        self.error = error


def _request(work: Path, program: str) -> FrontendBuildRequest:
    providers, commands = work / "providers.json", work / "commands.json"
    return FrontendBuildRequest(
        source_path=work / f"{program}.orc", source_roots=(work,), entry_workflow=f"{program}::run",
        provider_externs_path=providers if providers.exists() else None,
        command_boundaries_path=commands if commands.exists() else None, workspace_root=work)


def _defect(error) -> tuple[tuple, str] | None:
    """For a refusal: the crash it holds, when a diagnostic's code is or starts with `compiler_defect`, else None."""
    for diagnostic in error.diagnostics:
        if diagnostic.code.startswith(DEFECT):
            if diagnostic.cause is None:
                return ("crash", diagnostic.code), _first_line(diagnostic.message)
            return ("crash", *crash_signature(diagnostic.cause)), _first_line(diagnostic.cause)
    return None


def _observed(work: Path, program: str) -> tuple[tuple, str]:
    """The outcome of `outcome`, and for a crash the first line of its cause's message."""
    digest, witness = [], _Witness()

    def build():
        with witness:
            digest.append(prepare_closed_program_bundle(_request(work, program)).program.digest)

    result = build_outcome(build)
    if result == ("builds",):
        return ("compiles", digest[0]), ""
    if result[0] == "refused":
        return _defect(witness.error) or (result, "")
    cause = witness.error.diagnostics[0].cause if result[0] == "crash" else witness.error
    return result, _first_line(cause)


def outcome(work: Path, program: str) -> tuple:
    """The compile of `work/PROGRAM.orc` as it stands: `("compiles", digest)`; `("refused", *codes)`;
    `("crash", class, where)` for a `compiler_defect`, or `("crash", code)` for a refusal holding a
    `compiler_defect` code without a cause; `("traceback", class, where)` for an exception that left
    the build. Writes nothing."""
    return _observed(work, program)[0]


def _counts(results: list[dict], names: Sequence[str]) -> dict:
    """The readout's `operators`."""
    rows = {name: {"mutants": 0, "compiles": 0, "refused": Counter(), "crash_keys": Counter(),
                   f"lines_{LONG}_or_more": 0} for name in OPERATORS if name in names}
    for result in results:
        row, kind = rows[result["operator"]], result["outcome"][0]
        row["mutants"] += 1
        row[f"lines_{LONG}_or_more"] += result["lines"] >= LONG
        if kind == "compiles":
            row["compiles"] += 1
        elif kind == "refused":
            row["refused"][" ".join(result["outcome"][1:])] += 1
        else:
            row["crash_keys"][" ".join(result["outcome"][1:])] += 1
    return {name: {**row, "refused": dict(row["refused"]), "crash_keys": dict(row["crash_keys"])}
            for name, row in rows.items()}


def _crashes(results: list[dict]) -> list[dict]:
    """The readout's `crashes`."""
    records: dict[tuple, dict] = {}
    for result in (result for result in results if result["outcome"][0] in CRASH_KINDS):
        key = result["outcome"][1:]
        record = records.setdefault(key, {"key": list(key), "kinds": [], "mutants": 0, "operators": [],
                                          "pairs": [], "smallest": None, "cause": None, "causes": Counter()})
        record["mutants"] += 1
        record["causes"][result["cause"]] += 1
        pair = [result["operator"], result["program"]]
        for field, item in (("kinds", result["outcome"][0]), ("operators", result["operator"]), ("pairs", pair)):
            if item not in record[field]:
                record[field].append(item)
        if record["smallest"] is None or len(result["source"]) < len(record["smallest"]["source"]):
            record["smallest"], record["cause"] = {"name": result["name"], "source": result["source"]}, result["cause"]
    for record in records.values():
        record["kinds"].sort()
        record["operators"].sort(key=list(OPERATORS).index)
        record["causes"] = dict(record["causes"].most_common())
    return [records[key] for key in sorted(records)]


def _seed_digests(work: Path, programs: Sequence[str]) -> dict[str, str]:
    """Each seed's digest. Raises ValueError for a seed that does not build: the check needs its parent."""
    digests = {}
    for program in programs:
        result = outcome(work, program)
        if result[0] != "compiles":
            raise ValueError(f"the seed {program} does not build: {result}")
        digests[program] = result[1]
    return digests


def compiled(seed_dir: Path, sources: Mapping[str, str],
             drawn: Sequence[tuple[str, Mutation]]) -> tuple[list[dict], dict[str, str]]:
    """Each drawn `(program, mutation)` applied to `sources[program]` and compiled in a temporary copy of `seed_dir`:
    one result per mutant (`program`, `operator`, `params`, `outcome`, `cause`, `name`, `source`, `lines`), and each
    seed's digest. Raises ValueError for a seed that does not build, before any mutant compiles."""
    results = []
    with tempfile.TemporaryDirectory(prefix="mutants-") as scratch:
        work = Path(scratch) / "seed"
        shutil.copytree(seed_dir, work)
        for program, text in sources.items():
            (work / f"{program}.orc").write_text(text, encoding="utf-8")
        seeds = _seed_digests(work, sorted(sources))
        for program, mutation in drawn:
            source = apply(sources[program], mutation)
            (work / f"{program}.orc").write_text(source, encoding="utf-8")
            result, cause = _observed(work, program)
            (work / f"{program}.orc").write_text(sources[program], encoding="utf-8")
            results.append({"program": program, "operator": mutation.operator, "params": mutation.params,
                            "outcome": result, "cause": cause, "source": source,
                            "name": f"{program}/{mutation.operator}/{mutation.params}",
                            "lines": source.count("\n") + (not source.endswith("\n"))})
    return results, seeds


def _compiled_report(seed_dir: Path, programs: Sequence[str], cap: int, number: int,
                     operators: Sequence[str]) -> tuple[dict, list[dict], dict[str, str]]:
    """`compile_report`'s readout, with the per-mutant results and the seeds' digests it was made from."""
    sources = {program: read_source(Path(seed_dir) / f"{program}.orc") for program in programs}
    drawn = sample(sources, cap, number, operators)
    if not drawn:
        raise ValueError(f"the sample is empty: programs {sorted(sources)}, operators {list(operators)}, cap {cap}")
    results, seeds = compiled(seed_dir, sources, drawn)
    built = [(result["program"], result["outcome"][1]) for result in results if result["outcome"][0] == "compiles"]
    return {
        "sample": {"programs": sorted(sources), "operators": [name for name in OPERATORS if name in operators],
                   "cap": cap, "number": number, "python": platform.python_version(), "mutants": len(drawn)},
        "operators": _counts(results, operators),
        "distinct_digests": len({digest for _, digest in built}),
        "equal_to_seed": sum(digest == seeds[program] for program, digest in built),
        "crashes": _crashes(results),
    }, results, seeds


def compile_report(seed_dir: Path, programs: Sequence[str], cap: int, number: int,
                   operators: Sequence[str] = tuple(OPERATORS)) -> dict:
    """The readout (module docstring) of the sample `operators.sample(sources, cap, number, operators)` of
    the seeds in `seed_dir`. Raises, before any compile, OSError or ValueError for a program file that is
    missing or unreadable and ValueError for what `sample` refuses and for an empty sample; then
    ValueError for a seed that does not build, before any mutant compiles."""
    return _compiled_report(seed_dir, programs, cap, number, operators)[0]


def _build_world(world: Path, seed_dir: Path, program: str, standin: Mapping) -> None:
    """`src/` the seeds (the program's line ends normalised), `repo/` the workspace, `bin/claude` the fake."""
    src, repo, bin_dir = world / "src", world / "repo", world / "bin"
    shutil.copytree(seed_dir, src)
    (src / f"{program}.orc").write_text(read_source(src / f"{program}.orc"), encoding="utf-8")
    repo.mkdir()
    bin_dir.mkdir()
    (bin_dir / "claude").write_text(f"#!{sys.executable}\n" + FAKE_CLAUDE, encoding="utf-8")
    (bin_dir / "claude").chmod(0o700)
    for name, text in standin["files"].items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text.replace("{python}", sys.executable), encoding="utf-8")
    declared = entry_inputs((src / f"{program}.orc").read_text(encoding="utf-8"))
    workspace = {"repo": str(repo)} if "repo" in declared else {}  # an entry without the input refuses it
    (world / "inputs.json").write_text(json.dumps({**standin["inputs"], **workspace}), encoding="utf-8")


def _run_argv(world: Path, program: str) -> list[str]:
    src = world / "src"
    argv = [sys.executable, "-m", "orchestrator", "run", str(src / f"{program}.orc"), "--entry-workflow",
            f"{program}::run", "--source-root", str(src), "--input-file", str(world / "inputs.json")]
    for flag, name in (("--provider-externs-file", "providers.json"), ("--command-boundaries-file", "commands.json")):
        if (src / name).exists():
            argv += [flag, str(src / name)]
    return argv


def _requests(workspace: Path) -> int:
    """The fake's request log: one line per provider call."""
    log = workspace / "requests.jsonl"
    return len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0


def _priced_usd(run_root: Path) -> float | None:
    """The run's priced cost from its attempts' `usage.json`, or None when no attempt reported usage (a stand-in)."""
    usages = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(run_root.rglob("usage.json"))]
    return summed_usage(usages, load_price_table())["cost_usd"] if usages else None


def _committed(run_root: Path) -> list[dict]:
    """The run's committed journal rows (`memo.jsonl`), in journal order: its steps."""
    rows = [json.loads(line) for line in (run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return [row for row in rows if row.get("record") == "committed"]


def _cause(stderr: str) -> str:
    """The cause of a failed run: its last line that starts with a `[code]`, else its last non-empty line."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return ([line for line in lines if line.startswith("[")] or lines or ["no output"])[-1]


@contextmanager
def recorded_run(seed_dir: Path, program: str, standin: Mapping, scenario: str) -> Iterator[dict]:
    """One completed stand-in run of the seed `program` under `scenario`, in a temporary world removed on exit.

    The run is `python -m orchestrator run` with the fake `claude` of `tests/agent_session_shims.py` on
    `closed_path`, answering `standin["answers"][program][scenario]` in call order; no real provider can be
    reached. Yields `{world, run_root, workspace, program, scenario, steps, calls, priced_usd, priced_reason}`:
    `steps` the committed rows of the run's journal, `calls` the fake's request log lines. Raises ValueError
    when the run times out, does not exit 0 or does not use every answer (the stand-in does not fit the seed),
    and when it is not clean: its calls differ from its committed provider-class effects (a retry or an
    uncommitted attempt), so a provider call kept could not be told from an attempt."""
    answers, name = standin["answers"][program][scenario], f"the stand-in run of {program}/{scenario}"
    with tempfile.TemporaryDirectory(prefix="mutants-reuse-") as scratch:
        world = Path(scratch)
        _build_world(world, Path(seed_dir), program, standin)
        env = {"PATH": closed_path(world / "bin"), "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
               "HOME": str(world), "CLAUDE_CONFIG_DIR": str(world / "claude"),
               "AGENT_SHIM_PLAN": json.dumps({"claude": answers})}
        try:
            done = subprocess.run(_run_argv(world, program), cwd=world / "repo", env=env, capture_output=True,
                                  text=True, timeout=STANDIN_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise ValueError(f"{name} timed out after {STANDIN_TIMEOUT} s") from None
        calls = _requests(world / "repo")
        if done.returncode != 0 or calls != len(answers):
            raise ValueError(f"{name} does not fit: exit {done.returncode}, {calls} of {len(answers)} answers "
                             f"used: {_cause(done.stderr)}")
        (run_root,) = (world / "repo" / ".orchestrate" / "runs").iterdir()
        steps = _committed(run_root)
        effects = sum(row.get("effect_class") in PROVIDER_CLASSES for row in steps)
        if effects != calls:
            raise ValueError(f"{name} is not clean: {calls} provider calls for {effects} committed provider-class "
                             "effects (a retry or an uncommitted attempt); a recorded run needs one call per effect")
        priced = _priced_usd(run_root)
        yield {"world": world, "run_root": run_root, "workspace": world / "repo", "program": program,
               "scenario": scenario, "steps": len(steps), "calls": calls, "priced_usd": priced,
               "priced_reason": None if priced is not None else "no attempt reported usage (stand-in run)"}


def plan_outcome(run_root: Path, workspace: Path) -> tuple:
    """`plan_resume` for the run under the program as it now stands: `("plan", kept, cancelled, calls_cancelled)`,
    `calls_cancelled` being the cancelled provider-class commits; `("no_plan", code)` for a `ValueError` whose
    `code` is a string (a coded refusal). Any other exception propagates: an uncoded failure is never a share."""
    try:
        plan = plan_resume(run_root, workspace)
    except ValueError as error:
        if not isinstance(getattr(error, "code", None), str):
            raise
        return ("no_plan", error.code)
    return ("plan", len(plan.kept), len(plan.cancelled), len(plan.costs))


def _spread(values: list[int]) -> dict | None:
    return {"min": min(values), "median": statistics.median(values), "max": max(values)} if values else None


def _summary(results: list[tuple], calls: int) -> dict:
    """Figures over measured mutants' results; a `no_plan` is counted under its code and never in a share."""
    plans = [result for result in results if result[0] == "plan"]
    return {"measured": len(results), "same_program": sum(result[0] == "same_program" for result in results),
            "plans": len(plans), "steps_kept": _spread([result[1] for result in plans]),
            "calls_kept": _spread([calls - result[3] for result in plans]),
            "no_plan": dict(Counter(result[1] for result in results if result[0] == "no_plan"))}


SITE = {"effort": "=", "model": "=", "rounds": "=", "prompt": ".", "graft": "<-"}  # params up to this name the site


def _site(result: dict) -> str:
    operator = result["operator"]
    return result["params"].split(SITE[operator])[0] if operator in SITE else result["params"]


def _planned(run: dict, results: Sequence[dict], seed: str) -> dict[str, list[tuple[str, tuple]]]:
    """Per operator, `(site, plan outcome)` for each result of the run's program that compiled: `("same_program",)`
    when its digest is `seed`, else its source is written over the program in the world's `src/`, planned, and
    the seed's source restored."""
    path = run["world"] / "src" / f"{run['program']}.orc"
    seed_text, measured = path.read_text(encoding="utf-8"), {}
    for result in results:
        if result["program"] != run["program"] or result["outcome"][0] != "compiles":
            continue
        planned = ("same_program",)
        if result["outcome"][1] != seed:
            path.write_text(result["source"], encoding="utf-8")
            planned = plan_outcome(run["run_root"], run["workspace"])
            path.write_text(seed_text, encoding="utf-8")
        measured.setdefault(result["operator"], []).append((_site(result), planned))
    return measured


def measure(run: dict, results: Sequence[dict], seed: str) -> dict:
    """The readout's reuse section for one recorded run, from `compiled`'s results and the program's seed digest
    `seed`: a mutant that did not compile is left out, one whose digest is the seed's is `same_program`, every
    other one is planned (`_planned`). No mutant is compiled again here and none is run."""
    measured, operators = _planned(run, results, seed), {}
    for operator in (name for name in OPERATORS if name in measured):
        sites: dict[str, list[tuple]] = {}
        for site, planned in measured[operator]:
            sites.setdefault(site, []).append(planned)
        operators[operator] = {**_summary([planned for _, planned in measured[operator]], run["calls"]),
                               "sites": {site: _summary(found, run["calls"]) for site, found in sites.items()}}
    return {"program": run["program"], "scenario": run["scenario"], "steps": run["steps"],
            "provider_calls": run["calls"], "priced_usd": run["priced_usd"], "priced_reason": run["priced_reason"],
            "operators": operators}


def reuse_report(seed_dir: Path, program: str, standin: Mapping, scenario: str,
                 mutants: Sequence[tuple[str, Mutation]]) -> dict:
    """`compiled` and then `measure` on one stand-in run of `program` under `scenario`, made and removed here."""
    results, seeds = compiled(seed_dir, {program: read_source(Path(seed_dir) / f"{program}.orc")}, mutants)
    with recorded_run(seed_dir, program, standin, scenario) as run:
        return measure(run, results, seeds[program])


def _print(report: dict) -> None:
    long = f"lines_{LONG}_or_more"
    print(f"{'operator':<10} {'mutants':>7} {'compiles':>8} {'refused':>7} {'crashed':>7} {f'>={LONG} lines':>10}")
    for name, row in report["operators"].items():
        print(f"{name:<10} {row['mutants']:>7} {row['compiles']:>8} {sum(row['refused'].values()):>7} "
              f"{sum(row['crash_keys'].values()):>7} {row[long]:>10}")
        for codes, count in sorted(row["refused"].items()):
            print(f"{'':<10} refused {count:>4}  {codes}")
    print(f"distinct digests {report['distinct_digests']}, equal to the seed {report['equal_to_seed']}, "
          f"crash keys {len(report['crashes'])}")
    for record in report["crashes"]:
        print(json.dumps(record, indent=2))
    for section in report.get("reuse", ()):
        priced = section["priced_reason"] if section["priced_usd"] is None else f"USD {section['priced_usd']}"
        print(f"reuse {section['program']}/{section['scenario']}: {section['steps']} steps, "
              f"{section['provider_calls']} provider calls, priced: {priced}")
        for name, row in section["operators"].items():
            spread = [("-" if row[key] is None else "{min}/{median}/{max}".format(**row[key]))
                      for key in ("steps_kept", "calls_kept")]
            print(f"  {name:<10} measured {row['measured']:>4}  same {row['same_program']:>3}  plans {row['plans']:>4}  "
                  f"steps kept {spread[0]:<9} calls kept {spread[1]:<9} no plan {row['no_plan']}")


def _names(text: str) -> tuple[str, ...]:
    return tuple(name for name in text.split(",") if name)


def _out_problem(out: Path) -> str | None:
    """Why the readout cannot be written to `out`, or None."""
    if not out.parent.is_dir() or not os.access(out.parent, os.W_OK):
        return f"--out: {out.parent} is not a writable directory"
    if out.exists() and (not out.is_file() or not os.access(out, os.W_OK)):
        return f"--out: {out} is not a writable file"
    resolved = out.resolve()
    # ponytail: "a file of a git working tree" stands for "a tracked file": asking git would start a
    # process, which the check never does. It refuses some untracked files too, never a tracked one.
    if out.exists() and resolved != READOUT.resolve() and any((d / ".git").exists() for d in resolved.parents):
        return f"--out: {out} is a file of a git working tree; only {READOUT} may be overwritten"
    return None


def _input_problem(args: argparse.Namespace) -> str | None:
    """What the command refuses before reading any source, or None."""
    if not args.seed_dir.is_dir():
        return f"the seed directory {args.seed_dir} does not exist"
    if not args.programs:
        return "no program named (--programs)"
    missing = [program for program in args.programs if not (args.seed_dir / f"{program}.orc").is_file()]
    if missing:
        return f"no program file in {args.seed_dir} for {missing}"
    return _out_problem(args.out)


def _refuse(problem: object) -> int:
    print(f"{PROG}: error: {' '.join(str(problem).split())}", file=sys.stderr)
    return 2


def _read_standin(path: Path) -> dict:
    """The stand-in file, with its three keys and `answers` an object of objects. Raises OSError or ValueError."""
    standin = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(standin, dict) or not {"inputs", "files", "answers"} <= standin.keys():
        raise ValueError(f"the stand-in file {path} needs the keys inputs, files and answers")
    answers = standin["answers"]
    if not isinstance(answers, dict) or not all(isinstance(scenarios, dict) for scenarios in answers.values()):
        raise ValueError(f"the stand-in file {path}: answers must map each program to an object of scenarios")
    return standin


def _standin_runs(args: argparse.Namespace) -> tuple[dict, list[tuple[str, str]]]:
    """The stand-in file and its (program, scenario) runs, in program order. Raises OSError or ValueError."""
    if args.standin is None:
        if args.scenarios:
            raise ValueError("--scenarios needs --standin")
        return {}, []
    standin = _read_standin(args.standin)
    present = [(program, scenario) for program in args.programs for scenario in standin["answers"].get(program, {})]
    unknown = set(args.scenarios) - {scenario for _, scenario in present}
    if unknown:
        raise ValueError(f"no named program has the scenarios {sorted(unknown)} in {args.standin}")
    runs = [pair for pair in present if not args.scenarios or pair[1] in args.scenarios]
    if not runs:
        raise ValueError(f"the stand-in file {args.standin} has no scenario for {list(args.programs)}")
    return standin, runs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description="Compile a sample of mechanical mutants of the seeds.")
    parser.add_argument("seed_dir", type=Path)
    parser.add_argument("--programs", type=_names, required=True)
    parser.add_argument("--operators", type=_names, default=tuple(OPERATORS))
    parser.add_argument("--cap", type=int, default=100)
    parser.add_argument("--number", type=int, default=0)
    parser.add_argument("--out", type=Path, default=READOUT)
    parser.add_argument("--standin", type=Path)
    parser.add_argument("--scenarios", type=_names, default=())
    args = parser.parse_args(argv)
    problem = _input_problem(args)
    if problem:
        return _refuse(problem)
    with ExitStack() as worlds:
        try:  # an input the check refuses to measure: exit 2, see the docstring
            standin, pairs = _standin_runs(args)
            runs = [worlds.enter_context(recorded_run(args.seed_dir, program, standin, scenario))
                    for program, scenario in pairs]
            report, results, seeds = _compiled_report(args.seed_dir, args.programs, args.cap, args.number,
                                                      args.operators)
        except (OSError, ValueError) as error:
            return _refuse(error)
        if runs:  # a planner's uncoded exception propagates: exit 1, a traceback, no readout
            report["reuse"] = [measure(run, results, seeds[run["program"]]) for run in runs]
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _print(report)
    print(f"readout: {args.out}")
    return 1 if report["crashes"] else 0


if __name__ == "__main__":
    sys.exit(main())
