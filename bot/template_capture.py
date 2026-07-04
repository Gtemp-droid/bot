import logging
from pathlib import Path

import cv2

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
    log.info(f"Templates saved to: {TEMPLATE_DIR}")
    log.info("")
    log.info("How to capture an action button (e.g. 'Couper'):")
    log.info("  1. In Dofus, RIGHT-click a resource so the action menu appears")
    log.info("  2. Press SPACE in this window to freeze the frame")
    log.info("  3. A crosshair appears -- click-and-drag a box around the action button")
    log.info("  4. Press ENTER to confirm, then type a name")
    log.info("  5. Name it 'action' for the bot to auto-detect it")
    log.info("")
    log.info("Examples: name='action' for generic, or 'couper', 'recolter', etc.")
    log.info("")
    log.info("Press Q to quit")
    log.info("")

    win_name = "Template Capture"
    cv2.namedWindow(win_name)

    while True:
        frame = cap.capture()
        if frame is None:
            continue

        cv2.imshow(win_name, frame)
        key = cv2.waitKey(30) & 0xFF

        if key == ord('q'):
            break
        elif key == ord(' '):
            frozen = frame.copy()
            cv2.imshow(win_name, frozen)

            cv2.putText(frozen, "Drag a box around the button, then press ENTER",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frozen, "Press ESC to cancel",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            cv2.imshow(win_name, frozen)

            roi = cv2.selectROI(win_name, frozen, False)
            cv2.destroyWindow(win_name)
            cv2.namedWindow(win_name)

            if roi[2] > 10 and roi[3] > 10:
                x, y, w, h = [int(v) for v in roi]
                cropped = frozen[y:y + h, x:x + w]
                name = input("Template name (enter 'action' for the bot): ").strip()
                if name:
                    path = TEMPLATE_DIR / f"{name}.png"
                    cv2.imwrite(str(path), cropped)
                    log.info(f"Saved '{name}' ({w}x{h}) -> {path}")
                else:
                    log.info("Cancelled")
            else:
                log.info("Selection cancelled")

    cv2.destroyAllWindows()
    cap.close()
