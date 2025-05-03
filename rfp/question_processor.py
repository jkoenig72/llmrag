import logging
import time
import json
import copy
from typing import List, Dict, Any, Optional
from langchain.schema import HumanMessage, Document

from config import (
    QUESTION_ROLE, CONTEXT_ROLE, ANSWER_ROLE, COMPLIANCE_ROLE, 
    REFERENCES_ROLE, BATCH_SIZE, API_THROTTLE_DELAY, 
    PRIMARY_PRODUCT_ROLE, LLM_PROVIDER,
    RETRIEVER_K_DOCUMENTS, CUSTOMER_RETRIEVER_K_DOCUMENTS,
    INDEX_DIR, EMBEDDING_MODEL
)
from llm_utils import (
    extract_json_from_llm_response, validate_compliance_value,
    clean_json_answer, StrictJSONOutputParser
)
from text_processing import clean_text
from embedding_manager import EmbeddingManager
from prompts import QUESTION_PROMPT, REFINE_PROMPT

logger = logging.getLogger(__name__)

def validate_products_in_sheet(records, product_role, available_products):
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

def truncate_context(context, max_chars=12000):
    if len(context) <= max_chars:
        return context
    
    for sep in ["\n\n", "\n", ". ", " "]:
        boundary = context[:max_chars].rfind(sep)
        if boundary > max_chars * 0.8:
            return context[:boundary + len(sep)]
    
    return context[:max_chars]

