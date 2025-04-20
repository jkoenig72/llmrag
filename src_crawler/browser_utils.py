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
    """Create and return a new browser instance."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Optional: run headless for server environments
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def dismiss_cookie_popup(driver):
    """Attempt to dismiss cookie consent popups on the page."""
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
    """Load a URL in the driver and wait for it to render."""
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(wait_time)  # Allow time for JS rendering
        return True
    except Exception as e:
        logger.error(f"Failed to load page {url}: {e}")
        return False

def wait_for_element(driver, xpath, timeout=10):
    """Wait for an element to be present on the page."""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        return element
    except TimeoutException:
        logger.warning(f"Timeout waiting for element with xpath: {xpath}")
        return None

def is_404_page(soup):
    """Detect if the page is a 404 error page."""
    title_404 = soup.title and "404" in soup.title.text
    h1_404 = soup.find("h1") and "not found" in soup.find("h1").get_text().lower()
    return title_404 or h1_404