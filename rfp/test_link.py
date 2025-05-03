from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import requests

def is_404_page(soup):
    """
    Detect 404 pages across Salesforce Help, Developer, Trailhead, and MuleSoft.
    """
    title_404 = soup.title and "404" in soup.title.text.lower()
    print(f"[DEBUG] title_404: {title_404}")

    h1 = soup.find("h1")
    h1_text = h1.get_text().lower() if h1 else ""
    print(f"[DEBUG] h1_text: {h1_text}")

    help_404 = "we looked high and low" in h1_text or "not found" in h1_text
    dev_404 = soup.find(string=lambda t: t and "head back to the space station" in t.lower()) is not None
    trail_404 = soup.find(string=lambda t: t and "page you’re trying to view isn’t here" in t.lower()) is not None

    mule_404 = soup.find("h2", string=lambda t: t and (
        "it may be an old link or may have been moved" in t.lower() or
        "404 error. your page was not found." in t.lower()
    )) is not None

    internal_chrome_error = "this site can’t be reached" in soup.get_text().lower()

    print(f"[DEBUG] help_404: {help_404}, dev_404: {dev_404}, trail_404: {trail_404}, mule_404: {mule_404}, internal_chrome_error: {internal_chrome_error}")

    return title_404 or help_404 or dev_404 or trail_404 or mule_404 or internal_chrome_error

def check_salesforce_page(url):
    print(f"[INFO] Checking: {url}")
    try:
        if not any(domain in url for domain in ["www.mulesoft.com", "developer.mulesoft.com"]):
            response = requests.head(url, allow_redirects=True, timeout=10)
            print(f"[DEBUG] HEAD status code: {response.status_code}")
            if response.status_code >= 400:
                print(f"❌ HTTP {response.status_code} Detected (pre-check): {url}")
                return False
    except Exception as e:
        print(f"❌ Request failed before Selenium: {url} - {e}")
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

    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        print("[DEBUG] Page requested, waiting for content...")
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h2")))
            print("[DEBUG] <h2> tag detected")
        except:
            print("[DEBUG] <h2> tag not detected within timeout")

        time.sleep(2)  # allow for JS rendering fallback

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        if is_404_page(soup):
            print(f"❌ 404 Detected: {url}")
            return False

        h1 = soup.find("h1")
        h2 = soup.find("h2")
        title = h1.get_text(strip=True) if h1 else h2.get_text(strip=True) if h2 else soup.title.text.strip() if soup.title else "No title found"
        print(f"✅ OK: {url} [Title: {title}]")
        return True

    except Exception as e:
        print(f"❌ Error loading {url} - {e}")
        return False
    finally:
        driver.quit()

if __name__ == "__main__":
    test_urls = [
        # Help
        "https://help.salesforce.com/s/articleView?id=data.c360_a_calculated_insights.htm&type=5",
        "https://help.salesforce.com/s/articleView?id=sf.c360_a_segment_operators.htm&type=5",

        # Developer
        "https://developer.salesforce.com/docs/einstein/genai/guide/get-started.html",
        "https://developer.salesforce.com/test",

        # Trailhead
        "https://trailhead.salesforce.com/content/learn/trails/get-ready-for-agentforce",
        "https://trailhead.salesforce.com/content/learn/trails/get-ready-for-agentforce5656",

        # MuleSoft
        "https://www.mulesoft.com/platform/enterprise-integration",
        "https://www.mulesoft.com/platform/enterprise-integration123",

        # MuleSoft Developer
        "https://developer.mulesoft.com/tutorials-and-howtos/getting-started/hello-mule/",
        "https://developer.mulesoft.com/tutorials-and-howtos/getting-started/hello-mule2/"
    ]

    for url in test_urls:
        check_salesforce_page(url)
