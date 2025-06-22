# src/core/tasks.py
"""
Defines background tasks that run periodically while the bot is active.
"""
import asyncio
import logging
import time
import os
from telegram.ext import Application
from telegram.error import Forbidden # Import the Forbidden error for handling blocked users
import src.config as config

from src import services

logger = logging.getLogger(__name__)

async def performance_report_task():
    """Periodically exports performance metrics to a JSON file."""
    while True:
        try:
            # Handle sleep cancellation directly within the loop
            try:
                await asyncio.sleep(600)  # Export every 10 minutes
            except asyncio.CancelledError:
                logger.info("Performance report task is stopping.")
                break # Exit the loop cleanly on cancellation

            date_str = time.strftime("%Y-%m-%d_%H-%M-%S")
            report_path = os.path.join(config.LOGS_DIR, f"performance_report_{date_str}.json")
            await services.monitoring.export_performance_report(report_path)
        except Exception as e:
            logger.error(f"Error in performance report task: {e}", exc_info=True)

# --- NEW FUNCTION START ---
async def _notify_users_of_status_change(application: Application, user_ids: list[int]):
    """
    Asynchronously sends a notification to a list of users.
    Includes error handling for users who have blocked the bot.
    """
    logger.info(f"Sending 'AI ONLINE' notification to {len(user_ids)} users.")
    notification_text = "🟢 The AI is now online and ready to chat!"
    
    for user_id in user_ids:
        try:
            await application.bot.send_message(chat_id=user_id, text=notification_text)
            # Add a small delay between messages to avoid hitting Telegram's rate limits
            await asyncio.sleep(0.1) 
        except Forbidden:
            # This error occurs if the user has blocked the bot.
            logger.warning(f"Failed to send notification to user {user_id}: Bot was blocked.")
        except Exception as e:
            logger.error(f"Failed to send notification to user {user_id}: {e}")

    logger.info("Finished sending status notifications.")
# --- NEW FUNCTION END ---

async def health_check_task(application: Application):
    """Periodically checks the connection to the AI model server."""
    is_online = await services.ai_models.is_service_online()
    application.bot_data['ai_service_online'] = is_online
    
    while True:
        # Handle sleep cancellation directly within the loop
        try:
            await asyncio.sleep(60) # Check every minute
        except asyncio.CancelledError:
            logger.info("Health check task is stopping.")
            break # Exit the loop cleanly on cancellation

        try:
            previous_status = application.bot_data.get('ai_service_online', False)
            current_status = await services.ai_models.is_service_online()
            application.bot_data['ai_service_online'] = current_status

            # --- MODIFICATION START ---
            # Check for the specific transition from OFFLINE to ONLINE
            if previous_status is False and current_status is True:
                status_text = "✅ Online"
                logger.info(f"AI model server status changed to: {status_text}. Triggering user notifications.")
                
                # Get all user IDs that the bot knows about from its persistence data
                user_ids = list(application.user_data.keys())
                
                # Run the notification process in the background so it doesn't block this health check task
                if user_ids:
                    asyncio.create_task(_notify_users_of_status_change(application, user_ids))
            
            elif previous_status is True and current_status is False:
                 # The AI has just gone offline, just log it.
                status_text = "❌ Offline"
                logger.info(f"AI model server status changed to: {status_text}")
            # --- MODIFICATION END ---
        except Exception as e:
            logger.warning(f"Failed to check AI model connection: {e}", exc_info=True)