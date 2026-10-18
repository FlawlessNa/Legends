---
name: factory
description: Route a factory ticket to its current stage. Use whenever you are on an issue/<n>-* branch, or are asked to work, continue or pick up a ticket in the Legends factory. Computes the stage from the .factory/<n>/ chain and points at the section of docs/factory/stages.md to follow; never choose a stage yourself.
---

# Factory: entry

This file routes. It holds no stage instructions — those live only in
`docs/factory/stages.md`. If this file and that one ever seem to disagree, this
file is wrong.

0. **Check the gates are alive.** Your session start should have reported a
   line beginning `factory gates: LIVE`. If it did not, the hooks are not
   running — the factory is enforcing *nothing*, and a dead hook is
   indistinguishable from one that allowed your action. Say so before you start
   work, and run
   `bash .claude/hooks/factory-hook.sh session-start` to see the error (#199).

1. Run `factory next <ticket>`. It names the stage, the role and the section to
   read.
2. Read `docs/factory/stages.md` → "How to read a stage section", then the
   section it named. Follow that section.
3. Do not choose a stage yourself, and do not proceed past a non-zero exit code.
4. When the section's oracle holds and its artifacts are committed, start again
   at step 1.
