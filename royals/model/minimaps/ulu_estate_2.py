from royals.model.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class UluEstate2Minimap(MinimapPathingMechanics):
	map_area_width = 132
	map_area_height = 81
	minimap_speed = 8.29145728643216
	jump_height = 4.990004999999999
	jump_distance = 4.601758793969849
	teleport_h_dist = int(9.949748743718592)
	teleport_v_up_dist = int(9.949748743718592)  # TODO - Change this value (most likely decrease)
	teleport_v_down_dist = int(9.949748743718592)  # TODO - Change this value (most likely decrease)

	@property
	def central_node(self) -> tuple[int, int]:
		return 40, 56

	@property
	def feature_cycle(self) -> list[MinimapFeature]:
		bot_plat_rotation = [
			self.bottom_platform_section_1,
			self.bottom_platform_section_2,
			self.bottom_platform_section_3,
			self.bottom_platform_section_2,
		] * 5
		top_plat_rotation = [
			self.top_platform_section_1,
			self.top_platform_section_2,
			self.top_platform_section_3,
			self.top_platform_rail_2,
			self.top_platform_section_2,
			self.top_platform_rail
		] * 3
		return [*bot_plat_rotation, *top_plat_rotation]

	bottom_platform_section_1: MinimapFeature = MinimapFeature(
		left=5,
		right=45,
		top=62,
		bottom=62,
		name='bottom_platform_section_1',
	)
	bottom_platform_section_2: MinimapFeature = MinimapFeature(
		left=46,
		right=86,
		top=62,
		bottom=62,
		name='bottom_platform_section_2',
	)
	bottom_platform_section_3: MinimapFeature = MinimapFeature(
		left=87,
		right=127,
		top=62,
		bottom=62,
		name='bottom_platform_section_3',
	)
	bottom_platform_bench: MinimapFeature = MinimapFeature(
		left=22,
		right=25,
		top=60,
		bottom=60,
		name='bottom_platform_bench',
	)
	left_rope: MinimapFeature = MinimapFeature(
		left=40,
		right=40,
		top=44,
		bottom=59,
		name='left_rope',
	)
	right_rope: MinimapFeature = MinimapFeature(
		left=94,
		right=94,
		top=44,
		bottom=56,
		name='right_rope',
	)
	top_platform_section_1: MinimapFeature = MinimapFeature(
		left=5,
		right=45,
		top=43,
		bottom=43,
		name='top_platform_section_1',
	)
	top_platform_section_2: MinimapFeature = MinimapFeature(
		left=46,
		right=86,
		top=43,
		bottom=43,
		name='top_platform_section_2',
	)
	top_platform_section_3: MinimapFeature = MinimapFeature(
		left=87,
		right=127,
		top=43,
		bottom=43,
		name='top_platform_section_3',
	)
	top_platform_rail: MinimapFeature = MinimapFeature(
		left=54,
		right=65,
		top=41,
		bottom=41,
		name='top_platform_rail',
	)
	top_platform_rail_2: MinimapFeature = MinimapFeature(
		left=96,
		right=104,
		top=41,
		bottom=41,
		name='top_platform_rail_2',
	)
	top_platform_tire: MinimapFeature = MinimapFeature(
		left=88,
		right=92,
		top=41,
		bottom=41,
		name='top_platform_tire',
	)
	rope_safe_spot: MinimapFeature = MinimapFeature(
		left=68,
		right=68,
		top=25,
		bottom=38,
		name='rope_safe_spot',
	)
	safe_spot_platform: MinimapFeature = MinimapFeature(
		left=48,
		right=84,
		top=24,
		bottom=24,
		name='safe_spot_platform',
	)
	safe_spot_car_section_1: MinimapFeature = MinimapFeature(
		left=74,
		right=80,
		top=19,
		bottom=20,
		name='safe_spot_car_section_1',
		is_irregular=True,
		backward=True
	)
	safe_spot_car_section_2: MinimapFeature = MinimapFeature(
		left=81,
		right=83,
		top=19,
		bottom=21,
		name='safe_spot_car_section_2',
		is_irregular=True
	)
	safe_spot_tire_section_1: MinimapFeature = MinimapFeature(
		left=58,
		right=63,
		top=22,
		bottom=23,
		name='safe_spot_tire_section_1',
		is_irregular=True,
		backward=True
	)
	safe_spot_tire_section_2: MinimapFeature = MinimapFeature(
		left=64,
		right=67,
		top=22,
		bottom=22,
		name='safe_spot_tire_section_2',
	)
	safe_spot_bench: MinimapFeature = MinimapFeature(
		left=52,
		right=55,
		top=22,
		bottom=22,
		name='safe_spot_bench',
	)
	safe_spot_mid_spotlight: MinimapFeature = MinimapFeature(
		left=50,
		right=52,
		top=16,
		bottom=16,
		name='safe_spot_mid_spotlight',
	)
	safe_spot_spotlight_section_1: MinimapFeature = MinimapFeature(
		left=51,
		right=57,
		top=11,
		bottom=12,
		name='safe_spot_spotlight_section_1',
		is_irregular=True,
		backward=True
	)
	safe_spot_spotlight_section_2: MinimapFeature = MinimapFeature(
		left=42,
		right=52,
		top=10,
		bottom=12,
		name='safe_spot_spotlight_section_2',
		is_irregular=True,
	)
	safe_spot_topmost_light: MinimapFeature = MinimapFeature(
		left=39,
		right=48,
		top=7,
		bottom=12,
		name='safe_spot_topmost_light',
		is_irregular=True
	)
