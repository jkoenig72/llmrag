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
- 🔄 Refined knowledge aggregation across multiple documents

## Requirements

- Python 3.8+
- Google API credentials (JSON file)
- FAISS index with Salesforce documentation
- LLM server (Ollama or llama.cpp)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/jkoenig72/llmrag.git
cd llmrag
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
RETRIEVER_K_DOCUMENTS="3"
CUSTOMER_RETRIEVER_K_DOCUMENTS="3"
```

## User Guide

### Getting Started

This section provides a step-by-step guide to using the RAG Processing System to answer RFP/RFI questions.

#### Step 1: Prepare Your Google Sheet

1. **Create a new Google Sheet** or use the provided template (`Example Sheet.csv`).
2. **Structure your sheet** with the following format:
   - **First row:** Headers (e.g., "No.", "Question", "Primary Product", "Answer", etc.)
   - **Second row:** Include `#answerforge#` in column A, and define roles in other columns:
     - `question` - Column where questions are stored
     - `context` - Column for additional context (optional)
     - `primary_product` - Column for product focus (optional)
     - `answer` - Column where answers will be written
     - `compliance` - Column for compliance ratings
     - `references` - Column for reference URLs (optional)
   - **Subsequent rows:** Your RFP/RFI questions and data

3. **Share the sheet** with the service account email from your Google API credentials.

#### Step 2: Set Up the Example Sheet

The included `Example Sheet.csv` can be used as a template:

1. **Import to Google Sheets:**
   - Open Google Sheets
   - File > Import > Upload > Select `Example Sheet.csv`
   - Choose "Replace spreadsheet" or "Create new spreadsheet"
   - Click "Import data"

2. **Format the sheet correctly:**
   - Ensure row 2 contains `#answerforge#` in column A
   - Add appropriate role labels (question, answer, compliance, etc.)
   - Your sheet should look like:

| | No. | Additional Information | Additional Information2 | Primary Product | Question | Compliant Level | Answer |
|---|---|---|---|---|---|---|---|
| #answerforge# | | context | | primary_product | question | compliance | answer |
| | 1 | | | Communications Cloud | In your Order Management OM module, do you support the concept of a Point of no return PONR? | | |
| | 2 | | | Service Cloud | Do you support Email to Case functionality? If so explain how it works. | | |

#### Step 3: Configure the System

1. **Edit the configuration file** (`config.py`) or set environment variables with:
   - Your Google Sheet ID (from the URL)
   - Path to your Google credentials JSON file
   - LLM provider settings (Ollama or llama.cpp)
   - Document retrieval settings

2. **For customer-specific context:**
   - Create a folder with the customer name in `RFP_DOCUMENTS_DIR`
   - Add PDFs or DOCX files with customer information

#### Step 4: Run the System

1. **Start your LLM server:**
   - For llama.cpp: `./llama-server --model /path/to/model.gguf --ctx-size 4096 --port 8080`
   - For Ollama: Ensure Ollama is running with your model available

2. **Run the main script:**
   ```bash
   python main.py
   ```

3. **Interactive prompts will guide you:**
   - Select product focus (e.g., "Communications Cloud", "Service Cloud")
   - Choose customer context folder (if available)
   - Select starting row number (to resume processing)

4. **Monitor progress:**
   - The system will display detailed logs showing:
     - Documents being retrieved
     - LLM processing steps
     - Answer extraction
     - Google Sheet updates

#### Step 5: Review Results

1. **Check your Google Sheet** for generated answers, compliance ratings, and references.
2. **Review detailed logs** in `{BASE_DIR}/question_logs/` for each question processed.
3. **Examine refine logs** in `{BASE_DIR}/refine_logs/` to see how answers evolved across documents.

### Processing Flow

1. **Question retrieval:** Questions are loaded from the Google Sheet
2. **Document retrieval:** 
   - `RETRIEVER_K_DOCUMENTS` documents from the main FAISS index
   - Optional `CUSTOMER_RETRIEVER_K_DOCUMENTS` from customer index if selected
3. **Refine chain processing:**
   - Initial answer generated from first document(s)
   - Each additional document refines the answer
   - Multiple LLM calls create increasingly comprehensive responses
4. **Answer extraction:** Structured JSON responses are parsed
5. **Google Sheet update:** Answers, compliance ratings, and references written back

