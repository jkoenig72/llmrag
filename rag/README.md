## Performance Optimization

For optimal performance with large indices, it's highly recommended to use the GPU-accelerated version of FAISS:

```bash
pip uninstall faiss-cpu
pip install faiss-gpu
```

The system will automatically detect if a GPU is available and display recommendations accordingly.# RAG System

A Retrieval-Augmented Generation (RAG) system for processing and querying Markdown documents with YAML frontmatter.

## Overview

This system processes Markdown files, extracts content and metadata, splits documents into chunks, and creates vector embeddings stored in a FAISS index. The index can then be queried to retrieve relevant document chunks for generating responses using an Ollama LLM.

## Files Structure

- **main.py**: Main script and entry point
- **config.py**: Configuration settings and constants
- **utils.py**: Utility functions for file handling, hashing, and progress tracking
- **document_processor.py**: Document loading, parsing, and splitting functionality
- **indexer.py**: Vector embedding and FAISS index management
- **rag_query.py**: Query functionality for testing the RAG system

## Requirements

- Python 3.8+
- Dependencies (install via `pip install -r requirements.txt`):
  - langchain
  - langchain_huggingface
  - langchain_ollama
  - langchain_community
  - beautifulsoup4
  - markdownify
  - pyyaml
  - faiss-cpu (or faiss-gpu for GPU acceleration)

## Usage

### Building the Index

```bash
python main.py --source /path/to/markdown/files --target /path/to/faiss/index
```

### Building the Index and Testing with a Query

```bash
python main.py --source /path/to/markdown/files --target /path/to/faiss/index --test-query
```

### Running with a Custom Query

```bash
python main.py --source /path/to/markdown/files --target /path/to/faiss/index --test-query --question "Your custom question here"
```

### Using an Existing Index (Skip Indexing)

```bash
python main.py --target /path/to/faiss/index --skip-indexing --test-query --question "Your question here"
```

### Getting Information About an Index

```bash
python main.py --target /path/to/faiss/index --info
```

### Direct LLM Query (No RAG)

```bash
python main.py --direct-llm --question "Your question here"
```

### Comparing RAG vs Direct LLM

```bash
python main.py --target /path/to/faiss/index --skip-indexing --test-query --direct-llm --question "Your question here"
```

## Features

- **Incremental Processing**: Only processes new or changed files using content hashing
- **Progress Tracking**: Provides detailed progress information with time estimates
- **Error Handling**: Tracks and summarizes skipped files and processing errors
- **Document Splitting**: Splits documents at markdown headers for better context handling
- **Vector Embedding**: Uses HuggingFace embeddings for semantic search
- **RAG Query**: Tests the system with sample or custom queries