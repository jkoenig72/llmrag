"""
Vector indexing functionality for the RAG system.
Handles creating and updating FAISS indices with document embeddings.
"""
import os
import logging
import time
from collections import defaultdict
from typing import Tuple, Dict, Optional, Set
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema.document import Document
from langchain.text_splitter import MarkdownHeaderTextSplitter

import config
import utils
import document_processor


def initialize_or_load_index(index_dir: str) -> Optional[FAISS]:
    """Initialize a new FAISS index or load an existing one."""
    embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
    
    if os.path.exists(index_dir):
        try:
            index = FAISS.load_local(index_dir, embeddings, allow_dangerous_deserialization=True)
            logging.info("✅ Loaded existing FAISS index.")
            return index
        except Exception as e:
            logging.error(f"❌ Failed to load existing index: {e}")
            return None
    else:
        logging.info("🚧 No existing index. Will create a new one on first document.")
        return None


def process_markdown_files_individually(source_dir: str, index_dir: str) -> Tuple[int, int, Dict]:
    """
    Process markdown files individually, adding them to the FAISS index.
    
    Returns:
        Tuple containing (number of new files indexed, number of files skipped, summary of skips and errors)
    """
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "Header")])
    index = initialize_or_load_index(index_dir)

    processed_hashes = utils.load_processed_hashes()
    
    # Count total files and set up progress tracking
    product_counts = utils.count_files_by_product(source_dir)
    total_files = product_counts["Total"]
    processed_count_by_product = {k: 0 for k in product_counts.keys()}
    
    # Track skipped files and reasons
    skip_tracking = defaultdict(list)
    error_tracking = defaultdict(list)
    
    total_new = 0
    total_skipped = 0
    start_time = time.time()
    
    for root, _, files in os.walk(source_dir):
        files = [f for f in files if f.endswith(".md")]
        product_name = os.path.basename(root).replace("_", " ")
        
        for file_idx, file in enumerate(files):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read()
                content_hash = utils.hash_file_content(raw)
                
                # Track processed even if skipped for accurate progress
                processed_count_by_product[product_name] = processed_count_by_product.get(product_name, 0) + 1
                processed_count_by_product["Total"] = processed_count_by_product.get("Total", 0) + 1
                
                if content_hash in processed_hashes:
                    total_skipped += 1
                    skip_tracking["already_indexed"].append(path)
                    
                    # Show progress even for skipped files
                    elapsed_time = time.time() - start_time
                    time_estimate = utils.estimate_completion_time(
                        processed_count_by_product["Total"], 
                        product_counts["Total"], 
                        elapsed_time
                    )
                    
                    if file_idx % 10 == 0 or file_idx == len(files) - 1:  # Update every 10 files or on the last file
                        logging.info(f"⏭️ Skipped {file} [{processed_count_by_product[product_name]}/{product_counts[product_name]} for {product_name}, "
                                    f"{processed_count_by_product['Total']}/{product_counts['Total']} overall] - ETA: {time_estimate}")
                    continue

                # Extract metadata and content
                metadata, content, success = document_processor.extract_metadata_and_content(path)
                if not success:
                    skip_tracking["invalid_frontmatter"].append(path)
                    continue
                
                # Split the document into chunks
                split_docs = document_processor.split_document_into_chunks(content, metadata, splitter)
                if not split_docs:
                    skip_tracking["no_chunks"].append(path)
                    continue
                
                # Add to or create index
                try:
                    if index:
                        index.add_documents(split_docs)
                    else:
                        embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
                        index = FAISS.from_documents(split_docs, embeddings)
                    
                    # Save index and track the processed file
                    index.save_local(index_dir)
                    utils.save_processed_hash(content_hash)
                    total_new += 1
                    
                    # Calculate progress and time estimate
                    elapsed_time = time.time() - start_time
                    time_estimate = utils.estimate_completion_time(
                        processed_count_by_product["Total"], 
                        product_counts["Total"], 
                        elapsed_time
                    )
                    
                    logging.info(f"✅ Indexed {file} with {len(split_docs)} chunks "
                                f"[{processed_count_by_product[product_name]}/{product_counts[product_name]} for {product_name}, "
                                f"{processed_count_by_product['Total']}/{product_counts['Total']} overall] - ETA: {time_estimate}")
                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"💥 Error adding document to index: {e}")
                    error_tracking[error_msg[:50] + "..."].append(path)
                    
            except Exception as e:
                error_msg = str(e)
                logging.error(f"💥 Failed to process {path}: {e}")
                error_tracking[error_msg[:50] + "..."].append(path)

    # Final timing stats
    total_time = time.time() - start_time
    minutes, seconds = divmod(int(total_time), 60)
    logging.info(f"⏱️ Total processing time: {minutes} minutes and {seconds} seconds")
    
    # Combine all skipping info
    skip_summary = {
        "skip_reasons": skip_tracking,
        "error_reasons": error_tracking
    }
    
    return total_new, total_skipped, skip_summary