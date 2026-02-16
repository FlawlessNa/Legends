from unittest import TestCase

from botting.utilities import Box


class TestBox(TestCase):
    def setUp(self) -> None:
        self.box = Box(left=0, right=10, top=0, bottom=10, name="box1", config="test")
        self.box2 = Box(left=0, right=20, top=0, bottom=30, name="box2")
        self.box_offset = Box(
            left=0, right=10, top=0, bottom=10, relative=True, config="test2"
        )
        self.box_offset2 = Box(left=-10, right=10, top=-10, bottom=10, relative=True)
        self.box_offset3 = Box(left=10, right=-10, top=10, bottom=-10, relative=True)

    def test___post_init__(self):
        with self.assertRaises(AssertionError):
            Box(left=10, right=0, top=0, bottom=10)
        with self.assertRaises(AssertionError):
            Box(left=0, right=10, top=10, bottom=0)

        test = self.box2 + self.box_offset
        self.assertEqual(test.left, 0)
        self.assertEqual(test.right, 30)
        self.assertEqual(test.top, 0)
        self.assertEqual(test.bottom, 40)
        self.assertEqual(test.name, "box2")
        self.assertEqual(test.config, "test2")

    def test___add__(self):
        with self.assertRaises(TypeError):
            self.box + 1
        with self.assertRaises(ValueError):
            self.box + self.box2
        with self.assertRaises(ValueError):
            self.box + self.box_offset

    def test___getitem__(self):
        self.assertEqual(self.box["left"], 0)
        self.assertEqual(self.box["right"], 10)
        self.assertEqual(self.box["top"], 0)
        self.assertEqual(self.box["bottom"], 10)
        self.assertEqual(self.box["name"], "box1")
        self.assertEqual(self.box["offset"], False)
        self.assertEqual(self.box["config"], "test")
        self.assertEqual(self.box_offset["offset"], True)
        with self.assertRaises(AttributeError):
            print(self.box["wrong_key"])

    def test___contains__(self):
        wrong_arg = (0, 0, 0)
        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            print(wrong_arg in self.box)

        self.assertTrue((0, 0) in self.box)
        self.assertTrue((10, 10) in self.box)
        self.assertTrue((5, 5) in self.box)
        self.assertFalse((-1, 0) in self.box)
        self.assertFalse((0, -1) in self.box)
        self.assertFalse((11, 0) in self.box)
        self.assertFalse((0, 11) in self.box)
        self.assertFalse((11, 11) in self.box)
        self.assertTrue((0.5, 12.5) in self.box2)

    def test_width(self):
        self.assertEqual(self.box.width, 10)
        self.assertEqual(self.box2.width, 20)
        self.assertEqual(self.box_offset.width, 10)
        self.assertEqual(self.box_offset2.width, 20)
        self.assertEqual(self.box_offset3.width, -20)

    def test_height(self):
        self.assertEqual(self.box.height, 10)
        self.assertEqual(self.box2.height, 30)
        self.assertEqual(self.box_offset.height, 10)
        self.assertEqual(self.box_offset2.height, 20)
        self.assertEqual(self.box_offset3.height, -20)

    def test_xrange(self):
        self.assertEqual(self.box.xrange, (0, 10))
        self.assertEqual(self.box2.xrange, (0, 20))
        self.assertEqual(self.box_offset.xrange, (0, 10))
        self.assertEqual(self.box_offset2.xrange, (-10, 10))
        self.assertEqual(self.box_offset3.xrange, (10, -10))

    def test_yrange(self):
        self.assertEqual(self.box.yrange, (0, 10))
        self.assertEqual(self.box2.yrange, (0, 30))
        self.assertEqual(self.box_offset.yrange, (0, 10))
        self.assertEqual(self.box_offset2.yrange, (-10, 10))
        self.assertEqual(self.box_offset3.yrange, (10, -10))

    def test_area(self):
        self.assertEqual(self.box.area, 100)
        self.assertEqual(self.box2.area, 600)
        self.assertEqual(self.box_offset.area, 100)
        self.assertEqual(self.box_offset2.area, 400)
        self.assertEqual(self.box_offset3.area, 400)

    def test_center(self):
        self.assertEqual(self.box.center, (5, 5))
        self.assertEqual(self.box2.center, (10, 15))
        self.assertEqual(self.box_offset.center, (5, 5))
        self.assertEqual(self.box_offset2.center, (0, 0))
        self.assertEqual(self.box_offset3.center, (0, 0))

    def test_random(self):
        for i in range(1000):
            x, y = self.box.random()
            self.assertIn(x, range(0, 10 + 1))
            self.assertIn(y, range(0, 10 + 1))

            x, y = self.box2.random()
            self.assertIn(x, range(0, 20 + 1))
            self.assertIn(y, range(0, 30 + 1))

            x, y = self.box_offset.random()
            self.assertIn(x, range(0, 10 + 1))
            self.assertIn(y, range(0, 10 + 1))

            x, y = self.box_offset2.random()
            self.assertIn(x, range(-10, 10 + 1))
            self.assertIn(y, range(-10, 10 + 1))

            with self.assertRaises(ValueError):
                x, y = self.box_offset3.random()
