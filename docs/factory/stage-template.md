# Stage section template

Copy the block below into [stages.md](stages.md) to add a stage. Every slot is
required; one that genuinely has nothing to add says so rather than being
deleted. What each slot answers, and what holds for every stage without being
repeated, is in [stages.md → How to read a stage section](stages.md#how-to-read-a-stage-section).

Adding a stage also means teaching `factory next` to route to it (until #140,
a row in the entry skill's stub table) and a row in the stage table in
[README.md](README.md).

```markdown
## <#> · <Stage name> → <artifact>

### Trigger

`<identifier>`. Routed here when <the state of the .factory/<n>/ chain>.
Role: <role from roles.md, or "none">.

### Entry gate

<What must already be true. Name the artifact fields, not a feeling.>

### Context

<What to read beyond the standing list: CONTEXT.md entries, ADRs, docs/agents/ pages.>

### The work

<What to do. It ends at an artifact, never at a merge.>

### The oracle

<Exactly how done is demonstrated, and its enforcement marker.>

### Artifacts

<What the stage leaves behind, and where its contract lives in artifacts.md.>

### Decide and record

What this stage's agent decides for itself rather than asking. Anything not in
the Stop list below, and not one of the three things the maintainer owns
(scope approval on a hard-stop path, risk appetite, product priority,
or anything needing observation of a running client).

The conservative option, recorded under "Decisions I made" in this stage's
artifact, with the reasoning. Never a question asked mid-session.

### Stop and hand back

- <Stage-specific stops, beyond the standing list in AGENTS.md.>
```
