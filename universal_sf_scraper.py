import os
import re
import time
import json
import threading
import logging
from datetime import datetime
from urllib.parse import urljoin
from collections import defaultdict
from bs4 import BeautifulSoup
from markdownify import markdownify as md_convert
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_OUTPUT_FOLDER = "RAG"
MAX_LINK_LEVEL = 20
MAX_PAGES_PER_PRODUCT = 10000

PRODUCT_URL_PREFIXES = {
    "MuleSoft": [
        "/platform/", "/api/", "/general/", 
        "/runtime-manager/", "/api-manager/", "/studio/", "/anypoint/"
    ],
    "Communications_Cloud": ["id=ind.comms", "/products/communications"],
    "Sales_Cloud": ["id=sales", "/products/sales"],
    "Service_Cloud": ["id=service", "/products/service"],
    "Experience_Cloud": ["id=experience", "/products/experience"],
    "Marketing_Cloud": ["id=mktg", "/products/marketing"],
    "Data_Cloud": ["id=data", "/products/datacloud"],
    "Platform": ["id=platform", "/products/platform"],
    "Agentforce": ["id=ai", "ai.generative_ai"],
}

START_LINKS_PATH = os.path.join(os.path.dirname(__file__), "start_links.json")
with open(START_LINKS_PATH, "r", encoding="utf-8") as f:
    START_LINKS = json.load(f)

ALLOWED_DOMAINS = [
    "https://help.salesforce.com",
    "https://developer.salesforce.com",
    "https://trailhead.salesforce.com",
    "https://salesforce.com/docs",
    "https://www.mulesoft.com",
    "https://help.mulesoft.com",
    "https://docs.mulesoft.com"
]

visited = {}
crawl_graph = {"nodes": set(), "edges": set()}
product_md_counts = defaultdict(int)
visited_lock = threading.Lock()
graph_lock = threading.Lock()

def sanitize_filename(url):
    return re.sub(r'[^a-zA-Z0-9-_.]', '_', re.sub(r'^https?://', '', url))[:200]

def dismiss_cookie_popup(driver):
    try:
        reject_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Do Not Accept']"))
        )
        reject_button.click()
        time.sleep(1)
    except TimeoutException:
        pass

def log_skipped_404(url):
    path = os.path.join(BASE_OUTPUT_FOLDER, "skipped_404.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{url}\n")

def is_404_page(soup):
    title_404 = soup.title and "404" in soup.title.text
    h1_404 = soup.find("h1") and "not found" in soup.find("h1").get_text().lower()
    return title_404 or h1_404

def clean_cookie_content(soup):
    cookie_keywords = ["cookie", "consent", "accept all", "do not accept", "privacy", "cookie settings"]
    for tag in soup.find_all(True):
        if any(kw in tag.get_text().lower() for kw in cookie_keywords):
            tag.decompose()
    return soup

def create_markdown(content_html, tag, depth, source_url, title_override=None):
    soup = BeautifulSoup(content_html, "html.parser")
    soup = clean_cookie_content(soup)
    content_html = str(soup)

    md = md_convert(content_html, heading_style="ATX")
    title = title_override or (soup.title.get_text().strip() if soup.title else "")
    h1 = soup.find("h1")
    main_heading = h1.get_text().strip() if h1 else ""
    yaml = (
        f"---\n"
        f"title: \"{title or main_heading}\"\n"
        f"date: \"{datetime.now().strftime('%Y-%m-%d')}\"\n"
        f"tag: \"{tag}\"\n"
        f"category: \"Product Documentation: {tag}\"\n"
        f"toc: true\n"
        f"depth_level: {depth}\n"
        f"source_url: \"{source_url}\"\n"
        f"---\n\n"
    )
    headings = re.findall(r"^(#+)\s+(.*)", md, re.MULTILINE)
    toc = "\n".join(
        "  " * (len(h[0]) - 1) + f"- [{h[1]}](#{re.sub(r'[^a-zA-Z0-9 ]', '', h[1]).lower().replace(' ', '-')})"
        for h in headings
    )
    return yaml + f"## Table of Contents\n\n{toc}\n\n" + md

def extract_links_from_html(html, origin):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        link = {"text": a.get_text().strip(), "href": urljoin(origin, a["href"])}
        links.append(link)
    return links

def save_file(folder, filename, content):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def detect_page_type(url):
    if "help.salesforce.com/s/articleView" in url or "help.mulesoft.com/s/article" in url:
        return 1
    elif "developer.salesforce.com/docs" in url or "docs.mulesoft.com" in url:
        return 2
    elif "help.salesforce.com/s/products" in url:
        return 3
    elif "www.mulesoft.com/platform" in url:
        return 4
    return 0

def handle_type_1(driver, url, product, folder, depth, source_url):
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(2)
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'content with-toc')]//content"))
        )
        html = element.get_attribute("innerHTML")
        soup = BeautifulSoup(html, "html.parser")
        if is_404_page(soup):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url)
            return [], ""
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        product_md_counts[product] += 1
        links = extract_links_from_html(html, url)
        return links, base
    except TimeoutException as te:
        logger.error(f"[Timeout Error] {url} — {te}")
    except WebDriverException as wde:
        logger.error(f"[WebDriver Error] {url} — {wde}. Restarting browser.")
        driver.quit()
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=webdriver.ChromeOptions())
    except Exception as e:
        logger.error(f"[Type 1 Error] {url} — {e}")
    return [], ""

