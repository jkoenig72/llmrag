import logging
import time
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
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

def handle_type_5(driver, url, product, folder, depth, source_url, base_folder):
    """Handle standard Salesforce articleView pages (without /s/)."""
    try:
        # Wait for page to fully load
        time.sleep(3)
        
        # Get full page HTML as a fallback
        full_html = driver.page_source
        soup_full = BeautifulSoup(full_html, "html.parser")
        
        if is_404_page(soup_full):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url, base_folder)
            return [], ""
        
        # Get page title
        page_title = None
        if soup_full.title:
            page_title = soup_full.title.get_text().strip()
        
        # Try to find the main content container using various selectors
        content_html = None
        
        # Common content containers in Salesforce help pages
        selectors = [
            "div.article-content",
            "div.content-container", 
            "div.contentBody",
            "div.slds-template__container",
            "div#articleContent",
            "div.helpContent",
            "div.slds-col--padded.content",
            "div.slds-col--padded.contentRegion",
            "article.content",
            "main"
        ]
        
        # Try each selector
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and len(elements) > 0:
                    # Use the longest element as it's likely the main content
                    longest_element = max(elements, key=lambda e: len(e.get_attribute("innerHTML") or ""))
                    content_html = longest_element.get_attribute("innerHTML")
                    if content_html and len(content_html) > 500:  # Ensure it has substantial content
                        break
            except Exception as e:
                logger.debug(f"Exception with selector {selector}: {e}")
                continue
        
        # If no specific content container found, try finding the article h1 and navigate up
        if not content_html:
            try:
                heading = driver.find_element(By.CSS_SELECTOR, "h1")
                if heading:
                    # Try to find a parent div that might contain the content
                    parent = heading.find_element(By.XPATH, "./ancestor::div[contains(@class, 'content') or contains(@class, 'article')]")
                    if parent:
                        content_html = parent.get_attribute("innerHTML")
            except Exception as e:
                logger.debug(f"Exception finding heading parent: {e}")
        
        # If all else fails, use BeautifulSoup parsing as a fallback
        if not content_html:
            try:
                for selector in selectors:
                    content = soup_full.select_one(selector)
                    if content and len(str(content)) > 500:
                        content_html = str(content)
                        break
                
                # If still not found, try the body content
                if not content_html:
                    # Try to get article heading and its container
                    h1 = soup_full.find("h1")
                    if h1:
                        container = h1.find_parent("div", class_=lambda c: c and ("content" in c.lower() or "article" in c.lower()))
                        if container and len(str(container)) > 500:
                            content_html = str(container)
            except Exception as e:
                logger.debug(f"Exception using BeautifulSoup parsing: {e}")
        
        # Last resort: use the body, after attempting to clean it
        if not content_html:
            try:
                body = soup_full.body
                
                # Try to remove navigation, headers, footers
                for selector in ["header", "footer", "nav", ".navbar", ".navigation", ".header", ".footer", ".sidebar"]:
                    for tag in soup_full.select(selector):
                        tag.decompose()
                        
                content_html = str(body)
            except Exception as e:
                logger.debug(f"Exception using body fallback: {e}")
                content_html = full_html
        
        # Process the content
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(content_html, product, depth, source_url, title_override=page_title)
        save_file(folder, f"{base}.md", md)
        
        # Extract links for further crawling
        links = extract_links_from_html(content_html, url)
        return links, base
        
    except Exception as e:
        logger.error(f"[Type 5 Error] {url} — {e}")
        import traceback
        logger.error(traceback.format_exc())
    return [], ""

