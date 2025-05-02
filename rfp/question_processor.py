import logging
import time
import json
from typing import List, Dict, Any, Optional
from langchain.schema import HumanMessage, Document

from config import (
    QUESTION_ROLE, CONTEXT_ROLE, ANSWER_ROLE, COMPLIANCE_ROLE, 
    REFERENCES_ROLE, BATCH_SIZE, API_THROTTLE_DELAY, 
    PRIMARY_PRODUCT_ROLE, LLM_PROVIDER,
    RETRIEVER_K_DOCUMENTS, CUSTOMER_RETRIEVER_K_DOCUMENTS
)
from prompts import QUESTION_PROMPT, REFINE_PROMPT
from llm_utils import (
    extract_json_from_llm_response, validate_compliance_value,
    clean_json_answer, StrictJSONOutputParser
)
from text_processing import clean_text

logger = logging.getLogger(__name__)

def truncate_context(context, max_chars=12000):
    """
    Truncate context to a maximum number of characters.
    
    Parameters
    ----------
    context : str
        The context to truncate
    max_chars : int, default 12000
        Maximum number of characters to keep
    
    Returns
    -------
    str
        Truncated context
    """
    if len(context) <= max_chars:
        return context
    
    # Try to truncate at a natural boundary
    for sep in ["\n\n", "\n", ". ", " "]:
        boundary = context[:max_chars].rfind(sep)
        if boundary > max_chars * 0.8:  # Only use boundary if it's far enough
            return context[:boundary + len(sep)]
    
    # Fallback to hard truncation
    return context[:max_chars]

