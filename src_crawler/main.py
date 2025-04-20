import os
import threading
import logging
from collections import defaultdict

from config import BASE_OUTPUT_FOLDER, START_LINKS
from crawler import process_link_bfs
from logger import setup_logging, summarize_md_counts

def main():
    """Main entry point for the scraper."""
    # Create base output directory
    os.makedirs(BASE_OUTPUT_FOLDER, exist_ok=True)
    
    # Set up logging
    logger = setup_logging()
    logger.info("Starting Salesforce documentation scraper")
    
    # Launch a thread for each product
    threads = []
    for info in START_LINKS:
        logger.info(f"Starting thread for {info['product']}")
        t = threading.Thread(target=process_link_bfs, args=(info,))
        t.start()
        threads.append(t)
    
    # Wait for all threads to complete
    for t in threads:
        t.join()
    
    # Summarize results
    logger.info("Crawling complete. Generating summary...")
    summarize_md_counts()
    logger.info("Scraping completed successfully")

if __name__ == "__main__":
    main()