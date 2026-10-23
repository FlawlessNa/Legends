---
ticket: 217
stage: plan
accepted_by: nassim
accepted_at: 2026-10-22
---

# Intent: no file serialises the roadmap, no branch is special, and the policy page is true

## Problem statement

Four small defects (`docs/factory/design.md` §3, d2 and d5):

1. **`POLICY.protected_paths` lists nine `factory/` modules one by one.** Every
   new module edits `merge.py`, so every ticket that adds one collides with
   every other.
2. **`factory next <n>` and `factory model <n>` read the chain in the current
   directory** (cli.py:98, 138). From the primary checkout an in-flight ticket
   reads as `plan`.
3. **`merge-policy.md` is wrong in both directions, and its test passes.** It
   says `.factory/**` is not allowlisted, but it is. It lists `.claude/**` as
   allowlisted, but it is not. It also says the workflow is not on `dev`, which
   stopped being true on 2026-10-22.
4. **`movements-improvements` is hard-coded as the only branch CI may merge
   into** (merge.py:63). It became the base by accident. The maintainer: "I
   don't want to have special rules for movements improvement, it's just a
   branch." `dev` is the base.

Also from the ticket: `core.autocrlf=true` rewrites chain files on checkout, so a
`.gitattributes` makes `.factory/**` LF in the working copy.

## Proposed outcome

- One `factory/**` entry protects the package.
- `next` and `model` answer from the ticket's own worktree.
- The policy page and `POLICY` agree, and a test checks both directions.
- The base CI may merge into is the repository's default branch, read from
  GitHub. No branch name appears in code.

## Affected users and systems

- `factory/merge.py`, `factory/cli.py` and a new `factory/worktrees.py`.
- `docs/factory/merge-policy.md` and `docs/factory/design.md` (R11, d6, and
  §10's maintainer list).
- `tests/test_factory/test_merge.py` and `tests/test_factory/test_cli.py`.
- `.gitattributes`.

## Constraints

Every file here except `.gitattributes` is either protected or outside the
allowlist, so this PR is a human merge.

## Open questions

Acceptance is inferred. The maintainer accepted the roadmap and asked for work
to continue ("keep working on the next tickets", 2026-10-22). The base-branch
part is their own instruction.
