#!/bin/sh
# line_count.sh FILE: print the number of lines in FILE.
# Each call is logged to line_count.calls beside this script.
echo "$1" >> "$(dirname "$0")/line_count.calls"
wc -l < "$1" | tr -d ' '
