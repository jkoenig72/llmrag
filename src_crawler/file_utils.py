import os
import re
import logging

logger = logging.getLogger(__name__)

def sanitize_filename(url):
    """Convert a URL to a valid filename."""
    return re.sub(r'[^a-zA-Z0-9-_.]', '_', re.sub(r'^https?://', '', url))[:200]

def save_file(folder, filename, content):
    """Save content to a file in the specified folder."""
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path
    except Exception as e:
        logger.error(f"Error saving file {filename}: {e}")
        return None

def log_skipped_404(url, base_folder):
    """Log URLs that returned 404 errors."""
    path = os.path.join(base_folder, "skipped_404.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{url}\n")
    except Exception as e:
        logger.error(f"Error logging skipped URL {url}: {e}")

def get_product_folder(base_folder, product):
    """Get the folder path for a specific product."""
    return os.path.join(base_folder, product.replace(" ", "_"))

def save_summary(base_folder, summary_counts):
    """Save a summary of crawl results."""
    path = os.path.join(base_folder, "summary.log")
    try:
        with open(path, "w", encoding="utf-8") as f:
            for product, count in summary_counts.items():
                f.write(f"{product}: {count} markdown files\n")
        return path
    except Exception as e:
        logger.error(f"Error saving summary: {e}")
        return None
    