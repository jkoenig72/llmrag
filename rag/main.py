"""
Main entry point for the RAG system.
Handles command line arguments and orchestrates the indexing and query processes.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# Add the current directory to the Python path to ensure imports work
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

import config
import utils
import indexer
import rag_query


def main():
    """Main entry point for the RAG application."""
    # Set up logging
    logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
    
    # Check for GPU first thing
    gpu_count = 0
    try:
        import faiss
        gpu_count = faiss.get_num_gpus()
        if gpu_count == 0:
            print("\n⚠️  PERFORMANCE WARNING: GPU not detected for FAISS.")
            print("    For significantly better performance with large indices,")
            print("    we highly recommend installing faiss-gpu instead of faiss-cpu.")
            print("    Install with: pip uninstall faiss-cpu && pip install faiss-gpu\n")
        else:
            print(f"\n✅ FAISS with GPU support detected! ({gpu_count} GPU{'s' if gpu_count > 1 else ''} available)")
            print(f"    Using FAISS version: {faiss.__version__}\n")
    except Exception as e:
        print(f"\n❌ Error detecting FAISS GPU support: {e}\n")
    
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Build a FAISS index from Markdown files for RAG")
    parser.add_argument("--source", help="Path to markdown documents")
    parser.add_argument("--target", required=True, help="Path to store/load the FAISS index")
    parser.add_argument("--test-query", action="store_true", help="Run a test query after indexing")
    parser.add_argument("--question", help="Custom question for test query (used with --test-query)")
    parser.add_argument("--skip-indexing", action="store_true", help="Skip index building and just run queries")
    parser.add_argument("--info", action="store_true", help="Show information about the FAISS index")
    parser.add_argument("--direct-llm", action="store_true", help="Query the LLM directly without RAG for comparison")
    args = parser.parse_args()

    print("🧠 Starting RAG system...")
    print(f"💾 FAISS index location: {args.target}")
    
    # Process and build index if not skipped
    if not args.skip_indexing:
        if not args.source:
            parser.error("--source is required when not using --skip-indexing")
            
        print(f"📂 Source folder: {args.source}")
        
        # Count files before processing
        product_counts = utils.count_files_by_product(args.source)
        print("\n📊 Found files to process:")
        for product, count in product_counts.items():
            if product != "Total":
                print(f"  - {product}: {count} files")
        print(f"  Total: {product_counts['Total']} files\n")

        # Process files and build index
        added, skipped, skip_summary = indexer.process_markdown_files_individually(args.source, args.target)

        # Print summary statistics
        print("\n📊 Indexing summary:")
        print(f"🆕 {added} files newly indexed")
        print(f"⏭️ {skipped} files skipped")
        
        # Print detailed skip summary
        utils.print_skip_summary(skip_summary)
    else:
        print("⏭️ Skipping indexing phase as requested...")
        # Check if the index exists
        if not os.path.exists(args.target):
            parser.error(f"Index directory {args.target} does not exist. Cannot skip indexing.")
            return

    # Run test query if requested
    if args.info:
        try:
            print("\n📊 FAISS Index Information:")
            index_info = rag_query.get_index_info(args.target)
            
            print(f"Total vectors: {index_info['total_vectors']:,}")
            print(f"Vector dimension: {index_info['vector_dimension']}")
            print(f"Index type: {index_info['index_type']}")
            print(f"Index size: {index_info['disk_size_mb']:.2f} MB")
            
            # Print GPU information
            print(f"\nGPU usage: {index_info['gpu_usage']}")
            if not index_info['gpu_available']:
                print("\n⚠️  PERFORMANCE WARNING: GPU not detected for FAISS.")
                print("    For significantly better performance with large indices,")
                print("    we highly recommend installing faiss-gpu instead of faiss-cpu.")
                print("    Install with: pip uninstall faiss-cpu && pip install faiss-gpu")
            
            # Only print product distribution if available
            if index_info.get('product_distribution') and len(index_info['product_distribution']) > 0:
                print("\nProduct distribution:")
                for product, count in sorted(index_info['product_distribution'].items(), key=lambda x: x[1], reverse=True):
                    print(f"  - {product}: {count:,} vectors")
            else:
                print("\nProduct distribution: Not available")
                
        except Exception as e:
            print(f"❌ Error retrieving index information: {e}")
            
    elif args.direct_llm:
        # Skip RAG and query the LLM directly
        rag_query.direct_llm_query(args.question)
        
    elif args.test_query:
        if args.question:
            print(f"\n🔍 Running test query with custom question: '{args.question}'")
        else:
            print("\n🔍 Running test query with default question...")
        rag_query.test_query(args.target, args.question)
        
        # If comparison is desired, also run direct LLM query
        if args.direct_llm:
            rag_query.direct_llm_query(args.question)
            
    elif args.skip_indexing:
        print("\n❓ No action performed. Use --test-query to run a query against the existing index.")


if __name__ == "__main__":
    main()