"""Child judging of an episode: validation, compilation, the I2 slot check, the bounded planned maximum and the
entry's result type (driver.run_episode calls judge_child).

Design: docs/design/orc_structural_search_driver.md ("Edit Validation And Transactions").
"""

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.candidates import compile_candidate, validate_frozen_surfaces, validate_one_site
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.records import UNAVAILABLE
from experiments.orc_structural_search.sites import (
    derive_receipt, drop_hypothesis, replacement_start, site_manifest, slot_type)


def entry_result(root: Path, build_key: str) -> object:
    return json.loads((root / ".orchestrate" / "build" / build_key / "closed_program.json").read_text())["result"]


def judge_child(parent: Path, child: Path, config: ExperimentConfig, *, runtime: Path, site: Mapping | None = None,
                parent_candidate_id: str | None = None) -> dict:
    """Validation, full compilation with the runtime's orchestrator (a compiler crash is a rejection), the I2 slot
    check, a bounded planned maximum of provider calls (`unbounded_calls`), then the entry's result type against
    the parent's. Without `site`: frozen-surface validation. With
    `site` (I2): the receipt is derived from the child (`receipt` in the verdict), <child>/HYPOTHESIS.txt is then
    removed, and the one-site transaction validates the child; it applies the frozen-surface rule itself with the
    receipt's helpers allowed (a plain frozen-surface check would refuse any helper)."""
    receipt = None
    if site is None:
        verdict = validate_frozen_surfaces(parent, child, config)
    else:
        receipt = derive_receipt(parent, child, site, config, parent_candidate_id=parent_candidate_id)
        drop_hypothesis(child)
        verdict = validate_one_site(parent, child, receipt, config)
    shown = {"receipt": asdict(receipt) if receipt else None}
    if not verdict.accepted:
        return {**shown, "outcome": "rejected", "refusal_code": verdict.code, "detail": verdict.detail}
    compiled = compile_candidate(child, config, runtime=runtime)
    if compiled.status != "accepted":
        first = compiled.diagnostics[0] if compiled.diagnostics else {}
        return {**shown, "outcome": "rejected", "diagnostics_class": first.get("code", UNAVAILABLE),
                "detail": first.get("message") or first.get("stderr", "")}
    refusal = slot_refusal(parent, child, site, config, runtime=runtime) if site else None
    refusal = refusal or ledger.unbounded_refusal(child, config)  # an unbounded child never reaches an evaluation
    # Fires only when the entry is not exported or lacks a result annotation: frozen-surface validation already
    # freezes an exported signature and every type declaration.
    if refusal is None and entry_result(parent, compile_candidate(parent, config, runtime=runtime).build_key) != \
            entry_result(child, compiled.build_key):
        refusal = {"refusal_code": "slot_type_changed",
                   "detail": f"the result type of {config.entry_workflow} differs from the parent's"}
    if refusal is not None:
        return {**shown, "outcome": "rejected", **refusal}
    return {**shown, "outcome": "accepted", "program_digest": compiled.program_digest,
            "build_key": compiled.build_key}


def slot_refusal(parent: Path, child: Path, site: Mapping, config: ExperimentConfig, *, runtime: Path) -> dict | None:
    """The slot check of an accepted one-site child: the child manifest's type at the replacement's start against
    the parent site's (`slot_type_changed`; `slot_type_unavailable` when the manifest reports none, e.g. for a
    literal replacement), or None when they are equal."""
    file_name, line, column = replacement_start(parent, child, site)  # the one-site transaction located it
    found = slot_type(site_manifest(child, config, runtime=runtime), site["owner"]["name"], file_name, line, column)
    expected = site["result_type"]["canonical"]
    if found is None:
        return {"refusal_code": "slot_type_unavailable",
                "detail": f"the manifest reports no type at {file_name}:{line}:{column}"}
    if found != expected:
        return {"refusal_code": "slot_type_changed", "detail": f"the replacement is {found}, the site {expected}"}
    return None
