import xml.etree.ElementTree as ET


class _BackgroundExtractor:
    def __init__(
        self,
        background_tree: ET.Element,
    ):
        self.tree = background_tree
        self.res = self.extract_all()

    def extract_all(self):
        pass
