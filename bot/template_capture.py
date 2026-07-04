import logging
import time
from pathlib import Path

import cv2
import numpy as np

from bot.capture import WindowCapture
from bot.config import BotConfig

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def capture_templates():
    config = BotConfig.load()
    cap = WindowCapture(config.window_title)
    if not cap.find_window():
        log.error("Game window not found")
        return

    TEMPLATE_DIR.mkdir(exist_ok=True)
    log.info(f"Saving templates to {TEMPLATE_DIR}")
    log.info("Press SPACE to capture a template region")
    log.info("Press 'r' to capture a rectangle (resource sample)")
    log.info("Press 'q' to quit")

    win_name = "Template Capture"
    cv2.namedWindow(win_name)
    capturing = False
    rect_start = None
    frame = None

    while True:
        frame = cap.capture()
        if frame is None:
            time.sleep(0.3)
            continue

        display = frame.copy()
        if rect_start and capturing:
            h, w = frame.shape[:2]
            cv2.line(display, (w // 2, 0), (w // 2, h), (0, 255, 0), 1)
            cv2.line(display, (0, h // 2), (w, h // 2), (0, 255, 0), 1)
            cv2.putText(display, "Click and drag to select region, press ENTER to save",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        cv2.imshow(win_name, display)
        key = cv2.waitKey(30) & 0xFF

        if key == ord('q'):
            break
        elif key == ord(' ') or key == ord('r'):
            if not capturing:
                capturing = True
                rect_start = (0, 0)
            else:
                capturing = False
                _save_selection(frame, win_name)
        elif key == 13 and capturing:
            capturing = False

    cv2.destroyAllWindows()
    cap.close()


def _save_selection(frame, win_name):
    from_window = cv2.selectROI(win_name, frame, False)
    cv2.destroyWindow(win_name)
    if from_window[2] > 10 and from_window[3] > 10:
        x, y, w, h = [int(v) for v in from_window]
        roi = frame[y:y + h, x:x + w]
        name = input(f"Template name (e.g., 'wheat', 'barley', 'button_ok'): ").strip()
        if name:
            path = TEMPLATE_DIR / f"{name}.png"
            cv2.imwrite(str(path), roi)
            log.info(f"Saved template '{name}' ({w}x{h}) to {path}")
        else:
            log.info("Cancelled")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    capture_templates()
