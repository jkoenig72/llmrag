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
            
            # Extract product information from multiple sources
            product_info = {
                'directory': os.path.basename(os.path.dirname(file_path)).replace("_", " "),
                'frontmatter_tag': metadata.get('tag', ''),
                'frontmatter_category': metadata.get('category', ''),
                'frontmatter_product': metadata.get('product', '')
            }
            
            # Determine the primary product
            primary_product = None
            
            # Priority 1: Explicit product field
            if product_info['frontmatter_product']:
                primary_product = product_info['frontmatter_product']
            # Priority 2: Tag field
            elif product_info['frontmatter_tag']:
                primary_product = product_info['frontmatter_tag']
            # Priority 3: Category field (if it contains a product)
            elif product_info['frontmatter_category'] and ":" in product_info['frontmatter_category']:
                primary_product = product_info['frontmatter_category'].split(":", 1)[1].strip()
            # Priority 4: Directory name
            else:
                primary_product = product_info['directory']
                
            # Normalize product name
            primary_product = primary_product.replace("_", " ").strip()
            
            # Store all product information in metadata
            metadata.update({
                "product": primary_product,
                "product_info": product_info,
                "product_source": "frontmatter" if product_info['frontmatter_product'] else 
                                "tag" if product_info['frontmatter_tag'] else
                                "category" if product_info['frontmatter_category'] else
                                "directory"
            })
            
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