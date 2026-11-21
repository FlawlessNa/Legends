---
status: accepted
---

# Skills, weapons and reach come from the client's files

## Context

Until epic #631, a character's skills were a hand-written `dict[str, MapleSkill]`
on each job's `Character` subclass (`maple/model/characters/`), with
`animation_time`, `duration` and `horizontal_screen_range` typed in.
`MobsHitting` knew one `training_skill` and one `mob_count_threshold`, and the
rotation ranked spots by the same single threshold.

That failed in four ways:

- A job with an empty table could not attack at all: the maintainer's Swordsman
  had none, and `character_class: Fighter` raised a `KeyError`, since `MAPPING`
  had no Fighter, Page, Spearman or Bandit.
- Every number was typed by hand, from measuring the screen or from memory, and
  nothing said where it came from. Cast times, which decide how long a key is
  held, were the worst: Teleport's 0.6 s was one of them.
- A skill's numbers change with its level (14 of the client's 39 attack skills
  change their box or `range`; Iron Body lasts 300 s at level 1 and 600 s at
  level 20), which a table with one value per skill could not say.
- The client's own files already hold all of it, as they hold the maps
  (ADR 0004, virtual coordinates): each skill's levels, boxes, counts,
  cooldowns and durations, each weapon's swing set and speed, and each
  action's frame delays.

## Decision

- **Skills come from the catalogue** (`game_data`). A character's skills are
  built at launch for the names its `Skill Keys` give, by `SkillsProvider`
  (`SKILLS`). A name is looked up only in the character's job line, since one
  name can belong to several jobs. A name the line doesn't have refuses the
  start, and names the closest. The hand-written tables, `MapleBuff`,
  `MaplePartyBuff` and `main_skill` are gone.
- **A skill is at a level the profile gives** (`skill_levels`), or at its maximum
  level, until the skill window is read in game (#630). A launch warning names
  each skill whose box, `range`, mobs hit or duration depends on its level and
  that the profile gives none for.
- **Reach comes from the client's files too.** A skill with a box reaches that
  box. A skill with no box and no action of its own is a weapon-based attack: it
  plays one of the weapon's swings, drawn at random, so it reaches only what every
  swing reaches, the overlap of the swing boxes of the weapon's attack family
  (brackets 0 and 10, which cover every mastery). A mob is in reach when its
  detection box overlaps the reach by at least a pixel, as the game decides.
  `docs/research/weapon-reach.md` has the sources and their trust.
- **Cast time comes from the client's files.** A skill with an action of its own
  takes that action's duration. A weapon-based attack takes the longest of its
  family's actions, each frame scaled by the weapon's speed as the client does,
  with no booster applied.
- **The weapon is read in game.** `EquipmentMenuProvider` opens the equipment
  window at launch, matches the weapon slot's pixels against the catalogue's
  weapon icons, and serves `WEAPON`. A weapon that can't be read refuses the
  start, naming what failed. There is no profile fallback.
- **The attacks are the profile's.** `attacks` is an ordered list of a skill and
  its `min_mobs`, and `facing` is `closest` or `most`. `MobsHitting` casts the
  first attack that fires, and the rotation ranks spots by the earliest attack
  that would fire there (`ATTACKS`, served by `AttacksProvider`). One list serves
  every job: a Spearman or a Fighter is a copy of the Swordsman's profile, a
  Bandit a different list. `training_skill`, `mob_count_threshold`,
  `included_buffs` and `excluded_buffs` are retired: each refuses the start and
  names its replacement, as `game_map` and `mobs` do. Buffs are the profile's
  `buffs` list.
- **Casts keep the existing cast path** (ADR 0002): the attack's key is pressed
  and held, with its auto-repeat, for the cast time. Cast times changed for every
  skill, Teleport's and the buffs' included, so key timing changed for every
  character.

### What is still game knowledge in code

The client's files don't hold these, so each is a small named table or constant
in code, with its source beside it:

- **Job ids and job lines** (`maple/model/characters/jobs.py`: `JOB_IDS`,
  `job_line()`). The profile names a job, and the files key skills by job id,
  but no file maps one to the other. Every job in `JOB_IDS` has a thin
  `Character` class carrying its `main_stat`, which the ability-point
  distribution needs and no file says. A new *job* needs that class once; a new
  *character* of a known job needs none.
- **The action families** (`FAMILY_ACTIONS` in `maple/model/characters/reach.py`):
  which actions a normal attack draws, by the weapon's attack family. The files
  say which actions exist and the weapon's family, not which of them a normal
  attack plays. It comes from the classic clients' code and the MSCW
  community, and the spear family's list is low confidence: the longer one is
  kept, since it can only shrink the overlap, and so the reach.
- **The brackets overlapped** (`BRACKETS`) and **the speed formula**
  (`DEGREE_MIN`, `DEGREE_MAX`, `SPEED_BASE`, `SPEED_DIVISOR`): from the same
  research. They stand in for the weapon mastery, which isn't read, and for the
  client's own scaling of a frame's delay.
- **`WEAPON_MATCH`**, the lowest icon correlation that names the weapon: a
  starting constant, tuned at the client.

Rejected:

- **A hand-written skill table per job, kept for the awkward skills.** Two
  sources of skill facts disagree silently, as ADR 0004 found for maps.
- **A class per job for `MobsHitting`.** A Spearman, a Fighter and a Swordsman
  would be three copies of one rule.
- **The skill table built from every skill of the job line.** Hundreds of
  skills, each needing a key it doesn't have. The `Skill Keys` name the skills
  the bot will press, and a key the client doesn't know is caught at launch.
- **`weapon:` in the profile.** Hand-written, and it drifts from what the
  character holds.
- **The union of the swings as the reach.** It swings at air.
- **`job // 10 * 10` for the job line.** It skips the 3rd job.

## Consequences

- Starting a bot needs the extraction's catalogue, as a map does. A Build
  without one can't start a bot that has skills or attacks.
- A character's setup is its `Skill Keys` and its profile. Nobody measures a
  skill's range on screen, or types its reach, timing or duration.
- A character whose attack has no reach in the files can't start. That is a
  weapon-based attack with a bow, a crossbow, a wand or a claw, and an attack with
  an action of its own and no box, such as Magic Claw. How such a reach is made
  is a later topic.
- Slash Blast's `range` (130, then 150) is ignored until #633 confirms what it
  means, so a count can be low, never high.
- Reaches are conservative by construction. The cast-outcome report (#640)
  records misses and skipped mobs from a recorded Session, so the reach can be
  widened from evidence.
- Launch sends keys: the equipment key, pressed to open the window and again to
  close it, through the controller and the Held-Keys Ledger, as the ability menu
  does.
- Boosters are not applied to cast times, so with one on, a cast waits a little
  longer than the game needs.
- What is unverified until a live Session reads it (#642): that the equipment
  window opens, closes and is read; that MSCW keeps the classic clients' rules the
  reach rests on (a uniform draw over the family, brackets by mastery); the
  spear and polearm actions; and the cast times.
- Telecast is gone: this server has none. Its two Event Types stay, retired
  (ADR 0001, additive).
