---
ticket: 139
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "every chain committed under .factory/ parses without error, every plan.md radius in them passes radius_errors, every one reads as version 1, and routing.resolve answers each without raising"
---

# Spec review: chain v2

**Verdict: `changes-requested`.** I reviewed `spec.md` at `09bb586` against the
intent, issue #139 as it reads on GitHub today, `docs/factory/design.md` §5
(`chain.py`) and §6, `docs/factory/artifacts.md`, `factory/chain.py` and its
callers (`hooks.py` `session_report` and `_chain_lines`, `routing.py`, `cli.py`,
`models.py`), and every committed chain under `.factory/`.

The shape is right. A sibling `front_matter_lists`, an untouched
`front_matter`, `blob` built on `rev-parse`, and a radius grammar that makes
overlap a prefix comparison are all sound. Keeping `ARTIFACTS` at six names is
also sound (finding 6).

One defect is real. The Shape's mapping rule would make **this spec's own
`criteria` unreadable**, and criterion 10, the guard over real chains, would
not notice. Fix findings 1 and 2. The others are smaller decidability and
completeness gaps, and each has a one-line fix.

## 1. "An item containing `: ` is a mapping" misreads prose criteria (major)

The Shape says: "An item containing `: ` is a mapping, and makes the whole key
unreadable rather than half-read."

**Evidence.** I scanned every front-matter block under `.factory/` with that rule:

- `.factory/139/spec.md`: 3 of 11 criteria contain `: `. They are criterion 2
  (`"key: []"`), criterion 3 (`"- id: x"`) and criterion 7 (`"chain: 2"`). So
  this spec's whole `criteria` key would be absent.
- `.factory/197/spec.md:11`: "no real stop is weakened: a measured constant, a
  running client, ...". So 197's `criteria` would be absent too.

No real list item is a genuine mapping. The only contracted list of mappings is
`plan.md`'s `tasks`, and every real plan writes `tasks: null`.

The consequence is not cosmetic. Design §9 makes `spec submit` refuse a spec
with "no `criteria`", so a spec whose prose happens to contain a colon would be
refused for having no criteria at all.

Refusing mapping items is right, because the module's principle forbids
half-reading. The detector is what is wrong.

**Fix.** An item is a mapping only when its text after `- ` matches the
module's own `_SCALAR`: an identifier, then `:`, then whitespace or end of
line. `- id: x` and `- id:` are then mappings, while `an inline empty list
"key: []"` and `no real stop is weakened: ...` stay scalars. Write that
definition into criterion 3. Add a case for prose containing `: `.

## 2. Criterion 10 is vacuous in one clause and a time bomb in another (major)

> "every chain committed under .factory/ parses without error, every plan.md
> radius in them passes radius_errors, every one reads as version 1, and
> routing.resolve answers each without raising"

**"Parses without error" cannot fail.**
- `front_matter` returns `{}` on `OSError` and on a missing block.
- `front_matter_lists` is specified to drop an unreadable key rather than raise.

So the clause passes whether lists are read or not. Under finding 1's rule it
passes with 139's and 197's criteria silently gone. The issue asked for this
check ("Every committed chain in `.factory/` parses without error") to guard
the real list shapes, and as written it guards nothing.

**"Every one reads as version 1" breaks by design.** The first chain committed
with `chain: 2` makes the test fail. #222's `feature new` writes it, and #223
commits one. A test that encodes "no v2 chain exists yet" is not a regression
guard.

**Fix.**
- Replace "parses without error" with content assertions:
  - every committed `spec.md` has `criteria` as a non-empty tuple whose length
    equals the number of `- ` lines under `criteria:`;
  - every committed `plan.md` has a non-empty `radius`, and `radius_errors` on
    it is empty.
- Pin the version clause to the tickets committed at `9654223`: 140, 153, 162,
  179, 189, 191, 194, 197, 199, 202, 206, 209 and 214. Alternatively, assert
  version 1 exactly for chains whose `intent.md` has no `chain` key.

I ran `routing.resolve` on all 14 chains at `09bb586`. None raised. 153, 179
and 191 answer `blocked_by` "the chain is inconsistent: work exists downstream
of a gap", so "answers each" must accept a blocked answer. Say so, or say "each
answer equals the one at `9654223`". The second is the stronger guard for the
intent's "keep their answers" constraint.

## 3. `version` silently downgrades unknown values to 1 (moderate)

> "Chain.version is 2 exactly when intent.md carries "chain: 2", and 1
> otherwise, including when intent.md is absent"

Under this criterion, `chain: 3`, `chain: two`, `chain: "2"` and
`chain: 2  # v2` all read as **1**. `front_matter` does not strip trailing
comments; `models.py`'s record line `model: <alias>  # tier=...` shows the
repo writes them. So all four would route on the v1 table.

