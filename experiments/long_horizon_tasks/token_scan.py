"""Find the passthrough's token in files by its fingerprint, never by its value (plan D4, "The check").

The passthrough writes `fingerprint.json` at its start: a random salt, the token's length and the SHA-256
of salt + token. This scanner hashes every candidate string of that length (every window inside a run of
the bearer-token alphabet, RFC 6750 `b64token`) and prints the path and byte offset of a match, never the
bytes around it. It finds the whole token in plain form; not a part of it and not an encoded copy.

Usage: python -I token_scan.py scan --fingerprint FILE PATH...
           PATH is a file, a directory (walked; symlinks and special files are skipped) or `-` (stdin).
           Prints `match <path> <offset>` and `unreadable <path> <error class>` lines, then
           `scanned <n> files`. Exit 0: nothing found; 1: a match (a stop); 2: no match, but a file or
           directory could not be read (the scan is incomplete).
       python -I token_scan.py canary --fingerprint FILE --canary FILE DIR [PATH...]
           The canary check: the canary file must be what the fingerprint was made from (the canary was the
           passthrough's token); a copy planted in DIR must be found there, at its offset; and nothing else
           in the set may match. The planted copy is removed. Exit 0 when all three hold, 1 otherwise.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from pathlib import Path

ALPHABET = rb"A-Za-z0-9\-._~+/="  # RFC 6750 b64token; the passthrough refuses a token outside it
READ = 1 << 20


def fingerprint(token):
    """The fingerprint of `token`: {salt, length, sha256}; written beside the passthrough's log."""
    salt = secrets.token_bytes(16)
    return {"salt": salt.hex(), "length": len(token), "sha256": hashlib.sha256(salt + token.encode()).hexdigest()}


def matches(fp, candidate):
    return hashlib.sha256(bytes.fromhex(fp["salt"]) + candidate.encode()).hexdigest() == fp["sha256"]


def scan_stream(stream, fp):
    """Byte offsets in `stream` where the fingerprinted token starts."""
    length, salt, want = fp["length"], bytes.fromhex(fp["salt"]), fp["sha256"]
    runs = re.compile(rb"[%s]{%d,}" % (ALPHABET, length))
    carry, base, found = b"", 0, set()
    while chunk := stream.read(READ):
        buf = carry + chunk
        for run in runs.finditer(buf):
            for i in range(run.start(), run.end() - length + 1):
                if hashlib.sha256(salt + buf[i:i + length]).hexdigest() == want:
                    found.add(base + i)
        keep = min(len(buf), length - 1)  # a window that crosses into the next read starts in these bytes
        carry, base = buf[len(buf) - keep:], base + len(buf) - keep
    return sorted(found)


def _files(path, unreadable):
    if not os.path.isdir(path) or os.path.islink(path):
        yield path
        return
    for root, dirs, files in os.walk(path, onerror=lambda exc: unreadable.append((exc.filename, exc))):
        dirs.sort()
        for name in sorted(files):
            yield os.path.join(root, name)


def scan(paths, fp):
    """(matches as (path, offset), unreadable as (path, error class name), files read)."""
    found, unreadable, errors, count = [], [], [], 0
    for top in paths:
        for path in _files(top, errors):
            try:
                if path == "-":
                    offsets = scan_stream(sys.stdin.buffer, fp)
                elif stat.S_ISREG(os.lstat(path).st_mode):
                    with open(path, "rb") as fh:
                        offsets = scan_stream(fh, fp)
                else:
                    continue
            except OSError as exc:  # an unreadable file is reported, and makes the scan incomplete
                unreadable.append((path, type(exc).__name__))
                continue
            count += 1
            found += [(path, offset) for offset in offsets]
    unreadable += [(path, type(exc).__name__) for path, exc in errors]
    return found, unreadable, count


def _report(found, unreadable, count):
    for path, offset in found:
        print("match", path, offset)
    for path, error in unreadable:
        print("unreadable", path, error)
    print("scanned", count, "files")
    return 1 if found else 2 if unreadable else 0


def _canary(args, fp):
    canary = Path(args.canary).read_text().strip()
    if not matches(fp, canary):
        print("canary: the fingerprint was not made from this canary")
        return 1
    plant = Path(args.paths[0]) / f"lh-canary-plant-{secrets.token_hex(4)}.txt"
    filler = "planted canary copy: "
    plant.write_text(f"{filler}{canary}\n")
    try:
        found, unreadable, count = scan(args.paths, fp)
    finally:
        plant.unlink()
    code = _report([f for f in found if f != (str(plant), len(filler))], unreadable, count)
    if (str(plant), len(filler)) not in found:
        print("canary: the planted copy was not found")
        return 1
    print("canary:", "pass" if code == 0 else "fail")
    return 0 if code == 0 else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "canary"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--fingerprint", required=True)
        if name == "canary":
            cmd.add_argument("--canary", required=True)
        cmd.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    fp = json.loads(Path(args.fingerprint).read_text())
    if args.command == "canary":
        return _canary(args, fp)
    return _report(*scan(args.paths, fp))


if __name__ == "__main__":
    sys.exit(main())
