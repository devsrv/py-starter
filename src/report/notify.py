import asyncio
import aiohttp
import json
from ..config import Config
from enum import Enum, unique
from typing import Optional

@unique
class NotificationType(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    EXCEPTION = "EXCEPTION"
    EMERGENCY = "EMERGENCY"

async def async_report(message, notification_type: NotificationType=NotificationType.INFO, webhook_url=Config.GOOGLE_CHAT_DEV_TEAM_WEBHOOK):
    """
    Send a notification to Google Chat
    
    Args:
        message (str): The message to send
        notification_type (NotificationType): Type of notification
        webhook_url (str): The Google Chat webhook URL
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Format based on notification type
    if notification_type == NotificationType.WARNING:
        title = "⚠️ WARNING"
        color = "#FFC107"  # Yellow
    elif notification_type == NotificationType.ERROR or notification_type == NotificationType.EXCEPTION:
        title = "❌ ERROR"
        color = "#F44336"  # Red
    elif notification_type == NotificationType.EMERGENCY:
        title = "🚨 EMERGENCY"
        color = "#E91E63"  # Pink
    else:
        title = "ℹ️ INFO"
        color = "#2196F3"  # Blue
    
    # Create the message card
    card = {
        "cards": [
            {
                "header": {
                    "title": title,
                },
                "sections": [
                    {
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": message
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    # Post the message to Google Chat asynchronously
    try:
        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(webhook_url, json=card) as response:
                response.raise_for_status()
                return True
    except asyncio.TimeoutError:
        print(f"Timeout sending message to Google Chat: {message}")
        return False
    except aiohttp.ClientError as e:
        print(f"HTTP error sending message to Google Chat: {e}")
        return False
    except Exception as e:
        print(f"Failed to send message to Google Chat: {e}")
        return False
    
def report(
    message: str, 
    notification_type: NotificationType = NotificationType.INFO, 
    webhook_url: Optional[str] = None
) -> bool:
    """
    Synchronous wrapper for backward compatibility.
    This allows existing sync code to still work while gradually migrating to async.
    """
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a task
            task = loop.create_task(async_report(message, notification_type, webhook_url))
            # Don't wait for it to complete to avoid blocking
            return True
        else:
            # If no loop is running, run the async function
            return asyncio.run(async_report(message, notification_type, webhook_url))
    except RuntimeError:
        # If we can't use async, fall back to synchronous version
        print(f"[{notification_type.value}] {message}")
        return True