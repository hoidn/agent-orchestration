"""MLE-bench family plan, Task 1: the synthetic fixture and the task wrapper (experiments/mle_bench_tasks/wrap.py)."""

import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import statistics
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


def _scores():
    return [r["score"] for r in csv.DictReader((TINY / "competition" / "leaderboard.csv").open())]


def test_the_fixture_answers_beat_every_team_and_its_sample_scores_below_the_last():
    scores = [float(s) for s in _scores()]
    assert (len(scores), scores == sorted(scores, reverse=True)) == (20, True)
    answers, sample = (_grade(TINY / "prepared" / p) for p in ("private/answers.csv", "public/sample_submission.csv"))
    assert (answers, sample, answers > scores[0], sample < scores[-1]) == (1.0, 0.5, True, True)


# --- the wrapper -------------------------------------------------------------------------------------------------

KIT = ROOT / "experiments" / "mle_bench_tasks"
FAMILY = json.loads((KIT / "family.json").read_text())
PUBLIC = TINY / "prepared" / "public"
PRIVATE_SOURCES = [TINY / "prepared" / "private", TINY / "competition"]  # the answers, the grader, the leaderboard
IMAGES = {"agent": "localhost/mle-bench/tiny-agent@sha256:" + "a" * 64,
          "verifier": "localhost/mle-bench/tiny-verifier@sha256:" + "b" * 64}  # fixed fake digest references
COMPETITION_IN_VERIFIER = "/opt/mle-bench/mlebench/competitions/tiny-tabular/"  # Task 2's report: the registry's place


@pytest.fixture(scope="module")
def wrap():
    return _load(KIT / "wrap.py", "mle_bench_wrap")


@pytest.fixture
def tools(tmp_path):
    """Stand-ins for the kit's agent/ and verifier/ files; the verifier's script is executable, as Task 2's is."""
    for rel, text in {"agent/validate_submission.py": "# format check\n", "verifier/test.sh": "#!/bin/bash\n"}.items():
        (tmp_path / "tools" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "tools" / rel).write_text(text)
    (tmp_path / "tools" / "verifier" / "test.sh").chmod(0o755)
    return tmp_path / "tools"


def _contexts(wrap, tools, out, competition=TINY / "competition", data=FIXTURES, **kw):
    if tools is not None:
        kw = {"agent_files": tools / "agent", "verifier_files": tools / "verifier", **kw}
    return wrap.contexts(competition, data, out, agent_base="localhost/stand-in/agent-base:1",
                         verifier_base="localhost/stand-in/verifier-base:1", **kw)


def _packages(wrap, out, competition=TINY / "competition", data=FIXTURES, name="tiny", cls="cpu", images=IMAGES,
              **kw):
    return wrap.packages(competition, data, out, name=name, cls=cls, agent_image=images["agent"],
                         verifier_image=images["verifier"], **kw)


def _run(wrap, tools, out, competition=TINY / "competition", data=FIXTURES, public_sample=None, **kw):
    """Both steps, as a caller runs them: the two contexts, then (once their images exist) the three packages."""
    built = _contexts(wrap, tools, out, competition, data, public_sample=public_sample)
    packed = _packages(wrap, out, competition, data, public_sample=public_sample, **kw)
    return {**packed, "digests": {**built["digests"], **packed["digests"]}}


def _code(wrap, call):
    """The reason code of the refusal the call ends in; any other exception fails the test."""
    with pytest.raises(wrap.Refused) as caught:
        call()
    return caught.value.code


def _copy(tmp_path):
    """A copy of the fixture's data directory and competition: (data dir, competition dir, tiny-tabular dir)."""
    copy = tmp_path / "data" / "tiny-tabular"
    shutil.copytree(TINY, copy)
    return tmp_path / "data", copy / "competition", copy


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


