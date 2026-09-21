import asyncio
import logging
from enum import Enum, unique
from typing import Any

import aiohttp

from src.config import Config

logger = logging.getLogger(__name__)


@unique
class NotificationType(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    EXCEPTION = "EXCEPTION"
    EMERGENCY = "EMERGENCY"


_TITLES = {
    NotificationType.INFO: "ℹ️ INFO",
    NotificationType.WARNING: "⚠️ WARNING",
    NotificationType.ERROR: "❌ ERROR",
    NotificationType.EXCEPTION: "❌ ERROR",
    NotificationType.EMERGENCY: "🚨 EMERGENCY",
}

_LOG_LEVELS = {
    NotificationType.INFO: logging.INFO,
    NotificationType.WARNING: logging.WARNING,
    NotificationType.ERROR: logging.ERROR,
    NotificationType.EXCEPTION: logging.ERROR,
    NotificationType.EMERGENCY: logging.CRITICAL,
}

# Keep references to fire-and-forget tasks so they are not garbage collected mid-flight
_background_tasks: set[asyncio.Task[Any]] = set()


def build_card(message: str, notification_type: NotificationType) -> dict[str, Any]:
    """Build a Google Chat cardsV2 payload for the message."""
    return {
        "cardsV2": [
            {
                "cardId": f"notify-{notification_type.value.lower()}",
                "card": {
                    "header": {"title": _TITLES[notification_type]},
                    "sections": [{"widgets": [{"textParagraph": {"text": message}}]}],
                },
            }
        ]
    }


async def async_report(
    message: str,
    notification_type: NotificationType = NotificationType.INFO,
    webhook_url: str | None = None,
) -> bool:
    """
    Send a notification to Google Chat.

    Outside production the message is only logged (at a level matching the type).
    In production it is posted to `webhook_url` (defaults to GOOGLE_CHAT_DEV_TEAM_WEBHOOK).

    Returns:
        bool: True if delivered (or logged in non-production), False otherwise
    """
    if Config.APP_MODE != "production":
        logger.log(_LOG_LEVELS[notification_type], "[%s] %s", notification_type.value, message)
        return True

    webhook_url = webhook_url or Config.GOOGLE_CHAT_DEV_TEAM_WEBHOOK
    if not webhook_url:
        logger.error(
            "GOOGLE_CHAT_DEV_TEAM_WEBHOOK is not configured, dropping notification: [%s] %s",
            notification_type.value,
            message,
        )
        return False

    card = build_card(message, notification_type)

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(webhook_url, json=card) as response,
        ):
            response.raise_for_status()
            return True
    except TimeoutError:
        logger.error("Timeout sending message to Google Chat: %s", message)
        return False
    except aiohttp.ClientError as e:
        logger.error("HTTP error sending message to Google Chat: %s", e)
        return False
    except Exception as e:
        logger.error("Failed to send message to Google Chat: %s", e)
        return False


def report(
    message: str,
    notification_type: NotificationType = NotificationType.INFO,
    webhook_url: str | None = None,
) -> bool:
    """
    Synchronous wrapper around `async_report`.

    Inside a running event loop the notification is scheduled in the background and
    True is returned immediately. Outside a loop it runs to completion.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        task = loop.create_task(async_report(message, notification_type, webhook_url))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return True

    try:
        return asyncio.run(async_report(message, notification_type, webhook_url))
    except RuntimeError:
        logger.log(_LOG_LEVELS[notification_type], "[%s] %s", notification_type.value, message)
        return True
