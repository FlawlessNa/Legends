"""
The client's whole `Data` folder as one namespace of directories and images.

**Trees.** Each folder `<Tree>/` holding a `<Tree>.wz` is a tree. Classic
splits a tree into a stub `<Tree>.wz` and parts `<Tree>_000.wz` ...
`<Tree>_NNN.wz`, where `<Tree>.ini` gives the last part's number as
`LastWzIndex|N` (`-1`: no parts). Without an `.ini`, the stub is the whole tree.
The stub and its parts read as one directory: an image or directory in two of
them raises `CorruptArchive` rather than one silently winning.

**Sub-trees.** A directory a tree lists, whose folder `<Tree>/<Dir>/` holds a
`<Dir>.wz`, is that folder's tree: so `Map/Map/Map0/000001000.img` is found
in `Map/Map/Map0/Map0_000.wz`. The top of the namespace is every tree directly
under `Data`.

**Packs.** Each `Data/Packs/*.ms` holds images under their full path, such as
`Mob/0000001.img` or `Skill/MobSkill/200.img`, and they join the namespace
there: a pack's image is listed and resolved exactly as an archive's is, and a
directory only a pack has is listed too. Entries that aren't `.img`, such as
`Mob/pack_ignore.txt`, aren't parsed: `ClientData.skipped` lists their paths.
An image both in a pack and in any `.wz` raises `CorruptArchive`, naming both,
rather than one silently winning. Packs are read when the namespace is first
listed.

**Paths** are `/`-separated: directories, then an image, then nodes inside it,
such as `Map/Map/Map0/000001000.img/info/bgm`.

- `ClientData.directory(path)` returns a `Directory`, whose `directories` and
  `images` list what is in it. Folders are read when first listed.
- `ClientData.image(path)` returns an `Image`: which archive it is in, and
  where. `Image.parse()` reads its property tree.
- `ClientData.node(path)` is the node at `path`, links and all.
- `ClientData.resolve(path)` is the same, but follows every `UolNode` on the
  way, and at the end. A link's path is relative to the link's parent node,
  and `..` may climb out of the image into the directories.

Lookups raise `NodeNotFound`, naming the path and what was missing.
"""

from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Protocol

from .errors import CorruptArchive, NodeNotFound
from .ms import MsPack, PackEntry
from .nodes import Node, PropertyNode, UolNode
from .wz import ImageEntry, WzArchive, WzDirectory

# How many links one `resolve` follows before it decides they form a loop.
MAX_LINKS = 64

# How many parsed images `ClientData` keeps for `node` and `resolve`.
CACHED_TREES = 32

_INI_KEY = "LastWzIndex"

# The folder under `Data` that holds the packs.
PACKS = "Packs"
_PACK_SUFFIX = ".ms"
_IMAGE_SUFFIX = ".img"


class _Container[E](Protocol):
    """A file that holds images: a `WzArchive` or an `MsPack`."""

    @property
    def path(self) -> Path: ...

    def read(self, entry: E, /) -> bytes: ...

    def parse(self, entry: E, /) -> PropertyNode: ...


class Image:
    """
    One image in the client data.

    :ivar name: Such as `000001000.img`.
    :ivar path: From the top of the namespace, such as
        `Map/Map/Map0/000001000.img`.
    :ivar archive: The `.wz` archive or `.ms` pack it is in.
    :ivar entry: Where it is in that file: an `ImageEntry` in an archive, a
        `PackEntry` in a pack.
    """

    __slots__ = ("_parse", "_read", "archive", "entry", "name", "path")

    def __init__[E: (ImageEntry, PackEntry)](
        self, path: str, archive: _Container[E], entry: E
    ) -> None:
        self.name = path.rpartition("/")[2]
        self.path = path
        self.archive = archive.path
        self.entry: ImageEntry | PackEntry = entry
        self._read = partial(archive.read, entry)
        self._parse = partial(archive.parse, entry)

    def read(self) -> bytes:
        """The image's bytes, decrypted when it is in a pack."""
        return self._read()

    def parse(self) -> PropertyNode:
        """
        The image's property tree, parsed afresh on every call. In a pack, its
        canvas, sound and raw-data offsets count from the image's first
        decrypted byte (`MsPack.parse`).

        :raises CorruptArchive: The image doesn't parse.
        """
        return self._parse()

    def __repr__(self) -> str:
        return f"Image({self.path!r}, archive={str(self.archive)!r})"


