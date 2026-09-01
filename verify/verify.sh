#!/usr/bin/env bash
# Recompute every number this repo publishes, in a language that did not
# produce it, and require agreement.
#
# reports/audit.json, the figures and the README all come from one pandas
# implementation in src/auditor. If disparity() had divided by the wrong
# denominator, or group_metrics() had swapped FPR and FNR, nothing would have
# caught it: the tables, the charts and the prose would all be wrong in the
# same direction, because they all read the same output.
#
# The checks below start from the rawest thing the repo can commit. IEEE-CIS is
# not redistributable, so row-level predictions are gitignored and the segment
# tables are the raw material here. Every rate in them is a ratio of whole rows,
# so the integer confusion matrix behind each one can be recovered exactly, and
# everything the repo says follows from those integers.
#
# Each language is skipped with a clear message if its toolchain is absent, so
# this runs on a laptop with only some of them installed. CI has all of them.
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

pass=0 fail=0 skip=0

run () {
    local name="$1" tool="$2"; shift 2
    printf '\n=== %s ===\n' "$name"
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'skipped: %s is not installed\n' "$tool"
        skip=$((skip + 1)); return
    fi
    if "$@"; then pass=$((pass + 1)); else fail=$((fail + 1)); printf 'FAILED: %s\n' "$name"; fi
}

# SQL prints a line per disagreement and has no exit code of its own, so the
# output is the verdict. A run with no FAIL lines and a final summary passes.
check_sql () {
    local out
    out=$(sqlite3 -init verify/summary.sql :memory: "" 2>&1) || { echo "$out"; return 1; }
    echo "$out"
    case "$out" in *FAIL*) return 1;; esac
    case "$out" in *"SQL: "*) return 0;; *) echo "SQL produced no summary line"; return 1;; esac
}

# The C kernel prints a line per group, which is too much to read on a clean
# run. Keep the failures and the summary, drop the inventory.
check_c () {
    local bin="${TMPDIR:-/tmp}/aifa_kernel" out rc
    cc -std=c99 -O2 -Wall -Wextra -Wpedantic -Werror -o "$bin" verify/kernel.c -lm || return 1
    out=$("$bin" "$root"); rc=$?
    printf '%s\n' "$out" | grep -E 'FAIL|^C:|^   ' || true
    return $rc
}

check_go () { ( cd verify/gocheck && go run . -root "$root" ); }

check_rust () { ( cd verify/resample && cargo run --release --quiet -- "$root" ); }

run "SQL, audit.json from the segment tables"  sqlite3 check_sql
run "C, confusion matrix kernel"               cc      check_c
run "Java, the impossibility arithmetic"       java    java verify/Impossibility.java "$root"
run "Go, structural validation"                go      check_go
run "R, exact intervals and tests"             Rscript Rscript verify/inference.R "$root"
run "Rust, resampling the whole audit"         cargo   check_rust
run "Node, the README against the results"     node    node verify/readme.js "$root"

printf '\n%s\n' "----------------------------------------"
printf '%d passed, %d failed, %d skipped\n' "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ] || exit 1
[ "$pass" -gt 0 ] || { echo "nothing ran"; exit 1; }
