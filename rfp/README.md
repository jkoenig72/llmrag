# RAG Processing System for RFI/RFP

A Retrieval-Augmented Generation system for answering questions about Salesforce products with compliance ratings. Designed specifically for responding to Request for Information (RFI) and Request for Proposal (RFP) documents.

## Overview

This system processes questions from a Google Sheet, uses a FAISS vector database to retrieve relevant context, and generates structured answers using a Language Model. The answers include both explanatory text and a compliance rating that indicates how well Salesforce products meet the requirements.

## Features

- **Google Sheets Integration**: Input/output with robust error handling and API rate limiting
- **Text Processing**: Cleaning, normalization, and JSON response formatting
- **Vector Search**: FAISS index with product-specific knowledge
- **LLM Integration**: Multiple provider support (Ollama, llama.cpp)
- **Compliance Rating**: Assignment (FC, PC, NC, NA) with automatic categorization
- **Reference Extraction**: URL extraction and validation with Selenium
- **Question Filtering**: Advanced relevance filtering for out-of-scope questions
- **Custom Context**: Customer-specific document indices for tailored responses
- **Batch Processing**: API throttling for efficiency
- **Refinement Chain**: Multi-step processing with document aggregation
- **Detailed Logging**: Comprehensive logging of all processing steps
- **Dynamic Embedding Management**: Efficient memory handling for large models

## Requirements

- Python 3.8+
- Google API credentials (JSON file)
- FAISS index with Salesforce documentation
- LLM server (Ollama or llama.cpp)
- Chrome browser (for reference validation)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/jkoenig72/llmrag.git
cd llmrag/rfp
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
RETRIEVER_K_DOCUMENTS="6"
CUSTOMER_RETRIEVER_K_DOCUMENTS="2"
BATCH_SIZE="5"
API_THROTTLE_DELAY="3"
MAX_LINKS_PROVIDED="2"
```

## Usage

### Getting Started

1. Prepare a Google Sheet with the following format:
   - **First row:** Headers (e.g., "No.", "Question", "Primary Product", "Answer", etc.)
   - **Second row:** Include `#answerforge#` in column A, and define roles:
     - `question` - Column where questions are stored
     - `context` - Column for additional context (optional)
     - `primary_product` - Column for product focus (optional)
     - `answer` - Column where answers will be written
     - `compliance` - Column for compliance ratings
     - `references` - Column for reference URLs (optional)

2. Start your LLM server:
   - For llama.cpp: `./llama-server --model /path/to/model.gguf --ctx-size 4096 --port 8080`
   - For Ollama: Ensure Ollama is running with your model available (`ollama serve`)

3. Run the main script:
   ```bash
   python main.py
   ```

4. Follow the interactive prompts to:
   - Select product focus
   - Choose customer context folder (if available)
   - Select starting row number

### Command Line Options

The system is primarily configured through environment variables or the `.env` file. Main settings include:

- `GOOGLE_SHEET_ID`: ID of the Google Sheet to process
- `GOOGLE_CREDENTIALS_FILE`: Path to Google API credentials
- `INDEX_DIR`: Path to FAISS index with Salesforce documentation
- `LLM_PROVIDER`: "llamacpp" or "ollama"
- `LLM_MODEL`: Name of the LLM model to use
- `RETRIEVER_K_DOCUMENTS`: Number of documents to retrieve from FAISS (default: 6)
- `CUSTOMER_RETRIEVER_K_DOCUMENTS`: Number of customer documents to retrieve (default: 2)
- `MAX_LINKS_PROVIDED`: Maximum number of references to include (default: 2)

## Google Sheet Setup

### Required Structure

1. **Headers Row (Row 1)**: Define your column headers
2. **Role Definition Row (Row 2)**:
   - First cell must contain `#answerforge#`
   - Remaining cells define the role of each column (e.g., "question", "compliance")

Example:
```
| #answerforge# | question | primary_product | context | compliance | answer |
|--------------|----------|----------------|---------|------------|--------|
| 1            | Does...? | Sales Cloud    | Additional info | (empty) | (empty) |
```

### Role Definitions

- `question`: Required - Contains the questions to answer
- `primary_product`: Optional - Specifies the Salesforce product focus
- `context`: Optional - Additional information about the question
- `compliance`: Required - Where compliance ratings will be written
- `answer`: Required - Where answers will be written
- `references`: Optional - Where reference URLs will be written

