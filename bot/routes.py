import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class RouteManager:
    def __init__(self, route_path: str = "bot_routes.json"):
        self._path = Path(route_path)
        self._steps: List[dict] = []
        self._current_step = 0

    def load_zone(self, zone_name: str) -> bool:
        if not self._path.exists():
            return False
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"Failed to load route file {self._path}: {e}")
            return False
        zone = data.get("zones", {}).get(zone_name)
        if not zone:
            return False
        self._steps = zone.get("steps", [])
        self._current_step = 0
        log.info(f"Loaded route '{zone_name}' with {len(self._steps)} step(s)")
        return True

    def has_steps(self) -> bool:
        return len(self._steps) > 0

    def current_step(self) -> Optional[dict]:
        if self._current_step >= len(self._steps):
            return None
        return self._steps[self._current_step]

    def advance(self):
        self._current_step += 1
        if self._current_step >= len(self._steps):
            self._current_step = 0
            log.info("Route completed, looping back to start")

    def get_click_pos(self, fw: int, fh: int) -> Optional[Tuple[int, int]]:
        step = self.current_step()
        if not step:
            return None
        return (int(step["x"] * fw), int(step["y"] * fh))

    def current_dir(self) -> str:
        step = self.current_step()
        return step["dir"] if step else "?"