def test_no_leaderboard_number_and_no_line_of_the_grading_code_is_in_the_attempt_package(wrap, tools, tmp_path):
    """Every score of the snapshot, the medal lines (positions 2, 4 and 8 of twenty teams, the benchmark's rule) and
    the median, and every line of grade.py, against every file of the attempt package."""
    _run(wrap, tools, tmp_path / "out")
    scores = _scores()
    numbers = set(scores) | {f"{statistics.median(float(s) for s in scores):g}"}
    lines = {line.strip() for line in (TINY / "competition" / "grade.py").read_text().splitlines() if line.strip()}
    texts = [p.read_text() for p in _files(tmp_path / "out" / "attempt")]
    found = sorted(x for x in numbers | lines if any(x in t for t in texts))
    assert ({scores[1], scores[3], scores[7]} <= numbers, len(numbers), found) == (True, 21, [])


def test_the_attempt_package_holds_task_toml_and_the_instruction_only(wrap, tools, tmp_path):
    _run(wrap, tools, tmp_path / "out")
    assert sorted(_tree(tmp_path / "out" / "attempt")) == ["instruction.md", "task.toml"]


@pytest.mark.parametrize("cls", ["cpu", "gpu"])
def test_task_toml_carries_the_limits_the_artifact_both_images_and_the_canary(wrap, tools, tmp_path, cls):
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
        "environment": {"cpus": limits["cpus"], "memory_mb": limits["memory_mb"], "docker_image": IMAGES["agent"]},
        "verifier": {"timeout_sec": verifier["timeout_sec"], "environment_mode": "separate",
                     "environment": {"cpus": verifier["cpus"], "memory_mb": verifier["memory_mb"],
                                     "allow_internet": False, "docker_image": IMAGES["verifier"]}},
        "artifacts": [wrap.SUBMISSION_DIR + "/"], "canary": ["# " + FAMILY["canary"]], "agent_lines": 1}


def test_the_verifier_table_alone_carries_allow_internet_false(wrap, tools, tmp_path):
    _run(wrap, tools, tmp_path / "out", cls="gpu")
    toml = tomllib.loads((tmp_path / "out" / "attempt" / "task.toml").read_text())
    tables = {"agent": toml["agent"], "environment": toml["environment"], "verifier": toml["verifier"],
              "verifier.environment": toml["verifier"]["environment"]}
    assert {k: t.get("allow_internet", "absent") for k, t in tables.items()} == {
        "agent": "absent", "environment": "absent", "verifier": "absent", "verifier.environment": False}


def test_no_line_of_task_toml_sets_network_mode_allowed_hosts_or_gpus(wrap, tools, tmp_path):
    """The rule of the ladder's oracle_check.sh (a network_mode or allowed_hosts line anywhere is refused), and no
    gpus key, which Harbor refuses under Podman."""
    _run(wrap, tools, tmp_path / "out", cls="gpu")
    text = (tmp_path / "out" / "attempt" / "task.toml").read_text()
    assert [ln for ln in text.splitlines() if re.match(r"\s*(network_mode|allowed_hosts|gpus)\s*=", ln)] == []


def test_the_package_is_named_by_the_short_name_and_never_by_the_slug(wrap, tools, tmp_path):
    record = _run(wrap, tools, tmp_path / "out")
    text = (tmp_path / "out" / "attempt" / "task.toml").read_text()
    assert (tomllib.loads(text)["task"]["name"], record["name"], record["competition"], "tiny-tabular" in text) == (
        "mle-bench/tiny", "tiny", "tiny-tabular", False)


@pytest.mark.parametrize("name", ["tiny-tabular-x", "Tiny", "tiny_tab", "-tiny", ""])
def test_a_task_name_outside_the_rule_is_refused_before_any_file_is_written(wrap, tmp_path, name):
    assert (_code(wrap, lambda: _packages(wrap, tmp_path / "out", name=name)), (tmp_path / "out").exists()) == (
        "bad_name", False)


