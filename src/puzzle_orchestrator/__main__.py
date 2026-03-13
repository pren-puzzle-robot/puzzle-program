import logging
import os

from .orchestrator import PuzzleOrchestrator


def configure_logging() -> None:
    level_name = os.getenv("PUZZLE_LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    orchestrator = PuzzleOrchestrator()
    try:
        result = orchestrator.run_once()
    except Exception:
        logger.exception("Puzzle run failed")
        raise

    logger.info("Puzzle run completed with result=%s", result)
    print(result)


if __name__ == "__main__":
    main()
