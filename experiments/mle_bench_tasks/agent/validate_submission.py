"""The agent-side format check (family plan, decision M3): it replaces the benchmark's format server, which grades a
submission against the answers. This one compares a submission with the public sample submission only, so it can
sit in the agent's image, where no answer is: the same columns in the same order, the same ids (the sample's first
column) as often as the sample has them, no empty value. A submission it accepts can still be refused by the grader.

Usage: python /home/validate_submission.py <submission.csv> [<sample submission>]
  The sample defaults to /home/data/sample_submission.csv, the public copy in the agent's image.
Exit 0 and one line when the format matches; exit 1 and one line per problem, each "<code>: <detail>"
(no-file, unreadable, empty-file, missing-column, extra-column, column-order, ragged-row, missing-id, extra-id,
duplicate-id, empty-value); exit 2 on a usage error or an unreadable sample, on standard error.
Standard library only; it opens the two files it is given and nothing else.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

SAMPLE = Path("/home/data/sample_submission.csv")
SHOWN = 5  # examples printed per problem


def read(path):
    """(header, rows) of a CSV file; header is None for an empty file."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        return next(reader, None), list(reader)


def _some(items):
    items = list(items)
    more = f" and {len(items) - SHOWN} more" if len(items) > SHOWN else ""
    return ", ".join(map(str, items[:SHOWN])) + more


def column_problems(expected, header):
    missing = [c for c in expected if c not in header]
    extra = [c for c in header if c not in expected]
    lines = [f"missing-column: {_some(missing)}"] if missing else []
    lines += [f"extra-column: {_some(extra)}"] if extra else []
    if not lines and header != expected:
        lines.append(f"column-order: expected {', '.join(expected)}; got {', '.join(header)}")
    return lines


def id_problems(expected, got):
    """Ids compared as counted multisets, so a sample with repeated ids is matched as it is."""
    missing = [i for i in expected if i not in got]
    extra = [i for i in got if i not in expected]
    duplicated = [i for i in got if i in expected and got[i] > expected[i]]
    found = (("missing-id", missing), ("extra-id", extra), ("duplicate-id", duplicated))
    return [f"{code}: {len(ids)} ({_some(ids)})" for code, ids in found if ids]


def row_problems(width, rows):
    """Rows whose field count differs from the header's, and empty values; line numbers count the header as 1."""
    ragged = [n for n, row in enumerate(rows, 2) if len(row) != width]
    empty = [f"line {n} column {k + 1}" for n, row in enumerate(rows, 2) for k, v in enumerate(row) if not v.strip()]
    lines = [f"ragged-row: {len(ragged)} rows without {width} fields (lines {_some(ragged)})"] if ragged else []
    return lines + ([f"empty-value: {len(empty)} ({_some(empty)})"] if empty else [])


def problems(submission, sample_header, sample_rows):
    if not submission.is_file():
        return [f"no-file: {submission}"]
    try:
        header, rows = read(submission)
    except (OSError, UnicodeDecodeError, csv.Error) as e:  # the agent's file, not the check, is at fault
        return [f"unreadable: {e}"]
    if header is None:
        return ["empty-file: no header and no rows"]
    lines = column_problems(sample_header, header) + row_problems(len(header), rows)
    if sample_header[0] in header:
        k = header.index(sample_header[0])
        got = Counter(row[k] for row in rows if len(row) > k)
        lines += id_problems(Counter(row[0] for row in sample_rows), got)
    return lines


def main(argv):
    if len(argv) not in (2, 3):
        print(f"usage: {argv[0]} <submission.csv> [<sample submission>]", file=sys.stderr)
        return 2
    sample = Path(argv[2]) if len(argv) == 3 else SAMPLE
    try:
        sample_header, sample_rows = read(sample)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        print(f"cannot read the sample submission {sample}: {e}", file=sys.stderr)
        return 2
    if not sample_header:
        print(f"the sample submission {sample} is empty", file=sys.stderr)
        return 2
    found = problems(Path(argv[1]), sample_header, sample_rows)
    print("\n".join(found) if found else f"ok: {len(sample_rows)} rows, columns {', '.join(sample_header)}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
