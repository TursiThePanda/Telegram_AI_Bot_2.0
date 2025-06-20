# src/core/tasks.py
"""
Defines background tasks that run periodically while the bot is active.
"""
import asyncio
import logging
import time
import os
from telegram.ext import Application
import src.config as config

# In later steps, we will replace these imports with our new service modules.
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
            logger.error(f"Error in performance report task: {e}", exc_info=True) # Add exc_info=True for full traceback

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

            if previous_status != current_status:
                status_text = "✅ Online" if current_status else "❌ Offline"
                logger.info(f"AI model server status changed to: {status_text}")
        except Exception as e:
            logger.warning(f"Failed to check AI model connection: {e}", exc_info=True) # Add exc_info=True