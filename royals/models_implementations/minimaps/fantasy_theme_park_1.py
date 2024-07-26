import random
from royals.models_implementations.mechanics import (
	MinimapFeature,
	MinimapConnection,
	MinimapPathingMechanics,
)


class FantasyThemePark1Minimap(MinimapPathingMechanics):
	map_area_width = 145
	map_area_height = 111
	minimap_speed = 10

	jump_height: int = 5
	jump_distance: int = 6
	jump_down_limit = 35
	teleport_h_dist = 9
	teleport_v_up_dist = 7
	teleport_v_down_dist = 15

	@property
	def central_node(self) -> tuple[int, int]:
		return 72, 39

	@property
	def feature_cycle(self) -> list[MinimapFeature]:
		return [
			self.safe_spot,
			self.first_platform,
			self.first_platform,
			self.second_platform_upper,
			self.second_platform_slope,
			random.choice([self.second_platform_upper, self.second_platform_lower]),
			self.third_platform,
			self.third_platform,
			self.fourth_platform_upper,
			*[self.bottom_platform] * 5,
			self.rightmost_ramp,
		]

	top_left_portal_platform: MinimapFeature = MinimapFeature(
		left=8,
		right=43,
		top=22,
		bottom=22,
		name='top_left_portal_platform',
	)
	first_platform: MinimapFeature = MinimapFeature(
		left=41,
		right=99,
		top=34,
		bottom=34,
		name='first_platform',
	)
	safe_spot: MinimapFeature = MinimapFeature(
		left=104,
		right=120,
		top=34,
		bottom=34,
		name='safe_spot',
		connections=[
			MinimapConnection(
				'center_ramp',
				MinimapConnection.PORTAL,
				[(110, 34), (111, 34), (112, 34)],
				[(24, 86)]
			)
		]
	)
	second_platform_upper: MinimapFeature = MinimapFeature(
		left=47,
		right=81,
		top=49,
		bottom=49,
		name='second_platform_upper',
	)
	second_platform_slope: MinimapFeature = MinimapFeature(
		left=82,
		right=93,
		top=49,
		bottom=56,
		name='second_platform_slope',
		is_irregular=True
	)
	second_platform_lower: MinimapFeature = MinimapFeature(
		left=94,
		right=99,
		top=56,
		bottom=56,
		name='second_platform_lower',
	)
	third_platform: MinimapFeature = MinimapFeature(
		left=30,
		right=87,
		top=60,
		bottom=60,
		name='third_platform',
	)
	fourth_platform_upper: MinimapFeature = MinimapFeature(
		left=47,
		right=87,
		top=75,
		bottom=75,
		name='fourth_platform_upper',
	)
	fourth_platform_slope: MinimapFeature = MinimapFeature(
		left=88,
		right=94,
		top=75,
		bottom=79,
		name='fourth_platform_slope',
		is_irregular=True
	)
	arcade_roof_platform: MinimapFeature = MinimapFeature(
		left=73,
		right=83,
		top=80,
		bottom=80,
		name='arcade_roof_platform',
	)
	rightmost_rocks: MinimapFeature = MinimapFeature(
		left=59,
		right=65,
		top=84,
		bottom=85,
		name='rightmost_rocks',
		is_irregular=True
	)
	leftmost_rocks: MinimapFeature = MinimapFeature(
		left=45,
		right=50,
		top=83,
		bottom=84,
		name='leftmost_rocks',
		is_irregular=True
	)
	staircase_1: MinimapFeature = MinimapFeature(
		left=118,
		right=123,
		top=84,
		bottom=84,
		name='staircase_1',
	)
	staircase_2: MinimapFeature = MinimapFeature(
		left=120,
		right=125,
		top=86,
		bottom=86,
		name='staircase_2',
	)
	staircase_3: MinimapFeature = MinimapFeature(
		left=122,
		right=127,
		top=87,
		bottom=87,
		name='staircase_3',
	)
	staircase_4: MinimapFeature = MinimapFeature(
		left=123,
		right=128,
		top=89,
		bottom=89,
		name='staircase_4',
	)
	staircase_5: MinimapFeature = MinimapFeature(
		left=125,
		right=129,
		top=90,
		bottom=90,
		name='staircase_5',
	)
	bottom_platform: MinimapFeature = MinimapFeature(
		left=6,
		right=140,
		top=92,
		bottom=92,
		name='bottom_platform',
	)
	door_spot = list(bottom_platform)[40:-40]
	leftmost_ramp: MinimapFeature = MinimapFeature(
		left=9,
		right=16,
		top=86,
		bottom=86,
		name='leftmost_ramp',
	)
	stair_ramp: MinimapFeature = MinimapFeature(
		left=17,
		right=22,
		top=86,
		bottom=89,
		name='stair_ramp',
		is_irregular=True
	)
	center_ramp: MinimapFeature = MinimapFeature(
		left=23,
		right=32,
		top=86,
		bottom=86,
		name='center_ramp',
		connections=[
			MinimapConnection(
				'safe_spot',
				MinimapConnection.PORTAL,
				[(23, 86), (24, 86), (25, 86)],
				[(111, 34)]
			)
		]
	)
	rightmost_ramp: MinimapFeature = MinimapFeature(
		left=34,
		right=43,
		top=86,
		bottom=86,
		name='rightmost_ramp',
	)
	top_thrash_bin: MinimapFeature = MinimapFeature(
		left=56,
		right=59,
		top=29,
		bottom=29,
		name='top_thrash_bin',
	)
	wooden_bench: MinimapFeature = MinimapFeature(
		left=51,
		right=54,
		top=33,
		bottom=33,
		name='wooden_bench',
	)
	top_left_portal_rope: MinimapFeature = MinimapFeature(
		left=42,
		right=42,
		top=23,
		bottom=33,
		name='top_left_portal_rope',
	)
	first_platform_rope: MinimapFeature = MinimapFeature(
		left=72,
		right=72,
		top=35,
		bottom=47,
		name='first_platform_rope',
	)
	second_platform_rope: MinimapFeature = MinimapFeature(
		left=51,
		right=51,
		top=50,
		bottom=59,
		name='second_platform_rope',
	)
	third_platform_rope: MinimapFeature = MinimapFeature(
		left=79,
		right=79,
		top=61,
		bottom=73,
		name='third_platform_rope',
	)
	fourth_platform_rope: MinimapFeature = MinimapFeature(
		left=55,
		right=55,
		top=76,
		bottom=91,
		name='fourth_platform_rope',
	)
