"""The compile check of mechanical mutants: each one builds, is refused with codes, or crashes.

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md (Task T2).

A seed directory holds one `NAME.orc` per program, whose entry is `NAME::run`, beside
`providers.json` and `commands.json` when the programs use them. The directory is copied once to a
temporary work directory, which is removed afterwards; each mutant is written over its program
there and compiled in process with `prepare_closed_program_bundle`, which writes nothing. The seed
directory is never written. Nothing is run: no workflow, provider or command is started. Sources
are read as UTF-8 with `\\r\\n` and `\\r` turned into `\\n` before any operator or digest sees them.

An outcome is classified by `build_outcome` of `tests/workflow_lisp_closed_program_helpers.py`, the
classifier of the defect backlog's test module, so one crash has one key in both. A crash's key is
`crash_signature`'s pair (the exception class and a function under `orchestrator/`) without the
kind: a `compiler_defect` and an exception that left the build uncaught at one place share a key.
A key is a location, not a defect, and this module reads no list of known defects: every crash is
reported, per key, with its count, its operators and its shortest mutant.

Command: `python -m experiments.mutants.check SEED_DIR --programs a,b [--operators x,y] [--cap 100]
[--number 0] [--out PATH]`. It prints a table and every crash record, writes the readout (by
default `experiments/mutants/readout.json`), and exits 1 when any mutant crashed, else 0. A seed
that does not build, an unknown operator or a model or effort literal outside the closed sets is a
usage error (exit 2).
"""

import argparse
import json
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
from tests.workflow_lisp_closed_program_helpers import build_outcome

READOUT = Path(__file__).with_name("readout.json")
CRASH_KINDS = ("crash", "traceback")
LONG = 50  # lines: a mutant this long is over the seeds' line limit


def read_source(path: Path) -> str:
    """A program's text: UTF-8, line ends normalised to `\\n`."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


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


def _observed(work: Path, program: str) -> tuple[tuple, str]:
    """The outcome of `outcome`, and for a crash the first line of its cause's message."""
    digest, witness = [], _Witness()

    def build():
        with witness:
            digest.append(prepare_closed_program_bundle(_request(work, program)).program.digest)

    result = build_outcome(build)
    if result == ("builds",):
        return ("compiles", digest[0]), ""
    if result[0] not in CRASH_KINDS:
        return result, ""
    cause = witness.error.diagnostics[0].cause if result[0] == "crash" else witness.error
    return result, next(iter(str(cause).splitlines()), "")


def outcome(work: Path, program: str) -> tuple:
    """The compile of `work/PROGRAM.orc` as it stands: `("compiles", digest)`; `("refused", *codes)`;
    `("crash", class, where)` for a `compiler_defect`; `("traceback", class, where)` for an exception
    that left the build. Writes nothing."""
    return _observed(work, program)[0]


def _counts(results: list[dict], names: Sequence[str]) -> dict:
    """Per operator, in `OPERATORS` order: mutants, compiles, each refusal's codes, each crash key, long mutants."""
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
    """One record per crash key, by key: its kinds, mutants, operators, pairs, cause and shortest mutant."""
    records: dict[tuple, dict] = {}
    for result in (result for result in results if result["outcome"][0] in CRASH_KINDS):
        key = result["outcome"][1:]
        record = records.setdefault(key, {"key": list(key), "kinds": [], "mutants": 0, "operators": [],
                                          "pairs": [], "cause": result["cause"], "smallest": None})
        record["mutants"] += 1
        pair = [result["operator"], result["program"]]
        for field, item in (("kinds", result["outcome"][0]), ("operators", result["operator"]), ("pairs", pair)):
            if item not in record[field]:
                record[field].append(item)
        if record["smallest"] is None or len(result["source"]) < len(record["smallest"]["source"]):
            record["smallest"] = {"name": result["name"], "source": result["source"]}
    for record in records.values():
        record["kinds"].sort()
        record["operators"].sort(key=list(OPERATORS).index)
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
    """Compile the sample `operators.sample(sources, cap, number, operators)` of the seeds in `seed_dir`.

    The readout: the sample (programs, operators, cap, number, Python version, mutants); per operator
    the counts of `_counts`; `distinct_digests` among the mutants that compile and `equal_to_seed`, those
    whose digest is their seed's; `crashes`, one record per key (`_crashes`). Raises ValueError for what
    `sample` refuses and for a seed that does not build.
    """
    sources = {program: read_source(Path(seed_dir) / f"{program}.orc") for program in programs}
    drawn = sample(sources, cap, number, operators)
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m experiments.mutants.check",
                                     description="Compile a sample of mechanical mutants of the seeds.")
    parser.add_argument("seed_dir", type=Path)
    parser.add_argument("--programs", type=_names, required=True)
    parser.add_argument("--operators", type=_names, default=tuple(OPERATORS))
    parser.add_argument("--cap", type=int, default=100)
    parser.add_argument("--number", type=int, default=0)
    parser.add_argument("--out", type=Path, default=READOUT)
    args = parser.parse_args(argv)
    try:
        report = compile_report(args.seed_dir, args.programs, args.cap, args.number, args.operators)
    except ValueError as error:  # what the check refuses to measure is a usage error, exit 2
        parser.error(str(error))
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _print(report)
    print(f"readout: {args.out}")
    return 1 if report["crashes"] else 0


if __name__ == "__main__":
    sys.exit(main())