## Project Structure

```
rfp/
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
├── embedding_manager.py    # Dynamic embedding model management
├── reference_handler.py    # Reference URL validation
├── question_logger.py      # Detailed question logging
└── requirements.txt        # Required Python packages
```

## Processing Flow

1. **Question retrieval:** Questions are loaded from the Google Sheet
2. **Document retrieval:** 
   - Product documents from the main FAISS index
   - Optional customer documents from customer index if selected
3. **Refine chain processing:**
   - Initial answer generated from first document(s)
   - Each additional document refines the answer
   - Multiple LLM calls create increasingly comprehensive responses
4. **Reference validation:**
   - URLs are extracted from the answer
   - Each URL is validated using Selenium
   - Only working links are included (limited to MAX_LINKS_PROVIDED)
5. **Answer extraction:** Structured JSON responses are parsed
6. **Google Sheet update:** Answers, compliance ratings, and references written back

## Compliance Ratings

- **FC** (Fully Compliant): Supported via standard configuration or UI-based setup
- **PC** (Partially Compliant): Requires custom development (Apex, LWC, APIs)
- **NC** (Not Compliant): Not possible in Salesforce even with customization
- **NA** (Not Applicable): Question is out of scope for Salesforce

## Customer-Specific Context

The system supports loading customer-specific documents to provide tailored responses:

1. Create a folder with the customer name in the `RFP_DOCUMENTS_DIR` directory
2. Add PDF or DOCX files with customer-specific information
3. When running the system, select the customer folder when prompted
4. The system will create or use an existing index for those documents

The customer context is combined with product knowledge to provide more accurate, tailored responses.

## Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| RETRIEVER_K_DOCUMENTS | Number of documents to retrieve from FAISS | 6 |
| CUSTOMER_RETRIEVER_K_DOCUMENTS | Number of customer documents to retrieve | 2 |
| BATCH_SIZE | Number of updates to batch together | 5 |
| API_THROTTLE_DELAY | Seconds to wait between API calls | 3 |
| MAX_LINKS_PROVIDED | Maximum number of links to include in references | 2 |
| CLEAN_UP_CELL_CONTENT | Apply text cleaning to cells | False |
| SUMMARIZE_LONG_CELLS | Summarize texts longer than the word limit | False |
| MAX_WORDS_BEFORE_SUMMARY | Word limit before summarization | 200 |
| INTERACTIVE_PRODUCT_SELECTION | Enable product selection prompts | True |

## Detailed Logging

The system provides comprehensive logging for debugging and analysis:

1. **Main Log**: `{BASE_DIR}/rag_processing.log`
2. **Refine Logs**: `{BASE_DIR}/refine_logs/`
3. **Chain Logs**: `{BASE_DIR}/chain_logs/`

Chain logs record each step of the processing chain, including:
- Prompts sent to the LLM
- Raw LLM responses
- Parsed answers
- Changes between refinement steps
- Timing information

## Troubleshooting

### Common Issues

1. **Google Sheets API errors**: Verify credentials and permissions
2. **LLM connection errors**: Confirm your LLM server is running at the right address and port
3. **FAISS index not found**: Ensure INDEX_DIR points to a valid FAISS index directory
4. **Reference validation errors**: Check that Chrome is installed and WebDriver is accessible
5. **Memory limitations**: If using large models, consider enabling the CPU flag or using a machine with more RAM

### Debugging Tips

1. Check `rag_processing.log` for general errors
2. Examine refine logs for specific question processing issues
3. Review chain logs for detailed LLM interaction tracing
4. Try reducing `RETRIEVER_K_DOCUMENTS` if memory issues occur
5. Check that your LLM model is set up correctly and supports JSON output

## Example Output

```
✅ Row 3 complete
Question: In your Order Management module, do you support the concept of a Point of no return PONR?
Product Focus: Communications Cloud

Answer:
Yes, we support the concept of a Point of No Return (PONR) in our Order Management module within 
Communications Cloud. You can configure PONR at the order or item level, preventing further modifications 
once an order or item reaches a specific status.

Compliance: FC

References (2):
• https://help.salesforce.com/s/articleView?id=ind.comms_t_rules_for_how_point_of_no_returnponrpropagates_through_a_decompositionplan_234475.htm&language=en_US&type=5
```

**License and Contributions**

Maintained by Master Control Program. Contributions and feedback are welcome — please submit pull requests or open issues on GitHub.