"""Turn one prepared MLE-bench competition into Harbor task packages and image build contexts (family plan, Task 1).

Usage: python wrap.py <competition dir> <data dir> <out dir> --class cpu|gpu --agent-base <image>
                      --verifier-base <image> [--public-sample <file in public/>]
prints the record wrap() returns, as JSON.

Inputs (read only):
  <competition dir>  the benchmark's directory of the competition (mlebench/competitions/<id>/): config.yaml,
                     description.md, the grader's files and leaderboard.csv. Its config.yaml names the id, the
                     answers, the sample submission and, where one exists, a gold submission, relative to the data
                     directory.
  <data dir>         holds <id>/prepared/public/ and <id>/prepared/private/, as the benchmark's preparation
                     writes them.
  family.json        (this kit) the class limits, the agent's time limit, the verifier's limits and the canary.
  instructions.md    (this kit) the benchmark's instructions adapted to plan M3; the competition's description
                     follows it in the instruction.
  agent_files, verifier_files   the kit's agent/ and verifier/ directories (plan Task 2 writes their files).

Output, written under <out dir>, which must not exist (LAYOUT holds the names):
  agent-context/     Dockerfile, data/ (every file of public/), tools/ (agent_files). Built from public/ alone:
                     nothing of private/, of the competition directory or of the leaderboard (plan M3).
  verifier-context/  Dockerfile, tests/ (verifier_files), data/<id>/prepared/private/ (every file of private/),
                     competition/ (every file of the competition directory).
  attempt/           task.toml and instruction.md: the package an attempt runs.
  answers/, sample/  the attempt package plus solution/ (solve.sh and the submission it copies): the answers (or
                     the gold submission) and the public sample submission, for the qualification legs (plan M2).

It builds no image, runs no container and downloads nothing. Every digest is Harbor's package content hash over
the bytes of the files (digest()); bytecode caches are never copied, and no path outside an output directory and
no time enters a digest, so the same input gives the same digests anywhere. The images are named by local names
that carry the first 16 hex digits of their build context's digest, so the attempt package's digest binds both
contexts.
"""

import argparse
import hashlib
import json
import shutil
import string
import sys
from pathlib import Path

import yaml

KIT = Path(__file__).resolve().parent
LAYOUT = {"agent_context": "agent-context", "verifier_context": "verifier-context", "attempt": "attempt",
          "answers": "answers", "sample": "sample"}
AGENT_DATA = "/home/data"  # in the agent image: the public files
SUBMISSION_DIR = "/home/submission"  # the one artifact that crosses to the verifier (plan M3)
VALIDATOR = "/home/validate_submission.py"  # the agent-side format check (plan M3; the file is Task 2's)
VERIFIER_DATA = "/private/data"  # in the verifier image: the grader's data directory, <id>/prepared/private/
GRADER_WORK = "/grader-work"  # the grader's working directory: it writes a cache where it runs (scout report B)


class Refused(Exception):
    """The wrapper refuses: the message names the input at fault. Output already written stays for inspection."""


def digest(root):
    """Harbor's Packager.compute_content_hash of a directory: SHA-256 over '<relative path>\\0<sha256>\\n' per
    file, sorted by POSIX relative path, as 'sha256:<hex>'."""
    outer = hashlib.sha256()
    for path in sorted(_files(root), key=lambda p: p.relative_to(root).as_posix()):
        outer.update(f"{path.relative_to(root).as_posix()}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n"
                     .encode())
    return "sha256:" + outer.hexdigest()


def _files(root):
    """Every file under root, bytecode caches left out; a symbolic link is refused, since it could point anywhere."""
    out = []
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise Refused(f"{path}: a symbolic link; inputs must be plain files")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            out.append(path)
    return out


def _copy_tree(src, dst):
    if not Path(src).is_dir():
        raise Refused(f"{src}: not a directory")
    for path in _files(src):
        _copy(path, dst / path.relative_to(src))


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def _inside(path, root, what):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_file() or root not in path.parents:
        raise Refused(f"{path}: the {what} is not a file in {root}")
    return path


def competition_files(competition, data_dir, public_sample=None):
    """(id, public dir, private dir, answers or gold submission, public sample submission) from config.yaml."""
    config = yaml.safe_load((Path(competition) / "config.yaml").read_text())
    cid, dataset = config["id"], config["dataset"]
    prepared = Path(data_dir) / cid / "prepared"
    public, private = prepared / "public", prepared / "private"
    gold = _inside(Path(data_dir) / dataset.get("gold_submission", dataset["answers"]), private, "answers file")
    if public_sample is None:
        sample = Path(data_dir) / dataset["sample_submission"]
        if public.resolve() not in sample.resolve().parents:
            raise Refused(f"{cid}: config.yaml's sample submission is not in public/; name a public copy")
    else:
        sample = public / public_sample
    return cid, public, private, gold, _inside(sample, public, "sample submission")


