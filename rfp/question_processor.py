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

def validate_question_relevance(question: str, product_focus: str = None) -> bool:
    """
    Validate if a question is relevant to Salesforce products.
    
    This function uses simple heuristics to identify obviously irrelevant questions
    before sending them to the LLM, saving processing time and improving accuracy.
    
    Parameters
    ----------
    question : str
        The question text to validate
    product_focus : str, optional
        The primary product focus, if specified
        
    Returns
    -------
    bool
        True if the question seems relevant, False if it's clearly irrelevant
    """
    # Convert to lowercase for case-insensitive matching
    question_lower = question.lower()
    
    # List of irrelevant topics
    irrelevant_topics = [
        # General non-business topics
        "weather", "climate", "forecast", "rain", "temperature",
        # Colors and preferences
        "favorite color", "better color", "which color", "colors are", "red a better color than green",
        # History and people
        "history", "ancient", "medieval", "historical", "alexander the great", "napoleon", "caesar",
        # Personal opinions on non-business topics
        "do you like", "do you prefer", "what's your favorite", "what do you think about",
        # Common knowledge questions
        "how many states", "capital of", "population of", "tallest", "fastest",
        # Other clearly non-Salesforce topics
        "recipe", "cooking", "diet", "exercise", "workout", "game", "sports", "movie", "book",
        "political", "religion", "dating", "relationship", "diet"
    ]
    
    # Check for irrelevant topic patterns
    for topic in irrelevant_topics:
        if topic in question_lower:
            logger.info(f"Question '{question[:50]}...' identified as irrelevant (contains '{topic}')")
            return False
    
    # If a product focus is specified, and it's not mentioned or not a Salesforce product,
    # the question may still be relevant, so don't filter it out here
    
    return True

def validate_product_name(product_name, available_products):
    """
    Validate and normalize product name.
    Returns the normalized product name or None if invalid.
    """
    if not product_name:
        return None
        
    # Normalize the product name
    normalized = product_name.strip()
    
    # Check for exact matches first (case-insensitive)
    for available in available_products:
        if normalized.lower() == available.lower():
            return available
    
    # Check for partial matches
    for available in available_products:
        if normalized.lower() in available.lower() or available.lower() in normalized.lower():
            return available
    
    return None

