"""
Configuration settings for the Salesforce documentation crawler.

This module defines constants, settings, and configuration variables 
used throughout the crawler application.
"""

import os
import json

# Configuration defaults
BASE_OUTPUT_FOLDER = "RAG_Collection"
MAX_LINK_LEVEL = 50
MAX_PAGES_PER_PRODUCT = 50000

# Product URL prefixes for categorizing content
PRODUCT_URL_PREFIXES = {
    "MuleSoft": [
        "/platform/", "/api/", "/general/", 
        "/runtime-manager/", "/api-manager/", "/studio/", "/anypoint/",
        "/docs/", "/s/article", "/s/resources", "/s/training"
    ],
    "Communications_Cloud": [
        "id=ind.comms", "/products/communications", 
        "/articleView?id=ind.comms", "/apex/HTViewHelpDoc?id=ind.comms"
    ],
    "Sales_Cloud": [
        "id=sales", "/products/sales", 
        "/articleView?id=sales", "/apex/HTViewHelpDoc?id=sales",
        "/s/articleView?id=sales"
    ],
    "Service_Cloud": [
        "id=service", "/products/service", 
        "/articleView?id=service", "/apex/HTViewHelpDoc?id=service",
        "/s/articleView?id=service"
    ],
    "Experience_Cloud": [
        "id=experience", "/products/experience", 
        "/articleView?id=experience", "/apex/HTViewHelpDoc?id=experience",
        "/s/articleView?id=experience"
    ],
    "Marketing_Cloud": [
        "id=mktg", "/products/marketing", 
        "/articleView?id=mktg", "/apex/HTViewHelpDoc?id=mktg",
        "/s/articleView?id=mktg", "id=marketing"
    ],
    "Data_Cloud": [
        "id=data", "/products/datacloud", 
        "/articleView?id=data", "/apex/HTViewHelpDoc?id=data",
        "/s/articleView?id=data"
    ],
    "Platform": [
        "id=platform", "/products/platform", 
        "/articleView?id=platform", "/apex/HTViewHelpDoc?id=platform",
        "/s/articleView?id=platform"
    ],
    "Agentforce": [
        "id=ai", "ai.generative_ai", 
        "/articleView?id=ai", "/apex/HTViewHelpDoc?id=ai",
        "/s/articleView?id=ai", "generative_ai"
    ],
}

# Add Trailhead patterns to all products
for product in PRODUCT_URL_PREFIXES:
    PRODUCT_URL_PREFIXES[product].append("/content/learn/")
    PRODUCT_URL_PREFIXES[product].append("/en/content/learn/")

# Load starting links
START_LINKS_PATH = os.path.join(os.path.dirname(__file__), "start_links.json")
with open(START_LINKS_PATH, "r", encoding="utf-8") as f:
    START_LINKS = json.load(f)

# Allowed domains for crawling
ALLOWED_DOMAINS = [
    "https://help.salesforce.com",
    "https://developer.salesforce.com",
    "https://trailhead.salesforce.com",
    "https://salesforce.com/docs",
    "https://www.mulesoft.com",
    "https://help.mulesoft.com",
    "https://docs.mulesoft.com"
]

# File paths
SKIPPED_404_PATH = os.path.join(BASE_OUTPUT_FOLDER, "skipped_404.log")
SUMMARY_LOG_PATH = os.path.join(BASE_OUTPUT_FOLDER, "summary.log")