"""Write or check the freeze record of the long-horizon seeds, `seeds.json`.

    python -I experiments/long_horizon_seed/freeze.py write|check

The record holds, for each seed, the SHA-256 of its source, the digest of its compiled program and its target, and
the SHA-256 of every other kit file a run reads. A program digest does not cover the bytes of `dev_check.py`, the
script of the `dev-check` command, so the digests alone do not freeze the seeds. `check` exits 1 and names each entry
that differs. Nothing in the record depends on the machine or the day.
"""

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # `python -I` leaves the repository off the path
from orchestrator.workflow_lisp.build import FrontendBuildRequest  # noqa: E402
from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle  # noqa: E402

RECORD = HERE / "seeds.json"
SEEDS = ("staged", "designed", "milestones", "roles")
FILES = ("common.orc", "dev_check.py", "providers.json", "commands.json")  # what a run reads beside its seed
FROZEN = "the seeds are frozen: a change makes new seeds; record the new values deliberately"


def sha256(name: str) -> str:
    return hashlib.sha256((HERE / name).read_bytes()).hexdigest()


def compiled(seed: str) -> dict:
    """The seed's source hash and, from its program compiled in process (nothing is written), digest and target."""
    request = FrontendBuildRequest(
        source_path=HERE / f"{seed}.orc", source_roots=(HERE,), entry_workflow=f"{seed}::run",
        provider_externs_path=HERE / "providers.json", command_boundaries_path=HERE / "commands.json", workspace_root=HERE)
    program = prepare_closed_program_bundle(request).program
    return {"source_sha256": sha256(f"{seed}.orc"), "program_digest": program.digest, "target": program.tree["target"]}


def current() -> dict:
    """The record of the kit's files as they are."""
    return {"seeds": {seed: compiled(seed) for seed in SEEDS}, "files": {name: sha256(name) for name in FILES}}


def entries(record: dict) -> dict:
    """The record's values by path, `seeds/<seed>/<field>` and `files/<name>`."""
    seeds = {f"seeds/{seed}/{field}": value for seed, fields in record["seeds"].items() for field, value in fields.items()}
    return {**seeds, **{f"files/{name}": value for name, value in record["files"].items()}}


def differences() -> list[str]:
    """Each entry that differs between `seeds.json` and the files as they are: `entry: recorded -> current`."""
    recorded, now = entries(json.loads(RECORD.read_text())), entries(current())
    return [f"{entry}: {recorded.get(entry)} -> {now.get(entry)}" for entry in sorted(recorded | now)
            if recorded.get(entry) != now.get(entry)]


if __name__ == "__main__":
    if sys.argv[1:] == ["write"]:
        RECORD.write_text(json.dumps(current(), indent=2, sort_keys=True) + "\n")
    elif sys.argv[1:] == ["check"]:
        differing = differences()
        sys.exit("\n".join([*differing, FROZEN]) if differing else 0)
    else:
        sys.exit(__doc__)
