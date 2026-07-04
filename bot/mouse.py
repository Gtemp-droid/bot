import ctypes
import ctypes.wintypes
import logging
import time
from typing import Optional, Tuple

from bot.config import BotConfig

log = logging.getLogger(__name__)

PUL = ctypes.POINTER(ctypes.c_ulong)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("mi", MOUSEINPUT)]

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


def _send_input(*inputs) -> int:
    return ctypes.windll.user32.SendInput(
        len(inputs),
        ctypes.byref(INPUT(0, inputs[0])),
        ctypes.sizeof(INPUT)
    )


def _abs_coord(x: int, y: int) -> Tuple[int, int]:
    return (x * 65535 // ctypes.windll.user32.GetSystemMetrics(0),
            y * 65535 // ctypes.windll.user32.GetSystemMetrics(1))


class MouseController:
    def __init__(self, config: BotConfig):
        self.config = config
        self._window_left: int = 0
        self._window_top: int = 0

    def set_window_offset(self, left: int, top: int):
        self._window_left = left
        self._window_top = top

    def move_to(self, x: int, y: int, duration: Optional[float] = None):
        abs_x, abs_y = _abs_coord(
            self._window_left + x,
            self._window_top + y
        )
        inp = MOUSEINPUT(abs_x, abs_y, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None)
        _send_input(inp)
        time.sleep(duration or self.config.move_duration)

    def click(self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None):
        if x is not None and y is not None:
            self.move_to(x, y)
        if button == "left":
            down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        else:
            down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        inp_down = MOUSEINPUT(0, 0, 0, down, 0, None)
        inp_up = MOUSEINPUT(0, 0, 0, up, 0, None)
        _send_input(inp_down)
        time.sleep(0.05)
        _send_input(inp_up)

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None):
        self.click(x=x, y=y)
        time.sleep(0.08)
        self.click()

    def click_cell(self, screen_x: float, screen_y: float):
        self.click(x=int(screen_x), y=int(screen_y))
