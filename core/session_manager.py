

class SessionManager:
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        import ctypes
        from ctypes import wintypes

        # Define necessary structures
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", wintypes.DWORD),
                ("ki", KEYBDINPUT)
            ]

        # Define constants
        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002

        # Define SendInput function
        SendInput = ctypes.windll.user32.SendInput
        SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        SendInput.restype = wintypes.UINT

        # Function to release all keys
        def release_all_keys():
            for i in range(256):  # Iterate over all keys (0-255)
                # Create INPUT structure for key up event
                inp = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=i, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0))

                # Call SendInput to send event
                SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

        # Test the function
        release_all_keys()
