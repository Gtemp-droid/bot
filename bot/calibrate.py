import ctypes
import logging
import time

import cv2
import numpy as np

from bot.capture import WindowCapture
from bot.config import BotConfig

log = logging.getLogger(__name__)

CALIB_WIN_NAME = "DofusBot Calibration"
STEP_SMALL = 1
STEP_LARGE = 10
CELL_STEP = 1

VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28

_last_arrow_time = 0
_ARROW_DEBOUNCE = 0.08


def run_calibration(config: BotConfig):
    cap = WindowCapture(config.window_title)
    if not cap.find_window():
        log.error("Game window not found. Start Dofus first.")
        return

    show_grid = True
    calibrating_hsv = False

    ranges = [{"lower": [35, 80, 80], "upper": [75, 255, 255]}]
    if config.resource_hsv_ranges:
        ranges[0] = config.resource_hsv_ranges[0]
    hsv_lower = np.array(ranges[0]["lower"], dtype=np.uint8)
    hsv_upper = np.array(ranges[0]["upper"], dtype=np.uint8)
    current_range_idx = 0

    log.info("=== Calibration Mode ===")
    log.info("GRID: Arrows=move  Shift+arrow=fast  W/E=width  A/D=height")
    log.info("SHEAR: Z/X=x  N/M=y  R=reset all")
    log.info("HSV manual tuning (H=toggle mask):")
    log.info("  1/2=Hlo  3/4=Hhi  5/6=Slo  7/8=Shi  9/0=Vlo  -/=Vhi")
    log.info("  [/]=minArea  ;/'=maxArea  Shift=x5")
    log.info("  S=save as profile  U=list profiles  O=load profile  Q=quit")
    log.info("")

    _click_pos = []
    cv2.namedWindow(CALIB_WIN_NAME)

    def _mouse_cb(event, mx, my, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            _click_pos[:] = [mx, my]
            _mouse_cb.last_click = (mx, my)
    _mouse_cb.last_click = None

    cv2.setMouseCallback(CALIB_WIN_NAME, _mouse_cb)

    while True:
        frame = cap.capture()
        if frame is None:
            time.sleep(0.5)
            continue

        if _click_pos:
            cx, cy = _click_pos
            _sample_at(cx, cy, frame, hsv_lower, hsv_upper, config)
            calibrating_hsv = True
            _click_pos.clear()

        display = frame.copy()
        if show_grid:
            _draw_grid(display, config)
        if calibrating_hsv:
            display = _draw_hsv_mask(display, frame, config, hsv_lower, hsv_upper)

        if hasattr(_mouse_cb, 'last_click'):
            cv2.circle(display, _mouse_cb.last_click, 6, (0, 0, 255), 2)
            cv2.circle(display, _mouse_cb.last_click, 2, (0, 0, 255), -1)

        _ui(display, config, show_grid, calibrating_hsv, hsv_lower, hsv_upper)
        cv2.imshow(CALIB_WIN_NAME, display)

        key = cv2.waitKey(30)
        shift = _shift_pressed()

        if key != -1:
            k = key & 0xFF

            if k == ord('q'):
                break
            elif k == ord('g'):
                show_grid = not show_grid
            elif k == ord('h'):
                calibrating_hsv = not calibrating_hsv
                log.info(f"HSV mask: {'ON' if calibrating_hsv else 'OFF'}")
            elif k == ord('['):
                config.resource_min_area = max(1, config.resource_min_area - 1)
            elif k == ord(']'):
                config.resource_min_area = min(500, config.resource_min_area + 1)
            elif k == ord(';'):
                config.resource_max_area = max(config.resource_min_area + 1, config.resource_max_area - 5)
            elif k == ord("'"):
                config.resource_max_area = min(2000, config.resource_max_area + 5)
            elif k == ord('t'):
                log.info(f"Current range: H=[{hsv_lower[0]}-{hsv_upper[0]}]")
            elif k == ord('u'):
                if not config.profiles:
                    log.info("No saved profiles")
                else:
                    log.info("Profiles:")
                    for p in config.profiles:
                        log.info(f"  {p['name']}: H=[{p['hsv_ranges'][0]['lower'][0]}-{p['hsv_ranges'][0]['upper'][0]}]")
            elif k == ord('o'):
                if not config.profiles:
                    log.info("No profiles to load")
                else:
                    names = [p['name'] for p in config.profiles]
                    log.info(f"Profiles: {names}")
                    pick = input("Load profile: ").strip()
                    if config.apply_profile(pick):
                        hsv_lower[:] = config.resource_hsv_ranges[0]["lower"]
                        hsv_upper[:] = config.resource_hsv_ranges[0]["upper"]
                        calibrating_hsv = True
                        log.info(f"Loaded profile '{pick}'")
                    else:
                        log.info(f"Profile '{pick}' not found")
            elif k == ord('r'):
                config.grid_origin_x = 140.0
                config.grid_origin_y = 188.0
                config.cell_width = 86.0
                config.cell_height = 43.0
                config.grid_shear_x = 0.0
                config.grid_shear_y = 0.0
                log.info("Grid reset")
            elif k == ord('s'):
                cv2.putText(display, "Enter profile name in console...",
                            (8, display.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                cv2.imshow(CALIB_WIN_NAME, display)
                cv2.waitKey(1)
                name = input("Profile name (e.g., wheat, wood): ").strip()
                if not name:
                    log.info("Save cancelled")
                    break
                t_min = float(input(f"Harvest min seconds [{config.harvest_wait_min}]: ") or config.harvest_wait_min)
                t_max = float(input(f"Harvest max seconds [{config.harvest_wait_max}]: ") or config.harvest_wait_max)
                config.save_profile(
                    name, [{"lower": hsv_lower.tolist(), "upper": hsv_upper.tolist()}],
                    config.resource_min_area, config.resource_max_area,
                    t_min, t_max,
                )
                config.resource_hsv_ranges = [{"lower": hsv_lower.tolist(), "upper": hsv_upper.tolist()}]
                config.harvest_wait_min = t_min
                config.harvest_wait_max = t_max
                config.save()
                log.info(f"Profile '{name}' saved (H=[{hsv_lower[0]}-{hsv_upper[0]}])")
                log.info(f"Profiles available: {[p['name'] for p in config.profiles]}")

            elif k == ord('w'):
                step = CELL_STEP * 5 if shift else CELL_STEP
                config.cell_width = max(10, config.cell_width - step)
            elif k == ord('e'):
                step = CELL_STEP * 5 if shift else CELL_STEP
                config.cell_width = min(200, config.cell_width + step)
            elif k == ord('a'):
                step = CELL_STEP * 5 if shift else CELL_STEP
                config.cell_height = max(10, config.cell_height - step)
            elif k == ord('d'):
                step = CELL_STEP * 5 if shift else CELL_STEP
                config.cell_height = min(200, config.cell_height + step)

            elif k == ord('z'):
                step = 0.5 if shift else 0.1
                config.grid_shear_x = max(-5.0, config.grid_shear_x - step)
            elif k == ord('x'):
                step = 0.5 if shift else 0.1
                config.grid_shear_x = min(5.0, config.grid_shear_x + step)
            elif k == ord('n'):
                step = 0.5 if shift else 0.1
                config.grid_shear_y = max(-5.0, config.grid_shear_y - step)
            elif k == ord('m'):
                step = 0.5 if shift else 0.1
                config.grid_shear_y = min(5.0, config.grid_shear_y + step)

            elif _adjust_hsv(k, shift, hsv_lower, hsv_upper):
                calibrating_hsv = True
                pass

        _handle_arrows(config, shift)

    cv2.destroyAllWindows()
    cap.close()
    log.info("Calibration done")


def _adjust_hsv(k: int, shift: bool, lo: np.ndarray, hi: np.ndarray) -> bool:
    s = 5 if shift else 1
    ch = False
    if k == ord('1'):
        lo[0] = max(0, int(lo[0]) - s); ch = True
    elif k == ord('2'):
        lo[0] = min(179, int(lo[0]) + s); ch = True
    elif k == ord('3'):
        hi[0] = max(0, int(hi[0]) - s); ch = True
    elif k == ord('4'):
        hi[0] = min(179, int(hi[0]) + s); ch = True
    elif k == ord('5'):
        lo[1] = max(0, int(lo[1]) - s); ch = True
    elif k == ord('6'):
        lo[1] = min(255, int(lo[1]) + s); ch = True
    elif k == ord('7'):
        hi[1] = max(0, int(hi[1]) - s); ch = True
    elif k == ord('8'):
        hi[1] = min(255, int(hi[1]) + s); ch = True
    elif k == ord('9'):
        lo[2] = max(0, int(lo[2]) - s); ch = True
    elif k == ord('0'):
        lo[2] = min(255, int(lo[2]) + s); ch = True
    elif k == ord('-') or k == ord('_'):
        hi[2] = max(0, int(hi[2]) - s); ch = True
    elif k == ord('=') or k == ord('+'):
        hi[2] = min(255, int(hi[2]) + s); ch = True
    return ch


def _handle_arrows(config: BotConfig, shift: bool):
    global _last_arrow_time
    now = time.time()
    if now - _last_arrow_time < _ARROW_DEBOUNCE:
        return
    step = STEP_LARGE if shift else STEP_SMALL
    moved = False
    if ctypes.windll.user32.GetAsyncKeyState(VK_LEFT) & 0x8000:
        config.grid_origin_x = max(0, config.grid_origin_x - step); moved = True
    elif ctypes.windll.user32.GetAsyncKeyState(VK_RIGHT) & 0x8000:
        config.grid_origin_x = min(2000, config.grid_origin_x + step); moved = True
    elif ctypes.windll.user32.GetAsyncKeyState(VK_UP) & 0x8000:
        config.grid_origin_y = max(0, config.grid_origin_y - step); moved = True
    elif ctypes.windll.user32.GetAsyncKeyState(VK_DOWN) & 0x8000:
        config.grid_origin_y = min(2000, config.grid_origin_y + step); moved = True
    if moved:
        _last_arrow_time = now


def _draw_grid(display: np.ndarray, config: BotConfig):
    for i in range(config.grid_rows):
        for j in range(config.grid_cols):
            sx = int(config.grid_origin_x + (j - i) * (config.cell_width / 2))
            sy = int(config.grid_origin_y + (i + j) * (config.cell_height / 2))
            col = (0, 255, 255) if i == 0 or j == 0 else (100, 200, 100)
            cv2.circle(display, (sx, sy), 2, col, -1)
            if i == 0 and j % 2 == 0:
                cv2.putText(display, str(j), (sx - 8, sy - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 0), 1)
    ox, oy = int(config.grid_origin_x), int(config.grid_origin_y)
    cv2.line(display, (ox - 15, oy), (ox + 15, oy), (0, 0, 255), 1)
    cv2.line(display, (ox, oy - 15), (ox, oy + 15), (0, 0, 255), 1)
    cr, cc = config.grid_rows // 2, config.grid_cols // 2
    mx = int(config.grid_origin_x + (cc - cr) * (config.cell_width / 2))
    my = int(config.grid_origin_y + (cr + cc) * (config.cell_height / 2))
    cv2.drawMarker(display, (mx, my), (255, 255, 0), cv2.MARKER_CROSS, 12, 1)
    cv2.putText(display, "CENTER", (mx + 6, my + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1)


def _draw_hsv_mask(display: np.ndarray, frame: np.ndarray,
                   config: BotConfig,
                   lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    overlay = frame.copy()
    overlay[mask > 0] = (0, 255, 0)
    display[:] = cv2.addWeighted(display, 0.7, overlay, 0.3, 0)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < config.resource_min_area or area > config.resource_max_area:
            continue
        M = cv2.moments(cnt)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            cv2.circle(display, (cx, cy), 5, (0, 255, 255), 2)
            cv2.drawMarker(display, (cx, cy), (0, 255, 255), cv2.MARKER_CROSS, 10, 1)

    margin = 10
    small_w = display.shape[1] // 4
    ratio = small_w / mask.shape[1]
    small_h = int(mask.shape[0] * ratio)
    mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    mask_small = cv2.resize(mask_bgr, (small_w, small_h))
    x_off = display.shape[1] - small_w - margin
    y_off = margin
    display[y_off:y_off + small_h, x_off:x_off + small_w] = mask_small
    cv2.rectangle(display, (x_off, y_off), (x_off + small_w, y_off + small_h), (0, 255, 0), 1)
    return display


def _ui(display: np.ndarray, config: BotConfig, show_grid: bool, hsv_on: bool,
        lower: np.ndarray, upper: np.ndarray):
    lines = [
        f"Origin({config.grid_origin_x:.0f},{config.grid_origin_y:.0f}) "
        f"Cell={config.cell_width:.1f}x{config.cell_height:.1f}  "
        f"Shear({config.grid_shear_x:.2f},{config.grid_shear_y:.2f})",
        f"Grid={'ON' if show_grid else 'OFF'}  HSV={'ON' if hsv_on else 'OFF'}",
    ]
    if hsv_on:
        lines.append(
            f"H:[{lower[0]:>3d}-{upper[0]:>3d}]  "
            f"S:[{lower[1]:>3d}-{upper[1]:>3d}]  "
            f"V:[{lower[2]:>3d}-{upper[2]:>3d}]  "
            f"Area:[{config.resource_min_area}-{config.resource_max_area}]")
        lines.append("1/2=Hlo 3/4=Hhi 5/6=Slo 7/8=Shi 9/0=Vlo -=/+Vhi  [/]=min  ;/'=max")
    lines.append(f"Active: {config.active_profile or '(none)'}  Profiles: {len(config.profiles)}")
    for i, line in enumerate(lines):
        cv2.putText(display, line, (8, 15 + i * 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1)


def _sample_at(mx: int, my: int, frame: np.ndarray,
               hsv_lower: np.ndarray, hsv_upper: np.ndarray,
               config: BotConfig):
    if frame is None:
        return
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hh, ww = frame.shape[:2]
    mx = max(0, min(ww - 1, mx))
    my = max(0, min(hh - 1, my))
    ph, ps, pv = [int(v) for v in hsv[my, mx]]
    log.info(f"Click ({mx},{my}) -> H={ph} S={ps} V={pv}")

    half_h = 10
    lower = np.array([max(0, ph - half_h), max(0, ps - 60), max(0, pv - 60)], dtype=np.uint8)
    upper = np.array([min(179, ph + half_h), min(255, ps + 60), min(255, pv + 60)], dtype=np.uint8)

    mask = cv2.inRange(hsv, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    areas = [cv2.contourArea(c) for c in contours if 5 < cv2.contourArea(c) < 500]
    if areas:
        config.resource_min_area = max(5, int(min(areas)) - 5)
        config.resource_max_area = int(max(areas)) + 10
        log.info(f"Area range: {config.resource_min_area}-{config.resource_max_area}")

    hsv_lower[:] = lower
    hsv_upper[:] = upper
    log.info(f"Range: H=[{lower[0]}-{upper[0]}]  S=[{lower[1]}-{upper[1]}]  V=[{lower[2]}-{upper[2]}]")


def _shift_pressed() -> bool:
    return ctypes.windll.user32.GetKeyState(0x10) & 0x80 != 0
