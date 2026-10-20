# Structural search over orchestration programs

Check a whole-module proposal locally and inspect structural-search evidence without
provider calls. This apparatus remains experimental; no live successor study or
structural-search provider allocation is selected. The separate
[measurement plan](../../docs/plans/2026-10-19-orc-structural-search-measurement-plan.md)
records verified offline preparation and I/F freeze. Approved calibration
Step A completed 8 calls within cap 10 and failed (RPI spread;
PRR passed). A′ offline preparation is verified; its new freeze and approval
are pending; the no-Claude experiment directive blocks it on 2026-10-19 (America/Los_Angeles).

The [driver design](../../docs/design/orc_structural_search_driver.md) owns admission,
qualification, metering and selection. The [delivery plan](../../docs/plans/2026-10-19-orc-structural-search-module-condition-implementation-plan.md)
records offline verification, policy-set/cache-write delivery and remaining checks; the [roadmap](../../docs/plans/2026-10-18-orc-structural-search-roadmap.md)
owns live selection. Scripted checks establish mechanics, not research utility.

| Surface | Current use |
| --- | --- |
| Whole-file I1 under `module` | Intended future primary search surface; private procedures, prompts and types may change together |
| Legacy conditions and one-site I2 | Maintained controls and ablations |
| Matched Python I3 | Separate control with Python scope/type checks |
| Mode 1 and criterion-configured arms | Offline launch/check/readout mechanics; live work requires separate approval and qualification |
| Adaptive mode 2 | Historical helpers retained; fresh adaptive launches and finalist validation refuse as unsupported |

## Check a module proposal

1. Obtain a repository checkout and install its Python dependencies using the
   [testing prerequisites](../../tests/README.md). The shipped parent under
   `experiments/orc_structural_search/three_arm/orc/` supplies the public types,
   provider bindings and command boundary; nothing outside the checkout is needed.
2. Run this complete sequence from the repository root. It creates a temporary
   measure-free criterion and configuration, copies the parent and checks the copy.
   It compiles locally, prints an accepted verdict and removes temporary files.
   It launches no provider and creates no frozen study criterion.

```bash
python - <<'PYMODULE'
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path.cwd()
# Optional existing evidence, chosen by the reader; leave unset for the local check.
HISTORICAL_LOG = None
HISTORICAL_COMPILE_READOUT = None
HISTORICAL_CRITERION = ROOT / "experiments/orc_structural_search/criteria/three_arm.json"

from experiments.orc_structural_search.check import stage_parent
from experiments.orc_structural_search.config import load_config
from experiments.orc_structural_search.qualification import validate
from experiments.orc_structural_search.three_arm import arm_config, load_criterion

with tempfile.TemporaryDirectory(prefix="structural-module-") as directory:
    work = Path(directory)
    study = {
        "purpose": "measure-free",
        "arms": {
            "I1": {"interface": "I1", "condition": "topology-only", "parent": "orc"},
            "I2": {"interface": "I2", "condition": "topology-only", "parent": "orc"},
            "I3": {"interface": "I3", "condition": "topology-only", "parent": "python"},
            "I1/module": {"interface": "I1", "condition": "module", "parent": "orc"},
        },
    }
    criterion = work / "criterion.json"
    criterion.write_text(json.dumps(study))
    config = {
        "mutable_files": ["direct.orc"], "mutable_definitions": ["run"],
        "condition": "module", "interface": "I1", "entry_workflow": "direct::run",
        "source_root": ".", "providers_file": "providers.json",
        "command_boundaries_file": "commands.json", "episode_wall_clock_sec": 60,
        "criterion_sha256": hashlib.sha256(criterion.read_bytes()).hexdigest(),
        "models": {"gpt-6.1-sol": ["high"]}, "per_call_timeout_sec": 5400,
    }
    config_path = work / "config.json"
    config_path.write_text(json.dumps(config))
    assert load_config(config_path).condition == "module"
    frozen = load_criterion(criterion)
    assert arm_config(config_path, "I1/module", frozen).interface == "I1"
    assert arm_config(config_path, "I1", frozen).condition == "topology-only"
    assert validate(criterion, config_sha256=config["criterion_sha256"])["mode"] == "measure-free"
    seed = ROOT / "experiments/orc_structural_search/three_arm/orc"
    stage_parent(seed, work / "parent")
    shutil.copytree(seed, work / "cand-1")
    (work / "py").symlink_to(ROOT, target_is_directory=True)
    metadata = work / "admission.json"
    metadata.write_text(json.dumps({"parent": "parent", "config": "config.json"}))
    command = [sys.executable, "-P", "-m", "experiments.orc_structural_search.check",
               "--metadata", str(metadata)]
    result = subprocess.run(command, cwd=work / "cand-1",
                            env={**os.environ, "PYTHONPATH": str(ROOT)},
                            check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["outcome"] == "accepted"
    print(result.stdout.strip())

if HISTORICAL_LOG is not None:
    assert HISTORICAL_COMPILE_READOUT is not None
    subprocess.run([sys.executable, "-m", "experiments.orc_structural_search.three_arm",
                    "readout", "--measure-free", "--log", str(HISTORICAL_LOG),
                    "--driver-readout", str(HISTORICAL_COMPILE_READOUT),
                    "--criterion", str(HISTORICAL_CRITERION)], check=True)
PYMODULE
```

