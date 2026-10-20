"""Malformed reference metadata fails before reading any judge result."""

import pytest

from experiments.compare import repos, summarize
from tests.experiments.compare_harness_support import world  # noqa: F401
from tests.experiments.test_compare_pool_summarize import reference_pool  # noqa: F401


@pytest.mark.parametrize("change", ["missing", "empty", "truncated", "unknown", "wrong-arm", "blind-member"])
def test_reference_rubric_requires_complete_reference_metadata(reference_pool, world, change):
    out, mapping = reference_pool
    cid = mapping["references"][0]
    if change == "missing":
        del mapping["references"]
    elif change == "empty":
        mapping["references"] = []
    elif change == "truncated":
        mapping["batches"].append(mapping["batches"][0])
    elif change == "unknown":
        mapping["references"] = ["unknown"]
    elif change == "wrong-arm":
        mapping["clones"][cid]["arm"] = "anchor"
    else:
        mapping["batches"][0].append(cid)
    repos.dump(out / "records/mapping.json", mapping)
    with pytest.raises(SystemExit, match="^reference metadata"):
        summarize.summarize(out, world.criterion)
