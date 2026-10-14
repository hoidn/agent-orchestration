import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from profile import ensure_delegated, Slot, Holder
ensure_delegated(sys.argv)
import image_import
record = json.loads(Path(sys.argv[1]).read_text())
rootfs = image_import.admit(record)
work = Path(tempfile.mkdtemp(prefix="runref-spike-"))
(work / "clone").mkdir(); (work / "clone" / "hello.txt").write_text("hi\n")
(work / "result").mkdir()
slot = Slot("attempt-smoke", memory_mib=256, pids=64, cpus=1)
holder = Holder(slot, rootfs, work / "result", work / "control", workspace_mib=16, scratch_mib=8)
try:
    print(holder.seed(work / "clone"))
    print(holder.leaf("l0", ["true"]))
    print(holder.leaf("l1", ["python3", "-c", "import os; print(os.listdir('/workspace'), os.getuid(), open('/proc/self/status').read().split('CapEff:')[1].split()[0])"]))
    print(sorted(p.name for p in holder.host_view().iterdir()))
finally:
    holder.stop(); slot.remove()
