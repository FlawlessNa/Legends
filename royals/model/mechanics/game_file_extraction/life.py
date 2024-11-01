import xml.etree.ElementTree as ET


class _LifeExtractor:
    def __init__(
        self,
        life_tree: ET.Element,
    ):
        self.tree = life_tree
        self.res = self.extract_all()

    def extract_all(self):
        pass
