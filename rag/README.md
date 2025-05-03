# RAG System

A Retrieval-Augmented Generation (RAG) system for processing and querying Markdown documents with YAML frontmatter.

## Overview

This system processes Markdown files, extracts content and metadata, splits documents into chunks, and creates vector embeddings stored in a FAISS index. The index can then be queried to retrieve relevant document chunks for generating responses using an Ollama or llama.cpp LLM.

## Features

- **Incremental Processing**: Only processes new or changed files using content hashing
- **Progress Tracking**: Provides detailed progress information with time estimates
- **Error Handling**: Tracks and summarizes skipped files and processing errors
- **Document Splitting**: Splits documents at markdown headers for better context handling
- **Vector Embedding**: Uses HuggingFace embeddings for semantic search
- **Comprehensive Testing**: Tests queries with three modes - raw LLM, grounded LLM, and RAG
- **GPU Acceleration**: Automatically detects and utilizes GPU for faster processing
- **Compliance Categorization**: Classifies responses as Fully Compliant (FC), Partially Compliant (PC), Not Compliant (NC), or Not Applicable (NA)
- **Response Parsing**: Ensures responses follow the expected JSON format

## Requirements

- Python 3.8+
- Dependencies (install via `pip install -r requirements.txt`)
- Ollama server or llama.cpp server (for LLM access)
- FAISS index (or source markdown files to build one)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/jkoenig72/llmrag.git
cd llmrag/rag
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install Ollama and run it locally (required for LLM):
```bash
# Visit https://ollama.com/download for installation instructions
ollama serve  # Start the Ollama server
ollama pull gemma3:12b  # Pull the default model
```

Alternatively, you can use llama.cpp server:
```bash
./llama-server --model /path/to/your/model.gguf --n-gpu-layers 35 --ctx-size 4096 --port 8080
```

## Configuration

Key settings can be adjusted in `config.py`:

- `EMBEDDING_MODEL`: Model to use for embeddings (default: "intfloat/e5-large-v2")
- `LLM_MODEL`: Model to use for LLM responses (default: "gemma3:12b")
- `OLLAMA_URL`: URL for the Ollama server (default: "http://localhost:11434")
- `DEFAULT_BASE_DIR`: Base directory for data storage (default: "RAGV6")
- `DEFAULT_INDEX_DIR`: Directory for FAISS index (default: "faiss_index")

## Usage

### Building the Index

```bash
python main.py --source /path/to/markdown/files --target /path/to/faiss/index
```

Command line options:
- `--source`: Path to directory containing markdown documents
- `--target`: Path to store/load the FAISS index
- `--skip-indexing`: Skip index building and just run queries

### Testing with Query Comparison

Run a comprehensive test that compares three different query modes:
1. Raw LLM (no grounding, no RAG)
2. Grounded LLM (with grounding, no RAG)
3. RAG-enhanced LLM (with grounding and document context)

```bash
python main.py --target /path/to/faiss/index --skip-indexing --test-query --question "Your question here"
```

Command line options:
- `--question`: Custom question for test query
- `--test-query`: Run test queries comparing raw LLM, grounded LLM, and RAG

### Getting Information About an Index

```bash
python main.py --target /path/to/faiss/index --info
```

Command line options:
- `--info`: Show information about the FAISS index (vectors, dimensions, product distribution, etc.)

## Full Command Line Reference

```
python main.py [OPTIONS]

Options:
  --source TEXT           Path to markdown documents
  --target TEXT           Path to store/load the FAISS index (required)
  --test-query            Run test queries comparing raw LLM, grounded LLM, and RAG
  --question TEXT         Custom question for test query (used with --test-query)
  --skip-indexing         Skip index building and just run queries
  --info                  Show information about the FAISS index
```

## Project Structure

