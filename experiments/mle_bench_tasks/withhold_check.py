"""The withholding check on a built agent image (MLE-bench family plan, decision M3 and Task 3).

A guard against accidental inclusion of withheld files in images we build ourselves. It runs on the agent image's
exported file system before any attempt, and its result names the image by its digest, the competition, a digest
of every input and of this file, so a later gate can require a pass made by this code against these inputs. Inputs:
the export (a directory, or a plain tar read as a stream, never unpacked to disk); the competition's id, private
directory, grading-code directory (the benchmark's competition directory, holding grade.py), leaderboard snapshot
and public directory; optionally directories withheld by hash only (`--withheld`, the raw download) and a list of
exemptions for "not inspected" findings (`--exempt`).

What is a hit (each a kind of finding in the result):
  private_hash, grader_hash, leaderboard_hash, withheld_file: a file whose SHA-256 equals that of a private file,
      a grading-code file, the leaderboard snapshot or a file under a withheld directory, under any name and at any
      depth. A file byte-identical to a public file is public content: never reported, and not opened further.
  private_lines: a file holding at least one private-only line. A private-only line is a line of a private file
      with no NUL byte, other than its first line (the header) and blank lines, that occurs in no public file. Lines
      are split on `\\n`, compared as bytes with surrounding whitespace stripped (so CRLF and LF match); a file's
      count is the number of distinct such lines it holds, per private file. Which lines of a file are compared:
      every line of a file named as a table or text (TEXT_TYPES), and of a file with no suffix and no NUL byte in
      its first FIRST_BLOCK bytes, NUL bytes notwithstanding; the lines before the first NUL byte of any other file.
  benchmark: a path component named for the benchmark's package (`mlebench`, `mlebench-<...>`, `mlebench.<...>`,
      `__editable__.mlebench...`) or for the competition id, as a directory, a file or an archive (`<id>.tar.gz`).
Fail closed (each fails the check, with the path named):
  unreadable: a path that cannot be read, a special file (fifo, device, socket), a tar member that cannot be
      extracted, an archive whose bytes match its format but cannot be read to its end, a hard link to a member
      not earlier in the tar.
  export_incomplete: a tar export that cannot be opened, or is not read to its end-of-archive marker (at least
      END_MARKER NUL bytes after the last member and nothing else after them): a cut or corrupted export.
  not_inspected: an archive over the archive cap, or an archive inside an archive. Only these may be exempted, by
      SHA-256 with a reason (`--exempt`); an exempted one is listed under `exempted` and no longer fails.
  links_outside: a symbolic link whose target climbs above the export's root. An absolute target is resolved
      against the export's root, as the container sees it (`/usr/bin/x -> /etc/alternatives/x` stays inside).
      No symbolic link is followed.
An export with no regular file fails too.

Archives: a file is opened as an archive only when its suffix is one of ARCHIVES and its first bytes match that
format (gzip `1f 8b`; zip `PK\\3\\4` or `PK\\5\\6`; tar `ustar` at offset 257). Any other file is an ordinary file,
hashed and line-checked. An archive up to ARCHIVE_CAP is held in memory and opened one level deep; a member whose
bytes match any of the three formats, whatever its name, is a nested archive (so a `.gz` holding a tar is two
levels). The hard link of a tar gets its target's findings under its own path, as the directory form reads it.

Caps and memory (real images are several gigabytes; a public training table can be hundreds of megabytes):
  ARCHIVE_CAP (64 MiB, `cap`): the only cap on a file's size. Every other file is read once as a stream in CHUNK
      pieces and never loaded whole.
  LINE_CAP (1 MiB): a line longer than this is not compared (never kept whole), on every side, the header included.
  Memory: the private-only line set, one 16-byte BLAKE2b digest per line, built straight into one dict and
      measured at about 110 bytes per line (a million lines: 132 MB peak for the whole run, against 25 MB with the
      fixture's 40; ten million about 1.1 GB), plus one archive of at most ARCHIVE_CAP, plus
      CHUNK and one line of at most LINE_CAP. Time grows with the export's size and archive members' size.

What this cannot see is listed in LIMITS and copied into every result.

Usage: python -m experiments.mle_bench_tasks.withhold_check --image-ref R --competition ID --export PATH \\
           --private DIR --grader DIR --leaderboard FILE --public DIR [--withheld DIR]... [--exempt FILE] \\
           --out result.json
       The output path is removed first and written last, through a temporary file and os.replace: an interrupted
       or crashed run leaves no result. Exit 0: pass; 1: fail (result written) or a crash (none written);
       2: refused (bad inputs; none written).
"""

