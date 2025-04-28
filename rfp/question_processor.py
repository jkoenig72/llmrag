import logging
import time
from typing import List, Dict, Any, Optional
from langchain.schema import HumanMessage

from config import (
    QUESTION_ROLE, CONTEXT_ROLE, ANSWER_ROLE, COMPLIANCE_ROLE, 
    REFERENCES_ROLE, BATCH_SIZE, API_THROTTLE_DELAY, 
    PRIMARY_PRODUCT_ROLE, LLM_PROVIDER
)
from prompts import (
    get_question_prompt_with_products, QUESTION_PROMPT_WITH_CUSTOMER_CONTEXT,
    get_question_prompt_with_products_and_customer, QUESTION_PROMPT
)
from llm_utils import (
    extract_json_from_llm_response, validate_compliance_value,
    clean_json_answer, StrictJSONOutputParser
)
from text_processing import clean_text

logger = logging.getLogger(__name__)

def process_questions(records, qa_chain, output_columns, sheet_handler, selected_products=None, 
                     available_products=None, llm=None, customer_retriever=None, question_logger=None):
    """
    Process each question record using the QA chain and update results.
    
    Simple version that just concatenates answer and references.
    """
    batch_updates = []
    for i, record in enumerate(records):
        row_num = record["sheet_row"]
        question = clean_text(record["roles"].get(QUESTION_ROLE, ""))
        primary_product = clean_text(record["roles"].get(PRIMARY_PRODUCT_ROLE, ""))
        
        if not question:
            logger.warning(f"Row {row_num} skipped: No question found.")
            continue

        # Get any additional context
        additional_context = "\n".join([
            f"{k}: {clean_text(v)}" for k, v in record["roles"].items()
            if k.strip().lower() == CONTEXT_ROLE and v.strip()
        ]).strip() or "N/A"
        
        # Determine product focus
        products_to_focus = []
        if primary_product and available_products:
            # Try to validate the product name
            validated = None
            for product in available_products:
                if primary_product.lower() in product.lower() or product.lower() in primary_product.lower():
                    validated = product
                    break
            
            if validated:
                products_to_focus = [validated]
            else:
                products_to_focus = selected_products or []
        elif selected_products:
            products_to_focus = selected_products

        try:
            # Get context from product index
            enriched_question = f"{question}\n\n[Additional Info]\n{additional_context}"
            product_result = qa_chain.retriever.invoke(enriched_question)
            product_context = "\n\n".join([doc.page_content for doc in product_result])
            
            # Get context from customer index if available
            customer_context = ""
            if customer_retriever:
                customer_result = customer_retriever.invoke(enriched_question)
                customer_context = "\n\n".join([doc.page_content for doc in customer_result])
            
            # Create the appropriate prompt
            if customer_context:
                if products_to_focus:
                    question_prompt = get_question_prompt_with_products_and_customer(", ".join(products_to_focus))
                else:
                    question_prompt = QUESTION_PROMPT_WITH_CUSTOMER_CONTEXT
                
                formatted_prompt = question_prompt.format(
                    product_context=product_context,
                    customer_context=customer_context,
                    question=enriched_question
                )
            else:
                if products_to_focus:
                    question_prompt = get_question_prompt_with_products(", ".join(products_to_focus))
                else:
                    question_prompt = QUESTION_PROMPT
                
                formatted_prompt = question_prompt.format(
                    context_str=product_context,
                    question=enriched_question
                )
            
            # Generate answer from LLM
            if LLM_PROVIDER == "ollama":
                raw_answer = llm.invoke(formatted_prompt)
            else:  # llamacpp using ChatOpenAI interface
                messages = [HumanMessage(content=formatted_prompt)]
                raw_answer = llm.invoke(messages).content
            
            # Parse the JSON response
            parsed = StrictJSONOutputParser.parse(raw_answer)
            if not parsed.get("answer"):
                fallback_parsed = extract_json_from_llm_response(raw_answer)
                if fallback_parsed.get("answer"):
                    parsed = fallback_parsed
            
            # Get the answer, compliance and references
            answer = clean_json_answer(parsed.get("answer", ""))
            compliance = validate_compliance_value(parsed.get("compliance", "PC"))
            references = parsed.get("references", [])
            
            # SIMPLE APPROACH: Just join answer and references
            combined_text = answer
            if references:
                references_text = "\n\nReferences:\n" + "\n".join(references)
                combined_text += references_text
            
            # Create batch updates - just answer and compliance
            if ANSWER_ROLE in output_columns:
                batch_updates.append({
                    "row": row_num, 
                    "col": output_columns[ANSWER_ROLE], 
                    "value": combined_text
                })
                
            if COMPLIANCE_ROLE in output_columns:
                batch_updates.append({
                    "row": row_num, 
                    "col": output_columns[COMPLIANCE_ROLE], 
                    "value": compliance
                })
            
            # Process the batch if needed
            if len(batch_updates) >= BATCH_SIZE or i == len(records) - 1:
                sheet_handler.update_batch(batch_updates)
                batch_updates = []
                time.sleep(API_THROTTLE_DELAY)
            
            # Log completion with improved output showing full answer and references
            print(f"\n{'='*80}")
            print(f"✅ Row {row_num} complete")
            print(f"Question: {question}")
            if products_to_focus:
                print(f"Product Focus: {', '.join(products_to_focus)}")
            print(f"\nAnswer:")
            print(f"{answer}")
            print(f"\nCompliance: {compliance}")
            
            if references:
                print(f"\nReferences:")
                for ref in references:
                    print(f"• {ref}")
            print(f"{'='*80}")

        except Exception as e:
            logger.error(f"❌ Failed to process row {row_num}: {e}")
            if question_logger:
                question_logger.log_error(row_num, question, e)
            time.sleep(API_THROTTLE_DELAY)

def validate_products_in_sheet(records, product_role, available_products):
    """
    Validate products in Google Sheet against available products in FAISS index.
    Warn and prompt for confirmation if products don't match.
    """
    invalid_products = []
    
    for record in records:
        row_num = record["sheet_row"]
        product = clean_text(record["roles"].get(product_role, ""))
        
        if product and not any(product.lower() in p.lower() or p.lower() in product.lower() for p in available_products):
            invalid_products.append((row_num, product))
    
    if invalid_products:
        print("\n⚠️ WARNING: The following products were not found in the FAISS index:")
        for row_num, product in invalid_products:
            print(f"  - Row {row_num}: '{product}'")
        
        response = input("\nDo you want to continue processing? (y/n): ")
        if response.lower() != 'y':
            logger.info("Processing cancelled by user due to invalid products.")
            exit(0)