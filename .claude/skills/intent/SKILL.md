---
name: intent
description: Start or continue a topic discussion with the maintainer on a lavish page, to agree on the intent (and a spec when the change is large) before any work is split into tickets. Use when the maintainer wants to discuss a topic, an idea, or "what we should build", or invokes /intent.
argument-hint: <topic>
---

# /intent: discuss a topic until we agree

The rules live in `docs/agents/topics.md`. Read it first; this file only says
how to run them. The page itself is a lavish page: use the `lavish` skill's
CLI guidance (`npx -y lavish-axi@0.1.92 --help`) for opening, polling and
replying, and don't modify that skill.

## Start a topic

1. **Ask before you propose.** Read what the maintainer said, then ask what
   you need to know about what they want and why. A recommendation comes after
   their answers, not instead of them.
2. Create `.lavish/<topic-slug>/`:
   - copy `.claude/skills/intent/template.html` to `index.html`, and fill in
     the context and one decision card per open question. Past the
     threshold, add `spec-section.html` before `</main>`;
   - write `intent.md` in the layout from `topics.md`, with status `draft`.
3. Render, then open the page and wait for feedback:
   ```
   node .claude/skills/intent/render.mjs .lavish/<topic-slug>
   npx -y lavish-axi@0.1.92 .lavish/<topic-slug>/index.html
   npx -y lavish-axi@0.1.92 poll .lavish/<topic-slug>/index.html
   ```
   Run the poll as a tracked background job, so its feedback wakes you.

## Each round of feedback

1. Address every item. Edit `index.html`, `intent.md` and `spec.md`, keeping
   every `data-block` id stable. A settled decision collapses into a short card
   with the same id, and joins "Already settled".
2. **Render again** before replying. That is what highlights the round's
   changes for the maintainer; a page you didn't render shows no change bar.
3. Reply with `poll --agent-reply`, or `reply`, keeping it short. If the poll
   returns `browser_disconnected`, ask whether to reopen; don't reopen
   uninvited.

## When it's agreed

Follow `topics.md`:
1. Mark the intent agreed and check the threshold.
2. Write and approve the spec if the threshold is crossed.
3. Publish the epic, file the tickets with the template, and link them as
   sub-issues.