def handle_type_6(driver, url, product, folder, depth, source_url, base_folder):
    """Handle Salesforce Apex Help Documentation pages."""
    try:
        # Wait for page to fully load
        time.sleep(3)
        
        # Get full page HTML
        full_html = driver.page_source
        soup_full = BeautifulSoup(full_html, "html.parser")
        
        if is_404_page(soup_full):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url, base_folder)
            return [], ""
        
        # Get page title
        page_title = None
        if soup_full.title:
            page_title = soup_full.title.get_text().strip()
        
        # Try to find the main content container - Apex Help pages often use different structures
        content_html = None
        
        # Common content containers in Apex Help pages
        selectors = [
            "div.content",
            "div.helpContent",
            "div.apexHelpPanel",
            "div.apexHelpText",
            "div#contentArea",
            "div.documentMainContent",
            "div.bodyContent",
            "div.slds-col--padded.contentRegion",
            "article.content"
        ]
        
        # Try each selector
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and len(elements) > 0:
                    # Use the longest element as it's likely the main content
                    longest_element = max(elements, key=lambda e: len(e.get_attribute("innerHTML") or ""))
                    content_html = longest_element.get_attribute("innerHTML")
                    if content_html and len(content_html) > 500:  # Ensure it has substantial content
                        break
            except Exception as e:
                logger.debug(f"Exception with selector {selector}: {e}")
                continue
        
        # Try finding specific markers in Apex Help pages - often they have distinct section headers
        if not content_html:
            try:
                # Look for common Apex Help headers or markers
                markers = driver.find_elements(By.CSS_SELECTOR, "h1.helpTitle, h2.helpSectionTitle, div.helpText")
                if markers and len(markers) > 0:
                    # Find a parent container
                    for marker in markers:
                        try:
                            parent = marker.find_element(By.XPATH, "./ancestor::div[contains(@class, 'help') or contains(@class, 'content')]")
                            if parent:
                                content_html = parent.get_attribute("innerHTML")
                                if content_html and len(content_html) > 500:
                                    break
                        except:
                            continue
            except Exception as e:
                logger.debug(f"Exception finding Apex Help markers: {e}")
        
        # If all else fails, use BeautifulSoup parsing as a fallback
        if not content_html:
            try:
                for selector in selectors:
                    content = soup_full.select_one(selector)
                    if content and len(str(content)) > 500:
                        content_html = str(content)
                        break
                
                # If still not found, try the body content
                if not content_html:
                    # Try to clean the body
                    body = soup_full.body
                    
                    # Try to remove navigation, headers, footers
                    for selector in ["header", "footer", "nav", ".navbar", ".navigation", ".header", ".footer", ".sidebar"]:
                        for tag in soup_full.select(selector):
                            tag.decompose()
                            
                    content_html = str(body)
            except Exception as e:
                logger.debug(f"Exception using BeautifulSoup parsing for Apex Help: {e}")
                content_html = full_html
        
        # Process the content
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(content_html, product, depth, source_url, title_override=page_title)
        save_file(folder, f"{base}.md", md)
        
        # Extract links for further crawling
        links = extract_links_from_html(content_html, url)
        return links, base
        
    except Exception as e:
        logger.error(f"[Type 6 Error] {url} — {e}")
        import traceback
        logger.error(traceback.format_exc())
    return [], ""