type _Contents = tuple[dict[str, "Directory"], dict[str, Image]]


class Directory:
    """
    A directory in the namespace: a tree, or a directory inside one.

    :ivar name: Empty for the top of the namespace.
    :ivar path: From the top, such as `Map/Map/Map0`.
    """

    __slots__ = ("_contents", "_load", "name", "path")

    def __init__(self, name: str, path: str, load: Callable[[], _Contents]) -> None:
        self.name = name
        self.path = path
        self._load = load
        self._contents: _Contents | None = None

    def _read(self) -> _Contents:
        if self._contents is None:
            self._contents = self._load()
        return self._contents

    @property
    def directories(self) -> Mapping[str, Directory]:
        """The subdirectories, by name."""
        return self._read()[0]

    @property
    def images(self) -> Mapping[str, Image]:
        """The images, by name, such as `000001000.img`."""
        return self._read()[1]

    def walk(self) -> Iterator[Image]:
        """Every image in this directory and below it, depth first."""
        yield from self.images.values()
        for child in self.directories.values():
            yield from child.walk()

    def __repr__(self) -> str:
        return f"Directory({self.path!r})"


@dataclass
class _PackIndex:
    """Every pack's entries, by the directory they are in."""

    images: dict[str, dict[str, Image]] = field(
        default_factory=dict[str, dict[str, Image]]
    )
    directories: dict[str, set[str]] = field(default_factory=dict[str, set[str]])
    skipped: list[str] = field(default_factory=list[str])


