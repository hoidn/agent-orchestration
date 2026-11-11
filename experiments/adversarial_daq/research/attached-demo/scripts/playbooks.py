"""The recovery playbooks DAQ on-call runs: what each one does, and when it applies.

Each is a documented TMO recovery (SLAC Confluence: "Link And Firmware
Robustness Issues", "Debugging DAQ", "SOP Debugging DAQ"). A playbook is
written once by the people who own the recovery and reviewed like code. The
model only proposes which one, and on what target; check_playbook.py tests
its precondition against the fetched bundle before anyone is asked to
approve, and daq_recover.py runs its steps. Playbooks act only on members of
the partition, as named in the cnf the run was configured with (tmo.cnf in
the bundle). check_playbook and daq_recover list this file in their closure,
so an edit here changes the program and a waiting run refuses to resume.

Each step names the command and the readback that says it worked.
"""
import re
from pathlib import Path

XPM = "DAQ:NEH:XPM:2"


class Member:
    """A DRP process in the cnf: alias, host, and for an HSD its card:side."""

    def __init__(self, alias, host, hsd_side, active):
        self.alias, self.host, self.hsd_side, self.active = alias, host, hsd_side, active

    def remote(self):
        """How this member appears as a decoded RemoteLinkId on the XPM."""
        return f"hsd {self.hsd_side}" if self.hsd_side else self.host

    def __str__(self):
        return f"{self.alias} on {self.host}" + (f" (hsd {self.hsd_side})" if self.hsd_side else "")


def members(cnf_text):
    found = []
    for line in cnf_text.splitlines():
        host = re.search(r"host:\s*'([^']+)'", line)
        alias = re.search(r"id:\s*'([^']+)'", line)
        if not (host and alias):
            continue
        side = re.search(r"hsd_epics_prefix=\{hsd_epics\}_(\w+:\w)", line)
        found.append(Member(alias.group(1), host.group(1), side.group(1) if side else None,
                            active=not line.lstrip().startswith("#")))
    return found


def resolve(target, cnf_text):
    """A target may be a segment alias, a host, or an HSD card:side. Prefer active members."""
    wanted = target.strip().lower().removeprefix("hsd ").removeprefix("1_")
    hits = [m for m in members(cnf_text)
            if wanted in (m.alias.lower(), m.host.lower(), (m.hsd_side or "").lower())]
    hits.sort(key=lambda m: not m.active)
    return hits[0] if hits else None


def _text(bundle_dir, name):
    path = Path(bundle_dir) / name
    return path.read_text() if path.exists() else ""


def links(bundle_dir):
    """The XPM link table: {remote: (link, LinkRxReady, DeadFLnk)}."""
    table = {}
    for line in _text(bundle_dir, "xpm.txt").splitlines():
        row = re.match(r"^\s*(\d+)\s+(.+?)\s+([01])\s+(\d+)\s+([\d.]+)\s*$", line)
        if row:
            table[row.group(2)] = (int(row.group(1)), int(row.group(3)), float(row.group(5)))
    return table


def group(bundle_dir, pv):
    value = re.search(rf"^{XPM}:PART:0:{pv} \S+ \S+\s+([\d.]+)$", _text(bundle_dir, "xpm.txt"), re.M)
    return float(value.group(1)) if value else None


def hsd_sides(bundle_dir):
    """hsdpva summary: {side: (enable, lanes_up, lanes)}."""
    table = {}
    for line in _text(bundle_dir, "hsd.txt").splitlines():
        row = re.match(r"^(\w+:\w)\s+([01])\s+(\d)/(\d)\s", line)
        if row:
            table[row.group(1)] = (int(row.group(2)), int(row.group(3)), int(row.group(4)))
    return table


def write_buffers(bundle_dir, host):
    """From /proc/datadev_0 on host: (write buffer count, write buffers in hardware), or None."""
    section = re.search(rf"==== {re.escape(host)}: .*?(?=^====|\Z)", _text(bundle_dir, "datadev.txt"), re.S | re.M)
    if not section:
        return None
    writes = section.group(0).split("Write Buffers", 1)[-1]
    count = re.search(r"Buffer Count : (\d+)", writes)
    in_hw = re.search(r"Buffers In Hw : (\d+)", writes)
    return (int(count.group(1)), int(in_hw.group(1))) if count and in_hw else None


# --- preconditions: (bundle_dir, member) -> (applies, why) ------------------------------------
def _deadtime_link(bundle_dir, m):
    table = links(bundle_dir)
    if m.remote() not in table:
        return False, f"no XPM link to {m.remote()} in the link table"
    link, ready, dead = table[m.remote()]
    down = [remote for remote, (_, rx, _) in table.items() if rx == 0]
    if ready:
        return False, f"link {link} to {m.remote()} is up (LinkRxReady 1, DeadFLnk {dead:.3f})"
    if len(down) > 1:
        return False, f"{len(down)} links are down ({', '.join(down)}): not a single-link fault"
    deadfrac = group(bundle_dir, "DeadFrac")
    if deadfrac is None or deadfrac < 0.99:
        return False, f"readout group 0 DeadFrac is {deadfrac}, not 100%"
    return True, f"link {link} to {m.remote()} is the only link down (LinkRxReady 0); readout group 0 DeadFrac {deadfrac:g}"


