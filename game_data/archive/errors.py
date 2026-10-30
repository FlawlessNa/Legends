"""
The errors `archive/` raises.

Every error names where it happened: the archive file, the image inside it, and
the node path inside the image. A reader that fails never returns what it had
read so far.
"""

from pathlib import Path


class ArchiveError(Exception):
    """
    Base of every error raised while reading the client's files.

    :param archive: The file being read.
    :param image: The image being parsed, such as `000001000.img`, or `None`
        when the error is in the archive's header or directory.
    :param node: The path inside the image (`info/bgm`), or inside the archive's
        directory, or `None` when there is no narrower place to point at.
    :param reason: What was wrong.
    """

    def __init__(
        self,
        archive: Path | str,
        image: str | None,
        node: str | None,
        reason: str,
    ) -> None:
        self.archive = str(archive)
        self.image = image
        self.node = node
        self.reason = reason
        super().__init__(self._describe())

    def _describe(self) -> str:
        where = [f"archive {self.archive}"]
        if self.image is not None:
            where.append(f"image {self.image}")
        if self.node is not None:
            where.append(f"node {self.node or '/'}")
        return f"{', '.join(where)}: {self.reason}"


class CorruptArchive(ArchiveError):
    """The bytes don't follow the format: truncated, out of range, or unknown."""


class UnsupportedFormat(ArchiveError):
    """A format this reader recognises but doesn't implement."""


class NodeNotFound(ArchiveError, LookupError):
    """
    A path names nothing in the client data.

    `archive` is the client's `Data` folder when the missing piece is a
    directory or an image, and the image's archive when it is a node inside it.
    """


class BrokenLink(NodeNotFound):
    """
    A canvas's `_outlink` or `_inlink` names nothing, so its pixels can't be
    found. `node` is the link's path. The client has one: an icon under
    `Character/Weapon` whose `_inlink` names a node its image doesn't have.
    """
