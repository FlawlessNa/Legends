"""
`load_instructions`: the default, an extension, a replacement, and the errors
that refuse the start (#461).
"""

from pathlib import Path

import pytest

from maple.chat_replies.instructions import (
    SECTIONS,
    InstructionsError,
    load_instructions,
)

IGN = "Mapler"


def instructions(**sections: str) -> str:
    """An instructions file with every section. A keyword (a heading, or
    `persona`, `party`) sets that section's text; the text '-' leaves it out."""
    texts = {
        "Persona": "Be brief.",
        "Party and training requests": "Say no.",
        "GM": "Be careful.",
        "Never": "Never say you are a bot.",
    }
    keys = {"persona": "Persona", "party": "Party and training requests"}
    for key, text in sections.items():
        texts[keys.get(key, key)] = text
    body = "".join(
        f"## {name}\n\n{text}\n\n" for name, text in texts.items() if text != "-"
    )
    return f"# Instructions\n\nYou are a player.\n\n{body}"


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    (tmp_path / "chat_replies").mkdir()
    (tmp_path / "chat_replies" / "instructions.md").write_text(
        instructions(), encoding="utf-8"
    )
    (tmp_path / "chat_replies.ini").write_text(
        "[Replies]\nmax_reply_chars = 70\n", encoding="utf-8"
    )
    return tmp_path


def write(configs: Path, name: str, text: str) -> Path:
    path = configs / "chat_replies" / name
    path.write_text(text, encoding="utf-8")
    return path


def test_the_default_alone(configs: Path) -> None:
    loaded = load_instructions(IGN, configs)

    assert loaded.files == (configs / "chat_replies" / "instructions.md",)
    assert loaded.text == instructions().strip() + "\n"
    assert dict(loaded.sections) == {
        "Persona": "Be brief.",
        "Party and training requests": "Say no.",
        "GM": "Be careful.",
        "Never": "Never say you are a bot.",
    }
    assert loaded.max_reply_chars == 70


def test_an_extension_is_appended_to_the_default(configs: Path) -> None:
    extend = write(
        configs,
        f"{IGN}.extend.md",
        "## Persona\n\nYou main a bishop.\n\n## Style\n\nNo caps.\n",
    )

    loaded = load_instructions(IGN, configs)

    assert loaded.files == (configs / "chat_replies" / "instructions.md", extend)
    assert loaded.text.startswith(instructions().strip())
    assert loaded.text.endswith("## Style\n\nNo caps.\n")
    assert loaded.sections["Persona"] == "Be brief.\n\nYou main a bishop."
    assert loaded.sections["Style"] == "No caps."
    assert loaded.sections["GM"] == "Be careful."


def test_a_replacement_is_used_instead_of_the_default(configs: Path) -> None:
    replace = write(configs, f"{IGN}.replace.md", instructions(persona="Be curt."))

    loaded = load_instructions(IGN, configs)

    assert loaded.files == (replace,)
    assert loaded.sections["Persona"] == "Be curt."
    assert "Be brief." not in loaded.text


def test_another_characters_files_are_not_read(configs: Path) -> None:
    write(configs, "Other.replace.md", instructions(persona="Be curt."))

    assert load_instructions(IGN, configs).sections["Persona"] == "Be brief."


def test_an_extension_and_a_replacement_both_present_refuse(configs: Path) -> None:
    extend = write(configs, f"{IGN}.extend.md", "## Persona\n\nMore.\n")
    replace = write(configs, f"{IGN}.replace.md", instructions())

    with pytest.raises(InstructionsError) as raised:
        load_instructions(IGN, configs)

    assert str(extend) in str(raised.value)
    assert str(replace) in str(raised.value)


@pytest.mark.parametrize("missing", SECTIONS)
def test_a_missing_section_refuses_naming_it(configs: Path, missing: str) -> None:
    default = write(configs, "instructions.md", instructions(**{missing: "-"}))

    with pytest.raises(InstructionsError, match=f"no '## {missing}' section"):
        load_instructions(IGN, configs)

    with pytest.raises(InstructionsError, match=str(default).replace("\\", "\\\\")):
        load_instructions(IGN, configs)


def test_a_replacement_missing_a_section_refuses_naming_it(configs: Path) -> None:
    write(configs, f"{IGN}.replace.md", instructions(Never="-"))

    with pytest.raises(InstructionsError, match=r"replace\.md: no '## Never' section"):
        load_instructions(IGN, configs)


def test_an_empty_section_refuses_naming_it(configs: Path) -> None:
    write(configs, "instructions.md", instructions(GM=""))

    with pytest.raises(InstructionsError, match="'## GM' section is empty"):
        load_instructions(IGN, configs)


def test_a_subheading_stays_inside_its_section(configs: Path) -> None:
    write(
        configs, "instructions.md", instructions(GM="Be careful.\n\n### Tone\n\nKind.")
    )

    sections = load_instructions(IGN, configs).sections

    assert sections["GM"] == "Be careful.\n\n### Tone\n\nKind."


def test_a_missing_default_refuses_naming_it(configs: Path) -> None:
    default = configs / "chat_replies" / "instructions.md"
    default.unlink()

    with pytest.raises(InstructionsError, match="can't be read") as raised:
        load_instructions(IGN, configs)

    assert str(default) in str(raised.value)


@pytest.mark.parametrize(
    "settings",
    [
        "",
        "[Replies]\n",
        "[Replies]\nmax_reply_chars = many\n",
        "[Replies]\nmax_reply_chars = 0\n",
    ],
)
def test_a_bad_max_reply_chars_refuses(configs: Path, settings: str) -> None:
    (configs / "chat_replies.ini").write_text(settings, encoding="utf-8")

    with pytest.raises(InstructionsError, match="max_reply_chars"):
        load_instructions(IGN, configs)


def test_the_committed_default_loads() -> None:
    # An IGN no character has, so a local extension or replacement isn't read.
    loaded = load_instructions("NoSuchCharacter-461")

    assert loaded.files[0].name == "instructions.md"
    assert len(loaded.files) == 1
    assert set(SECTIONS) <= set(loaded.sections)
    assert loaded.max_reply_chars == 70