import argparse
import collections
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path
from typing import NamedTuple

from experiments.mle_bench_tasks.wrap import PINNED

ARCHIVE_CAP = 64 << 20
LINE_CAP = 1 << 20
CHUNK = 1 << 20
FIRST_BLOCK = 8192
END_MARKER = 1024  # two 512-byte NUL blocks end a tar
TAIL_KEEP = 64 << 10  # more than tarfile's read-ahead (one 10 KiB record and one header)
TEXT_TYPES = (".csv", ".tsv", ".json", ".jsonl", ".txt", ".log", ".md", ".yaml", ".yml", ".xml")
ARCHIVES = {".tar.gz": "gzip", ".tgz": "gzip", ".tar": "tar", ".zip": "zip", ".gz": "gzip"}  # longest suffix first
KINDS = ("private_hash", "grader_hash", "leaderboard_hash", "withheld_file", "private_lines", "benchmark",
         "not_inspected", "unreadable", "export_incomplete", "links_outside")
LIMITS = (
    "answer lines placed after a NUL byte inside a binary file (a file not named as a table or text) are not seen",
    "archives of other formats are not opened (.whl, .npz, .jar, zip-format checkpoints such as .pt or .pth, .xz, "
    ".bz2, .7z, .zst, tar without ustar magic): they are hashed and line-checked as ordinary files",
    "an archive inside an archive is not opened: it is reported as not inspected",
    "answers re-encoded (delimiter, quoting, number format, column order, an encoding such as UTF-16), split or "
    "altered, labels without their ids, or learned into model weights are not seen",
    "a line longer than LINE_CAP bytes is not compared",
    "the check reads the export it is given; that the export came from the named image is the exporter's to show",
)
PACKAGE = re.compile(r"(__editable__[._-])?mlebench([-_.].*)?")
COMPETITION = re.compile(r"[a-z0-9][a-z0-9-]*")
# zipfile raises RuntimeError for an encrypted member and NotImplementedError for an unknown compression
BROKEN = (OSError, EOFError, zlib.error, tarfile.TarError, zipfile.BadZipFile, RuntimeError, NotImplementedError)


class Refused(Exception):
    """An input the check cannot run on: an unpinned reference, a missing or empty input, a link in an input tree."""


