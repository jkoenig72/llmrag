import logging
import os
from collections import defaultdict

from config import BASE_OUTPUT_FOLDER
from file_utils import save_summary

# Set up logging
def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(BASE_OUTPUT_FOLDER, "scraper.log")),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def summarize_md_counts():
    """Scan the output folder and count markdown files by product."""
    summary_counts = defaultdict(int)
    logger = logging.getLogger(__name__)
    
    logger.info(f"\n🔍 Scanning '{BASE_OUTPUT_FOLDER}' for markdown files...")
    
    try:
        for product_dir in os.listdir(BASE_OUTPUT_FOLDER):
            full_path = os.path.join(BASE_OUTPUT_FOLDER, product_dir)
            if os.path.isdir(full_path):
                md_files = [f for f in os.listdir(full_path) if f.endswith(".md")]
                summary_counts[product_dir] = len(md_files)
                
        logger.info("\n📊 Crawl Summary:")
        for product, count in summary_counts.items():
            logger.info(f"  - {product}: {count} markdown files")
            
        save_summary(BASE_OUTPUT_FOLDER, summary_counts)
        return summary_counts
    except Exception as e:
        logger.error(f"Error summarizing markdown counts: {e}")
        return {}