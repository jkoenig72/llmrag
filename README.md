# Web Scraper and Request For Information (RFI) Processor

## Overview

This project includes tools for scraping and processing Salesforce and MuleSoft documentation, and automating responses to Requests for Information (RFIs) using advanced language models and retrieval systems.

## Project Structure

- **env.sh**: A shell script for setting environment variables or initializing the environment setup required for the scraping sessions.
- **rag.py**: A script for processing and responding to RFIs using a combination of large language models (LLMs), FAISS (a library for efficient similarity search), and Google Sheets as a data source. It provides a structured approach to evaluating compliance and crafting tailored responses.
- **rfp.py**: Similar to `rag.py`, this script also handles RFI responses but may be configured to use different models or indexing strategies to handle varied processing needs.
- **requirements.txt**: Lists the Python dependencies needed to run the scraper and RFI processing scripts, including libraries like `selenium`, `beautifulsoup4`, `gspread`, and `langchain`.
- **start_links.json**: Contains structured JSON data specifying initial URLs and products for the scraper to process, defining the starting points of the scrape.
- **test.py**: A script for testing the functionalities of the scraper, ensuring that each component runs as expected and handles edge cases and errors properly.
- **universal_sf_scraper.py**: The core Python file that defines how different Salesforce and MuleSoft product pages are scraped and processed, implementing functionality such as markdown conversion and multithreading for efficient data collection.

## Installation

tbd
