"""
To be able to insert a hook, it looks like I would need to code the callback function in C++/C and then compile it into a DLL.
"""
import ctypes
from ctypes import wintypes
import os

handle = 0x000206B0
lib = ctypes.cdll.LoadLibrary('../utilities/test.dll')

WH_GETMESSAGE = 3


GetMsgProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)(my_package.my_function)
dwThreadId = 0x00005624
hHook = ctypes.windll.user32.SetWindowsHookExA(WH_GETMESSAGE, GetMsgProc, hex(lib._handle), dwThreadId)
if not hHook:
    raise ctypes.WinError(ctypes.get_last_error())
#
msg = wintypes.MSG()
while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
    ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
    ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))