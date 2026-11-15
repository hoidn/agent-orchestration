"""MLE-bench family plan, Task 1: the synthetic fixture and the task wrapper (experiments/mle_bench_tasks/wrap.py)."""

import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "experiments" / "fixtures" / "mle_bench"
TINY = FIXTURES / "tiny-tabular"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree(root):
    """Every file under root by relative path, bytecode caches left out (importing the fixture's grader makes one)."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def test_the_generator_rebuilds_the_committed_fixture_byte_for_byte(tmp_path):
    subprocess.run([sys.executable, "-I", str(FIXTURES / "make_tiny_tabular.py"), str(tmp_path)], check=True)
    assert _tree(tmp_path / "tiny-tabular") == _tree(TINY)


def _grade(submission_csv):
    """The fixture's grading function on a submission file, against its answers (exec'd: no bytecode cache)."""
    import pandas as pd
    namespace = {}
    exec(compile((TINY / "competition" / "grade.py").read_text(), "grade.py", "exec"), namespace)
    answers = pd.read_csv(TINY / "prepared" / "private" / "answers.csv")
    return namespace["grade"](pd.read_csv(submission_csv), answers)


def test_the_fixture_answers_beat_every_team_and_its_sample_scores_below_the_last():
    scores = [float(r["score"]) for r in csv.DictReader((TINY / "competition" / "leaderboard.csv").open())]
    assert (len(scores), scores == sorted(scores, reverse=True)) == (20, True)
    answers, sample = (_grade(TINY / "prepared" / p) for p in ("private/answers.csv", "public/sample_submission.csv"))
    assert (answers, sample, answers > scores[0], sample < scores[-1]) == (1.0, 0.5, True, True)


# --- the wrapper -------------------------------------------------------------------------------------------------

KIT = ROOT / "experiments" / "mle_bench_tasks"
FAMILY = json.loads((KIT / "family.json").read_text())
PUBLIC = TINY / "prepared" / "public"
PRIVATE_SOURCES = [TINY / "prepared" / "private", TINY / "competition"]  # the answers, the grader, the leaderboard


@pytest.fixture(scope="module")
def wrap():
    return _load(KIT / "wrap.py", "mle_bench_wrap")


@pytest.fixture
def tools(tmp_path):
    """Stand-ins for the kit's agent/ and verifier/ files (plan Task 2 writes the real ones)."""
    for rel, text in {"agent/validate_submission.py": "# format check\n", "verifier/test.sh": "#!/bin/bash\n"}.items():
        (tmp_path / "tools" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "tools" / rel).write_text(text)
    return tmp_path / "tools"


IMAGES = {"agent": "localhost/mle-bench/tiny-agent@sha256:" + "a" * 64,
          "verifier": "localhost/mle-bench/tiny-verifier@sha256:" + "b" * 64}  # fixed fake digest references


def _run(wrap, tools, out, cls="cpu", competition=TINY / "competition", data=FIXTURES, name="tiny", images=IMAGES,
         **kw):
    """Both steps, as a caller runs them: the two contexts, then (once their images exist) the three packages."""
    built = wrap.contexts(competition, data, out, agent_base="localhost/stand-in/agent-base:1",
                          verifier_base="localhost/stand-in/verifier-base:1", agent_files=tools / "agent",
                          verifier_files=tools / "verifier", **kw)
    packed = wrap.packages(competition, data, out, name=name, cls=cls, agent_image=images["agent"],
                           verifier_image=images["verifier"], **kw)
    return {**packed, "digests": {**built["digests"], **packed["digests"]}}


def _sha_names(*roots):
    """{sha256: [file names]} over every file under the roots."""
    out = {}
    for p in (p for r in roots for p in sorted(r.rglob("*")) if p.is_file()):
        out.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), []).append(p.name)
    return out


def _shas(*roots):
    return set(_sha_names(*roots))


def _files(root):
    return [p for p in sorted(root.rglob("*")) if p.is_file()]


