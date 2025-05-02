import logging
import os
import time
import warnings
from typing import List, Dict, Any, Optional
from langchain.chains import RetrievalQA

# Import from local modules
from config import (
    GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, BASE_DIR, INDEX_DIR, 
    # Removed: SKIP_INDEXING, (not used in this file)
    BATCH_SIZE, LLM_PROVIDER, LLM_MODEL, OLLAMA_BASE_URL, 
    LLAMA_CPP_BASE_URL, EMBEDDING_MODEL, QUESTION_ROLE, CONTEXT_ROLE, 
    ANSWER_ROLE, COMPLIANCE_ROLE, API_THROTTLE_DELAY, CLEAN_UP_CELL_CONTENT, 
    SUMMARIZE_LONG_CELLS, PRIMARY_PRODUCT_ROLE, INTERACTIVE_PRODUCT_SELECTION, 
    REFERENCES_ROLE, RETRIEVER_K_DOCUMENTS, CUSTOMER_RETRIEVER_K_DOCUMENTS
)
from prompts import (
    SUMMARY_PROMPT, QUESTION_PROMPT, REFINE_PROMPT
)
from sheets_handler import GoogleSheetHandler, parse_records, find_output_columns
from text_processing import clean_text, clean_up_cells, summarize_long_texts
from llm_utils import (
    # Removed: discover_products_from_index, (not used anymore)
    load_products_from_json
)
from llm_wrapper import get_llm
from product_selector import select_products, select_starting_row
from question_processor import process_questions, validate_products_in_sheet  
from customer_docs import select_customer_folder, load_customer_index
from question_logger import QuestionLogger
from embedding_manager import EmbeddingManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "rag_processing.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Main execution function for the RAG processing pipeline.
    
    This function orchestrates the entire workflow:
    1. Load data from Google Sheets
    2. Set up the language model
    3. Process and clean text if configured
    4. Summarize long text if configured
    5. Process each question by retrieving context and generating answers
    6. Update the Google Sheet with answers and compliance ratings
    
    Returns
    -------
    None
    
    Notes
    -----
    The function uses configuration parameters from the config module.
    Processing can be customized via environment variables or the config module.
    Errors are logged but may not halt processing (depends on the error).
    """
    try:
        logger.info("Starting RFI/RFP response processing...")
        
        # Use factory to get LLM instance (includes llama-server check)
        llm = get_llm(LLM_PROVIDER, LLM_MODEL, OLLAMA_BASE_URL, LLAMA_CPP_BASE_URL)
        
        # Initialize question logger
        question_logger = QuestionLogger(BASE_DIR)
        
        sheet_handler = GoogleSheetHandler(GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE)
        headers, roles, rows, sheet = sheet_handler.load_data()

        records = parse_records(headers, roles, rows)
        
        # Let user select starting row
        start_row = select_starting_row(records, QUESTION_ROLE)
        if start_row is None:
            logger.error("No valid starting row selected. Exiting.")
            return
            
        # Filter records to only include rows from start_row onwards
        records = [r for r in records if r["sheet_row"] >= start_row]
        logger.info(f"Processing {len(records)} records starting from row {start_row}")

        if CLEAN_UP_CELL_CONTENT:
            clean_up_cells(records, QUESTION_ROLE, CONTEXT_ROLE, API_THROTTLE_DELAY)
            sheet_handler.update_cleaned_records(records, roles, QUESTION_ROLE, CONTEXT_ROLE, API_THROTTLE_DELAY)

        if SUMMARIZE_LONG_CELLS:
            summarize_long_texts(records, llm, SUMMARY_PROMPT)
            sheet_handler.update_cleaned_records(records, roles, QUESTION_ROLE, CONTEXT_ROLE, API_THROTTLE_DELAY)

        output_columns = find_output_columns(roles, ANSWER_ROLE, COMPLIANCE_ROLE, REFERENCES_ROLE)
        if not output_columns:
            logger.error("No output columns found. Exiting.")
            return

        # No longer load FAISS index here - we'll do it on-demand using EmbeddingManager
        logger.info(f"Using dynamic embedding model management for FAISS index: {INDEX_DIR}")
        print(f"\n{'='*30} EMBEDDING MODEL CONFIGURATION {'='*30}")
        print(f"🔄 Using dynamic load/unload pattern for embedding models")
        print(f"📊 Product index path: {INDEX_DIR}")
        print(f"🔢 Embedding model: {EMBEDDING_MODEL}")
        
        # Load products directly from JSON or discover from index
        # This still requires a temporary loading of the FAISS index
        if os.path.exists('start_links.json'):
            available_products = load_products_from_json()
            logger.info(f"Loaded {len(available_products)} products from start_links.json")
            print(f"📋 Loaded {len(available_products)} products from start_links.json")
        else:
            # Use the get_index_info function to extract product info directly from the index
            print(f"🔍 Extracting product information from FAISS index...")
            
            try:
                # Import needed modules for index inspection
                import faiss
                import pickle
                # Note: we don't import os here since it's already imported at the top level
                
                # Path to index files
                index_faiss = os.path.join(INDEX_DIR, "index.faiss")
                index_pkl = os.path.join(INDEX_DIR, "index.pkl")
                
                if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
                    raise FileNotFoundError("FAISS index files not found. Build the index first.")
                
                # Load the index metadata
                with open(index_pkl, 'rb') as f:
                    metadata = pickle.load(f)
                
                # Load the FAISS index to get its properties
                index = faiss.read_index(index_faiss)
                
                # Extract product distribution from metadata
                products = {}
                
                # Debug: print metadata structure to understand its format
                print(f"DEBUG: Metadata type: {type(metadata)}")
                if isinstance(metadata, tuple):
                    print(f"DEBUG: Metadata tuple length: {len(metadata)}")
                elif isinstance(metadata, dict):
                    print(f"DEBUG: Metadata dict keys: {list(metadata.keys())}")
                
                # Try multiple approaches to extract product information
                try:
                    # Approach 1: Direct access to docstore dictionary (newer format)
                    if hasattr(metadata, 'get') and metadata.get('docstore'):
                        docstore_dict = metadata.get('docstore', {}).get('_dict', {})
                        for doc_id, doc_metadata in docstore_dict.items():
                            if hasattr(doc_metadata, 'metadata') and 'product' in doc_metadata.metadata:
                                product = doc_metadata.metadata.get('product', '')
                                if product:
                                    products[product] = products.get(product, 0) + 1
                            # Also check for 'tag' field which might contain product info
                            elif hasattr(doc_metadata, 'metadata') and 'tag' in doc_metadata.metadata:
                                product = doc_metadata.metadata.get('tag', '')
                                if product:
                                    products[product] = products.get(product, 0) + 1
                                    
                    # Approach 2: Handle tuple format (older or modified format)
                    elif isinstance(metadata, tuple):
                        # Try different elements of the tuple
                        for i, element in enumerate(metadata):
                            # Look for docstore in dict elements
                            if isinstance(element, dict) and 'docstore' in element:
                                docstore = element['docstore']
                                if hasattr(docstore, '_dict'):
                                    for doc_id, doc_metadata in docstore._dict.items():
                                        if hasattr(doc_metadata, 'metadata'):
                                            # Try product field first
                                            if 'product' in doc_metadata.metadata:
                                                product = doc_metadata.metadata.get('product', '')
                                                if product:
                                                    products[product] = products.get(product, 0) + 1
                                            # Then try tag field
                                            elif 'tag' in doc_metadata.metadata:
                                                product = doc_metadata.metadata.get('tag', '')
                                                if product:
                                                    products[product] = products.get(product, 0) + 1
                                                    
                            # Look for direct access to documents
                            elif hasattr(element, '_dict'):
                                for doc_id, doc_metadata in element._dict.items():
                                    if hasattr(doc_metadata, 'metadata'):
                                        # Try product field first
                                        if 'product' in doc_metadata.metadata:
                                            product = doc_metadata.metadata.get('product', '')
                                            if product:
                                                products[product] = products.get(product, 0) + 1
                                        # Then try tag field
                                        elif 'tag' in doc_metadata.metadata:
                                            product = doc_metadata.metadata.get('tag', '')
                                            if product:
                                                products[product] = products.get(product, 0) + 1
                                                
                    # Optional: Print extracted products for debugging
                    if products:
                        print(f"DEBUG: Successfully extracted product distribution with {len(products)} products")
                    else:
                        print("DEBUG: No products extracted - metadata format may be different than expected")
                        
                except Exception as e:
                    print(f"Warning: Could not extract product distribution: {e}")
                    # Continue without product distribution
                
                # Clean up product names
                clean_products = {}
                for product, count in products.items():
                    # Convert underscores to spaces in product names
                    clean_name = product.replace('_', ' ')
                    if clean_name.endswith(' Cloud') or clean_name.endswith(' cloud'):
                        # Keep as is
                        pass
                    elif '_Cloud' in product or '_cloud' in product:
                        clean_name = product.replace('_Cloud', ' Cloud').replace('_cloud', ' cloud')
                    
                    # Add to clean products dictionary
                    clean_products[clean_name] = clean_products.get(clean_name, 0) + count
                
                # Convert to sorted list based on document count (most common first)
                available_products = [product for product, _ in sorted(clean_products.items(), 
                                                                     key=lambda x: x[1], 
                                                                     reverse=True)]
                
                # Print product distribution
                print("\n📊 Product Distribution:")
                for product, count in sorted(clean_products.items(), key=lambda x: x[1], reverse=True):
                    print(f"  - {product}: {count:,} vectors")
                
                # Free resources
                del index
                del metadata
                import gc
                gc.collect()
                
            except Exception as e:
                logger.error(f"Error extracting products from index: {e}")
                print(f"⚠️ Error extracting products: {e}")
                # Fallback to hardcoded list in case of any errors
                available_products = ["Sales Cloud", "Service Cloud", "Marketing Cloud", "Platform", 
                                      "Experience Cloud", "Communications Cloud", "Data Cloud",
                                      "Agentforce", "MuleSoft"]
                
            if not available_products:
                logger.warning("No products found in index, using fallback list")
                print("⚠️ No products found in index, using fallback list")
                available_products = ["Sales Cloud", "Service Cloud", "Marketing Cloud", "Platform", 
                                      "Experience Cloud", "Communications Cloud", "Data Cloud",
                                      "Agentforce", "MuleSoft"]
            
            logger.info(f"Discovered {len(available_products)} products from FAISS index")
            print(f"📋 Using {len(available_products)} products from index")
            print("\nAvailable Products:")
            for product in available_products:
                print(f"  - {product}")
            print("")
            
        # Validate products from sheet against available products
        if PRIMARY_PRODUCT_ROLE in roles:
            validate_products_in_sheet(records, PRIMARY_PRODUCT_ROLE, available_products)
        
        selected_products = None
        if INTERACTIVE_PRODUCT_SELECTION and available_products:
            selected_products = select_products(available_products)
            
        if selected_products:
            logger.info(f"Selected products for focus: {', '.join(selected_products)}")
            print(f"🎯 Selected products for focus: {', '.join(selected_products)}")
        
        # Select customer folder and index
        customer_folder = select_customer_folder()
        customer_index_path = None
        
        if customer_folder and customer_folder["has_index"]:
            customer_index_path = customer_folder["index_path"]
            logger.info(f"Using customer context: {customer_folder['name']}")
            logger.info(f"Customer index path: {customer_index_path}")
            print(f"👥 Using customer context: {customer_folder['name']}")
            print(f"📁 Customer index path: {customer_index_path}")
        else:
            print(f"🔍 Using product knowledge only (no customer context)")
        
        print(f"{'='*75}")
        
        # Create a dummy retriever for compatibility with the QA chain
        # The actual retrieval will happen in the question_processor
        # This is just a placeholder to satisfy the QA chain's initialization
        from langchain.schema import Document
        from langchain.schema.retriever import BaseRetriever
        
        # Suppress deprecation warnings for BaseRetriever
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")
        
        # Updated DummyRetriever class compliant with latest LangChain patterns
        class DummyRetriever(BaseRetriever):
            """A dummy retriever that always returns empty results but has required attributes."""
            
            # Define as a class variable for Pydantic model
            search_kwargs: Dict[str, Any] = {"k": 0}
            
            # Implement required abstract methods with underscore prefix
            def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
                """Always returns empty list."""
                return []
            
            async def _aget_relevant_documents(self, query: str, **kwargs) -> List[Document]:
                """Always returns empty list."""
                return []
            
            # Add backward compatibility methods to prevent warnings
            def get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
                """Backward compatibility method."""
                return self._get_relevant_documents(query, **kwargs)
            
            async def aget_relevant_documents(self, query: str, **kwargs) -> List[Document]:
                """Backward compatibility method."""
                return await self._aget_relevant_documents(query, **kwargs)
        
        dummy_retriever = DummyRetriever()
        
        # Use the standard QA chain - we'll pass the product focus during question processing
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=dummy_retriever,  # We don't use this - it's just a placeholder
            chain_type="refine",
            input_key="question",
            return_source_documents=True,
            chain_type_kwargs={
                "question_prompt": QUESTION_PROMPT,
                "refine_prompt": REFINE_PROMPT,
                "document_variable_name": "context_str",
                "initial_response_name": "existing_answer",
            }
        )
        
        # Pass customer index path instead of retriever
        process_questions(records, qa_chain, output_columns, sheet_handler, selected_products, 
                         available_products, llm, customer_index_path, question_logger)

        logger.info("RFI/RFP response processing completed successfully.")
        print(f"\n{'='*30} PROCESSING COMPLETE {'='*30}")
        print(f"✅ Successfully processed {len(records)} questions")
        print(f"🔖 Detailed logs saved to: {os.path.join(BASE_DIR, 'rag_processing.log')}")
        if question_logger:
            print(f"📊 Refinement logs saved to: {os.path.join(BASE_DIR, 'refine_logs')}")
        print(f"{'='*75}")

    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}")
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()