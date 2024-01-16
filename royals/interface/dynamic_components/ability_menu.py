import cv2
import numpy as np
import os
import string
from paths import ROOT
from botting.visuals import InGameDynamicVisuals
from botting.utilities import (
    Box,
    take_screenshot,
    CLIENT_VERTICAL_MARGIN_PX,
    CLIENT_HORIZONTAL_MARGIN_PX,
)


class AbilityMenu(InGameDynamicVisuals):
    """
    Implements the in-game ability menu.
    """

    _menu_icon_detection_needle: np.ndarray = cv2.imread(
        os.path.join(ROOT, "royals/assets/detection_images/ability_menu.png")
    )

    ign_box: Box = Box(
        offset=True, name="IGN", left=54, right=-5, top=26, bottom=28, config="--psm 7"
    )
    # level_box: Box = Box(offset=True, name='Level', left=37, right=125, top=45, bottom=-90, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}')
    # hp_box: Box = Box(offset=True, name='HP', left=37, right=125, top=81, bottom=-54, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}/ ')
    # add_hp_box: Box = Box(offset=True, name='AddHP', left=166, right=141, top=84, bottom=-55)
    # mp_box: Box = Box(offset=True, name='MP', left=37, right=125, top=99, bottom=-36, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}/ ')
    # add_mp_box: Box = Box(offset=True, name='AddMP', left=166, right=141, top=102, bottom=-37)
    # exp_box: Box = Box(offset=True, name='EXP', left=37, right=125, top=117, bottom=-18, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}, ')
    # fame_box: Box = Box(offset=True, name='Fame', left=37, right=125, top=135, bottom=0, config=f'--psm 7 -c tessedit_char_whitelist={string.digits},')
    str_box: Box = Box(
        offset=True,
        name="STR",
        left=54,
        right=-20,
        top=223,
        bottom=223,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}+()",
    )
    dex_box: Box = Box(
        offset=True,
        name="DEX",
        left=54,
        right=-20,
        top=242,
        bottom=242,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}+()",
    )
    int_box: Box = Box(
        offset=True,
        name="INT",
        left=54,
        right=-20,
        top=260,
        bottom=260,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}+()",
    )
    luk_box: Box = Box(
        offset=True,
        name="LUK",
        left=54,
        right=-20,
        top=278,
        bottom=278,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}+()",
    )
    add_str_box: Box = Box(
        offset=True, name="AddSTR", left=150, right=-8, top=228, bottom=222
    )
    add_dex_box: Box = Box(
        offset=True, name="AddDEX", left=150, right=-8, top=247, bottom=241
    )
    add_int_box: Box = Box(
        offset=True, name="AddINT", left=150, right=-8, top=265, bottom=259
    )
    add_luk_box: Box = Box(
        offset=True, name="AddLUK", left=150, right=-8, top=283, bottom=277
    )
    # attack_box: Box = Box(offset=True, name='Attack', left=225, right=310, top=119, bottom=-16, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}~, ')
    # weapon_def_box: Box = Box(offset=True, name='WeaponDef', left=225, right=310, top=137, bottom=2, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}+-()')
    # magic_box: Box = Box(offset=True, name='Magic', left=225, right=310, top=155, bottom=20, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}+-()')
    # magic_def_box: Box = Box(offset=True, name='MagicDef', left=225, right=310, top=173, bottom=38, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}+-()')
    # accuracy_box: Box = Box(offset=True, name='Accuracy', left=225, right=310, top=191, bottom=56, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}+-()')
    # avoidability_box: Box = Box(offset=True, name='Avoidability', left=225, right=310, top=209, bottom=74, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}+-()')
    # hand_box: Box = Box(offset=True, name='Hand', left=225, right=310, top=227, bottom=92, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}')
    # speed_box: Box = Box(offset=True, name='Speed', left=225, right=310, top=245, bottom=110, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}%')
    # jump_box: Box = Box(offset=True, name='Jump', left=225, right=310, top=263, bottom=128, config=f'--psm 7 -c tessedit_char_whitelist={string.digits}%')
    # extended_menu_button_box: Box = Box(offset=True, left=110, right=115, top=293, bottom=156)
    ability_points_box: Box = Box(
        offset=True,
        name="AP",
        left=91,
        right=-50,
        top=197,
        bottom=193,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}",
    )

    # _extended_menu_detection_path: os.PathLike = field(default=os.path.join(ROOT_DIR, 'UI/menus/icons/AbilityMenuIsExtended.png'), repr=False, init=False)
    # _extended_menu_detection_box: Box = field(default=Box(offset=True, left=185, right=200, top=100, bottom=25), repr=False, init=False)

    # @cached_property
    # def extended_section(self) -> dict:
    #     """
    #     Returns a dictionary of all the boxes in the extended section of the ability menu. These boxes are only available when the menu is extended.
    #     """
    #     return {
    #         'Attack': self.attack_box,
    #         'WeaponDef': self.weapon_def_box,
    #         'Magic': self.magic_box,
    #         'MagicDef': self.magic_def_box,
    #         'Accuracy': self.accuracy_box,
    #         'Avoidability': self.avoidability_box,
    #         'Hand': self.hand_box,
    #         'Speed': self.speed_box,
    #         'Jump': self.jump_box,
    #     }

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.resize(cv2.bitwise_not(gray), None, fx=10, fy=10)

    def is_displayed(self, handle: int, image: np.ndarray = None) -> bool:
        return True if self._menu_icon_position(handle, image) is not None else False

    def get_available_ap(self, handle: int) -> int | None:
        img = take_screenshot(handle)
        icon = self._menu_icon_position(handle, img)
        box = icon + self.ability_points_box
        cropped = img[
                  box.top-CLIENT_VERTICAL_MARGIN_PX:box.bottom-CLIENT_VERTICAL_MARGIN_PX,
                  box.left-CLIENT_HORIZONTAL_MARGIN_PX:box.right-CLIENT_HORIZONTAL_MARGIN_PX
                  ]
        try:
            return int(self.read_from_img(cropped, box.config))
        except ValueError:
            return

    @property
    def stat_mapper(self) -> dict[str, Box]:
        return {
            "STR": self.add_str_box,
            "DEX": self.add_dex_box,
            "INT": self.add_int_box,
            "LUK": self.add_luk_box,
        }
