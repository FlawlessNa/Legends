from maple.model.mechanics import MapleMap

MAP_NAME: str = 'FreeMarket7'
IGN: str = 'StarBase'

if __name__ == '__main__':
    MapleMap(
        MAP_NAME,
        True,
        include_character_position=True,
        ign=IGN
    )