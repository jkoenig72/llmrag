# RAG Processing System

A Retrieval-Augmented Generation system for answering questions about Salesforce products with compliance ratings.

## Overview

This system processes questions from a Google Sheet, uses a FAISS vector database to retrieve relevant context, and generates structured answers using a Language Model. The answers include both explanatory text and a compliance rating that indicates how well Salesforce products meet the requirements.

## Features

- 📊 Google Sheets integration for input/output
- 🧹 Text cleaning and normalization
- 📝 Automatic summarization of long texts
- 🔍 Vector search using FAISS index
- 🤖 LLM-powered question answering with Ollama
- ✅ Compliance rating assignment (FC, PC, NC, NA)
- 🔄 Batch processing for efficiency

## Requirements

- Python 3.8+
- Google API credentials (JSON file)
- FAISS index with Salesforce documentation
- Ollama LLM server

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/rag-processing.git
cd rag-processing
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

# LLM Configuration
LLM_MODEL="gemma3:12b"
LLM_BASE_URL="http://localhost:11434"
EMBEDDING_MODEL="intfloat/e5-large-v2"

# Processing Configuration
SKIP_INDEXING="True"
BATCH_SIZE="5"
API_THROTTLE_DELAY="1"
```

## Usage

### Basic Usage

Run the main script to process all questions in the Google Sheet:

```bash
python main.py
```

### Google Sheet Format

The sheet must follow this structure:
1. First row: Headers (any text)
2. Marker row: Must contain `#answerforge#` in the first column, with role names in other columns
3. Content rows: Data to be processed

Example roles:
- `question`: The question to be answered
- `context`: Additional context for the question
- `answer`: Where the answer will be written
- `compliance`: Where the compliance rating will be written

### Compliance Ratings

- **FC** (Fully Compliant): Supported via standard configuration or UI-based setup
- **PC** (Partially Compliant): Requires custom development (Apex, LWC, APIs)
- **NC** (Not Compliant): Not possible in Salesforce even with customization
- **NA** (Not Applicable): Question is out of scope for Salesforce

### Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| SKIP_INDEXING | Skip creating index and use existing one | True |
| CLEAN_UP_CELL_CONTENT | Apply text cleaning to cells | True |
| SUMMARIZE_LONG_CELLS | Summarize texts longer than the word limit | True |
| MAX_WORDS_BEFORE_SUMMARY | Word limit before summarization | 200 |
| BATCH_SIZE | Number of updates to batch together | 1 |
| API_THROTTLE_DELAY | Seconds to wait between API calls | 1 |

## Project Structure

```
.
├── config.py              # Configuration parameters
├── llm_utils.py           # Utilities for LLM and FAISS
├── main.py                # Main execution script
├── prompts.py             # Prompt templates
├── sheets_handler.py      # Google Sheets integration
└── text_processing.py     # Text cleaning and summarization
```

## Example Workflow

1. The system loads data from a Google Sheet
2. Text is cleaned and/or summarized if configured
3. For each question:
   - Relevant context is retrieved from the FAISS index
   - The LLM generates an answer with a compliance rating
   - Results are written back to the Google Sheet
4. Processing status is logged to the console and log file

## Advanced Usage Examples

### Process Only Specific Rows

To process only specific rows, modify `main.py`:

```python
# Filter records to process only specific rows
filtered_records = [r for r in records if r["sheet_row"] in [5, 8, 12]]
process_questions(filtered_records, qa_chain, output_columns, sheet_handler)
```

### Custom Compliance Rating Logic

To modify compliance rating determination, edit `extract_json_from_llm_response` in `llm_utils.py`.

### Implementing Retry Logic

Example of adding retry logic for API calls:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def invoke_llm_with_retry(llm, prompt):
    return llm.invoke(prompt)
```

## Troubleshooting

### Common Issues

1. **FAISS index not found**: Ensure INDEX_DIR points to a valid FAISS index directory

2. **Google Sheets API errors**: Verify credentials and permissions

3. **LLM connection errors**: Confirm Ollama server is running at LLM_BASE_URL

### Logging

Logs are written to both the console and a log file at `{BASE_DIR}/rag_processing.log`.

## Recent Updates

- Added comprehensive PEP 257-compliant docstrings to all functions
- Improved error handling with more specific exception handling
- Refactored main.py to extract `process_questions` function for better organization
- Enhanced documentation including flow diagrams and sequence diagrams
- Standardized code style and improved readability
