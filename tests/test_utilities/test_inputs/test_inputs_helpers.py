import ctypes
import string
import win32gui

from unittest import TestCase
from royals.core.controls.inputs.inputs_helpers import _InputsHelpers


class TestInputsHelpers(TestCase):
    HKL_NEXT = 1
    HKL_PREV = 0
    handle: int
    get_active_layout_name: callable
    layout_name: type(ctypes.create_unicode_buffer(10))
    original_layout: str
    languages: dict[str, str]
    load_new_layout: callable
    unload_layout: callable
    activate_keyboard_layout: callable

    @classmethod
    def setUpClass(cls) -> None:
        """
        We use the handle to the foreground window to get the keyboard layout (This should normally be this PyCharm window). Technically since Windows 8, the active keyboard layout is the same
        across all processes, so the handle should not matter.
        We load a bunch of keyboard layouts to test that the functions work properly with different layouts.
        """
        cls.layout_name = ctypes.create_unicode_buffer(10)
        cls.handle = win32gui.GetForegroundWindow()
        cls.inputs_helpers = _InputsHelpers(cls.handle)

        cls.activate_keyboard_layout = ctypes.windll.user32.ActivateKeyboardLayout
        cls.get_active_layout_name = ctypes.windll.user32.GetKeyboardLayoutNameW
        cls.load_new_layout = ctypes.windll.user32.LoadKeyboardLayoutW
        cls.unload_layout = ctypes.windll.user32.UnloadKeyboardLayout

        cls.get_active_layout_name(cls.layout_name)
        cls.original_layout = cls.layout_name.value
        print(f"Original keyboard layout is {cls.original_layout}.")

        cls.languages = {
            "ENG-US": "00000409",
            "ENG-UK": "00000809",
            "FRA-FR": "0000040c",
            "CAN-CMS": "00011009",
            "CAN-FR": "00001009",
        }
        for lang in cls.languages.values():
            print(f"Loading {lang} layout")
            cls.load_new_layout(lang, 0)

    @classmethod
    def tearDownClass(cls) -> None:
        """Make sure to unload the unnecessary layouts. Return the keyboard language to the original one."""
        for key, lang in cls.languages.items():
            if key == "ENG-US" or key == "CAN-CMS":
                continue
            print(f"Unloading {key} layout {lang}")
            cls.unload_layout(lang)
        while True:
            cls.activate_keyboard_layout(cls.HKL_NEXT, 0)
            cls.get_active_layout_name(cls.layout_name)
            if cls.layout_name.value == cls.original_layout:
                print(f"Keyboard layout returned to {cls.layout_name.value}.")
                break

    def test__get_virtual_key(self):
        """Goal is to test that this function returns consistent values for the same key, regardless of the keyboard language settings."""
        for _ in self.languages:
            self.activate_keyboard_layout(self.HKL_NEXT, 0)

            for c in string.ascii_letters:
                vk_sensitive = self.inputs_helpers._get_virtual_key(
                    c, True, self.inputs_helpers._keyboard_layout_handle()
                )
                self.assertEqual(
                    vk_sensitive,
                    ord(c),
                    f"Virtual key for {c} is {vk_sensitive} instead of {ord(c)}",
                )
                vk_lower = self.inputs_helpers._get_virtual_key(
                    c, False, self.inputs_helpers._keyboard_layout_handle()
                )
                self.assertEqual(
                    vk_lower,
                    ord(c.upper()),
                    f"Virtual key for {c} is {vk_lower} instead of {ord(c)}",
                )
            for c in string.digits:
                vk = self.inputs_helpers._get_virtual_key(
                    c, False, self.inputs_helpers._keyboard_layout_handle()
                )
                self.assertEqual(
                    vk, ord(c), f"Virtual key for {c} is {vk} instead of {ord(c)}"
                )
            for c in string.punctuation:
                vk = self.inputs_helpers._get_virtual_key(
                    c, True, self.inputs_helpers._keyboard_layout_handle()
                )
                self.assertEqual(
                    vk, ord(c), f"Virtual key for {c} is {vk} instead of {ord(c)}"
                )

    def test__keyboard_layout_handle(self):
        """Here we merely test that the returned value doesn't changes when we change the keyboard language settings. This is because the function is cached."""
        prev_val = self.inputs_helpers._keyboard_layout_handle(self.handle)
        for _ in self.languages:
            self.activate_keyboard_layout(self.HKL_NEXT, 0)
            new_val = self.inputs_helpers._keyboard_layout_handle(self.handle)
            self.assertEqual(
                prev_val,
                new_val,
                f"Keyboard layout handle is the same after changing keyboard language settings.",
            )
            prev_val = new_val

    def test__setup_exported_functions(self):
        results = self.inputs_helpers._setup_exported_functions()
        self.assertIsInstance(results, dict)
        self.assertEqual(len(results), 3)
        for key, val in results.items():
            self.assertIsInstance(key, str)
            self.assertTrue(
                key
                in ["MapVirtualKeyExW", "GetWindowThreadProcessId", "GetKeyboardLayout"]
            )
            self.assertTrue(callable(val))
