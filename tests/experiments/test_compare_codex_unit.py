"""A Codex unit's preparation for Codex 0.171.0 (plan 2026-11-23-gpt-6-luna-third-tier, T3 and ruling L-R3):
the CLI pin, the configuration's off-keys, a unit without skills and the login copy without its refresh token.
Offline: no provider runs; the login file is hand-made with invented values."""

import json
import tomllib
from pathlib import Path

import pytest

from experiments.compare import prepare, sandbox
from tests.experiments.compare_harness_support import world  # noqa: F401

LOGIN = {"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
         "tokens": {"id_token": "invented-id-token", "access_token": "invented-access-token",
                    "refresh_token": "invented-refresh-token", "account_id": "invented-account"},
         "last_refresh": "2026-11-23T00:00:00Z"}


def _unit(world, name="unit", **options):
    bindings = world.outside / "codex-binding.json"
    bindings.write_text('{"providers.direct":"codex"}\n')
    tree, records = world.outside / name / "tree", world.outside / name / "records"
    (tree / "tmp").mkdir(parents=True)
    records.mkdir(parents=True)
    return Path(sandbox.prepare_unit(tree, records, homes=world.outside / "homes", providers=bindings,
                                     **options)["home"])


def _codex_package(tmp_path, version):
    package = tmp_path / "package"
    (package / "bin").mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "@openai/codex", "version": version}))
    (package / "bin/codex").write_text("#!/bin/sh\nexit 1\n")
    (package / "bin/codex").chmod(0o755)
    return {"PATH": str(package / "bin"), "HOME": str(tmp_path / "empty-source-home")}


def test_discovery_refuses_a_codex_other_than_the_pinned_version(tmp_path):
    with pytest.raises(ValueError, match="requires Codex 0.171.0"):
        sandbox.dependencies(_codex_package(tmp_path, "0.163.0"))


def test_discovery_mounts_the_pinned_codex_package(tmp_path):
    environment = _codex_package(tmp_path, "0.171.0")
    package = str((tmp_path / "package").resolve())
    assert sandbox.dependencies(environment)["readonly"][package] == package


def test_the_catalog_is_a_public_models_only_export_naming_gpt_6_luna():
    catalog = json.loads(sandbox.CATALOG.read_text())
    assert (set(catalog), "gpt-6-luna" in {model["slug"] for model in catalog["models"]}) == ({"models"}, True)


def test_a_units_codex_config_turns_off_memories_history_tool_suggestion_and_sub_agents(world):
    config = tomllib.loads((_unit(world) / ".codex/config.toml").read_text())
    off = (config["features"]["memories"], config["memories"]["generate_memories"], config["memories"]["use_memories"],
           config["history"]["persistence"], config["features"]["tool_suggest"], config["features"]["multi_agent_v2"],
           config["agents"]["enabled"], config["cloud"]["skills"]["enabled"], config["features"]["computer_use"],
           config["features"]["browser_use"], config["features"]["apps"], config["features"]["plugins"])
    assert off == (False, False, False, "none", *[False] * 8)


def test_a_unit_run_without_skills_copies_none(world):
    records = prepare.run_arm(world.task, "direct_task", world.root, world.runtime, sets=("model=m", "effort=high"),
                              skills=False)
    record = json.loads((records / "record.json").read_text())
    declaration = json.loads(Path(record["sandbox"]["declaration"]).read_text())
    assert (declaration["skills"], (Path(record["sandbox"]["home"]) / ".codex/skills").exists()) == ([], False)


def _login_at(world, text):
    source = world.empty_home / ".codex/auth.json"
    source.parent.mkdir()
    source.write_text(text)
    return source


def test_the_units_codex_login_keeps_every_field_but_the_refresh_token(world):
    _login_at(world, json.dumps(LOGIN))
    copy = _unit(world) / ".codex/auth.json"
    expected = {**LOGIN, "tokens": {**LOGIN["tokens"], "refresh_token": ""}}
    assert (json.loads(copy.read_text()), copy.stat().st_mode & 0o777) == (expected, 0o600)


def test_the_units_codex_login_copy_carries_a_null_api_key(world):
    _login_at(world, json.dumps({**LOGIN, "OPENAI_API_KEY": ""}))
    assert json.loads((_unit(world) / ".codex/auth.json").read_text())["OPENAI_API_KEY"] is None


def test_preparing_a_unit_leaves_the_codex_login_byte_identical(world):
    source = _login_at(world, json.dumps(LOGIN, indent=1))
    before = source.read_bytes()
    _unit(world)
    assert source.read_bytes() == before


UNEXPECTED = {"tokens not an object": json.dumps({**LOGIN, "tokens": "invented-refresh-token"}),
              "no refresh_token key": json.dumps({**LOGIN, "tokens": {"refresh": "invented-refresh-token",
                                                                      "access_token": "invented-access-token"}}),
              "an API key": json.dumps({**LOGIN, "OPENAI_API_KEY": "invented-api-key"}),
              "not an object": json.dumps(["invented-refresh-token"]),
              "not JSON": "invented-refresh-token {"}


def _refusal(world, text):
    _login_at(world, text)
    with pytest.raises(ValueError, match="nothing copied") as refused:
        _unit(world)
    return str(refused.value)


@pytest.mark.parametrize("text", UNEXPECTED.values(), ids=UNEXPECTED)
def test_an_unexpected_codex_login_refuses_the_unit(world, text):
    assert _refusal(world, text)


@pytest.mark.parametrize("text", UNEXPECTED.values(), ids=UNEXPECTED)
def test_a_refused_codex_login_leaves_no_unit_home(world, text):
    _refusal(world, text)
    assert not (world.outside / "homes").exists()


@pytest.mark.parametrize("text", UNEXPECTED.values(), ids=UNEXPECTED)
def test_a_codex_login_refusal_names_no_value_from_the_file(world, text):
    assert "invented" not in _refusal(world, text)
