# LLMRAG: Retrieval-Augmented Generation Pipeline for Salesforce Documentation

LLMRAG is a modular Retrieval-Augmented Generation (RAG) system designed to automate the collection, processing, and querying of Salesforce and MuleSoft documentation, but it can easly used to crawl any other platform as long vaild and solid information is available on the web. 

The system enables high-quality, offline-ready markdown generation, vector-based search, and structured question answering with compliance ratings by using small, local ollama/llama.cpp based LLMs directly into a Google sheet. About local LLMs - my basics tests so far shown its an advantage if the LLM is capable to generate JSON output, there I have seen best results with llama.cpp "Instruct" models like

https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3 
or 
https://huggingface.co/starble-dev/Mistral-Nemo-12B-Instruct-2407-GGUF

Simple start them in server mode and let the scripts talk to them on localhost via HTTP. 

## Overview

The project consists of three main modules:

- **crawler/**: Multithreaded documentation crawler to collect and convert Salesforce and MuleSoft documentation into markdown format. 
- **rag/**: Document processor that builds vector embeddings (using Hugging Face models) and manages FAISS indices for semantic search. I have added a faiss vector DB with around 110k markdowns to the release. Its 7z format in 4 parts, you need to rename as git only allows certain extensions to upload. 
- **rfp/**: Question answering system integrated with Google Sheets for RFI/RFP workflows, including compliance scoring (FC, PC, NC, NA).

This architecture enables efficient retrieval-augmented generation workflows, ideal for answering complex questions about Salesforce capabilities with reliable grounding in product documentation.

## Features

- **Multithreaded crawling** and markdown conversion with YAML frontmatter
- **Vector embeddings** and FAISS-powered semantic search with GPU acceleration
- **Google Sheets integration** for structured Q&A workflows
- **Compliance scoring system** (Fully Compliant, Partially Compliant, Not Compliant, Not Applicable)
- **Dynamic embedding management** for efficient memory usage
- **Customer context support** for tailored responses
- **Reference validation** for ensuring high-quality citations
- **Detailed logging** for troubleshooting and analysis
- **Multiple LLM providers** (Ollama and llama.cpp)

## Requirements

- Python 3.8+
- Chrome browser (for Selenium-based web crawling and reference validation)
- FAISS index for vector search
- Ollama or llama.cpp LLM server
- Google API credentials (for rfp module)
- GPU recommended (but not required) for faster processing

## Installation

1. Clone the repository:
```bash
git clone https://github.com/jkoenig72/llmrag.git
cd llmrag
```

2. Install dependencies for each module:
```bash
cd crawler && pip install -r requirements.txt
cd ../rag && pip install -r requirements.txt
cd ../rfp && pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp env.template.sh env.sh
# Edit env.sh with your API keys, paths, and configuration
source env.sh
```

## Usage

Each module can be used independently or as part of a complete pipeline:

### 1. Run the Documentation Crawler

```bash
cd crawler
python main.py
```

This will:
- Create a directory structure for markdown outputs
- Crawl Salesforce documentation sites defined in `start_links.json`
- Generate markdown files with YAML frontmatter and tables of contents
- Produce summary logs with metrics

### 2. Build the FAISS Index for Vector Search

```bash
cd rag
python main.py --source /path/to/markdown/files --target /path/to/faiss/index
```

This will:
- Extract content and metadata from markdown files
- Split documents into chunks at markdown headers
- Generate vector embeddings using the specified model
- Create a FAISS index for efficient similarity search
- Skip already processed files using content hashing

### 3. Run the RFP Compliance Question Answering System

```bash
cd rfp
python main.py
```

This will:
- Connect to the specified Google Sheet
- Let you select product focus areas and customer context
- Process questions using the FAISS index
- Generate comprehensive answers with compliance ratings
- Validate and include reference URLs
- Write answers back to the Google Sheet

## Module Workflow

The complete workflow would typically be:

1. **Collect Documentation**: Use the crawler to fetch and convert documentation
2. **Build Vector Index**: Process the markdown files into a FAISS index
3. **Answer Questions**: Use the RFP module to answer specific questions

However, each module can be used independently. For example, you can use the RFP module with an existing FAISS index without running the crawler again.

## Configuration

Each module has its own configuration files:

- **crawler/config.py**: Settings for the crawler (depth, domains, products)
- **rag/config.py**: Settings for the RAG system (models, paths)
- **rfp/config.py**: Settings for the RFP system (Google Sheets, LLM, processing)

The main environment variables are defined in `env.template.sh` and can be customized in your own `env.sh` file.

## Compliance Scoring

The system assigns compliance levels to each answer:

- **FC**: Fully Compliant (out-of-the-box or standard configuration)
- **PC**: Partially Compliant (requires custom development)
- **NC**: Not Compliant (not possible even with customization)
- **NA**: Not Applicable (question is out of scope)

## Advanced Usage

### GPU Acceleration

For optimal performance with FAISS:

```bash
pip uninstall faiss-cpu
pip install faiss-gpu
```

The system will automatically detect GPU availability.

### Custom LLM Models

The system supports both Ollama and llama.cpp servers:

- **Ollama**: `ollama serve` and `ollama pull your-model`
- **llama.cpp**: `./llama-server --model /path/to/model.gguf --ctx-size 4096 --port 8080`

Configure the provider and model in the config file or environment variables.

### Customer-Specific Context

For tailored responses, add customer PDF/DOCX files:

1. Create a folder in the RFP_DOCUMENTS_DIR
2. Add relevant PDF or DOCX documents
3. Select the customer folder when running the RFP module

### Reference Validation

The system validates all extracted URLs before including them:

- Uses Selenium for comprehensive validation
- Detects 404 pages and other errors across Salesforce domains
- Limits references to the configured maximum (default: 2)

## Troubleshooting

- If the crawler fails to connect to Salesforce documentation sites, ensure your network connection is stable and not restricted.
- For GPU acceleration issues with FAISS, verify that you have installed faiss-gpu correctly and your system has compatible drivers.
- If experiencing rate limits with Google Sheets API, adjust the API_THROTTLE_DELAY in the configuration.
- For memory issues with large models, try enabling CPU mode for embeddings or reduce the number of documents retrieved.
- If reference validation fails, ensure Chrome is installed and WebDriver is accessible.

## Project Structure

```
llmrag/
├── crawler/           # Documentation crawler
│   ├── main.py        # Entry point for crawler
│   ├── crawler.py     # Core crawling logic
│   ├── config.py      # Crawler configuration
│   └── ...
├── rag/               # Vector embedding and RAG processing
│   ├── main.py        # Entry point for RAG system
│   ├── indexer.py     # FAISS index management
│   ├── config.py      # RAG configuration
│   └── ...
├── rfp/               # Compliance Q&A with Google Sheets integration
│   ├── main.py        # Entry point for RFP system
│   ├── question_processor.py # Core processing logic
│   ├── config.py      # RFP configuration
│   └── ...
├── .gitignore         # Git ignore file
└── env.template.sh    # Template for environment configuration
```

## Logs and Output

The system generates detailed logs for monitoring and debugging:

- **crawler/**: `RAG_Collection/scraper.log` and `summary.log`
- **rag/**: Processing logs with progress and time estimates
- **rfp/**: `{BASE_DIR}/rag_processing.log`, `refine_logs/` and `chain_logs/`

## License and Contributions

Maintained by Master Control Program. Contributions and feedback are welcome — please submit pull requests or open issues on GitHub.
