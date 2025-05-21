import logging
import time
import requests
import re
from typing import List, Dict, Any, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from config import get_config

config = get_config()
MAX_LINKS_PROVIDED = config.max_links_provided

logger = logging.getLogger(__name__)

class ReferenceHandler:
    """
    Class for handling, validating, and processing URL references.
    
    Provides methods for checking URLs, validating references, and processing
    reference information for RFP responses.
    """
    
    @staticmethod
    def is_404_page(soup: BeautifulSoup) -> bool:
        """
        Check if a BeautifulSoup object represents a 404 page.
        
        Args:
            soup: BeautifulSoup object to check
            
        Returns:
            True if the page appears to be a 404 page, False otherwise
        """
        indicators = [
            soup.title and "404" in soup.title.text.lower(),
            any(phrase in soup.get_text().lower() for phrase in [
                "we looked high and low", "not found", "head back to the space station",
                "page you're trying to view isn't here", "it may be an old link", 
                "404 error", "this site can't be reached"
            ])
        ]
        return any(indicators)

    @staticmethod
    def check_salesforce_help_page(url: str, timeout: int = 10) -> bool:
        """
        Check if a Salesforce help page URL is valid and accessible.
        
        Args:
            url: URL to check
            timeout: Request timeout in seconds
            
        Returns:
            True if the URL is valid and accessible, False otherwise
        """
        logger.info(f"Checking: {url}")
        try:
            if not any(domain in url for domain in ["www.mulesoft.com", "developer.mulesoft.com"]):
                response = requests.head(url, allow_redirects=True, timeout=timeout)
                if response.status_code >= 400:
                    logger.info(f"❌ HTTP {response.status_code} Detected (pre-check): {url}")
                    return False
        except Exception as e:
            logger.error(f"❌ Request failed before Selenium: {url} - {e}")
            return False

        options = ReferenceHandler._get_chrome_options()
        
        try:
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            return False
        
        try:
            driver.get(url)
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h2")))
            except:
                pass

            time.sleep(2)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            if ReferenceHandler.is_404_page(soup):
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

    @staticmethod
    def _get_chrome_options() -> Options:
        """
        Get Chrome options for headless browser operation.
        
        Returns:
            Configured Chrome options
        """
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36")
        return options

    @staticmethod
    def validate_and_filter_references(references: List[str], max_links: int = None) -> List[str]:
        """
        Validate and filter a list of references.
        
        Args:
            references: List of reference URLs to validate
            max_links: Maximum number of references to return
            
        Returns:
            Filtered list of valid reference URLs
        """
        if max_links is None:
            max_links = MAX_LINKS_PROVIDED
            
        if not references:
            return []
        
        logger.info(f"Validating {len(references)} references...")
        
        valid_refs = []
        
        for url in references:
            if ReferenceHandler.check_salesforce_help_page(url):
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

    @staticmethod
    def process_references(parsed_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process references in a parsed response.
        
        Args:
            parsed_response: Parsed response dictionary
            
        Returns:
            Updated response with validated references
        """
        references = parsed_response.get("references", [])
        
        if not references:
            logger.info("No references found in LLM response.")
            return parsed_response
        
        valid_references = ReferenceHandler.validate_and_filter_references(references)
        
        parsed_response["references"] = valid_references
        
        return parsed_response
    
    @staticmethod
    def extract_references_from_text(text: str) -> List[str]:
        """
        Extract URL references from text.
        
        Args:
            text: Text to extract references from
            
        Returns:
            List of extracted URLs
        """
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        urls = re.findall(url_pattern, text)
        
        cleaned_urls = []
        for url in urls:
            # Clean trailing punctuation
            url = re.sub(r'[.,;:!?)\]}]+$', '', url)
            
            # Only include Salesforce domains
            if any(domain in url.lower() for domain in [
                'salesforce.com', 
                'force.com', 
                'trailhead.com',
                'developer.salesforce.com',
                'help.salesforce.com'
            ]):
                if url not in cleaned_urls:
                    cleaned_urls.append(url)
        
        return cleaned_urls
    
    @staticmethod
    def is_valid_salesforce_domain(url: str) -> bool:
        """
        Check if a URL is from a valid Salesforce domain.
        
        Args:
            url: URL to check
            
        Returns:
            True if the URL is from a valid Salesforce domain, False otherwise
        """
        valid_domains = [
            'salesforce.com', 
            'force.com', 
            'trailhead.com',
            'developer.salesforce.com',
            'help.salesforce.com',
            'appexchange.salesforce.com',
            'admin.salesforce.com',
            'mulesoft.com',
            'heroku.com'
        ]
        return any(domain in url.lower() for domain in valid_domains)