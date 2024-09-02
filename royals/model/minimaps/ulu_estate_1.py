from royals.model.mechanics import (
    MinimapFeature,
    MinimapPathingMechanics,
)


class UluEstate1Minimap(MinimapPathingMechanics):

	map_area_width = 132
	map_area_height = 104
	minimap_speed = 8.25
	jump_height = 5.303741721854304
	jump_distance = 4.57875
	teleport_h_dist = int(9.9)  # Real number is 9.9, needs to be converted into int
	teleport_v_up_dist = int(9.9)  # TODO - Change this value (most likely decrease)
	teleport_v_down_dist = int(9.9)  # TODO - Change this value (most likely decrease)


	@property
	def feature_cycle(self) -> list[MinimapFeature]:
		pass

	@property
	def central_node(self) -> tuple[int, int]:
		return 109, 45

	spawning_platform: MinimapFeature = MinimapFeature(
		left=20,
		right=32,
		top=73,
		bottom=73,
		name='spawning_platform',
	)
	spawning_platform_tire: MinimapFeature = MinimapFeature(
		left=26,
		right=31,
		top=71,
		bottom=71,
		name='spawning_platform_tire',
	)
	bottom_platform: MinimapFeature = MinimapFeature(
		left=5,
		right=127,
		top=85,
		bottom=85,
		name='bottom_platform',
	)
	bottom_platform_rail: MinimapFeature = MinimapFeature(
		left=74,
		right=86,
		top=83,
		bottom=83,
		name='bottom_platform_rail',
	)
	bottom_platform_bench: MinimapFeature = MinimapFeature(
		left=89,
		right=92,
		top=82,
		bottom=82,
		name='bottom_platform_bench',
	)
	platform_1_section_1: MinimapFeature = MinimapFeature(
		left=17,
		right=23,
		top=83,
		bottom=83,
		name='platform_1_section_1',
	)
	platform_1_section_2: MinimapFeature = MinimapFeature(
		left=24,
		right=34,
		top=75,
		bottom=82,
		name='platform_1_section_2',
		is_irregular=True,
		backward=True
	)
	platform_1_section_3: MinimapFeature = MinimapFeature(
		left=35,
		right=58,
		top=75,
		bottom=75,
		name='platform_1_section_3',
	)
	platform_1_section_4: MinimapFeature = MinimapFeature(
		left=59,
		right=63,
		top=71,
		bottom=75,
		name='platform_1_section_4',
		is_irregular=True,
		backward=True
	)
	platform_1_section_5: MinimapFeature = MinimapFeature(
		left=64,
		right=80,
		top=71,
		bottom=71,
		name='platform_1_section_5',
	)
	platform_1_section_6: MinimapFeature = MinimapFeature(
		left=81,
		right=108,
		top=53,
		bottom=71,
		name='platform_1_section_6',
		is_irregular=True,
		backward=True
	)
	platform_1_section_7: MinimapFeature = MinimapFeature(
		left=109,
		right=120,
		top=53,
		bottom=53,
		name='platform_1_section_7',
	)
	platform_1_rope: MinimapFeature = MinimapFeature(
		left=114,
		right=114,
		top=53,
		bottom=81,
		name='platform_1_rope',
	)
	car_section_1: MinimapFeature = MinimapFeature(
		left=41,
		right=46,
		top=71,
		bottom=71,
		name='car_section_1',
		is_irregular=True,
	)
	car_section_2: MinimapFeature = MinimapFeature(
		left=47,
		right=49,
		top=71,
		bottom=73,
		name='car_section_2',
		is_irregular=True,
	)
	platform_1_box: MinimapFeature = MinimapFeature(
		left=65,
		right=69,
		top=69,
		bottom=69,
		name='platform_1_box',
	)
	platform_1_bench: MinimapFeature = MinimapFeature(
		left=70,
		right=73,
		top=69,
		bottom=69,
		name='platform_1_bench',
	)
	platform_2_section_1: MinimapFeature = MinimapFeature(
		left=86,
		right=97,
		top=56,
		bottom=56,
		name='platform_2_section_1',
	)
	platform_2_section_2: MinimapFeature = MinimapFeature(
		left=69,
		right=85,
		top=46,
		bottom=56,
		name='platform_2_section_2',
		is_irregular=True,
	)
	platform_2_section_3: MinimapFeature = MinimapFeature(
		left=57,
		right=68,
		top=45,
		bottom=45,
		name='platform_2_section_3',
	)
	platform_2_section_4: MinimapFeature = MinimapFeature(
		left=47,
		right=56,
		top=38,
		bottom=45,
		name='platform_2_section_4',
		is_irregular=True,
	)
	platform_2_section_5: MinimapFeature = MinimapFeature(
		left=17,
		right=46,
		top=38,
		bottom=38,
		name='platform_2_section_5',
	)
	platform_2_rightmost_tire_section_1: MinimapFeature = MinimapFeature(
		left=63,
		right=66,
		top=44,
		bottom=44,
		name='platform_2_rightmost_tire_section_1',
	)
	platform_2_rightmost_tire_section_2: MinimapFeature = MinimapFeature(
		left=58,
		right=62,
		top=44,
		bottom=44,
		name='platform_2_rightmost_tire_section_2',
	)
	platform_2_leftmost_tire: MinimapFeature = MinimapFeature(
		left=30,
		right=34,
		top=36,
		bottom=36,
		name='platform_2_leftmost_tire',
	)
	platform_2_bench: MinimapFeature = MinimapFeature(
		left=22,
		right=25,
		top=36,
		bottom=36,
		name='platform_2_bench',
	)
	platform_3_section_1: MinimapFeature = MinimapFeature(
		left=37,
		right=55,
		top=36,
		bottom=36,
		name='platform_3_section_1',
	)
	platform_3_section_2: MinimapFeature = MinimapFeature(
		left=56,
		right=71,
		top=25,
		bottom=35,
		name='platform_3_section_2',
		is_irregular=True,
		backward=True,
	)
	platform_3_section_3: MinimapFeature = MinimapFeature(
		left=72,
		right=127,
		top=25,
		bottom=25,
		name='platform_3_section_3',
	)
	platform_3_rail: MinimapFeature = MinimapFeature(
		left=41,
		right=52,
		top=34,
		bottom=34,
		name='platform_3_rail',
	)
	platform_3_tire_section_1: MinimapFeature = MinimapFeature(
		left=99,
		right=103,
		top=23,
		bottom=23,
		name='platform_3_tire_section_1',
	)
	platform_3_tire_section_2: MinimapFeature = MinimapFeature(
		left=104,
		right=106,
		top=23,
		bottom=23,
		name='platform_3_tire_section_2',
	)
	platform_3_box_1: MinimapFeature = MinimapFeature(
		left=119,
		right=122,
		top=22,
		bottom=22,
		name='platform_3_box_1',
	)
	platform_3_box_2: MinimapFeature = MinimapFeature(
		left=123,
		right=127,
		top=22,
		bottom=22,
		name='platform_3_box_2',
	)
	platform_3_ladder: MinimapFeature = MinimapFeature(
		left=109,
		right=109,
		top=25,
		bottom=48,
		name='platform_3_ladder',
	)
