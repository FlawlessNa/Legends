"""
The destination sources: one rotation each, one module each (#571).

`DestinationProvider` (`maple/decision_makers/providers/destination.py`) serves
the one the profile's `rotation` names, from its registry, `SOURCES`. A source
decides where the character goes, never how: Paths are planned to it as to any
destination.

- `random`: random points on the platforms a Path reaches.
- `smart`: towards the side most mobs are on.
- `hunting_area`: towards the mobs inside the Hunting Area, else around it.
"""