- **main.py**: Main script and entry point
- **config.py**: Configuration settings and constants
- **utils.py**: Utility functions for file handling, hashing, and progress tracking
- **document_processor.py**: Document loading, parsing, and splitting functionality
- **indexer.py**: Vector embedding and FAISS index management
- **rag_query.py**: Query functionality for testing the RAG system
- **response_parser.py**: Ensures responses follow the expected JSON format

## Response Format

The RAG system generates responses in JSON format with the following structure:

```json
{
  "compliance": "FC|PC|NC|NA",
  "answer": "Detailed explanation about the Salesforce capability",
  "references": ["URL1", "URL2"]
}
```

Where:
- `compliance` is one of:
  - `FC` (Fully Compliant): Available through standard configuration
  - `PC` (Partially Compliant): Requires custom development
  - `NC` (Not Compliant): Not possible in Salesforce
  - `NA` (Not Applicable): Out of scope
- `answer` contains a detailed explanation
- `references` lists relevant URLs from the documentation

## Example Output

When running a comprehensive test query:

```bash
python main.py --target ./faiss_index --skip-indexing --test-query --question "Describe the Order Management functionality in your solution."
```

Output:
```
🧠 Starting RAG system...
💾 FAISS index location: ./faiss_index
⏭️ Skipping indexing phase as requested...

🔍 Running comprehensive test query with all three modes:
  1. Raw LLM (no grounding, no RAG)
  2. Grounded LLM (with grounding, no RAG)
  3. RAG-enhanced LLM (with grounding and document context)

📝 Querying LLM with no grounding or RAG (raw query)

========================================
Question: Describe the Order Management functionality in your solution.
Raw LLM Answer (NO GROUNDING, NO RAG): Salesforce Order Management provides a comprehensive solution for managing the entire order lifecycle, from capture to fulfillment. It allows businesses to create a unified commerce experience across channels by centralizing order processing.

Key capabilities include:
[...]
========================================

📝 Querying LLM with grounding but without RAG (no context provided)

========================================
Question: Describe the Order Management functionality in your solution.
Grounded LLM Answer (NO RAG): {
  "compliance": "FC",
  "answer": "Salesforce Order Management provides a comprehensive solution for the entire order lifecycle. It enables businesses to capture, process, fulfill, and service orders across all channels in a unified system.[...]"
}
========================================

📝 Running RAG-enhanced query (with grounding and document context)
🚀 Using GPU acceleration for vector search (GPUs: 2)

========================================
Question: Describe the Order Management functionality in your solution.
RAG-Enhanced Answer: {
  "compliance": "FC",
  "answer": "Salesforce Order Management is a robust solution that enables businesses to manage their order fulfillment processes end-to-end.[...]"
}
========================================
```

## Performance Optimization

For optimal performance with large indices, it's highly recommended to use the GPU-accelerated version of FAISS:

```bash
pip uninstall faiss-cpu
pip install faiss-gpu
```

The system will automatically detect if a GPU is available and display recommendations accordingly.

## Troubleshooting

- **Memory Issues**: For large indices, ensure your system has adequate RAM or use a machine with GPU
- **Model Loading Errors**: Verify that Ollama or llama.cpp server is running and the specified model is available
- **Slow Performance**: Check GPU detection, consider installing faiss-gpu
- **File Processing Errors**: Verify markdown files have valid YAML frontmatter
- **Index Loading Errors**: Ensure the index path is correct and the index files are not corrupted

## Common Issues and Solutions

1. **"FAISS index files not found"**
   - Ensure you've built the index first or specify the correct path

2. **"No GPU detected for FAISS"**
   - Install CUDA and faiss-gpu for better performance

3. **"Failed to load existing index"**
   - The index may be corrupted; rebuild it from source files

4. **"Error connecting to Ollama server"**
   - Verify Ollama is running and accessible at the configured URL

5. **"Invalid YAML frontmatter"**
   - Check that source markdown files have proper frontmatter format

**License and Contributions**

Maintained by Master Control Program. Contributions and feedback are welcome — please submit pull requests or open issues on GitHub.