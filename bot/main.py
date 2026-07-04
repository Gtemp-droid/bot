import argparse
import logging
import sys

from bot.config import BotConfig
from bot.state import HarvestBot


def setup_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def main():
    parser = argparse.ArgumentParser(description="Dofus 1.29 HarvestBot (CV only)")
    parser.add_argument("--config", default="bot_config.json", help="Config file path")
    parser.add_argument("--log-level", default=None, help="DEBUG/INFO/WARNING")
    parser.add_argument("--calibrate", action="store_true", help="Run calibration tool")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan and log only, no mouse clicks")
    parser.add_argument("--profile", default=None,
                        help="Load named HSV profile (e.g., --profile wheat)")
    parser.add_argument("--calibrate-route", action="store_true",
                        help="Define navigation route for zone (keyboard: G/H/B/D)")
    parser.add_argument("--run-route", default=None, metavar="ZONE",
                        help="Test a navigation route (5s between clicks, no harvesting)")
    parser.add_argument("--route-delay", type=float, default=5.0,
                        help="Delay between route clicks in seconds (default: 5.0)")
    parser.add_argument("--calibrate-character", action="store_true",
                        help="Calibrate character detection (motion diff)")
    parser.add_argument("--capture-templates", action="store_true",
                        help="Capture UI template images")
    parser.add_argument("--list-profiles", action="store_true",
                        help="List saved profiles and exit")
    parser.add_argument("--zone", default=None,
                        help="Zone name for map navigation route (e.g., --zone zone_a)")
    args = parser.parse_args()

    config = BotConfig.load(args.config)
    if args.log_level:
        config.log_level = args.log_level

    setup_logging(config.log_level)
    log = logging.getLogger(__name__)

    if args.list_profiles:
        if not config.profiles:
            log.info("No saved profiles")
        else:
            log.info(f"Profiles ({len(config.profiles)}):")
            for p in config.profiles:
                r = p["hsv_ranges"][0]
                log.info(f"  {p['name']}: "
                         f"H=[{r['lower'][0]}-{r['upper'][0]}] "
                         f"wait={p['harvest_wait_min']}-{p['harvest_wait_max']}s")
        return

    if args.calibrate_character:
        from bot.character_calibrate import run_character_calibration
        run_character_calibration(config)
        return

    if args.capture_templates:
        from bot.template_capture import capture_templates
        capture_templates()
        return

    if args.calibrate:
        from bot.calibrate import run_calibration
        run_calibration(config)
        config.save(args.config)
        return

    if args.calibrate_route:
        from bot.route_calibrate import calibrate_route
        calibrate_route(config)
        return

    if args.run_route:
        from bot.route_runner import run_route
        run_route(config, args.run_route, args.route_delay)
        return

    if args.profile:
        if not config.apply_profile(args.profile):
            log.error(f"Profile '{args.profile}' not found. Use --list-profiles to see available.")
            return
        log.info(f"Using profile: {args.profile}")

    if args.zone:
        config.active_zone = args.zone
        log.info(f"Using zone: {args.zone}")

    bot = HarvestBot(config, dry_run=args.dry_run)
    try:
        bot.run()
    except KeyboardInterrupt:
        log.info("Shutdown")
        bot.stop()


if __name__ == "__main__":
    main()