def test_the_agent_context_and_the_attempt_package_hold_no_private_grader_or_leaderboard_file(wrap, tools, tmp_path):
    """By SHA-256, against every file of private/ and of the competition directory (its grader and leaderboard),
    less the files that are byte for byte a public file: the description only, which the agent is meant to read."""
    _run(wrap, tools, tmp_path / "out")
    sources, public = _sha_names(*PRIVATE_SOURCES), _shas(PUBLIC)
    exempt = sorted(n for sha, names in sources.items() if sha in public for n in names)
    withheld = set(sources) - public
    given = _shas(tmp_path / "out" / "agent-context", tmp_path / "out" / "attempt")
    verifier = _shas(tmp_path / "out" / "verifier-context")
    assert (exempt, given & withheld, withheld <= verifier) == (["description.md"], set(), True)


def test_no_file_given_to_the_agent_holds_the_answers_rows_under_another_name(wrap, tools, tmp_path):
    _run(wrap, tools, tmp_path / "out")
    rows = set((TINY / "prepared" / "private" / "answers.csv").read_text().splitlines()[1:])
    def holding(root):
        return [p.name for p in _files(root) if rows & set(p.read_text().splitlines())]
    given = holding(tmp_path / "out" / "agent-context") + holding(tmp_path / "out" / "attempt")
    assert (given, holding(tmp_path / "out" / "answers" / "solution")) == ([], ["submission.csv"])


def test_the_attempt_package_holds_task_toml_and_the_instruction_only(wrap, tools, tmp_path):
    _run(wrap, tools, tmp_path / "out")
    assert sorted(_tree(tmp_path / "out" / "attempt")) == ["instruction.md", "task.toml"]


@pytest.mark.parametrize("cls", ["cpu", "gpu"])
def test_task_toml_carries_the_limits_the_artifact_both_images_and_the_canary_and_no_network_key(
        wrap, tools, tmp_path, cls):
    _run(wrap, tools, tmp_path / "out", cls=cls)
    text = (tmp_path / "out" / "attempt" / "task.toml").read_text()
    toml = tomllib.loads(text)
    limits, verifier = FAMILY["classes"][cls], FAMILY["verifier"]
    seen = {"agent": toml["agent"], "environment": toml["environment"],
            "verifier": toml["verifier"], "artifacts": toml["artifacts"],
            "canary": [line for line in text.splitlines() if line == "# " + FAMILY["canary"]],
            "agent_lines": text.splitlines().count("[agent]")}
    assert seen == {
        "agent": {"timeout_sec": FAMILY["agent_timeout_sec"]},
        "environment": {"cpus": limits["cpus"], "memory_mb": limits["memory_mb"],
                        "docker_image": IMAGES["agent"]},
        "verifier": {"timeout_sec": verifier["timeout_sec"], "environment_mode": "separate",
                     "environment": {"cpus": verifier["cpus"], "memory_mb": verifier["memory_mb"],
                                     "docker_image": IMAGES["verifier"]}},
        "artifacts": [wrap.SUBMISSION_DIR + "/"], "canary": ["# " + FAMILY["canary"]], "agent_lines": 1}


def test_the_package_is_named_by_the_short_name_and_never_by_the_slug(wrap, tools, tmp_path):
    record = _run(wrap, tools, tmp_path / "out")
    text = (tmp_path / "out" / "attempt" / "task.toml").read_text()
    assert (tomllib.loads(text)["task"]["name"], record["name"], record["competition"], "tiny-tabular" in text) == (
        "mle-bench/tiny", "tiny", "tiny-tabular", False)


@pytest.mark.parametrize("name", ["tiny-tabular-x", "Tiny", "tiny_tab", "-tiny", ""])
def test_a_task_name_outside_the_rule_is_refused(wrap, tools, tmp_path, name):
    with pytest.raises(wrap.Refused, match="name"):
        _run(wrap, tools, tmp_path / "out", name=name)


