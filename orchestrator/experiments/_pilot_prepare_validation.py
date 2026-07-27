"""Closed source-map shape validation for private pilot preparation."""

from __future__ import annotations

import re

from ._pilot_prepare_support import (
    _closed,
    _component,
    _digest,
    _fail,
    _items,
    _relative,
    _text,
    _texts,
)


_OBJECT = re.compile(r"^[0-9a-f]{40,64}$")


def _shape(value: dict[str, object]) -> None:
    _closed(
        value,
        set(
            "schema_version pilot archive provider_policy apparatus review "
            "treatments sources expected_derived_digests".split()
        ),
        "source map",
    )
    if value["schema_version"] != "lean-pilot-apparatus-source-map.v1":
        _fail("unsupported source map schema")

    pilot = _closed(
        value["pilot"],
        set(
            "pilot_id task_id randomization_seed valid_block_count "
            "max_live_attempt_count smoke_id live_attempt_ids claim_level".split()
        ),
        "pilot",
    )
    live = _texts(pilot["live_attempt_ids"], "live IDs", components=True)
    if (
        pilot["valid_block_count"] != 3
        or pilot["max_live_attempt_count"] != 5
        or pilot["claim_level"] != "exploratory_controlled_task"
        or len(live) != 5
        or _component(pilot["smoke_id"], "smoke ID") in live
    ):
        _fail("pilot constants are invalid")

    archive = _closed(
        value["archive"],
        set(
            "repository_identity revision_identity source_subtree_path "
            "source_tree_identity archive_digest task_source_path".split()
        ),
        "archive",
    )
    revision = str(archive["revision_identity"])
    tree = str(archive["source_tree_identity"])
    if (
        not revision.startswith("commit:")
        or _OBJECT.fullmatch(revision[7:]) is None
    ):
        _fail("archive revision must bind a full commit")
    if not tree.startswith("git-tree:") or _OBJECT.fullmatch(tree[9:]) is None:
        _fail("archive tree must bind a full tree")
    for key in ("source_subtree_path", "task_source_path"):
        _relative(archive[key], key)
    _digest(archive["archive_digest"], "archive digest")

    _closed(
        value["provider_policy"],
        {
            "family",
            "model",
            "reasoning_effort",
            "tool_policy",
            "timeout_milliseconds",
            "currency",
        },
        "provider policy",
    )
    apparatus = _closed(
        value["apparatus"],
        set(
            "treatment_asset_paths task_path provider_config_path prompt_config_path "
            "command_config_path environment visible_check "
            "product_projection_exclusions maximum_start_skew_milliseconds "
            "quiescence_grace_milliseconds".split()
        ),
        "apparatus",
    )
    _texts(apparatus["treatment_asset_paths"], "treatment assets", paths=True)
    _texts(
        apparatus["product_projection_exclusions"],
        "product exclusions",
        paths=True,
    )
    for key in (
        "task_path",
        "provider_config_path",
        "prompt_config_path",
        "command_config_path",
    ):
        _relative(apparatus[key], key)
    environment = _closed(
        apparatus["environment"],
        {"identity", "allowed_keys", "credential_keys"},
        "environment",
    )
    if set(_texts(environment["allowed_keys"], "allowed keys")) != {
        "CODEX_HOME",
        "HOME",
        "PATH",
        "PYTHONUNBUFFERED",
        "TMPDIR",
    } or _texts(environment["credential_keys"], "credential keys") != [
        "CODEX_HOME"
    ]:
        _fail("treatment environment partition is invalid")
    _digest(environment["identity"], "environment identity")
    _closed(
        apparatus["visible_check"],
        {"argv", "timeout_milliseconds"},
        "visible check",
    )

    review = _closed(
        value["review"],
        set(
            "reviewer_ids disagreement_policy selected_final_files "
            "permitted_check_evidence_names rubric_path "
            "calibration_evidence_path evaluator reviewer_command".split()
        ),
        "review",
    )
    if len(_texts(review["reviewer_ids"], "reviewer IDs")) != 2:
        _fail("exactly two reviewer IDs are required")
    for key in ("rubric_path", "calibration_evidence_path"):
        _relative(review[key], key)
    _texts(review["selected_final_files"], "selected files", paths=True)
    _texts(
        review["permitted_check_evidence_names"],
        "check names",
        components=True,
    )
    for name in ("evaluator", "reviewer_command"):
        bundle = _closed(review[name], {"config_path", "asset_paths"}, name)
        paths = _texts(bundle["asset_paths"], f"{name} assets", paths=True)
        if _relative(bundle["config_path"], f"{name} config") not in paths:
            _fail(f"{name} config is outside its bundle")

    treatments = _items(value["treatments"], "treatments")
    treatment_ids = []
    for row in treatments:
        item = _closed(
            row,
            {
                "treatment_id",
                "command_config_path",
                "source_asset_paths",
                "provider_call_bounds",
            },
            "treatment",
        )
        treatment_ids.append(_text(item["treatment_id"], "treatment ID"))
        _relative(item["command_config_path"], "treatment command")
        _texts(item["source_asset_paths"], "treatment sources", paths=True)
        _closed(item["provider_call_bounds"], {"minimum", "maximum"}, "call bounds")
    if len(treatments) != 3 or set(treatment_ids) != {
        "DIRECT",
        "COORDINATOR",
        "ORC",
    }:
        _fail("treatment set is invalid")
    expected = _closed(
        value["expected_derived_digests"],
        {
            "treatment_sources",
            "evaluator_bundle",
            "reviewer_command_bundle",
            "task_profile",
        },
        "expected derived digests",
    )
    source_digests = _closed(
        expected["treatment_sources"],
        set(treatment_ids),
        "expected treatment digests",
    )
    for treatment_id in sorted(source_digests):
        _digest(
            source_digests[treatment_id],
            f"{treatment_id} treatment source digest",
        )
