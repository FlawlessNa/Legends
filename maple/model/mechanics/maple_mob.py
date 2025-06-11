import os
import xml.etree.ElementTree as ET

from botting.models_abstractions import BaseMob
from paths import ROOT


class MapleMob:
    """
    Dynamically create subclasses of BaseMob with class name being the mob's name.
    To do so, it maps the mob ID's received to corresponding mob names from game files.
    """
    _created_classes = {}
    mob_tree = ET.parse(os.path.join(ROOT, 'maple/assets/game_files/Mob.img.xml'))
    root = mob_tree.getroot()

    def __new__(cls, mob_id: int) -> BaseMob:
        return cls.create(mob_id)

    @classmethod
    def create(cls, mob_id: int) -> BaseMob:
        """
        Factory method to create an instance of a dynamically generated subclass of
        BaseMob.
        """
        if mob_id not in cls._created_classes:
            mob_name = cls._get_mob_name_from_id(mob_id)
            mob_class = type(
                mob_name, (BaseMob, ), {'_filter': None, '_preprocess_img': None}
            )
            cls._created_classes[mob_id] = mob_class
        else:
            mob_class = cls._created_classes[mob_id]
        return mob_class()

    @classmethod
    def _get_mob_name_from_id(cls, mob_id: int) -> str:
        """
        Parses the Mob xml file retrieved from game files.
        """
        return (
            cls
            .root
            .find(f"./imgdir[@name='{mob_id}']")
            .find("string[@name='name']").get('value')
        )