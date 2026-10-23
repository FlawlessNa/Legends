---
ticket: 216
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "every hook event takes its session root from the event's cwd field when that names an existing directory, and falls back to the process cwd otherwise"
---

# Spec review: the hook runs the main checkout's gate code

**Verdict: `changes-requested`.** The diagnosis is right, and the fix is right.
I reproduced every factual claim the spec makes. Two things block it. The red
test as specified can pass without the installed factory ever answering. The
"every event" criterion adds a stdin read that can hang, and two of its three
events have no test. Both are cheap to fix. Three smaller gaps against the issue
follow.

Reviewed: `spec.md` and `intent.md` at `374d04a`, issue #216, `design.md` §3 d4,
§7, §10, §12 and §13, `artifacts.md`, `factory-hook.sh`, `settings.json`,
`cli.py` (`_run_hook`, `_read_stdin`, `_written_path`, `_anchored`,
`_stop_everywhere`), `hooks.py` (`decide_write`, `_primary_refusal`,
`session_report`, `_primary_lines`), the hook tests in `test_cli.py` and
`test_hook_wiring.py`, `factory/AGENTS.md`, and `.claude/skills/factory/SKILL.md`.

## Claims I verified

I ran all of these in my scratchpad with the primary checkout's
`.venv\Scripts\python.exe` (3.14.7, `-B`). Nothing was written in the repo.

- **`-I` implies `-E -P -s` on 3.14.** `python -h` says exactly that.
- **Today's `-m` runs the shadow.** I used a temporary directory holding
  `factory/__init__.py` and a `factory/__main__.py` that prints
  `SHADOW-SENTINEL`. From that directory, `python -m factory hook session-start`
  printed the sentinel and exited 0. So did the **real `factory-hook.sh`** from
  this worktree, run via `bash "${CLAUDE_PROJECT_DIR}/..."` with that directory
  as cwd. The red test's premise holds.
- **`-I` loads the editable install.** From the same directory,
  `python -I -m factory hook session-start` printed the real `SessionStart` JSON,
  whose `additionalContext` opens with `factory gates: LIVE`. Under `-I`,
  `factory.__file__` is `C:\Users\Nassim\code\Legends\factory\__init__.py`, and
  `sys.path` holds no cwd entry. The mechanism is that the editable install is
  finder-mode: `__editable___legends_factory_0_1_0_finder.py` maps
  `factory` to the primary's `factory/`. It is appended to `sys.meta_path`, which
  is why a `factory/` found on `sys.path` has always won. `-I` removes the only
  `sys.path` entry that could hold one. `-I` also keeps `PYTHONPATH=.` from
  bringing the shadow back. Without `-I`, it does.
- **The `cwd` test is red today.** I set up a primary on `dev`, a builder on
  `issue/5-x` and a sibling on `scratch-branch`. The process cwd was an unrelated
  directory, and the event carried `"cwd": <builder>`. The worktree's
  `main(["hook", "pre-tool-use"])` wrote **nothing** to stdout. As a control,
  with the process cwd set to the builder, it denied with "Ticket 5 …". So the
  proposed test goes red, but on `json.loads("")`. See finding 7.
- **A worktree has no `.venv`.** Confirmed. `factory-hook.sh` falls back to the
  primary's, as the spec says.
- **`#159` owns the heartbeat's HEAD line.** Its body says so ("The SessionStart
  heartbeat prints the primary checkout's HEAD … (S1)"). The Not-in-scope entry
  is correctly attributed.

## Findings

### 1. The red test can pass without the real hook answering (blocking)

**Evidence.** The spec's red test makes one assertion: "Assert the sentinel never
appears." That assertion also holds whenever the hook does not run at all:

- No `.venv` is found. The script prints `factory hook unreachable` and exits 0.
  The sentinel is absent, so the test passes.
- `-I` breaks the import of the real `factory`. There is a traceback on stderr
  and nothing on stdout. The test passes again.

The issue asks for more: "assert the **real decision comes back**". `design.md`
§12 also leaves one claim for this ticket's tests to settle: "Whether
`python -I -m factory`, run from a worktree, loads the primary checkout's code in
the hook's real environment … #216's tests prove it." An absence-only test
proves neither.

Criterion 1's wording ("returns the installed factory's answer and never the
shadow's") is right. The test plan proves only its second half.

**Fix.** Make the red test assert both halves:

- stdout parses as a `SessionStart` payload whose `additionalContext` starts
  with the heartbeat line (`factory gates: LIVE`);
- `SHADOW-SENTINEL` appears nowhere in stdout or stderr.

Use `session-start` with empty stdin. It answers from any directory, and I
confirmed it does from a plain temporary directory. If the environment has no
`.venv`, make the test **skip with that reason** rather than pass. A pass there
would claim a proof that was never run.

### 2. "Every event" adds a blocking stdin read, and two of its three events are untested (blocking)

**Scope first: this is not creep.** The issue's *What to change* names
`_run_hook`, which answers all three events, and says it "takes the session root
from the hook event's `cwd` field". Its acceptance also asks for "a test that
`_run_hook` judges the event's `cwd`". Reading `cwd` for every event is the
literal ask.

The spec is also honest that the issue's premise is wrong. "The process may now
run from anywhere" is false, because `-I` does not move the cwd. So this part is
in scope, and its value is forward-looking. It is not part of the fix. That
makes its side effects worth pricing.

**Evidence: a hang.** Today `session-start` and `stop` never read stdin.
`.claude/skills/factory/SKILL.md:17` tells whoever notices a missing heartbeat to
run `bash .claude/hooks/factory-hook.sh session-start` by hand. A person who does
that in an interactive terminal after this change gets `sys.stdin.read()`
blocking until Ctrl-D. The diagnostic for "the hooks are dead" would then itself
look dead. In this agent's Bash tool, stdin reports `isatty() == True` but
returns EOF at once, so an agent would not notice. A human would.

