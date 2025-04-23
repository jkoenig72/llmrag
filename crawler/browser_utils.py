import time
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import logging

logger = logging.getLogger(__name__)

def create_browser():
    """
    Create and return a new Chrome browser instance.
    
    Uses webdriver_manager to automatically download and manage the appropriate
    ChromeDriver version for the installed Chrome browser.
    
    Returns:
        webdriver.Chrome: A configured Chrome WebDriver instance.
    """
    options = webdriver.ChromeOptions()
    #options.add_argument("--headless")  # Optional: run headless for server environments
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def dismiss_cookie_popup(driver):
    """
    Attempt to dismiss cookie consent popups on the page.
    
    Looks for a "Do Not Accept" button and clicks it if found.
    
    Args:
        driver (webdriver.Chrome): The WebDriver instance.
        
    Returns:
        None
    """
    try:
        reject_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Do Not Accept']"))
        )
        reject_button.click()
        time.sleep(1)
    except TimeoutException:
        # No cookie popup or couldn't find the button - this is expected in many cases
        pass

def load_page(driver, url, wait_time=2):
    """
    Load a URL in the driver and wait for it to render.
    
    Navigates to the given URL, attempts to dismiss any cookie popups,
    and waits for the specified time to allow for JavaScript rendering.
    
    Args:
        driver (webdriver.Chrome): The WebDriver instance.
        url (str): The URL to load.
        wait_time (int, optional): Time to wait after loading for rendering, in seconds. Defaults to 2.
        
    Returns:
        bool: True if page loaded successfully, False otherwise.
    """
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(wait_time)  # Allow time for JS rendering
        return True
    except Exception as e:
        logger.error(f"Failed to load page {url}: {e}")
        return False

def wait_for_element(driver, xpath, timeout=10):
    """
    Wait for an element to be present on the page.
    
    Uses explicit waits to allow time for elements to appear in the DOM.
    
    Args:
        driver (webdriver.Chrome): The WebDriver instance.
        xpath (str): XPath selector for the element to wait for.
        timeout (int, optional): Maximum time to wait in seconds. Defaults to 10.
        
    Returns:
        WebElement or None: The element if found, None if timeout occurs.
    """
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        return element
    except TimeoutException:
        logger.warning(f"Timeout waiting for element with xpath: {xpath}")
        return None

def is_404_page(soup):
    """
    Detect if the page is a 404 error page.
    
    Checks common indicators like "404" in the title or "not found" in an h1 element.
    
    Args:
        soup (BeautifulSoup): The BeautifulSoup object representing the page.
        
    Returns:
        bool: True if the page appears to be a 404 error page, False otherwise.
    """
    title_404 = soup.title and "404" in soup.title.text
    h1_404 = soup.find("h1") and "not found" in soup.find("h1").get_text().lower()
    return title_404 or h1_404