@pytest.mark.parametrize("which, ref", [("agent", "localhost/mle-bench/tiny-agent:1"),
                                        ("verifier", "localhost/mle-bench/tiny-verifier@sha256:" + "b" * 63),
                                        ("agent", "localhost/mle-bench/tiny-agent:1@sha256:" + "A" * 64)])
def test_an_image_reference_not_pinned_by_digest_is_refused(wrap, tools, tmp_path, which, ref):
    with pytest.raises(wrap.Refused, match="digest"):
        _run(wrap, tools, tmp_path / "out", images={**IMAGES, which: ref})
    assert not (tmp_path / "out" / "attempt").exists()


def test_no_table_of_task_toml_sets_a_network_or_gpu_key(wrap, tools, tmp_path):
    _run(wrap, tools, tmp_path / "out", cls="gpu")
    toml = tomllib.loads((tmp_path / "out" / "attempt" / "task.toml").read_text())
    tables = [toml["agent"], toml["environment"], toml["verifier"], toml["verifier"]["environment"]]
    keys = {"network_mode", "allowed_hosts", "allow_internet", "gpus"}
    assert [sorted(keys & set(t)) for t in tables] == [[], [], [], []]


@pytest.mark.parametrize("leg, source", [("answers", TINY / "prepared" / "private" / "answers.csv"),
                                         ("sample", TINY / "prepared" / "public" / "sample_submission.csv")])
def test_a_leg_package_differs_from_the_attempt_package_only_by_its_solution_directory(
        wrap, tools, tmp_path, leg, source):
    _run(wrap, tools, tmp_path / "out")
    attempt, package = _tree(tmp_path / "out" / "attempt"), _tree(tmp_path / "out" / leg)
    outside = {k: v for k, v in package.items() if not k.startswith("solution/")}
    assert (outside == attempt, sorted(set(package) - set(outside)),
            package["solution/submission.csv"] == source.read_bytes()) == (
        True, ["solution/solve.sh", "solution/submission.csv"], True)


def test_the_same_input_gives_the_same_digests_at_two_output_paths(wrap, tools, tmp_path):
    first = _run(wrap, tools, tmp_path / "a" / "out")
    second = _run(wrap, tools, tmp_path / "b" / "deeper" / "out")
    recomputed = {k: wrap.digest(tmp_path / "a" / "out" / wrap.LAYOUT[k]) for k in first["digests"]}
    assert (first == second, recomputed == first["digests"], sorted(first["digests"])) == (
        True, True, ["agent_context", "answers", "attempt", "sample", "verifier_context"])


def test_the_digest_is_harbors_package_content_hash(wrap, tmp_path):
    """Harbor's Packager.compute_content_hash: sha256 over '<posix relative path>\\0<file sha256>\\n', sorted."""
    files = {"task.toml": b"t", "instruction.md": b"i", "solution/solve.sh": b"s"}
    (tmp_path / "p" / "solution").mkdir(parents=True)
    for rel, data in files.items():
        (tmp_path / "p" / rel).write_bytes(data)
    lines = "".join(f"{rel}\0{hashlib.sha256(data).hexdigest()}\n" for rel, data in sorted(files.items()))
    assert wrap.digest(tmp_path / "p") == "sha256:" + hashlib.sha256(lines.encode()).hexdigest()


def test_bytecode_caches_in_the_inputs_change_nothing(wrap, tools, tmp_path):
    plain = _run(wrap, tools, tmp_path / "plain")
    copy = tmp_path / "data" / "tiny-tabular"
    shutil.copytree(TINY, copy)
    for d in (copy / "competition", copy / "prepared" / "public"):
        (d / "__pycache__").mkdir()
        (d / "__pycache__" / "grade.cpython-313.pyc").write_bytes(b"\x00machine-specific")
    cached = _run(wrap, tools, tmp_path / "cached", competition=copy / "competition", data=tmp_path / "data")
    assert cached["digests"] == plain["digests"]


