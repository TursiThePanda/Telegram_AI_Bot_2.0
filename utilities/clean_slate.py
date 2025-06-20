# clean_slate.py
import os
import shutil
import logging

# Configure basic logging for the script itself
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def delete_directory(path):
    """Deletes a directory if it exists."""
    if os.path.exists(path) and os.path.isdir(path):
        try:
            shutil.rmtree(path)
            logger.info(f"Successfully deleted: {path}")
        except OSError as e:
            logger.error(f"Error deleting {path}: {e}")
    else:
        logger.info(f"Directory not found or not a directory, skipping: {path}")

def main():
    """Performs a clean slate operation for the bot project."""
    project_root = os.getcwd()
    logger.info(f"Starting clean slate operation in: {project_root}")

    # 1. Delete all __pycache__ directories
    logger.info("Searching for and deleting __pycache__ directories...")
    for dirpath, dirnames, filenames in os.walk(project_root):
        if '__pycache__' in dirnames:
            pycache_path = os.path.join(dirpath, '__pycache__')
            delete_directory(pycache_path)
            # Remove from dirnames to prevent os.walk from trying to enter it
            dirnames.remove('__pycache__') 
    logger.info("Finished deleting __pycache__ directories.")

    # 2. Delete the /data directory
    logger.info("Deleting the /data directory...")
    data_dir_path = os.path.join(project_root, 'data')
    delete_directory(data_dir_path)
    logger.info("Finished deleting the /data directory.")

    logger.info("Clean slate operation complete. Your bot environment is now reset.")
    logger.info("Remember to run 'python main.py' to restart your bot.")

if __name__ == '__main__':
    main()