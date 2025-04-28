# RAG Processing System

A Retrieval-Augmented Generation system for answering questions about Salesforce products with compliance ratings.

## Overview

This system processes questions from a Google Sheet, uses a FAISS vector database to retrieve relevant context, and generates structured answers using a Language Model. The answers include both explanatory text and a compliance rating that indicates how well Salesforce products meet the requirements.

## Features

- 📊 Google Sheets integration for input/output with robust error handling
- 🧹 Text cleaning, normalization, and JSON response formatting
- 📝 Automatic summarization of long texts
- 🔍 Vector search using FAISS index with product-specific knowledge
- 🤖 LLM-powered question answering with multiple provider support (Ollama, llama.cpp)
- ✅ Compliance rating assignment (FC, PC, NC, NA) with optimistic fallback
- 🔗 Automatic URL extraction and formatting for references
- 🚫 Advanced question relevance filtering to identify out-of-scope questions
- 📝 Detailed question processing logs for troubleshooting
- 📦 Customer-specific document indices for tailored responses
- 📎 Enhanced JSON parsing with multiple fallback strategies
- 🔄 Batch processing with API throttling for efficiency

## Requirements

- Python 3.8+
- Google API credentials (JSON file)
- FAISS index with Salesforce documentation
- LLM server (Ollama or llama.cpp)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/rag-system.git
cd rag-system
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables or create a `.env` file:
```bash
# Google Sheets Configuration
GOOGLE_SHEET_ID="your-sheet-id"
GOOGLE_CREDENTIALS_FILE="path/to/credentials.json"

# Directory Configuration
BASE_DIR="~/RAG"
INDEX_DIR="~/faiss_index_sf"
RFP_DOCUMENTS_DIR="~/RFP_Documents"
CUSTOMER_INDEX_DIR="~/customer_indices"

# LLM Configuration
LLM_PROVIDER="llamacpp"  # "ollama" or "llamacpp"
LLM_MODEL="mistral-small3.1"
OLLAMA_BASE_URL="http://localhost:11434"
LLAMA_CPP_BASE_URL="http://localhost:8080"
EMBEDDING_MODEL="intfloat/e5-large-v2"

# Processing Configuration
SKIP_INDEXING="True"
BATCH_SIZE="5"
API_THROTTLE_DELAY="3"
RETRIEVER_K_DOCUMENTS="8"
```

## Usage

### Basic Usage

Run the main script to process all questions in the Google Sheet:

```bash
python main.py
```

The system will:
1. Check if the LLM server is running
2. Connect to Google Sheets
3. Ask you to select a starting row and product focus
4. Process questions, displaying progress
5. Update the Google Sheet with the answers, compliance ratings, and references

### Google Sheet Format

The sheet must follow this structure:
1. First row: Headers (any text)
2. Marker row: Must contain `#answerforge#` in the first column, with role names in other columns
3. Content rows: Data to be processed

Example roles:
- `question`: The question to be answered
- `context`: Additional context for the question
- `primary_product`: The primary product focus (optional)
- `answer`: Where the answer will be written
- `compliance`: Where the compliance rating will be written
- `references`: Where reference URLs will be written

### Compliance Ratings

- **FC** (Fully Compliant): Supported via standard configuration or UI-based setup
- **PC** (Partially Compliant): Requires custom development (Apex, LWC, APIs)
- **NC** (Not Compliant): Not possible in Salesforce even with customization
- **NA** (Not Applicable): Question is out of scope for Salesforce

### Customer-Specific Context

The system supports loading customer-specific documents to provide tailored responses:

1. Create a folder with the customer name in the `RFP_DOCUMENTS_DIR` directory
2. Add PDF or DOCX files with customer-specific information
3. When running the system, select the customer folder when prompted
4. The system will create or use an existing index for those documents

Customer context is combined with product knowledge to provide more accurate answers.

### Configuration Options

|
 Setting 
|
 Description 
|
 Default 
|
|
---------
|
-------------
|
---------
|
|
 SKIP_INDEXING 
|
 Skip creating index and use existing one 
|
 True 
|
|
 CLEAN_UP_CELL_CONTENT 
|
 Apply text cleaning to cells 
|
 True 
|
|
 SUMMARIZE_LONG_CELLS 
|
 Summarize texts longer than the word limit 
|
 True 
|
|
 MAX_WORDS_BEFORE_SUMMARY 
|
 Word limit before summarization 
|
 200 
|
|
 BATCH_SIZE 
|
 Number of updates to batch together 
|
 5 
|
|
 API_THROTTLE_DELAY 
|
 Seconds to wait between API calls 
|
 3 
|
|
 RETRIEVER_K_DOCUMENTS 
|
 Number of documents to retrieve from FAISS 
|
 8 
|
|
 CUSTOMER_RETRIEVER_K_DOCUMENTS 
|
 Number of customer documents to retrieve 
|
 5 
|
|
 INTERACTIVE_PRODUCT_SELECTION 
|
 Allow interactive selection of products to focus on 
|
 True 
|

## Project Structure

```
.
├── main.py                 # Main orchestration script
├── config.py               # Configuration parameters
├── llm_utils.py            # Utilities for LLM and FAISS
├── llm_wrapper.py          # LLM provider initialization
├── prompts.py              # Prompt templates
├── sheets_handler.py       # Google Sheets integration
├── text_processing.py      # Text cleaning and summarization
├── question_processor.py   # Question processing logic
├── product_selector.py     # Product selection and user interaction
├── customer_docs.py        # Customer document handling
├── question_logger.py      # Detailed question logging
└── requirements.txt        # Required Python packages
```

## Advanced Features

### Question Relevance Filtering

The system automatically identifies irrelevant questions (e.g., about weather, colors, history) and marks them as NA without sending to the LLM, saving processing time and improving accuracy.

### JSON Response Parsing

Multiple strategies are used to extract structured information from LLM responses:
1. Direct JSON parsing
2. Extraction from code blocks
3. Pattern matching for specific fields
4. Fallback to text-based extraction

### Reference URL Handling

URLs are automatically extracted from the context and response, formatted with bullet points, and properly stored in the Google Sheet for easy access.

### Detailed Logging

Each question processed creates a detailed log file with:
- Original question and context
- Retrieved information
- Complete prompt sent to LLM
- Raw and parsed responses
- Processing summary

Logs are stored in the `question_logs` directory within `BASE_DIR`.

## Troubleshooting

### Common Issues

1. **FAISS index not found**: Ensure INDEX_DIR points to a valid FAISS index directory

2. **Google Sheets API errors**: Verify credentials and permissions

3. **LLM connection errors**: Confirm your LLM server is running at the right address and port

4. **Empty answers**: Check the question log file to see the raw LLM response

### Logging

Logs are written to both the console and a log file at `{BASE_DIR}/rag_processing.log`. Detailed question processing logs are stored in `{BASE_DIR}/question_logs/`.

