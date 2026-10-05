import asyncio

from automation.weave_driver import WeaveDriver
from core.config import config
from core.logging import configure_logging
from worker.worker import Worker


def main() -> None:
    configure_logging(config.log_level)
    asyncio.run(Worker(driver_factory=WeaveDriver).run_forever())


if __name__ == "__main__":
    main()
