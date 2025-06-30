# src/core/tasks.py
"""
Defines background tasks that run periodically while the bot is active.
"""
import asyncio
import logging
import time
import os
from telegram.ext import Application
from telegram.error import Forbidden
import src.config as config

from src import services

logger = logging.getLogger(__name__)

async def performance_report_task():
    """Periodically exports performance metrics to a JSON file."""
    while True:
        try:
            try:
                await asyncio.sleep(600) # Check every 10 minutes
            except asyncio.CancelledError:
                logger.info("Performance report task is stopping.")
                break

            date_str = time.strftime("%Y-%m-%d_%H-%M-%S")
            report_path = os.path.join(config.LOGS_DIR, f"performance_report_{date_str}.json")
            await services.monitoring.export_performance_report(report_path)
        except Exception as e:
            logger.error(f"Error in performance report task: {e}", exc_info=True)

async def _notify_owner_of_status_change(application: Application):
    """
    Asynchronously sends a notification to the bot owner.
    """
    if not config.BOT_OWNER_ID:
        return

    logger.info(f"Sending 'AI ONLINE' notification to bot owner (ID: {config.BOT_OWNER_ID}).")
    notification_text = "🟢 The AI is now online and ready to chat!"

    try:
        await application.bot.send_message(chat_id=config.BOT_OWNER_ID, text=notification_text)
    except Forbidden:
        logger.warning(f"Failed to send notification to owner {config.BOT_OWNER_ID}: Bot might be blocked.")
    except Exception as e:
        logger.error(f"Failed to send notification to owner {config.BOT_OWNER_ID}: {e}")

    logger.info("Finished sending status notification to owner.")


async def health_check_task(application: Application):
    """Periodically checks the connection to the AI model server."""
    is_online = await services.ai_models.is_service_online()
    application.bot_data['ai_service_online'] = is_online

    while True:
        try:
            await asyncio.sleep(60) # Check every minute
        except asyncio.CancelledError:
            logger.info("Health check task is stopping.")
            break

        try:
            previous_status = application.bot_data.get('ai_service_online', False)
            current_status = await services.ai_models.is_service_online()
            application.bot_data['ai_service_online'] = current_status

            if previous_status is False and current_status is True:
                status_text = "✅ Online"
                logger.info(f"AI model server status changed to: {status_text}. Triggering owner notification.")

                # Run the notification process in the background for the owner only
                asyncio.create_task(_notify_owner_of_status_change(application))

            elif previous_status is True and current_status is False:
                status_text = "❌ Offline"
                logger.info(f"AI model server status changed to: {status_text}")
        except Exception as e:
            logger.warning(f"Failed to check AI model connection: {e}", exc_info=True)

async def unblock_users_task(application: Application):
    """Periodically checks for and removes expired timed blocks."""
    while True:
        try:
            await asyncio.sleep(300) # Check every 5 minutes
        except asyncio.CancelledError:
            logger.info("Unblock users task is stopping.")
            break

        try:
            users_to_unblock = await services.database.get_timed_unblocks()
            if users_to_unblock:
                for user_id in users_to_unblock:
                    await services.database.unblock_user_by_id(user_id)
                    logger.info(f"Automatically unblocked user {user_id} due to timed block expiration.")
        except Exception as e:
            logger.error(f"Error in unblock users task: {e}", exc_info=True)