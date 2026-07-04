import logging
import time

from bot.capture import WindowCapture
from bot.config import BotConfig
from bot.mouse import MouseController
from bot.routes import RouteManager

log = logging.getLogger(__name__)


def run_route(config: BotConfig, zone: str, click_delay: float = 5.0):
    capture = WindowCapture(config.window_title)
    if not capture.find_window():
        log.error("Game window not found")
        return

    rect = capture.get_window_rect()
    if rect:
        log.info(f"Window: {rect[2]}x{rect[3]} at ({rect[0]},{rect[1]})")

    mouse = MouseController(config)
    if rect:
        mouse.set_window_offset(rect[0], rect[1])

    routes = RouteManager(config.route_file)
    if not routes.load_zone(zone):
        log.error(f"Zone '{zone}' not found in {config.route_file}")
        return

    log.info(f"Starting route test for zone '{zone}' ({click_delay}s between clicks)")
    log.info("Press Ctrl+C to stop")
    log.info("=" * 45)

    step_count = 0
    lap_count = 0

    try:
        while True:
            frame = capture.capture()
            if frame is None:
                time.sleep(1)
                continue
            fh, fw = frame.shape[:2]
            pos = routes.get_click_pos(fw, fh)
            if pos is None:
                log.warning("No step available, restarting route")
                routes.load_zone(zone)
                lap_count += 1
                log.info(f"--- Lap #{lap_count} ---")
                continue

            dx, dy = pos
            dir_label = routes.current_dir()
            step_count += 1
            log.info(f"[{step_count}] {dir_label} -> ({dx}, {dy})")
            mouse.click(x=dx, y=dy)
            routes.advance()
            time.sleep(click_delay)

    except KeyboardInterrupt:
        log.info(f"Stopped after {step_count} clicks ({lap_count} laps)")
