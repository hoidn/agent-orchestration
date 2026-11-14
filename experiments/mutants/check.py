"""The compile check of mechanical mutants: each one builds, is refused with codes, or crashes.

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md (Task T2).

A seed directory holds one `NAME.orc` per program, whose entry is `NAME::run`, beside
`providers.json` and `commands.json` when the programs use them. The directory is copied once to a
temporary work directory, which is removed afterwards; each mutant is written over its program
there and compiled in process with `prepare_closed_program_bundle`, which writes nothing. The seed
directory is never written. Nothing is run: no workflow, provider or command is started, and the
module imports none of the runtime's dispatch entry points. Sources are read as UTF-8 with `\\r\\n`
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

Command: `python -m experiments.mutants.check SEED_DIR --programs a,b [--operators x,y] [--cap 100]
[--number 0] [--out PATH]`. It prints a table and every crash record, writes the readout (by
default `experiments/mutants/readout.json`), and exits 1 when any mutant crashed, else 0. Every
problem with its input exits 2 with one line and writes no readout, before any mutant compiles: a
missing seed directory or program file, an unreadable or undecodable one, no program, an unknown
operator, a negative cap, an empty sample, a model or effort literal outside the closed sets, a
seed that does not build, an `--out` whose directory is missing or not writable, and an `--out`
that is an existing file of a git working tree other than the default readout.
"""

import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from experiments.mutants.operators import OPERATORS, apply, sample
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle
from tests.workflow_lisp_closed_program_helpers import build_outcome, crash_signature

READOUT = Path(__file__).with_name("readout.json")
CRASH_KINDS = ("crash", "traceback")
DEFECT = "compiler_defect"
LONG = 50  # lines: a mutant this long is over the seeds' line limit
PROG = "python -m experiments.mutants.check"


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


def compile_report(seed_dir: Path, programs: Sequence[str], cap: int, number: int,
                   operators: Sequence[str] = tuple(OPERATORS)) -> dict:
    """The readout (module docstring) of the sample `operators.sample(sources, cap, number, operators)` of
    the seeds in `seed_dir`. Raises, before any compile, OSError or ValueError for a program file that is
    missing or unreadable and ValueError for what `sample` refuses and for an empty sample; then
    ValueError for a seed that does not build, before any mutant compiles."""
    sources = {program: read_source(Path(seed_dir) / f"{program}.orc") for program in programs}
    drawn = sample(sources, cap, number, operators)
    if not drawn:
        raise ValueError(f"the sample is empty: programs {sorted(sources)}, operators {list(operators)}, cap {cap}")
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
            results.append({"program": program, "operator": mutation.operator, "outcome": result, "cause": cause,
                            "name": f"{program}/{mutation.operator}/{mutation.params}", "source": source,
                            "lines": source.count("\n") + (not source.endswith("\n"))})
    built = [(result["program"], result["outcome"][1]) for result in results if result["outcome"][0] == "compiles"]
    return {
        "sample": {"programs": sorted(sources), "operators": [name for name in OPERATORS if name in operators],
                   "cap": cap, "number": number, "python": platform.python_version(), "mutants": len(drawn)},
        "operators": _counts(results, operators),
        "distinct_digests": len({digest for _, digest in built}),
        "equal_to_seed": sum(digest == seeds[program] for program, digest in built),
        "crashes": _crashes(results),
    }


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description="Compile a sample of mechanical mutants of the seeds.")
    parser.add_argument("seed_dir", type=Path)
    parser.add_argument("--programs", type=_names, required=True)
    parser.add_argument("--operators", type=_names, default=tuple(OPERATORS))
    parser.add_argument("--cap", type=int, default=100)
    parser.add_argument("--number", type=int, default=0)
    parser.add_argument("--out", type=Path, default=READOUT)
    args = parser.parse_args(argv)
    problem = _input_problem(args)
    if problem:
        return _refuse(problem)
    try:
        report = compile_report(args.seed_dir, args.programs, args.cap, args.number, args.operators)
    except (OSError, ValueError) as error:  # an input the check refuses to measure: exit 2, see the docstring
        return _refuse(error)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _print(report)
    print(f"readout: {args.out}")
    return 1 if report["crashes"] else 0


if __name__ == "__main__":
    sys.exit(main())
