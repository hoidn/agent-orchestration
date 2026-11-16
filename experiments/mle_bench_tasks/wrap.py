"""Turn one prepared MLE-bench competition into Harbor task packages and image build contexts (family plan, Task 1).

Two steps, because a package names its images by digest and an image exists only once its context is built:

  python wrap.py contexts <competition dir> <data dir> <out dir> --agent-base <image> --verifier-base <image>
                          [--public-sample <file in public/>]
  (a later task builds the two images and reads their digest references)
  python wrap.py packages <competition dir> <data dir> <out dir> --name <task name> --class cpu|gpu
                          --agent-image <ref@sha256:...> --verifier-image <ref@sha256:...> [--public-sample ...]

Each prints the record contexts() or packages() returns, as JSON. A refusal prints one line,
"refused: <code>: <message>", and exits 2; Refused.code is the reason.

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
  agent_files, verifier_files   the kit's agent/ and verifier/ directories (plan Task 2's files).

Output, written under <out dir>; each directory below must not exist yet (LAYOUT holds the names):
  agent-context/     Dockerfile, data/ (every file of public/), tools/ (agent_files). Built from public/ alone:
                     nothing of private/, of the competition directory or of the leaderboard (plan M3).
  verifier-context/  Dockerfile, tests/ (verifier_files), data/<id>/prepared/private/ (every file of private/),
                     competition/ (every file of the competition directory, copied in the image to where the
                     benchmark's registry finds it, COMPETITIONS/<id>/).
  attempt/           task.toml and instruction.md: the package an attempt runs, named mle-bench/<task name>. The
                     task name is short (NAME): the launcher derives socket paths from it. The competition's id
                     (its Kaggle slug) stays where the benchmark's code needs it, in the verifier context.
  answers/, sample/  the attempt package plus solution/ (solve.sh and the submission it copies): the answers (or
                     the gold submission) and the public sample submission, for the qualification legs (plan M2).

Withholding holds by construction and by itself (plan M3): public/ and agent_files may neither equal, contain nor
lie inside private/ or the competition directory; no input root and no file under one may be a symbolic link;
every name and every input is checked before anything is written. A hard link cannot be told from a copy here;
the check on the built image (plan Task 3) is the second guard.

It builds no image, runs no container and downloads nothing. Every digest is Harbor's package content hash over
the bytes of the files (digest()); bytecode caches are never copied, and no path outside an output directory and
no time enters a digest, so the same input gives the same digests anywhere. Text is read and written as UTF-8
whatever the locale. Modes are normalised whatever the umask: directories 0755, files 0644, and 0755 for solve.sh
and for a copied file with an execute bit. The image references are written into task.toml as given and must be
pinned by digest (PINNED): the launcher compares them as strings, so a tag alone would let a rebuilt image pass.
"""

import argparse
import hashlib
import json
import re
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
VALIDATOR = "/home/validate_submission.py"  # the agent-side format check (plan M3; Task 2's file)
VERIFIER_DATA = "/private/data"  # in the verifier image: the grader's data directory, <id>/prepared/private/
COMPETITIONS = "/opt/mle-bench/mlebench/competitions"  # where the benchmark's registry finds a competition (Task 2)
GRADER_WORK = "/grader-work"  # the grader's working directory: it writes a cache where it runs (scout report B)
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,11}")  # a task name: the launcher's socket paths are at most 107 bytes
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")  # a competition id as config.yaml gives it (a Kaggle slug)
PINNED = re.compile(r"(?:[a-z0-9][a-z0-9.-]*(?::[0-9]+)?/)?[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}")


class Refused(Exception):
    """The wrapper refuses. code: str, a short reason; the message names the input at fault. Every refusal comes
    before anything is written."""

    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


