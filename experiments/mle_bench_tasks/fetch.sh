#!/usr/bin/env bash
# Download and prepare MLE-bench competitions with the owner's Kaggle token (family plan M10; Task 10a). The one
# command of this line that reads the token, and it never reads it itself: it gives the benchmark's tool the
# token's directory and nothing else.
#
#   KAGGLE_CONFIG_DIR=<token dir> fetch.sh <slug>...
#
# For each slug it runs `mlebench prepare -c <slug> --data-dir ~/mle-cache/prepared` (the tool found on PATH) and
# prints one fixed line, `<slug>: done`, `<slug>: rules not accepted or download failed` or `<slug>: no room`
# (the lower free space of the data directory and the token directory under the ladder's 20 GB floor; the tool is
# not started). Exit 0 when every slug is done, 1 otherwise.
#
# The tool runs with KAGGLE_USERNAME and KAGGLE_KEY unset (so the client reads kaggle.json from KAGGLE_CONFIG_DIR),
# in a new session with standard input from /dev/null (no terminal to read or write, so the rules question gets
# end of file), with its working and temporary directories inside the token directory, no core dumps, and its
# standard output and error in <token dir>/fetch-<slug>.log, mode 600. The pane sees only the fixed lines. INT, TERM
# or HUP stops the tool with fetch.sh (exit 130).
#
# Refuses (exit 2, one line on stderr, nothing started): KAGGLE_CONFIG_DIR unset, empty or relative; a token
# directory that is not a directory of mode 700 (a link included) or lies inside a git repository (or git cannot
# tell); a kaggle.json that is not a regular file of mode 600 (a link included); no slug, or a name that is not a
# slug.
set -u
umask 077
ulimit -c 0

refuse() { echo "fetch.sh: $1" >&2; exit 2; }

dir=${KAGGLE_CONFIG_DIR:-}
dir=${dir%/}
[[ $dir == /* ]] || refuse "KAGGLE_CONFIG_DIR is not set to an absolute path"
[ "$(stat -c '%a %F' -- "$dir" 2>/dev/null)" = "700 directory" ] || refuse "the token directory is not a directory of mode 700"
[ "$(stat -c '%a %F' -- "$dir/kaggle.json" 2>/dev/null)" = "600 regular file" ] || refuse "kaggle.json is not a regular file of mode 600"
git -C "$dir" rev-parse >/dev/null 2>&1; [ $? -eq 128 ] || refuse "the token directory is inside a git repository, or git cannot tell"
[ $# -gt 0 ] || refuse "no competition named"
for slug; do
  [[ $slug =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || refuse "a name that is not a competition slug"
done

unset KAGGLE_USERNAME KAGGLE_KEY
export KAGGLE_CONFIG_DIR=$dir TMPDIR=$dir/tmp
data=$HOME/mle-cache/prepared
mkdir -p "$data" "$TMPDIR" || refuse "cannot create the data or temporary directory"
cd "$dir" || refuse "cannot enter the token directory"

floor=20000000000  # the ladder's free-disk floor, 20 GB (family plan M9)
pid=
trap '[ -n "$pid" ] && kill -TERM -- "-$pid" 2>/dev/null; exit 130' INT TERM HUP
status=0
for slug; do
  free=$(df --output=avail -B1 "$data" "$dir" | tail -n +2 | sort -n | head -n 1)
  if [ "${free:-0}" -lt "$floor" ]; then
    echo "$slug: no room"; status=1; continue
  fi
  # setsid: the tool leads its own session and process group, with no controlling terminal; $! is its pid.
  setsid mlebench prepare -c "$slug" --data-dir "$data" </dev/null >"$dir/fetch-$slug.log" 2>&1 &
  pid=$!
  if wait "$pid"; then echo "$slug: done"; else echo "$slug: rules not accepted or download failed"; status=1; fi
  pid=
done
exit "$status"
