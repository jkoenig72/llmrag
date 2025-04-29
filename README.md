# LLMRAG: Retrieval-Augmented Generation Pipeline for Salesforce Documentation

LLMRAG is a modular Retrieval-Augmented Generation (RAG) system designed to automate the collection, processing, and querying of Salesforce and MuleSoft documentation, but it can easly used to crawl any other platform as long vaild and solid information is available on the web. 

The system enables high-quality, offline-ready markdown generation, vector-based search, and structured question answering with compliance ratings by using small, local ollama based LLMs directly into a Google sheet.

## Overview

The project consists of three main modules:

- **crawler/**: Multithreaded documentation crawler to collect and convert Salesforce and MuleSoft documentation into markdown format.
- **rag/**: Document processor that builds vector embeddings (using Hugging Face models) and manages FAISS indices for semantic search.
- **rfp/**: Question answering system integrated with Google Sheets for RFI/RFP workflows, including compliance scoring (FC, PC, NC, NA).

This architecture enables efficient retrieval-augmented generation workflows, ideal for answering complex questions about Salesforce capabilities with reliable grounding in product documentation.

## Features

- **Multithreaded crawling** and markdown conversion with YAML frontmatter
- **Vector embeddings** and FAISS-powered semantic search
- **Google Sheets integration** for structured Q&A workflows
- **Compliance scoring system** (Fully Compliant, Partially Compliant, Not Compliant, Not Applicable)
- **GPU acceleration** support for faster processing
- **Batch processing** and retry logic for robust automation

## Architecture Diagrams

Architecture and sequence diagrams are available in the images/ folder:

- crawler_f.png, crawler_s.png (Crawler module flow and sequence diagrams)
- rag_f.png, rag_s.png (RAG module flow and sequence diagrams)
- rfp_f.png, rfp_s.png (RFP module flow and sequence diagrams)

## Current Vector Database Coverage

The current FAISS index vector database is built with information from help.salesforce and trailhead around these products:

- Sales Cloud
- ServiceCloud
- Agentforce
- Platform
- Communications Cloud
- Experience Cloud
- Data Cloud
- Marketing Cloud
- MuleSoft

Total vectors: 112,188  
Vector dimension: 1024  
Index type: Flat  
Index size: 550.05 MB  
GPU usage: Available and detected

Product distribution:
  - Platform: 18,976 vectors
  - Sales Cloud: 17,528 vectors
  - Marketing Cloud: 14,760 vectors
  - Agentforce: 14,400 vectors
  - Communications Cloud: 13,709 vectors
  - Data Cloud: 13,256 vectors
  - Service Cloud: 12,638 vectors
  - Experience Cloud: 3,978 vectors
  - MuleSoft: 2,943 vectors

### !!! A built index is not part of this repo. Build one yourself or ping me. !!! 

## Requirements

- Python 3.8+
- Chrome browser (for Selenium in crawler module)
- FAISS index for vector search
- Ollama LLM server (for local large language model inference)
- Google API credentials (for rfp module)

## Installation

1. Clone the repository:
```
git clone https://github.com/jkoenig72/llmrag.git
```

2. Install dependencies in each module:
```
cd crawler && pip install -r requirements.txt
cd ../rag && pip install -r requirements.txt
cd ../rfp && pip install -r requirements.txt
```

3. Set up environment variables:
```
cp env.template.sh env.sh
nano env.sh  # Add your API keys, paths, and configuration
```

## Usage

Run the Documentation Crawler:
```
cd crawler
python main.py
```

Build the FAISS Index for Vector Search:
```
cd rag
python main.py --source /path/to/markdown/files --target /path/to/faiss/index
```

Run the RFP Compliance Question Answering System:
```
cd rfp
python main.py
```

## Project Structure

```
llmrag/
├── crawler/           # Documentation crawler
├── rag/               # Vector embedding and RAG processing
├── rfp/               # Compliance Q&A with Google Sheets integration
├── images/            # Architecture diagrams
├── .gitignore         # Ignore list, including env.sh
├── env.template.sh    # Example environment configuration (copy to env.sh)
└── README.md          # Project overview (this file)
```

## Compliance Scoring

The system assigns compliance levels to each answer:

- **FC**: Fully Compliant (out-of-the-box or standard config)
- **PC**: Partially Compliant (requires custom development)
- **NC**: Not Compliant (not possible even with customization)
- **NA**: Not Applicable (question is out of scope)

## Troubleshooting

- If the crawler fails to connect to Salesforce documentation sites, ensure your network connection is stable and not restricted.
- For GPU acceleration issues with FAISS, verify that you have installed faiss-gpu correctly and your system has compatible drivers.
- If experiencing rate limits with Google Sheets API, adjust the API_THROTTLE_DELAY in the configuration.

**License and Contributions**

Maintained by Master Control Program. Contributions and feedback are welcome — please submit pull requests or open issues on GitHub.