That contradicts the factory's own rule in `artifacts.md` "Verdicts" and
`routing.verdict_of`: "An unrecognised value is an error, never guessed." For
#218, guessing v1 is the dangerous direction, because v1 rows let a hand-run
chain through without `acceptance.md` or `proof.md`.

**Fix.** Define the spellings:
- An absent key is 1.
- `2`, once surrounding quotes are stripped as `verdict_of` strips them, is 2.
- `1` is 1.
- Anything else raises a named error, for example `MalformedChain`, in the
  manner of `MalformedVerdict`.

Add one test per branch. If comments should be tolerated, say so explicitly.

## 4. `blob`: testable here, but the criterion leaves the test free to be vacuous (moderate)

> "blob(repo_root, commit, relpath) returns git's blob id ... or None when it
> does not exist there, and returns the same id for content checked out with
> CRLF and committed with LF"

**Testable on this machine.** `core.autocrlf=true` here comes from the system
gitconfig. I checked it in a scratch repo with local `core.autocrlf=true`:

- A file was committed as `a\nb\n`, deleted, and checked out again. On disk it
  reads `a \r \n b \r \n`.
- `git rev-parse HEAD:d/f.md` gives `422c2b7...`, the id of the LF content.
- A byte hash of the working file (`hash-object --no-filters`) gives `c30dea8...`.

So the property holds, and a test can show it.

**Gaps that let two honest implementations differ:**

- **"The same id" has no comparand.** `rev-parse` never reads the working tree,
  so a test that only calls `blob` twice proves nothing. The criterion should
  require the test to:
  - set `core.autocrlf=true` in the temporary repo's own config, not rely on
    this machine's system config, since `merge-policy.yml` runs on
    `ubuntu-latest`;
  - assert the checked-out bytes contain `\r\n`, so the test is not vacuous;
  - assert `blob` equals the id of the LF bytes (`sha1(b"blob %d\0" % n + lf)`),
    and differs from the id of the working bytes.
- **A directory returns a tree id, not None.** `git rev-parse HEAD:d` printed
  the tree `2f53f43...` with exit 0. Specify `rev-parse --verify --quiet
  <commit>:<relpath>^{blob}`, which printed nothing with exit 1. Then add
  "a directory path returns None" to the criterion.
- **On failure, plain `rev-parse` echoes its argument to stdout.** `git
  rev-parse HEAD:nope` printed `HEAD:nope` with exit 128. An implementation
  that reads stdout without checking the exit code returns that string as an
  id. `--verify --quiet` and an exit-code check close this.