**Evidence: untested branches.** Criterion 3 claims "every hook event", but the
test plan covers only `pre-tool-use` (criterion 4). Nothing exercises
`session-start` or `stop` taking the event's `cwd`. Nothing exercises the "names
an existing directory" fallback either. Existing tests cover only a *missing*
`cwd` key (stdin `{}` or empty), never a `cwd` naming a directory that does not
exist. A Builder could read `cwd` in the `pre-tool-use` branch alone, and every
specified test would pass.

**Fix.**

1. Add a criterion: the hook does not read stdin when stdin is a terminal, and
   treats that event as empty. In practice `_read_stdin` returns `{}` when
   `sys.stdin.isatty()`. The harness always pipes its event, so this costs
   nothing.
2. Add one through-`main` test for a second event. Example: `session-start`
   from an unrelated process cwd, with `"cwd": <builder on issue/5-x>`, asserts
   the report names ticket 5. That is red today, because the report says "Not
   in a ticket worktree".
3. Add one test where `cwd` names a directory that does not exist, and the
   answer falls back to the process cwd.

### 3. The issue's documentation criterion is replaced without saying so

**Evidence.** The issue's acceptance list ends with "`docs/factory/README.md`'s
description of how the hook resolves its interpreter is updated". The spec's
criterion 7 targets `factory/AGENTS.md` instead, and gives no reason.

The redirect is correct. `grep` finds no such description in
`docs/factory/README.md`; its only hook mention is line 24. `factory/AGENTS.md`
"How it runs" is where the hook's invocation is described, and it is **already
wrong**. It says "The console script is the one hooks and CI call". Hooks have
called `python -m factory` through `factory-hook.sh` since #199.

**Fix.** Record the deviation under *Decisions I made*: README holds no such
description, so AGENTS.md is the target. Make criterion 7 require that sentence
corrected, as well as adding the why-`-I` paragraph.

### 4. The issue's Could-not-verify is dropped, and one consequence is unnamed

**Evidence.** The issue says: "**Could not verify, by design:** that the primary
checkout is up to date … Say so in the PR body." The spec carries only its own
item, about a worktree `.venv`.

The spec also misses a consequence of the fix. Once `-I` lands, every subprocess
test in `test_hook_wiring.py`, run from a worktree, exercises the **primary's**
`factory`, not the branch's. Pytest's in-process tests still import the
worktree's copy, because the root `conftest.py` puts the worktree first on
`sys.path` and the editable finder comes last. So:

- this ticket's own `_run_hook` change is tested only in-process until it is
  merged and the primary has pulled it;
- any later ticket that changes a hook decision gets no end-to-end coverage of
  its own code from the wiring tests.

That is the intended effect of the fix, but a Builder or reviewer will not
expect it.

**Fix.** Under *Decisions* or *Could not verify*, state both:

- the primary checkout's currency, carried into the PR body as the issue
  requires;
- that subprocess hook tests now judge the primary's code from a worktree.

One sentence in `factory/AGENTS.md` would stop the next ticket being surprised.

### 5. Whether the event's `cwd` can differ from the hook's process cwd is asserted, not known (minor)

**Evidence.** The spec calls the event "the harness's own statement of where the
session is". If Claude Code reports a `cwd` that follows the agent's Bash `cd`,
the session root moves with it. It would not move if the process cwd stayed at
the launch directory. An orchestrator in the primary that `cd`s into a ticket
worktree would then be judged as that ticket's session (row 3 of `decide_write`,
and the identity check in `_primary_refusal`).

The intent permits changing "which directory it treats as the session". But this
is harness behaviour, and nothing offline settles it.

**Fix.** Add it to *Could not verify*: when the event's `cwd` and the process cwd
differ in a real session, and which one tracks a Bash `cd`.

### 6. Criterion 5 has no test (minor)

**Evidence.** "A hook that cannot find an interpreter still prints its
unreachable message and exits 0". No test covers it today: `grep unreachable
tests/` finds nothing in `test_factory`. As written it is decidable only by
reading the diff, by checking the script's last three lines are untouched. That
is acceptable, but the spec should say it is a diff-read criterion.

**Fix.** Either label it so, or add a cheap test. Copy `factory-hook.sh` into
`tmp/.claude/hooks/` of a directory with no `.git` and no `.venv`, run it through
bash, and assert exit 0 and the `unreachable` line on stderr.

### 7. The `cwd` test goes red on a decode error, not on the missing deny (minor)

**Evidence.** Against the current code the hook writes nothing (see *Claims I
verified*). A test modelled on `test_the_pre_tool_use_hook_still_reaches_the_session_row`
therefore fails at `json.loads("")` with `JSONDecodeError`. It is red, but the
stash-and-run evidence will show a parse error rather than "expected a deny".

**Fix.** Assert first that stdout is non-empty, with a message such as "no deny:
the session was taken from the process cwd". Then parse it.

## Notes, not findings

- `-I`'s `-E` also drops `PYTHONUTF8` and `PYTHONIOENCODING`. On this machine
  none are set, and stdin decodes as `cp1252` with or without `-I`, so nothing
  changes today. A non-ASCII path in an event was already decoded by locale.
  That is pre-existing, and out of scope.
- The *Decisions* on a worktree-local `.venv`, and on the worktree-read hook
  launcher, are sound and correctly deferred to §4 rule 2's fingerprint.

## What this review could not verify

- How Claude Code populates `cwd` for `SessionStart` and `Stop`, and whether it
  follows a Bash `cd` (finding 5).
- Anything in the harness's real environment beyond what a bash subprocess with
  the wiring tests' minimal env reproduces.
- I did not run pytest.