def process_questions(records, qa_chain, output_columns, sheet_handler, selected_products=None, 
                     available_products=None, llm=None, customer_index_path=None, question_logger=None):
    batch_updates = []
    
    embedding_manager = EmbeddingManager(EMBEDDING_MODEL)
    
    print("\n" + "="*50)
    print("DEBUGGING QA CHAIN")
    print("Chain type:", getattr(qa_chain, "chain_type", "unknown"))
    print("Chain attributes:", [attr for attr in dir(qa_chain) if not attr.startswith('_')])
    
    print("Retriever:", type(qa_chain.retriever).__name__)
    if hasattr(qa_chain.retriever, "search_kwargs"):
        print("Retriever k:", getattr(qa_chain.retriever.search_kwargs, "get", lambda x: "unknown")("k", "unknown"))
    else:
        print("Retriever: Custom retriever (no search_kwargs attribute)")
    
    print("\nEMBEDDING MANAGEMENT:")
    print(f"Using dynamic load/unload pattern for embedding models")
    print(f"Product index path: {INDEX_DIR}")
    print(f"Customer index path: {customer_index_path if customer_index_path else 'None'}")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print("="*50 + "\n")
    
    product_focus_str = ", ".join(selected_products) if selected_products else "None"
    
    for i, record in enumerate(records):
        row_num = record["sheet_row"]
        question = clean_text(record["roles"].get(QUESTION_ROLE, ""))
        primary_product = clean_text(record["roles"].get(PRIMARY_PRODUCT_ROLE, ""))
        
        if not question:
            logger.warning(f"Row {row_num} skipped: No question found.")
            continue

        additional_context = "\n".join([
            f"{k}: {clean_text(v)}" for k, v in record["roles"].items()
            if k.strip().lower() == CONTEXT_ROLE and v.strip()
        ]).strip() or "N/A"
        
        products_to_focus = []
        if primary_product and available_products:
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
            # Initialize a list to hold chain log data for this question
            chain_log_data = []
            
            enriched_question = f"{question}\n\n[Additional Info]\n{additional_context}"
            
            print(f"\n[CHAIN] ======== Processing Question for Row {row_num} ========")
            print(f"[CHAIN] Question: {question[:100]}...")
            print(f"[CHAIN] Product focus: {product_focus_str}")
            
            print(f"[CHAIN] Starting product context retrieval...")
            
            product_docs = embedding_manager.query_index(
                index_path=INDEX_DIR,
                query=enriched_question,
                k=RETRIEVER_K_DOCUMENTS,
                use_cpu=False,
                db_name="Products DB"
            )
            
            print(f"[CHAIN] Product context retrieval complete - got {len(product_docs)} documents")
            
            if product_docs:
                print(f"\n[CHAIN] Product Document Sources:")
                for idx, doc in enumerate(product_docs[:3]):
                    source = doc.metadata.get('source', 
                                            doc.metadata.get('product', 
                                                           doc.metadata.get('tag', 'unknown')))
                    print(f"[CHAIN]   #{idx+1}: {source}")
                    
                    metadata_str = ", ".join([f"{k}: {v}" for k, v in doc.metadata.items() if k in ['product', 'tag', 'source']])
                    if metadata_str:
                        print(f"[CHAIN]      Metadata: {metadata_str}")
                    
                    print(f"[CHAIN]      Preview: {doc.page_content[:100]}...")
                
                if len(product_docs) > 3:
                    print(f"[CHAIN]   ... and {len(product_docs) - 3} more documents")
            else:
                print(f"[CHAIN] ⚠️ Warning: No product documents retrieved")
            
            customer_docs = []
            has_customer_docs = False
            if customer_index_path:
                print(f"\n[CHAIN] Starting customer context retrieval...")
                
                try:
                    customer_docs = embedding_manager.query_index(
                        index_path=customer_index_path,
                        query=enriched_question,
                        k=CUSTOMER_RETRIEVER_K_DOCUMENTS,
                        use_cpu=False,
                        db_name="Customer DB"
                    )
                    
                    has_customer_docs = len(customer_docs) > 0
                    print(f"[CHAIN] Customer context retrieval complete - got {len(customer_docs)} documents")
                    
                    if customer_docs:
                        print(f"\n[CHAIN] Customer Document Sources:")
                        for idx, doc in enumerate(customer_docs[:3]):
                            source = f"Customer: {doc.metadata.get('source', 'unknown')}"
                            print(f"[CHAIN]   #{idx+1}: {source}")
                            print(f"[CHAIN]      Preview: {doc.page_content[:100]}...")
                        
                        if len(customer_docs) > 3:
                            print(f"[CHAIN]   ... and {len(customer_docs) - 3} more documents")
                    else:
                        print(f"[CHAIN] ⚠️ Warning: No customer documents retrieved")
                except Exception as e:
                    logger.error(f"Error retrieving customer documents: {e}")
                    print(f"[CHAIN] ❌ Error retrieving customer documents: {e}")
                    customer_docs = []
            else:
                print(f"[CHAIN] ℹ️ No customer context selected - using product knowledge only")
            
            print(f"\n[CHAIN] ======== Context Retrieval Complete ========")
            
            start_time = time.time()
            
            initial_context = ""
            
            print(f"\n[CHAIN] ======== Starting LLM Chain Processing ========")
            print(f"[CHAIN] Building initial context...")
            
            if product_docs:
                initial_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
                initial_context += product_docs[0].page_content
                product_doc_source = product_docs[0].metadata.get('source', 'unknown')
                print(f"[CHAIN] Added product document #1 from: {product_doc_source}")
            
            if has_customer_docs and len(customer_docs) > 0:
                initial_context += "\n\n--- CUSTOMER CONTEXT ---\n\n"
                customer_content = customer_docs[0].page_content
                initial_context += customer_content
                customer_doc_source = customer_docs[0].metadata.get('source', 'unknown')
                print(f"[CHAIN] Added customer document #1 from: {customer_doc_source}")
                print(f"[CHAIN] Combined initial context length: {len(initial_context)} chars")
            elif customer_index_path is not None:
                print(f"[CHAIN] No customer documents were retrieved - using product context only")
            
            original_length = len(initial_context)
            initial_context = truncate_context(initial_context)
            if len(initial_context) < original_length:
                print(f"[CHAIN] ⚠️ Initial context truncated from {original_length} to {len(initial_context)} chars")
            
            product_focus = ", ".join(products_to_focus) if products_to_focus else None
            
            initial_prompt_vars = {
                "context_str": initial_context,
                "question": enriched_question
            }
            
            if product_focus:
                initial_prompt_vars["product_focus"] = product_focus
            
            print(f"[CHAIN] Generating initial answer with LLM...")
            
            # Log context information
            initial_context_info = {
                "product_doc": product_doc_source if product_docs else None,
                "customer_doc": customer_doc_source if has_customer_docs and len(customer_docs) > 0 else None,
                "context_size": len(initial_context)
            }
            
            if has_customer_docs and len(customer_docs) > 0:
                log_msg = "[CHAIN] Initial step using Product Document #1 & Customer Document #1"
            else:
                log_msg = "[CHAIN] Initial step using Product Document #1 only"
            print(log_msg)
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(lambda: QUESTION_PROMPT.format(**initial_prompt_vars))
                try:
                    print(f"[CHAIN] Formatting initial prompt...")
                    formatted_prompt = future.result(timeout=10)
                    
                    # Store initial prompt information
                    initial_prompt_data = {
                        "step_type": "PROMPT",
                        "context_info": initial_context_info,
                        "prompt": formatted_prompt
                    }
                    
                    print(f"[CHAIN] Sending request to LLM (timeout: 60s)...")
                    llm_start_time = time.time()
                    future = executor.submit(lambda: llm.invoke(formatted_prompt))
                    initial_response = future.result(timeout=60)
                    llm_time = time.time() - llm_start_time
                    
                    if hasattr(initial_response, "content"):
                        current_answer = initial_response.content
                    else:
                        current_answer = str(initial_response)
                    
                    print(f"[CHAIN] ✅ Initial answer generated in {llm_time:.2f}s ({len(current_answer)} chars)")
                    
                    # Add response to prompt data
                    initial_prompt_data["raw_response"] = current_answer
                    initial_prompt_data["processing_time"] = llm_time
                    chain_log_data.append(initial_prompt_data)
                    
                except concurrent.futures.TimeoutError:
                    print("[CHAIN] ⚠️ LLM request timed out! Falling back to product-only context...")
                    
                    initial_context = ""
                    if product_docs:
                        initial_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
                        initial_context += product_docs[0].page_content
                    
                    initial_prompt_vars["context_str"] = initial_context
                    formatted_prompt = QUESTION_PROMPT.format(**initial_prompt_vars)
                    
                    # Create a fallback prompt data entry
                    fallback_prompt_data = {
                        "step_type": "PROMPT_FALLBACK",
                        "context_info": {
                            "product_doc": product_doc_source if product_docs else None,
                            "customer_doc": None,
                            "context_size": len(initial_context)
                        },
                        "prompt": formatted_prompt,
                        "error": "Initial prompt timeout"
                    }
                    chain_log_data.append(fallback_prompt_data)
                    
                    print(f"[CHAIN] Retrying with product-only context...")
                    llm_start_time = time.time()
                    initial_response = llm.invoke(formatted_prompt)
                    llm_time = time.time() - llm_start_time
                    
                    if hasattr(initial_response, "content"):
                        current_answer = initial_response.content
                    else:
                        current_answer = str(initial_response)
                    
                    print(f"[CHAIN] ✅ Initial answer generated with fallback in {llm_time:.2f}s ({len(current_answer)} chars)")
                    
                    # Update fallback prompt data
                    fallback_prompt_data["raw_response"] = current_answer
                    fallback_prompt_data["processing_time"] = llm_time
            
            try:
                print(f"[CHAIN] Parsing initial answer...")
                current_parsed = json.loads(current_answer)
                print(f"[CHAIN] ✅ Successfully parsed initial answer as JSON")
                
                # Add parsed answer to prompt data
                if chain_log_data:
                    chain_log_data[-1]["parsed_answer"] = current_parsed
            except json.JSONDecodeError:
                print(f"[CHAIN] ⚠️ Failed to parse as JSON, trying fallback extraction...")
                current_parsed = extract_json_from_llm_response(current_answer)
                if not current_parsed:
                    print(f"[CHAIN] ⚠️ Fallback extraction failed, creating default answer structure")
                    current_parsed = {
                        "answer": current_answer,
                        "compliance": "PC",
                        "references": []
                    }
                else:
                    print(f"[CHAIN] ✅ Fallback extraction succeeded")
                
                # Update parsed answer in prompt data
                if chain_log_data:
                    chain_log_data[-1]["parsed_answer"] = current_parsed
            
            print(f"[CHAIN] Initial answer compliance: {current_parsed.get('compliance', 'Unknown')}")
            answer_preview = current_parsed.get('answer', '')[:100] + "..." if len(current_parsed.get('answer', '')) > 100 else current_parsed.get('answer', '')
            print(f"[CHAIN] Initial answer preview: {answer_preview}")
            
            paired_docs = []
            
            remaining_product_docs = product_docs[1:] if product_docs else []
            remaining_customer_docs = customer_docs[1:] if customer_docs else []
            
            has_both_doc_types = len(remaining_product_docs) > 0 and len(remaining_customer_docs) > 0
            
            print(f"\n[CHAIN] Planning refinement steps...")
            print(f"[CHAIN] Remaining product documents: {len(remaining_product_docs)}")
            print(f"[CHAIN] Remaining customer documents: {len(remaining_customer_docs)}")
            print(f"[CHAIN] Has both document types: {has_both_doc_types}")
            
            for i in range(max(len(remaining_product_docs), len(remaining_customer_docs))):
                refinement_context = ""
                has_product_doc = i < len(remaining_product_docs)
                has_customer_doc = i < len(remaining_customer_docs)
                
                if has_product_doc:
                    refinement_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
                    refinement_context += remaining_product_docs[i].page_content
                    product_source = remaining_product_docs[i].metadata.get('source', 
                                                                         remaining_product_docs[i].metadata.get('product', 
                                                                                                             remaining_product_docs[i].metadata.get('tag', 'unknown')))
                
                if has_customer_doc:
                    refinement_context += "\n\n--- CUSTOMER CONTEXT ---\n\n"
                    refinement_context += remaining_customer_docs[i].page_content
                    customer_source = remaining_customer_docs[i].metadata.get('source', 'unknown')
                
                original_length = len(refinement_context)
                refinement_context = truncate_context(refinement_context)
                
                if refinement_context.strip():
                    doc_info = {
                        "context": refinement_context,
                        "has_product": has_product_doc,
                        "has_customer": has_customer_doc,
                        "product_source": product_source if has_product_doc else None,
                        "customer_source": customer_source if has_customer_doc else None,
                        "document_number": i + 2,
                        "truncated": original_length > len(refinement_context)
                    }
                    paired_docs.append(doc_info)
            
            print(f"[CHAIN] Created {len(paired_docs)} refinement steps")
            
            refine_steps = 1
            
            for doc_idx, doc_info in enumerate(paired_docs):
                refine_steps += 1
                context = doc_info["context"]
                doc_number = doc_info["document_number"]
                
                print(f"\n[CHAIN] ======== Refinement Step {refine_steps} ========")
                
                if has_both_doc_types:
                    if doc_info["has_product"] and doc_info["has_customer"]:
                        print(f"[CHAIN] Using paired documents: Product #{doc_number} & Customer #{doc_number}")
                    elif doc_info["has_product"]:
                        print(f"[CHAIN] Using Product Document #{doc_number} only (no matching Customer Document)")
                    elif doc_info["has_customer"]:
                        print(f"[CHAIN] Using Customer Document #{doc_number} only (no matching Product Document)")
                else:
                    if doc_info["has_product"]:
                        if customer_index_path is None:
                            print(f"[CHAIN] Using Product Document #{doc_number} (Customer Documentation not enabled)")
                        else:
                            print(f"[CHAIN] Using Product Document #{doc_number} (No customer documents retrieved)")
                    elif doc_info["has_customer"]:
                        print(f"[CHAIN] Using Customer Document #{doc_number} (no Product Documents remaining)")
                
                if doc_info["has_product"]:
                    print(f"[CHAIN] Product source: {doc_info['product_source']}")
                if doc_info["has_customer"]:
                    print(f"[CHAIN] Customer source: {doc_info['customer_source']}")
                
                print(f"[CHAIN] Context size: {len(context)} chars")
                if doc_info["truncated"]:
                    print(f"[CHAIN] ⚠️ Context was truncated to fit size limits")
                
                # Log context information for this refinement step
                refine_context_info = {
                    "product_doc": doc_info["product_source"] if doc_info["has_product"] else None,
                    "customer_doc": doc_info["customer_source"] if doc_info["has_customer"] else None,
                    "context_size": len(context),
                    "document_number": doc_number,
                    "truncated": doc_info["truncated"]
                }
                
                refine_prompt_vars = {
                    "question": enriched_question,
                    "existing_answer": json.dumps(current_parsed, indent=2),
                    "context_str": context
                }
                
                if product_focus:
                    refine_prompt_vars["product_focus"] = product_focus
                
                print(f"[CHAIN] Formatting refinement prompt...")
                formatted_refine_prompt = REFINE_PROMPT.format(**refine_prompt_vars)
                
                # Create refine step data structure
                refine_step_data = {
                    "step_type": "REFINE",
                    "step_number": refine_steps,
                    "context_info": refine_context_info,
                    "prompt": formatted_refine_prompt
                }
                
                print(f"[CHAIN] Sending refinement to LLM (timeout: 60s)...")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    llm_start_time = time.time()
                    future = executor.submit(lambda: llm.invoke(formatted_refine_prompt))
                    try:
                        refine_response = future.result(timeout=60)
                        llm_time = time.time() - llm_start_time
                        
                        if hasattr(refine_response, "content"):
                            refined_answer = refine_response.content
                        else:
                            refined_answer = str(refine_response)
                        
                        print(f"[CHAIN] ✅ Refinement generated in {llm_time:.2f}s ({len(refined_answer)} chars)")
                        
                        # Add response to refine step data
                        refine_step_data["raw_response"] = refined_answer
                        refine_step_data["processing_time"] = llm_time
                        
                        try:
                            print(f"[CHAIN] Parsing refined answer...")
                            refined_parsed = json.loads(refined_answer)
                            print(f"[CHAIN] ✅ Successfully parsed refined answer as JSON")
                            
                            # Add parsed answer to refine step data
                            refine_step_data["parsed_answer"] = refined_parsed
                            
                            prev_compliance = current_parsed.get('compliance', 'Unknown')
                            new_compliance = refined_parsed.get('compliance', 'Unknown')
                            if prev_compliance != new_compliance:
                                print(f"[CHAIN] 📊 Compliance changed: {prev_compliance} -> {new_compliance}")
                            
                            # Update current parsed answer for next iteration
                            current_parsed = refined_parsed
                        except json.JSONDecodeError:
                            print(f"[CHAIN] ⚠️ Failed to parse as JSON, trying fallback extraction...")
                            refined_parsed = extract_json_from_llm_response(refined_answer)
                            if refined_parsed:
                                print(f"[CHAIN] ✅ Fallback extraction succeeded")
                                current_parsed = refined_parsed
                                refine_step_data["parsed_answer"] = refined_parsed
                            else:
                                print(f"[CHAIN] ⚠️ Fallback extraction failed, keeping previous answer")
                                refine_step_data["parsed_answer"] = "Failed to parse"
                        
                        # Add this refine step to chain log data
                        chain_log_data.append(refine_step_data)
                                
                    except concurrent.futures.TimeoutError:
                        print(f"[CHAIN] ⚠️ Refinement step {refine_steps} timed out! Skipping this document...")
                        refine_step_data["error"] = "Timeout"
                        refine_step_data["processing_time"] = 60.0  # Timeout value
                        chain_log_data.append(refine_step_data)
                        continue
            
            chain_time = time.time() - start_time
            print(f"\n[CHAIN] ======== Chain Execution Summary ========")
            print(f"[CHAIN] Total execution time: {chain_time:.2f} seconds")
            print(f"[CHAIN] Total steps completed: {refine_steps}")
            print(f"[CHAIN] Final compliance rating: {current_parsed.get('compliance', 'Unknown')}")
            print(f"[CHAIN] Final answer length: {len(current_parsed.get('answer', ''))}")
            print(f"[CHAIN] Final references: {len(current_parsed.get('references', []))}")
            print(f"[CHAIN] ======== End of Chain Processing ========\n")
            
            raw_answer = json.dumps(current_parsed, indent=2)
            
            print(f"[RESULT] Raw answer length: {len(raw_answer)}")
            print(f"[RESULT] Raw answer preview: {raw_answer[:200]}...")
            
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
            
            answer = clean_json_answer(parsed.get("answer", ""))
            compliance = validate_compliance_value(parsed.get("compliance", "PC"))
            references = parsed.get("references", [])
            
            print(f"[RESULT] Extracted answer length: {len(answer)}")
            print(f"[RESULT] Compliance: {compliance}")
            print(f"[RESULT] References count: {len(references)}")
            
            combined_text = answer
            if references:
                clean_references = []
                for ref in references:
                    if not ref or not isinstance(ref, str):
                        continue
                    clean_ref = ref.strip()
                    if clean_ref and clean_ref not in clean_references:
                        clean_references.append(clean_ref)
                
                if clean_references:
                    references_text = "\n\nReferences:\n" + "\n".join(clean_references)
                    combined_text += references_text
                    references = clean_references
                else:
                    references = []
            
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
            
            if len(batch_updates) >= BATCH_SIZE or i == len(records) - 1:
                sheet_handler.update_batch(batch_updates)
                batch_updates = []
                time.sleep(API_THROTTLE_DELAY)
            
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
            
            if question_logger:
                sources = []
                for doc in product_docs:
                    source = doc.metadata.get('source', 
                                            doc.metadata.get('product', 
                                                           doc.metadata.get('tag', 'unknown')))
                    sources.append(source)
                
                for doc in customer_docs:
                    source = f"Customer: {doc.metadata.get('source', 'unknown')}"
                    sources.append(source)
                
                log_data = {
                    "question": question,
                    "product_focus": ", ".join(products_to_focus) if products_to_focus else "None",
                    "refine_chain_time": chain_time,
                    "refine_steps": refine_steps,
                    "product_documents": len(product_docs),
                    "customer_documents": len(customer_docs),
                    "documents_retrieved": len(product_docs) + len(customer_docs),
                    "answer": answer,
                    "compliance": compliance,
                    "references": references,
                    "sources_used": sources,
                    # Add chain log data
                    "chain_log_data": chain_log_data
                }
                
                question_logger.log_enhanced_processing(row_num, log_data)

        except Exception as e:
            logger.error(f"❌ Failed to process row {row_num}: {e}")
            import traceback
            print(f"[ERROR] Exception details: {traceback.format_exc()}")
            if question_logger:
                question_logger.log_error(row_num, question, e)
            time.sleep(API_THROTTLE_DELAY)