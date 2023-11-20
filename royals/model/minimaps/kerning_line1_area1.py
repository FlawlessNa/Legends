from functools import cached_property

from royals.interface import Minimap
from botting.utilities import Box


class KerningLine1Area1(Minimap):
    @property
    def features(self) -> dict[str, Box]:
        return super().features

    @cached_property
    def bottom_platform(self) -> Box:
        return Box(left=19, right=237, top=56, bottom=57, name="bottom_platform")

    @cached_property
    def fourth_wagon(self) -> Box:
        return Box(left=215, right=227, top=52, bottom=53, name="fourth_wagon")

    @cached_property
    def third_wagon(self) -> Box:
        return Box(left=172, right=184, top=52, bottom=53, name="third_wagon")

    @cached_property
    def second_wagon(self) -> Box:
        return Box(left=99, right=112, top=52, bottom=53, name="second_wagon")

    @cached_property
    def first_wagon(self) -> Box:
        return Box(left=49, right=62, top=52, bottom=53, name="first_wagon")

    @cached_property
    def first_ladder_bot_to_main(self) -> Box:
        return Box(
            left=31, right=32, top=48, bottom=55, name="first_ladder_bot_to_main"
        )

    @cached_property
    def second_ladder_bot_to_main(self) -> Box:
        return Box(
            left=97, right=98, top=48, bottom=56, name="second_ladder_bot_to_main"
        )

    @cached_property
    def third_ladder_bot_to_main(self) -> Box:
        return Box(
            left=126, right=127, top=48, bottom=56, name="third_ladder_bot_to_main"
        )

    @cached_property
    def fourth_ladder_bot_to_main(self) -> Box:
        return Box(
            left=161, right=162, top=48, bottom=56, name="fifth_ladder_bot_to_main"
        )

    @cached_property
    def fifth_ladder_bot_to_main(self) -> Box:
        return Box(
            left=198, right=199, top=48, bottom=56, name="fifth_ladder_bot_to_main"
        )

    @cached_property
    def main_platform(self) -> Box:
        return Box(left=19, right=237, top=48, bottom=49, name="main_platform")

    @cached_property
    def platform_1(self) -> Box:
        return Box(left=45, right=92, top=25, bottom=26, name="platform_1")

    @cached_property
    def platform_1_right_ladder(self) -> Box:
        return Box(left=86, right=87, top=26, bottom=37, name="platform_1_right_ladder")

    @cached_property
    def platform_1_left_ladder(self) -> Box:
        return Box(left=55, right=56, top=26, bottom=34, name="platform_1_left_ladder")

    @cached_property
    def platform_2(self) -> Box:
        return Box(left=101, right=131, top=29, bottom=30, name="platform_2")

    @cached_property
    def platform_2_ladder(self) -> Box:
        return Box(left=117, right=118, top=29, bottom=40, name="platform_2_ladder")

    @cached_property
    def platform_3(self) -> Box:
        return Box(left=135, right=154, top=33, bottom=34, name="platform_3")

    @cached_property
    def platform_4(self) -> Box:
        return Box(left=152, right=177, top=25, bottom=26, name="platform_4")

    @cached_property
    def platform_4_right_ladder(self) -> Box:
        return Box(
            left=174, right=175, top=25, bottom=36, name="platform_4_right_ladder"
        )

    @cached_property
    def platform_4_left_ladder(self) -> Box:
        return Box(
            left=157, right=158, top=26, bottom=39, name="platform_4_left_ladder"
        )

    @cached_property
    def platform_5(self) -> Box:
        return Box(left=180, right=205, top=25, bottom=26, name="platform_5")

    @cached_property
    def platform_5_ladder(self) -> Box:
        return Box(left=198, right=199, top=25, bottom=39, name="platform_5_ladder")

    @cached_property
    def safe_spot_right(self) -> Box:
        return Box(left=214, right=221, top=29, bottom=30, name="safe_spot_right")

    @cached_property
    def safe_spot_right_ladder(self) -> Box:
        return Box(
            left=217, right=218, top=29, bottom=40, name="safe_spot_right_ladder"
        )

    @cached_property
    def platform_6(self) -> Box:
        return Box(left=29, right=54, top=32, bottom=34, name="platform_6")

    @cached_property
    def platform_6_ladder(self) -> Box:
        return Box(left=47, right=48, top=33, bottom=40, name="platform_6_ladder")

    @cached_property
    def platform_7(self) -> Box:
        return Box(left=34, right=64, top=40, bottom=41, name="platform_7")

    @cached_property
    def platform_7_ladder(self) -> Box:
        return Box(left=55, right=56, top=40, bottom=48, name="platform_7_ladder")

    @cached_property
    def platform_8_ladder(self) -> Box:
        return Box(left=87, right=88, top=37, bottom=46, name="platform_8_ladder")

    @cached_property
    def platform_8(self) -> Box:
        return Box(left=73, right=109, top=37, bottom=38, name="platform_8")

    @cached_property
    def platform_9(self) -> Box:
        return Box(left=118, right=171, top=40, bottom=41, name="platform_9")

    @cached_property
    def platform_9_right_ladder(self) -> Box:
        return Box(
            left=168, right=169, top=40, bottom=47, name="platform_9_right_ladder"
        )

    @cached_property
    def platform_9_left_ladder(self) -> Box:
        return Box(
            left=140, right=141, top=40, bottom=49, name="platform_9_left_ladder"
        )

    @cached_property
    def safe_spot_left(self) -> Box:
        return Box(left=174, right=177, top=37, bottom=38, name="safe_spot_left")

    @cached_property
    def platform_10(self) -> Box:
        return Box(left=180, right=227, top=40, bottom=41, name="platform_10")

    @cached_property
    def platform_10_ladder(self) -> Box:
        return Box(left=208, right=209, top=40, bottom=48, name="platform_10_ladder")
