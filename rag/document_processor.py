"""
Document processing functionality for the RAG system.
Handles loading, parsing, and splitting markdown documents.
"""
import os
import re
import logging
import yaml
from uuid import uuid4
from collections import defaultdict
from typing import Dict, Tuple, List, Any

from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain.schema.document import Document

from utils import hash_file_content, load_processed_hashes, save_processed_hash


def extract_metadata_and_content(file_path: str) -> Tuple[Dict[str, Any], str, bool]:
    """Extract metadata and content from a markdown file with YAML frontmatter.
    
    Reads a markdown file, extracts the YAML frontmatter metadata and the main content.
    Also retrieves product information from the directory structure.
    
    Args:
        file_path: Path to the markdown file
        
    Returns:
        Tuple containing (
            metadata: Dictionary of metadata fields,
            content: String containing the markdown content,
            success_flag: Boolean indicating if extraction was successful
        )
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()
            
        match = re.match(r"(?s)^---\n(.*?)\n---\n(.*)$", raw)
        if not match:
            logging.warning(f"❌ Invalid markdown frontmatter: {file_path}")
            return {}, raw, False
            
        metadata_yaml, content = match.groups()
        try:
            metadata = yaml.safe_load(metadata_yaml)
            
            # Add product information based on directory and frontmatter
            product_name = os.path.basename(os.path.dirname(file_path)).replace("_", " ")
            
            # First, try to get product from frontmatter metadata
            if metadata.get('tag'):
                product_name = metadata.get('tag').replace("_", " ")
            elif metadata.get('category') and ":" in metadata.get('category'):
                # Extract product from category field if it's in format "X: Y"
                product_name = metadata.get('category').split(":", 1)[1].strip().replace("_", " ")
                
            # Store product info in standard metadata fields
            metadata["tag"] = metadata.get("tag", product_name)
            metadata["product"] = product_name  # Ensure product field always exists
            
            return metadata, content, True
        except yaml.YAMLError as e:
            logging.warning(f"❌ Invalid YAML in frontmatter: {file_path}")
            return {}, raw, False
            
    except Exception as e:
        logging.error(f"💥 Failed to read file {file_path}: {e}")
        return {}, "", False


def split_document_into_chunks(content: str, metadata: Dict[str, Any], splitter: MarkdownHeaderTextSplitter) -> List[Document]:
    """Split document content into chunks using the provided splitter.
    
    Divides a document into smaller chunks based on markdown headers,
    preserving metadata across all chunks.
    
    Args:
        content: The markdown content to split
        metadata: Metadata dictionary to associate with each chunk
        splitter: The MarkdownHeaderTextSplitter to use for chunking
        
    Returns:
        List of Document objects with appropriate metadata
    """
    # Make sure we're passing a string
    if not isinstance(content, str):
        logging.warning(f"⚠️ Content is not a string: {type(content)}")
        content = str(content)
    
    try:
        split_docs = splitter.split_text(content)
        
        # Check if we got any chunks
        if not split_docs:
            logging.warning(f"⚠️ No chunks generated for content")
            return []
        
        # Process the split documents
        document_chunks = []
        for i, doc_chunk in enumerate(split_docs):
            if isinstance(doc_chunk, Document):
                doc = Document(
                    page_content=doc_chunk.page_content,
                    metadata={**metadata, **doc_chunk.metadata, "chunk_uuid": str(uuid4()), "chunk_index": i}
                )
            else:
                doc = Document(
                    page_content=doc_chunk,
                    metadata={**metadata, "chunk_uuid": str(uuid4()), "chunk_index": i}
                )
            document_chunks.append(doc)
            
        return document_chunks
    except Exception as e:
        logging.error(f"💥 Error splitting document: {e}")
        return []