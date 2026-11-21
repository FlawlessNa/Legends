"""
The client's job ids, and a job's line: the jobs whose skills it has.

A profile names its job by `character_class`; the client knows it by an id. A
skill's name is looked up only among the skills of the character's line
(`maple.model.characters.maple_skills`), since a name can belong to several jobs:
`Teleport` is a Wizard's, a Cleric's and others'.
"""

# The profile's `character_class`, case aside -> the client's job id. A job has
# its own skills and those of every job before it, back to the beginner's (0).
JOB_IDS: dict[str, int] = {
    "beginner": 0,
    "swordsman": 100,
    "fighter": 110,
    "crusader": 111,
    "hero": 112,
    "page": 120,
    "whiteknight": 121,
    "paladin": 122,
    "spearman": 130,
    "dragonknight": 131,
    "darkknight": 132,
    "magician": 200,
    "wizardfirepoison": 210,
    "magefirepoison": 211,
    "wizardicelightning": 220,
    "mageicelightning": 221,
    "cleric": 230,
    "priest": 231,
    "bishop": 232,
    "archer": 300,
    "hunter": 310,
    "crossbowman": 320,
    "rogue": 400,
    "assassin": 410,
    "hermit": 411,
    "bandit": 420,
    "chiefbandit": 421,
    "shadower": 422,
}


def job_line(job: str) -> frozenset[int]:
    """
    The ids of `job` and of every job before it: Bishop (232) is
    `{0, 200, 230, 231, 232}`.

    :raises LookupError: `job` isn't in `JOB_IDS`.
    """
    try:
        job_id = JOB_IDS[job.casefold()]
    except KeyError:
        raise LookupError(
            f"no job id for {job!r}; the known jobs are {', '.join(JOB_IDS)}"
        ) from None
    tens = job_id - job_id % 10
    return frozenset({0, job_id - job_id % 100, *range(tens, job_id + 1)})
