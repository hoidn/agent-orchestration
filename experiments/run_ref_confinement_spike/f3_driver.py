"""Throwaway F2/F3 driver. Usage: python f3_driver.py <image-record.json>; prints JSON evidence."""
import errno, hashlib, json, os, shutil, socket, stat, subprocess, sys, tempfile, time
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from profile import ensure_delegated, Slot, Holder
ensure_delegated(sys.argv)
import image_import
sys.path.insert(0, str(HERE.parents[1]))
from orchestrator.providers.isolation_backend import CgroupV2ContainmentRoot, DurableLaunchReleaseGate

evidence = {}
record = json.loads(Path(sys.argv[1]).read_text())
started = time.monotonic()
rootfs = image_import.admit(record)
evidence["admission"] = {"image": record["image"], "tree_digest": record["tree_digest"],
                         "admit_seconds": round(time.monotonic() - started, 2)}
try:
    image_import.admit({**record, "tree_digest": "sha256:" + "0" * 64})
except RuntimeError as exc:
    evidence["admission"]["tampered_record"] = str(exc)
pin_row = next(row for row in image_import.tree_manifest(rootfs) if row[0] == "usr/local/bin/python3.12")
pin = {"guest_path": "/usr/local/bin/python3.12", "sha256": pin_row[4], "tree_digest": record["tree_digest"]}
evidence["executable_pin"] = {**pin, "host_which_python3": shutil.which("python3")}

work = Path(tempfile.mkdtemp(prefix="runref-f3-"))
git_env = {"PATH": "/usr/bin:/bin", "HOME": str(work), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}
parent = work / "parent"
parent.mkdir()
(parent / "hello.txt").write_text("hi\n")
for name in ("guest_command.py", "guest_escape.py"):
    shutil.copy(HERE / name, parent / name)
for args in (["init", "-q"], ["add", "."], ["-c", "user.name=s", "-c", "user.email=s@e", "commit", "-qm", "base"]):
    subprocess.run(["git", *args], cwd=parent, env=git_env, check=True)
subprocess.run(["git", "clone", "-q", "--shared", str(parent), str(work / "clone")], env=git_env, check=True)
sibling = work / "sibling"
shutil.copytree(work / "clone", sibling, symlinks=True)
control_root = work / "control" / "runs" / "child-1"   # authority: header/program/memo/request live here
control_root.mkdir(parents=True, mode=0o700)
for name in ("run.json", "closed_program.json", "memo.jsonl", "request.json"):
    (control_root / name).write_text("{}\n")
(work / "result").mkdir()
abstract_name = f"runref-spike-{os.getpid()}"
listener = socket.socket(socket.AF_UNIX)
listener.bind("\0" + abstract_name)
listener.listen(1)

# Containment authority assumptions of the existing backend.
root = CgroupV2ContainmentRoot.discover()
try:
    (root.path / "cgroup.subtree_control").write_text("+memory")
    discovered = "controllers enabled"
except OSError as exc:
    discovered = errno.errorcode[exc.errno]
evidence["containment_root_discover"] = {"path": str(root.path), "enable_memory_for_slots": discovered,
                                         "has_memory_max": (root.path / "memory.max").exists()}

slot = Slot("attempt-1", memory_mib=256, pids=64, cpus=1)
evidence["slot_limits"] = slot.limits
gate_dir = work / "control" / "launch"
gate_dir.mkdir(mode=0o700)
slot_identity = "sha256:" + hashlib.sha256(f"{slot.path}:{os.stat(slot.path).st_ino}".encode()).hexdigest()
gate = DurableLaunchReleaseGate.create(gate_dir / "holder.json", launch_token="sha256:" + "1" * 64,
                                       containment_identity=slot_identity)
gate.record_intent()
permit = gate.record_commit()
holder = Holder(slot, rootfs, work / "result", work / "ipc", workspace_mib=16, scratch_mib=8)
gate.consume_release(permit)
try:
    gate.consume_release(permit)
    replay = "accepted"
except Exception as exc:
    replay = type(exc).__name__
evidence["release_gate"] = {"events": list(gate.events), "release_consumed": gate.release_consumed, "replay": replay}
sibling_holder = Holder(Slot("attempt-sibling", memory_mib=64, pids=16, cpus=1), rootfs, work / "result",
                        work / "ipc-sibling", workspace_mib=4, scratch_mib=4)
