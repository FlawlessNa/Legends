"""
`catalogue.sqlite`'s tables, and the version they're at.

The schema is documented column by column in `docs/agents/game-data.md`, for
anyone querying the file directly, and a test holds the two together. Changing
a table bumps `SCHEMA_VERSION`, and an extraction whose catalogue is at another
version has it rebuilt from its raw layer when it's opened.
"""

from typing import Final

SCHEMA_VERSION: Final = 1
CATALOGUE: Final = "catalogue.sqlite"

TABLES: Final = (
    """CREATE TABLE strings (
        kind TEXT NOT NULL,
        id INTEGER NOT NULL,
        name TEXT,
        description TEXT,
        PRIMARY KEY (kind, id)
    )""",
    """CREATE TABLE maps (
        id INTEGER PRIMARY KEY,
        name TEXT,
        street TEXT,
        vr_left INTEGER NOT NULL,
        vr_top INTEGER NOT NULL,
        vr_right INTEGER NOT NULL,
        vr_bottom INTEGER NOT NULL,
        vr_derived INTEGER NOT NULL,
        minimap_center_x INTEGER,
        minimap_center_y INTEGER,
        minimap_mag INTEGER,
        minimap_width INTEGER,
        minimap_height INTEGER,
        town INTEGER NOT NULL,
        swim INTEGER NOT NULL,
        fly INTEGER NOT NULL,
        field_limit INTEGER NOT NULL,
        bgm TEXT,
        return_map INTEGER
    )""",
    """CREATE TABLE footholds (
        map INTEGER NOT NULL,
        source TEXT NOT NULL,
        layer INTEGER,
        group_id INTEGER,
        id INTEGER NOT NULL,
        x1 INTEGER NOT NULL,
        y1 INTEGER NOT NULL,
        x2 INTEGER NOT NULL,
        y2 INTEGER NOT NULL,
        prev INTEGER,
        next INTEGER,
        PRIMARY KEY (map, source, id)
    )""",
    """CREATE TABLE ropes (
        map INTEGER NOT NULL,
        source TEXT NOT NULL,
        id INTEGER NOT NULL,
        x INTEGER NOT NULL,
        y1 INTEGER NOT NULL,
        y2 INTEGER NOT NULL,
        ladder INTEGER,
        usable_from_foothold INTEGER,
        page INTEGER,
        PRIMARY KEY (map, source, id)
    )""",
    """CREATE TABLE portals (
        map INTEGER NOT NULL,
        name TEXT NOT NULL,
        type INTEGER NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        target_map INTEGER,
        target_portal TEXT
    )""",
    """CREATE TABLE spawns (
        map INTEGER NOT NULL,
        kind TEXT NOT NULL,
        id INTEGER NOT NULL,
        x INTEGER NOT NULL,
        cy INTEGER NOT NULL,
        foothold INTEGER NOT NULL,
        rx0 INTEGER NOT NULL,
        rx1 INTEGER NOT NULL,
        respawn_time INTEGER,
        flip INTEGER NOT NULL,
        hidden INTEGER NOT NULL
    )""",
    """CREATE TABLE map_layers (
        item INTEGER PRIMARY KEY,
        map INTEGER NOT NULL,
        kind TEXT NOT NULL,
        layer INTEGER,
        z INTEGER NOT NULL,
        zm INTEGER,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        flip INTEGER NOT NULL,
        origin_x INTEGER,
        origin_y INTEGER,
        frame_count INTEGER NOT NULL,
        asset TEXT,
        type INTEGER,
        rx INTEGER,
        ry INTEGER,
        cx INTEGER,
        cy INTEGER,
        a INTEGER,
        front INTEGER
    )""",
    """CREATE TABLE layer_frames (
        item INTEGER NOT NULL,
        frame INTEGER NOT NULL,
        image TEXT,
        origin_x INTEGER NOT NULL,
        origin_y INTEGER NOT NULL,
        delay INTEGER,
        PRIMARY KEY (item, frame)
    )""",
    """CREATE TABLE physics (
        key TEXT PRIMARY KEY,
        value REAL NOT NULL
    )""",
)

INDEXES: Final = (
    "CREATE INDEX portals_map ON portals (map)",
    "CREATE INDEX spawns_map ON spawns (map)",
    "CREATE INDEX map_layers_map ON map_layers (map)",
)
