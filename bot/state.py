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
from bot.vision import ResourceDetector, TemplateMatcher

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class BotState(Enum):
    INIT = auto()
    CHECK_OK = auto()
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
        self.templates = TemplateMatcher(config)
        self.grid = IsometricGrid(config)
        self.mouse = MouseController(config)
        self.state = BotState.INIT
        self._running = True
        self._harvest_count = 0
        self._no_resource_streak = 0
        self._explore_idx = 0
        self._screenshot_count = 0
        self._target_screen: Optional[Tuple[int, int]] = None
        self._click_queue: List[Tuple[int, int]] = []

        self._debug_dir = Path(config.screenshot_dir)
        self._debug_dir.mkdir(exist_ok=True)
        TEMPLATE_DIR.mkdir(exist_ok=True)
        ok_path = TEMPLATE_DIR / "ok.png"
        if ok_path.exists():
            self.templates.load_template("ok", str(ok_path))
            log.info(f"Loaded OK template: {ok_path}")
        else:
            log.info("No ok.png template found -- level-up popup won't be auto-dismissed")
            log.info("  Capture one with: run_bot --capture-templates")

    def run(self):
        log.info("=" * 45)
        log.info("Dofus 1.29 HarvestBot (CV only)")
        log.info(f"Grid: ({self.config.grid_origin_x:.0f},{self.config.grid_origin_y:.0f}) "
                 f"{self.config.cell_width:.1f}x{self.config.cell_height:.1f}")
        pname = self.config.active_profile or "(default)"
        log.info(f"Profile: {pname}")
        for i, r in enumerate(self.config.resource_hsv_ranges):
            log.info(f"  HSV: H=[{r['lower'][0]}-{r['upper'][0]}] "
                     f"S=[{r['lower'][1]}-{r['upper'][1]}] "
                     f"V=[{r['lower'][2]}-{r['upper'][2]}]")
        log.info(f"Area: {self.config.resource_min_area}-{self.config.resource_max_area}  "
                 f"Harvest: {self.config.harvest_wait_min}-{self.config.harvest_wait_max}s")
        if self.dry_run:
            log.info("DRY RUN mode -- no clicks")
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
            self.state = BotState.CHECK_OK

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
                log.info(f"> FOUND {len(points)} resource(s)")
                self._no_resource_streak = 0
                # Remove from queue any positions no longer visible
                old = set(self._click_queue)
                still_valid = old & set(points)
                new_ones = [p for p in points if p not in old]
                self._click_queue = [p for p in self._click_queue if p in still_valid]
                self._click_queue.extend(new_ones)
                log.info(f"  Queue: {len(self._click_queue)} pending")
                self._target_screen = self._click_queue.pop(0)
                self.state = BotState.CLICK_RESOURCE
            else:
                self._no_resource_streak += 1
                log.info(f". No resources (streak={self._no_resource_streak})")
                self._click_queue.clear()
                if self._no_resource_streak >= 3:
                    self.state = BotState.EXPLORE
                else:
                    time.sleep(self.config.resource_search_interval)

        elif self.state == BotState.CLICK_RESOURCE:
            if not self._target_screen:
                self.state = BotState.SCAN
                return
            sx, sy = self._target_screen
            log.info(f">> Right-click resource at ({sx}, {sy})")
            if not self.dry_run:
                self.mouse.click(button="right", x=sx, y=sy)
            self._harvest_start = time.time()
            self.state = BotState.WAIT_HARVEST

        elif self.state == BotState.WAIT_HARVEST:
            elapsed = time.time() - self._harvest_start
            wait = random.uniform(self.config.harvest_wait_min, self.config.harvest_wait_max)
            if elapsed >= wait:
                self._harvest_count += 1
                log.info(f"< Harvest #{self._harvest_count} ({elapsed:.1f}s)")
                self._target_screen = None
                self.state = BotState.CHECK_OK
            else:
                time.sleep(0.3)

        elif self.state == BotState.CHECK_OK:
            if self.dry_run or "ok" not in self.templates._templates:
                self.state = BotState.SCAN
                return
            frame = self.capture.capture()
            if frame is None:
                self.state = BotState.SCAN
                return
            hh, ww = frame.shape[:2]
            cx, cy = ww // 2, hh // 2
            search = frame[cy - 100:cy + 100, cx - 150:cx + 150]
            result = self.templates.find_template(search, "ok", threshold=0.6)
            if result:
                tx, ty, conf = result
                ax = cx - 150 + tx
                ay = cy - 100 + ty
                log.info(f">> Level-up popup detected at ({ax}, {ay}) conf={conf:.2f}")
                self.mouse.click(x=ax, y=ay)
                time.sleep(0.5)
            self.state = BotState.SCAN

        elif self.state == BotState.EXPLORE:
            fw, fh = 1280, 720
            frame = self.capture.capture()
            if frame is not None:
                fh, fw = frame.shape[:2]
            targets = [
                (fw // 2, fh // 2 + fh // 6),
                (fw // 2 - fw // 5, fh // 2 + fh // 8),
                (fw // 2 + fw // 5, fh // 2 + fh // 8),
                (fw // 2, fh // 2 - fh // 6),
            ]
            t = targets[self._explore_idx % len(targets)]
            self._explore_idx += 1
            log.info(f"> Explore click ({t[0]}, {t[1]})")
            if not self.dry_run:
                self.mouse.click(x=t[0], y=t[1])
                time.sleep(self.config.move_recheck_interval)
            self.state = BotState.SCAN

    def _save_debug_frame(self, frame, points):
        debug = frame.copy()
        h, w = debug.shape[:2]
        for x, y in points:
            cv2.circle(debug, (x, y), 5, (0, 255, 0), 2)
            cv2.drawMarker(debug, (x, y), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
        info = [
            f"Resources: {len(points)}  State: {self.state.name}",
            f"Harvests: {self._harvest_count}",
        ]
        if self.config.active_profile:
            info.append(f"Profile: {self.config.active_profile}")
        for i, line in enumerate(info):
            cv2.putText(debug, line, (8, h - 30 + i * 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        p = self._debug_dir / f"debug_{self._screenshot_count:04d}.png"
        cv2.imwrite(str(p), debug)

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        combined = np.zeros(frame.shape[:2], dtype=np.uint8)
        for r in self.config.resource_hsv_ranges:
            lo = np.array(r["lower"], dtype=np.uint8)
            hi = np.array(r["upper"], dtype=np.uint8)
            combined = cv2.bitwise_or(combined, cv2.inRange(hsv, lo, hi))
        mp = self._debug_dir / f"mask_{self._screenshot_count:04d}.png"
        cv2.imwrite(str(mp), combined)

        self._screenshot_count += 1
