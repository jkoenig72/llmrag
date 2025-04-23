import re
from bs4 import BeautifulSoup
from markdownify import markdownify as md_convert
from urllib.parse import urljoin
from datetime import datetime

def clean_cookie_content(soup):
    """
    Remove cookie consent related content from the soup.
    
    Identifies and removes elements that contain cookie-related keywords
    to clean up the content before conversion.
    
    Args:
        soup (BeautifulSoup): The BeautifulSoup object to clean.
        
    Returns:
        BeautifulSoup: The cleaned BeautifulSoup object.
    """
    cookie_keywords = ["cookie", "consent", "accept all", "do not accept", "privacy", "cookie settings"]
    for tag in soup.find_all(True):
        if any(kw in tag.get_text().lower() for kw in cookie_keywords):
            tag.decompose()
    return soup

def create_markdown(content_html, tag, depth, source_url, title_override=None):
    """
    Convert HTML content to Markdown with YAML frontmatter.
    
    Processes HTML content by cleaning it, converting to markdown, and adding
    YAML frontmatter with metadata. Also generates a table of contents.
    
    Args:
        content_html (str): The HTML content to convert.
        tag (str): Product tag/category for the content.
        depth (int): Depth level in the crawl hierarchy.
        source_url (str): Original source URL of the content.
        title_override (str, optional): Custom title to use instead of extracting from content.
        
    Returns:
        str: Markdown content with YAML frontmatter and table of contents.
    """
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
    """
    Extract all links from HTML content and normalize URLs.
    
    Finds all anchor tags in the HTML, extracts their href attributes,
    and normalizes relative URLs using the origin URL.
    
    Args:
        html (str): The HTML content to extract links from.
        origin (str): The origin URL for resolving relative links.
        
    Returns:
        list: A list of dictionaries with 'text' and 'href' keys for each link.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        link = {"text": a.get_text().strip(), "href": urljoin(origin, a["href"])}
        links.append(link)
    return links

def detect_page_type(url):
    """
    Determine the type of page based on URL patterns.
    
    Analyzes the URL to categorize it into one of several predefined types:
    1: Salesforce/MuleSoft article view pages (/s/articleView)
    2: Developer documentation pages
    3: Product pages
    4: MuleSoft platform pages
    5: Standard Salesforce article view pages (without /s/)
    6: Salesforce Apex Help pages
    7: Trailhead learning content
    0: Unknown/uncategorized pages
    
    Args:
        url (str): The URL to analyze.
        
    Returns:
        int: The detected page type (0-7).
    """
    if "help.salesforce.com/s/articleView" in url or "help.mulesoft.com/s/article" in url:
        return 1  # Current type 1 - s/articleView pattern
    elif "developer.salesforce.com/docs" in url or "docs.mulesoft.com" in url:
        return 2  # Current type 2 - developer docs
    elif "help.salesforce.com/s/products" in url:
        return 3  # Current type 3 - product pages
    elif "www.mulesoft.com/platform" in url:
        return 4  # Current type 4 - mulesoft platform
    elif "help.salesforce.com/articleView" in url:
        return 5  # New type 5 - standard articleView pattern (without /s/)
    elif "help.salesforce.com/apex/HTViewHelpDoc" in url:
        return 6  # New type 6 - Apex Help pages
    elif "trailhead.salesforce.com" in url and ("/content/learn/" in url or "/en/content/learn/" in url):
        return 7  # New type 7 - Trailhead learning content
    return 0  # Unknown type