def process_questions(records, qa_chain, output_columns, sheet_handler, selected_products=None, 
                     available_products=None, llm=None, customer_retriever=None, question_logger=None):
    """
    Process each question record using the QA chain and update results.
    
    Parameters
    ----------
    records : List[Dict]
        List of record dictionaries to process
    qa_chain : RetrievalQA
        The language model QA chain for generating answers
    output_columns : Dict[str, int]
        Dictionary mapping output roles to column indices
    sheet_handler : GoogleSheetHandler
        Handler for updating the Google Sheet
    selected_products : List[str], optional
        List of products selected by the user
    available_products : List[str], optional
        List of all available products for validation
    llm : OllamaLLM, optional
        Language model instance for creating new QA chains
    customer_retriever : Optional
        FAISS retriever for customer-specific documents
    question_logger : QuestionLogger, optional
        Logger for detailed question processing logs
        
    Returns
    -------
    None
    
    Notes
    -----
    This function:
    - Processes each record to extract the question and context
    - Validates and normalizes product names
    - Retrieves relevant context from both product and customer indices
    - Generates an answer using the QA chain
    - Extracts structured JSON from the response
    - Updates the Google Sheet with answers, compliance ratings, and references
    - Handles batch updates for efficiency
    """
    batch_updates = []
    for i, record in enumerate(records):
        row_num = record["sheet_row"]
        question = clean_text(record["roles"].get(QUESTION_ROLE, ""))
        primary_product = clean_text(record["roles"].get(PRIMARY_PRODUCT_ROLE, ""))
        
        additional_context = "\n".join([
            f"{k}: {clean_text(v)}" for k, v in record["roles"].items()
            if k.strip().lower() == CONTEXT_ROLE and v.strip()
        ]).strip() or "N/A"

        if not question:
            logger.warning(f"⏭️ Row {row_num} skipped: No question found.")
            continue

        # Validate question relevance using our new validation function
        if not validate_question_relevance(question, primary_product):
            # Question is clearly irrelevant, mark as NA directly
            logger.info(f"🚫 Row {row_num}: Question identified as not applicable to Salesforce.")
            
            na_response = {
                "compliance": "NA",
                "answer": "This question is not applicable to Salesforce or its product offerings and should be marked as out of scope.",
                "references": []
            }
            
            # Update sheet with NA response
            for role, col in output_columns.items():
                if role == ANSWER_ROLE:
                    batch_updates.append({"row": row_num, "col": col, "value": na_response["answer"]})
                elif role == COMPLIANCE_ROLE:
                    batch_updates.append({"row": row_num, "col": col, "value": na_response["compliance"]})
                elif role == REFERENCES_ROLE:
                    batch_updates.append({"row": row_num, "col": col, "value": ""})
                    
            # Process batch updates if needed
            if len(batch_updates) >= BATCH_SIZE or i == len(records) - 1:
                sheet_handler.update_batch(batch_updates)
                batch_updates = []
                # Add extra delay after batch to respect Google API quotas
                time.sleep(API_THROTTLE_DELAY)
                
            # Log the processing
            print("\n" + "=" * 40)
            print(f"✅ Row {row_num} complete")
            print(f"Question: {question}")
            print(f"Answer: {na_response['answer']}")
            print(f"Compliance: {na_response['compliance']}")
            print("=" * 40)
            
            # Skip further processing for this question
            continue

        # Validate and normalize product name
        if primary_product and available_products:
            validated_product = validate_product_name(primary_product, available_products)
            if validated_product:
                products_to_focus = [validated_product]
            else:
                logger.warning(f"Invalid product '{primary_product}' in row {row_num}, using selected products")
                products_to_focus = selected_products or []
        elif selected_products:
            products_to_focus = selected_products
        else:
            products_to_focus = []

        enriched_question = f"{question}\n\n[Additional Info]\n{additional_context}"

        try:
            # Retrieve product context
            product_result = qa_chain.retriever.invoke(enriched_question)
            product_context = "\n\n".join([doc.page_content for doc in product_result])
            
            # Retrieve customer context if available
            customer_context = ""
            if customer_retriever:
                customer_result = customer_retriever.invoke(enriched_question)
                customer_context = "\n\n".join([doc.page_content for doc in customer_result])
            
            # Choose appropriate prompt template
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
            
            # Generate answer
            if LLM_PROVIDER == "ollama":
                raw_answer = llm.invoke(formatted_prompt)
            else:  # llamacpp using ChatOpenAI interface
                from langchain.schema import HumanMessage
                messages = [HumanMessage(content=formatted_prompt)]
                raw_answer = llm.invoke(messages).content
            
            # Use our new StrictJSONOutputParser to ensure valid JSON
            parsed = StrictJSONOutputParser.parse(raw_answer)
            
            # As a fallback, if parsing failed, use the improved extract_json_from_llm_response
            if not parsed.get("answer") or parsed.get("answer") == raw_answer.strip():
                fallback_parsed = extract_json_from_llm_response(raw_answer)
                # Only use fallback if it extracted a better answer
                if fallback_parsed.get("answer") and fallback_parsed.get("answer") != raw_answer.strip():
                    parsed = fallback_parsed
            
            # Clean the answer text again to ensure it's formatted correctly
            parsed["answer"] = clean_json_answer(parsed.get("answer", ""))
            
            # Log the question processing details
            if question_logger:
                question_logger.log_question_processing(
                    row_num=row_num,
                    question=question,
                    product_context=product_context,
                    customer_context=customer_context,
                    formatted_prompt=formatted_prompt,
                    raw_answer=raw_answer,
                    parsed_answer=parsed,
                    products_focus=products_to_focus,
                    additional_info=additional_context
                )
            
            answer_text = parsed.get("answer", "")
            compliance_value = validate_compliance_value(parsed.get("compliance", "PC"))
            references = parsed.get("references", [])

            # Prepare updates with our enhanced reference formatting
            for role, col in output_columns.items():
                if role == ANSWER_ROLE:
                    # Ensure answer has content and is properly cleaned
                    clean_answer = clean_json_answer(answer_text)
                    if not clean_answer or len(clean_answer.strip()) < 5:
                        # Empty or very short answer, use a default message
                        clean_answer = "The system couldn't generate a proper answer for this question. Please try reformulating the question or select a different product focus."
                    batch_updates.append({"row": row_num, "col": col, "value": clean_answer})
                elif role == COMPLIANCE_ROLE:
                    batch_updates.append({"row": row_num, "col": col, "value": compliance_value})
                elif role == REFERENCES_ROLE:
                    # Format references as a newline-separated string with bullets
                    references_text = "\n".join([f"• {ref}" for ref in references]) if references else ""
                    batch_updates.append({"row": row_num, "col": col, "value": references_text})

            if len(batch_updates) >= BATCH_SIZE or i == len(records) - 1:
                sheet_handler.update_batch(batch_updates)
                batch_updates = []
                # Add extra delay after batch to respect Google API quotas
                time.sleep(API_THROTTLE_DELAY)

            logger.info(f"✅ Row {row_num} processed - Compliance: {compliance_value}")
            print("\n" + "=" * 40)
            print(f"✅ Row {row_num} complete")
            print(f"Question: {question}")
            if products_to_focus:
                print(f"Product Focus: {', '.join(products_to_focus)}")
            if customer_context:
                print(f"Customer Context: Used")
            
            # Display the answer with any JSON cleaned out
            print(f"Answer: {clean_answer}")
            print(f"Compliance: {compliance_value}")
            
            # Display the references with full URLs
            if references:
                print(f"References ({len(references)} found):")
                for ref in references:
                    print(f"  - {ref}")
            print("=" * 40)

        except Exception as e:
            logger.error(f"❌ Failed to process row {row_num}: {e}")
            # Log the error details
            if question_logger:
                question_logger.log_error(row_num, question, e)
            # Add delay even after errors to avoid quota issues
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
        
        if product and not validate_product_name(product, available_products):
            invalid_products.append((row_num, product))
    
    if invalid_products:
        print("\n⚠️ WARNING: The following products were not found in the FAISS index:")
        for row_num, product in invalid_products:
            print(f"  - Row {row_num}: '{product}'")
        
        response = input("\nDo you want to continue processing? (y/n): ")
        if response.lower() != 'y':
            logger.info("Processing cancelled by user due to invalid products.")
            exit(0)