class ClientData:
    """
    The namespace over a client's `Data` folder.

    :param data: The folder, such as `...\\MapleStory\\MSCW\\Data`.
    :raises NotADirectoryError: `data` isn't a folder.
    """

    def __init__(self, data: Path) -> None:
        if not data.is_dir():
            raise NotADirectoryError(f"the client data folder {data} doesn't exist")
        self.data = data
        self.root = Directory(
            "", "", lambda: self._overlay("", self._trees_in(data), {})
        )
        self._trees: OrderedDict[str, PropertyNode] = OrderedDict()
        self._packs: _PackIndex | None = None

    @property
    def skipped(self) -> list[str]:
        """
        The paths of the pack entries that aren't images, and so aren't parsed,
        such as `Mob/pack_ignore.txt`.

        :raises UnsupportedFormat: A pack isn't v2.
        :raises CorruptArchive: A pack doesn't decode.
        """
        return list(self._pack_index().skipped)

    def directory(self, path: str) -> Directory:
        """
        The directory at `path`; `""` is the top.

        :raises NodeNotFound: There is none.
        """
        directory = self.root
        walked: list[str] = []
        for step in _steps(path):
            child = directory.directories.get(step)
            if child is None:
                raise NodeNotFound(
                    self.data,
                    None,
                    path,
                    f"{'/'.join(walked) or 'the top'} has no directory {step!r}",
                )
            walked.append(step)
            directory = child
        return directory

    def image(self, path: str) -> Image:
        """
        The image at `path`, such as `Map/Map/Map0/000001000.img`.

        :raises NodeNotFound: There is none.
        """
        steps = _steps(path)
        if not steps:
            raise NodeNotFound(self.data, None, path, "the path names no image")
        image, rest = self._locate(steps)
        if rest:
            raise NodeNotFound(self.data, None, path, "the path goes into the image")
        return image

    def node(self, path: str) -> Node:
        """
        The node at `path`, without following links. An image's path gives its
        root.

        :raises NodeNotFound: There is none.
        :raises CorruptArchive: The image doesn't parse.
        """
        image, steps = self._locate(_steps(path))
        node: Node = self._tree(image)
        for index, step in enumerate(steps):
            child = node.children.get(step)
            if child is None:
                raise self._missing(image, steps[:index], step)
            node = child
        return node

    def resolve(self, path: str) -> Node:
        """
        The node at `path`, following every link on the way and at the end.

        :raises NodeNotFound: The path, or a link on it, names nothing.
        :raises CorruptArchive: An image doesn't parse, or the links loop.
        """
        steps = _steps(path)
        links = 0
        while True:
            image, inner = self._locate(steps)
            node: Node = self._tree(image)
            image_steps = _steps(image.path)
            for index, step in enumerate(inner):
                child = node.children.get(step)
                if child is None:
                    raise self._missing(image, inner[:index], step)
                if isinstance(child, UolNode):
                    links += 1
                    if links > MAX_LINKS:
                        raise CorruptArchive(
                            image.archive,
                            image.name,
                            "/".join(inner[: index + 1]),
                            f"following {path!r} met more than {MAX_LINKS} links",
                        )
                    parent = image_steps + inner[:index]
                    steps = _follow(parent, child, image) + inner[index + 1 :]
                    break
                node = child
            else:
                return node

    def _tree(self, image: Image) -> PropertyNode:
        tree = self._trees.get(image.path)
        if tree is None:
            tree = image.parse()
            self._trees[image.path] = tree
            if len(self._trees) > CACHED_TREES:
                self._trees.popitem(last=False)
        else:
            self._trees.move_to_end(image.path)
        return tree

    def _locate(self, steps: list[str]) -> tuple[Image, list[str]]:
        """The image a path goes through, and the steps inside it."""
        directory = self.root
        for index, step in enumerate(steps):
            image = directory.images.get(step)
            if image is not None:
                return image, steps[index + 1 :]
            child = directory.directories.get(step)
            if child is None:
                raise NodeNotFound(
                    self.data,
                    None,
                    "/".join(steps),
                    f"{directory.path or 'the top'} has no directory or image {step!r}",
                )
            directory = child
        raise NodeNotFound(self.data, None, "/".join(steps), "the path names no image")

    def _missing(self, image: Image, parent: list[str], step: str) -> NodeNotFound:
        where = "/".join(parent)
        return NodeNotFound(
            image.archive,
            image.name,
            f"{where}/{step}" if where else step,
            f"{where or 'the root'} has no child {step!r}",
        )

    def _trees_in(self, folder: Path) -> dict[str, Directory]:
        """The trees directly under `Data`: the sub-folders with a stub."""
        trees: dict[str, Directory] = {}
        for child in sorted(folder.iterdir()):
            if child.is_dir() and (child / f"{child.name}.wz").is_file():
                trees[child.name] = self._tree_directory(child, child.name)
        return trees

    def _tree_directory(self, folder: Path, path: str) -> Directory:
        return Directory(
            folder.name,
            path,
            lambda: self._overlay(path, *self._read_tree(folder, path)),
        )

    def _read_tree(self, folder: Path, path: str) -> _Contents:
        archives = [WzArchive.open(file) for file in _tree_files(folder)]
        directories: dict[str, Directory] = {}
        listed: dict[str, list[tuple[WzArchive, WzDirectory]]] = {}
        for archive in archives:
            for name, directory in archive.root.directories.items():
                listed.setdefault(name, []).append((archive, directory))
        for name, parts in listed.items():
            sub_folder = folder / name
            if (sub_folder / f"{name}.wz").is_file():
                for archive, directory in parts:
                    if directory.directories or directory.images:
                        raise CorruptArchive(
                            archive.path,
                            None,
                            name,
                            f"the directory has entries, but {sub_folder} is its tree",
                        )
                directories[name] = self._tree_directory(sub_folder, f"{path}/{name}")
            else:
                directories[name] = self._inner_directory(name, f"{path}/{name}", parts)
        images = _merge_images(path, [(a, a.root) for a in archives])
        _check_disjoint(archives[0].path, directories, images)
        return directories, images

    def _inner_directory(
        self, name: str, path: str, parts: list[tuple[WzArchive, WzDirectory]]
    ) -> Directory:
        def load() -> _Contents:
            listed: dict[str, list[tuple[WzArchive, WzDirectory]]] = {}
            for archive, directory in parts:
                for child_name, child in directory.directories.items():
                    listed.setdefault(child_name, []).append((archive, child))
            directories = {
                child_name: self._inner_directory(
                    child_name, f"{path}/{child_name}", children
                )
                for child_name, children in listed.items()
            }
            images = _merge_images(path, parts)
            _check_disjoint(parts[0][0].path, directories, images)
            return self._overlay(path, directories, images)

        return Directory(name, path, load)

    def _pack_directory(self, name: str, path: str) -> Directory:
        """A directory that only packs have."""
        return Directory(name, path, lambda: self._overlay(path, {}, {}))

    def _overlay(
        self, path: str, directories: dict[str, Directory], images: dict[str, Image]
    ) -> _Contents:
        """A directory's contents from its archives, with its packs' added."""
        packs = self._pack_index()
        added = packs.images.get(path, {})
        for name, image in added.items():
            existing = images.get(name)
            if existing is not None:
                raise CorruptArchive(
                    image.archive,
                    image.path,
                    None,
                    f"the image is also in {existing.archive}",
                )
            images[name] = image
        for name in sorted(packs.directories.get(path, set()) - directories.keys()):
            directories[name] = self._pack_directory(name, _join(path, name))
        if added or path in packs.directories:
            _check_disjoint(self.data / PACKS, directories, images)
        return directories, images

    def _pack_index(self) -> _PackIndex:
        if self._packs is None:
            self._packs = _read_packs(self.data / PACKS)
        return self._packs


