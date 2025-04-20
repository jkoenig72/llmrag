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