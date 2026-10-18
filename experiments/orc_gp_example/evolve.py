"""A (mu+lambda) grammar-guided GP loop over ORC workflow programs, run offline against a scripted world.

Each individual (a `grammar` genotype) is rendered to a `.orc` module, compiled with the ordinary compiler
(the validity filter: a rejection is recorded, never crashes the loop), run through the public
`python -P -m orchestrator run` in its own workspace with `scripted_agent.py` as `claude`/`codex`, and scored
from that run's memo alone. Identical rendered sources share one evaluation (a cache hit, not a replicate).

    python -m experiments.orc_gp_example.evolve --out <dir> [--population 6] [--generations 4] [--seed 0]

Writes `<dir>/results.json` and one workspace per evaluated source under `<dir>/runs/<digest>/`.
Dependencies: this checkout's `orchestrator` (PYTHONPATH is set to it for every subprocess);
`experiments.orc_structural_search.records.skeleton_hash` for structural diversity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

from experiments.orc_gp_example import grammar
from experiments.orc_structural_search.records import skeleton_hash

REPO = Path(__file__).resolve().parents[2]
AGENT = Path(__file__).with_name("scripted_agent.py")
PRICE = {"claude-sonnet-5-5": 1.0, "gpt-6-sol": 3.0, "claude-opus-5-5": 5.0}  # toy units per call
SUCCESS_REWARD, COST_WEIGHT = 10.0, 0.5
MAX_STAGES = 6
SEED_GENOTYPE = (("implement", "claude-sonnet-5-5"),)
TASK = "Add input validation to the parser."


# --- variation ---------------------------------------------------------------------------------------

def random_stage(rng: random.Random) -> tuple:
    kind = rng.choice(grammar.STAGE_KINDS)
    model = rng.choice(grammar.MODELS)
    if kind in ("plan", "implement"):
        return (kind, model)
    return (kind, rng.randint(1, grammar.MAX_ROUNDS), model)


def valid(genotype: tuple) -> bool:
    return 0 < len(genotype) <= MAX_STAGES and any(s[0] in ("implement", "ill_typed_implement") for s in genotype)


def random_genotype(rng: random.Random) -> tuple:
    while True:
        genotype = tuple(random_stage(rng) for _ in range(rng.randint(1, 3)))
        if valid(genotype):
            return genotype


def _point_mutation(genotype: list, rng: random.Random, ill_typed_rate: float) -> None:
    """One of: insert, delete, replace a stage, change a model, change rounds (in place)."""
    i = rng.randrange(len(genotype))
    op = rng.choice(("insert", "delete", "replace", "model", "rounds"))
    if op == "insert":
        genotype.insert(rng.randint(0, len(genotype)), random_stage(rng))
    elif op == "delete":
        del genotype[i]
    elif op == "replace":
        genotype[i] = random_stage(rng)
    elif op == "model":
        genotype[i] = (*genotype[i][:-1], rng.choice(grammar.MODELS))
    elif genotype[i][0] in grammar.LOOPS:
        genotype[i] = (genotype[i][0], rng.randint(1, grammar.MAX_ROUNDS), genotype[i][2])
    implements = [j for j, stage in enumerate(genotype) if stage[0] == "implement"]
    if implements and rng.random() < ill_typed_rate:  # off-grammar operator, only with --ill-typed-rate
        j = rng.choice(implements)
        genotype[j] = ("ill_typed_implement", genotype[j][1])


def mutate(genotype: tuple, rng: random.Random, ill_typed_rate: float = 0.0) -> tuple:
    """A valid child differing from `genotype` (retries until the stage-list constraints hold)."""
    while True:
        child = list(genotype)
        _point_mutation(child, rng, ill_typed_rate)
        if valid(tuple(child)) and tuple(child) != genotype:
            return tuple(child)


def crossover(a: tuple, b: tuple, rng: random.Random) -> tuple:
    """One-point crossover on the stage lists: a prefix of `a` then a suffix of `b`; a parent when no cut
    point yields a valid child."""
    cuts = [(i, j) for i in range(len(a) + 1) for j in range(len(b) + 1) if valid(a[:i] + b[j:])]
    if not cuts:
        return a
    i, j = rng.choice(cuts)
    return a[:i] + b[j:]


def tournament(population: list[dict], rng: random.Random, size: int = 2) -> dict:
    return max(rng.sample(population, size), key=rank)


def rank(individual: dict) -> float:
    """Selection key: an individual without a fitness (rejected, or missing run data) ranks last."""
    return individual["fitness"] if individual["fitness"] is not None else float("-inf")


# --- evaluation --------------------------------------------------------------------------------------

def _env(workspace: Path) -> dict:
    fakebin = workspace / "bin"
    return {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": os.pathsep.join([str(fakebin), str(Path(sys.executable).parent), os.environ.get("PATH", "")])}


def prepare_workspace(workspace: Path, source: str) -> None:
    """Module, boundary files, the check command and the scripted `claude`/`codex` executables."""
    if workspace.exists():
        shutil.rmtree(workspace)
    (workspace / "bin").mkdir(parents=True)
    (workspace / f"{grammar.MODULE}.orc").write_text(source)
    (workspace / "providers.json").write_text(json.dumps(grammar.PROVIDERS))
    (workspace / "commands.json").write_text(json.dumps(grammar.COMMANDS))
    shutil.copy(AGENT, workspace / "check.py")
    for name in ("claude", "codex"):
        (workspace / "bin" / name).write_text(f"#!{sys.executable} -I\n" + AGENT.read_text())
        (workspace / "bin" / name).chmod(0o755)


def orchestrator(workspace: Path, command: str, *extra: str) -> subprocess.CompletedProcess:
    argv = [sys.executable, "-P", "-m", "orchestrator", command, f"{grammar.MODULE}.orc",
            "--entry-workflow", f"{grammar.MODULE}::run", "--source-root", ".",
            "--provider-externs-file", "providers.json", "--command-boundaries-file", "commands.json", *extra]
    return subprocess.run(argv, cwd=workspace, env=_env(workspace), capture_output=True, text=True, timeout=600)


def score(genotype: tuple, memo: Path) -> dict:
    """Whole-run fitness from the memo: success needs a completed DONE terminal and a passing final check;
    cost prices each `committed` row whose effect_class is `provider`, by model (started, phased or failed
    attempt rows are not priced). Missing terminal or final check -> fitness None."""
    rows = [json.loads(line) for line in memo.read_text().splitlines() if line]
    committed = [r for r in rows if r.get("record") == "committed"]
    terminal = next((r for r in rows if r.get("record") == "terminal"), None)
    final = next((r["value"] for r in committed if r["identity"].endswith(" / final")), None)
    calls = [grammar.call_model(genotype, r["identity"]) for r in committed if r["effect_class"] == "provider"]
    cost = sum(PRICE[m] for m in calls)
    result = {"calls": len(calls), "calls_by_model": {m: calls.count(m) for m in sorted(set(calls))}, "cost": cost}
    if terminal is None or final is None:
        return {**result, "success": None, "fitness": None}
    success = terminal["outcome"] == "completed" and terminal["value"].get("variant") == "DONE" and final["passed"]
    return {**result, "success": success, "fitness": SUCCESS_REWARD * success - COST_WEIGHT * cost}


def evaluate(genotype: tuple, runs: Path) -> dict:
    """Compile, then (if accepted) run one individual in `runs/<digest>/` and score it."""
    source = grammar.render(genotype)
    digest = hashlib.sha256(source.encode()).hexdigest()
    workspace = runs / digest[:16]
    prepare_workspace(workspace, source)
    record = {"genotype": [list(s) for s in genotype], "source_digest": digest,
              "skeleton": skeleton_hash(source, definitions=["run"]), "workspace": str(workspace)}
    compiled = orchestrator(workspace, "compile")
    if compiled.returncode != 0:
        return {**record, "compile": "rejected", "compile_error": compiled.stderr[-800:], "fitness": None,
                "success": None, "calls": None, "cost": None}
    ran = orchestrator(workspace, "run", "--input", f"task={TASK}", "--state-dir", "state")
    memos = sorted((workspace / "state").glob("*/memo.jsonl"))
    if len(memos) != 1:
        return {**record, "compile": "accepted", "run_exit": ran.returncode, "run_error": ran.stderr[-800:],
                "fitness": None, "success": None, "calls": None, "cost": None}
    return {**record, "compile": "accepted", "run_exit": ran.returncode, **score(genotype, memos[0])}


# --- search ------------------------------------------------------------------------------------------

class Evaluator:
    """Evaluates genotypes, caching by rendered-source digest; counts cache hits per generation."""

    def __init__(self, runs: Path):
        self.runs, self.by_digest, self.hits = runs, {}, 0

    def __call__(self, genotype: tuple) -> dict:
        digest = hashlib.sha256(grammar.render(genotype).encode()).hexdigest()
        if digest in self.by_digest:
            self.hits += 1
        else:
            self.by_digest[digest] = evaluate(genotype, self.runs)
        return self.by_digest[digest]


def offspring(population: list[dict], rng: random.Random, count: int, ill_typed_rate: float) -> list[tuple]:
    """`count` children: crossover of two tournament winners with probability 0.5, then one mutation."""
    children = []
    for _ in range(count):
        parent = tuple(map(tuple, tournament(population, rng)["genotype"]))
        if rng.random() < 0.5:
            parent = crossover(parent, tuple(map(tuple, tournament(population, rng)["genotype"])), rng)
        children.append(mutate(parent, rng, ill_typed_rate))
    return children


def summarize(index: int, population: list[dict], children: list[dict], hits: int) -> dict:
    scored = [p["fitness"] for p in population if p["fitness"] is not None]
    return {"generation": index,
            "best_fitness": max(scored) if scored else None,
            "mean_fitness": round(statistics.mean(scored), 3) if scored else None,
            "unscored": len(population) - len(scored),
            "distinct_skeletons": len({p["skeleton"] for p in population}),
            "offspring_compiled": sum(c["compile"] == "accepted" for c in children),
            "offspring_rejected": sum(c["compile"] == "rejected" for c in children),
            "cache_hits": hits,
            "offspring_calls": [c["calls"] for c in children],
            "best_genotype": max(population, key=rank)["genotype"],
            "population": [p["source_digest"] for p in population]}


def evolve(out: Path, population_size: int, generations: int, seed: int, ill_typed_rate: float = 0.0) -> dict:
    """Run the (mu+lambda) search (mu = lambda = population_size) and write `out/results.json`."""
    rng = random.Random(seed)
    evaluate_ = Evaluator(out / "runs")
    initial = [SEED_GENOTYPE] + [random_genotype(rng) for _ in range(population_size - 1)]
    population = [evaluate_(g) for g in initial]
    seed_record = population[0]
    history = [summarize(0, population, population, evaluate_.hits)]
    for index in range(1, generations + 1):
        evaluate_.hits = 0
        children = [evaluate_(g) for g in offspring(population, rng, population_size, ill_typed_rate)]
        unique = {p["source_digest"]: p for p in population + children}  # a duplicate is one individual
        population = sorted(unique.values(), key=rank, reverse=True)[:population_size]
        history.append(summarize(index, population, children, evaluate_.hits))
    results = {"config": {"population": population_size, "generations": generations, "seed": seed,
                          "ill_typed_rate": ill_typed_rate, "price": PRICE, "success_reward": SUCCESS_REWARD,
                          "cost_weight": COST_WEIGHT, "task": TASK},
               "seed_individual": seed_record["source_digest"],
               "generations": history[1:], "initial": history[0],
               "individuals": evaluate_.by_digest}
    (out / "results.json").write_text(json.dumps(results, indent=2))
    return results


def table(results: dict) -> str:
    head = f"{'gen':>3} {'best':>6} {'mean':>6} {'skel':>4} {'ok':>3} {'rej':>3} {'hits':>4}  best genotype"
    rows = [head]
    for g in [results["initial"], *results["generations"]]:
        best = " ".join(":".join(map(str, s)) for s in g["best_genotype"])
        rows.append(f"{g['generation']:>3} {g['best_fitness']!s:>6} {g['mean_fitness']!s:>6} "
                    f"{g['distinct_skeletons']:>4} {g['offspring_compiled']:>3} {g['offspring_rejected']:>3} "
                    f"{g['cache_hits']:>4}  {best}")
    return "\n".join(rows)


def _at_least_two(text: str) -> int:
    if int(text) < 2:
        raise argparse.ArgumentTypeError("population must be at least 2 (size-2 tournaments)")
    return int(text)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--population", type=_at_least_two, default=6, help="mu = lambda; >= 2 (tournaments)")
    parser.add_argument("--generations", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ill-typed-rate", type=float, default=0.0)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    print(table(evolve(args.out.resolve(), args.population, args.generations, args.seed, args.ill_typed_rate)))


if __name__ == "__main__":
    main()
