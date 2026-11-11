#!/usr/bin/env python3
"""Tool-layer stand-in: fetch the log bundle for a stalled DAQ run.

In the facility this is an access-checked tool that gathers, for one run: the
shift's elog entries, the control-level log, the XPM readout-group and link
status (pvget, and a link table rendered from the per-link PVs), an archiver
query of the link PVs, the DRP Prometheus metrics, the hsdpva summary,
/proc/datadev_0 from each DRP node, the cnf the run was configured with, and
the procmgr logs of the DRPs. Here it copies a canned stall from
fixtures/stall-<run>/ into
artifacts/daq/<run>/<orchestrator run id>/, one directory per orchestrator
run, and concatenates everything into bundle.txt, the document the model is
given. Returns the typed LogBundle the workflow declared.
"""
import argparse
import json
import os
import shutil
from pathlib import Path

ORDER = ["shift.log", "control.log", "xpm.txt", "archiver.txt", "prometheus.txt", "hsd.txt", "datadev.txt",
         "tmo.cnf"]

ap = argparse.ArgumentParser()
ap.add_argument("--hutch", required=True)
ap.add_argument("--run", required=True, type=int)
args = ap.parse_args()

src = Path("fixtures") / f"stall-{args.run}"
if not src.is_dir():
    raise SystemExit(f"daq_logs: no log bundle for {args.hutch} run {args.run} (looked in {src})")

out = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
# the bundle path is .orchestrate/runs/<run id>/effects/...: name the snapshot after its run
parts = out.parts
fetch = parts[parts.index("runs") + 1] if "runs" in parts else "latest"
dst = Path("artifacts") / "daq" / str(args.run) / fetch
dst.mkdir(parents=True, exist_ok=True)
for item in sorted(src.iterdir()):
    shutil.copyfile(item, dst / item.name)

names = [n for n in ORDER if (dst / n).exists()]
names += sorted(p.name for p in dst.iterdir() if p.name.endswith(".log") and p.name not in names)
with (dst / "bundle.txt").open("w") as bundle:
    for name in names:
        bundle.write(f"==== {name} ====\n{(dst / name).read_text()}\n")

out.write_text(json.dumps({"logs": str(dst / "bundle.txt"), "run_number": args.run}))
print(f"daq_logs: {args.hutch} run {args.run}: {len(names)} sources in {dst / 'bundle.txt'}")
