"""
Entry point for running the app as a standalone script (batch jobs, one-off
processing, etc.) instead of behind uvicorn.

    python -m src.app.main
"""

import asyncio
import logging

from boot import app_boot
from src.db.async_mongo import mongo_manager
from src.db.async_mysql import mysql_manager
from src.report.notify import NotificationType, async_report
from src.utils.performance import performance_tracker

logger = logging.getLogger(__name__)


async def main() -> None:
    await app_boot()

    try:
        await mongo_manager.initialize()
        await mysql_manager.initialize()

        # Your work goes here, e.g.
        # users = await get_collection("users")  # noqa: ERA001
        # rows = await fetch_one("SELECT 1")  # noqa: ERA001
        logger.info("App started in %.3f seconds", performance_tracker.get_boot_time() or 0.0)

    except Exception as e:
        logger.error("Critical error in main execution: %s", e, exc_info=True)
        await async_report(f"Critical error in main execution: {e}", NotificationType.ERROR)
        raise
    finally:
        await mongo_manager.close()
        await mysql_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
