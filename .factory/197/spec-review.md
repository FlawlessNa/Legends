---
ticket: 197
verdict: changes-requested
reviewed_by: explore-subagent (read-only, no write access)
reviewed_at: 2026-10-17
transcribed_by: claude
---

# Spec review: #197

Read-only agent, given `intent.md`, `spec.md` and the new README section only.
It was asked directly whether the fix over-corrects. It found that it did.

## Findings, and what was done

**1. Criterion 5 contradicts criterion 6 — ACTED ON.** Criterion 5 says move any
stop that is not one of the three reasons into "Decide and record"; criterion 6
says a measured constant must still stop. A measured constant is not one of the
three, so an agent satisfying the spec literally deletes the half the intent
says must not erode.

**2. The operative test excluded the observation class — ACTED ON.** The README
said *"Exactly three things need the maintainer"*, which is false. An agent
applying the stated test would correctly decide a measured constant for itself.
The protective sentence existed only as a trailing assurance after
*"Anything else is yours."*

> "The disclaimer needs to become part of the enumeration, not a footnote to it."

Fixed: **Observation** is now item 4 in the numbered list, in README and
`roles.md`, and the stage pointers say four rather than three. The README also
records why, so the next editor does not undo it.

**3. The new rule carried no enforcement marker — ACTED ON.** The README's own
contract requires one on every rule. Marked **[instruction]**.

**4. The intent's open question answered but not recorded — ACTED ON.** The
stage sections and the template now *reference* the README rule rather than
restating it, which is what keeps twelve copies from drifting.

**5. No criterion covers #180 — NOT ACTED ON.** Correct, and deliberately left:
a spec that fails to say what the agent may decide is indeed incomplete, and
#180's checklist should gain that question. Recorded on #180 rather than scoped
into this ticket.

## Criterion 5 was not executed as written

Nothing was moved out of any "Stop and hand back" section. Executing criterion 5
literally would have stripped the observation class, which criterion 6 forbids
and the intent names as a hard constraint. Counterparts were **added**; stops
were left intact.

The criterion stands unedited in `spec.md`, unsatisfied, with this as the
record. The Builder does not get to rewrite a criterion it finds inconvenient —
even when a reviewer agrees the criterion is wrong.

## On over-correction, verbatim

> "A hard-stop path is safe: item 1 names it explicitly. Risk appetite and
> priority are safe. The measured-constant / running-client / minimap class is
> **not** safe: an agent applying the stated test ('is it one of the three? no →
> decide and record') plough through it correctly, by the letter, and the
> disclaimer's only enforcement is a pointer to sections that criterion 5 is
> simultaneously instructing the agent to strip."

## Criteria it judged sound

> "bootstrap.md says questions are batched into the PR body under a named
> heading, never asked mid-session"

Decidable from the diff alone: the file either contains that instruction with a
named heading or it does not, and the heading name is checkable against the
README.