### Optimizing for Best Results

- **Set appropriate document retrieval counts:**
  ```
  RETRIEVER_K_DOCUMENTS="3"
  CUSTOMER_RETRIEVER_K_DOCUMENTS="3"
  ```
  These should typically be the same value for balanced results.

- **Structure questions clearly:**
  - Be specific about which Salesforce product you're asking about
  - Provide additional context in the context column when needed
  - Use the primary_product column to ensure proper focus

- **Batch processing:**
  - Adjust `BATCH_SIZE` in config for more efficient sheet updates
  - Increase `API_THROTTLE_DELAY` if you hit API rate limits

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

| Setting | Description | Default |
|---------|-------------|---------|
| SKIP_INDEXING | Skip creating index and use existing one | True |
| CLEAN_UP_CELL_CONTENT | Apply text cleaning to cells | False |
| SUMMARIZE_LONG_CELLS | Summarize texts longer than the word limit | False |
| MAX_WORDS_BEFORE_SUMMARY | Word limit before summarization | 200 |
| BATCH_SIZE | Number of updates to batch together | 5 |
| API_THROTTLE_DELAY | Seconds to wait between API calls | 3 |
| RETRIEVER_K_DOCUMENTS | Number of documents to retrieve from FAISS | 3 |
| CUSTOMER_RETRIEVER_K_DOCUMENTS | Number of customer documents to retrieve | 3 |
| INTERACTIVE_PRODUCT_SELECTION | Allow interactive selection of products to focus on | True |

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

### Refine Strategy for Knowledge Aggregation

The system uses a sophisticated refine strategy to build comprehensive answers:

1. **Initial Context**: Starts with the first retrieved document
2. **Iterative Refinement**: Each additional document refines the answer with new information
3. **Knowledge Accumulation**: Builds a more complete answer with each refinement step
4. **Product Focus**: Maintains product-specific context throughout refinement
5. **Multi-step Processing**: Typically 3-5 LLM calls per question (initial + refinements)

This approach ensures that information from multiple documents is combined coherently, providing more detailed and accurate answers than single-document retrieval.

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

Each question processed creates detailed log files:

1. **Question Logs**: Basic processing information
   - Original question and context
   - Retrieved information
   - Complete prompt sent to LLM
   - Raw and parsed responses
   - Processing summary

2. **Refine Logs**: Trace the refinement process
   - Initial answer
   - Changes made with each document
   - Source documents used
   - Metrics on refinement steps

Logs are stored in the `question_logs` and `refine_logs` directories within `BASE_DIR`.

## Troubleshooting

### Common Issues

1. **FAISS index not found**: Ensure INDEX_DIR points to a valid FAISS index directory

2. **Google Sheets API errors**: Verify credentials and permissions

3. **LLM connection errors**: Confirm your LLM server is running at the right address and port

4. **Empty answers**: Check the question log file to see the raw LLM response

5. **Document sources showing as "unknown"**: This is just a display issue related to metadata; the system is still using the correct documents

6. **"Missing some input keys" error**: Ensure your prompt templates don't reference missing variables

### Logging

Logs are written to both the console and a log file at `{BASE_DIR}/rag_processing.log`. Detailed question processing logs are stored in `{BASE_DIR}/question_logs/`.

## Example Outputs

The system generates comprehensive, well-structured answers with compliance ratings:

```
✅ Row 3 complete
Question: In your Order Managment OM module, do you support the concept of a Point of no return PONR?
Product Focus: Communications Cloud

Answer:
Yes, we support the concept of a Point of No Return (PONR) in our Order Management module within 
Communications Cloud. You can configure PONR at the order or item level, preventing further modifications 
once an order or item reaches a specific status. Once a PONR is reached, it cannot be reversed, even if 
the order or item is voided or canceled, ensuring a clear and irreversible point in the order lifecycle. 
The PONR feature is fully supported through standard configuration and can be set to trigger at various 
statuses like 'Completed', 'Running', 'Failed', or 'Fatally Failed'.

Compliance: FC

References (5):
• https://help.salesforce.com/s/articleView?id=ind.order_mgmt_order_config.htm&language=en_US&type=5
• https://help.salesforce.com/s/articleView?id=ind.comms_t_rules_for_how_point_of_no_returnponrpropagates_through_a_decompositionplan_234475.htm&language=en_US&type=5
```
