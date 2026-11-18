"""Find the passthrough's token in files by its fingerprint, never by its value (plan D4, "The check").

The forms of a token (`forms`): plain; hex, lower and upper case; base64, standard and URL-safe, at the three
alignments a copy can have inside a longer encoded stream (the encoding of the token's whole 3-byte groups
from offset 0, 1 or 2, which appears verbatim in the base64 of any stream holding the token); UTF-16LE.
The fingerprint (`fingerprint`), written by the passthrough beside its log at its start: one random salt, and
for each form its length and the SHA-256 of salt + form. It cannot give the token back: the token is assumed
high-entropy (a `setup-token` token or a canary of about 100 random characters), so no search over candidate
tokens can reach a hash, and the salt defeats precomputed tables; it discloses the token's length and nothing
else. This scanner hashes every candidate window of each form's length (every window inside a run of the
form's alphabet: RFC 6750 `b64token` for the text forms, its characters each followed by a NUL for UTF-16LE)
and prints the path, byte offset and form of a match, never the bytes around it. It finds whole copies only:
not a part of the token and not any other encoding (compressed, encrypted, escaped beyond JSON).

Usage: python -I token_scan.py scan --fingerprint FILE [--jobs N] PATH...
           PATH is a file, a directory (walked; symlinks and special files inside it are skipped, each named on
           a `skipped <path> <kind>` line) or `-` (stdin, read in this process).
           --jobs N: the files are read in N processes (default: the CPU count); 1 reads them here, one by one.
           The output is the same for every N.
           Prints `match <path> <offset> <form>` and `unreadable <path> <reason>` lines, then `scanned <n> files`.
           Exit 0: nothing found; 1: a match (a stop); 2: no match, but the scan is incomplete: a named path is
           missing, unreadable, a symlink or not a file or directory, a file inside could not be read, no file
           at all was read, or the scanner itself failed (a crash is never read as a match).
       python -I token_scan.py canary --fingerprint FILE --canary FILE [--jobs N] DIR [PATH...]
           The canary check: the canary must be what the fingerprint was made from (it was the passthrough's
           token); a copy of every form planted in DIR must be found there at its offset; nothing else in the
           set may match. The planted file is removed. Exit 0 when all three hold, 1 otherwise.
"""

import argparse
import base64
from concurrent.futures import ALL_COMPLETED, FIRST_COMPLETED, ProcessPoolExecutor, wait
import contextlib
import hashlib
import json
import multiprocessing
import os
import re
import secrets
import stat
import sys
from pathlib import Path

ALPHABET = rb"A-Za-z0-9\-._~+/="  # RFC 6750 b64token; the passthrough refuses a token outside it
RUNS = {"text": rb"[%s]{%d,}", "wide": rb"(?:[%s]\x00){%d,}"}
READ = 1 << 20
AHEAD = 256  # files handed to the workers and not yet read, at most: a file is read soon after it is listed


