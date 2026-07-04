import logging
import random
import sys
import time
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

try:
    import keyboard as _kb
    _HAS_KEYBOARD = True
except ImportError:
    _HAS_KEYBOARD = False

import cv2
import numpy as np

from bot.capture import WindowCapture
from bot.config import BotConfig
from bot.grid import IsometricGrid
from bot.mouse import MouseController
from bot.motion import MotionDetector
from bot.pathfinding import astar
from bot.routes import RouteManager
from bot.vision import ResourceDetector, TemplateMatcher

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class BotState(Enum):
    INIT = auto()
    CHECK_OK = auto()
    SCAN = auto()
    CLICK_RESOURCE = auto()
    WAIT_HARVEST = auto()
    NAVIGATE = auto()
    WAIT_MAP_CHANGE = auto()
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
        self._motion = MotionDetector(config)
        self.state = BotState.INIT
        self._running = True
        self._harvest_count = 0
        self._no_resource_streak = 0
        self._explore_idx = 0
        self._screenshot_count = 0
        self._target_screen: Optional[Tuple[int, int]] = None
        self._click_queue: List[Tuple[int, int]] = []
        self._harvested_set: set = set()
        self._last_pos: Optional[Tuple[int, int]] = None
        self._map_change_time: float = 0.0
        self._motion_stable_start: float = 0.0
        self._map_change_max_motion: float = 0.0
        self._was_walking: bool = False
        self._was_harvesting: bool = False
        self._last_debug_points: list = []
        self._map_change_char_start: Optional[Tuple[int, int]] = None

        self._routes = RouteManager(config.route_file)
        if config.active_zone:
            self._routes.load_zone(config.active_zone)

        self._hotkey_setup()

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
                 f"Motion tracking: ON  Fixed waits: OFF")
        if self.dry_run:
            log.info("DRY RUN mode -- no clicks")
        log.info("=" * 45)

        while self._running:
            try:
                if _HAS_MSVCRT and msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key in (b'q', b'Q'):
                        log.info("Q pressed, stopping")
                        self.stop()
                        break
                self._tick()
                time.sleep(0.03)
            except KeyboardInterrupt:
                log.info("Interrupted")
                self.stop()
            except Exception as e:
                log.exception(f"Error: {e}")
                time.sleep(2.0)

    def _hotkey_setup(self):
        if _HAS_KEYBOARD:
            _kb.add_hotkey("esc", self.stop, suppress=False)
            log.info("Global hotkey: ESC to stop (ESC still works in game)")

    def stop(self):
        self._running = False
        if _HAS_KEYBOARD:
            _kb.unhook_all_hotkeys()
        log.info("Bot stopped")

    def _tick(self):
        frame = self.capture.capture()

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
            return

        if frame is not None:
            self._motion.update(frame)

        if frame is None:
            return

        try:
            if self.state == BotState.SCAN:
                h, w = frame.shape[:2]
                points = self.detector.find_resource_centers(frame)
                self._last_debug_points = points

                always_save = self._screenshot_count == 0 or (points and self._screenshot_count < 5)
                if always_save or self.config.debug_overlay:
                    self._save_debug_frame(frame, points)

                if points:
                    new_ones = [p for p in points if p not in self._harvested_set]
                    if new_ones:
                        log.info(f"> FOUND {len(new_ones)} new resource(s)")
                        self._no_resource_streak = 0
                        for p in new_ones:
                            if p not in self._click_queue:
                                self._click_queue.append(p)
                        ref = self._last_pos or (w // 2, h // 2)
                        self._click_queue.sort(key=lambda p: (p[0] - ref[0]) ** 2 + (p[1] - ref[1]) ** 2)
                        log.info(f"  Queue: {len(self._click_queue)} pending, closest first")
                        self._target_screen = self._click_queue.pop(0)
                        self.state = BotState.CLICK_RESOURCE
                    else:
                        log.info(f". Only already-harvested resources visible (streak={self._no_resource_streak})")
                        self._no_resource_streak += 1
                        if self._no_resource_streak >= 3:
                            if self._routes.has_steps():
                                if self._motion.is_character_moving():
                                    return
                                if self._last_pos and self._motion.local_motion_ratio(
                                        self._last_pos[0], self._last_pos[1], radius=40) > 0.01:
                                    return
                                self._click_queue.clear()
                                self._harvested_set.clear()
                                self.state = BotState.NAVIGATE
                            else:
                                self.state = BotState.EXPLORE
                else:
                    self._no_resource_streak += 1
                    log.info(f". No resources (streak={self._no_resource_streak})")
                    if self._no_resource_streak >= 3:
                        if self._routes.has_steps():
                            if self._motion.is_character_moving():
                                return
                            if self._last_pos and self._motion.local_motion_ratio(
                                    self._last_pos[0], self._last_pos[1], radius=40) > 0.01:
                                return
                            self._click_queue.clear()
                            self._harvested_set.clear()
                            self.state = BotState.NAVIGATE
                        else:
                            self.state = BotState.EXPLORE

            elif self.state == BotState.CLICK_RESOURCE:
                if not self._target_screen:
                    self.state = BotState.SCAN
                    return

                if self._motion.is_character_moving():
                    return

                sx, sy = self._target_screen
                self._harvested_set.add((sx, sy))
                self._last_pos = (sx, sy)
                log.info(f">> Right-click resource at ({sx}, {sy})")
                if not self.dry_run:
                    self.mouse.click(button="right", x=sx, y=sy)
                self._harvest_start = time.time()
                self._motion_stable_start = 0.0
                self._was_walking = False
                self._was_harvesting = False
                self.state = BotState.WAIT_HARVEST

            elif self.state == BotState.WAIT_HARVEST:
                elapsed = time.time() - self._harvest_start

                global_m = self._motion.global_motion_ratio()
                local_m = self._motion.local_motion_ratio(
                    self._last_pos[0], self._last_pos[1], radius=40
                ) if self._last_pos else 0.0

                is_walking = global_m > 0.005
                is_harvesting = local_m > 0.01

                if is_walking and not self._was_walking:
                    log.info(">> Personnage en déplacement...")
                elif not is_walking and self._was_walking:
                    log.info(">> Personnage arrivé à destination")
                self._was_walking = is_walking

                if is_harvesting and not self._was_harvesting:
                    log.info(">> Personnage en train de récolter...")
                elif not is_harvesting and self._was_harvesting:
                    log.info(">> Animation de récolte terminée")
                self._was_harvesting = is_harvesting

                if is_walking or is_harvesting:
                    self._motion_stable_start = 0.0
                    return

                if self._motion_stable_start == 0.0:
                    self._motion_stable_start = time.time()
                stable_for = time.time() - self._motion_stable_start

                points = self.detector.find_resource_centers(frame)
                if self._target_screen:
                    resource_gone = self._target_screen not in points
                else:
                    resource_gone = True

                if resource_gone and stable_for >= 0.5:
                    self._harvest_count += 1
                    log.info(f"< Récolte #{self._harvest_count} terminée ({elapsed:.1f}s)")
                    self._target_screen = None
                    self._motion_stable_start = 0.0
                    self.state = BotState.CHECK_OK
                elif stable_for >= 3.0 and not resource_gone:
                    log.warning(f"! Ressource toujours présente après {elapsed:.1f}s, nouvelle tentative")
                    self._target_screen = None
                    self._motion_stable_start = 0.0
                    self.state = BotState.SCAN
                elif elapsed >= 30.0:
                    log.warning(f"! Sécurité: timeout 30s atteint ({elapsed:.1f}s)")
                    self._target_screen = None
                    self._motion_stable_start = 0.0
                    self.state = BotState.CHECK_OK

            elif self.state == BotState.CHECK_OK:
                if self.dry_run or "ok" not in self.templates._templates:
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
                self.state = BotState.SCAN

            elif self.state == BotState.NAVIGATE:
                fh, fw = frame.shape[:2]
                pos = self._routes.get_click_pos(fw, fh)
                if pos is None:
                    log.warning("No navigation step available, falling back to SCAN")
                    self.state = BotState.SCAN
                    return
                dx, dy = pos
                dir_label = self._routes.current_dir()
                log.info(f">> Navigate {dir_label} -> ({dx}, {dy})")
                if not self.dry_run:
                    self.mouse.click(x=dx, y=dy)
                self._routes.advance()
                self._map_change_time = time.time()
                self._map_change_max_motion = 0.0
                self._click_queue.clear()
                self._harvested_set.clear()
                self._last_pos = None
                self.state = BotState.WAIT_MAP_CHANGE

            elif self.state == BotState.WAIT_MAP_CHANGE:
                elapsed = time.time() - self._map_change_time

                global_m = self._motion.global_motion_ratio()
                if global_m > self._map_change_max_motion:
                    self._map_change_max_motion = global_m

                if self._map_change_char_start is None:
                    self._map_change_char_start = self._motion.character_position()

                char_moving = self._motion.is_character_moving()

                if elapsed > 2.0 and not char_moving and self._map_change_max_motion < 0.01:
                    log.warning("! Navigation annulée (personnage n'a pas bougé)")
                    self._map_change_max_motion = 0.0
                    self._map_change_char_start = None
                    self.state = BotState.SCAN
                    return

                if elapsed < 1.0:
                    return

                if global_m < 0.002 and self._map_change_max_motion > 0.05:
                    if self._motion_stable_start == 0.0:
                        self._motion_stable_start = time.time()
                    elif time.time() - self._motion_stable_start >= 0.5:
                        log.info(f"Changement de map détecté ({elapsed:.1f}s, pic {self._map_change_max_motion:.4f})")
                        self._motion_stable_start = 0.0
                        self._map_change_max_motion = 0.0
                        self._map_change_char_start = None
                        self.state = BotState.CHECK_OK
                        return
                else:
                    self._motion_stable_start = 0.0

                if elapsed >= self.config.map_load_timeout:
                    if self._map_change_max_motion < 0.05:
                        log.warning(f"! Échec changement de map, retour à SCAN")
                    else:
                        log.info(f"Changement de map timeout ({elapsed:.1f}s)")
                    self._motion_stable_start = 0.0
                    self._map_change_max_motion = 0.0
                    self._map_change_char_start = None
                    self.state = BotState.SCAN

            elif self.state == BotState.EXPLORE:
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
                self.state = BotState.SCAN

        finally:
            if self.config.debug_overlay:
                debug = frame.copy()
                self._motion.draw_debug(debug)
                for x, y in self._last_debug_points:
                    cv2.circle(debug, (x, y), 5, (0, 255, 255), 2)
                    cv2.drawMarker(debug, (x, y), (0, 255, 255), cv2.MARKER_CROSS, 8, 1)
                cv2.putText(debug, f"State: {self.state.name}  Harvests: {self._harvest_count}",
                            (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
                cv2.imshow("DofusBot Debug", debug)
                cv2.waitKey(1)

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
