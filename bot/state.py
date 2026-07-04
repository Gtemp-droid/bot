import logging
import random
import time
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from bot.capture import WindowCapture
from bot.config import BotConfig
from bot.grid import IsometricGrid
from bot.mouse import MouseController
from bot.pathfinding import astar
from bot.vision import ResourceDetector

log = logging.getLogger(__name__)


class BotState(Enum):
    INIT = auto()
    SCAN = auto()
    CLICK_RESOURCE = auto()
    WAIT_HARVEST = auto()
    EXPLORE = auto()


class HarvestBot:
    def __init__(self, config: BotConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.capture = WindowCapture(config.window_title)
        self.detector = ResourceDetector(config)
        self.grid = IsometricGrid(config)
        self.mouse = MouseController(config)
        self.state = BotState.INIT
        self._running = True
        self._harvest_count = 0
        self._no_resource_streak = 0
        self._explore_idx = 0
        self._screenshot_count = 0
        self._target_screen: Optional[Tuple[int, int]] = None

        self._debug_dir = Path(config.screenshot_dir)
        self._debug_dir.mkdir(exist_ok=True)

    def run(self):
        log.info("=" * 45)
        log.info("Dofus 1.29 HarvestBot (CV only)")
        log.info(f"Grid: ({self.config.grid_origin_x},{self.config.grid_origin_y}) "
                 f"{self.config.cell_width}x{self.config.cell_height}")
        log.info(f"HSV ranges: {len(self.config.resource_hsv_ranges)}")
        for i, r in enumerate(self.config.resource_hsv_ranges):
            log.info(f"  Range {i}: H=[{r['lower'][0]}-{r['upper'][0]}] "
                     f"S=[{r['lower'][1]}-{r['upper'][1]}] "
                     f"V=[{r['lower'][2]}-{r['upper'][2]}]")
        log.info(f"Area filter: {self.config.resource_min_area}-{self.config.resource_max_area}")
        if self.dry_run:
            log.info("DRY RUN mode -- no clicks will be sent")
        log.info("=" * 45)

        while self._running:
            try:
                self._tick()
            except KeyboardInterrupt:
                log.info("Interrupted")
                self.stop()
            except Exception as e:
                log.exception(f"Error: {e}")
                time.sleep(2.0)

    def stop(self):
        self._running = False

    def _tick(self):
        if self.state == BotState.INIT:
            if not self.capture.find_window():
                log.warning("Dofus window not found. Retrying in 3s...")
                time.sleep(3)
                return
            rect = self.capture.get_window_rect()
            if rect:
                self.mouse.set_window_offset(rect[0], rect[1])
                log.info(f"Window: {rect[2]}x{rect[3]} at ({rect[0]},{rect[1]})")
            time.sleep(1)
            self.state = BotState.SCAN

        elif self.state == BotState.SCAN:
            frame = self.capture.capture()
            if frame is None:
                time.sleep(0.5)
                return

            h, w = frame.shape[:2]
            points = self.detector.find_resource_centers(frame)

            always_save = self._screenshot_count == 0 or (points and self._screenshot_count < 5)
            if always_save or self.config.debug_overlay:
                self._save_debug_frame(frame, points)

            if points:
                log.info(f"> FOUND {len(points)} resource(s) on screen ({w}x{h})")
                for i, (px, py) in enumerate(points[:5]):
                    log.info(f"  [{i}] at ({px},{py})")
                self._no_resource_streak = 0
                target = self._pick_best(points, w, h)
                self._target_screen = target
                self.state = BotState.CLICK_RESOURCE
            else:
                self._no_resource_streak += 1
                log.info(f". Scan {self._no_resource_streak}: no resources ({w}x{h})")
                if self._no_resource_streak >= 3:
                    log.info("-> EXPLORE mode")
                    self.state = BotState.EXPLORE
                else:
                    time.sleep(self.config.resource_search_interval)

        elif self.state == BotState.CLICK_RESOURCE:
            if not self._target_screen:
                self.state = BotState.SCAN
                return
            sx, sy = self._target_screen
            log.info(f">> Click resource at ({sx}, {sy})")
            if not self.dry_run:
                self.mouse.double_click(x=sx, y=sy)
            self._harvest_start = time.time()
            self.state = BotState.WAIT_HARVEST

        elif self.state == BotState.WAIT_HARVEST:
            elapsed = time.time() - self._harvest_start
            wait = random.uniform(self.config.harvest_wait_min, self.config.harvest_wait_max)
            if elapsed >= wait:
                self._harvest_count += 1
                log.info(f"< Harvest #{self._harvest_count} complete ({elapsed:.1f}s)")
                self._target_screen = None
                self._no_resource_streak = 0

                frame = self.capture.capture()
                if frame is not None:
                    remaining = self.detector.find_resource_centers(frame)
                    if remaining:
                        log.info(f"  {len(remaining)} resource(s) still visible")
                self.state = BotState.SCAN
            else:
                time.sleep(0.3)

        elif self.state == BotState.EXPLORE:
            clicked = self._try_move()
            if clicked and not self.dry_run:
                time.sleep(self.config.move_recheck_interval)
            self._no_resource_streak = 0
            self.state = BotState.SCAN

    def _pick_best(self, points: List[Tuple[int, int]], fw: int, fh: int) -> Tuple[int, int]:
        cx, cy = fw // 2, fh // 2
        return min(points, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)

    def _try_move(self) -> bool:
        fw, fh = 1280, 720
        frame = self.capture.capture()
        if frame is not None:
            fh, fw = frame.shape[:2]

        explore_targets = [
            (fw // 2, fh // 2 + fh // 6),
            (fw // 2 - fw // 5, fh // 2 + fh // 8),
            (fw // 2 + fw // 5, fh // 2 + fh // 8),
            (fw // 2, fh // 2 - fh // 6),
        ]
        target = explore_targets[self._explore_idx % len(explore_targets)]
        self._explore_idx += 1

        log.info(f"> Explore: click ({target[0]}, {target[1]})")
        if not self.dry_run:
            self.mouse.click(x=target[0], y=target[1])
        return True

    def _save_debug_frame(self, frame, points):
        debug = frame.copy()
        h, w = debug.shape[:2]

        for x, y in points:
            cv2.circle(debug, (x, y), 5, (0, 255, 0), 2)
            cv2.drawMarker(debug, (x, y), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)

        info_lines = [
            f"Resources: {len(points)}  State: {self.state.name}",
            f"Harvests: {self._harvest_count}  Streak: {self._no_resource_streak}",
        ]
        for i, line in enumerate(info_lines):
            cv2.putText(debug, line, (8, h - 30 + i * 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        path = self._debug_dir / f"debug_{self._screenshot_count:04d}.png"
        cv2.imwrite(str(path), debug)

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        combined = np.zeros(frame.shape[:2], dtype=np.uint8)
        for r in self.config.resource_hsv_ranges:
            lo = np.array(r["lower"], dtype=np.uint8)
            hi = np.array(r["upper"], dtype=np.uint8)
            combined = cv2.bitwise_or(combined, cv2.inRange(hsv, lo, hi))
        mask_path = self._debug_dir / f"mask_{self._screenshot_count:04d}.png"
        cv2.imwrite(str(mask_path), combined)

        self._screenshot_count += 1
