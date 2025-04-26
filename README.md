
# LLMRAG: Retrieval-Augmented Generation Pipeline for Salesforce Documentation

LLMRAG is a modular Retrieval-Augmented Generation (RAG) system designed to automate the collection, processing, and querying of Salesforce and MuleSoft documentation. The system enables high-quality, offline-ready markdown generation, vector-based search, and structured question answering with compliance ratings.

## Overview

The project consists of three main modules:

- crawler/: Multithreaded documentation crawler to collect and convert Salesforce and MuleSoft documentation into markdown format.
- rag/: Document processor that builds vector embeddings (using Hugging Face models) and manages FAISS indices for semantic search.
- rfp/: Question answering system integrated with Google Sheets for RFI/RFP workflows, including compliance scoring (FC, PC, NC, NA).

This architecture enables efficient retrieval-augmented generation workflows, ideal for answering complex questions about Salesforce capabilities with reliable grounding in product documentation.

## Features

- Multithreaded crawling and markdown conversion with YAML frontmatter.
- Vector embeddings and FAISS-powered semantic search.
- Google Sheets integration for structured Q&A workflows.
- Compliance scoring system (Fully Compliant, Partially Compliant, Not Compliant, Not Applicable).
- GPU acceleration support for faster processing.
- Batch processing and retry logic for robust automation.

The current faiss index vector db is build with infos from help.salesforce and trailhead around those products

Sales_Cloud
Service_Cloud
Agentforce
Platform
Communications_Cloud
Experience_Cloud
Data_Cloud
Marketing_Cloud
MuleSoft

(llms-env) fritz@ai2:~/llms-env/llmrag/rag$ python main.py --target /home/fritz/FAISSIndexV5 --info

✅ FAISS with GPU support detected! (1 GPU available)
    Using FAISS version: 1.10.0

🧠 Starting RAG system...
💾 FAISS index location: /home/fritz/FAISSIndexV5
usage: main.py [-h] [--source SOURCE] --target TARGET [--test-query] [--question QUESTION] [--skip-indexing] [--info]
main.py: error: --source is required when not using --skip-indexing
(llms-env) fritz@ai2:~/llms-env/llmrag/rag$ python main.py --target /home/fritz/FAISSIndexV5 --skip-indexing --info

✅ FAISS with GPU support detected! (1 GPU available)
    Using FAISS version: 1.10.0

🧠 Starting RAG system...
💾 FAISS index location: /home/fritz/FAISSIndexV5
⏭️ Skipping indexing phase as requested...

📊 FAISS Index Information:
DEBUG: Metadata type: <class 'tuple'>
DEBUG: Metadata tuple length: 2
DEBUG: Successfully extracted product distribution with 9 products
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

## Architecture Diagrams

Architecture and sequence diagrams are available in the images/ folder:

- crawler_f.png, crawler_s.png
- rag_f.png, rag_s.png
- rfp_f.png, rfp_s.png

## Compliance Scoring

The system assigns compliance levels to each answer:

- FC: Fully Compliant (out-of-the-box or standard config)
- PC: Partially Compliant (requires custom development)
- NC: Not Compliant (not possible even with customization)
- NA: Not Applicable (question is out of scope)

## License and Contributions

Maintained by Master Control Program. Contributions and feedback are welcome — please submit pull requests or open issues on GitHub.
