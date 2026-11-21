# Weapon reach: swings, brackets, attack speed

Summary of what the reach rules of #631 rest on. Researched 2026-11-19 from the
MSCW client's files (extraction `3c238cfcb903ce34`) and from the classic clients'
code. Nothing was sent to the game. The full notes, with every quotation, are in
the maintainer's `.lavish/mobs-hitting/research-swings.md`.

**MSCW is not a v62 or v95 binary.** Its data mixes classic content with fields
no classic client had (`processtype`, `common`), and its skill IDs were
renumbered (Slash Blast is 1001002 here, 1001005 in v62 and v83). So every
client-code source below shows how a *classic* client behaved, not what the MSCW
binary does. Where the MSCW data has the same shape as the classic data
(swing sets, the body's actions and their delays), the behaviour very likely
carries over. Behaviour hard-coded per skill ID is the most likely to differ.

## Sources, by trust

| Source | What it is | Trust |
| --- | --- | --- |
| MSCW client data (`raw.sqlite`) | The client's own files | Primary |
| jon-zu/shroom95-decomp | Hand decompilation of the official v95 client, named from its PDB; many functions are still stubs | High, for what it decompiles |
| tensorfish/openms | Browser re-implementation from Ghidra work on a ~v83 client; cites function addresses | Medium-high |
| SYJourney/JourneyClient | Fan C++ client for v83 data; partly guessed | Medium |
| P0nk/Cosmic | OdinMS-lineage v83 server | High, for what a server checks |
| meowdb.com/msclassic | Community guides about MSCW itself (weapon reach, attack speed); its numbers match the data exactly | Medium |

## Attack families and their actions

A weapon's `info/attack` is its **attack family**: 1 a one-handed weapon or a
dagger, 2 a spear or polearm, 3 a bow, 4 a crossbow, 5 a two-handed weapon,
6 a wand or staff, 7 a claw, 8 bare hands. The data shows it directly, and it
matches the fan client's enum (confidence: high).

Action names follow the family: `O` is one-handed (`swingO1-3`, `stabO1-2`),
`T` two-handed (`swingT1-3`, and `stabT1-2` for spears, polearms and
crossbows), `P` spear and polearm swings. A trailing `F` is a Final Attack pose
(medium-high), and `proneStab` is the attack lying down.

A normal attack draws one action at random from its family at every attack.
Power Strike and Slash Blast have no `action` node and play that same draw
(medium-high; MeowDB says so for MSCW). The draw the reach uses (medium; fan
client plus MSCW community, the official function isn't decompiled):

| family | actions drawn at random |
| --- | --- |
| 1 | `stabO1`, `stabO2`, `swingO1`, `swingO2`, `swingO3` |
| 5 | `swingT1`, `swingT2`, `swingT3`, `stabO1`, `stabO2` |
| 2 | `swingP1`, `swingP2`, `swingT2`, `stabT1`, `stabT2` |

**The spear set is low confidence**: JourneyClient draws only `stabT1` and
`swingP1`. The longer list is used because it can only shrink the overlap.

`Character/Afterimage/<set>.img/<bracket>/<action>` holds each action's hit box
(`lt`, `rb`, facing left, relative to the feet). Each action also names the body
frame where the hit lands: `swingO1` at frame 2, after 450 ms of its delays,
`stabO1` at frame 1, after 350 ms. A weapon's `info` has no reach field of its
own. Sets: `axe`, `barehands`, `crossBow`, `mace`, `poleArm`, `spear`, `swordOL`,
`swordOS`, `swordTL`, `swordTS`; there is no bow set, and bows use `swordTS`.
`blank` and `hit` hold no boxes.

## Brackets

In the official v95 client the bracket is the weapon **mastery**, not the
character's level: `max(0, mastery% - 10) / 5` (decompiled `GetAfterimageUOL`;
confidence medium-high that MSCW does the same). A mastery skill's `mastery`
runs 1 to 10 over its 20 levels, which is the bracket.

The data agrees: brackets 0 to 9 are identical in every set, and bracket 10
differs by at most 11 px, mostly on the far edge (`swordOL` `swingO1`:
(-88, -62) to (-90, -72) at the top left). `mace`, `spear` and `poleArm` are
identical in every bracket, and bare hands goes to 16. So the reach is the
overlap of brackets 0 **and** 10, right whatever the mastery. A competing fan
reading, character level over 10, is contradicted by bare hands' 17 brackets.

## The speed formula

Each frame scales on its own: `trunc(delay x (10 + degree) / 16)`, and the
action takes the sum. `degree = clamp(weapon attackSpeed + Booster + party
booster + aura, 2, 10)`; a weapon Booster's `x` is -2 in MSCW. Decompiled
(`get_attack_speed_degree`, `GetDamageDelay`) and it reproduces MeowDB's
measured MSCW times, 720 ms for a swing at speed 4 and 750 ms for a spear stab
at 6 (confidence: high). Players see the time rounded up to 30 ms; that is
MeowDB's model, not a client rule (medium).

A one-handed sword at speed 4 (`swingO1` delays 300, 150, 350): 262 + 131 + 306
= 699 ms. With a Booster, degree 2: 599 ms. JourneyClient's `1.7 - speed / 10`
is a guess and doesn't match.

## The Slash Blast rule: still unconfirmed

Slash Blast has `range` (130, then 150 from level 11) and `areaAttack`, and no
box. In the classic client (openms, Ghidra-backed, medium-high): the drawn
action's box is placed, and if at least one mob is in it, the box's far edge
moves out to the character's x +/- `range`, the height stays the action's, and
up to `mobCount` mobs are hit, nearest first. That branch is hard-coded on the
classic skill IDs, and **MSCW renumbered Slash Blast**, so whether it keeps the
branch can't be known from the data (confidence for MSCW: low-medium). Only a
live check settles it. Until then `range` is ignored: Slash Blast counts fewer
mobs than it may hit, never more.

`range` is always a distance in px (high). `areaAttack` is on Power Strike
too, and nothing found reads it; it is unknown, and ignored. Cosmic shows a
server doesn't rebuild the melee box: the client picks the targets, and the
server only rejects one more than about 447 px away.

## Not verified

- Whether the MSCW binary keeps the random draw, the mastery brackets, or Slash
  Blast's extension.
- The spear family; the 30 ms rounding; Rush's `range`.
