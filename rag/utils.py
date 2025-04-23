"""
Utility functions for the RAG system.
Contains helper functions for file operations, text processing, and progress tracking.
"""
import os
import re
import hashlib
import time
from collections import defaultdict
from typing import Dict, Set

import config


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug format.
    
    Args:
        text: The input text to convert to a slug
        
    Returns:
        A lowercase string with non-alphanumeric characters replaced by hyphens
    """
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def hash_file_content(content: str) -> str:
    """Generate a SHA-256 hash for the given content.
    
    Args:
        content: The text content to hash
        
    Returns:
        A hexadecimal string representation of the SHA-256 hash
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_processed_hashes() -> Set[str]:
    """Load the set of already processed file hashes.
    
    Reads the hash tracker file to determine which files have already
    been processed and indexed.
    
    Returns:
        A set of hash strings for previously processed files
    """
    if os.path.exists(config.PROCESSED_HASHES_TRACKER):
        with open(config.PROCESSED_HASHES_TRACKER, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_processed_hash(hash_value: str) -> None:
    """Save a processed file hash to the tracker.
    
    Args:
        hash_value: The hash value to add to the tracker file
    """
    with open(config.PROCESSED_HASHES_TRACKER, "a") as f:
        f.write(hash_value + "\n")


def count_files_by_product(source_dir: str) -> Dict[str, int]:
    """Count the total number of markdown files by product directory.
    
    Walks through the source directory structure and counts markdown
    files in each product subdirectory.
    
    Args:
        source_dir: Root directory containing product subdirectories with markdown files
        
    Returns:
        A dictionary mapping product names to file counts, with a "Total" key for the overall count
    """
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
    """Estimate the time remaining to complete processing.
    
    Calculates an estimated completion time based on the current processing rate.
    
    Args:
        files_processed: Number of files processed so far
        total_files: Total number of files to process
        elapsed_time: Time elapsed in seconds
        
    Returns:
        A human-readable string describing the estimated remaining time
    """
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


def print_skip_summary(skip_summary: Dict) -> None:
    """Print a detailed summary of skipped files and errors.
    
    Generates a formatted report of files that were skipped during processing
    and the reasons for skipping them.
    
    Args:
        skip_summary: A dictionary containing skip reasons and corresponding file lists
    """
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