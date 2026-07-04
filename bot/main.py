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
    parser.add_argument("--capture-templates", action="store_true",
                        help="Capture UI template images")
    args = parser.parse_args()

    if args.capture_templates:
        from bot.template_capture import capture_templates
        capture_templates()
        return

    config = BotConfig.load(args.config)
    if args.log_level:
        config.log_level = args.log_level

    setup_logging(config.log_level)
    log = logging.getLogger(__name__)

    if args.calibrate:
        from bot.calibrate import run_calibration
        run_calibration(config)
        config.save(args.config)
        return

    bot = HarvestBot(config, dry_run=args.dry_run)
    try:
        bot.run()
    except KeyboardInterrupt:
        log.info("Shutdown")
        bot.stop()


if __name__ == "__main__":
    main()
