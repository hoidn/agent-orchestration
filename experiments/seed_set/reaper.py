"""Kill a launched unit's whole process tree: the launch's own process group and every group its descendants opened.
A provider call runs in a session of its own (the orchestrator starts it so), so killing the launch's group alone
leaves the agent running after its launcher died (review3 X5).

  python -I reaper.py PID    the guard of a launch (`study.launch`): it waits on stdin and, unless it reads
                             "done" (the launcher's normal end), kills PID's tree; a launcher killed with SIGKILL
                             closes the pipe and so kills its unit.

Standard library only: it runs as its own process, from the host's Python.
"""

import os
import signal
import sys


def tree(root):
    """PID `root` and its live descendants, read from /proc."""
    children = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as stat:
                parent = int(stat.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(parent, []).append(int(entry))
    found, todo = [], [root]
    while todo:
        pid = todo.pop()
        found.append(pid)
        todo += children.get(pid, [])
    return found


def quietly(kill, target, signum):
    try:
        kill(target, signum)
    except (ProcessLookupError, PermissionError):
        pass


def kill_tree(root):
    """Stop `root`'s tree until no new process appears in it, then kill every process and process group in it (the
    launch's own group `root` included, whatever is left of the tree)."""
    stopped = set()
    while new := set(tree(root)) - stopped:
        for pid in new:
            quietly(os.kill, pid, signal.SIGSTOP)
        stopped |= new
    groups = {root}
    for pid in stopped:
        try:
            groups.add(os.getpgid(pid))
        except ProcessLookupError:
            pass
    for group in groups - {os.getpgid(0)}:
        quietly(os.killpg, group, signal.SIGKILL)
    for pid in stopped:
        quietly(os.kill, pid, signal.SIGKILL)


if __name__ == "__main__":
    if sys.stdin.buffer.read() != b"done":
        kill_tree(int(sys.argv[1]))