def forms(token):
    """{form name: bytes} for every form the scanner and the passthrough's guard look for."""
    raw = token.encode()
    found = {"plain": raw, "hex": raw.hex().encode(), "HEX": raw.hex().upper().encode(),
             "utf16le": token.encode("utf-16-le")}
    for skip in range(3):
        whole = raw[skip:skip + (len(raw) - skip) // 3 * 3]
        found[f"base64-{skip}"] = base64.b64encode(whole)
        found[f"base64url-{skip}"] = base64.urlsafe_b64encode(whole)
    return found


def _kind(name):
    return "wide" if name == "utf16le" else "text"


def fingerprint(token):
    """The fingerprint of `token`: one salt; per form its length and salted SHA-256. Holds no form."""
    salt = secrets.token_bytes(16)
    return {"salt": salt.hex(), "forms": [{"name": name, "length": len(form),
                                            "sha256": hashlib.sha256(salt + form).hexdigest()}
                                           for name, form in forms(token).items()]}


def matches(fp, candidate, form="plain"):
    entry = next(f for f in fp["forms"] if f["name"] == form)
    return hashlib.sha256(bytes.fromhex(fp["salt"]) + candidate.encode()).hexdigest() == entry["sha256"]


def _targets(fp):
    """{kind: {length: {digest: form name}}}"""
    targets = {}
    for entry in fp["forms"]:
        by_length = targets.setdefault(_kind(entry["name"]), {}).setdefault(entry["length"], {})
        by_length[bytes.fromhex(entry["sha256"])] = entry["name"]
    return targets


def _hits(buf, salt, targets):
    """(offset in buf, form name) of every window of buf that hashes to a form."""
    salted, view = hashlib.sha256(salt), memoryview(buf)
    for kind, by_length in targets.items():
        step = 2 if kind == "wide" else 1
        shortest = min(by_length) // step
        for run in re.finditer(RUNS[kind] % (ALPHABET, shortest), buf):
            for length, hashes in by_length.items():
                for i in range(run.start(), run.end() - length + 1, step):
                    window = salted.copy()
                    window.update(view[i:i + length])
                    if name := hashes.get(window.digest()):
                        yield i, name


def scan_stream(stream, fp):
    """Sorted (offset, form) pairs where a form of the fingerprinted token starts in `stream`."""
    salt, targets = bytes.fromhex(fp["salt"]), _targets(fp)
    longest = max(entry["length"] for entry in fp["forms"])
    carry, base, found = b"", 0, set()
    while chunk := stream.read(READ):
        buf = carry + chunk
        found |= {(base + i, name) for i, name in _hits(buf, salt, targets)}
        keep = min(len(buf), longest - 1)  # a window that crosses into the next read starts in these bytes
        carry, base = buf[len(buf) - keep:], base + len(buf) - keep
    return sorted(found)


def _named(path):
    """The reason a named path cannot be scanned, or None."""
    if path == "-":
        return None
    if os.path.islink(path):
        return "symlink"
    if not os.path.exists(path):
        return "missing"
    mode = os.stat(path).st_mode
    return None if stat.S_ISDIR(mode) or stat.S_ISREG(mode) else "not a file or directory"


def _files(path, unreadable):
    if path == "-" or not os.path.isdir(path):
        yield path
        return
    for root, dirs, files in os.walk(path, onerror=lambda exc: unreadable.append((exc.filename, type(exc).__name__))):
        dirs.sort()
        for name in sorted(files):
            yield os.path.join(root, name)


def _unread(path):
    """Why a walked file is not read, taken when the walk lists it: the kind of a symlink or special file inside a
    directory (not followed), or the OSError of its lstat; None for stdin and a regular file."""
    if path == "-":
        return None
    try:
        mode = os.lstat(path).st_mode
    except OSError as exc:
        return exc
    if stat.S_ISREG(mode):
        return None
    return "symlink" if stat.S_ISLNK(mode) else "special file"


def _scan_one(path, fp):
    """The hits of stdin or a regular file, or the OSError that kept it from being read."""
    try:
        if path == "-":
            return scan_stream(sys.stdin.buffer, fp)
        with open(path, "rb") as fh:
            return scan_stream(fh, fp)
    except OSError as exc:  # returned, not raised: only a worker's own failure reaches the parent as an exception
        return exc


def _settle(running, results, return_when=FIRST_COMPLETED):
    """Wait for the reads of `running` ({future: walk index}) as `return_when` says and move each finished one's
    result to `results` ({walk index: result}). A worker that raised or died raises here."""
    for future in wait(running, return_when=return_when).done:
        results[running.pop(future)] = future.result()


def _read(paths, fp, jobs):
    """(walked, results): each file under the scannable `paths` in walk order, with each directory os.walk could
    not list in its place as (path, OSError class name); and {walk index: _scan_one's result} of each file, read in
    `jobs` processes, AHEAD at most at a time, or here when `jobs` is 1 (stdin always here). Each file's kind is
    taken here when the walk lists it; a worker only reads a regular file."""
    walked, results, running = [], {}, {}
    pool = _pool(jobs)
    with pool or contextlib.nullcontext():
        for top in [p for p in paths if not _named(p)]:
            for path in _files(top, walked):
                walked.append(path)
                index, unread = len(walked) - 1, _unread(path)
                if unread is not None:
                    results[index] = unread
                elif pool is None or path == "-":
                    results[index] = _scan_one(path, fp)
                else:
                    running[pool.submit(_scan_one, path, fp)] = index
                    if len(running) >= AHEAD:
                        _settle(running, results)
        _settle(running, results, ALL_COMPLETED)
    return walked, results


def _pool(jobs):
    """None when `jobs` is 1, else a pool of `jobs` worker processes, every one of them started."""
    if jobs == 1:
        return None
    # fork: a worker is a copy of this process, so under `python -I` it needs no importable module to run _scan_one
    pool = ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("fork"))
    pool.submit(int).result()  # forks every worker now, before the walk, so no file's lstat waits for the forks
    return pool


