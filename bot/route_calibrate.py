import json
import logging
from pathlib import Path

import cv2
import numpy as np

from bot.capture import WindowCapture

log = logging.getLogger(__name__)

DIR_MAP = {
    ord("g"): "G", ord("d"): "D", ord("h"): "H", ord("b"): "B",
    ord("G"): "G", ord("D"): "D", ord("H"): "H", ord("B"): "B",
}
DIR_LABELS = {"G": "GAUCHE", "D": "DROITE", "H": "HAUT", "B": "BAS"}
COLORS = {"G": (0, 200, 255), "D": (255, 100, 0), "H": (0, 255, 0), "B": (0, 100, 255)}


def calibrate_route(config):
    capture = WindowCapture(config.window_title)
    if not capture.find_window():
        log.error("Game window not found")
        return

    rect = capture.get_window_rect()
    if rect:
        log.info(f"Window: {rect[2]}x{rect[3]} at ({rect[0]},{rect[1]})")

    cv2.namedWindow("Route Calibration", cv2.WINDOW_NORMAL)
    steps = []
    last_mouse = (0, 0)

    def mouse_cb(event, x, y, flags, param):
        nonlocal last_mouse
        if event == cv2.EVENT_MOUSEMOVE:
            last_mouse = (int(x), int(y))

    cv2.setMouseCallback("Route Calibration", mouse_cb)

    zone_name = ""
    saved = False

    while True:
        frame = capture.capture()
        if frame is None:
            cv2.waitKey(100)
            continue

        display = frame.copy()
        fh, fw = display.shape[:2]

        # Draw existing steps
        for i, (direction, fx, fy) in enumerate(steps):
            sx, sy = int(fx * fw), int(fy * fh)
            color = COLORS.get(direction, (255, 255, 255))
            cv2.circle(display, (sx, sy), 8, color, -1)
            cv2.drawMarker(display, (sx, sy), color, cv2.MARKER_CROSS, 16, 2)
            label = f"{i + 1}:{DIR_LABELS.get(direction, direction)}"
            cv2.putText(display, label, (sx + 12, sy + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            # Draw arrow from previous step
            if i > 0:
                px, py = int(steps[i - 1][1] * fw), int(steps[i - 1][2] * fh)
                cv2.arrowedLine(display, (px, py), (sx, sy), color, 2, tipLength=0.1)

        # Show current mouse position
        mx, my = int(last_mouse[0]), int(last_mouse[1])
        cv2.circle(display, (mx, my), 4, (255, 255, 255), -1)

        # Info overlay
        lines = [
            f"Steps: {len(steps)}  Zone: {zone_name or '(not saved)'}",
            "G: Gauche   D: Droite   H: Haut   B: Bas",
            "  -> place mouse where to click, then press key",
            "BACKSPACE: remove last   S: save zone   ESC: quit",
        ]
        for i, line in enumerate(lines):
            cv2.putText(display, line, (10, 20 + i * 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        # Step list on the right
        for i, (direction, fx, fy) in enumerate(steps[-8:]):
            sx, sy = int(fx * fw), int(fy * fh)
            color = COLORS.get(direction, (255, 255, 255))
            text = f"{i + 1}. {DIR_LABELS.get(direction, direction)} ({sx},{sy})"
            cv2.putText(display, text, (fw - 220, 20 + i * 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        cv2.imshow("Route Calibration", display)
        key = cv2.waitKey(50) & 0xFF

        if key == 27:  # ESC
            break

        if key == ord("s") or key == ord("S"):
            if not steps:
                log.warning("No steps defined, cannot save")
                continue
            cv2.destroyWindow("Route Calibration")
            zone_name = input("Enter zone name: ").strip()
            if not zone_name:
                zone_name = f"zone_{len(steps)}"
            _save_zone(config.route_file, zone_name, steps, fw, fh)
            log.info(f"Zone '{zone_name}' saved with {len(steps)} step(s)")
            saved = True
            cv2.namedWindow("Route Calibration", cv2.WINDOW_NORMAL)
            cv2.setMouseCallback("Route Calibration", mouse_cb)
            continue

        if key == 8 or key == 127:  # BACKSPACE / DEL
            if steps:
                removed = steps.pop()
                log.info(f"Removed step {len(steps) + 1}")

        if key in DIR_MAP:
            direction = DIR_MAP[key]
            rx = mx / fw
            ry = my / fh
            step_num = len(steps) + 1
            steps.append((direction, rx, ry))
            log.info(f"Step {step_num}: {DIR_LABELS[direction]} at ({mx}, {my})")

    cv2.destroyAllWindows()
    if not saved and steps:
        log.info(f"Calibration cancelled ({len(steps)} steps unsaved)")


def _save_zone(route_file: str, zone_name: str, steps: list, fw: int, fh: int):
    path = Path(route_file)
    data = {"zones": {}}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    steps_data = [{"dir": d, "x": round(fx, 4), "y": round(fy, 4)} for d, fx, fy in steps]
    data.setdefault("zones", {})[zone_name] = {"steps": steps_data}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Saved zone '{zone_name}' to {path}")
