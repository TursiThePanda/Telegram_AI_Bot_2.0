# clear_pycache.py
import os
import shutil
import logging

# Configure basic logging for the script itself
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def delete_pycache_dirs(start_path):
    """Recursively deletes all __pycache__ directories from a given start path."""
    logger.info(f"Searching for and deleting __pycache__ directories in: {start_path}")
    for dirpath, dirnames, filenames in os.walk(start_path):
        if '__pycache__' in dirnames:
            pycache_path = os.path.join(dirpath, '__pycache__')
            try:
                shutil.rmtree(pycache_path)
                logger.info(f"Successfully deleted: {pycache_path}")
            except OSError as e:
                logger.error(f"Error deleting {pycache_path}: {e}")
            # Remove from dirnames to prevent os.walk from trying to enter it or re-list it
            dirnames.remove('__pycache__') 
    logger.info("Finished deleting __pycache__ directories.")

if __name__ == '__main__':
    # --- MODIFICATION START ---
    # Get the directory where this script is located (e.g., /path/to/project/utilities)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Get the parent directory of the script's directory, which is the project root
    project_root = os.path.dirname(script_dir)
    # --- MODIFICATION END ---

    delete_pycache_dirs(project_root)
    logger.info("Pycache cleanup complete.")