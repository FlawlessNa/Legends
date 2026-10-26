# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Epics and sub-issues

An epic holds a topic's intent and spec, and its tickets are linked to it as
GitHub sub-issues (`topics.md`).

- **Link a ticket to its epic:**
  `gh api --method POST repos/FlawlessNa/Legends/issues/<epic>/sub_issues -F sub_issue_id=<id>`,
  where `<id>` is the ticket's database id
  (`gh api repos/FlawlessNa/Legends/issues/<n> -q .id`), not its number.
- **List an epic's tickets:** `gh api repos/FlawlessNa/Legends/issues/<epic>/sub_issues -q '.[] | "\(.number) \(.state) \(.title)"'`.
- **A ticket's first line** is `Part of #<epic>`, plus `Blocked by #<n>` when it
  depends on another ticket.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.