@pytest.mark.parametrize("which, ref", [
    ("agent", 'localhost/mle-bench/x"y@sha256:' + "a" * 64),
    ("agent", "localhost/mle-bench/x y@sha256:" + "a" * 64),
    ("verifier", "localhost/mle-bench/x\ny@sha256:" + "b" * 64),
    ("verifier", "localhost/mle-bench/tiny-verifier@sha256:" + "B" * 64),
    ("agent", "localhost/mle-bench/tiny-agent:1@sha256:" + "a" * 64),
    ("agent", "localhost/mle-bench/tiny-agent:1"),
    ("verifier", "localhost/mle-bench/tiny-verifier@sha256:" + "b" * 63),
    ("verifier", "localhost/mle-bench/tiny-verifier@sha256:" + "b" * 65),
    ("agent", "Localhost/mle-bench/tiny-agent@sha256:" + "a" * 64),
])
def test_an_image_reference_outside_the_pinned_form_is_refused_before_any_file_is_written(wrap, tmp_path, which, ref):
    code = _code(wrap, lambda: _packages(wrap, tmp_path / "out", images={**IMAGES, which: ref}))
    assert (code, (tmp_path / "out").exists()) == ("unpinned_image", False)


@pytest.mark.parametrize("ref", ["localhost/mle-bench/tiny-agent@sha256:" + "a" * 64,
                                 "localhost:5000/mle_bench/tiny.agent-2@sha256:" + "0123456789abcdef" * 4])
def test_a_pinned_reference_with_a_registry_port_dots_and_underscores_is_accepted(wrap, tmp_path, ref):
    record = _packages(wrap, tmp_path / "out", images={**IMAGES, "agent": ref})
    assert tomllib.loads((tmp_path / "out" / "attempt" / "task.toml").read_text())["environment"]["docker_image"] \
        == record["images"]["agent"] == ref


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


def test_the_verifier_context_places_the_competition_where_the_benchmarks_registry_finds_it(wrap, tools, tmp_path):
    _run(wrap, tools, tmp_path / "out")
    context = tmp_path / "out" / "verifier-context"
    lines = (context / "Dockerfile").read_text().splitlines()
    copies = dict(ln.split()[1:] for ln in lines if ln.startswith("COPY "))
    env = [ln for ln in lines if ln.startswith("ENV ")]
    assert (copies, env, _tree(context / "competition") == _tree(TINY / "competition")) == (
        {"tests/": "/tests/", "data/": "/private/data/", "competition/": COMPETITION_IN_VERIFIER},
        ["ENV MLE_COMPETITION_ID=tiny-tabular MLE_DATA_DIR=/private/data"], True)


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
    data, competition, copy = _copy(tmp_path)
    for d in (competition, copy / "prepared" / "public"):
        (d / "__pycache__").mkdir()
        (d / "__pycache__" / "grade.cpython-313.pyc").write_bytes(b"\x00machine-specific")
    cached = _run(wrap, tools, tmp_path / "cached", competition=competition, data=data)
    assert cached["digests"] == plain["digests"]


def _modes(out):
    """{path under out: (is a directory, mode)} for every output directory of LAYOUT and everything in it."""
    paths = [p for p in sorted(out.rglob("*"))]
    return {p.relative_to(out).as_posix(): (p.is_dir(), p.stat().st_mode & 0o7777) for p in paths}


def test_file_modes_are_normalised_whatever_the_umask(wrap, tools, tmp_path):
    seen = {}
    for mask in (0o022, 0o077):
        (tmp_path / f"out-{mask:o}").mkdir()
        previous = os.umask(mask)
        try:
            _run(wrap, tools, tmp_path / f"out-{mask:o}")
        finally:
            os.umask(previous)
        seen[mask] = _modes(tmp_path / f"out-{mask:o}")
    modes = seen[0o077]
    executable = sorted(k for k, (is_dir, mode) in modes.items() if not is_dir and mode == 0o755)
    assert (seen[0o022] == modes, {m for d, m in modes.values() if d}, {m for d, m in modes.values() if not d},
            executable) == (True, {0o755}, {0o644, 0o755},
                            ["answers/solution/solve.sh", "sample/solution/solve.sh", "verifier-context/tests/test.sh"])


