import os
import re
import logging

logger = logging.getLogger(__name__)

def sanitize_filename(url):
    """
    Convert a URL to a valid filename.
    
    Removes illegal characters from URLs to create valid filenames.
    
    Args:
        url (str): The URL to convert to a filename.
        
    Returns:
        str: A sanitized string that can be used as a filename.
    """
    return re.sub(r'[^a-zA-Z0-9-_.]', '_', re.sub(r'^https?://', '', url))[:200]

def save_file(folder, filename, content):
    """
    Save content to a file in the specified folder.
    
    Creates the folder if it doesn't exist, then writes the content to a file.
    
    Args:
        folder (str): The folder path where the file should be saved.
        filename (str): The name of the file.
        content (str): The content to write to the file.
        
    Returns:
        str or None: The full file path if saved successfully, None if an error occurred.
    """
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
    """
    Log URLs that returned 404 errors.
    
    Appends URLs that resulted in 404 errors to a log file.
    
    Args:
        url (str): The URL that returned a 404 error.
        base_folder (str): The base folder where the log file is located.
        
    Returns:
        None
    """
    path = os.path.join(base_folder, "skipped_404.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{url}\n")
    except Exception as e:
        logger.error(f"Error logging skipped URL {url}: {e}")

def get_product_folder(base_folder, product):
    """
    Get the folder path for a specific product.
    
    Creates a path by joining the base folder with a sanitized product name.
    
    Args:
        base_folder (str): The base output folder.
        product (str): The product name.
        
    Returns:
        str: The path to the product-specific folder.
    """
    return os.path.join(base_folder, product.replace(" ", "_"))

def save_summary(base_folder, summary_counts):
    """
    Save a summary of crawl results.
    
    Writes a summary of product crawl statistics to a log file.
    
    Args:
        base_folder (str): The base folder where the summary file should be saved.
        summary_counts (dict): Dictionary mapping product names to markdown file counts.
        
    Returns:
        str or None: The path to the summary file if saved successfully, None if an error occurred.
    """
    path = os.path.join(base_folder, "summary.log")
    try:
        with open(path, "w", encoding="utf-8") as f:
            for product, count in summary_counts.items():
                f.write(f"{product}: {count} markdown files\n")
        return path
    except Exception as e:
        logger.error(f"Error saving summary: {e}")
        return None