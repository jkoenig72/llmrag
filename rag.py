import os
import logging
import re
import argparse
import hashlib
import time
from uuid import uuid4
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import FAISS
from langchain.schema.document import Document
from typing import List, Tuple, Dict
from markdownify import markdownify as md_convert
import yaml
from collections import defaultdict

# Configuration defaults
DEFAULT_BASE_DIR = "RAG"
DEFAULT_INDEX_DIR = "faiss_index"
EMBEDDING_MODEL = "intfloat/e5-large-v2"
LLM_MODEL = "gemma3:12b"
OLLAMA_URL = "http://localhost:11434"
PROCESSED_HASHES_TRACKER = "processed_hashes.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def hash_file_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def load_processed_hashes() -> set:
    if os.path.exists(PROCESSED_HASHES_TRACKER):
        with open(PROCESSED_HASHES_TRACKER, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_hash(hash_value: str):
    with open(PROCESSED_HASHES_TRACKER, "a") as f:
        f.write(hash_value + "\n")

def count_files_by_product(source_dir: str) -> Dict[str, int]:
    """Count the total number of markdown files by product directory."""
    product_counts = {}
    total_files = 0
    
    for root, _, files in os.walk(source_dir):
        md_files = [f for f in files if f.endswith(".md")]
        if md_files:
            product_name = os.path.basename(root).replace("_", " ")
            product_counts[product_name] = len(md_files)
            total_files += len(md_files)
    
    product_counts["Total"] = total_files
    return product_counts

def estimate_completion_time(files_processed: int, total_files: int, elapsed_time: float) -> str:
    """Estimate the time remaining to complete processing."""
    if files_processed == 0:
        return "Unknown"
    
    # Calculate processing rate (files per second)
    rate = files_processed / elapsed_time
    
    # Estimate time remaining in seconds
    remaining_files = total_files - files_processed
    remaining_time = remaining_files / rate if rate > 0 else 0
    
    # Convert to human-readable format
    if remaining_time < 60:
        return f"{int(remaining_time)} seconds"
    elif remaining_time < 3600:
        return f"{int(remaining_time / 60)} minutes"
    else:
        hours = int(remaining_time / 3600)
        minutes = int((remaining_time % 3600) / 60)
        return f"{hours} hours, {minutes} minutes"

def process_markdown_files_individually(source_dir: str, index_dir: str) -> Tuple[int, int, Dict]:
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "Header")])
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    if os.path.exists(index_dir):
        index = FAISS.load_local(index_dir, embeddings, allow_dangerous_deserialization=True)
        logging.info("✅ Loaded existing FAISS index.")
    else:
        index = None
        logging.info("🚧 No existing index. Will create a new one on first document.")

    processed_hashes = load_processed_hashes()
    
    # Count total files and set up progress tracking
    product_counts = count_files_by_product(source_dir)
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
                content_hash = hash_file_content(raw)
                
                # Track processed even if skipped for accurate progress
                processed_count_by_product[product_name] = processed_count_by_product.get(product_name, 0) + 1
                processed_count_by_product["Total"] = processed_count_by_product.get("Total", 0) + 1
                
                if content_hash in processed_hashes:
                    total_skipped += 1
                    skip_tracking["already_indexed"].append(path)
                    
                    # Show progress even for skipped files
                    elapsed_time = time.time() - start_time
                    time_estimate = estimate_completion_time(
                        processed_count_by_product["Total"], 
                        product_counts["Total"], 
                        elapsed_time
                    )
                    
                    if file_idx % 10 == 0 or file_idx == len(files) - 1:  # Update every 10 files or on the last file
                        logging.info(f"⏭️ Skipped {file} [{processed_count_by_product[product_name]}/{product_counts[product_name]} for {product_name}, "
                                    f"{processed_count_by_product['Total']}/{product_counts['Total']} overall] - ETA: {time_estimate}")
                    continue

                match = re.match(r"(?s)^---\n(.*?)\n---\n(.*)$", raw)
                if not match:
                    logging.warning(f"❌ Invalid markdown frontmatter: {path}")
                    skip_tracking["invalid_frontmatter"].append(path)
                    continue

                metadata_yaml, content = match.groups()
                try:
                    metadata = yaml.safe_load(metadata_yaml)
                except yaml.YAMLError as e:
                    logging.warning(f"❌ Invalid YAML in frontmatter: {path}")
                    skip_tracking["invalid_yaml"].append(path)
                    continue
                    
                metadata["tag"] = metadata.get("tag", product_name)
                metadata["product"] = metadata.get("product", product_name)

                raw_doc = Document(page_content=content, metadata=metadata)
                
                try:
                    # Make sure we're passing a string
                    content_to_split = raw_doc.page_content
                    if not isinstance(content_to_split, str):
                        logging.warning(f"⚠️ Content is not a string: {type(content_to_split)}")
                        content_to_split = str(content_to_split)
                    
                    split_docs = splitter.split_text(content_to_split)
                    
                    # Check if we got any chunks
                    if not split_docs:
                        logging.warning(f"⚠️ No chunks generated for: {path}")
                        skip_tracking["no_chunks"].append(path)
                        continue
                    
                    # Process the split documents
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
                        
                        if index:
                            index.add_documents([doc])
                        else:
                            index = FAISS.from_documents([doc], embeddings)
                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"💥 Error splitting document {file}: {e}")
                    error_tracking[error_msg[:50] + "..."].append(path)
                    continue

                index.save_local(index_dir)
                save_processed_hash(content_hash)
                total_new += 1
                
                # Calculate progress and time estimate
                elapsed_time = time.time() - start_time
                time_estimate = estimate_completion_time(
                    processed_count_by_product["Total"], 
                    product_counts["Total"], 
                    elapsed_time
                )
                
                logging.info(f"✅ Indexed {file} with {len(split_docs)} chunks "
                            f"[{processed_count_by_product[product_name]}/{product_counts[product_name]} for {product_name}, "
                            f"{processed_count_by_product['Total']}/{product_counts['Total']} overall] - ETA: {time_estimate}")

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

