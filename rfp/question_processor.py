import logging
import time
import json
from typing import List, Dict, Any, Optional
from langchain.schema import HumanMessage, Document

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
    Process each question record using the QA chain with proper refine strategy.
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
            
            # FIXED: Create a clean input dictionary that doesn't include any unexpected variables
            # that could cause errors in the refine chain
            chain_input = {
                "question": enriched_question,
                # No metadata dictionary - we'll handle products directly
            }
            
            # Initialize source documents and chain_result for later use
            source_documents = []
            chain_result = None
            
            # IMPROVED: Track retrieval and refinement steps
            print(f"[CHAIN] Retrieving relevant documents...")
            
            # Pre-fetch documents to log them
            # This doesn't change the chain execution but gives us visibility
            retriever_docs = qa_chain.retriever.get_relevant_documents(enriched_question)
            print(f"[CHAIN] Retrieved {len(retriever_docs)} documents")
            source_documents = retriever_docs  # Store for logging
            
            # IMPROVED: Log top document sources for visibility using available metadata
            for idx, doc in enumerate(retriever_docs[:3]):
                # Use product or tag field if source isn't available
                source = doc.metadata.get('source', 
                                        doc.metadata.get('product', 
                                                       doc.metadata.get('tag', 'unknown')))
                score = doc.metadata.get('score', 'N/A')
                print(f"[CHAIN] Document {idx+1}: {source} (score: {score})")
                
                # Also log the document metadata for debugging
                metadata_str = ", ".join([f"{k}: {v}" for k, v in doc.metadata.items() if k in ['product', 'tag', 'source']])
                if metadata_str:
                    print(f"[CHAIN] Metadata: {metadata_str}")
                
                print(f"[CHAIN] Preview: {doc.page_content[:100]}...")
            
            print(f"[CHAIN] Starting refine chain execution with {len(retriever_docs)} documents")
            start_time = time.time()
            
            # FIXED: Create a custom LLMChain for this specific question that includes product focus
            # This is the clean approach that works with the refine chain
            if products_to_focus:
                # Generate a custom prompt with specific product names
                product_str = ", ".join(products_to_focus)
                
                # Direct invocation approach - use simple question and direct LLM call first
                prompt_text = f"""
You are a Senior Solution Engineer at Salesforce, with deep expertise in {product_str}.

CRITICAL INSTRUCTIONS:
1. Your ENTIRE response must be ONLY a valid JSON object - nothing else
2. The "answer" field MUST contain NORMAL PLAIN TEXT ONLY - NO JSON STRUCTURES, NO LISTS, NO OBJECTS
3. NEVER put JSON, code blocks, or structured data inside the "answer" field
4. The "references" field must be an array of relevant Salesforce URLs from the context
5. Be OPTIMISTIC about compliance ratings - if it can be achieved with configuration or low-code tools, mark it as FC

Does {product_str} support the following:

{enriched_question}

Format your response as a JSON with the following structure:
{{
  "compliance": "FC|PC|NC|NA",
  "answer": "Write ONLY a clear explanation in 5-10 sentences. NO JSON HERE!",
  "references": ["URL1", "URL2"]
}}
"""
                
                # Use direct LLM invocation instead of the chain
                print(f"[DIRECT] Using direct LLM invocation with product focus: {product_str}")
                start_time = time.time()
                direct_response = llm.invoke(prompt_text)
                chain_time = time.time() - start_time
                print(f"[DIRECT] LLM invocation completed in {chain_time:.2f} seconds")
                
                if hasattr(direct_response, "content"):
                    raw_answer = direct_response.content
                else:
                    raw_answer = str(direct_response)
                
                # Create a mock chain_result for compatibility with the rest of the code
                chain_result = {
                    "result": raw_answer,
                    "source_documents": source_documents
                }
            else:
                # Use the standard chain without product focus
                print(f"[CHAIN] Using standard chain without product focus")
                chain_result = qa_chain.invoke(chain_input)
                chain_time = time.time() - start_time
                print(f"[CHAIN] Chain execution completed in {chain_time:.2f} seconds")
                
                # Extract the result
                if isinstance(chain_result, dict):
                    if "result" in chain_result:
                        raw_answer = chain_result["result"]
                        print(f"[CHAIN] Got result from chain result dictionary")
                    elif "answer" in chain_result:
                        raw_answer = chain_result["answer"]
                        print(f"[CHAIN] Got answer from chain result dictionary")
                    else:
                        # Fall back to string representation
                        raw_answer = str(chain_result)
                        print(f"[CHAIN] Converted dictionary result to string")
                elif isinstance(chain_result, str):
                    raw_answer = chain_result
                    print(f"[CHAIN] Got string result from chain")
                    # Create a mock chain_result for consistency
                    chain_result = {
                        "result": raw_answer,
                        "source_documents": source_documents
                    }
                else:
                    raw_answer = str(chain_result)
                    print(f"[CHAIN] Converted unknown result type to string")
                    # Create a mock chain_result for consistency
                    chain_result = {
                        "result": raw_answer,
                        "source_documents": source_documents
                    }
            
            print(f"[RESULT] Raw answer length: {len(raw_answer)}")
            print(f"[RESULT] Raw answer preview: {raw_answer[:200]}...")
            
            # IMPROVED: Enhanced JSON parsing with better error handling
            print(f"[PARSING] Parsing LLM response")
            try:
                parsed = StrictJSONOutputParser.parse(raw_answer)
                if not parsed.get("answer"):
                    print(f"[PARSING] Primary parsing failed, using fallback extraction")
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
                # FIXED: Safely extract source documents
                sources = []
                if chain_result and isinstance(chain_result, dict) and "source_documents" in chain_result:
                    sources = []
                    for doc in chain_result["source_documents"]:
                        # Use the most descriptive metadata field available
                        source = doc.metadata.get('source', 
                                                doc.metadata.get('product', 
                                                               doc.metadata.get('tag', 'unknown')))
                        sources.append(source)
                
                # Create structured log entry
                log_data = {
                    "question": question,
                    "product_focus": ", ".join(products_to_focus) if products_to_focus else "None",
                    "refine_chain_time": chain_time,
                    "documents_retrieved": len(retriever_docs),
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