def _stuck_transitions(bundle_dir, _m):
    down = [remote for remote, (_, rx, _) in links(bundle_dir).items() if rx == 0]
    deadfrac, inp, acc = (group(bundle_dir, pv) for pv in ("DeadFrac", "L0InpRate", "L0AccRate"))
    if down:
        return False, f"links are down ({', '.join(down)})"
    if deadfrac is None or deadfrac >= 0.01:
        return False, f"readout group 0 DeadFrac is {deadfrac}: a deadtime problem, not stuck transitions"
    if not (inp and acc == 0):
        return False, f"L0InpRate {inp}, L0AccRate {acc}"
    return True, f"all links up, no deadtime, L0InpRate {inp:g} and L0AccRate 0"


def _hsd_link(bundle_dir, m):
    if not m.hsd_side:
        return False, f"{m.alias} is not an HSD"
    sides = hsd_sides(bundle_dir)
    if m.hsd_side not in sides:
        return False, f"no hsdpva summary for {m.hsd_side}"
    _, up, total = sides[m.hsd_side]
    if up == total:
        return False, f"hsd {m.hsd_side} has {up}/{total} pgp lanes linked"
    return True, f"hsd {m.hsd_side} has only {up}/{total} pgp lanes linked"


def _kcu_buffers(bundle_dir, m):
    buffers = write_buffers(bundle_dir, m.host)
    if buffers is None:
        return False, f"no /proc/datadev_0 snapshot for {m.host} in the bundle"
    count, in_hw = buffers
    if in_hw < count:
        return False, f"{m.host}: {in_hw} of {count} write buffers in hardware, not stuck"
    return True, f"{m.host}: all {count} write buffers are stuck in hardware"


# --- steps: (member, link) -> what the actuator does, each with its readback --------------------
PLAYBOOKS = {
    "deadtime_link": (_deadtime_link, lambda m, link: [
        f"{m.host}: TxPhyPllReset on the KCU1500 timing link (devGui); if LinkRxReady stays 0, "
        "switch timing to xpmmini and back to LCLS2",
        f"pvget {XPM}:LinkRxReady{link}: expect 1; pvget {XPM}:PART:0:DeadFrac: expect below 0.01",
        "control_gui: Disable, then Enable (End Run and Begin Run if Disable still hangs)",
        f"pvget {XPM}:PART:0:L0AccRate: expect it to follow L0InpRate"]),
    "stuck_transitions": (_stuck_transitions, lambda _m, _link: [
        f"groupca {XPM}: Clear readout group 0 (GroupL0Reset)",
        "control_gui: Disable, then Enable",
        f"pvget {XPM}:PART:0:L0AccRate: expect it to follow L0InpRate"]),
    "hsd_link": (_hsd_link, lambda m, _link: [
        "control_gui: Shutdown",
        f"daqmgr restart hsd.py hsdioc_tmo_{m.hsd_side.split(':')[0].lower()} (the hsdioc for {m.hsd_side}; "
        "it serves both sides of the card)",
        f"hsdpva DAQ:TMO:HSD:1_{m.hsd_side}: expect 4/4 pgp lanes linked",
        "restartdaq"]),
    "kcu_buffers": (_kcu_buffers, lambda m, _link: [
        "control_gui: Shutdown",
        f"{m.host}: sudo systemctl restart kcu.service",
        f"{m.host}: cat /proc/datadev_0: expect Write Buffers In Hw 0",
        "restartdaq"]),
}


def check(cause, target, bundle_dir):
    """(applies, why, member) for this cause on this target, against the fetched bundle."""
    member = resolve(target, _text(bundle_dir, "tmo.cnf"))
    if member is None:
        return False, f"{target!r} is not a process in tmo.cnf", None
    if not member.active:
        return False, (f"{member} is not in this partition (commented out of tmo.cnf); "
                       "playbooks only act on partition members"), member
    applies, why = PLAYBOOKS[cause][0](bundle_dir, member)
    return applies, why, member


def steps_for(cause, target, bundle_dir):
    """The steps the actuator runs on this target, as configured in this run's cnf."""
    member = resolve(target, _text(bundle_dir, "tmo.cnf"))
    if member is None or not member.active:
        raise SystemExit(f"playbooks: {target!r} is not a member of this run's partition")
    link = links(bundle_dir).get(member.remote(), ("?",))[0]
    return PLAYBOOKS[cause][1](member, link)
