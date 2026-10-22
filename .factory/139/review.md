---
ticket: 139
stage: review
verdict: changes-requested
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-22
commit: 6a87bc05599a9e66b1e5b3abe41c6bac6c4b475a
---

# Review: chain v2

**Verdict: `changes-requested`.** The work is careful. The red proof
reproduces, the suite is green, `front_matter` is byte-identical, the plan's
deviation for `blob` is real, and every committed chain reads cleanly. Two
defects need fixing first, and both are small and inside the radius:

1. `front_matter_lists` silently half-reads two block-list spellings, which is
   what the spec's "absent, never half-read" rule forbids.
2. The `ls-tree` replacement in `blob` misses any path that git C-quotes. With
   `core.quotePath=false` it also raises.

The rest are minor.

## Criteria

| # | Criterion (short) | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Block list reads in order, stripped, quotes kept, ends where it should | **Not fully met** | Tests `test_a_block_list_reads_in_order`, `test_items_keep_their_quotes`, `test_a_list_ends_at_the_next_top_level_key`. CRLF, tabs and list-as-last-key all read correctly (probed). But a column-0 `# comment` ends the list early and drops the items after it (F1a). |
| 2 | Flow lists `[]` and `[a, b]` | Met | `test_flow_lists` |
| 3 | Mapping items, or differing indentation, make the key absent; prose with `: ` is read | Met as written | `test_a_mapping_item_makes_the_key_unreadable`, `..._bare_mapping_item...`, `test_prose_with_a_colon_is_not_a_mapping`, `..._differing_indentation...`. Column-0 items break the same principle (F1b). |
| 4 | `front_matter` body and signature untouched; existing suite unmodified; lists via `front_matter_lists` | Met | The `def front_matter(` … `return found` text at `9654223` and at HEAD diffs empty. The only test file in the diff is the new `test_chain.py`, which is absent at `9654223`. No other test file is touched. |
| 5 | `Chain` exposes `spec_review`, `acceptance`, `proof`, `answers`, `park`; `criteria`/`radius` are tuples, empty when absent or unreadable | Met | `test_the_loop_s_artifacts_are_read`, `test_criteria_and_radius_are_tuples`, `test_absent_or_unreadable_lists_are_empty`. The `has_proof` and `Chain.proof` docstrings both state the split. |
| 6 | `ARTIFACTS` unchanged, `LOOP_ARTIFACTS` has five names, `present` covers both, session listing unchanged | Met | `test_artifacts_keeps_its_six_names`. `hooks.py:277-281` iterates `ARTIFACTS` only. Routing reads `present` only by explicit name (`routing.py:120-166`), so no route changes. |
| 7 | `version`: 1 when absent or no key, 1, 2, else `UnknownChainVersion` | Met | `test_the_version_marker` (4 cases) and `test_an_unknown_version_is_an_error_not_a_guess` (5 cases, including `2  # a comment`) |
| 8 | `blob`: id of the file at the commit; `None` for missing commit, missing path or directory; LF id under autocrlf with CRLF on disk | **Not met for C-quoted paths** | The CRLF test asserts CRLF on disk and compares against `hash-object` of the LF bytes. The `None` cases are tested. But a tracked file whose path git quotes returns `None`, and with `core.quotePath=false` the call raises (F2). |
| 9 | `radius_errors` grammar and messages | Met | 14 rejected and 6 accepted forms are tested. I also checked `/**`, `a/**/**`, `a**` and `factory/**/`: all are rejected. `.claude/...` and `.factory/<n>/**` are accepted. Each message carries `repr(entry)` and both forms. |
| 10 | Every chain committed at `9654223` reads: criteria counts, valid non-empty radii, v1, `resolve` does not raise | Met | `test_the_repo_s_committed_chains_read_cleanly` covers all 13. I ran an independent script over all 13 plus 139 (see Evidence). |
| 11 | `artifacts.md` contracts for the five files and `chain`, each naming its ticket; radius grammar replaces "list of globs"; list grammar stated | Met, with doc gaps | Every contract and ticket is present. "list of globs" is gone and appears nowhere else in the tree. The list grammar is under "What the reader understands". Minor gaps are in F4 and F5. |

## Findings

### F1. `front_matter_lists` half-reads two block-list spellings (major)

Probed with `front_matter_lists` on files written byte-for-byte:

| Input | Result | Should be |
| --- | --- | --- |
| `radius:\n  - a.py\n# note\n  - b.py` (a column-0 comment inside the list) | `{'radius': ('a.py',)}` | `('a.py', 'b.py')`, or absent |
| `radius:\n- a.py\n- b.py` (a compact YAML sequence at column 0) | `{'radius': ()}` | absent |

