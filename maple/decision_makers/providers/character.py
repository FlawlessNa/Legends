"""
The Bot's character: its class, with its skills and its detection, and the
buffs its profile casts.
"""

from typing import Any

from botting.core import Key, Provider
from maple.model.characters.character import Character
from maple.screen.font import GlyphSet


class CharacterProvider(Provider):
    """
    Serves `CHARACTER`, made from the profile's `character_class`, and the
    names of the buffs the profile casts.

    Bot-level: the Bot resolves the class and the buffs from its profile when
    it is built, and registers the detection models before it builds this
    Provider. `setup()` makes the character, as `child_init` always did.
    """

    bot_level = True

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        character_class: type[Character],
        detection_configs: str | None = None,
        client_size: str = "medium",
        name_tags: GlyphSet | None = None,
        buff_names: tuple[str, ...] = (),
        **settings: object,
    ) -> None:
        """
        :param character_class: The class the profile's `character_class` names.
        :param detection_configs: The profile's detection settings.
        :param client_size: The profile's client size.
        :param name_tags: The glyphs that read name tags, when the sprites have
            them: the character finds its own by its name.
        :param buff_names: The buffs the profile casts, by skill name.
        """
        super().__init__(*args, **settings)
        self.character_class = character_class
        self.detection_configs = detection_configs
        self.client_size = client_size
        self.name_tags = name_tags
        self.buff_names = buff_names

    def setup(self) -> None:
        self.register(CHARACTER, self._character)
        self.register(BUFF_NAMES, lambda: self.buff_names)

    def _character(self) -> Character:
        made = self.character_class(
            self.data.ign, self.detection_configs, self.client_size
        )
        if self.name_tags is not None:
            made.read_name_tags_with(self.name_tags)
        return made


#: The character: its class's skills, and how it is detected on screen.
CHARACTER: Key[Character] = Key("character", CharacterProvider)
#: The buffs the profile casts, by skill name (`solo_buffs`).
BUFF_NAMES: Key[tuple[str, ...]] = Key("buff_names", CharacterProvider)