def _read_packs(folder: Path) -> _PackIndex:
    """Every pack in `folder`, indexed by directory. No folder: no packs."""
    index = _PackIndex()
    if not folder.is_dir():
        return index
    seen: dict[str, Path] = {}
    for file in sorted(folder.glob(f"*{_PACK_SUFFIX}")):
        pack = MsPack.open(file)
        for entry in pack.entries:
            steps = entry.name.split("/")
            if not all(steps):
                raise CorruptArchive(
                    file, entry.name, None, "the entry's path has an empty step"
                )
            if entry.name in seen:
                raise CorruptArchive(
                    file, entry.name, None, f"the entry is also in {seen[entry.name]}"
                )
            seen[entry.name] = file
            if not entry.name.endswith(_IMAGE_SUFFIX):
                index.skipped.append(entry.name)
                continue
            parent = "/".join(steps[:-1])
            index.images.setdefault(parent, {})[steps[-1]] = Image(
                entry.name, pack, entry
            )
            for depth in range(len(steps) - 1):
                index.directories.setdefault("/".join(steps[:depth]), set()).add(
                    steps[depth]
                )
    return index


def _join(path: str, name: str) -> str:
    return f"{path}/{name}" if path else name


def _tree_files(folder: Path) -> list[Path]:
    """A tree's stub, then its parts, as its `.ini` lists them."""
    stub = folder / f"{folder.name}.wz"
    ini = folder / f"{folder.name}.ini"
    if not ini.is_file():
        return [stub]
    last = _last_part(ini)
    parts = [folder / f"{folder.name}_{index:03d}.wz" for index in range(last + 1)]
    for part in parts:
        if not part.is_file():
            raise CorruptArchive(
                ini, None, None, f"it lists {part.name}, which doesn't exist"
            )
    return [stub, *parts]


def _last_part(ini: Path) -> int:
    values: dict[str, str] = {}
    for line in ini.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition("|")
        if not separator:
            raise CorruptArchive(ini, None, None, f"unknown line {line!r}")
        values[key.strip()] = value.strip()
    if _INI_KEY not in values:
        raise CorruptArchive(ini, None, None, f"it has no {_INI_KEY}")
    try:
        last = int(values[_INI_KEY])
    except ValueError:
        raise CorruptArchive(
            ini, None, None, f"{_INI_KEY} is {values[_INI_KEY]!r}, not a number"
        ) from None
    if last < -1:
        raise CorruptArchive(ini, None, None, f"{_INI_KEY} is {last}")
    return last


def _merge_images(
    path: str, parts: list[tuple[WzArchive, WzDirectory]]
) -> dict[str, Image]:
    images: dict[str, Image] = {}
    for archive, directory in parts:
        for name, entry in directory.images.items():
            if name in images:
                raise CorruptArchive(
                    archive.path,
                    name,
                    None,
                    f"the image is also in {images[name].archive.name}",
                )
            images[name] = Image(f"{path}/{name}" if path else name, archive, entry)
    return images


def _check_disjoint(
    archive: Path, directories: Mapping[str, Directory], images: Mapping[str, Image]
) -> None:
    clash = sorted(directories.keys() & images.keys())
    if clash:
        raise CorruptArchive(
            archive, None, clash[0], "the name is both a directory and an image"
        )


def _steps(path: str) -> list[str]:
    return [step for step in path.split("/") if step]


def _follow(parent: list[str], link: UolNode, image: Image) -> list[str]:
    """The full path a link names, from the top of the namespace."""
    target = list(parent)
    for step in link.path.split("/"):
        if step in ("", "."):
            continue
        if step == "..":
            if not target:
                raise NodeNotFound(
                    image.archive,
                    image.name,
                    "/".join([*parent[len(_steps(image.path)) :], link.name]),
                    f"the link {link.path!r} climbs above the top",
                )
            target.pop()
        else:
            target.append(step)
    return target
