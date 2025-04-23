"""
Configuration settings for the RAG system.

This module contains default values and constants used across the RAG application.
It centralizes configuration to make it easier to adjust system-wide settings.
"""
import os

# Directory configuration
DEFAULT_BASE_DIR = "RAG"
DEFAULT_INDEX_DIR = "faiss_index"

# Model configuration
EMBEDDING_MODEL = "intfloat/e5-large-v2"
LLM_MODEL = "gemma3:12b"
OLLAMA_URL = "http://localhost:11434"

# File tracking
PROCESSED_HASHES_TRACKER = "processed_hashes.txt"

# Logging format
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"