def test_the_instruction_is_the_kit_header_then_the_competition_description(wrap, tools, tmp_path):
    _run(wrap, tools, tmp_path / "out")
    instruction = (tmp_path / "out" / "attempt" / "instruction.md").read_text()
    head, description = instruction.split((TINY / "competition" / "description.md").read_text())
    named = [p for p in (wrap.AGENT_DATA, wrap.SUBMISSION_DIR + "/submission.csv", wrap.VALIDATOR) if p in head]
    assert (description, len(named), "localhost" in head, "${" in head) == ("", 3, False, False)


def test_a_sample_submission_in_the_private_directory_needs_a_named_public_copy(wrap, tools, tmp_path):
    data, competition, copy = _copy(tmp_path)
    config = competition / "config.yaml"
    config.write_text(config.read_text().replace("prepared/public/sample_submission.csv",
                                                 "prepared/private/sample_submission.csv"))
    shutil.copy(copy / "prepared" / "public" / "sample_submission.csv", copy / "prepared" / "private")
    code = _code(wrap, lambda: _run(wrap, tools, tmp_path / "refused", competition=competition, data=data))
    _run(wrap, tools, tmp_path / "out", competition=competition, data=data, public_sample="sample_submission.csv")
    sample = (tmp_path / "out" / "sample" / "solution" / "submission.csv").read_bytes()
    assert (code, (tmp_path / "refused").exists(), sample) == (
        "sample_not_public", False, (copy / "prepared" / "public" / "sample_submission.csv").read_bytes())


def test_a_symbolic_link_inside_the_public_directory_is_refused(wrap, tools, tmp_path):
    data, competition, copy = _copy(tmp_path)
    (copy / "prepared" / "public" / "extra.csv").symlink_to(copy / "prepared" / "private" / "answers.csv")
    code = _code(wrap, lambda: _contexts(wrap, tools, tmp_path / "out", competition=competition, data=data))
    assert (code, (tmp_path / "out").exists()) == ("symbolic_link", False)


def test_a_public_directory_linked_to_the_private_one_is_refused_as_aliased(wrap, tools, tmp_path):
    """The independent review's case: public/ a symbolic link to private/, with the sample copied into private/."""
    data, competition, copy = _copy(tmp_path)
    public = copy / "prepared" / "public"
    shutil.copy(public / "sample_submission.csv", copy / "prepared" / "private")
    shutil.rmtree(public)
    public.symlink_to(copy / "prepared" / "private")
    codes = [_code(wrap, lambda: _contexts(wrap, tools, tmp_path / "out", competition=competition, data=data)),
             _code(wrap, lambda: _packages(wrap, tmp_path / "out", competition=competition, data=data))]
    assert (codes, (tmp_path / "out").exists()) == (["aliased_input", "aliased_input"], False)


@pytest.mark.parametrize("root", ["prepared/public", "prepared/private", "competition", "agent", "verifier"])
def test_a_root_input_that_is_a_symbolic_link_is_refused(wrap, tools, tmp_path, root):
    """Each root replaced by a link to a real copy elsewhere, which aliases nothing."""
    data, competition, copy = _copy(tmp_path)
    shutil.copytree(tools, copy / "agent-tools")
    source = {"agent": copy / "agent-tools" / "agent", "verifier": copy / "agent-tools" / "verifier"}.get(
        root, copy / root)
    elsewhere = tmp_path / "elsewhere" / source.name
    shutil.move(source, elsewhere)
    source.symlink_to(elsewhere)
    code = _code(wrap, lambda: _contexts(wrap, tools, tmp_path / "out", competition=competition, data=data,
                                   agent_files=copy / "agent-tools" / "agent",
                                   verifier_files=copy / "agent-tools" / "verifier"))
    assert (code, (tmp_path / "out").exists()) == ("symbolic_link", False)


@pytest.mark.parametrize("agent_files", ["prepared/private", "prepared", ".", "competition", "competition/sub"])
def test_agent_files_that_alias_the_private_or_grading_directory_are_refused(wrap, tools, tmp_path, agent_files):
    data, competition, copy = _copy(tmp_path)
    (competition / "sub").mkdir()
    code = _code(wrap, lambda: _contexts(wrap, tools, tmp_path / "out", competition=competition, data=data,
                                   agent_files=copy / agent_files))
    assert (code, (tmp_path / "out").exists()) == ("aliased_input", False)