- **The relpath form.** Backslashes fail (`HEAD:d\f.md`: "exists on disk, but
  not in 'HEAD'"), and `./` is resolved relative to the cwd. State that
  `relpath` is POSIX and relative to the repo root, and that git runs with
  `cwd=repo_root`.
- **Design §4 rule 7.** "Every loop git call runs with `-c core.hooksPath=<empty>
  -c core.fsmonitor=false`." `blob` is a loop git call. Pass those flags, or
  record why `rev-parse` is exempt. The test's own `git init`/`commit` also
  needs `user.name`/`user.email` and an empty `core.hooksPath`. It would be the
  first test in `tests/` to create a git repo.

## 5. The radius criterion dropped the issue's message requirement, and leaves edge forms open (moderate)

> "radius_errors(entries) accepts a relative POSIX file path or "dir/**" with no
> other glob characters, and names each entry it rejects"

**Coverage.** The issue's acceptance reads: "A radius entry like `factory/*.py`
is rejected with a message naming the allowed forms." The criterion keeps
"names each entry" and drops "naming the allowed forms".

**Strictness against real plans: not too strict.** Every entry in the nine
committed `plan.md` radii is either a file path or `dir/**`. That includes
`.claude/skills/factory/**`, `.claude/hooks/**`, `.factory/140/**`,
`.gitignore`, `.github/workflows/merge-policy.yml` and
`.pre-commit-config.yaml`. Each passes, provided "no `..` segment" is read as
a segment equal to `..`, not a segment starting with `.`. Say that in the
criterion, because a dot-leading rejection would refuse every plan's
`.factory/<n>/**`.

**Undefined forms**, where implementations will differ:
- `C:/x`, which `PurePosixPath` does not call absolute;
- `/x` and backslashes;
- a trailing `/`, `./`, `a//b` and the empty string;
- a bare `**`;
- `**` mid-path (`a/**/b`) or as a suffix without a slash (`a**`).

**Fix.**
- Add "and each message names the allowed forms (a file path, or `dir/**`)".
- List the rejected cases above, or define the grammar positively. For
  example: non-empty `/`-separated segments, none empty, none `.` or `..`,
  none containing `*?[]\:`, and an optional single final `/**`.
- Add `.claude/skills/factory/**` and `.factory/139/**` to the accept cases.

## 6. `ARTIFACTS` stays at six: sound, but it overrides the issue silently (minor)

**Sound.**
- `_chain_lines` (hooks.py:280) prints one line per `ARTIFACTS` name, with
  `MISSING` for an absent one. Growing it would print four `MISSING` lines on
  every v1 chain, which the intent's "No behaviour of any existing caller
  changes" forbids.
- `routing` reads `present` only through explicit names (`_DOWNSTREAM`, the
  `has_*` properties, `"intent.md"`). A larger `present` changes no route.
- Nothing outside `chain.py` constructs `Chain`, so the new fields break no caller.

**Not recorded.** The issue says "`ARTIFACTS` grows to match", and the spec
does the opposite. AGENTS.md: "Contradicting one is allowed; doing it silently
is not." It is argued in the Shape but missing from "Decisions I made".

**Gaps.**
- `run.md` is in design §6. Either track it in `LOOP_ARTIFACTS` or say why not.
- Criterion 6 says "tracked separately" without naming the tuple. Name
  `LOOP_ARTIFACTS` and its four (or five) members.
- State that `present` includes them.
- Note for #218 that a v2 session report will not list the v2 files.

## 7. `artifacts.md` scope misses what its own Supersedes note assigns to #139 (minor)

> "docs/factory/artifacts.md carries a contract for acceptance.md, proof.md,
> answers.md and park.md, and the chain field of intent.md"

`artifacts.md`'s Supersedes note reads: "gains `acceptance.md`, `proof.md`,
`answers.md`, `park.md`, **`run.md`** and `intent.md: chain: 2`, #139." The
criterion omits `run.md`.

Two contracts this ticket changes are also not listed:
- **`plan.md` → `radius`** is typed "list of globs". After this ticket, globs
  other than `dir/**` are a validation error. The contract parsers implement
  must say so.
- **The list grammar itself.** Authors need to know that a `- word: ...` item
  makes the list unreadable, and that quotes are not removed (finding 8). The
  natural place is under `spec.md` → `criteria`.

**Fix.** Add `run.md`, the `radius` grammar and the list grammar to criterion
11. Also say that the #139 line comes out of the Supersedes note.

## 8. Smaller decidability gaps in criteria 1, 4 and 5 (minor)

- **Criterion 1, the issue's "list next to a nested block".** It is in the
  issue's acceptance but not in any criterion. Every real `plan.md` puts
  `radius:` above a `proof:` block. Add: "a list followed by a nested block
  reads the list, and leaves the block's `proof.*` keys in `front_matter`
  unchanged". Also say what a deeper list does, such as
  `proof:\n  steps:\n    - a`. It should neither join `proof` nor make it
  unreadable.
- **Criterion 1, quotes.** `.factory/153/spec.md:13` writes an item wholly in
  double quotes. "Stripped of surrounding whitespace" implies the quotes are
  kept. That is decidable, but the Decisions section states "no quote
  handling" only for flow lists. Say it for block items too, or strip one
  matching pair as `verdict_of` does.
- **Criterion 4, "its answers on every existing input are unchanged".** This
  ranges over infinitely many inputs, so no test can decide it. Make it "the
  existing suite passes unmodified, and `front_matter` returns the same dict as
  at `9654223` for every committed `.factory/*/*.md`". The Shape already says
  the function is untouched. Only its docstring and the module docstring
  ("Lists stay unread", "Only scalar front-matter is understood") should
  change.
- **Criterion 5, absence.** It does not say what `criteria`/`radius` return
  when the file is absent, the key is absent, or the key is unreadable.
  `()` for all three is defensible. But `spec submit` (design §9) then cannot
  tell `criteria: []` from an unreadable list, and its message will mislead.
  Pick (`()` or `None`) and state it.
- **Criterion 5, naming.** `Chain.proof` (from `proof.md`) will sit beside
  `has_proof`, which reads `plan.md`'s `proof.suite`. Say in the criterion that
  `has_proof` keeps reading `plan.md`, so no Builder "fixes" it to read the
  new field before #145.

## What holds

- **Scope.** No routing change, no hook calls `blob`, and no new dependency.
  This matches design §5's `chain.py` row and leaves the v2 routing table to
  #218.
- **Flow lists.** `docs_cleared: []` is the only flow list in the tree, at
  140, 162, 206, 209 and 214. Splitting on commas without quote handling is
  enough for it.
- **The `version` source.** `intent.md` is the source the issue and design §5
  name.
- **The red tests.** Each named red test is red today, because the functions
  do not exist.

## What this review could not verify

- I did not run pytest.
- I did not check that `test_the_repos_own_plan_md_records_a_proof` stays green
  under an implementation, because none exists yet.
- Whether a Windows `git` on another machine has a system `core.autocrlf` other
  than `true`. Finding 4's fix makes the test independent of it.
