"""
`maple.menus` against a fake client: it draws the Game Menu, the Options window
and the resolution list from synthetic sprites, the way the client places them
(centred, so they move with the client's size), and reacts only to inputs that
land where the real ones would. At 2560x1440 it draws them at half that size and
doubles each pixel, as the real client does (#412).
"""

from dataclasses import dataclass, field

import numpy as np
import pytest

from botting.screen import Frame
from game_data.sprites import Sprite
from maple import menus
from maple.screen.sprites import GAUGE_LABEL, ReaderSprites

RNG = np.random.default_rng(352)
LT = (131, 59)
RB = (357, 77)
WINDOW_W, WINDOW_H = 375, 495
PITCH = 16


def _sprite(path: str, w: int, h: int, origin: tuple[int, int] = (0, 0)) -> Sprite:
    rgba = RNG.integers(0, 256, (h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    return Sprite(path, rgba, origin)


def _canvases() -> dict[str, Sprite]:
    found = {
        GAUGE_LABEL: _sprite(GAUGE_LABEL, 30, 10),
        menus.MENU_TITLE: _sprite(menus.MENU_TITLE, 58, 9, (-9, -7)),
        menus.CONFIRM: _sprite(menus.CONFIRM, 65, 19, (-234, -469)),
    }
    for path in menus.GAME_OPTION_STATES:
        found[path] = _sprite(path, 81, 25, (-6, -76))
    for i in range(menus.TAB_COUNT):
        found[menus.TABS_ENABLED[i]] = _sprite(
            menus.TABS_ENABLED[i], 71, 21, (-10 - 71 * i, -24)
        )
        found[menus.TABS_DISABLED[i]] = _sprite(
            menus.TABS_DISABLED[i], 71, 20, (-10 - 71 * i, -25)
        )
    for path in menus.KEY_BINDINGS_TABS:
        found[path] = _sprite(path, 110, 21)
    return found


SPRITES = ReaderSprites(
    "test",
    _canvases(),
    {menus.RESOLUTION_LT: LT, menus.RESOLUTION_RB: RB},
)


def _box(path: str, point: tuple[int, int]) -> tuple[int, int, int, int]:
    sprite = SPRITES.canvas(path)
    x = point[0] - sprite.origin[0]
    y = point[1] - sprite.origin[1]
    h, w = sprite.rgba.shape[:2]
    return x, y, x + w, y + h


def _inside(box: tuple[int, int, int, int], x: int, y: int) -> bool:
    return box[0] <= x < box[2] and box[1] <= y < box[3]


DOUBLED = {(2560, 1440): 2}
"""The sizes the real client draws at half size and doubles each pixel of."""

OFF_SCREEN = (
    "client rectangle (0, 200, 1920, 1400) isn't entirely on the primary monitor"
)


@dataclass
class FakeClient:
    """
    The client's menus as a little state machine. Escape closes the list and the
    Options window together, as the real one does.
    """

    current: tuple[int, int] = (1024, 768)
    menu: bool = False
    tab: int | None = None  # the Options window's selected tab, when it is open
    listed: bool = False
    chosen: int | None = None
    key_bindings: bool = False
    ignore_clicks_on_combo: bool = False
    escape_closes: bool = True
    highlight: int | None = None  # the list's highlighted row, if not the size's
    status_bar: bool = True
    off_screen_after_resize: bool = False  # until `fit` moves it back
    off_screen: bool = False
    fits: int = 0
    inputs: list[tuple] = field(default_factory=list)

    @property
    def scale(self) -> int:
        return DOUBLED.get(self.current, 1)

    @property
    def drawn(self) -> tuple[int, int]:
        """The size the client draws at, before doubling its pixels."""
        return self.current[0] // self.scale, self.current[1] // self.scale

    @property
    def window(self) -> tuple[int, int]:
        return (self.drawn[0] - WINDOW_W) // 2, (self.drawn[1] - WINDOW_H) // 2

    @property
    def menu_point(self) -> tuple[int, int]:
        return self.drawn[0] - 300, self.drawn[1] - 250

    @property
    def open(self) -> bool:
        return self.menu or self.tab is not None

    def size(self) -> tuple[int, int]:
        return self.current

    def fit(self) -> None:
        self.fits += 1
        self.off_screen = False

    def resize(self, size: tuple[int, int]) -> None:
        self.current = size
        self.off_screen = self.off_screen_after_resize

    def grab(self) -> Frame:
        if self.off_screen:
            blank = np.zeros((self.current[1], self.current[0], 3), np.uint8)
            return Frame(blank, self.current, 1.0, False, False, OFF_SCREEN)
        pixels = np.full((self.drawn[1], self.drawn[0], 3), 40, dtype=np.uint8)
        if self.status_bar:
            self._paste(pixels, GAUGE_LABEL, (10, self.drawn[1] - 20))
        if self.menu:
            self._paste(pixels, menus.MENU_TITLE, self.menu_point)
            self._paste(pixels, menus.GAME_OPTION_STATES[1], self.menu_point)
        if self.tab is not None:
            for i in range(menus.TAB_COUNT):
                tabs = menus.TABS_ENABLED if i == self.tab else menus.TABS_DISABLED
                self._paste(pixels, tabs[i], self.window)
            self._paste(pixels, menus.CONFIRM, self.window)
        if self.listed:
            self._draw_list(pixels)
        if self.key_bindings:
            self._paste(pixels, menus.KEY_BINDINGS_TABS[0], (50, 50))
        pixels = pixels.repeat(self.scale, axis=0).repeat(self.scale, axis=1)
        return Frame(pixels, self.current, 1.0, True, True)

    def _paste(self, pixels: np.ndarray, path: str, point: tuple[int, int]) -> None:
        left, top, right, bottom = _box(path, point)
        pixels[top:bottom, left:right] = SPRITES.canvas(path).rgba[:, :, 2::-1]

    def _draw_list(self, pixels: np.ndarray) -> None:
        x, y = self.window
        top = y + RB[1] - 1
        left, right = x + LT[0] + 1, x + RB[0] - 4
        pixels[top : top + menus.LIST_ROWS * PITCH - 1, left:right] = menus.LIST_BACK
        highlight = self.highlight
        if highlight is None and self.current in menus.WINDOWED_SIZES:
            highlight = menus.WINDOWED_SIZES.index(self.current)
        if highlight is not None:
            row = top + highlight * PITCH
            pixels[row : row + PITCH - 1, left:right] = menus.LIST_FOCUSED

    def press(self, key: str) -> None:
        self.inputs.append(("press", key))
        assert key == "escape"
        if not self.escape_closes:
            return
        if self.tab is not None:
            self.tab, self.listed = None, False
        elif self.menu:
            self.menu = False
        else:
            self.menu = True

    def click(self, x: int, y: int) -> None:
        self.inputs.append(("click", x, y))
        x, y = x // self.scale, y // self.scale
        if self.menu and _inside(
            _box(menus.GAME_OPTION_STATES[0], self.menu_point), x, y
        ):
            self.menu, self.tab = False, 2  # Options opens on the Game tab
            return
        if self.tab is None:
            return
        wx, wy = self.window
        if self.listed:
            row = (y - (wy + RB[1] - 1)) // PITCH
            if wx + LT[0] <= x < wx + RB[0] and 0 <= row < menus.LIST_ROWS:
                self.chosen, self.listed = row, False
            return
        for i in range(menus.TAB_COUNT):
            if _inside(_box(menus.TABS_DISABLED[i], self.window), x, y):
                self.tab = i
                return
        combo = (wx + LT[0], wy + LT[1], wx + RB[0], wy + RB[1])
        if self.tab == 0 and _inside(combo, x, y) and not self.ignore_clicks_on_combo:
            self.listed = True
        elif (
            _inside(_box(menus.CONFIRM, self.window), x, y) and self.chosen is not None
        ):
            self.resize(menus.WINDOWED_SIZES[self.chosen])

    def wait(self, seconds: float) -> None:
        del seconds


@pytest.fixture(autouse=True)
def _short_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing step polls a few frames, not seconds' worth."""
    monkeypatch.setattr(menus, "STEP_TIMEOUT", 3 * menus.POLL)
    monkeypatch.setattr(menus, "RESIZE_TIMEOUT", 3 * menus.POLL)


def test_it_sets_the_size_and_closes_the_menus() -> None:
    client = FakeClient((1920, 1080))

    before = menus.set_resolution(client, SPRITES, (800, 600))

    assert before == (1920, 1080)
    assert client.current == (800, 600)
    assert not client.open
    assert client.inputs[0] == ("press", "escape")


@pytest.mark.parametrize("start", [(800, 600), (1024, 768), (1366, 768), (1920, 1080)])
def test_positions_follow_the_client_size(start: tuple[int, int]) -> None:
    client = FakeClient(start)

    menus.set_resolution(client, SPRITES, (1280, 720))

    assert client.current == (1280, 720)
    assert not client.open


def test_a_client_that_doubles_its_pixels_is_driven_at_half_size() -> None:
    client = FakeClient((2560, 1440))

    before = menus.set_resolution(client, SPRITES, (1920, 1080))

    assert before == (2560, 1440)
    assert client.current == (1920, 1080)
    assert not client.open


def test_menus_left_open_at_the_doubled_size_are_closed() -> None:
    client = FakeClient((1920, 1080))

    menus.set_resolution(client, SPRITES, (2560, 1440))

    # The fake keeps the Options window open after Confirm, now pixel-doubled.
    assert client.current == (2560, 1440)
    assert not client.open
    assert client.inputs[-1] == ("press", "escape")


def test_closing_finds_a_doubled_menu() -> None:
    client = FakeClient((2560, 1440), menu=True)

    menus.close_menus(client, SPRITES)

    assert not client.open
    assert client.inputs == [("press", "escape")]


def test_start_says_why_the_frame_cannot_be_read() -> None:
    client = FakeClient(status_bar=False)

    with pytest.raises(menus.MenuError) as raised:
        menus.set_resolution(client, SPRITES, (800, 600))

    assert raised.value.step == "start"
    assert "gauge label isn't drawn at 1:1 or 2:1" in raised.value.detail
    assert client.inputs == []


def test_a_resize_that_puts_the_client_off_the_screen_is_fitted_back() -> None:
    client = FakeClient((1920, 1080), off_screen_after_resize=True)

    menus.set_resolution(client, SPRITES, (1920, 1200))

    assert client.current == (1920, 1200)
    assert client.fits == 1
    assert not client.off_screen
    assert not client.open


def test_an_unconfirmed_size_names_the_size_the_client_is() -> None:
    client = FakeClient((1024, 768))
    client.resize = lambda size: None  # type: ignore[method-assign]

    with pytest.raises(menus.MenuError) as raised:
        menus.set_resolution(client, SPRITES, (800, 600))

    assert raised.value.step == "confirm"
    assert "it is 1024x768" in raised.value.detail
    assert client.fits == 1
    assert not client.open


def test_an_open_game_menu_is_used_without_pressing_escape() -> None:
    client = FakeClient(menu=True)

    menus.set_resolution(client, SPRITES, (1024, 768))

    assert client.inputs[0][0] == "click"
    assert client.current == (1024, 768)


def test_an_open_options_window_is_used() -> None:
    client = FakeClient(tab=0)

    menus.set_resolution(client, SPRITES, (1024, 768))

    assert ("press", "escape") not in client.inputs[:1]
    assert client.current == (1024, 768)


def test_the_key_bindings_window_is_refused_before_any_input() -> None:
    client = FakeClient(key_bindings=True)

    with pytest.raises(menus.MenuError, match="Key Bindings"):
        menus.set_resolution(client, SPRITES, (800, 600))

    assert client.inputs == []


def test_a_step_that_fails_names_itself_and_closes_the_menus() -> None:
    client = FakeClient(ignore_clicks_on_combo=True)

    with pytest.raises(menus.MenuError) as raised:
        menus.set_resolution(client, SPRITES, (800, 600))

    assert raised.value.step == "open the resolution list"
    assert not client.open
    assert client.inputs[-1] == ("press", "escape")
    assert client.current == (1024, 768)


def test_any_other_failure_also_closes_the_menus() -> None:
    client = FakeClient()
    clicks = 0
    real_click = client.click

    def click_then_fail(x: int, y: int) -> None:
        nonlocal clicks
        real_click(x, y)
        clicks += 1
        if clicks == 2:  # the Graphics tab: the Options window is open
            raise RuntimeError("the input layer failed")

    client.click = click_then_fail  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        menus.set_resolution(client, SPRITES, (800, 600))

    assert not client.open


def test_a_list_whose_highlight_is_not_the_client_size_is_refused() -> None:
    client = FakeClient((1024, 768), highlight=2)  # 1280x720's row

    with pytest.raises(menus.MenuError, match="highlighted"):
        menus.set_resolution(client, SPRITES, (800, 600))

    assert not client.open
    assert client.current == (1024, 768)


@pytest.mark.parametrize("size", [(640, 480), (1920, 1081)])
def test_a_size_the_list_lacks_is_refused_before_any_input(
    size: tuple[int, int],
) -> None:
    client = FakeClient()

    with pytest.raises(ValueError, match="windowed size"):
        menus.set_resolution(client, SPRITES, size)

    assert client.inputs == []


def test_closing_sends_nothing_when_nothing_is_open() -> None:
    client = FakeClient()

    menus.close_menus(client, SPRITES)

    assert client.inputs == []


def test_closing_gives_up_after_the_cap_of_escapes() -> None:
    client = FakeClient((640, 480), menu=True, escape_closes=False)

    with pytest.raises(menus.MenuError, match="still open"):
        menus.close_menus(client, SPRITES)

    assert client.inputs == [("press", "escape")] * menus.MAX_ESCAPES


def test_the_list_pitch_is_its_height_over_its_rows() -> None:
    pixels = np.full((900, 600, 3), 40, dtype=np.uint8)
    combo = menus.Combo(100, 50, 326, 68)
    pitch = 20
    top = 67
    pixels[top : top + menus.LIST_ROWS * pitch, 101:300] = menus.LIST_BACK
    pixels[top + 3 * pitch : top + 4 * pitch - 1, 101:300] = menus.LIST_FOCUSED
    frame = Frame(pixels, (600, 900), 1.0, True, True)

    found = menus.find_list(frame, combo)

    assert found == menus.DropdownList(top, pitch, 3)
    assert found is not None
    assert found.row_centre_y(5) == top + 5 * pitch + pitch // 2


def test_a_list_of_the_wrong_length_is_not_the_list() -> None:
    pixels = np.full((900, 600, 3), 40, dtype=np.uint8)
    combo = menus.Combo(100, 50, 326, 68)
    pixels[67 : 67 + 10 * 16, 101:300] = menus.LIST_BACK
    frame = Frame(pixels, (600, 900), 1.0, True, True)

    assert menus.find_list(frame, combo) is None


@pytest.mark.client_files
def test_the_declared_sprites_and_list_colours_are_the_clients() -> None:
    from game_data.sprites import Sprites
    from maple.screen.sprites import Profile, load_reader_sprites

    load_reader_sprites(list(menus.DECLARATIONS), Profile(job=""))

    def bgr(argb: int) -> tuple[int, int, int]:
        argb &= 0xFFFFFFFF
        return argb & 0xFF, (argb >> 8) & 0xFF, (argb >> 16) & 0xFF

    with Sprites.latest() as sprites:
        combo = sprites._node("UI/Options.img/graphic/combo:resolution")  # pyright: ignore[reportPrivateUsage]
        assert bgr(combo.integer("backColor")) == menus.LIST_BACK
        assert bgr(combo.integer("backFocusedColor")) == menus.LIST_FOCUSED