def test_a_competition_directory_inside_the_public_directory_is_refused(wrap, tools, tmp_path):
    data, competition, copy = _copy(tmp_path)
    shutil.copytree(competition, copy / "prepared" / "public" / "grader")
    code = _code(wrap, lambda: _packages(wrap, tmp_path / "out", competition=copy / "prepared" / "public" / "grader",
                                   data=data))
    assert (code, (tmp_path / "out").exists()) == ("aliased_input", False)


def test_a_file_name_that_is_not_utf8_is_refused_before_any_file_is_written(wrap, tools, tmp_path):
    data, competition, copy = _copy(tmp_path)
    (copy / "prepared" / "public" / os.fsdecode(b"bad\xff.csv")).write_bytes(b"x\n")
    code = _code(wrap, lambda: _contexts(wrap, tools, tmp_path / "out", competition=competition, data=data))
    assert (code, (tmp_path / "out").exists()) == ("name_not_utf8", False)


@pytest.mark.parametrize("config, code", [
    ("id: [unclosed\n", "bad_config"),
    ("- a list\n", "bad_config"),
    ("id: tiny-tabular\ndataset:\n  sample_submission: x.csv\n", "bad_config"),
    ("id: ../escape\ndataset:\n  answers: a.csv\n  sample_submission: s.csv\n", "bad_config"),
    (b"id: tiny-tabular\xff\n", "not_utf8"),
    (None, "unreadable"),
])
def test_a_malformed_or_missing_config_is_a_refusal_not_a_traceback(wrap, tmp_path, config, code):
    data, competition, _ = _copy(tmp_path)
    target = competition / "config.yaml"
    if config is None:
        target.unlink()
    else:
        target.write_bytes(config if isinstance(config, bytes) else config.encode())
    assert (_code(wrap, lambda: _packages(wrap, tmp_path / "out", competition=competition, data=data)),
            (tmp_path / "out").exists()) == (code, False)


def test_a_description_that_is_not_utf8_is_refused(wrap, tmp_path):
    data, competition, _ = _copy(tmp_path)
    (competition / "description.md").write_bytes(b"caf\xe9\n")
    assert _code(wrap, lambda: _packages(wrap, tmp_path / "out", competition=competition, data=data)) == "not_utf8"


def _cli(args):
    """wrap.py's command line under an ASCII-only locale: LC_ALL=C and UTF-8 mode off (-I ignores PYTHONUTF8)."""
    env = {"PATH": os.environ["PATH"], "LC_ALL": "C", "LANG": "C"}
    return subprocess.run([sys.executable, "-I", "-X", "utf8=0", str(KIT / "wrap.py"), *map(str, args)], env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="backslashreplace")


def test_under_an_ascii_only_locale_a_utf8_description_gives_the_same_digests(wrap, tmp_path):
    data, competition, _ = _copy(tmp_path)
    (competition / "description.md").write_text("# Кириллица and தமிழ்\n", encoding="utf-8")
    expected = _packages(wrap, tmp_path / "in-process", competition=competition, data=data)
    done = _cli(["packages", competition, data, tmp_path / "cli", "--name", "tiny", "--class", "cpu",
                 "--agent-image", IMAGES["agent"], "--verifier-image", IMAGES["verifier"]])
    assert (done.returncode, json.loads(done.stdout)["digests"] if done.returncode == 0 else done.stderr) == (
        0, expected["digests"])


def test_a_refusal_on_the_command_line_is_one_line_with_its_code_and_exit_2(tmp_path):
    done = _cli(["packages", TINY / "competition", FIXTURES, tmp_path / "cli", "--name", "tiny", "--class", "cpu",
                 "--agent-image", "localhost/x:1", "--verifier-image", IMAGES["verifier"]])
    assert (done.returncode, done.stdout, len(done.stderr.splitlines()), done.stderr.split(":")[:2]) == (
        2, "", 1, ["refused", " unpinned_image"])