def handle_type_2(driver, url, product, folder, depth, source_url):
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(2)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        if is_404_page(soup):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url)
            return [], ""
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        product_md_counts[product] += 1
        links = extract_links_from_html(html, url)
        return links, base
    except TimeoutException as te:
        logger.error(f"[Timeout Error] {url} — {te}")
    except WebDriverException as wde:
        logger.error(f"[WebDriver Error] {url} — {wde}. Restarting browser.")
        driver.quit()
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=webdriver.ChromeOptions())
    except Exception as e:
        logger.error(f"[Type 2 Error] {url} — {e}")
    return [], ""

def handle_type_3(driver, url, product, folder, depth, source_url):
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(2)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        if is_404_page(soup):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url)
            return [], ""
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        product_md_counts[product] += 1
        links = extract_links_from_html(html, url)
        return links, base
    except TimeoutException as te:
        logger.error(f"[Timeout Error] {url} — {te}")
    except WebDriverException as wde:
        logger.error(f"[WebDriver Error] {url} — {wde}. Restarting browser.")
        driver.quit()
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=webdriver.ChromeOptions())
    except Exception as e:
        logger.error(f"[Type 3 Error] {url} — {e}")
    return [], ""

def handle_type_4(driver, url, product, folder, depth, source_url):
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(2)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        if is_404_page(soup):
            logger.warning(f"Skipping 404 page: {url}")
            log_skipped_404(url)
            return [], ""
        main = soup.find("main") or soup.body or soup
        content_html = str(main)
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(content_html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        product_md_counts[product] += 1
        links = extract_links_from_html(content_html, url)
        return links, base
    except TimeoutException as te:
        logger.error(f"[Timeout Error] {url} — {te}")
    except WebDriverException as wde:
        logger.error(f"[WebDriver Error] {url} — {wde}. Restarting browser.")
        driver.quit()
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=webdriver.ChromeOptions())
    except Exception as e:
        logger.error(f"[Type 4 Error] {url} — {e}")
    return [], ""

def process_link_bfs(product_info):
    product = product_info["product"]
    urls = product_info.get("urls", [])
    folder = os.path.join(BASE_OUTPUT_FOLDER, product.replace(" ", "_"))
    os.makedirs(folder, exist_ok=True)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=webdriver.ChromeOptions())
    queue_by_depth = defaultdict(list)

    for start_url in urls:
        with visited_lock:
            visited[start_url] = {
                "product": product,
                "source_url": start_url,
                "filename": f"output_{sanitize_filename(start_url)}.md"
            }
        queue_by_depth[0].append((start_url, start_url))

    try:
        for depth in range(MAX_LINK_LEVEL + 1):
            urls_at_depth = queue_by_depth[depth]
            if not urls_at_depth:
                continue
            logger.info(f"\n📦 {product}, Depth {depth} — {len(urls_at_depth)} pages to scrape")
            for idx, (url, src) in enumerate(urls_at_depth, start=1):
                if product_md_counts[product] >= MAX_PAGES_PER_PRODUCT:
                    logger.info(f"🛑 {product} reached max page limit — stopping early.")
                    return
                logger.info(f"✅ {product}, Depth {depth} — {idx}/{len(urls_at_depth)}")

                page_type = detect_page_type(url)
                if page_type == 1:
                    links, _ = handle_type_1(driver, url, product, folder, depth, src)
                elif page_type == 2:
                    links, _ = handle_type_2(driver, url, product, folder, depth, src)
                elif page_type == 3:
                    links, _ = handle_type_3(driver, url, product, folder, depth, src)
                elif page_type == 4:
                    links, _ = handle_type_4(driver, url, product, folder, depth, src)
                else:
                    logger.warning(f"❌ Unknown page type: {url}")
                    continue

                with graph_lock:
                    crawl_graph["nodes"].add(url)
                    for link in links:
                        crawl_graph["nodes"].add(link["href"])
                        crawl_graph["edges"].add((url, link["href"]))

                allowed_prefixes = PRODUCT_URL_PREFIXES.get(product, [])
                for link in links:
                    href = link["href"]
                    if not any(prefix in href for prefix in allowed_prefixes):
                        continue
                    if not any(href.startswith(domain) for domain in ALLOWED_DOMAINS):
                        continue
                    with visited_lock:
                        if href in visited:
                            continue
                        visited[href] = {
                            "product": product,
                            "source_url": url,
                            "filename": f"output_{sanitize_filename(href)}.md"
                        }
                    if depth < MAX_LINK_LEVEL:
                        queue_by_depth[depth + 1].append((href, url))
    finally:
        driver.quit()

def summarize_md_counts():
    summary_counts = defaultdict(int)
    logger.info(f"\n🔍 Scanning '{BASE_OUTPUT_FOLDER}' for markdown files...")
    for product_dir in os.listdir(BASE_OUTPUT_FOLDER):
        full_path = os.path.join(BASE_OUTPUT_FOLDER, product_dir)
        if os.path.isdir(full_path):
            md_files = [f for f in os.listdir(full_path) if f.endswith(".md")]
            summary_counts[product_dir] = len(md_files)
    logger.info("\n📊 Crawl Summary:")
    for product, count in summary_counts.items():
        logger.info(f"  - {product}: {count} markdown files")
    with open(os.path.join(BASE_OUTPUT_FOLDER, "summary.log"), "w", encoding="utf-8") as f:
        for product, count in summary_counts.items():
            f.write(f"{product}: {count} markdown files\n")

def main():
    threads = []
    for info in START_LINKS:
        t = threading.Thread(target=process_link_bfs, args=(info,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    summarize_md_counts()

if __name__ == "__main__":
    main()
