import logging
from typing import Optional, Tuple

import cv2
import mss
import numpy as np
import pygetwindow as gw
from mss.base import MSSBase

log = logging.getLogger(__name__)


class WindowCapture:
    def __init__(self, window_title: str = "Dofus Retro"):
        self.window_title = window_title
        self.sct: MSSBase = mss.mss()
        self._window: Optional[gw.Window] = None
        self._offset_x: int = 0
        self._offset_y: int = 0
        self._last_rect: Optional[Tuple[int, int, int, int]] = None

    def find_window(self) -> bool:
        wins = gw.getWindowsWithTitle(self.window_title)
        if not wins:
            log.warning(f"No window found with title containing '{self.window_title}'")
            return False
        self._window = wins[0]
        log.info(f"Found window: {self._window.title} ({self._window.width}x{self._window.height})")
        return True

    def update_rect(self) -> Optional[Tuple[int, int, int, int]]:
        if self._window is None:
            return None
        try:
            if self._window.isMinimized:
                return self._last_rect
            r = self._window.left, self._window.top, self._window.width, self._window.height
            self._last_rect = r
            return r
        except Exception:
            return self._last_rect

    def capture(self) -> Optional[np.ndarray]:
        rect = self.update_rect()
        if rect is None:
            return None
        left, top, width, height = rect
        monitor = {"left": left, "top": top, "width": width, "height": height}
        try:
            img = self.sct.grab(monitor)
            return cv2.cvtColor(np.array(img), cv2.COLOR_BGRA2BGR)
        except Exception as e:
            log.error(f"Capture failed: {e}")
            return None

    def capture_region(self, x: int, y: int, w: int, h: int) -> Optional[np.ndarray]:
        rect = self.update_rect()
        if rect is None:
            return None
        monitor = {"left": rect[0] + x, "top": rect[1] + y, "width": w, "height": h}
        try:
            img = self.sct.grab(monitor)
            return cv2.cvtColor(np.array(img), cv2.COLOR_BGRA2BGR)
        except Exception as e:
            log.error(f"Region capture failed: {e}")
            return None

    def get_window_rect(self) -> Optional[Tuple[int, int, int, int]]:
        return self.update_rect()

    def close(self):
        self.sct.close()
