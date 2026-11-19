"""
The DecisionMaker that picks our character among others by its name tag names
the `name-tag` glyphs, so a bot without them refuses to start, as for the other
font readers (#457).
"""

from maple.decision_makers.mobs_hitting import MobsHitting
from maple.screen.name_tag import NAME_TAGS
from maple.screen.sprites import enabled_readers


def test_mobs_hitting_names_the_name_tag_reader() -> None:
    """It is what asks `Character.get_onscreen_position`, which reads the tags
    (`mobs_hitting.MobsHitting._get_on_screen_pos`)."""
    assert NAME_TAGS in MobsHitting.screen_readers
    assert NAME_TAGS in enabled_readers([MobsHitting])
