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
from prompts import (
    get_question_prompt_with_products, QUESTION_PROMPT_WITH_CUSTOMER_CONTEXT,
    get_question_prompt_with_products_and_customer, QUESTION_PROMPT, REFINE_PROMPT
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
    
    Note: For optimal results, RETRIEVER_K_DOCUMENTS and CUSTOMER_RETRIEVER_K_DOCUMENTS
    should have the same value (e.g., both set to 3).
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
            
            # SIMPLIFIED: Fetch documents from both sources
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
            if customer_retriever:
                print(f"[CHAIN] Retrieving customer documents...")
                customer_docs = customer_retriever.get_relevant_documents(enriched_question)
                print(f"[CHAIN] Retrieved {len(customer_docs)} customer documents")
                
                # Log customer document sources
                for idx, doc in enumerate(customer_docs[:3]):
                    source = f"Customer: {doc.metadata.get('source', 'unknown')}"
                    print(f"[CHAIN] Customer Document {idx+1}: {source}")
                    print(f"[CHAIN] Preview: {doc.page_content[:100]}...")
            
            # SIMPLIFIED: Prepare documents for refine chain
            # Start with one product document + one customer document (if available)
            # Then process remaining documents one by one
            
            # Record start time for performance measurement
            start_time = time.time()
            
            # Create the initial prompt with first product document and customer document (if available)
            initial_context = ""
            if product_docs:
                initial_context += product_docs[0].page_content
            
            if customer_docs:
                # Add separator if we already have product context
                if initial_context:
                    initial_context += "\n\n--- CUSTOMER CONTEXT ---\n\n"
                initial_context += customer_docs[0].page_content
            
            # Create the appropriate prompt with product focus if specified
            if products_to_focus:
                product_str = ", ".join(products_to_focus)
                prompt_text = f"""
You are a Senior Solution Engineer at Salesforce, with deep expertise in {product_str}.

CRITICAL INSTRUCTIONS:
1. Your ENTIRE response must be ONLY a valid JSON object - nothing else
2. The "answer" field MUST contain NORMAL PLAIN TEXT ONLY - NO JSON STRUCTURES, NO LISTS, NO OBJECTS
3. NEVER put JSON, code blocks, or structured data inside the "answer" field
4. The "references" field must be an array of relevant Salesforce URLs from the context
5. Be OPTIMISTIC about compliance ratings - if it can be achieved with configuration or low-code tools, mark it as FC

Use the following context to answer the question:

{initial_context}

Question:
{enriched_question}

Format your response as a JSON with the following structure:
{{
  "compliance": "FC|PC|NC|NA",
  "answer": "Write ONLY a clear explanation in 5-10 sentences. NO JSON HERE!",
  "references": ["URL1", "URL2"]
}}
"""
            else:
                # Use a simpler prompt without product focus
                prompt_text = f"""
You are a Senior Solution Engineer at Salesforce.

CRITICAL INSTRUCTIONS:
1. Your ENTIRE response must be ONLY a valid JSON object - nothing else
2. The "answer" field MUST contain NORMAL PLAIN TEXT ONLY - NO JSON STRUCTURES, NO LISTS, NO OBJECTS
3. NEVER put JSON, code blocks, or structured data inside the "answer" field
4. The "references" field must be an array of relevant Salesforce URLs from the context
5. Be OPTIMISTIC about compliance ratings - if it can be achieved with configuration or low-code tools, mark it as FC

Use the following context to answer the question:

{initial_context}

Question:
{enriched_question}

Format your response as a JSON with the following structure:
{{
  "compliance": "FC|PC|NC|NA",
  "answer": "Write ONLY a clear explanation in 5-10 sentences. NO JSON HERE!",
  "references": ["URL1", "URL2"]
}}
"""
            
            # Generate initial answer
            print(f"[CHAIN] Generating initial answer with first document(s)")
            initial_response = llm.invoke(prompt_text)
            
            if hasattr(initial_response, "content"):
                current_answer = initial_response.content
            else:
                current_answer = str(initial_response)
            
            print(f"[CHAIN] Initial answer generated ({len(current_answer)} chars)")
            
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
            
            # Prepare the remaining documents for refinement
            remaining_docs = []
            
            # Add remaining product docs (skip the first one which we already used)
            for doc in product_docs[1:]:
                remaining_docs.append(("product", doc))
            
            # Add remaining customer docs (skip the first one if it was used)
            if customer_docs and len(customer_docs) > 1:
                for doc in customer_docs[1:]:
                    remaining_docs.append(("customer", doc))
            
            # Keep track of refine steps
            refine_steps = 1
            
            # Process each remaining document
            for doc_type, doc in remaining_docs:
                refine_steps += 1
                print(f"[CHAIN] Refinement step {refine_steps} using {doc_type} document")
                
                # Create refine prompt
                if products_to_focus:
                    product_str = ", ".join(products_to_focus)
                    refine_prompt = f"""
You are refining an RFI response about Salesforce, particularly regarding {product_str}.

CRITICAL INSTRUCTIONS:
1. Return ONLY a valid JSON object with the EXACT same structure as the existing answer
2. The "answer" field must contain ONLY plain text - NO JSON, NO code blocks
3. Your task is to ENHANCE the existing answer with new information, not replace it entirely 

Carefully analyze the new context and update ONLY if the new information:
1. Contradicts your previous answer with more accurate information
2. Provides more specific details about Salesforce capabilities
3. Changes the compliance level based on new evidence
4. Adds relevant references not previously included

Compliance levels:
- FC: Available through standard features, configuration, or low-code tools
- PC: Requires significant custom development
- NC: Not possible even with customization
- NA: Out of scope

Existing JSON Answer:
{json.dumps(current_parsed, indent=2)}

New Context:
{doc.page_content}

Question:
{enriched_question}

Return ONLY this JSON structure (with your refinements):
{{
  "compliance": "FC|PC|NC|NA",
  "answer": "Refined explanation in plain text only (5-10 sentences)",
  "references": ["URL1", "URL2"]
}}
"""
                else:
                    # Generic refine prompt without product focus
                    refine_prompt = f"""
You are refining an RFI response about Salesforce.

CRITICAL INSTRUCTIONS:
1. Return ONLY a valid JSON object with the EXACT same structure as the existing answer
2. The "answer" field must contain ONLY plain text - NO JSON, NO code blocks
3. Your task is to ENHANCE the existing answer with new information, not replace it entirely 

Carefully analyze the new context and update ONLY if the new information:
1. Contradicts your previous answer with more accurate information
2. Provides more specific details about Salesforce capabilities
3. Changes the compliance level based on new evidence
4. Adds relevant references not previously included

Compliance levels:
- FC: Available through standard features, configuration, or low-code tools
- PC: Requires significant custom development
- NC: Not possible even with customization
- NA: Out of scope

Existing JSON Answer:
{json.dumps(current_parsed, indent=2)}

New Context:
{doc.page_content}

Question:
{enriched_question}

Return ONLY this JSON structure (with your refinements):
{{
  "compliance": "FC|PC|NC|NA",
  "answer": "Refined explanation in plain text only (5-10 sentences)",
  "references": ["URL1", "URL2"]
}}
"""
                
                # Get refined answer
                refine_response = llm.invoke(refine_prompt)
                
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