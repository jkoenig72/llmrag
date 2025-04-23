import logging
import time
import threading
import queue
from collections import defaultdict
from selenium.common.exceptions import WebDriverException

from config import PRODUCT_URL_PREFIXES, ALLOWED_DOMAINS, MAX_LINK_LEVEL, MAX_PAGES_PER_PRODUCT, BASE_OUTPUT_FOLDER
from browser_utils import create_browser, load_page
from page_handlers import process_page
from file_utils import get_product_folder

logger = logging.getLogger(__name__)

# Shared resources
visited = {}
crawl_graph = {"nodes": set(), "edges": set()}
product_md_counts = defaultdict(int)
visited_lock = threading.Lock()
graph_lock = threading.Lock()

def process_link_bfs(product_info):
    """
    Process links for a product using breadth-first search.
    
    Crawls product documentation by following links in a breadth-first manner,
    processing pages at each level before moving to the next depth level.
    
    Args:
        product_info (dict): Dictionary containing product name and starting URLs.
            Expected keys: 'product' and 'urls'.
    
    Returns:
        dict: Metrics dictionary containing statistics about the crawl.
    """
    product = product_info["product"]
    urls = product_info.get("urls", [])
    folder = get_product_folder(BASE_OUTPUT_FOLDER, product)
    
    # Add metrics tracking
    metrics = {
        "links_found": 0,
        "links_processed": 0,
        "links_skipped_duplicate": 0,
        "links_skipped_filter": 0,
        "links_skipped_error": 0,
        "max_depth_reached": 0,
        "reached_max_pages": False,
        "reached_max_depth": False
    }
    
    driver = create_browser()
    queue_by_depth = defaultdict(list)

    # Initialize queue with starting URLs
    for start_url in urls:
        with visited_lock:
            visited[start_url] = {
                "product": product,
                "source_url": start_url,
                "filename": f"output_{start_url.replace('https://', '').replace('/', '_')}.md"
            }
        queue_by_depth[0].append((start_url, start_url))

    try:
        for depth in range(MAX_LINK_LEVEL + 1):
            urls_at_depth = queue_by_depth[depth]
            if not urls_at_depth:
                logger.info(f"No URLs found at depth {depth} for {product} - crawler stopping naturally")
                break
                
            metrics["max_depth_reached"] = depth
            if depth == MAX_LINK_LEVEL:
                metrics["reached_max_depth"] = True
                logger.info(f"🔵 {product} reached MAX_LINK_LEVEL ({MAX_LINK_LEVEL})")
                
            logger.info(f"\n📦 {product}, Depth {depth} — {len(urls_at_depth)} pages to scrape")
            
            for idx, (url, src) in enumerate(urls_at_depth, start=1):
                # Check if we've reached the max page limit for this product
                if product_md_counts[product] >= MAX_PAGES_PER_PRODUCT:
                    metrics["reached_max_pages"] = True
                    logger.info(f"🛑 {product} reached MAX_PAGES_PER_PRODUCT ({MAX_PAGES_PER_PRODUCT}) — stopping early.")
                    return metrics
                    
                logger.info(f"✅ {product}, Depth {depth} — {idx}/{len(urls_at_depth)}")
                
                # Load the page and process it
                if not load_page(driver, url):
                    metrics["links_skipped_error"] += 1
                    continue
                
                links, base_name = process_page(driver, url, product, folder, depth, src, BASE_OUTPUT_FOLDER)
                
                if base_name:  # Successfully processed
                    metrics["links_processed"] += 1
                    product_md_counts[product] += 1
                else:  # Error during processing
                    metrics["links_skipped_error"] += 1
                
                # Count discovered links
                metrics["links_found"] += len(links)
                
                # Update crawl graph
                with graph_lock:
                    crawl_graph["nodes"].add(url)
                    for link in links:
                        crawl_graph["nodes"].add(link["href"])
                        crawl_graph["edges"].add((url, link["href"]))

                # Filter links for next level
                allowed_prefixes = PRODUCT_URL_PREFIXES.get(product, [])
                for link in links:
                    href = link["href"]
                    
                    # Skip links that don't match product prefixes or allowed domains
                    if not any(prefix in href for prefix in allowed_prefixes) or not any(href.startswith(domain) for domain in ALLOWED_DOMAINS):
                        metrics["links_skipped_filter"] += 1
                        continue
                        
                    # Skip already visited links
                    with visited_lock:
                        if href in visited:
                            metrics["links_skipped_duplicate"] += 1
                            continue
                        visited[href] = {
                            "product": product,
                            "source_url": url,
                            "filename": f"output_{href.replace('https://', '').replace('/', '_')}.md"
                        }
                        
                    # Add to queue for next depth level
                    if depth < MAX_LINK_LEVEL:
                        queue_by_depth[depth + 1].append((href, url))
        
        # End of crawling - log final metrics
        logger.info(f"\n📊 Crawling metrics for {product}:")
        logger.info(f"  - Links found: {metrics['links_found']}")
        logger.info(f"  - Links processed: {metrics['links_processed']}")
        logger.info(f"  - Links skipped (duplicate): {metrics['links_skipped_duplicate']}")
        logger.info(f"  - Links skipped (filter): {metrics['links_skipped_filter']}")
        logger.info(f"  - Links skipped (error): {metrics['links_skipped_error']}")
        logger.info(f"  - Max depth reached: {metrics['max_depth_reached']}")
        logger.info(f"  - Reached MAX_PAGES_PER_PRODUCT: {metrics['reached_max_pages']}")
        logger.info(f"  - Reached MAX_LINK_LEVEL: {metrics['reached_max_depth']}")
        
        return metrics
                        
    except Exception as e:
        logger.error(f"Error in crawler for {product}: {e}")
        return metrics
    finally:
        driver.quit()