def process_questions(records, qa_chain, output_columns, sheet_handler, selected_products=None, 
                     available_products=None, llm=None, customer_retriever=None, question_logger=None):
    """
    Process each question record using the QA chain with an optimized refine strategy.
    
    This implementation combines corresponding product and customer documents in each step,
    reducing the number of LLM calls and improving context integration.
    """
    batch_updates = []
    
    # IMPROVED: Enhanced QA chain debugging
    print("\n" + "="*50)
    print("DEBUGGING QA CHAIN")
    print("Chain type:", getattr(qa_chain, "chain_type", "unknown"))
    print("Chain attributes:", [attr for attr in dir(qa_chain) if not attr.startswith('_')])
    if hasattr(qa_chain, "retriever"):
        print("Retriever:", type(qa_chain.retriever).__name__)
        print("Retriever k:", getattr(qa_chain.retriever.search_kwargs, "get", lambda x: "unknown")("k", "unknown"))
    
    # Debug customer retriever if available
    if customer_retriever:
        print("Customer Retriever:", type(customer_retriever).__name__)
        print("Customer Retriever k:", getattr(customer_retriever.search_kwargs, "get", lambda x: "unknown")("k", "unknown"))
    else:
        print("Customer Retriever: None")
    print("="*50 + "\n")
    
    # Get current product focus string for logging
    product_focus_str = ", ".join(selected_products) if selected_products else "None"
    
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
            # Create enriched question
            enriched_question = f"{question}\n\n[Additional Info]\n{additional_context}"
            
            print(f"\n[CHAIN] Processing row {row_num}")
            print(f"[CHAIN] Question: {question[:100]}...")
            print(f"[CHAIN] Product focus: {product_focus_str}")
            
            # Fetch documents from both sources
            print(f"[CHAIN] Retrieving product documents...")
            product_docs = qa_chain.retriever.get_relevant_documents(enriched_question)
            print(f"[CHAIN] Retrieved {len(product_docs)} product documents")
            
            # Log product document sources
            for idx, doc in enumerate(product_docs[:3]):
                # Use product or tag field if source isn't available
                source = doc.metadata.get('source', 
                                        doc.metadata.get('product', 
                                                       doc.metadata.get('tag', 'unknown')))
                print(f"[CHAIN] Product Document {idx+1}: {source}")
                
                # Also log the document metadata for debugging
                metadata_str = ", ".join([f"{k}: {v}" for k, v in doc.metadata.items() if k in ['product', 'tag', 'source']])
                if metadata_str:
                    print(f"[CHAIN] Metadata: {metadata_str}")
                
                print(f"[CHAIN] Preview: {doc.page_content[:100]}...")
            
            # Optional: Fetch customer documents if customer retriever is available
            customer_docs = []
            has_customer_docs = False
            if customer_retriever:
                print(f"[CHAIN] Retrieving customer documents...")
                try:
                    customer_docs = customer_retriever.get_relevant_documents(enriched_question)
                    has_customer_docs = len(customer_docs) > 0
                    print(f"[CHAIN] Retrieved {len(customer_docs)} customer documents")
                    
                    # Log customer document sources
                    for idx, doc in enumerate(customer_docs[:3]):
                        source = f"Customer: {doc.metadata.get('source', 'unknown')}"
                        print(f"[CHAIN] Customer Document {idx+1}: {source}")
                        print(f"[CHAIN] Preview: {doc.page_content[:100]}...")
                except Exception as e:
                    logger.error(f"Error retrieving customer documents: {e}")
                    print(f"[CHAIN] Error retrieving customer documents: {e}")
                    customer_docs = []
            
            # Record start time for performance measurement
            start_time = time.time()
            
            # Performance improvement: Handle initial context separately
            # Create the initial context by combining first product document and first customer document
            initial_context = ""
            if product_docs:
                initial_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
                initial_context += product_docs[0].page_content
            
            if has_customer_docs and len(customer_docs) > 0:
                initial_context += "\n\n--- CUSTOMER CONTEXT ---\n\n"
                customer_content = customer_docs[0].page_content
                initial_context += customer_content
                print(f"[CHAIN] Including customer context in initial prompt (length: {len(customer_content)} chars)")
            elif customer_retriever is not None:
                print(f"[CHAIN] Customer retriever available but no documents were retrieved")
            
            # IMPORTANT: Truncate context if it's too large to avoid LLM issues
            initial_context = truncate_context(initial_context)
            print(f"[CHAIN] Total initial context length: {len(initial_context)} chars")
            
            # Use the QUESTION_PROMPT from prompts.py with our context
            product_focus = ", ".join(products_to_focus) if products_to_focus else None
            
            # Format the initial prompt using the template from prompts.py
            initial_prompt_vars = {
                "context_str": initial_context,
                "question": enriched_question
            }
            
            if product_focus:
                initial_prompt_vars["product_focus"] = product_focus
            
            # Add a timeout for the LLM call
            print(f"[CHAIN] Starting initial LLM request (with timeout)...")
            if has_customer_docs and len(customer_docs) > 0:
                log_msg = "[CHAIN] Generating initial answer with Product Document 1 & Customer Document 1"
            else:
                log_msg = "[CHAIN] Generating initial answer with Product Document 1"
            print(log_msg)
            
            # Timeouts aren't directly supported by all LLM implementations, so wrap in our own timeout
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Submit the LLM request as a future task
                future = executor.submit(lambda: QUESTION_PROMPT.format(**initial_prompt_vars))
                try:
                    # Get the formatted prompt with a timeout
                    formatted_prompt = future.result(timeout=10)  # 10 second timeout for formatting
                    
                    # Submit the actual LLM request
                    future = executor.submit(lambda: llm.invoke(formatted_prompt))
                    initial_response = future.result(timeout=60)  # 60 second timeout for LLM
                    
                    if hasattr(initial_response, "content"):
                        current_answer = initial_response.content
                    else:
                        current_answer = str(initial_response)
                    
                    print(f"[CHAIN] Initial answer generated ({len(current_answer)} chars)")
                    
                except concurrent.futures.TimeoutError:
                    print("[CHAIN] ⚠️ LLM request timed out! Falling back to product-only context...")
                    
                    # If timeout occurs, try again with just product context
                    initial_context = ""
                    if product_docs:
                        initial_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
                        initial_context += product_docs[0].page_content
                    
                    initial_prompt_vars["context_str"] = initial_context
                    formatted_prompt = QUESTION_PROMPT.format(**initial_prompt_vars)
                    initial_response = llm.invoke(formatted_prompt)
                    
                    if hasattr(initial_response, "content"):
                        current_answer = initial_response.content
                    else:
                        current_answer = str(initial_response)
                    
                    print(f"[CHAIN] Initial answer generated with product-only context ({len(current_answer)} chars)")
            
            # Parse the initial answer
            try:
                current_parsed = json.loads(current_answer)
            except json.JSONDecodeError:
                # If parsing fails, try to extract JSON using fallback
                current_parsed = extract_json_from_llm_response(current_answer)
                if not current_parsed:
                    current_parsed = {
                        "answer": current_answer,
                        "compliance": "PC",
                        "references": []
                    }
            
            # FIXED: Better handling of document pairs for refinement
            paired_docs = []
            
            # Determine how many refinement steps to perform based on remaining documents
            # Handle the case when customer documents are not available
            remaining_product_docs = product_docs[1:] if product_docs else []
            remaining_customer_docs = customer_docs[1:] if customer_docs else []
            
            # Limit the number of refinement steps to avoid excessive processing
            max_refinement_steps = 3  # Adjust as needed
            
            remaining_product_docs = remaining_product_docs[:max_refinement_steps]
            remaining_customer_docs = remaining_customer_docs[:max_refinement_steps]
            
            # Check if we have both types of documents for pairing
            has_both_doc_types = len(remaining_product_docs) > 0 and len(remaining_customer_docs) > 0
            
            # Create paired documents by index, handling cases where one source has fewer documents
            for i in range(max(len(remaining_product_docs), len(remaining_customer_docs))):
                refinement_context = ""
                has_product_doc = i < len(remaining_product_docs)
                has_customer_doc = i < len(remaining_customer_docs)
                
                # Add product document if available for this index
                if has_product_doc:
                    refinement_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
                    refinement_context += remaining_product_docs[i].page_content
                    product_source = remaining_product_docs[i].metadata.get('source', 
                                                                         remaining_product_docs[i].metadata.get('product', 
                                                                                                             remaining_product_docs[i].metadata.get('tag', 'unknown')))
                
                # Add customer document if available for this index
                if has_customer_doc:
                    refinement_context += "\n\n--- CUSTOMER CONTEXT ---\n\n"
                    refinement_context += remaining_customer_docs[i].page_content
                    customer_source = remaining_customer_docs[i].metadata.get('source', 'unknown')
                
                # IMPORTANT: Truncate context if it's too large
                refinement_context = truncate_context(refinement_context)
                
                # Only add this paired context if it's not empty
                if refinement_context.strip():
                    # Track which document types are included in this refinement
                    doc_info = {
                        "context": refinement_context,
                        "has_product": has_product_doc,
                        "has_customer": has_customer_doc,
                        "product_source": product_source if has_product_doc else None,
                        "customer_source": customer_source if has_customer_doc else None,
                        "document_number": i + 2  # +2 because we're starting with docs[1] (doc[0] was in initial step)
                    }
                    paired_docs.append(doc_info)
            
            # Keep track of refine steps (initial step already done)
            refine_steps = 1
            
            # Process each paired refinement context
            for doc_info in paired_docs:
                refine_steps += 1
                context = doc_info["context"]
                doc_number = doc_info["document_number"]
                
                # Improved logging to clearly show what documents are being used
                if has_both_doc_types:
                    if doc_info["has_product"] and doc_info["has_customer"]:
                        print(f"[CHAIN] Refinement step {refine_steps} using paired documents (Product Document {doc_number} & Customer Document {doc_number})")
                    elif doc_info["has_product"]:
                        print(f"[CHAIN] Refinement step {refine_steps} using Product Document {doc_number} only (no matching Customer Document available)")
                    elif doc_info["has_customer"]:
                        print(f"[CHAIN] Refinement step {refine_steps} using Customer Document {doc_number} only (no matching Product Document available)")
                else:
                    if doc_info["has_product"]:
                        if customer_retriever is None:
                            print(f"[CHAIN] Refinement step {refine_steps} using Product Document {doc_number} (Customer Documentation not enabled)")
                        else:
                            print(f"[CHAIN] Refinement step {refine_steps} using Product Document {doc_number} (No customer documents retrieved)")
                    elif doc_info["has_customer"]:
                        print(f"[CHAIN] Refinement step {refine_steps} using Customer Document {doc_number} (no Product Documents remaining)")
                
                # Use the REFINE_PROMPT from prompts.py with our context
                refine_prompt_vars = {
                    "question": enriched_question,
                    "existing_answer": json.dumps(current_parsed, indent=2),
                    "context_str": context
                }
                
                if product_focus:
                    refine_prompt_vars["product_focus"] = product_focus
                
                # Format the refine prompt using the template from prompts.py
                formatted_refine_prompt = REFINE_PROMPT.format(**refine_prompt_vars)
                
                # Use timeout for refinement steps too
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(lambda: llm.invoke(formatted_refine_prompt))
                    try:
                        refine_response = future.result(timeout=60)  # 60 second timeout
                        
                        if hasattr(refine_response, "content"):
                            refined_answer = refine_response.content
                        else:
                            refined_answer = str(refine_response)
                        
                        print(f"[CHAIN] Refined answer generated ({len(refined_answer)} chars)")
                        
                        # Parse the refined answer
                        try:
                            refined_parsed = json.loads(refined_answer)
                            # Update current parsed answer for next iteration
                            current_parsed = refined_parsed
                        except json.JSONDecodeError:
                            # If parsing fails, try to extract JSON using fallback
                            refined_parsed = extract_json_from_llm_response(refined_answer)
                            if refined_parsed:
                                current_parsed = refined_parsed
                            # If extraction fails, keep current parsed answer
                                
                    except concurrent.futures.TimeoutError:
                        print(f"[CHAIN] ⚠️ Refinement step {refine_steps} timed out! Skipping this document...")
                        continue
            
            # Measure total execution time
            chain_time = time.time() - start_time
            print(f"[CHAIN] Chain execution completed in {chain_time:.2f} seconds with {refine_steps} steps")
            
            # Extract the final result - use current_parsed as our final answer
            raw_answer = json.dumps(current_parsed, indent=2)
            
            print(f"[RESULT] Raw answer length: {len(raw_answer)}")
            print(f"[RESULT] Raw answer preview: {raw_answer[:200]}...")
            
            # IMPROVED: Ensure our final answer is formatted correctly
            try:
                parsed = current_parsed
                if not parsed.get("answer"):
                    print(f"[PARSING] Missing answer field, using fallback extraction")
                    fallback_parsed = extract_json_from_llm_response(raw_answer)
                    if fallback_parsed.get("answer"):
                        print(f"[PARSING] Fallback parsing succeeded")
                        parsed = fallback_parsed
                    else:
                        print(f"[PARSING] Fallback parsing also failed, creating default structure")
                        # Create minimal structure if all parsers fail
                        parsed = {
                            "answer": raw_answer.strip(),
                            "compliance": "PC", 
                            "references": []
                        }
            except Exception as e:
                print(f"[PARSING] JSON parsing error: {e}")
                parsed = {
                    "answer": raw_answer.strip(),
                    "compliance": "PC", 
                    "references": []
                }
            
            # Get the answer, compliance and references
            answer = clean_json_answer(parsed.get("answer", ""))
            compliance = validate_compliance_value(parsed.get("compliance", "PC"))
            references = parsed.get("references", [])
            
            print(f"[RESULT] Extracted answer length: {len(answer)}")
            print(f"[RESULT] Compliance: {compliance}")
            print(f"[RESULT] References count: {len(references)}")
            
            # IMPROVED: Process references better
            combined_text = answer
            if references:
                # Ensure references are properly formatted
                clean_references = []
                for ref in references:
                    # Skip empty or invalid references
                    if not ref or not isinstance(ref, str):
                        continue
                    # Clean up the reference
                    clean_ref = ref.strip()
                    if clean_ref and clean_ref not in clean_references:
                        clean_references.append(clean_ref)
                
                # Add references section only if we have valid references
                if clean_references:
                    references_text = "\n\nReferences:\n" + "\n".join(clean_references)
                    combined_text += references_text
                    references = clean_references
                else:
                    references = []
            
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
            
            # IMPROVED: Enhanced logging with more structured output
            print(f"\n{'='*80}")
            print(f"✅ Row {row_num} complete")
            print(f"Question: {question}")
            if products_to_focus:
                print(f"Product Focus: {', '.join(products_to_focus)}")
            print(f"\nAnswer:")
            print(f"{answer}")
            print(f"\nCompliance: {compliance}")
            
            if references:
                print(f"\nReferences ({len(references)}):")
                for ref in references:
                    print(f"• {ref}")
            print(f"{'='*80}")
            
            # IMPROVED: Log the question processing details if logger available
            if question_logger:
                # Gather sources from both product and customer docs
                sources = []
                for doc in product_docs:
                    source = doc.metadata.get('source', 
                                            doc.metadata.get('product', 
                                                           doc.metadata.get('tag', 'unknown')))
                    sources.append(source)
                
                for doc in customer_docs:
                    source = f"Customer: {doc.metadata.get('source', 'unknown')}"
                    sources.append(source)
                
                # Create structured log entry
                log_data = {
                    "question": question,
                    "product_focus": ", ".join(products_to_focus) if products_to_focus else "None",
                    "refine_chain_time": chain_time,
                    "refine_steps": refine_steps,
                    "product_documents": len(product_docs),
                    "customer_documents": len(customer_docs),
                    "documents_retrieved": len(product_docs) + len(customer_docs),  # Add this line
                    "answer": answer,
                    "compliance": compliance,
                    "references": references,
                    "sources_used": sources
                }
                
                # Log to question logger
                question_logger.log_enhanced_processing(row_num, log_data)

        except Exception as e:
            logger.error(f"❌ Failed to process row {row_num}: {e}")
            import traceback
            print(f"[ERROR] Exception details: {traceback.format_exc()}")
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