def test_the_instruction_is_the_kit_header_then_the_competition_description(wrap, tools, tmp_path):
    _run(wrap, tools, tmp_path / "out")
    instruction = (tmp_path / "out" / "attempt" / "instruction.md").read_text()
    head, description = instruction.split((TINY / "competition" / "description.md").read_text())
    named = [p for p in (wrap.AGENT_DATA, wrap.SUBMISSION_DIR + "/submission.csv", wrap.VALIDATOR) if p in head]
    assert (description, len(named), "localhost" in head, "${" in head) == ("", 3, False, False)


def test_a_sample_submission_in_the_private_directory_needs_a_named_public_copy(wrap, tools, tmp_path):
    copy = tmp_path / "data" / "tiny-tabular"
    shutil.copytree(TINY, copy)
    config = copy / "competition" / "config.yaml"
    config.write_text(config.read_text().replace("prepared/public/sample_submission.csv",
                                                 "prepared/private/sample_submission.csv"))
    shutil.copy(copy / "prepared" / "public" / "sample_submission.csv", copy / "prepared" / "private")
    with pytest.raises(wrap.Refused, match="public"):
        _run(wrap, tools, tmp_path / "refused", competition=copy / "competition", data=tmp_path / "data")
    _run(wrap, tools, tmp_path / "out", competition=copy / "competition", data=tmp_path / "data",
         public_sample="sample_submission.csv")
    sample = (tmp_path / "out" / "sample" / "solution" / "submission.csv").read_bytes()
    assert sample == (copy / "prepared" / "public" / "sample_submission.csv").read_bytes()


def test_a_symbolic_link_in_the_public_directory_is_refused(wrap, tools, tmp_path):
    copy = tmp_path / "data" / "tiny-tabular"
    shutil.copytree(TINY, copy)
    (copy / "prepared" / "public" / "extra.csv").symlink_to(copy / "prepared" / "private" / "answers.csv")
    with pytest.raises(wrap.Refused, match="link"):
        _run(wrap, tools, tmp_path / "out", competition=copy / "competition", data=tmp_path / "data")


@pytest.mark.parametrize("existing", ["agent-context", "attempt"])
def test_an_existing_output_directory_is_refused(wrap, tools, tmp_path, existing):
    (tmp_path / "out" / existing).mkdir(parents=True)
    with pytest.raises(wrap.Refused, match="exists"):
        _run(wrap, tools, tmp_path / "out")


def test_family_json_lists_the_thirteen_candidates_in_the_plans_order_three_on_the_cpu():
    rows = [(c["order"], c["slug"], c["class"]) for c in FAMILY["candidates"]]
    assert ([r[0] for r in rows], [r[1] for r in rows if r[2] == "cpu"], len(rows)) == (
        list(range(1, 14)), ["leaf-classification", "text-normalization-challenge-russian-language",
                             "mlsp-2013-birds"], 13)


def test_every_task_name_is_unique_short_and_of_lower_case_letters_digits_and_hyphens(wrap):
    names = [c["name"] for c in FAMILY["candidates"]]
    assert ([n for n in names if not wrap.NAME.fullmatch(n)], len(set(names)), wrap.NAME.pattern) == (
        [], 13, "[a-z0-9][a-z0-9-]{0,11}")


def test_every_size_figure_is_a_number_from_a_named_source_or_unknown_with_a_reason():
    def ok(size):
        figures = {k: v for k, v in size.items() if k != "unknown_because"}
        known = all(isinstance(v, (int, float)) for v in figures.values())
        unknown = all(v is None for v in figures.values()) and bool(size.get("unknown_because"))
        return set(figures) <= set(FAMILY["size_sources"]) and known != unknown
    unknown = [c["slug"] for c in FAMILY["candidates"] if "unknown_because" in c["size_gb"]]
    assert ([c["slug"] for c in FAMILY["candidates"] if not ok(c["size_gb"])], unknown) == (
        [], ["text-normalization-challenge-russian-language"])