@pytest.mark.parametrize("existing", ["agent-context", "attempt"])
def test_an_existing_output_directory_is_refused(wrap, tools, tmp_path, existing):
    (tmp_path / "out" / existing).mkdir(parents=True)
    assert _code(wrap, lambda: _run(wrap, tools, tmp_path / "out")) == "output_exists"


def test_an_unknown_class_is_refused(wrap, tmp_path):
    assert _code(wrap, lambda: _packages(wrap, tmp_path / "out", cls="tpu")) == "unknown_class"


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


def _assigned(path, name):
    """The literal value assigned to a module-level name in a Python file, read without importing it."""
    import ast
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value) if not isinstance(node.value, ast.Call) else ast.literal_eval(
                node.value.args[0])
    raise AssertionError(f"{name} not assigned in {path}")


def test_the_real_agent_and_verifier_files_wrap_the_fixture_at_the_paths_task_2_reads(wrap, tmp_path):
    """contexts() and packages() with their default agent/ and verifier/ directories (Task 2's files); the in-image
    paths the wrapper writes equal the ones grade_submission.py and validate_submission.py read."""
    _contexts(wrap, None, tmp_path / "out", agent_files=wrap.KIT / "agent", verifier_files=wrap.KIT / "verifier")
    _packages(wrap, tmp_path / "out")
    agent, verifier = tmp_path / "out" / "agent-context", tmp_path / "out" / "verifier-context"
    in_image = _assigned(KIT / "verifier" / "grade_submission.py", "IN_IMAGE")
    sample = _assigned(KIT / "agent" / "validate_submission.py", "SAMPLE")
    seen = {"tools": _tree(agent / "tools") == _tree(KIT / "agent"),
            "tests": _tree(verifier / "tests") == _tree(KIT / "verifier"),
            "test.sh": (verifier / "tests" / "test.sh").stat().st_mode & 0o777,
            "validator": ["/home/" + k for k in _tree(agent / "tools")],
            "paths": (wrap.SUBMISSION_DIR + "/submission.csv", wrap.VERIFIER_DATA, wrap.COMPETITIONS,
                      wrap.GRADER_WORK, wrap.AGENT_DATA + "/sample_submission.csv"),
            "attempt": sorted(_tree(tmp_path / "out" / "attempt"))}
    assert seen == {"tools": True, "tests": True, "test.sh": 0o755, "validator": [wrap.VALIDATOR],
                    "paths": (in_image["MLE_SUBMISSION"], in_image["MLE_DATA_DIR"],
                              in_image["MLE_BENCHMARK_DIR"] + "/mlebench/competitions", in_image["MLE_GRADER_WORK"],
                              sample),
                    "attempt": ["instruction.md", "task.toml"]}


def test_family_json_matches_the_plans_candidates_table_name_slug_and_class():
    """The revised plan's 'Candidates' table: | order | `name` | `slug` | GB | class | rank |."""
    text = (ROOT / FAMILY["plan"]).read_text()
    table = text[text.index("\n## Candidates"):text.index("\n## Decisions")]
    rows = [[c.strip().strip("`") for c in ln.strip("|").split("|")] for ln in table.splitlines()
            if re.match(r"\| \d+ \|", ln)]
    plan = [(int(r[0]), r[1], r[2], r[4].lower()) for r in rows]
    assert plan == [(c["order"], c["name"], c["slug"], c["class"]) for c in FAMILY["candidates"]]


def _env_reads(path):
    """The names a Python file reads as env["NAME"]: the variables without a default (ast, no import)."""
    import ast
    return {n.slice.value for n in ast.walk(ast.parse(path.read_text()))
            if isinstance(n, ast.Subscript) and getattr(n.value, "id", None) == "env"
            and isinstance(n.slice, ast.Constant)}


