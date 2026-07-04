import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class HSVProfile:
    name: str
    hsv_ranges: list = field(default_factory=lambda: [
        {"lower": [35, 80, 80], "upper": [75, 255, 255]},
    ])
    min_area: int = 10
    max_area: int = 300
    harvest_wait_min: float = 3.0
    harvest_wait_max: float = 5.0


@dataclass
class BotConfig:
    window_title: str = "Dofus Retro"
    process_name: str = "Dofus.exe"

    grid_origin_x: float = 140.0
    grid_origin_y: float = 188.0
    cell_width: float = 86.0
    cell_height: float = 43.0
    grid_shear_x: float = 0.0
    grid_shear_y: float = 0.0
    grid_rows: int = 21
    grid_cols: int = 14

    resource_hsv_ranges: list = field(default_factory=lambda: [
        {"lower": [35, 80, 80], "upper": [75, 255, 255]},
    ])
    resource_min_area: int = 10
    resource_max_area: int = 300

    harvest_wait_min: float = 3.0
    harvest_wait_max: float = 5.0
    map_load_timeout: float = 15.0
    resource_search_interval: float = 0.5
    move_recheck_interval: float = 0.8
    explore_wait: float = 1.5
    click_button: str = "right"
    move_duration: float = 0.2
    map_wait_time: float = 3.0

    log_level: str = "INFO"
    save_screenshots: bool = True
    screenshot_dir: str = "screenshots"
    debug_overlay: bool = True

    profiles: list = field(default_factory=list)
    active_profile: str = ""
    route_file: str = "bot_routes.json"
    active_zone: str = ""

    @classmethod
    def load(cls, path: str = "bot_config.json") -> "BotConfig":
        if not os.path.exists(path):
            return cls()
        with open(path) as f:
            data = json.load(f)
        data = cls._migrate(data)
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        cfg = cls(**valid)
        if len(cfg.resource_hsv_ranges) > 1:
            log.warning(f"Keeping only first HSV range ({len(cfg.resource_hsv_ranges)} found)")
            cfg.resource_hsv_ranges = [cfg.resource_hsv_ranges[0]]
            cfg.save()
            log.info("Config auto-fixed to single range")
        return cfg

    @staticmethod
    def _migrate(data: dict) -> dict:
        if "resource_hsv_lower" in data or "resource_hsv_upper" in data:
            old_lower = data.pop("resource_hsv_lower", [35, 80, 80])
            old_upper = data.pop("resource_hsv_upper", [75, 255, 255])
            if "resource_hsv_ranges" not in data:
                data["resource_hsv_ranges"] = [
                    {"lower": old_lower, "upper": old_upper},
                ]
        return data

    def save(self, path: str = "bot_config.json"):
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    def apply_profile(self, name: str) -> bool:
        for p in self.profiles:
            if p["name"] == name:
                self.resource_hsv_ranges = p["hsv_ranges"]
                self.resource_min_area = p["min_area"]
                self.resource_max_area = p["max_area"]
                self.harvest_wait_min = p["harvest_wait_min"]
                self.harvest_wait_max = p["harvest_wait_max"]
                self.active_profile = name
                return True
        return False

    def save_profile(self, name: str, hsv_ranges: list,
                     min_area: int, max_area: int,
                     harvest_min: float, harvest_max: float):
        entry = {"name": name, "hsv_ranges": hsv_ranges,
                 "min_area": min_area, "max_area": max_area,
                 "harvest_wait_min": harvest_min,
                 "harvest_wait_max": harvest_max}
        for i, p in enumerate(self.profiles):
            if p["name"] == name:
                self.profiles[i] = entry
                return
        self.profiles.append(entry)
