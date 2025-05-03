import logging
import time
import requests
from typing import List, Dict, Any

# For Selenium-based link validation
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Configuration
MAX_LINKS_PROVIDED = 2  # Maximum number of references to include in each answer

logger = logging.getLogger(__name__)

def is_404_page(soup):
    """
    Detect 404 pages across Salesforce Help, Developer, Trailhead, and MuleSoft.
    """
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
    """
    Check if a Salesforce documentation link is valid using Selenium.
    Comprehensive checks for various Salesforce domains.
    
    Args:
        url: The URL to check
        
    Returns:
        bool: True if the link works, False otherwise
    """
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

        time.sleep(2)  # allow for JS rendering fallback

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
    """
    Validate and filter references to ensure only working links are included.
    
    Args:
        references: List of reference URLs extracted from LLM response
        max_links: Maximum number of links to include
        
    Returns:
        List[str]: Filtered list of working reference URLs, limited to max_links
    """
    if not references:
        return []
    
    logger.info(f"Validating {len(references)} references...")
    
    # Check each link and keep only the working ones
    valid_refs = []
    
    for url in references:
        if check_salesforce_help_page(url):
            valid_refs.append(url)
    
    # Log the results
    logger.info(f"Validation complete: {len(valid_refs)}/{len(references)} links are valid")
    
    # Limit to max_links if needed
    if len(valid_refs) > max_links:
        logger.info(f"Limiting to {max_links} references")
        limited_refs = valid_refs[:max_links]
    else:
        limited_refs = valid_refs
    
    # Log the final references
    for i, ref in enumerate(limited_refs):
        logger.info(f"Reference {i+1}: {ref}")
    
    return limited_refs


def process_references(parsed_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process the references in an LLM response.
    
    Args:
        parsed_response: The parsed JSON response from the LLM
        
    Returns:
        Dict[str, Any]: The updated response with validated references
    """
    # Extract references if present
    references = parsed_response.get("references", [])
    
    if not references:
        logger.info("No references found in LLM response.")
        return parsed_response
    
    # Validate and filter references
    valid_references = validate_and_filter_references(references)
    
    # Update the parsed response
    parsed_response["references"] = valid_references
    
    return parsed_response


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO, 
                      format="%(asctime)s [%(levelname)s] %(message)s")
    
    # Test with sample references
    test_references = [
        # Known working link
        "https://help.salesforce.com/s/articleView?id=data.c360_a_calculated_insights.htm&type=5",
        # Known non-working links
        "https://help.salesforce.com/s/articleView?id=sf.om_order_lifecycle.htm&type=5",
        "https://help.salesforce.com/s/articleView?id=sf.om_decomposition_plans.htm&type=5"
    ]
    
    # Test the validation and filtering
    print("Testing reference validation...")
    valid_refs = validate_and_filter_references(test_references)
    
    print(f"\nValid references ({len(valid_refs)}/{len(test_references)}):")
    for ref in valid_refs:
        print(f" - {ref}")