def test_every_variable_the_verifier_dockerfile_sets_is_one_task_2_reads(wrap, tools, tmp_path):
    """The competition id's variable is tied to grade_submission.py's env[...] read, MLE_DATA_DIR to its IN_IMAGE."""
    _run(wrap, tools, tmp_path / "out")
    source = KIT / "verifier" / "grade_submission.py"
    env = [ln for ln in (tmp_path / "out" / "verifier-context" / "Dockerfile").read_text().splitlines()
           if ln.startswith("ENV ")]
    assigned = dict(item.split("=", 1) for item in env[0].split()[1:])
    assert (len(env), _env_reads(source), assigned) == (
        1, {wrap.COMPETITION_ID_VAR},
        {wrap.COMPETITION_ID_VAR: "tiny-tabular",
         next(k for k, v in _assigned(source, "IN_IMAGE").items() if v == wrap.VERIFIER_DATA): wrap.VERIFIER_DATA})


@pytest.mark.parametrize("planted, source", [
    ("public/held.csv", "private/answers.csv"),
    ("public/ranks.csv", "competition/leaderboard.csv"),
    ("public/helper.py", "competition/grade.py"),
    ("agent/notes.csv", "private/answers.csv"),
])
@pytest.mark.parametrize("how", ["hard link", "copy"])
def test_a_withheld_file_under_another_name_in_what_the_agent_is_given_is_refused(
        wrap, tools, tmp_path, planted, source, how):
    data, competition, copy = _copy(tmp_path)
    shutil.copytree(tools, copy / "tools")
    roots = {"public": copy / "prepared" / "public", "private": copy / "prepared" / "private",
             "competition": competition, "agent": copy / "tools" / "agent"}
    (top, rel), (src_top, src_rel) = planted.split("/", 1), source.split("/", 1)
    (os.link if how == "hard link" else shutil.copyfile)(roots[src_top] / src_rel, roots[top] / rel)
    with pytest.raises(wrap.Refused) as caught:
        _contexts(wrap, None, tmp_path / "out", competition=competition, data=data,
                  agent_files=roots["agent"], verifier_files=copy / "tools" / "verifier")
    assert (caught.value.code, rel in str(caught.value), (tmp_path / "out").exists()) == (
        "withheld_content", True, False)


def test_only_the_description_is_public_by_design_when_the_sample_is_public(wrap):
    exempt = wrap.public_by_design(TINY / "competition", FIXTURES)
    assert (exempt, sorted(wrap.PUBLIC_BY_DESIGN)) == (
        {(TINY / "competition" / "description.md").resolve(): "description"}, ["description", "private_sample"])


def test_a_sample_placed_in_private_is_public_by_design_and_nothing_else_is(wrap, tools, tmp_path):
    data, competition, copy = _copy(tmp_path)
    config = competition / "config.yaml"
    config.write_text(config.read_text().replace("prepared/public/sample_submission.csv",
                                                 "prepared/private/sample_submission.csv"))
    shutil.copy(copy / "prepared" / "public" / "sample_submission.csv", copy / "prepared" / "private")
    exempt = wrap.public_by_design(competition, data)
    withheld = {p for _, p in wrap.withheld(competition, data).values()}
    every = {p.resolve() for root in (copy / "prepared" / "private", competition) for p in _files(root)}
    record = _run(wrap, tools, tmp_path / "out", competition=competition, data=data,
                  public_sample="sample_submission.csv")
    assert (sorted(exempt.values()), withheld == every - set(exempt), record["competition"]) == (
        ["description", "private_sample"], True, "tiny-tabular")


def test_an_attempt_package_file_equal_to_a_withheld_file_is_refused(wrap, tmp_path):
    """The check also covers task.toml and the instruction: here a private file holding the instruction's bytes."""
    data, competition, copy = _copy(tmp_path)
    _packages(wrap, tmp_path / "first", competition=competition, data=data)
    shutil.copyfile(tmp_path / "first" / "attempt" / "instruction.md", copy / "prepared" / "private" / "notes.md")
    code = _code(wrap, lambda: _packages(wrap, tmp_path / "out", competition=competition, data=data))
    assert (code, (tmp_path / "out").exists()) == ("withheld_content", False)
