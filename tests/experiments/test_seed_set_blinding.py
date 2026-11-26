"""Blinding of what the judges read (coordinator ruling 3): the build order of a batch's clones, the scan of pooled
patches for arm-identifying text, and the binding of each rating to the patch its judge read. No provider."""

import json
from pathlib import Path
from types import SimpleNamespace

from experiments.compare import pool as pooling
from experiments.seed_set import blinding

ARMS = {"direct": {"source": "direct.orc", "entry": "direct::run"},
        "retry_until_check": {"source": "retry_until_check.orc", "entry": "retry_until_check::run"}}


def diff(path, added):
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1,2 @@\n context direct haiku\n+{added}\n"


def pool_dir(tmp_path, patches, upstream_adds="return a + b"):
    out, task = tmp_path / "pool", tmp_path / "tasks" / "t1"
    (out / "records" / "patches").mkdir(parents=True)
    (task / "anchors").mkdir(parents=True)
    (task / "anchors" / "t1-upstream.diff").write_text(diff("pkg/calc.py", upstream_adds))
    clones = {"a0": {"arm": "anchor"}}
    for cid, text in patches.items():
        clones[cid] = {"arm": "direct"}
        (out / "records" / "patches" / f"{cid}.diff").write_text(text)
    (out / "records" / "mapping.json").write_text(json.dumps({"clones": clones}))
    return out, task


def tokens(tmp_path, run_id="20261112T000000Z-abcdef"):
    run = tmp_path / "work" / "records" / "retry_until_check" / "run-1"
    (run / "state" / run_id).mkdir(parents=True)
    (run / "record.json").write_text(json.dumps({"tree": str(tmp_path / "work" / "agents" / "k3x9")}))
    study = SimpleNamespace(work=tmp_path / "work", pools=tmp_path / "pools")
    return blinding.identity_tokens(study, ARMS, [run])


def test_tokens_name_models_programs_and_the_runs_own_ids_but_not_the_word_direct(tmp_path):
    found = tokens(tmp_path)
    assert ({"claude-haiku-5-5", "sonnet", "retry_until_check", "direct.orc", "direct::run", "k3x9",
             "20261112T000000Z-abcdef"} <= set(found), "direct" in found) == (True, False)


def test_a_pooled_patch_naming_a_model_or_a_run_is_a_hit(tmp_path):
    out, task = pool_dir(tmp_path, {"c1": diff("pkg/calc.py", "# written by Claude Haiku"),
                                    "c2": diff(f"{tmp_path}/work/agents/k3x9/notes.txt", "ok"),
                                    "c3": diff("pkg/calc.py", "return direct(a) + b")})
    hits = blinding.scan_pool(out, task, tokens(tmp_path))
    assert {(h["clone"], h["token"]) for h in hits} == {
        ("c1", "haiku"), ("c2", "k3x9"), ("c2", str(tmp_path / "work")), ("c2", str(tmp_path / "work/agents/k3x9"))}


def test_a_pooled_patch_naming_the_luna_model_is_a_hit(tmp_path):
    out, task = pool_dir(tmp_path, {"c1": diff("pkg/calc.py", "# written by gpt-6-luna")})
    assert {h["token"] for h in blinding.scan_pool(out, task, tokens(tmp_path))} == {"gpt-6-luna", "luna"}


def test_context_lines_and_text_the_reference_fix_adds_are_not_hits(tmp_path):
    out, task = pool_dir(tmp_path, {"c1": diff("pkg/models.py", 'DEFAULT = "claude-sonnet-5-5"')},
                         upstream_adds='DEFAULT = "claude-sonnet-5-5"')
    assert blinding.scan_pool(out, task, tokens(tmp_path)) == []


def test_a_batch_is_built_in_an_order_that_mixes_anchors_and_candidates(tmp_path, monkeypatch):
    """Ruling 3a: file times show the build order, so it must not put the anchors (or any arm) in a fixed place.
    Retest pools are built by the same `pool.pool` call (study.build_pools for either kind)."""
    order = []
    monkeypatch.setattr(pooling, "add_clone", lambda out, task, ref, patch, entry, review_exclude: (
        order.append(entry["labels"][0]) or (entry["labels"][0], entry)))
    monkeypatch.setattr(pooling, "anchor_paths", lambda task, criterion: [Path("t-base.diff"), Path("t-upstream.diff")])
    monkeypatch.setattr(pooling, "patch_bytes", lambda path, rec, label: b"")
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"")
    batch = [(f"/r/{k}", {"arm": "direct" if k < 4 else "direct_sonnet"}, [f"c{k}"]) for k in range(5)]
    positions = set()
    for _ in range(40):
        order.clear()
        _, members, _ = pooling.build_batches(tmp_path, tmp_path, {}, [batch], {"reference": None})
        positions.add((order.index("t-base"), order.index("t-upstream"), order.index("c4")))
        assert members == [["c0", "c1", "c2", "c3", "c4", "t-base", "t-upstream"]]  # the mapping keeps its order
    assert len(positions) > 20
