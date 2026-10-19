"""The I2 brief names the replacement forms the slot check can type, kept in step with the site manifest; the I3
brief's check line runs in an episode workspace."""

import shlex
import shutil
import subprocess

from experiments.orc_structural_search.briefs import TYPED_HEADS, episode_brief
from experiments.orc_structural_search.config import ExperimentConfig
from orchestrator.workflow_lisp.source_sites import _KINDS
from tests.experiments.orc_structural_search_support import (  # noqa: F401 (pyright: fixture)
    I3_CONFIG, PYTHON_PARENT, REPO, pyright)

CONFIG = ExperimentConfig(
    mutable_files=("direct.orc",), mutable_definitions=("run",), condition="topology-only", interface="I2",
    entry_workflow="direct::run", source_root=".", providers_file="providers.json", command_boundaries_file=None,
    episode_wall_clock_sec=600, criterion_sha256=None)
SITE = {"site_id": "workflow:direct::run@direct.orc:1:1", "kind": "provider-call",
        "span": {"start": {"path": "direct.orc", "line": 1, "column": 1}, "end": {"path": "direct.orc", "line": 1}},
        "result_type": {"rendered": "Change"}, "bindings": [], "dependencies": {},
        "effects": {"restriction": "none"}}


def test_the_typed_heads_cover_every_typed_manifest_site_kind():
    # a pure function call is a manifest site excluded as pure-call-unretained: the slot check cannot use it
    assert set(TYPED_HEADS.values()) == set(_KINDS.values()) - {"function-call"}


def test_only_the_i2_brief_names_the_typed_heads():
    i2, i1 = episode_brief(CONFIG, 0, site=SITE), episode_brief(CONFIG, 0)
    assert ([head for head in TYPED_HEADS if head not in i2], "list/map-effect" in i1) == ([], False)


def test_the_i3_brief_names_the_python_check_and_no_runtime_path(tmp_path, pyright):
    brief = episode_brief(I3_CONFIG, 0)
    (line,) = [line for line in brief.splitlines() if "pyright" in line]
    words = shlex.split(line)
    command = words[min(i for i, word in enumerate(words) if word == "pyright" or "=" in word):]
    # the episode workspace's layout (driver.episode_workspace): cand-1 holds the parent, ../py the orchestrator
    shutil.copytree(PYTHON_PARENT, tmp_path / "cand-1", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "py").mkdir()
    (tmp_path / "py" / "orchestrator").symlink_to(REPO / "orchestrator")
    done = subprocess.run(["env", *command], cwd=tmp_path / "cand-1", capture_output=True, text=True)
    assert (done.returncode, [word for word in brief.split() if word.startswith("/")]) == (0, []), done.stdout