- **F1a.** The plan's own rule is "lines whose stripped text starts with `#`
  are skipped inside a list". The function's docstring and `artifacts.md` both
  say "`#` comments inside it are skipped". The code only skips *indented*
  comments: a column-0 `#` takes the `not line.startswith((" ", "\t"))` branch,
  which closes the list. The orphaned `- b.py` is then ignored because `key is
  None`. The result is a silently narrower radius, or a criteria count that is
  short by one, with nothing to say so.
- **F1b.** Column-0 items are valid YAML, and the commonest alternative
  spelling. Here they read as a *present, empty* list. That passes
  `radius_errors(())`, and it is indistinguishable from `criteria: []`.

**Fix.** While a key with an empty value is open:

- skip a column-0 line whose stripped text starts with `#`;
- mark the key broken on a column-0 line that starts with `-`.

Add one test for each case.

### F2. `blob` misses every path git C-quotes, and can raise (major)

The deviation itself is right. On git 2.39.1,
`git rev-parse --verify --quiet "HEAD:factory/chain.py^{blob}"` exits 1, while
the same spec without the peel exits 0 and prints `61f0673…`. The `^{blob}` is
read as part of the path.

The `ls-tree` replacement is right for:

- plain files;
- paths with spaces, `#`, `[`, and a leading `-`;
- directories, with and without a trailing `/`;
- missing paths, globs and pathspec magic (the exact-path comparison rejects them);
- bad commits (`nope`, forty zeros, `HEAD~5`, `-r`).

Three problems remain:

- **Quoted paths answer `None`.** With the default `core.quotePath=true`,
  `ls-tree` prints `"d\303\251j\303\240.md"`, `"q\"uote.md"`, `"t\tab.md"` and
  `"back\\slash.md"`. For each of those committed files, `blob` returns `None`
  where `git rev-parse HEAD:<path>` returns the id. I built them in a scratch
  repo with `git mktree -z`.
- **It can raise.** With `core.quotePath=false`, the UTF-8 output is decoded as
  `cp1252` because of `text=True` with no `encoding`. For a path containing
  `”` (byte `0x9d`), the reader thread hits a `UnicodeDecodeError`, `stdout` is
  `None`, and `blob` raises `AttributeError: 'NoneType' object has no attribute
  'splitlines'`. Its docstring says the opposite: "never an error". For `café.md`
  it silently returns `None`.
- **Option injection.** A `commit` that begins with `-` is parsed as an option.
  `blob(repo, "--help", …)` ran `git ls-tree --help`, which opened the HTML help
  in a browser and blocked. Callers pass SHAs today, so this is hardening, not a
  live bug.

**Fix.** Run `["git", "-C", root, "ls-tree", "-z", "--end-of-options", commit,
"--", relpath]` with `encoding="utf-8"` and `errors="surrogateescape"`, and
split on `"\0"`. I confirmed that `-z` and `--end-of-options` both work on this
git, and that `--end-of-options --help` exits 128. Add a test with a
non-ASCII path. Today's callers only hash `.factory/<n>/spec.md`, so nothing
current is affected, but criterion 8 is stated for any file.

### F3. Empty-valued keys and duplicate keys (minor)

- **Empty value.** `criteria:` with no items, whether followed by another key
  or last in the block, reads as `{'criteria': ()}`. So any empty-valued scalar
  becomes an empty list, `accepted_by:` included. That conflates YAML null with
  `[]`, the distinction spec-review cycle 1 raised for `spec submit`.
  `Chain.criteria` is `()` either way, so no criterion fails. Either record a
  block key only once it has an item, or document it.
- **Duplicate keys.** `radius:\n  - b.py\nradius: a.py` gives a list of
  `('b.py',)` while `front_matter` says `radius` is `'a.py'`. The two readers
  disagree about one key. **Fix:** a later column-0 scalar for the same name
  should pop the list, or a duplicate key should make the list absent.

### F4. The list grammar in `artifacts.md` omits two authoring traps (minor)

