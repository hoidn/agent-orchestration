"""The I2 brief names the replacement forms the slot check can type, kept in step with the site manifest."""

from experiments.orc_structural_search.briefs import TYPED_HEADS, episode_brief
from experiments.orc_structural_search.config import ExperimentConfig
from orchestrator.workflow_lisp.source_sites import _KINDS

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