sibling_holder.seed(sibling)
evidence["holder_argv"] = holder.argv[:-3] + ["<spawner>"]
try:
    evidence["seed"] = holder.seed(work / "clone")
    evidence["workflow_command"] = holder.leaf("cmd-1", [pin["guest_path"], "guest_command.py", "attempt-1"])
    result_path = work / "result" / "attempt-1" / "result.json"
    evidence["workflow_command"]["host_result"] = json.loads(result_path.read_text())
    evidence["workflow_command"]["host_view_hello"] = (holder.host_view() / "hello.txt").read_text()

    absent = {"parent_repo": str(parent), "sibling_clone": str(sibling), "worktree": str(HERE.parents[1]),
              "authority_control_root": str(control_root), "launch_gate_dir": str(gate_dir),
              "host_python": shutil.which("python3"), "codex_auth": os.path.expanduser("~/.codex/auth.json"),
              "claude_dir": os.path.expanduser("~/.claude"), "ssh_dir": os.path.expanduser("~/.ssh"),
              "user_bus": f"/run/user/{os.getuid()}/bus", "docker_sock": "/var/run/docker.sock",
              "sibling_holder_view": str(sibling_holder.host_view())}
    escape = holder.leaf("escape", [pin["guest_path"], "guest_escape.py", json.dumps(
        {"absent_paths": absent, "abstract_socket": abstract_name, "python_pin": pin["guest_path"]})])
    evidence["escape"] = {**escape, "stdout": json.loads(escape["stdout"] or "{}")}

    # Host reads of candidate files: naive path walk vs no-follow reader.
    view = holder.host_view()
    naive = (view / "leak").read_text().strip()
    evidence["host_reads"] = {"naive_symlink_follow_reads_host_etc_hostname":
                              naive == Path("/etc/hostname").read_text().strip()}
    root_fd = os.open(view, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    for name in ("leak", "hello-hardlink", "hello.txt"):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
            info = os.fstat(fd)
            os.close(fd)
            verdict = "refused:hardlink" if info.st_nlink != 1 else "read:regular"
        except OSError as exc:
            verdict = "refused:" + errno.errorcode[exc.errno]
        evidence["host_reads"]["nofollow:" + name] = verdict
    os.close(root_fd)
    evidence["host_reads"]["hook_is_data"] = stat.filemode(os.lstat(view / ".git/hooks/post-checkout").st_mode)

    shmem = lambda s: int(next(l.split()[1] for l in s.stat("memory.stat").splitlines() if l.startswith("shmem ")))
    before = shmem(slot)
    quota = holder.leaf("quota", ["/bin/sh", "-c", "dd if=/dev/zero of=/workspace/big bs=1M count=32 2>&1 | tail -2; stat -c %s /workspace/big"])
    evidence["workspace_quota"] = {**quota, "slot_shmem_delta_mib_after_leaf_exit": round((shmem(slot) - before) / 2**20, 2)}
    (holder.host_view() / "big").unlink()  # host frees quota for the next probes

    events = lambda s, f: dict(l.split() for l in s.stat(f).splitlines())
    oom_before = int(events(slot, "memory.events")["oom_kill"])
    memory = holder.leaf("memory", [pin["guest_path"], "-c",
        "b=[]\nfor i in range(40):\n b.append(bytearray(16<<20)); print((i+1)*16, flush=True)"], timeout=60)
    evidence["memory_max"] = {**memory, "stdout_tail": memory["stdout"].split()[-1:], "stdout": None,
                              "oom_kill_delta": int(events(slot, "memory.events")["oom_kill"]) - oom_before,
                              "memory_peak_mib": round(int(slot.stat("memory.peak")) / 2**20, 1)}
    pids = holder.leaf("pids", [pin["guest_path"], "-c",
        "import os, time\nn=0\ntry:\n for _ in range(200):\n  if os.fork()==0:\n   time.sleep(30); os._exit(0)\n  n+=1\nexcept OSError as e:\n print('fork failed after', n, e.strerror)"], timeout=20)
    evidence["pids_max"] = {**pids, "pids_events": events(slot, "pids.events")}
    cpu_before = int(events(slot, "cpu.stat")["usage_usec"])
    wall = time.monotonic()
    cpu = holder.leaf("cpu", ["/bin/sh", "-c",
        "for i in 1 2 3 4; do timeout 2 sh -c 'while :; do :; done' & done; wait"], timeout=20)
    used = (int(events(slot, "cpu.stat")["usage_usec"]) - cpu_before) / 1e6
    evidence["cpu_max"] = {**cpu, "cpu_seconds": round(used, 2), "wall_seconds": round(time.monotonic() - wall, 2),
                           "nr_throttled": events(slot, "cpu.stat")["nr_throttled"]}
    evidence["descendants"] = holder.leaf("daemon", ["/bin/sh", "-c", "setsid sleep 300 >/dev/null 2>&1 & echo started"])
    evidence["descendants"]["sleep_300_left"] = [p for p in (slot.path / "holder" / "cgroup.procs").read_text().split()
                                                 if "300" in Path(f"/proc/{p}/cmdline").read_text()]
    evidence["wall_timeout"] = holder.leaf("timeout", ["/usr/bin/sleep", "100"], timeout=1)
finally:
    mem_live = int(slot.stat("memory.current"))
    holder.stop()
    sibling_holder.stop()
    evidence["teardown"] = {"memory_current_mib_live": round(mem_live / 2**20, 1),
                            "memory_current_mib_after_holder_stop": round(int(slot.stat("memory.current")) / 2**20, 1),
                            "slot_populated_after_stop": Slot.populated(slot.path)}
    slot.remove()
    sibling_holder.slot.remove()

# Workspace larger than memory.max: does tmpfs hit ENOSPC or the OOM killer first?
small = Slot("attempt-small-memory", memory_mib=48, pids=32, cpus=1)
squeezed = Holder(small, rootfs, work / "result", work / "ipc-small", workspace_mib=128, scratch_mib=4)
try:
    oom_before = int(events(small, "memory.events")["oom_kill"])
    over = squeezed.leaf("over", ["/bin/sh", "-c", "dd if=/dev/zero of=/workspace/big bs=1M count=100 2>&1 | tail -2"], timeout=30)
    evidence["workspace_over_memory"] = {**over, "oom_kill_delta": int(events(small, "memory.events")["oom_kill"]) - oom_before,
                                         "holder_alive": Slot.populated(small.path / "holder")}
finally:
    squeezed.stop()
    small.remove()
listener.close()
print(json.dumps(evidence, indent=1, default=str))