- **A wrapped item makes the whole key absent.**
  `criteria:\n  - a long\n    wrapped item` reads as `{}`. That behaviour is
  correct, and the plan states it ("any other indented line … makes the key
  absent"). But `artifacts.md` names only mapping items and differing
  indentation. Wrapping a long prose criterion is the likeliest way an author
  trips this, and `Chain.criteria` then silently becomes `()`.
- **A trailing comment stays part of the item.** `- a.py  # why` reads as
  `'a.py  # why'`, and `radius_errors` accepts it, because `#` and spaces are
  legal in the grammar.

**Fix.** One sentence for each in "What the reader understands".

### F5. `artifacts.md` against design §6 (minor)

- **`proof.md`.** Design §6 lists "output digests". `artifacts.md` omits them.
  Add them, or say they are not yet specified.
- **`intent.md`.** Design §6 says "`accepted_by` is retired for v2", but the
  `intent.md` table still describes it without that qualifier.
- **Everything else matches.** That covers `acceptance.md`'s seven fields and
  its validity rule, `proof.md`'s currency rule, `answers.md` (Designer, R5),
  `park.md` and `run.md`. Each ticket number matches the §10 build order:
  `accept` and `feature new` are #222, `proof.md` is #145, `factory park` and
  loop state are #219, and the loop is #159.
- **The Supersedes note.** Only the #139 bullet was removed. The #145 and #218
  bullets and the closing line are unchanged.
- **Outside the radius, note only.** `docs/factory/stages.md:282` still says
  "matches a glob in `radius`". That is still literally true of `dir/**`, but it
  is the last prose describing radius entries as globs.

### F6. Smaller test and code notes (minor, optional)

- **Nested sequences.** `- - a` reads as the item `'- a'`, a nested sequence
  half-read as a string.
- **Indentation width.** It counts characters, so `\t- a` and ` - b` count as
  the same indentation and both are read.
- **The `crlf_repo` fixture.** It does not set `commit.gpgsign=false`, so a
  developer with global signing gets a red fixture.
- **`test_the_loop_s_artifacts_are_read`.** It does not assert `answers.md`
  or `run.md` in `present`.

## The red proof

I wrote `git show 9654223:factory/chain.py` over `factory/chain.py`, kept the
tests, and ran `pytest -q -p no:cacheprovider tests/test_factory/test_chain.py`:

```
E   ImportError: cannot import name 'LOOP_ARTIFACTS' from 'factory.chain'
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.52s
```

That matches the plan's recorded output and its stated reason. I then ran
`git checkout HEAD -- factory/chain.py`. `git status --short` and `git diff
HEAD --stat` were empty afterwards.

The red is coarse: one import error stands for every test. That is acceptable,
because none of the names existed. It does mean no individual test was shown
red for its own reason.

## Other evidence

- **Full suite.**
  `C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`
  from the worktree root gave `1260 passed, 3 skipped, 25 deselected`, with 0
  failed, 0 errors and 0 xfailed. The three skips are pre-existing
  `movement_lab` Expectation skips, not this change.
- **Ruff.** `ruff check` gave "All checks passed!" and `ruff format --check`
  gave "2 files already formatted", on `factory/chain.py` and
  `tests/test_factory/test_chain.py`.
- **Pyright.** `pyright --pythonpath C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe`
  on the same two files reported 0 errors and 0 warnings.
- **Radius.** `git diff 9654223..HEAD --name-only` lists only `factory/chain.py`,
  `tests/test_factory/test_chain.py`, `docs/factory/artifacts.md` and
  `.factory/139/*`, which is inside the plan's radius.
- **Real chains.** For each of 139, 140, 153, 162, 179, 189, 191, 194, 197,
  199, 202, 206, 209 and 214, an independent script found:
  - criteria equal to the raw `- ` count (11, 9, 11, 11, 6, 9, 5, 21, 7, 5, 7,
    11, 12, 17);
  - every radius non-empty with `radius_errors == ()`, except 197 and 202, which
    have no `plan.md`;
  - every version 1;
  - `resolve` never raising, with 153, 179 and 191 blocked, as allowed.
- **`read_chain` cost.** It is linear, with nothing quadratic or unbounded:
  - `lists` is built only over `sorted(present)`;
  - `_front_block` and the loop are single passes;
  - the five new `front_matter` calls on absent files each cost one failed open.

  Best of 5×500 calls:

  | Ticket | `9654223` | HEAD |
  | --- | --- | --- |
  | 214 | ~0.67 ms | ~1.64 ms |
  | 194 | ~0.56 ms | ~1.40 ms |

  That is about 2.5×, because each present file is read twice, once for scalars
  and once for lists. It is acceptable per edit. A shared read would halve it,
  but criterion 4 freezes `front_matter`, so leave it.

## What I could not verify

- **`red_output_sha: 4c916731681b`.** I did not establish what it hashes.
- **`blob` on other platforms.** Only on Windows git 2.39.1. I did not
  reproduce a tab or quote in a path on a real filesystem; I used `git mktree`
  objects.
- **The `--help` side effect.** My test started a browser-help process on this
  machine. I killed the processes I could find. A browser tab may have opened.
- **Behaviour under a real factory loop or a `chain: 2` ticket.** Neither
  exists yet.
- **Hook timing in a live session.** The per-edit cost above is from a
  micro-benchmark, not from timing the hooks themselves.

## What the Builder should do

Fix F1 and F2, with a test for each that is red without the fix. Optionally
take F3 to F5 in the same turn, since they are documentation or one-line
changes inside the radius. Then re-run the suite.
