import xml.etree.ElementTree as ET


class _PortalsExtractor:
    def __init__(
        self,
        portal_tree: ET.Element,
    ):
        self.tree = portal_tree
        self.res = self.extract_all()

    def extract_all(self) -> list[dict]:
        """
        Extracts all portals from the map .xml file, provided they are linked to
        some other portal and not just spawn points.
        https://mapleref.fandom.com/wiki/Portal
        pn: name of the portal (other portals points to a portal by its name)
        pt: type of portal
        tm: target map (ID)
        tn: name of the portal (located in the target map) linked to this portal

        Types of portals:
            - (0, sp) -> Starting Point
            - (1, pi) -> Portal Invisible
            - (2, pv) -> Portal Visible (default portals)
            - (3, pc) -> Portal Collision (invokes whenever it has collision with char)
            - (4, pg) -> Portal Changeable
            - (5, pgi) -> Portal Changeable Invisible
            - (6, tp) -> Town Portal Point (portals created from Mystic Door)
            - (7, ps) -> Portal Script, executes a script when a player enters it
            - (8, psi) -> Portal Script Invisible
            - (9, pcs) -> Portal Collision Script
            - (10, ph) -> Portal Hidden (appears when character is near)
            - (11, psh) -> Portal Script Hidden

        """
        res = []
        for portal in self.tree:
            portal_name = portal.find('string[@name="pn"]').get("value")
            portal_type = portal.find('int[@name="pt"]').get("value")
            if portal_name == 'sp' and portal_type == '0':
                continue
            elif portal_name == 'sp' or portal_type == '0':
                breakpoint()  # This should not happen
            target_map = portal.find('int[@name="tm"]').get("value")
            target_portal = portal.find('string[@name="tn"]').get("value")
            x = int(portal.find('int[@name="x"]').get("value"))
            y = int(portal.find('int[@name="y"]').get("value"))
            res.append(
                {
                    'name': portal_name,
                    'type': portal_type,
                    'target_map': target_map,
                    'target_name': target_portal,
                    'x': x,
                    'y': y
                }
            )
        return res

    def get_portal(self, portal_name: str) -> dict:
        for portal in self.res:
            if portal['name'] == portal_name:
                return portal
        return {}