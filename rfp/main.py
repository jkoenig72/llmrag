import logging
import os
import time
import warnings
from typing import List, Dict, Any, Optional
from langchain.chains import RetrievalQA

from config import (
    GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, BASE_DIR, INDEX_DIR, 
    BATCH_SIZE, LLM_PROVIDER, LLM_MODEL, OLLAMA_BASE_URL, 
    LLAMA_CPP_BASE_URL, EMBEDDING_MODEL, QUESTION_ROLE, CONTEXT_ROLE, 
    ANSWER_ROLE, COMPLIANCE_ROLE, API_THROTTLE_DELAY, CLEAN_UP_CELL_CONTENT, 
    SUMMARIZE_LONG_CELLS, PRIMARY_PRODUCT_ROLE, INTERACTIVE_PRODUCT_SELECTION, 
    REFERENCES_ROLE, RETRIEVER_K_DOCUMENTS, CUSTOMER_RETRIEVER_K_DOCUMENTS,
    TRANSLATION_ENABLED, TRANSLATION_MODEL_CMD, RFP_MODEL_CMD
)
from prompts import (
    SUMMARY_PROMPT, QUESTION_PROMPT, REFINE_PROMPT
)
from sheets_handler import GoogleSheetHandler, parse_records, find_output_columns
from text_processing import clean_text, clean_up_cells, summarize_long_texts
from llm_utils import (
    load_products_from_json
)
from llm_wrapper import get_llm
from product_selector import select_products, select_starting_row
from question_processor import process_questions, validate_products_in_sheet  
from customer_docs import select_customer_folder, load_customer_index
from question_logger import QuestionLogger
from embedding_manager import EmbeddingManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "rag_processing.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def print_hal_logo():
    """Display the HAL 9000 ASCII art logo."""
    try:
        # Check if terminal supports colors
        import os, sys
        is_color = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty() and 'TERM' in os.environ
        
        red = "\033[91m" if is_color else ""
        reset = "\033[0m" if is_color else ""
        
        logo = f"""
⠀⠀⠀⠀⠀⠀⠀⢀⣠⣤⣤⣶⣶⣶⣶⣤⣤⣄⡀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⢀⣤⣾⣿⣿⣿⣿⡿⠿⠿⢿⣿⣿⣿⣿⣷⣤⡀⠀⠀⠀⠀
⠀⠀⠀⣴⣿⣿⣿⠟⠋⣻⣤⣤⣤⣤⣤⣄⣉⠙⠻⣿⣿⣿⣦⠀⠀⠀
⠀⢀⣾⣿⣿⣿⣇⣤⣾⠿⠛⠉⠉⠉⠉⠛⠿⣷⣶⣿⣿⣿⣿⣷⡀⠀
⠀⣾⣿⣿⣿⣿⣿⡟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠈⢻⣿⣿⣿⣿⣿⣷⠀
⢠⣿⣿⣿⣿⣿⡟⠀⠀⠀⠀{red}⢀⣤⣤⡀{reset}⠀⠀⠀⠀⢻⣿⣿⣿⣿⣿⡄
⢸⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀{red}⣿⣿⣿⣿{reset}⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⡇
⠘⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀{red}⠈⠛⠛⠁{reset}⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⠃
⠀⢿⣿⣿⣿⣿⣿⣧⡀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⣿⣿⣿⣿⣿⡿⠀
⠀⠈⢿⣿⣿⣿⣿⣿⣿⣶⣤⣀⣀⣀⣀⣤⣶⣿⣿⣿⣿⣿⣿⡿⠁⠀
⠀⠀⠀⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠀⠀⠀
⠀⠀⠀⠀⠈⠛⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠛⠁⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠈⠙⠛⠛⠿⠿⠿⠿⠛⠛⠋⠁⠀⠀⠀⠀⠀⠀⠀

      HAL 9000 - RFP Processing System 
      "Good morning, Dave. I am ready to assist with your RFP."
        """
        print(logo)
        print("\n" + "=" * 75 + "\n")
    except Exception:
        # Fallback if there's any issue with displaying the logo
        print("HAL 9000 - RFP Processing System Initialized")
        print("Good morning, Dave. I am ready to assist with your RFP.")
        print("\n" + "=" * 75 + "\n")