def _sha(path):
    """SHA-256 hex of a file (str | Path), streamed."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _has_nul(path):
    """True when the file (str | Path) holds a NUL byte anywhere."""
    with open(path, "rb") as fh:
        return any(b"\x00" in chunk for chunk in iter(lambda: fh.read(CHUNK), b""))


def _digest(line):
    """The 16-byte BLAKE2b digest (bytes) under which a normalised line (bytes) is kept and compared."""
    return hashlib.blake2b(line, digest_size=16).digest()


def _every(base):
    """Which lines of a file named `base` (lower-case str) are compared: True, every line (a table or text type);
    None, decided by its first block (no suffix); False, the lines before its first NUL byte."""
    ext = os.path.splitext(base)[1]
    return True if ext in TEXT_TYPES else None if not ext else False


class _Lines:
    """The stripped non-blank lines (list[bytes]) of a stream fed in chunks; an empty chunk ends it.

    every: see _every; when False the text ends at the first NUL byte. skip_first drops the first line (a header).
    A line over LINE_CAP is dropped without being kept whole."""

    def __init__(self, every, skip_first=False):
        self.every, self.carry, self.long, self.done = every, b"", skip_first, False

    def feed(self, chunk):
        if self.done:
            return []
        if self.every is None:
            self.every = b"\x00" not in chunk[:FIRST_BLOCK]
        end = not chunk
        if not self.every and (nul := chunk.find(b"\x00")) >= 0:
            chunk, end, self.done = chunk[:nul], True, True
        parts = (self.carry + chunk).split(b"\n")
        self.carry = b"" if end else parts.pop()
        if self.long and parts:  # the end of a line to drop: the header, or one over LINE_CAP
            parts[0], self.long = b"", False
        if len(self.carry) > LINE_CAP:
            self.carry, self.long = b"", True
        return [line for part in parts if (line := part.strip())]


def _read(stream, on_line, lines, digest=None, keep=-1):
    """Read a binary stream to its end in CHUNK pieces, calling on_line(bytes) with the digest of every line `lines`
    (a _Lines) gives and updating `digest` (hashlib object | None) with every byte. Returns (head, kept): the first
    FIRST_BLOCK bytes, and the whole content (bytearray) when it is at most `keep` bytes, else None."""
    head, kept = None, bytearray() if keep >= 0 else None
    while True:
        chunk = stream.read(CHUNK)
        head = chunk[:FIRST_BLOCK] if head is None else head
        if digest:
            digest.update(chunk)
        if kept is not None:
            kept += chunk
            kept = kept if len(kept) <= keep else None
        for line in lines.feed(chunk):
            on_line(_digest(line))
        if not chunk:
            return head, kept


def _magic(head):
    """The archive format (str | None: "gzip", "zip", "tar") whose signature starts `head` (bytes)."""
    if head[:2] == b"\x1f\x8b":
        return "gzip"
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return "zip"
    return "tar" if head[257:262] == b"ustar" else None


def _family(base):
    """The ARCHIVES suffix (str | None) that `base` (lower-case str) ends with."""
    return next((suffix for suffix in ARCHIVES if base.endswith(suffix)), None)


class _Tail:
    """A read-only stream over `raw` that counts the bytes it gave (`total`) and keeps at least the last TAIL_KEEP."""

    def __init__(self, raw):
        self.raw, self.total, self.kept, self.size = raw, 0, collections.deque(), 0

    def read(self, size=-1):
        data = self.raw.read(size)
        self.total += len(data)
        self.kept.append(data)
        self.size += len(data)
        while self.size - len(self.kept[0]) >= TAIL_KEEP:
            self.size -= len(self.kept.popleft())
        return data

    def tail(self):
        return b"".join(self.kept)


def _ends(tf, src):
    """True when the tar `tf`, read in stream mode from `src` (a _Tail), ends with its end-of-archive marker: at
    least END_MARKER bytes after its last member, all NUL, to the end of the stream."""
    behind, tail = src.total - tf.offset, src.tail()
    if not 0 <= behind <= len(tail):
        return False
    rest = tail[len(tail) - behind:]
    size, clean = behind, not rest.strip(b"\x00")
    while chunk := src.read(CHUNK):
        size, clean = size + len(chunk), clean and not chunk.strip(b"\x00")
    return clean and size >= END_MARKER


class _Targets(NamedTuple):
    hashes: dict  # {sha256 hex: [(kind, source)]}
    public: set  # sha256 hex of every public file
    lines: dict  # {line digest: bitmask over `names`}: one small int per private-only line
    names: list  # private file relative paths, in bitmask order
    inputs: dict  # {"private" | "grader" | "leaderboard" | "public": "sha256:<hex>", "withheld": [...]}


def _tree(root):
    """[(posix relative path, Path, sha256 hex)] of every file under an input directory; a link or special file is
    refused."""
    found = []
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise Refused(f"{path}: not a plain file or directory in an input tree")
        if path.is_file():
            found.append((path.relative_to(root).as_posix(), path, _sha(path)))
    return found


def _tree_digest(entries):
    """"sha256:<hex>" over the sorted "<relative path>\\0<sha256>\\n" lines of _tree entries (wrap.digest's formula,
    without its bytecode-cache filter)."""
    text = "".join(f"{rel}\0{sha}\n" for rel, _, sha in sorted(entries))
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _private_lines(private, public):
    """({line digest: bitmask}, names) of the private-only lines, from _tree entries of the two directories."""
    lines, names = {}, [rel for rel, _, _ in private]
    for bit, (_, path, _) in enumerate(private):
        if _has_nul(path):  # a binary private file is withheld by hash only
            continue
        with open(path, "rb") as fh:
            _read(fh, lambda d, b=1 << bit: lines.__setitem__(d, lines.get(d, 0) | b), _Lines(True, skip_first=True))
    for rel, path, _ in public:
        with open(path, "rb") as fh:
            _read(fh, lambda d: lines.pop(d, None), _Lines(_every(rel.rsplit("/", 1)[-1].lower())))
    return lines, names


def targets(private, grader, leaderboard, public, withheld=()):
    """What the export is searched for (_Targets), from the input directories and the leaderboard file."""
    trees = {"private": _tree(private), "grader": _tree(grader), "public": _tree(public)}
    held = [_tree(root) for root in withheld]
    hashes = {}
    sources = [("private_hash", rel, sha) for rel, _, sha in trees["private"]]
    sources += [("grader_hash", rel, sha) for rel, _, sha in trees["grader"]]
    sources += [("withheld_file", f"{Path(root).name}/{rel}", sha) for root, tree in zip(withheld, held)
                for rel, _, sha in tree]
    board = _sha(leaderboard)
    sources.append(("leaderboard_hash", Path(leaderboard).name, board))
    for kind, source, sha in sources:  # a source equal to a public file is never reported: content() skips them
        hashes.setdefault(sha, []).append((kind, source))
    lines, names = _private_lines(trees["private"], trees["public"])
    inputs = {name: _tree_digest(tree) for name, tree in trees.items()}
    inputs |= {"leaderboard": "sha256:" + board, "withheld": [_tree_digest(tree) for tree in held]}
    return _Targets(hashes, {sha for _, _, sha in trees["public"]}, lines, names, inputs)


def _norm(name):
    """A tar or zip member name (str) as a relative posix path ('./etc/x' and '/etc/x' are 'etc/x')."""
    return "/".join(part for part in name.split("/") if part not in ("", "."))


def _leaves(rel, target):
    """True when a link at `rel` (export-relative str) with `target` (str) climbs above the export's root."""
    depth = 0 if target.startswith("/") else rel.count("/")
    for part in target.split("/"):
        depth += {"..": -1, ".": 0, "": 0}.get(part, 1)
        if depth < 0:
            return True
    return False


