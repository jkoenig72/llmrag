import logging
import time
import requests
from typing import List, Dict, Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

MAX_LINKS_PROVIDED = 2

logger = logging.getLogger(__name__)

def is_404_page(soup):
    title_404 = soup.title and "404" in soup.title.text.lower()
    logger.debug(f"title_404: {title_404}")

    h1 = soup.find("h1")
    h1_text = h1.get_text().lower() if h1 else ""
    logger.debug(f"h1_text: {h1_text}")

    help_404 = "we looked high and low" in h1_text or "not found" in h1_text
    dev_404 = soup.find(string=lambda t: t and "head back to the space station" in t.lower()) is not None
    trail_404 = soup.find(string=lambda t: t and "page you're trying to view isn't here" in t.lower()) is not None

    mule_404 = soup.find("h2", string=lambda t: t and (
        "it may be an old link or may have been moved" in t.lower() or
        "404 error. your page was not found." in t.lower()
    )) is not None

    internal_chrome_error = "this site can't be reached" in soup.get_text().lower()

    logger.debug(f"help_404: {help_404}, dev_404: {dev_404}, trail_404: {trail_404}, mule_404: {mule_404}, internal_chrome_error: {internal_chrome_error}")

    return title_404 or help_404 or dev_404 or trail_404 or mule_404 or internal_chrome_error

def check_salesforce_help_page(url: str) -> bool:
    logger.info(f"Checking: {url}")
    try:
        if not any(domain in url for domain in ["www.mulesoft.com", "developer.mulesoft.com"]):
            response = requests.head(url, allow_redirects=True, timeout=10)
            logger.debug(f"HEAD status code: {response.status_code}")
            if response.status_code >= 400:
                logger.info(f"❌ HTTP {response.status_code} Detected (pre-check): {url}")
                return False
    except Exception as e:
        logger.error(f"❌ Request failed before Selenium: {url} - {e}")
        return False

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36")

    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        logger.error(f"Failed to initialize Chrome driver: {e}")
        return False
    
    try:
        driver.get(url)
        logger.debug("Page requested, waiting for content...")
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h2")))
            logger.debug("<h2> tag detected")
        except:
            logger.debug("<h2> tag not detected within timeout")

        time.sleep(2)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        if is_404_page(soup):
            logger.info(f"❌ 404 Detected: {url}")
            return False

        h1 = soup.find("h1")
        h2 = soup.find("h2")
        title = h1.get_text(strip=True) if h1 else h2.get_text(strip=True) if h2 else soup.title.text.strip() if soup.title else "No title found"
        logger.info(f"✅ OK: {url} [Title: {title}]")
        return True
            
    except Exception as e:
        logger.error(f"❌ Error loading {url} - {e}")
        return False
    finally:
        try:
            driver.quit()
        except:
            pass


def validate_and_filter_references(references: List[str], max_links: int = MAX_LINKS_PROVIDED) -> List[str]:
    if not references:
        return []
    
    logger.info(f"Validating {len(references)} references...")
    
    valid_refs = []
    
    for url in references:
        if check_salesforce_help_page(url):
            valid_refs.append(url)
    
    logger.info(f"Validation complete: {len(valid_refs)}/{len(references)} links are valid")
    
    if len(valid_refs) > max_links:
        logger.info(f"Limiting to {max_links} references")
        limited_refs = valid_refs[:max_links]
    else:
        limited_refs = valid_refs
    
    for i, ref in enumerate(limited_refs):
        logger.info(f"Reference {i+1}: {ref}")
    
    return limited_refs


def process_references(parsed_response: Dict[str, Any]) -> Dict[str, Any]:
    references = parsed_response.get("references", [])
    
    if not references:
        logger.info("No references found in LLM response.")
        return parsed_response
    
    valid_references = validate_and_filter_references(references)
    
    parsed_response["references"] = valid_references
    
    return parsed_response