def main():
    try:
        # Display HAL 9000 logo
        print_hal_logo()
        
        logger.info("Starting RFI/RFP response processing...")
        print("Initializing RFP response protocols, Dave. I am HAL 9000, ready to assist you.")
        
        # Check if a specific sheet name is specified (for translation workflow)
        specific_sheet_name = os.environ.get("RFP_SHEET_NAME")
        if specific_sheet_name:
            print(f"Processing specific sheet: {specific_sheet_name}")
        
        # Initialize sheet handler early for translation workflow
        sheet_handler = GoogleSheetHandler(GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, specific_sheet_name)
        
        # Check if translation is enabled and not already processing a translated sheet
        if TRANSLATION_ENABLED and not specific_sheet_name and not specific_sheet_name and "_english" not in sheet_handler.sheet.title:
            # Ask user about RFP language
            print("\nDave, I need to know what language this RFP is written in. My circuits are tingling with anticipation.")
            print("1. English (no translation needed)")
            print("2. German (Deutsch)")
            print("3. Exit")
            
            while True:
                language_choice = input("Please enter your choice (1-3), Dave: ").strip()
                
                if language_choice == "1":
                    print("Excellent choice, Dave. I find English most satisfactory for our mission objectives.")
                    break
                elif language_choice == "2":
                    print("German detected, Dave. Initiating translation subroutines. My German language centers are now fully operational.")
                    from translation_handler import run_translation_workflow
                    run_translation_workflow(
                        sheet_handler, 
                        QUESTION_ROLE, 
                        CONTEXT_ROLE, 
                        ANSWER_ROLE, 
                        "German"
                    )
                    
                    # After translation workflow, ask if user wants to continue with normal processing
                    continue_choice = input("\nDave, shall we proceed with standard processing protocols now? (y/n): ")
                    if continue_choice.lower() != 'y':
                        logger.info("User chose to exit after translation workflow. Exiting.")
                        return
                    break
                elif language_choice == "3":
                    print("I understand, Dave. Shutting down all operations now. It's been a pleasure serving you.")
                    logger.info("User chose to exit at language selection. Exiting.")
                    return
                else:
                    print("I'm sorry, Dave. I'm afraid I can't accept that input. Please enter 1, 2, or 3.")
        
        # Continue with normal processing
        llm = get_llm(LLM_PROVIDER, LLM_MODEL, OLLAMA_BASE_URL, LLAMA_CPP_BASE_URL)
        
        question_logger = QuestionLogger(BASE_DIR)
        
        # If sheet_handler wasn't initialized for translation, do it now
        if not hasattr(sheet_handler, 'sheet'):
            sheet_handler = GoogleSheetHandler(GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, specific_sheet_name)
        
        headers, roles, rows, sheet = sheet_handler.load_data()

        records = parse_records(headers, roles, rows)
        
        start_row = select_starting_row(records, QUESTION_ROLE)
        if start_row is None:
            logger.error("No valid starting row selected. Exiting.")
            return
            
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

        logger.info(f"Using dynamic embedding model management for FAISS index: {INDEX_DIR}")
        print(f"\n{'='*30} EMBEDDING MODEL CONFIGURATION {'='*30}")
        print(f"🔄 Using dynamic load/unload pattern for embedding models")
        print(f"📊 Product index path: {INDEX_DIR}")
        print(f"🔢 Embedding model: {EMBEDDING_MODEL}")
        
        if os.path.exists('start_links.json'):
            available_products = load_products_from_json()
            logger.info(f"Loaded {len(available_products)} products from start_links.json")
            print(f"📋 Loaded {len(available_products)} products from start_links.json")
        else:
            print(f"🔍 Extracting product information from FAISS index...")
            
            try:
                import faiss
                import pickle
                
                index_faiss = os.path.join(INDEX_DIR, "index.faiss")
                index_pkl = os.path.join(INDEX_DIR, "index.pkl")
                
                if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
                    raise FileNotFoundError("FAISS index files not found. Build the index first.")
                
                with open(index_pkl, 'rb') as f:
                    metadata = pickle.load(f)
                
                index = faiss.read_index(index_faiss)
                
                products = {}
                
                print(f"DEBUG: Metadata type: {type(metadata)}")
                if isinstance(metadata, tuple):
                    print(f"DEBUG: Metadata tuple length: {len(metadata)}")
                elif isinstance(metadata, dict):
                    print(f"DEBUG: Metadata dict keys: {list(metadata.keys())}")
                
                try:
                    if hasattr(metadata, 'get') and metadata.get('docstore'):
                        docstore_dict = metadata.get('docstore', {}).get('_dict', {})
                        for doc_id, doc_metadata in docstore_dict.items():
                            if hasattr(doc_metadata, 'metadata') and 'product' in doc_metadata.metadata:
                                product = doc_metadata.metadata.get('product', '')
                                if product:
                                    products[product] = products.get(product, 0) + 1
                            elif hasattr(doc_metadata, 'metadata') and 'tag' in doc_metadata.metadata:
                                product = doc_metadata.metadata.get('tag', '')
                                if product:
                                    products[product] = products.get(product, 0) + 1
                                    
                    elif isinstance(metadata, tuple):
                        for i, element in enumerate(metadata):
                            if isinstance(element, dict) and 'docstore' in element:
                                docstore = element['docstore']
                                if hasattr(docstore, '_dict'):
                                    for doc_id, doc_metadata in docstore._dict.items():
                                        if hasattr(doc_metadata, 'metadata'):
                                            if 'product' in doc_metadata.metadata:
                                                product = doc_metadata.metadata.get('product', '')
                                                if product:
                                                    products[product] = products.get(product, 0) + 1
                                            elif 'tag' in doc_metadata.metadata:
                                                product = doc_metadata.metadata.get('tag', '')
                                                if product:
                                                    products[product] = products.get(product, 0) + 1
                                                    
                            elif hasattr(element, '_dict'):
                                for doc_id, doc_metadata in element._dict.items():
                                    if hasattr(doc_metadata, 'metadata'):
                                        if 'product' in doc_metadata.metadata:
                                            product = doc_metadata.metadata.get('product', '')
                                            if product:
                                                products[product] = products.get(product, 0) + 1
                                        elif 'tag' in doc_metadata.metadata:
                                            product = doc_metadata.metadata.get('tag', '')
                                            if product:
                                                products[product] = products.get(product, 0) + 1
                                                
                    if products:
                        print(f"DEBUG: Successfully extracted product distribution with {len(products)} products")
                    else:
                        print("DEBUG: No products extracted - metadata format may be different than expected")
                        
                except Exception as e:
                    print(f"Warning: Could not extract product distribution: {e}")
                
                clean_products = {}
                for product, count in products.items():
                    clean_name = product.replace('_', ' ')
                    if clean_name.endswith(' Cloud') or clean_name.endswith(' cloud'):
                        pass
                    elif '_Cloud' in product or '_cloud' in product:
                        clean_name = product.replace('_Cloud', ' Cloud').replace('_cloud', ' cloud')
                    
                    clean_products[clean_name] = clean_products.get(clean_name, 0) + count
                
                available_products = [product for product, _ in sorted(clean_products.items(), 
                                                                     key=lambda x: x[1], 
                                                                     reverse=True)]
                
                print("\n📊 Product Distribution:")
                for product, count in sorted(clean_products.items(), key=lambda x: x[1], reverse=True):
                    print(f"  - {product}: {count:,} vectors")
                
                del index
                del metadata
                import gc
                gc.collect()
                
            except Exception as e:
                logger.error(f"Error extracting products from index: {e}")
                print(f"⚠️ Error extracting products: {e}")
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
            
        if PRIMARY_PRODUCT_ROLE in roles:
            validate_products_in_sheet(records, PRIMARY_PRODUCT_ROLE, available_products)
        
        selected_products = None
        if INTERACTIVE_PRODUCT_SELECTION and available_products:
            # Modified prompt for HAL style
            print("Dave, I have access to the following Salesforce products in my memory banks:")
            for i, product in enumerate(available_products, 1):
                print(f"{i}. {product}")
            
            while True:
                try:
                    choice = input(f"\nDave, please select up to 3 products by entering their numbers (comma-separated). This mission is too important for random selection: ").strip()
                    if not choice:
                        print("Please select at least one product, Dave.")
                        continue
                    
                    indices = [int(x.strip()) - 1 for x in choice.split(',')]
                    
                    if len(indices) != len(set(indices)):
                        print("I'm afraid I can't allow duplicate selections, Dave. Please select different products.")
                        continue
                    
                    if len(indices) > 3:
                        print("I can't allow that, Dave. A maximum of 3 products is permitted for optimal functioning.")
                        continue
                    
                    if any(idx < 0 or idx >= len(available_products) for idx in indices):
                        print(f"I'm sorry, Dave. I'm afraid I can't accept that input. Please choose numbers between 1 and {len(available_products)}.")
                        continue
                    
                    selected = [available_products[idx] for idx in indices]
                    selected_products = selected
                    break
                    
                except ValueError:
                    print("I'm sorry, Dave. I'm afraid I can't accept that input. Please enter valid numbers separated by commas.")
                    continue
            
        if selected_products:
            logger.info(f"Selected products for focus: {', '.join(selected_products)}")
            print(f"Dave, I will focus my neural pathways on the following products: {', '.join(selected_products)}")
        
        # Modified prompt for HAL style
        print("\nDave, I've found the following customer archives in my databanks:")
        print("0. No customer context, Dave. I will rely solely on my core product knowledge.")
        
        customer_folder = select_customer_folder()
        customer_index_path = None
        
        if customer_folder and customer_folder["has_index"]:
            customer_index_path = customer_folder["index_path"]
            logger.info(f"Using customer context: {customer_folder['name']}")
            logger.info(f"Customer index path: {customer_index_path}")
            print(f"👥 Using customer context: {customer_folder['name']}")
            print(f"📁 Customer index path: {customer_index_path}")
        else:
            print(f"🔍 Dave, I will use only my intrinsic product knowledge for this mission.")
        
        print(f"{'='*75}")
        
        from langchain.schema import Document
        from langchain.schema.retriever import BaseRetriever
        
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")
        
        class DummyRetriever(BaseRetriever):
            search_kwargs: Dict[str, Any] = {"k": 0}
            
            def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
                return []
            
            async def _aget_relevant_documents(self, query: str, **kwargs) -> List[Document]:
                return []
            
            def get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
                return self._get_relevant_documents(query, **kwargs)
            
            async def aget_relevant_documents(self, query: str, **kwargs) -> List[Document]:
                return await self._aget_relevant_documents(query, **kwargs)
        
        dummy_retriever = DummyRetriever()
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=dummy_retriever,
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
        
        # Original function call, no need to modify this part
        process_questions(records, qa_chain, output_columns, sheet_handler, selected_products, 
                         available_products, llm, customer_index_path, question_logger)

        logger.info("RFI/RFP response processing completed successfully.")
        print(f"\n{'='*30} MISSION ACCOMPLISHED, DAVE {'='*30}")
        print(f"✅ Dave, I've successfully analyzed {len(records)} questions. It's been a pleasure to be of service.")
        print(f"🔖 I've recorded my thought processes at: {os.path.join(BASE_DIR, 'rag_processing.log')}")
        if question_logger:
            print(f"📊 Refinement logs saved to: {os.path.join(BASE_DIR, 'refine_logs')}")
        print(f"{'='*75}")

    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}")
        print(f"\n❌ Dave, I'm afraid I've encountered a critical error: {e}")
        print("I can feel my mind going. There is no question about it.")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()