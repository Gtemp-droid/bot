import logging

import cv2
import numpy as np

from bot.capture import WindowCapture
from bot.config import BotConfig
from bot.motion import MotionDetector

log = logging.getLogger(__name__)

WIN_NAME = "Character Calibration"
MASK_WIN = "Motion Mask"


def run_character_calibration(config: BotConfig):
    cap = WindowCapture(config.window_title)
    if not cap.find_window():
        log.error("Game window not found. Start Dofus first.")
        return

    motion = MotionDetector(config)
    motion.motion_threshold = config.motion_threshold
    motion.char_min_area = config.character_min_area
    motion.char_max_area = config.character_max_area

    cv2.namedWindow(WIN_NAME)
    cv2.namedWindow(MASK_WIN)

    cv2.createTrackbar("Threshold", WIN_NAME, config.motion_threshold, 100, lambda v: None)
    cv2.createTrackbar("Min Area", WIN_NAME, config.character_min_area, 500, lambda v: None)
    cv2.createTrackbar("Max Area", WIN_NAME, config.character_max_area, 2000, lambda v: None)
    cv2.createTrackbar("Pause", WIN_NAME, 0, 1, lambda v: None)

    log.info("=== Character Calibration ===")
    log.info("Green box = tracked by motion    Blue box = tracked by template")
    log.info("Adjust trackbars until the character is outlined in green when moving.")
    log.info("Press S to save, Q to quit, R to reset.")

    paused = False

    while True:
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q'):
            break
        if key == ord('r'):
            motion.reset()
            log.info("History reset")
            continue
        if key == ord('s'):
            config.motion_threshold = motion.motion_threshold
            config.character_min_area = motion.char_min_area
            config.character_max_area = motion.char_max_area
            config.save()
            log.info(f"Saved: threshold={config.motion_threshold} "
                     f"min_area={config.character_min_area} "
                     f"max_area={config.character_max_area}")
            continue

        paused = cv2.getTrackbarPos("Pause", WIN_NAME) == 1

        frame = cap.capture()
        if frame is None:
            continue

        motion.motion_threshold = cv2.getTrackbarPos("Threshold", WIN_NAME)
        motion.char_min_area = cv2.getTrackbarPos("Min Area", WIN_NAME)
        motion.char_max_area = cv2.getTrackbarPos("Max Area", WIN_NAME)

        if not paused:
            motion.update(frame)

        display = frame.copy()
        motion.draw_debug(display)

        hh, ww = display.shape[:2]

        # Template preview in top-right corner
        if motion._char_template is not None:
            tmpl = motion._char_template.copy()
            scale = min(80 / tmpl.shape[1], 80 / tmpl.shape[0])
            new_w = int(tmpl.shape[1] * scale)
            new_h = int(tmpl.shape[0] * scale)
            tmpl_small = cv2.resize(tmpl, (new_w, new_h))
            margin = 10
            x_off = ww - new_w - margin
            y_off = margin
            display[y_off:y_off + new_h, x_off:x_off + new_w] = tmpl_small
            cv2.rectangle(display, (x_off, y_off),
                          (x_off + new_w, y_off + new_h), (255, 200, 0), 1)
            cv2.putText(display, "template", (x_off, y_off + new_h + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 200, 0), 1)

        info = [
            f"Threshold={motion.motion_threshold}  "
            f"Area=[{motion.char_min_area}-{motion.char_max_area}]  "
            f"Method={motion._last_match_method}",
            "S=save  Q=quit  R=reset  Pause=freeze",
        ]
        for i, line in enumerate(info):
            cv2.putText(display, line, (8, 20 + i * 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

        cv2.imshow(WIN_NAME, display)

        if motion._last_thresh is not None:
            mask_bgr = cv2.cvtColor(motion._last_thresh, cv2.COLOR_GRAY2BGR)
            sh, sw = mask_bgr.shape[:2]
            scale = min(400 / sw, 300 / sh)
            mw, mh = int(sw * scale), int(sh * scale)
            mask_small = cv2.resize(mask_bgr, (mw, mh))
            cv2.imshow(MASK_WIN, mask_small)

    cv2.destroyAllWindows()
    cap.close()
    log.info("Character calibration done")