def agent_context(out, public, agent_files, base):
    _copy_tree(public, out / "data")
    _copy_tree(agent_files, out / "tools")
    (out / "Dockerfile").write_text(
        f"FROM {base}\nRUN bash -c true\nCOPY data/ {AGENT_DATA}/\nCOPY tools/ /home/\n"
        f"RUN mkdir -p {SUBMISSION_DIR}\n")


def verifier_context(out, cid, private, competition, verifier_files, base):
    _copy_tree(verifier_files, out / "tests")
    _copy_tree(private, out / "data" / cid / "prepared" / "private")
    _copy_tree(competition, out / "competition")
    (out / "Dockerfile").write_text(
        f"FROM {base}\nRUN bash -c true\nCOPY tests/ /tests/\nCOPY data/ {VERIFIER_DATA}/\n"
        f"COPY competition/ /grader/{cid}/\n"
        f"ENV MLE_COMPETITION_ID={cid} MLE_DATA_DIR={VERIFIER_DATA} MLE_GRADER_DIR=/grader/{cid}\n"
        f"WORKDIR {GRADER_WORK}\n")


def task_toml(family, cid, cls, images):
    limits, verifier = family["classes"][cls], family["verifier"]
    return (f"# {family['canary']}\n"
            f'schema_version = "1.4"\nartifacts = ["{SUBMISSION_DIR}/"]\n\n'
            f'[task]\nname = "mle-bench/{cid}"\nversion = "{family["benchmark"]["commit"][:7]}"\n\n'
            f'[verifier]\ntimeout_sec = {verifier["timeout_sec"]}\nenvironment_mode = "separate"\n\n'
            f'[verifier.environment]\ncpus = {verifier["cpus"]}\nmemory_mb = {verifier["memory_mb"]}\n'
            f'docker_image = "{images["verifier"]}"\n\n'
            f'[agent]\ntimeout_sec = {family["agent_timeout_sec"]}\n\n'
            f'[environment]\ncpus = {limits["cpus"]}\nmemory_mb = {limits["memory_mb"]}\n'
            f'docker_image = "{images["agent"]}"\n')


def instruction(family, cls, competition):
    header = string.Template((KIT / "instructions.md").read_text()).substitute(
        data=AGENT_DATA, submission=SUBMISSION_DIR + "/submission.csv", validator=VALIDATOR,
        hardware=family["classes"][cls]["hardware"], hours=f"{family['agent_timeout_sec'] / 3600:g}")
    return header + (Path(competition) / "description.md").read_text()


def package(out, toml, text, submission=None):
    out.mkdir(parents=True)
    (out / "task.toml").write_text(toml)
    (out / "instruction.md").write_text(text)
    if submission is not None:
        _copy(submission, out / "solution" / "submission.csv")
        solve = out / "solution" / "solve.sh"
        solve.write_text(f"#!/bin/bash\nset -euo pipefail\nmkdir -p {SUBMISSION_DIR}\n"
                         f"cp /solution/submission.csv {SUBMISSION_DIR}/submission.csv\n")
        solve.chmod(0o755)


def wrap(competition, data_dir, out, *, cls, agent_base, verifier_base, public_sample=None,
         agent_files=KIT / "agent", verifier_files=KIT / "verifier", family=None):
    """Write the two build contexts and the three packages under out; returns {"competition", "class",
    "images": {"agent", "verifier"}, "digests": {LAYOUT key: "sha256:<hex>"}}."""
    family = family or json.loads((KIT / "family.json").read_text())
    out = Path(out)
    if out.exists():
        raise Refused(f"{out}: the output directory exists")
    if cls not in family["classes"]:
        raise Refused(f"{cls}: not a class of family.json")
    cid, public, private, gold, sample = competition_files(competition, data_dir, public_sample)
    paths = {k: out / v for k, v in LAYOUT.items()}
    agent_context(paths["agent_context"], public, agent_files, agent_base)
    verifier_context(paths["verifier_context"], cid, private, competition, verifier_files, verifier_base)
    images = {k: f"localhost/mle-bench/{cid}-{k}:{digest(paths[k + '_context'])[7:23]}" for k in ("agent", "verifier")}
    toml, text = task_toml(family, cid, cls, images), instruction(family, cls, competition)
    for key, submission in (("attempt", None), ("answers", gold), ("sample", sample)):
        package(paths[key], toml, text, submission)
    return {"competition": cid, "class": cls, "images": images, "digests": {k: digest(p) for k, p in paths.items()}}


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for name in ("competition", "data_dir", "out"):
        p.add_argument(name, type=Path)
    p.add_argument("--class", dest="cls", required=True)
    p.add_argument("--agent-base", required=True)
    p.add_argument("--verifier-base", required=True)
    p.add_argument("--public-sample")
    a = p.parse_args(argv)
    try:
        record = wrap(a.competition, a.data_dir, a.out, cls=a.cls, agent_base=a.agent_base,
                      verifier_base=a.verifier_base, public_sample=a.public_sample)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(json.dumps(record, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
