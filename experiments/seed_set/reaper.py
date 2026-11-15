"""The guard of a launched unit, and the exact kill of a process tree (review3 X5; re-review of fix round 1, minors
n1 and n2).

  python -I reaper.py PGID_FILE -- ARGV...

The guard is the unit's launch (`study.launch`, `host.guarded`): it makes itself a child subreaper, so every orphan
of the unit is reparented to it and the unit's tree stays whole when its root shell dies; it starts ARGV in a
session of its own, writes that session's id and its start time to PGID_FILE, and kills the whole tree (the
provider calls' own sessions and sandboxes included) when its stdin ends (the launcher closed it at a timeout or an
exception, or died) and, once ARGV ended, whatever is left of it. It exits with ARGV's status (128 + N when a
signal N ended it). The command is the guard's child from its first instant, so no moment exists when it runs
unguarded.

A kill is exact (`kill_tree`): each pid is signalled through a pidfd opened while its start time still matches the
scan that listed it, so a pid reused in between is never signalled.

Standard library only, Linux (prctl, pidfd): it runs as its own process, from the host's Python.
"""

import ctypes
import os
import signal
import subprocess
import sys
import threading

PR_SET_CHILD_SUBREAPER = 36
SYS_PIDFD_OPEN = 434  # the same number on every architecture but alpha; os.pidfd_open is missing in some builds
LIBC = ctypes.CDLL(None, use_errno=True)


def stat(pid):
    """(parent pid, start time in clock ticks since boot) of `pid`, or None when it does not exist."""
    try:
        with open(f"/proc/{pid}/stat") as file:
            fields = file.read().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None
    return int(fields[1]), int(fields[19])


def tree(root):
    """{pid: start time} of `root` and its live descendants, from one reading of /proc."""
    children, starts = {}, {}
    for entry in os.listdir("/proc"):
        if entry.isdigit() and (found := stat(entry)):
            children.setdefault(found[0], []).append(int(entry))
            starts[int(entry)] = found[1]
    found, todo = {}, [root]
    while todo:
        pid = todo.pop()
        if pid in starts:
            found[pid] = starts[pid]
            todo += children.get(pid, [])
    return found


def signal_exact(pid, started, signum):
    """Send `signum` to `pid` only while it is the process that started at `started`: a pidfd is opened, then its
    start time is checked, so the signal reaches that process or none."""
    if (handle := LIBC.syscall(SYS_PIDFD_OPEN, pid, 0)) < 0:  # the process is gone
        return
    try:
        if (stat(pid) or (None, None))[1] == started:
            signal.pidfd_send_signal(handle, signum)
    except OSError:
        pass
    finally:
        os.close(handle)


def kill_tree(root, started=None, keep=()):
    """Stop `root`'s tree until no new process appears in it, then kill each of its processes, never one in `keep`
    (the guard itself). Nothing when `started` is given and `root` is not the process that started then."""
    if started is not None and (stat(root) or (None, None))[1] != started:
        return
    stopped = {}
    while new := {pid: t for pid, t in tree(root).items() if pid not in stopped and pid not in keep}:
        for pid, t in new.items():
            signal_exact(pid, t, signal.SIGSTOP)
        stopped |= new
    for pid, t in stopped.items():
        signal_exact(pid, t, signal.SIGKILL)


def guard(pgid_file, argv):
    """Run `argv` as described in the module docstring; return its exit status."""
    if LIBC.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_CHILD_SUBREAPER)")
    me = os.getpid()
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, start_new_session=True)
    with open(pgid_file, "w") as out:  # a recovery refuses while the session lives (`units.session_alive`)
        out.write(f"{child.pid} {stat(child.pid)[1]}\n")
    threading.Thread(target=watch, args=(me,), daemon=True).start()
    status = child.wait()
    kill_tree(me, keep={me})  # what is left once the command ended: orphans of a root shell that died included
    return status if status >= 0 else 128 - status


def run(argv, pgid_file, timeout, **popen):
    """Run `argv` under a guard (this module as a script, in a session of its own) and wait at most `timeout`
    seconds; `popen` gives the guard's env, cwd, stdout and stderr, which the command inherits. Return the command's
    exit status, "timeout" (the guard killed the tree), or, when the guard itself was killed, "guard killed by
    signal N" once this process killed the command's session tree in its place. However this process ends, the end
    of the guard's stdin kills the tree."""
    guard = subprocess.Popen([sys.executable, "-I", __file__, str(pgid_file), "--", *argv], stdin=subprocess.PIPE,
                             start_new_session=True, **popen)
    try:
        status = guard.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        status = "timeout"
    finally:
        guard.stdin.close()
        guard.wait()
    if status == "timeout" or status >= 0:
        return status
    if os.path.isfile(pgid_file):
        kill_tree(*map(int, open(pgid_file).read().split()))
    return f"guard killed by signal {-status}"


def watch(me):
    """Kill the guard's tree when its stdin ends: the launcher closed it, or died."""
    while os.read(0, 4096):  # unbuffered: a blocked read holds no lock the interpreter's exit needs
        pass
    kill_tree(me, keep={me})


if __name__ == "__main__":
    if sys.argv[2:3] != ["--"] or len(sys.argv) < 4:
        raise SystemExit("usage: python -I reaper.py PGID_FILE -- ARGV...")
    sys.exit(guard(sys.argv[1], sys.argv[3:]))