def test_query(index_dir: str):
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    index_faiss = os.path.join(index_dir, "index.faiss")
    index_pkl = os.path.join(index_dir, "index.pkl")
    if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
        raise FileNotFoundError("FAISS index files not found. Build the index first.")

    vectorstore = FAISS.load_local(index_dir, embeddings, allow_dangerous_deserialization=True)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    llm = OllamaLLM(model=LLM_MODEL, base_url=OLLAMA_URL)

    question = "How does Salesforce Communications Cloud handle product bundling?"
    docs = retriever.get_relevant_documents(question)
    context = "\n---\n".join([doc.page_content for doc in docs])

    prompt = f"""
You are a Senior Solution Engineer at Salesforce. Answer the following question using only the context provided.

Context:
{context}

Question:
{question}

Answer:
"""

    response = llm.invoke(prompt)
    print("\n" + "=" * 40)
    print(f"Question: {question}")
    print(f"Answer: {response}")
    print("=" * 40)

def print_skip_summary(skip_summary: Dict):
    """Print a detailed summary of skipped files and errors."""
    print("\n📝 Skip and Error Summary:")
    
    # Print skip reasons
    skip_reasons = skip_summary["skip_reasons"]
    if skip_reasons:
        print("\n🔄 Files skipped by reason:")
        for reason, files in skip_reasons.items():
            print(f"  - {reason}: {len(files)} files")
            # Print up to 3 examples
            if len(files) > 0:
                for i, file in enumerate(files[:3]):
                    print(f"    • {os.path.basename(file)}")
                if len(files) > 3:
                    print(f"    • ...and {len(files) - 3} more")
    
    # Print error reasons
    error_reasons = skip_summary["error_reasons"]
    if error_reasons:
        print("\n⚠️ Files with errors by reason:")
        for reason, files in error_reasons.items():
            print(f"  - Error: {reason}")
            print(f"    Count: {len(files)} files")
            # Print up to 3 examples
            if len(files) > 0:
                for i, file in enumerate(files[:3]):
                    print(f"    • {os.path.basename(file)}")
                if len(files) > 3:
                    print(f"    • ...and {len(files) - 3} more")

def main():
    print("🧠 Starting FAISS indexing pipeline...")
    parser = argparse.ArgumentParser(description="Safely build a FAISS index from Markdown files, one by one.")
    parser.add_argument("--source", required=True, help="Path to markdown documents")
    parser.add_argument("--target", required=True, help="Path to store the FAISS index")
    parser.add_argument("--test-query", action="store_true", help="Run a test query after indexing")
    args = parser.parse_args()

    print(f"📂 Source folder: {args.source}")
    print(f"💾 Target FAISS index: {args.target}")

    # Count files before processing
    product_counts = count_files_by_product(args.source)
    print("\n📊 Found files to process:")
    for product, count in product_counts.items():
        if product != "Total":
            print(f"  - {product}: {count} files")
    print(f"  Total: {product_counts['Total']} files\n")

    added, skipped, skip_summary = process_markdown_files_individually(args.source, args.target)

    print("\n📊 Indexing summary:")
    print(f"🆕 {added} files newly indexed")
    print(f"⏭️ {skipped} files skipped")
    
    # Print detailed skip summary
    print_skip_summary(skip_summary)

    if args.test_query:
        test_query(args.target)

if __name__ == "__main__":
    main()