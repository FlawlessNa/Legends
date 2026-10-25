#!/usr/bin/env bash
# Run a tool from the project venv, from a normal checkout or a linked worktree.
#
# `.pre-commit-config.yaml` used to hardcode `./.venv/Scripts/ruff.exe`, which
# works in the main checkout and fails in every linked worktree, which has no
# .venv of its own (#199).
#
# Unlike the hook launcher, this one EXITS NON-ZERO when it cannot find a venv.
# A commit that silently skips ruff and pyright is worse than one that stops.
set -uo pipefail

tool="${1:?usage: venv-tool.sh <tool> [args...]}"
shift
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# A linked worktree's .git is a file: "gitdir: <path>/.git/worktrees/<name>".
main_repo() {
    local git_path="$here/.git"
    [[ -f "$git_path" ]] || return 1
    local gitdir
    gitdir="$(sed -n 's/^gitdir: //p' "$git_path")" || return 1
    [[ -n "$gitdir" ]] || return 1
    ( cd "$gitdir/../../.." 2>/dev/null && pwd ) || return 1
}

for root in "$here" "$(main_repo || true)"; do
    [[ -n "$root" ]] || continue
    for candidate in "$root/.venv/Scripts/$tool.exe" "$root/.venv/bin/$tool"; do
        if [[ -x "$candidate" ]]; then
            # pyproject sets `venvPath = "."`, which resolves against the cwd --
            # so in a worktree pyright finds no venv and reports every import as
            # unresolved. It is the same assumption as the rest of this script,
            # one layer down, so the fix belongs here rather than in a static
            # config that cannot know where it is running.
            if [[ "$tool" == "pyright" ]]; then
                exec "$candidate" --venvpath "$root" "$@"
            fi
            exec "$candidate" "$@"
        fi
    done
done

echo "venv-tool: no .venv found for '$tool' from $here" >&2
echo "  Install with: pip install -r requirements-dev.txt" >&2
exit 1