class _Scan:
    """The findings over one export, built one entry at a time from `found` (_Targets)."""

    def __init__(self, found, competition, cap):
        self.t, self.competition, self.cap = found, competition, cap
        self.findings = {kind: [] for kind in KINDS}
        self.checked, self.seen, self.benchmark = 0, {}, set()  # seen: {tar member path: files checked under it}

    def add(self, kind, path, **extra):
        self.findings[kind].append({"path": path, **extra})

    def name(self, rel, prefix=""):
        """(c) by name: record the first path component named for the benchmark or the competition."""
        parts = rel.split("/")
        for i, part in enumerate(parts):
            base = part.lower()
            family = _family(base)
            if (base[:-len(family)] if family else base) == self.competition or PACKAGE.fullmatch(base):
                self.benchmark.add(prefix + "/".join(parts[:i + 1]))
                return

    def link(self, path, rel, target):
        """A symbolic link at `path` (`rel` inside its tree) to `target` (str): recorded when it leaves the root."""
        if _leaves(rel, target):
            self.add("links_outside", path, target=target)

    def content(self, path, stream, depth=0):
        """(a), (b) and the archive rule for one regular file's bytes (binary stream), read once."""
        self.checked += 1
        base = path.rsplit("!", 1)[-1].rsplit("/", 1)[-1].lower()
        family, digest, found = None if depth else _family(base), hashlib.sha256(), set()
        wanted = self.t.lines
        head, kept = _read(stream, lambda d: found.add(d) if d in wanted else None, _Lines(_every(base)), digest,
                           self.cap if family else -1)
        sha = digest.hexdigest()
        if sha in self.t.public:
            return
        for kind, source in self.t.hashes.get(sha, ()):
            self.add(kind, path, source=source)
        self._lines(path, found)
        if depth and _magic(head):
            self.add("not_inspected", path, sha256=sha, reason="nested archive")
        elif family and _magic(head) == ARCHIVES[family]:
            self._archive(path, family, kept, sha)

    def _lines(self, path, found):
        counts = {}
        for line in found:
            for i, name in enumerate(self.t.names):
                if self.t.lines[line] >> i & 1:
                    counts[name] = counts.get(name, 0) + 1
        if counts:
            self.add("private_lines", path, lines=dict(sorted(counts.items())))

    def _archive(self, path, family, data, sha):
        if data is None:
            self.add("not_inspected", path, sha256=sha, reason="archive over the cap")
            return
        try:
            complete = self._members(path, family, bytes(data))
        except BROKEN as exc:
            self.add("unreadable", path, reason=type(exc).__name__)
            return
        if not complete:
            self.add("unreadable", path, reason="not read to its end-of-archive marker")

    def _members(self, path, family, data):
        """Check every member of an archive held in memory; True when it was read to its end."""
        prefix = path + "!"
        if family == ".zip":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    rel = _norm(info.filename)
                    self.name(rel, prefix)
                    if not info.is_dir():
                        with zf.open(info) as fh:
                            self.content(prefix + rel, fh, depth=1)
            return True
        if family == ".gz":
            rel = path.rsplit("/", 1)[-1][:-3]
            self.name(rel, prefix)
            self.content(prefix + rel, gzip.GzipFile(fileobj=io.BytesIO(data)), depth=1)
            return True
        raw = io.BytesIO(data) if family == ".tar" else gzip.GzipFile(fileobj=io.BytesIO(data))
        return self.tar_stream(raw, prefix, depth=1)

    def tar_stream(self, raw, prefix="", depth=0):
        """Check a plain tar read from the binary stream `raw`; True when every member was read and the tar ends with
        its end-of-archive marker. A tar that cannot be opened raises tarfile.ReadError."""
        src = _Tail(raw)
        with tarfile.open(fileobj=src, mode="r|") as tf:
            return self.tar(tf, prefix, depth) and _ends(tf, src)

    def tar(self, tf, prefix="", depth=0):
        """Every member of an open tar, in order; False when a member cannot be read (the stream is then lost)."""
        for member in tf:
            rel = _norm(member.name)
            path = prefix + rel
            self.name(rel, prefix)
            if not rel or member.isdir():
                continue
            if member.issym():
                self.link(path, rel, member.linkname)
            elif member.islnk():
                self._hard_link(path, prefix + _norm(member.linkname))
            elif not member.isreg():
                self.add("unreadable", path, reason="special file")
            elif not self._tar_file(tf, member, path, depth):
                return False
        return True

    def _hard_link(self, path, target):
        """A hard link's bytes are its target's: it gets the target's findings and count under its own path."""
        if target not in self.seen:
            self.add("unreadable", path, reason="hard link to a member not earlier in the tar")
            return
        self.checked += self.seen[target]
        for items in self.findings.values():
            items += [{**f, "path": path + f["path"][len(target):]} for f in items
                      if f["path"] == target or f["path"].startswith(target + "!")]
        self.benchmark |= {path + b[len(target):] for b in self.benchmark if b.startswith(target + "!")}

    def _tar_file(self, tf, member, path, depth):
        before = self.checked
        try:
            self.content(path, tf.extractfile(member), depth)
        except BROKEN as exc:
            self.add("unreadable", path, reason=type(exc).__name__)
            return False
        self.seen[path] = self.checked - before
        return True

    def directory(self, root):
        """Walk an export given as a directory (Path), never following a link."""
        errors = []
        for top, dirs, files in os.walk(root, onerror=errors.append):
            dirs.sort()
            for name in sorted(dirs + files):
                full = os.path.join(top, name)
                rel = Path(full).relative_to(root).as_posix()
                try:
                    self._dir_entry(full, rel)
                except OSError as exc:
                    self.add("unreadable", rel, reason=type(exc).__name__)
        for exc in errors:
            self.add("unreadable", Path(exc.filename).relative_to(root).as_posix(), reason=type(exc).__name__)

    def _dir_entry(self, full, rel):
        self.name(rel)
        mode = os.lstat(full).st_mode
        if stat.S_ISLNK(mode):
            self.link(rel, rel, os.readlink(full))
        elif stat.S_ISREG(mode):
            with open(full, "rb") as fh:
                self.content(rel, fh)
        elif not stat.S_ISDIR(mode):
            self.add("unreadable", rel, reason="special file")

    def export(self, export):
        """Scan the export: a directory, or a plain tar read as a stream and required to end properly."""
        if os.path.isdir(export):
            self.directory(Path(export))
            return
        try:
            with open(export, "rb") as raw:
                reason = None if self.tar_stream(raw) else "not read to its end-of-archive marker"
        except BROKEN as exc:
            reason = type(exc).__name__
        if reason:
            self.add("export_incomplete", str(export), reason=reason)


