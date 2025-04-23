"""
Main entry point for the Salesforce documentation scraper.

This module initializes the crawler and coordinates the scraping process
across multiple products using a multithreaded approach.
"""

import os
import threading
import queue
import logging
from collections import defaultdict

from config import BASE_OUTPUT_FOLDER, START_LINKS
from crawler import process_link_bfs
from logger import setup_logging, summarize_md_counts

def main():
    """
    Main entry point for the scraper.
    
    Creates the output directory, sets up logging, launches crawler threads
    for each product, collects metrics, and summarizes results.
    
    Returns:
        None
    """
    # Create base output directory
    os.makedirs(BASE_OUTPUT_FOLDER, exist_ok=True)
    
    # Set up logging
    logger = setup_logging()
    logger.info("Starting Salesforce documentation scraper")
    
    # Launch a thread for each product and store metrics
    threads = []
    product_metrics = {}
    
    for info in START_LINKS:
        product = info['product']
        logger.info(f"Starting thread for {product}")
        
        # Create a result queue for each thread
        result_queue = queue.Queue()
        t = threading.Thread(
            target=lambda q, arg: q.put(process_link_bfs(arg)),
            args=(result_queue, info)
        )
        t.start()
        threads.append((t, result_queue, product))
    
    # Wait for all threads to complete and collect metrics
    for t, result_queue, product in threads:
        t.join()
        try:
            metrics = result_queue.get(block=False)
            product_metrics[product] = metrics
        except queue.Empty:
            logger.error(f"No metrics returned for {product}")
    
    # Summarize results
    logger.info("Crawling complete. Generating summary...")
    summarize_md_counts(product_metrics)
    logger.info("Scraping completed successfully")

if __name__ == "__main__":
    main()