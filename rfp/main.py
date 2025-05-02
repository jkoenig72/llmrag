import logging
import os
import time
from typing import List, Dict, Any, Optional
from langchain.chains import RetrievalQA

# Import from local modules
from config import (
    GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, BASE_DIR, INDEX_DIR, 
    SKIP_INDEXING, BATCH_SIZE, LLM_PROVIDER, LLM_MODEL, OLLAMA_BASE_URL, 
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
    load_faiss_index, discover_products_from_index, load_products_from_json
)
from llm_wrapper import get_llm
from product_selector import select_products, select_starting_row
from question_processor import (
    validate_products_in_sheet, process_questions
)
from customer_docs import select_customer_folder, load_customer_index
from question_logger import QuestionLogger

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

        # Load main FAISS index
        faiss_index = load_faiss_index(INDEX_DIR, EMBEDDING_MODEL, SKIP_INDEXING)
        retriever = faiss_index.as_retriever(search_kwargs={"k": RETRIEVER_K_DOCUMENTS})
        
        # Load products directly from JSON or discover from index
        if os.path.exists('start_links.json'):
            available_products = load_products_from_json()
        else:
            available_products = discover_products_from_index(faiss_index)
        
        # Validate products from sheet against available products
        if PRIMARY_PRODUCT_ROLE in roles:
            validate_products_in_sheet(records, PRIMARY_PRODUCT_ROLE, available_products)
        
        selected_products = None
        if INTERACTIVE_PRODUCT_SELECTION and available_products:
            selected_products = select_products(available_products)
            
        if selected_products:
            logger.info(f"Selected products for focus: {', '.join(selected_products)}")
        
        # Select customer folder and index
        customer_folder = select_customer_folder()
        customer_index = None
        customer_retriever = None
        
        if customer_folder and customer_folder["has_index"]:
            customer_index = load_customer_index(customer_folder["name"])
            if customer_index:
                customer_retriever = customer_index.as_retriever(search_kwargs={"k": CUSTOMER_RETRIEVER_K_DOCUMENTS})
                logger.info(f"Using customer context: {customer_folder['name']}")
            else:
                logger.warning(f"Failed to load customer index for {customer_folder['name']}")
        
        # Use the standard QA chain - we'll pass the product focus during question processing
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=retriever,
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

        process_questions(records, qa_chain, output_columns, sheet_handler, selected_products, 
                         available_products, llm, customer_retriever, question_logger)

        logger.info("RFI/RFP response processing completed successfully.")

    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}")

if __name__ == "__main__":
    main()