def _refuse_bad_inputs(competition, private, grader, leaderboard, public, withheld):
    if not COMPETITION.fullmatch(competition):
        raise Refused(f"{competition!r}: not a competition id")
    if not os.path.isdir(private) or not any(p.is_file() for p in Path(private).rglob("*")):
        raise Refused(f"{private}: the private directory is missing or holds no file")
    if not os.path.isfile(Path(grader) / "grade.py"):
        raise Refused(f"{grader}: the grading-code directory has no grade.py")
    if not os.path.isfile(leaderboard) or not os.path.getsize(leaderboard):
        raise Refused(f"{leaderboard}: the leaderboard file is missing or empty")
    for label, path in [("public", public)] + [("withheld", root) for root in withheld]:
        if not os.path.isdir(path):
            raise Refused(f"{path}: the {label} directory is missing")
    _refuse_another_competition(competition, grader)


def _refuse_another_competition(competition, grader):
    """Refused when the grading-code directory's config.yaml names another competition id."""
    config = Path(grader) / "config.yaml"
    named = config.is_file() and re.search(r"(?m)^id:\s*(\S+)", config.read_text())
    if named and named.group(1) != competition:
        raise Refused(f"{config} names {named.group(1)!r}, not {competition!r}")


def _exemptions(path):
    """({sha256: reason}, "sha256:<hex>" | None) from an exemption file (str | None): a JSON list of
    {"sha256": <64 hex>, "reason": <non-empty str>}."""
    if path is None:
        return {}, None
    entries = json.loads(Path(path).read_text())
    ok = isinstance(entries, list) and all(
        isinstance(e, dict) and re.fullmatch(r"[0-9a-f]{64}", str(e.get("sha256"))) and str(e.get("reason", "")).strip()
        for e in entries)
    if not ok:
        raise Refused(f"{path}: not a JSON list of {{sha256, reason}}")
    return {e["sha256"]: e["reason"] for e in entries}, "sha256:" + _sha(path)


