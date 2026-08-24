import pytest

from botting.utilities import Box


@pytest.fixture
def box() -> Box:
    return Box(left=0, right=10, top=0, bottom=10, name="box1", config="test")


@pytest.fixture
def box2() -> Box:
    return Box(left=0, right=20, top=0, bottom=30, name="box2")


@pytest.fixture
def box_offset() -> Box:
    return Box(left=0, right=10, top=0, bottom=10, relative=True, config="test2")


@pytest.fixture
def box_offset2() -> Box:
    return Box(left=-10, right=10, top=-10, bottom=10, relative=True)


@pytest.fixture
def box_offset3() -> Box:
    return Box(left=10, right=-10, top=10, bottom=-10, relative=True)


def test___post_init__(box2, box_offset):
    with pytest.raises(AssertionError):
        Box(left=10, right=0, top=0, bottom=10)
    with pytest.raises(AssertionError):
        Box(left=0, right=10, top=10, bottom=0)

    test = box2 + box_offset
    assert test.left == 0
    assert test.right == 30
    assert test.top == 0
    assert test.bottom == 40
    assert test.name == "box2"
    assert test.config == "test2"


def test___add__(box, box2, box_offset):
    with pytest.raises(TypeError):
        box + 1
    with pytest.raises(ValueError):
        box + box2
    with pytest.raises(ValueError):
        box + box_offset


def test___getitem__(box, box_offset):
    assert box["left"] == 0
    assert box["right"] == 10
    assert box["top"] == 0
    assert box["bottom"] == 10
    assert box["name"] == "box1"
    assert box["offset"] is False
    assert box["config"] == "test"
    assert box_offset["offset"] is True
    with pytest.raises(AttributeError):
        print(box["wrong_key"])


def test___contains__(box, box2):
    wrong_arg = (0, 0, 0)
    with pytest.raises(ValueError):
        # noinspection PyTypeChecker
        print(wrong_arg in box)

    assert (0, 0) in box
    assert (10, 10) in box
    assert (5, 5) in box
    assert (-1, 0) not in box
    assert (0, -1) not in box
    assert (11, 0) not in box
    assert (0, 11) not in box
    assert (11, 11) not in box
    assert (0.5, 12.5) in box2


def test_width(box, box2, box_offset, box_offset2, box_offset3):
    assert box.width == 10
    assert box2.width == 20
    assert box_offset.width == 10
    assert box_offset2.width == 20
    assert box_offset3.width == -20


def test_height(box, box2, box_offset, box_offset2, box_offset3):
    assert box.height == 10
    assert box2.height == 30
    assert box_offset.height == 10
    assert box_offset2.height == 20
    assert box_offset3.height == -20


def test_xrange(box, box2, box_offset, box_offset2, box_offset3):
    assert box.xrange == (0, 10)
    assert box2.xrange == (0, 20)
    assert box_offset.xrange == (0, 10)
    assert box_offset2.xrange == (-10, 10)
    assert box_offset3.xrange == (10, -10)


def test_yrange(box, box2, box_offset, box_offset2, box_offset3):
    assert box.yrange == (0, 10)
    assert box2.yrange == (0, 30)
    assert box_offset.yrange == (0, 10)
    assert box_offset2.yrange == (-10, 10)
    assert box_offset3.yrange == (10, -10)


def test_area(box, box2, box_offset, box_offset2, box_offset3):
    assert box.area == 100
    assert box2.area == 600
    assert box_offset.area == 100
    assert box_offset2.area == 400
    assert box_offset3.area == 400


def test_center(box, box2, box_offset, box_offset2, box_offset3):
    assert box.center == (5, 5)
    assert box2.center == (10, 15)
    assert box_offset.center == (5, 5)
    assert box_offset2.center == (0, 0)
    assert box_offset3.center == (0, 0)


def test_random(box, box2, box_offset, box_offset2, box_offset3):
    for i in range(1000):
        x, y = box.random()
        assert x in range(0, 10 + 1)
        assert y in range(0, 10 + 1)

        x, y = box2.random()
        assert x in range(0, 20 + 1)
        assert y in range(0, 30 + 1)

        x, y = box_offset.random()
        assert x in range(0, 10 + 1)
        assert y in range(0, 10 + 1)

        x, y = box_offset2.random()
        assert x in range(-10, 10 + 1)
        assert y in range(-10, 10 + 1)

        with pytest.raises(ValueError):
            x, y = box_offset3.random()
