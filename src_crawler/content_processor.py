import re
from bs4 import BeautifulSoup
from markdownify import markdownify as md_convert
from urllib.parse import urljoin
from datetime import datetime

def clean_cookie_content(soup):
    """Remove cookie consent related content from the soup."""
    cookie_keywords = ["cookie", "consent", "accept all", "do not accept", "privacy", "cookie settings"]
    for tag in soup.find_all(True):
        if any(kw in tag.get_text().lower() for kw in cookie_keywords):
            tag.decompose()
    return soup

def create_markdown(content_html, tag, depth, source_url, title_override=None):
    """Convert HTML content to Markdown with YAML frontmatter."""
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
    """Extract all links from HTML content and normalize URLs."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        link = {"text": a.get_text().strip(), "href": urljoin(origin, a["href"])}
        links.append(link)
    return links

def detect_page_type(url):
    """Determine the type of page based on URL patterns."""
    if "help.salesforce.com/s/articleView" in url or "help.mulesoft.com/s/article" in url:
        return 1
    elif "developer.salesforce.com/docs" in url or "docs.mulesoft.com" in url:
        return 2
    elif "help.salesforce.com/s/products" in url:
        return 3
    elif "www.mulesoft.com/platform" in url:
        return 4
    return 0