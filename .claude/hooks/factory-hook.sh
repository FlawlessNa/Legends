#!/usr/bin/env bash
# Launch `factory hook <event>` from wherever the harness happens to run us.
#
# This exists because two assumptions turned out to be false:
#
#   1. `factory` is on PATH.           It is a console script in .venv, and the
#                                      hook shell has no venv active (#199).
#   2. The venv sits in the repo root. A git worktree has no .venv of its own,
#                                      and `factory claim` gives every ticket a
#                                      worktree -- so the hook would be dead in
#                                      precisely the environment it is for.
#
# So: resolve an interpreter, and if none can be found, SAY SO. Hooks fail open
# -- Claude Code treats a non-zero exit as non-blocking -- which means a broken
# hook and a hook that allowed the action look identical. Silence is the bug.
set -uo pipefail

event="${1:?usage: factory-hook.sh <event>}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# A linked worktree's .git is a file: "gitdir: <path>/.git/worktrees/<name>".
# The main checkout is three levels up from there, and that is where .venv lives.
main_repo() {
    local git_path="$here/.git"
    [[ -f "$git_path" ]] || return 1
    local gitdir
    gitdir="$(sed -n 's/^gitdir: //p' "$git_path")" || return 1
    [[ -n "$gitdir" ]] || return 1
    ( cd "$gitdir/../../.." 2>/dev/null && pwd ) || return 1
}

# A person checking the gates by hand (SKILL.md) has a terminal on stdin, and
# the hook reads stdin to the end. Under Git Bash's mintty, python.exe sees that
# terminal as a pipe and would wait for an end of input nobody types.
[[ -t 0 ]] && exec </dev/null

for root in "$here" "$(main_repo || true)"; do
    [[ -n "$root" ]] || continue
    for python in "$root/.venv/Scripts/python.exe" "$root/.venv/bin/python"; do
        if [[ -x "$python" ]]; then
            # -I, isolated mode, keeps the current directory OFF the import
            # path. The hook runs in the session's directory, and plain
            # `-m factory` imported a `factory/` package found there first --
            # so a worktree editing the gates was judged by its own unfinished
            # gates, and could switch them off by "fixing" them (#216). With
            # -I, `factory` resolves only through the venv's installed
            # packages: the editable install of the main checkout.
            exec "$python" -I -m factory hook "$event"
        fi
    done
done

echo "factory hook unreachable: no .venv interpreter found from $here." >&2
echo "  The factory's gates are NOT running. Fix the venv or see #199." >&2
exit 0