def digest(root):
    """Path -> 'sha256:<hex>'. Harbor's Packager.compute_content_hash of a directory: SHA-256 over
    '<relative path>\\0<sha256>\\n' per file of _files(root), sorted by POSIX relative path."""
    outer = hashlib.sha256()
    for path in sorted(_files(root), key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        outer.update(f"{rel}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode("utf-8"))
    return "sha256:" + outer.hexdigest()


def _files(root):
    """Path -> [Path]: every file under root, bytecode caches left out. Refused (symbolic_link) for a link anywhere
    under root, (name_not_utf8) for a name UTF-8 cannot encode."""
    out = []
    for path in sorted(Path(root).rglob("*")):
        try:
            path.relative_to(root).as_posix().encode("utf-8")
        except UnicodeEncodeError:
            raise Refused("name_not_utf8", f"{_shown(path)}: a file name that is not UTF-8") from None
        if path.is_symlink():
            raise Refused("symbolic_link", f"{_shown(path)}: a symbolic link; inputs must be plain files")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            out.append(path)
    return out


def _shown(path):
    """Path -> str safe to print under any locale."""
    return str(path).encode("ascii", "backslashreplace").decode("ascii")


def _text(path):
    """Path -> str: the file's text as UTF-8. Refused (not_utf8, unreadable) names the path."""
    try:
        return Path(path).read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("not_utf8", f"{_shown(path)}: not UTF-8 text") from None
    except OSError as e:
        raise Refused("unreadable", f"{_shown(path)}: {e.strerror}") from None


def _write(path, text, mode=0o644):
    """Write str text to Path path as UTF-8 with the given mode, making its directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    path.chmod(mode)


def _copy(src, dst):
    """Copy file src to dst by bytes; mode 0755 if src has an execute bit, else 0644."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    dst.chmod(0o755 if src.stat().st_mode & 0o111 else 0o644)


def _normalise_dirs(root):
    """Set mode 0755 on root and on every directory under it (mkdir follows the umask)."""
    for path in [root, *root.rglob("*")]:
        if path.is_dir():
            path.chmod(0o755)


def _overlap(a, b):
    """True when Paths a and b resolve to the same directory or one lies inside the other."""
    a, b = Path(a).resolve(), Path(b).resolve()
    return a == b or a in b.parents or b in a.parents


def _separate(given, withheld):
    """Refused (aliased_input) when any path the agent is given overlaps any withheld path."""
    for g in given:
        for w in withheld:
            if _overlap(g, w):
                raise Refused("aliased_input", f"{_shown(g)} and {_shown(w)}: what the agent is given overlaps "
                                               "what is withheld")


def _plain(*roots):
    """Refused (symbolic_link) when an input root is itself a symbolic link."""
    for root in roots:
        if Path(root).is_symlink():
            raise Refused("symbolic_link", f"{_shown(root)}: an input root that is a symbolic link")


def _inside(path, root, code):
    """Path -> resolved Path, a file inside root; else Refused(code)."""
    resolved, top = Path(path).resolve(), Path(root).resolve()
    if not resolved.is_file() or top not in resolved.parents:
        raise Refused(code, f"{_shown(path)}: not a file in {_shown(root)}")
    return resolved


def _config(competition):
    """Competition dir -> (id, answers, gold submission or None, sample submission), the three paths relative to
    the data directory, from config.yaml. Refused (bad_config, not_utf8, unreadable) names the file."""
    path = Path(competition) / "config.yaml"
    try:
        config = yaml.safe_load(_text(path))
        dataset = config["dataset"]
        fields = (config["id"], dataset["answers"], dataset.get("gold_submission"), dataset["sample_submission"])
    except (yaml.YAMLError, KeyError, TypeError, AttributeError) as e:
        raise Refused("bad_config", f"{_shown(path)}: {type(e).__name__}: {e}") from None
    if not (isinstance(fields[0], str) and SLUG.fullmatch(fields[0])) or not all(
            isinstance(f, str) for f in fields if f is not None):
        raise Refused("bad_config", f"{_shown(path)}: the id must be a slug and the dataset fields paths")
    return fields


def competition_files(competition, data_dir, public_sample=None):
    """(competition dir, data dir, public_sample: str or None) -> (id, public dir, private dir, answers or gold
    submission, public sample submission). Reads config.yaml; refuses aliased or linked roots and a sample outside
    public/ (a private one needs public_sample, relative to public/)."""
    cid, answers, gold, sample = _config(competition)
    prepared = Path(data_dir) / cid / "prepared"
    public, private = prepared / "public", prepared / "private"
    _separate([public], [private, competition])
    _plain(competition, data_dir, Path(data_dir) / cid, prepared, public, private)
    gold = _inside(Path(data_dir) / (gold or answers), private, "answers_not_private")
    sample = Path(data_dir) / sample if public_sample is None else public / public_sample
    return cid, public, private, gold, _inside(sample, public, "sample_not_public")


def agent_dockerfile(base):
    """str image -> the agent image's Dockerfile: public data in AGENT_DATA, the tools in /home/."""
    return (f"FROM {base}\nRUN bash -c true\nCOPY data/ {AGENT_DATA}/\nCOPY tools/ /home/\n"
            f"RUN mkdir -p {SUBMISSION_DIR}\n")


def verifier_dockerfile(cid, base):
    """(id, str image) -> the verifier image's Dockerfile: the tests in /tests/, the answers under VERIFIER_DATA,
    the competition in COMPETITIONS/<id>/, the variables Task 2's grade_submission.py reads."""
    return (f"FROM {base}\nRUN bash -c true\nCOPY tests/ /tests/\nCOPY data/ {VERIFIER_DATA}/\n"
            f"COPY competition/ {COMPETITIONS}/{cid}/\n"
            f"ENV MLE_COMPETITION_ID={cid} MLE_DATA_DIR={VERIFIER_DATA}\nWORKDIR {GRADER_WORK}\n")


def task_toml(family, name, cls, images):
    """(family.json dict, task name, class, {"agent", "verifier": reference}) -> task.toml text. Reads family's
    canary, benchmark.commit, agent_timeout_sec, verifier and classes[cls]. The verifier has no network
    (allow_internet = false, the Terminal-Bench packages' form); no table carries network_mode or allowed_hosts."""
    limits, verifier = family["classes"][cls], family["verifier"]
    return (f"# {family['canary']}\n"
            f'schema_version = "1.4"\nartifacts = ["{SUBMISSION_DIR}/"]\n\n'
            f'[task]\nname = "mle-bench/{name}"\nversion = "{family["benchmark"]["commit"][:7]}"\n\n'
            f'[verifier]\ntimeout_sec = {verifier["timeout_sec"]}\nenvironment_mode = "separate"\n\n'
            f'[verifier.environment]\ncpus = {verifier["cpus"]}\nmemory_mb = {verifier["memory_mb"]}\n'
            f'allow_internet = false\ndocker_image = "{images["verifier"]}"\n\n'
            f'[agent]\ntimeout_sec = {family["agent_timeout_sec"]}\n\n'
            f'[environment]\ncpus = {limits["cpus"]}\nmemory_mb = {limits["memory_mb"]}\n'
            f'docker_image = "{images["agent"]}"\n')


def instruction(family, cls, competition):
    """(family.json dict, class, competition dir) -> the instruction: KIT/instructions.md filled from family and
    the in-image paths, then the competition's description.md."""
    header = string.Template(_text(KIT / "instructions.md")).substitute(
        data=AGENT_DATA, submission=SUBMISSION_DIR + "/submission.csv", validator=VALIDATOR,
        hardware=family["classes"][cls]["hardware"], hours=f"{family['agent_timeout_sec'] / 3600:g}")
    return header + _text(Path(competition) / "description.md")


def package(out, toml, text, submission=None):
    """Write a package at Path out: task.toml, instruction.md and, with a submission file, solution/."""
    _write(out / "task.toml", toml)
    _write(out / "instruction.md", text)
    if submission is not None:
        _copy(submission, out / "solution" / "submission.csv")
        _write(out / "solution" / "solve.sh", f"#!/bin/bash\nset -euo pipefail\nmkdir -p {SUBMISSION_DIR}\n"
                                              f"cp /solution/submission.csv {SUBMISSION_DIR}/submission.csv\n", 0o755)
    _normalise_dirs(out)


def _fresh(out, keys):
    """{LAYOUT key: Path under out}; Refused (output_exists) when one exists."""
    paths = {k: Path(out) / LAYOUT[k] for k in keys}
    for path in paths.values():
        if path.exists():
            raise Refused("output_exists", f"{_shown(path)}: the output directory exists")
    return paths


def contexts(competition, data_dir, out, *, agent_base, verifier_base, public_sample=None,
             agent_files=KIT / "agent", verifier_files=KIT / "verifier"):
    """Write the two build contexts under out; returns {"competition": id, "digests": {"agent_context",
    "verifier_context": "sha256:<hex>"}}. Reads config.yaml, the public and private directories, the competition
    directory and the two file directories; lists every input before writing anything."""
    cid, public, private, _, _ = competition_files(competition, data_dir, public_sample)
    _separate([agent_files], [private, competition])
    _plain(agent_files, verifier_files)
    for files in (agent_files, verifier_files):
        if not Path(files).is_dir():
            raise Refused("not_a_directory", f"{_shown(files)}: not a directory")
    paths = _fresh(out, ("agent_context", "verifier_context"))
    agent, verifier = paths["agent_context"], paths["verifier_context"]
    trees = [(public, agent / "data"), (agent_files, agent / "tools"), (verifier_files, verifier / "tests"),
             (private, verifier / "data" / cid / "prepared" / "private"), (competition, verifier / "competition")]
    listed = [(src, dst, _files(src)) for src, dst in trees]
    for src, dst, files in listed:
        for path in files:
            _copy(path, dst / path.relative_to(src))
    _write(agent / "Dockerfile", agent_dockerfile(agent_base))
    _write(verifier / "Dockerfile", verifier_dockerfile(cid, verifier_base))
    for path in paths.values():
        _normalise_dirs(path)
    return {"competition": cid, "digests": {k: digest(p) for k, p in paths.items()}}


def packages(competition, data_dir, out, *, name, cls, agent_image, verifier_image, public_sample=None,
             family=None):
    """Write the attempt, answers and sample packages under out; returns {"name", "competition", "class",
    "images": {"agent", "verifier"}, "digests": {"attempt", "answers", "sample": "sha256:<hex>"}}. Reads
    family.json (unless given), instructions.md, config.yaml, description.md, the answers and the sample."""
    family = family or json.loads(_text(KIT / "family.json"))
    if not (isinstance(name, str) and NAME.fullmatch(name)):
        raise Refused("bad_name", f"{name!r}: a task name is 1 to 12 lower-case letters, digits and hyphens, "
                                  "not first a hyphen")
    if cls not in family["classes"]:
        raise Refused("unknown_class", f"{cls!r}: not a class of family.json")
    images = {"agent": agent_image, "verifier": verifier_image}
    for which, ref in images.items():
        if not (isinstance(ref, str) and PINNED.fullmatch(ref)):
            raise Refused("unpinned_image", f"{ref!r}: the {which} image reference is not <name>@sha256:<64 hex>")
    cid, _, _, gold, sample = competition_files(competition, data_dir, public_sample)
    toml, text = task_toml(family, name, cls, images), instruction(family, cls, competition)
    paths = _fresh(out, ("attempt", "answers", "sample"))
    for key, submission in (("attempt", None), ("answers", gold), ("sample", sample)):
        package(paths[key], toml, text, submission)
    return {"name": name, "competition": cid, "class": cls, "images": images,
            "digests": {k: digest(p) for k, p in paths.items()}}


def _parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="step", required=True)
    for step, options in (("contexts", ("--agent-base", "--verifier-base")),
                          ("packages", ("--name", "--class", "--agent-image", "--verifier-image"))):
        q = sub.add_parser(step)
        for name in ("competition", "data_dir", "out"):
            q.add_argument(name, type=Path)
        for option in options:
            q.add_argument(option, required=True, dest=option[2:].replace("-", "_").replace("class", "cls"))
        q.add_argument("--public-sample")
    return p


def main(argv):
    """The command line; 0 with the record as JSON on stdout, 2 with one refusal line on stderr."""
    a = vars(_parser().parse_args(argv))
    step = {"contexts": contexts, "packages": packages}[a.pop("step")]
    try:
        record = step(a.pop("competition"), a.pop("data_dir"), a.pop("out"), **a)
    except Refused as e:
        print(f"refused: {_shown(e)}", file=sys.stderr)
        return 2
    print(json.dumps(record, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