def _settle(scan, exemptions):
    """(findings: {kind: sorted list}, exempted: list) of a finished _Scan, with the exempted "not inspected"
    findings ({sha256: reason}) moved out of the findings."""
    findings = scan.findings | {"benchmark": [{"path": p} for p in sorted(scan.benchmark)]}
    findings = {kind: sorted(items, key=lambda f: json.dumps(f, sort_keys=True)) for kind, items in findings.items()}
    exempted = [f | {"reason": exemptions[f["sha256"]], "finding": f["reason"]} for f in findings["not_inspected"]
                if f["sha256"] in exemptions]
    findings["not_inspected"] = [f for f in findings["not_inspected"] if f["sha256"] not in exemptions]
    return findings, exempted


def check(export, *, competition, private, grader, leaderboard, public, image_ref, withheld=(), exempt=None,
          cap=ARCHIVE_CAP):
    """The result (dict) for one image; see the module docstring. Raises Refused before reading the export."""
    if not PINNED.fullmatch(image_ref):
        raise Refused(f"{image_ref!r}: the image reference is not pinned by digest (<name>@sha256:<64 hex>)")
    _refuse_bad_inputs(competition, private, grader, leaderboard, public, withheld)
    if not os.path.exists(export):
        raise Refused(f"{export}: the export is missing")
    exemptions, exempt_sha = _exemptions(exempt)
    found = targets(private, grader, leaderboard, public, withheld)
    scan = _Scan(found, competition, cap)
    scan.export(export)
    findings, exempted = _settle(scan, exemptions)
    used = {f["sha256"] for f in exempted}
    passed = scan.checked > 0 and not any(findings.values())
    return {"image": image_ref, "competition": competition, "verdict": "pass" if passed else "fail",
            "files_checked": scan.checked, "inputs": found.inputs, "check_sha256": "sha256:" + _sha(__file__),
            "exemptions_sha256": exempt_sha, "caps": {"archive_bytes": cap, "line_bytes": LINE_CAP, "archive_depth": 1},
            "limits": list(LIMITS), "findings": findings, "exempted": exempted,
            "exemptions_unused": sorted(sha for sha in exemptions if sha not in used)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for flag in ("--image-ref", "--competition", "--export", "--private", "--grader", "--leaderboard", "--public",
                 "--out"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--withheld", action="append", default=[])
    parser.add_argument("--exempt")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.unlink(missing_ok=True)
    try:
        result = check(args.export, competition=args.competition, private=args.private, grader=args.grader,
                       leaderboard=args.leaderboard, public=args.public, image_ref=args.image_ref,
                       withheld=args.withheld, exempt=args.exempt)
    except Refused as exc:
        print("refused:", exc, file=sys.stderr)
        return 2
    temporary = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    os.replace(temporary, out)
    print(result["verdict"], args.image_ref)
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