def scan(paths, fp, skipped=None, jobs=None):
    """(matches as (path, offset, form), unreadable as (path, reason), files read); each path skipped inside a
    directory is appended to `skipped` as (path, kind). The files are read in `jobs` processes (None: one per CPU;
    1: here, one by one); stdin is read here. The result is the same for every `jobs`."""
    found, count, skipped = [], 0, [] if skipped is None else skipped
    unreadable = [(path, reason) for path in paths if (reason := _named(path))]
    walked, results = _read(paths, fp, jobs)
    for index, entry in enumerate(walked):
        if isinstance(entry, tuple):  # a directory os.walk could not list
            unreadable.append(entry)
            continue
        hits = results[index]
        if isinstance(hits, OSError):  # an unreadable file is reported, and makes the scan incomplete
            unreadable.append((entry, type(hits).__name__))
        elif isinstance(hits, str):
            skipped.append((entry, hits))
        else:
            count += 1
            found += [(entry, offset, name) for offset, name in hits]
    return found, unreadable, count


def _report(found, unreadable, count, skipped=()):
    for path, offset, name in found:
        print("match", path, offset, name)
    for path, reason in unreadable:
        print("unreadable", path, reason)
    for path, kind in skipped:
        print("skipped", path, kind)
    print("scanned", count, "files")
    return 1 if found else 2 if unreadable or not count else 0


def _canary(args, fp):
    canary = Path(args.canary).read_text().strip()
    if not matches(fp, canary):
        print("canary: the fingerprint was not made from this canary")
        return 1
    plant = Path(args.paths[0]) / f"lh-canary-plant-{secrets.token_hex(4)}.txt"
    text, planted = b"", set()
    for form in forms(canary).values():
        text += b"planted copy: "
        planted.add((str(plant), len(text)))
        text += form + b"\n"
    plant.write_bytes(text)
    try:
        found, unreadable, count = scan(args.paths, fp, jobs=args.jobs)
    finally:
        plant.unlink()
    code = _report([f for f in found if f[0] != str(plant)], unreadable, count)
    missed = planted - {(path, offset) for path, offset, _ in found}
    if missed:
        print("canary: planted copies not found at offsets", sorted(offset for _, offset in missed))
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
        cmd.add_argument("--jobs", type=int, default=os.cpu_count())
        cmd.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    fp = json.loads(Path(args.fingerprint).read_text())
    if args.command == "canary":
        return _canary(args, fp)
    skipped = []
    return _report(*scan(args.paths, fp, skipped, args.jobs), skipped)


def _main(argv):
    """main, with any failure of the scanner itself an incomplete scan (exit 2), never a match (Task 8 m1)."""
    try:
        return main(argv)
    except Exception as exc:  # the class only: never a message that could quote what was read
        print("failed", type(exc).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
