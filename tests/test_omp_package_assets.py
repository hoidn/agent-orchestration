"""OMP package assets (Tasks 5 and 7, OMP-I1)."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

import pytest
import yaml

from orchestrator.omp_assets import (
    inference_output_contract_path,
    neutral_config_path,
    preset_conf_root,
)
from orchestrator.providers.omp_conf import admit_conf_tree
from orchestrator.providers.omp_launch import neutral_conf_root

_BUNDLED_AGENTS = [
    "designer",
    "librarian",
    "reviewer",
    "scout",
    "security-reviewer",
    "sonic",
    "task",
]

FIXTURE_PRESETS = (
    "neutral",
    "advised",
    "fanout",
    "peer-team",
    "advised-fanout",
)

# Preset -> expected admitted tree membership (beyond config.yml).
_PRESET_MEMBERSHIP = {
    "neutral": frozenset(),
    "advised": frozenset({"agent/WATCHDOG.yml"}),
    "fanout": frozenset(
        {"agent/agents/alpha.md", "agent/agents/beta.md"}
    ),
    "peer-team": frozenset(
        {"agent/agents/alpha.md", "agent/agents/beta.md"}
    ),
    "advised-fanout": frozenset(
        {
            "agent/WATCHDOG.yml",
            "agent/agents/alpha.md",
            "agent/agents/beta.md",
        }
    ),
}

# Preset -> admitted agent names a canary prompt must ask for.
_PRESET_AGENTS = {
    "neutral": frozenset(),
    "advised": frozenset({"code-reviewer"}),
    "fanout": frozenset({"alpha", "beta"}),
    "peer-team": frozenset({"alpha", "beta"}),
    "advised-fanout": frozenset({"code-reviewer", "alpha", "beta"}),
}


def test_neutral_conf_path_helper_is_single_sourced() -> None:
    """F8: one neutral-conf path helper; the assets package reuses it."""
    assert neutral_config_path() == neutral_conf_root()


def test_neutral_conf_package_resolves() -> None:
    root = neutral_conf_root()
    assert root.endswith("confs/neutral")
    config = resources.files("orchestrator.omp_assets").joinpath(
        "confs", "neutral", "config.yml"
    )
    assert config.is_file()
    assert neutral_config_path() == root


def test_neutral_conf_contract() -> None:
    root = neutral_conf_root()
    with open(f"{root}/config.yml", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    assert document["advisor"]["enabled"] is False
    assert document["memory"]["backend"] == "off"
    assert document["task"]["maxConcurrency"] == 1
    assert document["task"]["maxRecursionDepth"] == 0
    assert document["task"]["disabledAgents"] == _BUNDLED_AGENTS


def test_neutral_conf_tree_admits() -> None:
    import os

    fd = os.open(neutral_conf_root(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        snapshot = admit_conf_tree(fd)
    finally:
        os.close(fd)
    assert snapshot.manifest_sha256
    assert "config.yml" in snapshot.files
    assert "agent/WATCHDOG.yml" not in snapshot.files


# --- Task 7: packaged presets, canary fixtures, inference resource -----------


def _admit_package_preset(name: str):
    fd = os.open(
        preset_conf_root(name), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        return admit_conf_tree(fd)
    finally:
        os.close(fd)


@pytest.mark.parametrize("name", FIXTURE_PRESETS)
def test_packaged_preset_conf_tree_admits(name: str) -> None:
    snapshot = _admit_package_preset(name)
    expected = _PRESET_MEMBERSHIP[name] | {"config.yml"}
    assert set(snapshot.files) == expected


def test_packaged_preset_manifests_are_distinct() -> None:
    digests = {
        name: _admit_package_preset(name).manifest_sha256
        for name in FIXTURE_PRESETS
    }
    assert len(set(digests.values())) == len(FIXTURE_PRESETS)

def test_packaged_fanout_presets_allow_headless_task_dispatch() -> None:
    for name in ("fanout", "peer-team", "advised-fanout"):
        config = yaml.safe_load(
            Path(preset_conf_root(name), "config.yml").read_text(encoding="utf-8")
        )
        assert config["tools"]["approval"] == {"task": "allow"}


def test_packaged_canary_agents_use_current_model() -> None:
    expected = "openai-codex/gpt-5.6-sol"
    for name in FIXTURE_PRESETS:
        root = Path(preset_conf_root(name))
        for agent in root.glob("agent/agents/*.md"):
            frontmatter = yaml.safe_load(agent.read_text(encoding="utf-8").split("---", 2)[1])
            assert frontmatter.get("model", expected) == expected
        watchdog = root / "agent" / "WATCHDOG.yml"
        if watchdog.is_file():
            document = yaml.safe_load(watchdog.read_text(encoding="utf-8"))
            assert all(advisor["model"] == expected for advisor in document["advisors"])



def test_preset_conf_root_is_importlib_resources_based() -> None:
    root = preset_conf_root("neutral")
    assert root == neutral_conf_root()
    assert resources.files("orchestrator.omp_assets").joinpath(
        "confs", "neutral", "config.yml"
    ).is_file()
    with pytest.raises(ValueError):
        preset_conf_root("not-a-preset")


def test_preset_canary_prompt_fixtures_exist_and_name_admitted_agents() -> None:
    presets_root = Path(__file__).parent / "fixtures" / "omp" / "presets"
    for name in FIXTURE_PRESETS:
        prompt_path = presets_root / name / "prompt.md"
        assert prompt_path.is_file()
        text = prompt_path.read_text(encoding="utf-8")
        assert text.strip()
        for agent in _PRESET_AGENTS[name]:
            assert agent in text
        if "code-reviewer" in _PRESET_AGENTS[name]:
            assert "advisor" in text


def test_inference_output_contract_resource_exists_and_compiles() -> None:
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint

    resource_path = Path(inference_output_contract_path())
    assert resource_path.is_file()
    source = resource_path.read_text(encoding="utf-8")
    assert "OutputContractDraft" in source
    assert "infer-output-contract" in source
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td)
        (workspace / "prompt.md").write_text("synthesize the output contract\n")
        entry = workspace / "infer-output-contract.orc"
        entry.write_text(source)
        result = compile_stage3_entrypoint(
            entry,
            source_roots=(workspace,),
            provider_externs={"providers.inference": "omp_conf_inference"},
            prompt_externs={"prompts.inference": {"asset_file": "prompt.md"}},
            validate_shared=True,
            workspace_root=workspace,
        )
        mapping = result.entry_result.lowered_workflows[0].authored_mapping
        step = next(s for s in mapping["steps"] if "provider" in s)
        assert step["provider"] == "omp_conf_inference"
        fields = step["output_bundle"]["fields"]
        assert [field["name"] for field in fields] == ["fields"]
        assert fields[0]["type"] == "list"
