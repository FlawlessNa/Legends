"""
The instructions the model answers players with.

`configs/chat_replies/instructions.md` is committed and reviewed like code. A
character may have, gitignored beside it, at most one of:

- `<IGN>.extend.md`, appended to the default;
- `<IGN>.replace.md`, used instead of it.

Either way the result must have every section of `SECTIONS`, each with some
text in it. A section the default and an extension both have is the two joined,
the default's first. Any other `##` section is kept as written.

`max_reply_chars`, the longest reply sent, is read from
`configs/chat_replies.ini`.

A problem with any of this refuses the start, naming the file or section.
"""

import configparser
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from paths import ROOT

CONFIGS = Path(ROOT) / "configs"
DEFAULT = "instructions.md"
SETTINGS = "chat_replies.ini"
SECTIONS = ("Persona", "Party and training requests", "GM", "Never")
"""The sections the instructions must have, as their `##` headings read."""
_HEADING = re.compile(r"^## +(?P<name>.+?) *$")


class InstructionsError(Exception):
    """The instructions can't be loaded. The message names the file or section."""


@dataclass(frozen=True, slots=True)
class Instructions:
    """
    :ivar text: The whole instructions, as the model is given them.
    :ivar sections: Each `##` section's text, by heading, without the heading.
    :ivar max_reply_chars: The longest reply sent, in characters.
    :ivar files: The files read, in order.
    """

    text: str
    sections: Mapping[str, str]
    max_reply_chars: int
    files: tuple[Path, ...]


def load_instructions(ign: str, configs: Path = CONFIGS) -> Instructions:
    """
    The instructions `ign` answers with.

    :param configs: The configs directory, holding `chat_replies.ini` and the
        `chat_replies/` directory of instructions.
    :raises InstructionsError: a file is missing or unreadable, both an
        extension and a replacement exist, or a section is missing or empty.
    """
    directory = configs / "chat_replies"
    default = directory / DEFAULT
    extend = directory / f"{ign}.extend.md"
    replace = directory / f"{ign}.replace.md"
    if extend.exists() and replace.exists():
        raise InstructionsError(
            f"{extend} and {replace} both exist: keep at most one of them"
        )
    if replace.exists():
        files = (replace,)
    elif extend.exists():
        files = (default, extend)
    else:
        files = (default,)
    text = "\n\n".join(_read(path).strip() for path in files) + "\n"
    sections = _sections(text)
    for name in SECTIONS:
        if name not in sections:
            raise InstructionsError(f"{_names(files)}: no '## {name}' section")
        if not sections[name]:
            raise InstructionsError(
                f"{_names(files)}: the '## {name}' section is empty"
            )
    return Instructions(text, sections, _max_reply_chars(configs / SETTINGS), files)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise InstructionsError(f"{path} can't be read: {error}") from error


def _names(files: tuple[Path, ...]) -> str:
    return " + ".join(str(path) for path in files)


def _sections(text: str) -> dict[str, str]:
    """Each `##` section's text, by heading. A heading met twice is one section,
    its two texts joined in order."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = found.setdefault(heading["name"], [])
            current.append("")
        elif line.startswith("# "):
            current = None
        elif current is not None:
            current[-1] += line + "\n"
    return {
        name: "\n\n".join(part.strip() for part in parts if part.strip())
        for name, parts in found.items()
    }


def _max_reply_chars(path: Path) -> int:
    parser = configparser.ConfigParser()
    try:
        with path.open(encoding="utf-8") as file:
            parser.read_file(file)
        value = parser.getint("Replies", "max_reply_chars")
    except (OSError, configparser.Error, ValueError) as error:
        raise InstructionsError(
            f"{path}: no whole number for 'max_reply_chars' under [Replies]: {error}"
        ) from error
    if value <= 0:
        raise InstructionsError(f"{path}: 'max_reply_chars' is {value}, not positive")
    return value
