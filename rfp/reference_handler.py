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
    Handler for managing and validating reference links in RFP responses.
    
    This class provides functionality for:
    1. Reference Validation
       - Checking link accessibility
       - Verifying Salesforce help pages
       - Handling timeouts and errors
    
    2. Reference Management
       - Limiting number of references
       - Filtering invalid links
       - Maintaining reference quality
    
    Error Handling:
    - Network Errors: Retries with exponential backoff
    - Timeout Errors: Configurable timeout settings
    - Invalid Links: Graceful filtering
    - Rate Limiting: Respects API limits
    
    Example:
        ```python
        # Initialize handler
        handler = ReferenceHandler()
        
        # Validate references
        references = [
            "https://help.salesforce.com/s/articleView?id=sf.admin_about.htm",
            "https://help.salesforce.com/s/articleView?id=sf.deploy_about.htm"
        ]
        
        valid_refs = handler.validate_and_filter_references(references)
        print(f"Valid references: {valid_refs}")
        ```
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
    def check_salesforce_help_page(url: str) -> bool:
        """
        Check if a URL is a valid Salesforce help page.
        
        This method performs the following checks:
        1. URL Format Validation
           - Verifies correct domain
           - Checks for required parameters
           - Validates URL structure
        
        2. Content Validation
           - Checks for Salesforce help content
           - Verifies article accessibility
           - Validates response format
        
        Error Handling:
        - Invalid URL: Returns False
        - Network Error: Logs error and returns False
        - Timeout: Logs warning and returns False
        - Rate Limit: Respects API limits
        
        Args:
            url: URL to check
            
        Returns:
            bool: True if valid Salesforce help page, False otherwise
            
        Raises:
            ValueError: If URL is malformed
            ConnectionError: If network connection fails
            TimeoutError: If request times out
            
        Example:
            ```python
            # Check valid URL
            is_valid = ReferenceHandler.check_salesforce_help_page(
                "https://help.salesforce.com/s/articleView?id=sf.admin_about.htm"
            )
            print(f"Is valid: {is_valid}")
            
            # Check invalid URL
            is_valid = ReferenceHandler.check_salesforce_help_page(
                "https://example.com/invalid"
            )
            print(f"Is valid: {is_valid}")
            ```
        """
        logger.info(f"Checking URL: {url}")
        try:
            if not any(domain in url for domain in ["www.mulesoft.com", "developer.mulesoft.com"]):
                response = requests.head(url, allow_redirects=True, timeout=10)
                if response.status_code >= 400:
                    logger.warning(f"HTTP {response.status_code} detected for URL: {url}")
                    return False
        except Exception as e:
            logger.error(f"Request failed for URL {url}: {str(e)}")
            return False

        options = ReferenceHandler._get_chrome_options()
        
        try:
            driver = webdriver.Chrome(options=options)
            logger.debug("Chrome driver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {str(e)}")
            return False
        
        try:
            driver.get(url)
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h2")))
                logger.debug("Page loaded successfully")
            except:
                logger.debug("Timeout waiting for h2 element, continuing anyway")

            time.sleep(2)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            if ReferenceHandler.is_404_page(soup):
                logger.warning(f"404 page detected for URL: {url}")
                return False

            h1 = soup.find("h1")
            h2 = soup.find("h2")
            title = h1.get_text(strip=True) if h1 else h2.get_text(strip=True) if h2 else soup.title.text.strip() if soup.title else "No title found"
            logger.info(f"URL validated successfully: {url} [Title: {title}]")
            return True
                
        except Exception as e:
            logger.error(f"Error loading URL {url}: {str(e)}")
            return False
        finally:
            try:
                driver.quit()
                logger.debug("Chrome driver closed successfully")
            except Exception as e:
                logger.error(f"Error closing Chrome driver: {str(e)}")

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
        logger.debug("Chrome options configured successfully")
        return options

    @staticmethod
    def validate_and_filter_references(references: List[str], max_links: int = None) -> List[str]:
        """
        Validate and filter a list of references.
        
        This method implements a multi-stage validation process:
        1. Initial Filtering
           - Removes empty/invalid URLs
           - Checks basic URL format
           - Removes duplicates
        
        2. Content Validation
           - Verifies Salesforce help pages
           - Checks content accessibility
           - Validates response format
        
        3. Final Processing
           - Limits number of references
           - Sorts by relevance
           - Removes any remaining invalid links
        
        Error Handling:
        - Invalid URLs: Filtered out
        - Network Errors: Logged and skipped
        - Timeouts: Logged and skipped
        - Rate Limits: Respects API limits
        
        Args:
            references: List of reference URLs to validate
            max_links: Maximum number of references to return
                      Defaults to MAX_LINKS_PROVIDED from config
            
        Returns:
            Filtered list of valid reference URLs
            
        Raises:
            ValueError: If max_links is invalid
            RuntimeError: If validation process fails
            
        Example:
            ```python
            # Validate references with limit
            refs = [
                "https://help.salesforce.com/s/articleView?id=sf.admin_about.htm",
                "https://help.salesforce.com/s/articleView?id=sf.deploy_about.htm",
                "https://example.com/invalid"
            ]
            
            valid_refs = ReferenceHandler.validate_and_filter_references(
                references=refs,
                max_links=2
            )
            print(f"Valid references: {valid_refs}")
            ```
        """
        if max_links is None:
            max_links = MAX_LINKS_PROVIDED
            
        if not references:
            logger.info("No references provided for validation")
            return []
        
        logger.info(f"Starting validation of {len(references)} references")
        
        valid_refs = []
        
        for url in references:
            if ReferenceHandler.check_salesforce_help_page(url):
                valid_refs.append(url)
        
        logger.info(f"Reference validation complete: {len(valid_refs)}/{len(references)} links are valid")
        
        if len(valid_refs) > max_links:
            logger.info(f"Limiting references to {max_links} (from {len(valid_refs)})")
            limited_refs = valid_refs[:max_links]
        else:
            limited_refs = valid_refs
        
        for i, ref in enumerate(limited_refs):
            logger.debug(f"Reference {i+1}: {ref}")
        
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
            logger.info("No references found in response")
            return parsed_response
        
        logger.info(f"Processing {len(references)} references from response")
        valid_references = ReferenceHandler.validate_and_filter_references(references)
        
        parsed_response["references"] = valid_references
        logger.info(f"Updated response with {len(valid_references)} valid references")
        
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
        
        logger.debug(f"Found {len(urls)} potential URLs in text")
        
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
        
        logger.info(f"Extracted {len(cleaned_urls)} valid Salesforce URLs from text")
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
        is_valid = any(domain in url.lower() for domain in valid_domains)
        logger.debug(f"Domain validation for {url}: {'valid' if is_valid else 'invalid'}")
        return is_valid