import logging
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from browser_utils import wait_for_element, is_404_page
from content_processor import create_markdown, extract_links_from_html, detect_page_type
from file_utils import sanitize_filename, save_file, log_skipped_404

logger = logging.getLogger(__name__)

def handle_type_1(driver, url, product, folder, depth, source_url, base_folder):
    """Handle article view pages."""
    try:
        element = wait_for_element(driver, "//div[contains(@class, 'content with-toc')]//content")
        if not element:
            logger.warning(f"Content element not found on page: {url}")
            return [], ""
            
        html = element.get_attribute("innerHTML")
        soup = BeautifulSoup(html, "html.parser")
        
        if is_404_page(soup):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url, base_folder)
            return [], ""
            
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        links = extract_links_from_html(html, url)
        return links, base
        
    except TimeoutException as te:
        logger.error(f"[Timeout Error] {url} — {te}")
    except WebDriverException as wde:
        logger.error(f"[WebDriver Error] {url} — {wde}")
    except Exception as e:
        logger.error(f"[Type 1 Error] {url} — {e}")
    return [], ""

def handle_type_2(driver, url, product, folder, depth, source_url, base_folder):
    """Handle developer documentation pages."""
    try:
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        if is_404_page(soup):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url, base_folder)
            return [], ""
            
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        links = extract_links_from_html(html, url)
        return links, base
        
    except TimeoutException as te:
        logger.error(f"[Timeout Error] {url} — {te}")
    except WebDriverException as wde:
        logger.error(f"[WebDriver Error] {url} — {wde}")
    except Exception as e:
        logger.error(f"[Type 2 Error] {url} — {e}")
    return [], ""

def handle_type_3(driver, url, product, folder, depth, source_url, base_folder):
    """Handle product pages."""
    try:
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        if is_404_page(soup):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url, base_folder)
            return [], ""
            
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        links = extract_links_from_html(html, url)
        return links, base
        
    except TimeoutException as te:
        logger.error(f"[Timeout Error] {url} — {te}")
    except WebDriverException as wde:
        logger.error(f"[WebDriver Error] {url} — {wde}")
    except Exception as e:
        logger.error(f"[Type 3 Error] {url} — {e}")
    return [], ""

def handle_type_4(driver, url, product, folder, depth, source_url, base_folder):
    """Handle MuleSoft platform pages."""
    try:
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        if is_404_page(soup):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url, base_folder)
            return [], ""
            
        main = soup.find("main") or soup.body or soup
        content_html = str(main)
        
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(content_html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        links = extract_links_from_html(content_html, url)
        return links, base
        
    except TimeoutException as te:
        logger.error(f"[Timeout Error] {url} — {te}")
    except WebDriverException as wde:
        logger.error(f"[WebDriver Error] {url} — {wde}")
    except Exception as e:
        logger.error(f"[Type 4 Error] {url} — {e}")
    return [], ""

def process_page(driver, url, product, folder, depth, source_url, base_folder):
    """Process a page based on its type."""
    page_type = detect_page_type(url)
    
    if page_type == 1:
        return handle_type_1(driver, url, product, folder, depth, source_url, base_folder)
    elif page_type == 2:
        return handle_type_2(driver, url, product, folder, depth, source_url, base_folder)
    elif page_type == 3:
        return handle_type_3(driver, url, product, folder, depth, source_url, base_folder)
    elif page_type == 4:
        return handle_type_4(driver, url, product, folder, depth, source_url, base_folder)
    else:
        logger.warning(f"❌ Unknown page type: {url}")
        return [], ""