from functools import cached_property

from .base_map import BaseMap
from botting.utilities import Box


class LudiFreeMarketTemplate(BaseMap):
    @cached_property
    def bottom_platform(self) -> Box:
        return Box(left=12, right=120, top=37, bottom=38, name="bottom_platform")

    @cached_property
    def bottom_left_portal(self) -> Box:
        return Box(left=20, right=22, top=37, bottom=38, name="bottom_left_portal")

    @cached_property
    def mid_left_portal(self) -> Box:
        return Box(left=20, right=23, top=24, bottom=25, name="mid_left_portal")

    @cached_property
    def mid_platform(self) -> Box:
        return Box(left=25, right=96, top=24, bottom=25, name="mid_platform")

    @cached_property
    def mid_right_portal(self) -> Box:
        return Box(left=99, right=101, top=24, bottom=25, name="mid_right_portal")

    @cached_property
    def top_platform_0(self) -> Box:
        return Box(left=17, right=20, top=11, bottom=12, name="top_platform_0")

    @cached_property
    def top_platform_1(self) -> Box:
        return Box(left=23, right=31, top=11, bottom=12, name="top_platform_1")

    @cached_property
    def top_platform_2(self) -> Box:
        return Box(left=33, right=42, top=11, bottom=12, name="top_platform_2")

    @cached_property
    def top_platform_3(self) -> Box:
        return Box(left=45, right=53, top=11, bottom=12, name="top_platform_3")

    @cached_property
    def top_platform_4(self) -> Box:
        return Box(left=56, right=65, top=11, bottom=12, name="top_platform_4")

    @cached_property
    def top_platform_5(self) -> Box:
        return Box(left=67, right=76, top=11, bottom=12, name="top_platform_5")

    @cached_property
    def top_platform_6(self) -> Box:
        return Box(left=79, right=87, top=11, bottom=12, name="top_platform_6")

    @cached_property
    def top_platform_7(self) -> Box:
        return Box(left=90, right=99, top=11, bottom=12, name="top_platform_7")

    @cached_property
    def top_right_portal(self) -> Box:
        return Box(left=101, right=104, top=11, bottom=12, name="top_right_portal")

    @cached_property
    def platform_5_ladder(self) -> Box:
        return Box(left=73, right=74, top=11, bottom=23, name="platform_5_ladder")

    @cached_property
    def platform_2_ladder(self) -> Box:
        return Box(left=39, right=40, top=11, bottom=23, name="platform_2_ladder")

    @cached_property
    def left_ladder(self) -> Box:
        return Box(left=33, right=34, top=24, bottom=37, name="left_ladder")

    @cached_property
    def right_ladder(self) -> Box:
        return Box(left=82, right=83, top=24, bottom=36, name="right_ladder")
