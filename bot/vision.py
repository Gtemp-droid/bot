import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

from bot.config import BotConfig

log = logging.getLogger(__name__)


class ResourceDetector:
    def __init__(self, config: BotConfig):
        self.config = config
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def find_resources(self, frame: np.ndarray) -> List[Tuple[int, int, float]]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        combined = np.zeros(frame.shape[:2], dtype=np.uint8)

        for hsv_range in self.config.resource_hsv_ranges:
            lower = np.array(hsv_range["lower"], dtype=np.uint8)
            upper = np.array(hsv_range["upper"], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)
            combined = cv2.bitwise_or(combined, mask)

        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, self.kernel)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, self.kernel)

        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        results = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.config.resource_min_area <= area <= self.config.resource_max_area:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    results.append((cx, cy, area))
        return results

    def find_resource_centers(self, frame: np.ndarray) -> List[Tuple[int, int]]:
        return [(x, y) for x, y, _ in self.find_resources(frame)]

    def draw_debug(self, frame: np.ndarray, points: List[Tuple[int, int]]):
        for x, y in points:
            cv2.circle(frame, (x, y), 4, (0, 255, 0), -1)
            cv2.drawMarker(frame, (x, y), (0, 255, 0), cv2.MARKER_CROSS, 8, 1)

    def find_player_on_minimap(self, minimap: np.ndarray) -> Optional[Tuple[int, int]]:
        hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)
        lower_white = np.array([0, 0, 200], dtype=np.uint8)
        upper_white = np.array([180, 30, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower_white, upper_white)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 2 < area < 60:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    return (cx, cy)
        return None


class TemplateMatcher:
    def __init__(self, config: BotConfig):
        self.config = config
        self._templates: dict = {}

    def load_template(self, name: str, path: str) -> bool:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            log.warning(f"Failed to load template: {path}")
            return False
        self._templates[name] = img
        return True

    def find_template(self, frame: np.ndarray, name: str, threshold: float = 0.7
                      ) -> Optional[Tuple[int, int, float]]:
        if name not in self._templates:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        template = self._templates[name]
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= threshold:
            return (max_loc[0] + template.shape[1] // 2,
                    max_loc[1] + template.shape[0] // 2, max_val)
        return None

    def find_all_templates(self, frame: np.ndarray, name: str, threshold: float = 0.7
                           ) -> List[Tuple[int, int, float]]:
        if name not in self._templates:
            return []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        template = self._templates[name]
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        locs = np.where(result >= threshold)
        points = []
        for pt in zip(*locs[::-1]):
            points.append((pt[0] + template.shape[1] // 2,
                           pt[1] + template.shape[0] // 2,
                           float(result[pt[1], pt[0]])))
        return points
