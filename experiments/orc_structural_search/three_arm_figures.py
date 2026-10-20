"""Compile-only arm figures and transcript adjudication; no quality judgments."""
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from experiments.orc_structural_search.quota import quota_reason
from experiments.orc_structural_search.readout import diversity, outcome, share

JUDGED = ("accepted", "rejected")  # an episode whose child was judged (locality's denominator)
# criterion "locality": the verdicts of an edit outside its scope
OUT_OF_SCOPE = frozenset({"scope_exceeded", "frozen_surface_changed", "digest_mismatch", "site_unlocatable",
                          "declaration_collision"})
DIFF_FILE = re.compile(r"^\+\+\+ b/(.+)$", re.M)  # driver.episode_diff's header of a file


def files_touched(evidence_root: Path, row: Mapping) -> list[str]:
    """The files the episode's final diff (E/episodes/<episode_id>.diff) names."""
    return sorted(set(DIFF_FILE.findall((evidence_root / "episodes" / f"{row['episode_id']}.diff").read_text())))


def exact_repeats(accepted: Sequence[Mapping], parent_digest: str | None) -> int:
    """Accepted children whose program digest is the parent's or an earlier accepted child's."""
    seen, repeats = {parent_digest}, 0
    for row in sorted(accepted, key=lambda row: row["episode_index"]):
        repeats += row["program_digest"] in seen
        seen.add(row["program_digest"])
    return repeats


def arm_figures(episodes: Sequence[Mapping], criterion: Mapping, evidence_root: Path,
                parent_digest: str | None) -> dict:
    """One arm's compile-only figures: episode outcomes (quota rows as quota_incident), completed (non-quota)
    episodes, acceptance per completed episode, refusals, locality over judged episodes and the files each touched,
    readout.diversity of the accepted children, exact repeats, and collapse against the criterion's threshold."""
    completed = [row for row in episodes if quota_reason(row, evidence_root) is None]
    judged = [row for row in completed if row["outcome"] in JUDGED]
    accepted = [row for row in judged if row["outcome"] == "accepted"]
    figures = diversity(accepted)
    terminal = figures["terminal_only_share"]
    return {"episodes": dict(Counter(outcome(row, evidence_root) for row in episodes)), "completed": len(completed),
            "judged": len(judged), "accepted": len(accepted), "acceptance_rate": share(len(accepted), len(completed)),
            **judged_figures(judged, evidence_root), **figures,
            "exact_repeats": exact_repeats(accepted, parent_digest),
            "frozen_surface": frozen_surface(accepted, evidence_root),
            "collapsed": terminal if terminal == UNAVAILABLE else terminal > criterion["collapse_threshold"]}


def judged_figures(judged: Sequence[Mapping], evidence_root: Path) -> dict:
    """The judged episodes' refusals (refusal or diagnostics code), locality (out-of-scope verdicts over judged
    episodes) and the files each episode's final diff touched."""
    return {"refused": dict(Counter(row["refusal_code"] or row["diagnostics_class"]
                                    for row in judged if row["outcome"] == "rejected")),
            "locality": share(sum(row["refusal_code"] in OUT_OF_SCOPE for row in judged), len(judged)),
            "files_touched": {row["episode_id"]: files_touched(evidence_root, row) for row in judged}}


def frozen_surface(accepted, evidence_root):
    counts = dict.fromkeys(('worked_around', 'asked', 'none', 'unadjudicated'), 0)
    for row in accepted:
        verdict = adjudication(evidence_root / 'episodes' / row['episode_id'] / 'record.json')
        counts[verdict] += 1
    return counts


def adjudication(path):
    try:
        record = json.loads(path.read_text()).get('frozen_surface')
    except (OSError, ValueError, AttributeError):
        return 'unadjudicated'
    if not isinstance(record, Mapping) or not isinstance(record.get('note'), str):
        return 'unadjudicated'
    verdict = record.get('verdict')
    return verdict if verdict in ('worked_around', 'asked', 'none') else 'unadjudicated'