3. To test a proposal, edit the temporary candidate before the command in the
   sequence. The check returns JSON: exit 0 accepts, 1 rejects, 2 records an
   incident. Ordinary compiler diagnostics support repair; final episode
   submission independently rechecks against the controller's staged parent.

## What happens

- Admission freezes the public entry/types, imports and bound capabilities;
  module model/effort and timeout values must be allowed literals. Unsupported
  agent/turn/phased effects refuse under every condition.
- A module reservation traverses the checked closed program per invocation,
  including arguments, imported helpers, loop exhaustion and finite map bounds.
  Both shims enforce the reservation before the real provider; refused attempts
  remain recorded and count in ledger settlement.
- Source metrics normalize coherent private renames. The current allocation contract
  compares sets of distinct provider/model/effort policies;
  static invocation paths remain diagnostic and unavailable proof stays unavailable.
  Policy and skeleton evidence classify `policy_only`, `structure_only`, `both`,
  `unchanged` or `unknown`; new sites reusing a policy do not change its set. Memo effects preserve
  identity, class, attempts and status;
  unexercised sites need a validated join and never establish branch coverage.

## Interpret evidence

Quality launches, resume, pooling, judging and readouts require an explicit criterion,
matching hashes and external family/measure precalibration evidence. The
[receipt contract](../../docs/design/orc_structural_search_driver.md#external-qualification-receipt)
explains inputs, private evidence layout and exact schemas. Invalid quality evidence
fails closed. A measure-free criterion permits execution/cost reporting; it permits
no judging or adaptive quality selection.

Qualified successor readouts join harness clone IDs, report anchors first and compare
matched tasks/replicates. Each arm's frontier is recomputed over its parent and all
evaluated children, including earlier continuation subsets; it retains only
non-dominated candidates above the quality floor. Parents share one evaluation per
identity, projected to their arms. Readout-only prices come from the criterion;
missing usage/rates remain unavailable. Codex cumulative totals distinguish
cache-write already inside input from separate cache-write; inconsistent counters
stay unavailable. Calls substitute for cost only with complete,
unambiguous actual model/effort identity proof for every compared call.

The [module decision](../../docs/plans/2026-10-19-orc-structural-search-module-rewrite-plan.md#gate-for-a-live-module-arm)
keeps evaluator, family, isolation, sealed-split and owner-budget gates open. Historical
Phase 1/2/three-arm criteria and the removed illustrative module criterion preserve
provenance; they grant no fresh launch permission. Captured campaign commands and
allocations remain in their [three-arm plan](../../docs/plans/2026-10-19-orc-structural-search-three-arm-readout-plan.md)
and [Phase 2 plan](../../docs/plans/2026-10-18-orc-structural-search-phase2-plan.md).

## Optional historical projection

For existing evidence, set the three historical constants in the sequence and rerun it.
The explicit measure-free readout projects compile, execution, calls and available cost
without altering frozen criteria or emitting quality means, anchors, improvements,
frontiers or deployment decisions. The separate
[measurement plan](../../docs/plans/2026-10-19-orc-structural-search-measurement-plan.md)
owns unimplemented offline calibration preparation and its later live budget gates.

## Limits

Native receipts can be absent or incomplete; hosted server revisions remain unavailable.
A wrapper mutator runs outside the CLI sandbox; home/network remain shared and scans
are pattern based. Process-group kills cannot stop children that start new sessions.
The ledger serializes one driver process, not separate drivers sharing evidence.
The development check runs in the working clone. See the driver design for remaining
scope and live-qualification limits.
