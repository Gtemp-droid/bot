import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)


class MotionDetector:
    def __init__(self, config=None, history_size: int = 15):
        if config is not None:
            self.motion_threshold = config.motion_threshold
            self.char_min_area = config.character_min_area
            self.char_max_area = config.character_max_area
        else:
            self.motion_threshold = 30
            self.char_min_area = 50
            self.char_max_area = 500
        self.history_size = history_size

        self._prev_frame: Optional[np.ndarray] = None
        self._last_thresh: Optional[np.ndarray] = None
        self._char_pos: Optional[Tuple[int, int]] = None
        self._char_history: List[Optional[Tuple[int, int]]] = []
        self._char_bbox: Optional[Tuple[int, int, int, int]] = None
        self._global_motion: float = 0.0
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        self._char_template: Optional[np.ndarray] = None
        self._template_wh: Optional[Tuple[int, int]] = None
        self._last_match_method: str = "none"
        self._template_conf: float = 0.0
        self._template_update_counter: int = 0

    def _extract_template(self, frame: np.ndarray, bbox_center_wh, margin: int = 5):
        cx, cy, w, h = bbox_center_wh
        x1 = max(0, cx - w // 2 - margin)
        y1 = max(0, cy - h // 2 - margin)
        x2 = min(frame.shape[1], cx + w // 2 + margin)
        y2 = min(frame.shape[0], cy + h // 2 + margin)
        patch = frame[y1:y2, x1:x2]
        if patch.shape[0] > 10 and patch.shape[1] > 10:
            self._char_template = patch.copy()
            self._template_wh = (patch.shape[1], patch.shape[0])

    def _match_template(self, frame: np.ndarray):
        if self._char_template is None or self._template_wh is None:
            return None, 0.0
        tw, th = self._template_wh
        cx, cy = self._char_pos or (frame.shape[1] // 2, frame.shape[0] // 2)

        margin = 150
        x1 = max(0, cx - margin)
        y1 = max(0, cy - margin)
        x2 = min(frame.shape[1], cx + margin)
        y2 = min(frame.shape[0], cy + margin)

        search = frame[y1:y2, x1:x2]
        if search.shape[0] < th or search.shape[1] < tw:
            return None, 0.0

        gray_search = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
        gray_tmpl = cv2.cvtColor(self._char_template, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(gray_search, gray_tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > 0.6:
            tx = x1 + max_loc[0] + tw // 2
            ty = y1 + max_loc[1] + th // 2
            return (tx, ty), max_val
        return None, max_val

    def update(self, frame: np.ndarray):
        if self._prev_frame is None:
            self._prev_frame = frame.copy()
            return

        diff = cv2.absdiff(frame, self._prev_frame)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, self.motion_threshold, 255, cv2.THRESH_BINARY)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self._kernel)

        self._last_thresh = thresh

        h, w = frame.shape[:2]
        self._global_motion = cv2.countNonZero(thresh) / (w * h)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_area = 0
        best_pos = None
        best_bbox = None
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.char_min_area or area > self.char_max_area:
                continue
            if area > best_area:
                best_area = area
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    best_pos = (cx, cy)
                    bx, by, bw, bh = cv2.boundingRect(cnt)
                    best_bbox = (cx, cy, bw, bh)

        if best_pos:
            self._char_pos = best_pos
            self._char_bbox = best_bbox
            self._char_history.append(best_pos)
            self._last_match_method = "motion"
            self._template_conf = 1.0

            self._extract_template(frame, best_bbox)
            if len(self._char_history) > self.history_size:
                self._char_history.pop(0)

        else:
            tm_pos, tm_conf = self._match_template(frame)
            if tm_pos:
                self._char_pos = tm_pos
                tw = self._template_wh[0] if self._template_wh else 20
                th = self._template_wh[1] if self._template_wh else 20
                self._char_bbox = (tm_pos[0], tm_pos[1], tw, th)
                self._char_history.append(tm_pos)
                self._last_match_method = "template"
                self._template_conf = tm_conf
                if len(self._char_history) > self.history_size:
                    self._char_history.pop(0)

        self._prev_frame = frame.copy()

    def character_position(self) -> Optional[Tuple[int, int]]:
        return self._char_pos

    def character_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        return self._char_bbox

    def is_character_moving(self, threshold: float = 5.0) -> bool:
        recent = [p for p in self._char_history[-4:] if p is not None]
        if len(recent) < 2:
            return False
        max_dist = max(
            ((recent[i][0] - recent[j][0]) ** 2 + (recent[i][1] - recent[j][1]) ** 2) ** 0.5
            for i in range(len(recent))
            for j in range(i + 1, len(recent))
        )
        return max_dist > threshold

    def global_motion_ratio(self) -> float:
        return self._global_motion

    def local_motion_ratio(self, center_x: int, center_y: int, radius: int = 50) -> float:
        if self._last_thresh is None:
            return 0.0
        hh, ww = self._last_thresh.shape
        mask = np.zeros((hh, ww), dtype=np.uint8)
        cv2.circle(mask, (int(center_x), int(center_y)), radius, 255, -1)
        masked = cv2.bitwise_and(self._last_thresh, mask)
        changed = cv2.countNonZero(masked)
        total = np.count_nonzero(mask)
        return changed / total if total > 0 else 0.0

    def reset(self):
        self._prev_frame = None
        self._last_thresh = None
        self._char_pos = None
        self._char_history.clear()
        self._char_bbox = None
        self._global_motion = 0.0
        self._char_template = None
        self._template_wh = None
        self._last_match_method = "none"
        self._template_conf = 0.0

    def draw_debug(self, frame: np.ndarray):
        if self._char_bbox:
            cx, cy, w, h = self._char_bbox
            color = (0, 255, 0) if self._last_match_method == "motion" else (255, 200, 0)
            cv2.rectangle(frame, (cx - w // 2, cy - h // 2),
                          (cx + w // 2, cy + h // 2), color, 2)
            cv2.drawMarker(frame, (cx, cy), color, cv2.MARKER_CROSS, 12, 2)
        info = [
            f"Motion: {self._global_motion:.4f}",
            f"Track: {self._last_match_method}",
        ]
        pos = self._char_pos
        if pos:
            info.append(f"Char: ({pos[0]}, {pos[1]})")
        if self._last_match_method == "template":
            info.append(f"Tmpl conf: {self._template_conf:.2f}")
        for i, line in enumerate(info):
            cv2.putText(frame, line, (8, frame.shape[0] - 30 + i * 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