def handle_type_7(driver, url, product, folder, depth, source_url, base_folder):
    """Handle Trailhead learning content pages."""
    try:
        # Wait for page to fully load - Trailhead has lots of JS
        time.sleep(5)
        
        # Get full page HTML
        full_html = driver.page_source
        soup_full = BeautifulSoup(full_html, "html.parser")
        
        if is_404_page(soup_full):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url, base_folder)
            return [], ""
        
        # Get detailed metadata
        module_title = None
        unit_title = None
        
        # Try to get module title and unit title for better metadata
        try:
            module_title_elem = driver.find_element(By.CSS_SELECTOR, ".module-title, .tds-module-name")
            if module_title_elem:
                module_title = module_title_elem.text.strip()
        except NoSuchElementException:
            pass
            
        try:
            unit_title_elem = driver.find_element(By.CSS_SELECTOR, ".unit-title, .tds-unit-name")
            if unit_title_elem:
                unit_title = unit_title_elem.text.strip()
        except NoSuchElementException:
            pass
        
        # Combine module and unit titles for a more complete title
        page_title = None
        if module_title and unit_title:
            page_title = f"{module_title} - {unit_title}"
        elif module_title:
            page_title = module_title
        elif unit_title:
            page_title = unit_title
        elif soup_full.title:
            page_title = soup_full.title.get_text().strip()
            
        # Try to extract the main content
        content_html = None
        
        # Common content containers in Trailhead
        selectors = [
            "div.content-container",
            "div.main-content",
            "div.slds-container--medium",
            "div.module-container",
            "div.unit-container",
            "div.tds-content-container",
            "main.slds-col"
        ]
        
        # Try specific Trailhead content containers first
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and len(elements) > 0:
                    # Use the longest matching element as it's most likely to be the main content
                    longest_element = max(elements, key=lambda e: len(e.get_attribute("innerHTML") or ""))
                    content_html = longest_element.get_attribute("innerHTML")
                    if content_html and len(content_html) > 500:
                        break
            except Exception as e:
                logger.debug(f"Exception with selector {selector}: {e}")
                continue
                
        # Try looking for specific Trailhead content sections
        if not content_html:
            try:
                # Trailhead often has units with distinct sections
                sections = driver.find_elements(By.CSS_SELECTOR, ".unit-content section, .tds-unit-content, .challenge-content")
                if sections and len(sections) > 0:
                    # Combine all sections
                    combined_html = ""
                    for section in sections:
                        combined_html += section.get_attribute("outerHTML")
                    
                    if len(combined_html) > 500:
                        content_html = combined_html
            except Exception as e:
                logger.debug(f"Exception finding Trailhead sections: {e}")
        
        # Use BeautifulSoup as a fallback
        if not content_html:
            try:
                for selector in selectors:
                    content = soup_full.select_one(selector)
                    if content and len(str(content)) > 500:
                        content_html = str(content)
                        break
                        
                # If still not found, try to extract all unit content sections
                if not content_html:
                    sections = soup_full.select(".unit-content section, .tds-unit-content, .challenge-content")
                    if sections and len(sections) > 0:
                        combined_html = ""
                        for section in sections:
                            combined_html += str(section)
                        
                        if len(combined_html) > 500:
                            content_html = combined_html
            except Exception as e:
                logger.debug(f"Exception using BeautifulSoup parsing for Trailhead: {e}")
        
        # Last resort: use the body after cleanup
        if not content_html:
            try:
                body = soup_full.body.copy()
                
                # Try to remove navigation, headers, footers, sidebars
                for selector in ["header", "footer", "nav", ".navbar", "aside", ".sidebar", ".navigation", 
                                ".header", ".footer", ".trailhead-nav", ".sidebar-nav"]:
                    for tag in body.select(selector):
                        tag.decompose()
                
                content_html = str(body)
            except Exception as e:
                logger.debug(f"Exception using body fallback for Trailhead: {e}")
                content_html = full_html
                
        # Extra metadata for Trailhead content
        extra_metadata = {}
        
        # Try to extract additional metadata like estimated time, points, type
        try:
            # Extract points
            points_elem = driver.find_element(By.CSS_SELECTOR, ".tds-badge-points, .badge-points")
            if points_elem:
                extra_metadata["points"] = points_elem.text.strip()
                
            # Extract estimated time
            time_elem = driver.find_element(By.CSS_SELECTOR, ".estimated-time, .tds-estimated-time")
            if time_elem:
                extra_metadata["estimated_time"] = time_elem.text.strip()
                
            # Extract type (module, trail, project)
            if "modules" in url:
                extra_metadata["type"] = "module"
            elif "trails" in url:
                extra_metadata["type"] = "trail"
            elif "projects" in url:
                extra_metadata["type"] = "project"
        except Exception:
            # Not critical, can continue without this metadata
            pass
            
        # Process the content
        base = f"output_{sanitize_filename(url)}"
        
        # Add a note about it being Trailhead content
        custom_yaml = (
            "trailhead: true\n"
            f"module_title: \"{module_title or ''}\"\n"
            f"unit_title: \"{unit_title or ''}\"\n"
        )
        
        # Add any extra metadata we extracted
        for key, value in extra_metadata.items():
            custom_yaml += f"{key}: \"{value}\"\n"
        
        md = create_markdown(content_html, product, depth, source_url, title_override=page_title)
        
        # Insert our custom YAML after the initial triple dash
        md = md.replace("---\n", f"---\n{custom_yaml}", 1)
        
        save_file(folder, f"{base}.md", md)
        
        # Extract links for further crawling
        links = extract_links_from_html(content_html, url)
        return links, base
        
    except Exception as e:
        logger.error(f"[Type 7 Error] {url} — {e}")
        import traceback
        logger.error(traceback.format_exc())
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
    elif page_type == 5:
        return handle_type_5(driver, url, product, folder, depth, source_url, base_folder)
    elif page_type == 6:
        return handle_type_6(driver, url, product, folder, depth, source_url, base_folder)
    elif page_type == 7:
        return handle_type_7(driver, url, product, folder, depth, source_url, base_folder)
    else:
        logger.warning(f"❌ Unknown page type: {url}")
        return [], ""