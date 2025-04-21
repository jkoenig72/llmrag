"""
Configuration settings for the RAG system.
Contains default values and constants used across the application.
"""
import os

# Directory configuration
DEFAULT_BASE_DIR = "RAG"
DEFAULT_INDEX_DIR = "faiss_index_v1"

# Model configuration
EMBEDDING_MODEL = "intfloat/e5-large-v2"
LLM_MODEL = "gemma3:12b"
OLLAMA_URL = "http://localhost:11434"

# File tracking
PROCESSED_HASHES_TRACKER = "processed_hashes_v2.log"

# Logging format
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

