import logging
import os
from collections import defaultdict

from config import BASE_OUTPUT_FOLDER, MAX_LINK_LEVEL
from file_utils import save_summary

def setup_logging():
    """
    Set up logging configuration.
    
    Configures logging to output to both a file and the console with
    appropriate formatting and log level.
    
    Returns:
        Logger: A configured logger instance.
    """
    os.makedirs(BASE_OUTPUT_FOLDER, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(BASE_OUTPUT_FOLDER, "scraper.log")),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def summarize_md_counts(product_metrics=None):
    """
    Scan the output folder and count markdown files by product, and summarize metrics.
    
    Traverses the output directory structure to count markdown files for each product
    and logs summary information including metrics if provided.
    
    Args:
        product_metrics (dict, optional): Dictionary containing metrics for each product.
            Defaults to None.
        
    Returns:
        dict: A dictionary mapping product names to markdown file counts.
    """
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
            
            # Add metrics if available
            if product_metrics and product in product_metrics:
                metrics = product_metrics[product]
                logger.info(f"    • Links found: {metrics['links_found']}")
                logger.info(f"    • Links processed: {metrics['links_processed']}")
                logger.info(f"    • Links skipped (duplicate): {metrics['links_skipped_duplicate']}")
                logger.info(f"    • Links skipped (filter): {metrics['links_skipped_filter']}")
                logger.info(f"    • Links skipped (error): {metrics['links_skipped_error']}")
                logger.info(f"    • Max depth reached: {metrics['max_depth_reached']}/{MAX_LINK_LEVEL}")
                logger.info(f"    • Reached MAX_PAGES_PER_PRODUCT: {metrics['reached_max_pages']}")
                logger.info(f"    • Reached MAX_LINK_LEVEL: {metrics['reached_max_depth']}")
            
        save_summary(BASE_OUTPUT_FOLDER, summary_counts)
        return summary_counts
    except Exception as e:
        logger.error(f"Error summarizing markdown counts: {e}")
        return {}