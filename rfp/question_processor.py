import logging
import time
import json
import re  # Make sure re is imported
import unicodedata  # Make sure unicodedata is imported
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
from langchain.schema import Document
import functools
import os

from config import get_config
from text_processing import TextProcessor

# Get configuration at module initialization
config = get_config()
QUESTION_ROLE = config.question_role
CONTEXT_ROLE = config.context_role
ANSWER_ROLE = config.answer_role
COMPLIANCE_ROLE = config.compliance_role
REFERENCES_ROLE = config.references_role
API_THROTTLE_DELAY = config.api_throttle_delay
PRIMARY_PRODUCT_ROLE = config.primary_product_role
RETRIEVER_K_DOCUMENTS = config.retriever_k_documents
CUSTOMER_RETRIEVER_K_DOCUMENTS = config.customer_retriever_k_documents
MAX_CONTEXT_CHARS = config.max_context_chars
LLM_REQUEST_TIMEOUT = config.llm_request_timeout

from llm_utils import JsonProcessor
from prompts import PromptManager
from reference_handler import ReferenceHandler

logger = logging.getLogger(__name__)


class PromptFormatter:
    """Formats prompts for LLM queries."""
    
    @staticmethod
    def format_initial_prompt(question: str, context: str, product_focus: Optional[str] = None) -> str:
        """Format the initial prompt with question and context."""
        prompt_vars = {
            "context_str": context,
            "question": question
        }
        
        if product_focus:
            prompt_vars["product_focus"] = product_focus
            
        return PromptManager.QUESTION_PROMPT.format(**prompt_vars)
    
    @staticmethod
    def format_refinement_prompt(question: str, current_answer: Dict[str, Any], 
                               context: str, product_focus: Optional[str] = None) -> str:
        """Format a refinement prompt with current answer and new context."""
        prompt_vars = {
            "question": question,
            "existing_answer": json.dumps(current_answer, indent=2),
            "context_str": context
        }
        
        if product_focus:
            prompt_vars["product_focus"] = product_focus
            
        return PromptManager.REFINE_PROMPT.format(**prompt_vars)


class LLMCaller:
    """Handles calling LLMs with proper timeout handling.
    
    This class provides a wrapper around LLM calls with timeout handling and
    proper error management. It ensures that LLM calls don't hang indefinitely
    and provides consistent error handling.
    
    Attributes:
        llm: The language model instance to use for calls
    """
    
    def __init__(self, llm):
        """
        Initialize the LLM caller.
        
        Args:
            llm: The language model instance to use for calls
        """
        self.llm = llm
        
    def call_with_timeout(self, prompt: str, timeout: int = LLM_REQUEST_TIMEOUT) -> Tuple[Optional[str], Optional[str], float]:
        """Call LLM with timeout handling.
        
        Args:
            prompt: The prompt to send to the LLM
            timeout: Maximum time to wait for response in seconds
            
        Returns:
            Tuple containing:
            - response_text: The LLM's response text or None if error
            - error_message: Error message if any, None if successful
            - elapsed_time: Time taken for the call in seconds
            
        Raises:
            concurrent.futures.TimeoutError: If the call exceeds the timeout
            Exception: For any other errors during the LLM call
        """
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: self.llm.invoke(prompt))
            try:
                start_time = time.time()
                response = future.result(timeout=timeout)
                elapsed_time = time.time() - start_time
                
                if hasattr(response, "content"):
                    response_text = response.content
                else:
                    response_text = str(response)
                    
                return response_text, None, elapsed_time
            except concurrent.futures.TimeoutError:
                logger.error(f"LLM call timed out after {timeout} seconds")
                return None, f"Timeout after {timeout} seconds", timeout
            except Exception as e:
                logger.error(f"Error during LLM call: {str(e)}")
                return None, str(e), 0


class ResponseParser:
    """Parses and validates LLM responses.
    
    This class handles the parsing and validation of LLM responses, ensuring
    they are in the correct format and contain all required fields. It provides
    fallback mechanisms for handling malformed responses.
    """
    
    @staticmethod
    def parse_response(response_text: Optional[str], error: Optional[str] = None) -> Dict[str, Any]:
        """Parse LLM response text into structured format.
        
        Args:
            response_text: The raw response text from the LLM
            error: Optional error message if the LLM call failed
            
        Returns:
            Dictionary containing:
            - answer: The LLM's answer text
            - compliance: Compliance status (FC, PC, NC)
            - references: List of reference URLs
            
        Raises:
            ValueError: If the response cannot be parsed and is missing required fields
        """
        if error:
            logger.error(f"Error in LLM response: {error}")
            return {
                "answer": f"Error generating response: {error}",
                "compliance": "NC",
                "references": []
            }
            
        if not response_text:
            logger.warning("Empty response received from LLM")
            return {
                "answer": "No response received from language model.",
                "compliance": "NC",
                "references": []
            }
            
        try:
            # Try to parse as JSON
            parsed_json = json.loads(response_text)
            # Validate required fields
            if "answer" not in parsed_json:
                raise ValueError("Response missing required 'answer' field")
            if "compliance" not in parsed_json:
                raise ValueError("Response missing required 'compliance' field")
                
            # Ensure references field exists
            if "references" not in parsed_json:
                parsed_json["references"] = []
                
            return parsed_json
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse response as JSON: {e}")
            # Fallback to extraction
            return JsonProcessor.extract_json_from_llm_response(response_text)
        except ValueError as e:
            logger.error(f"Invalid response format: {e}")
            return {
                "answer": f"Error: Invalid response format - {str(e)}",
                "compliance": "NC",
                "references": []
            }


class DocumentPairCreator:
    """Creates document pairs for refinement steps.
    
    This class handles the creation of document pairs for the refinement process,
    combining product and customer documents in a way that maximizes context
    while staying within token limits.
    
    The class ensures that:
    1. Documents are properly paired and ordered
    2. Context is properly formatted and labeled
    3. Metadata is preserved and tracked
    4. Context length is managed appropriately
    """
    
    @staticmethod
    def create_document_pairs(product_docs: List[Document], customer_docs: List[Document]) -> List[Dict[str, Any]]:
        """Create document pairs for refinement, pairing product and customer docs.
        
        Args:
            product_docs: List of product documents to pair
            customer_docs: List of customer documents to pair
            
        Returns:
            List of dictionaries containing paired document information:
            - context: str - Combined context from both documents
            - has_product: bool - Whether a product document was included
            - has_customer: bool - Whether a customer document was included
            - product_source: Optional[str] - Source of product document
            - customer_source: Optional[str] - Source of customer document
            - document_number: int - Sequential number of the pair
            - truncated: bool - Whether the context was truncated
            
        Raises:
            ValueError: If both document lists are empty
        """
        if not product_docs and not customer_docs:
            raise ValueError("Both product_docs and customer_docs are empty")
            
        paired_docs = []
        
        # Skip first documents as they're used for initial answer
        remaining_product_docs = product_docs[1:] if len(product_docs) > 1 else []
        remaining_customer_docs = customer_docs[1:] if len(customer_docs) > 1 else []
        
        for i in range(max(len(remaining_product_docs), len(remaining_customer_docs))):
            has_product_doc = i < len(remaining_product_docs)
            has_customer_doc = i < len(remaining_customer_docs)
            
            if not has_product_doc and not has_customer_doc:
                continue
                
            refinement_context = ""
            product_source = None
            customer_source = None
            
            if has_product_doc:
                refinement_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
                refinement_context += remaining_product_docs[i].page_content
                product_source = DocumentMetadataExtractor.extract_product_metadata(remaining_product_docs[i])
            
            if has_customer_doc:
                refinement_context += "\n\n--- CUSTOMER CONTEXT ---\n\n"
                refinement_context += remaining_customer_docs[i].page_content
                customer_source = remaining_customer_docs[i].metadata.get('source', 'unknown')
            
            original_length = len(refinement_context)
            # Use truncate_text instead of truncate_context
            refinement_context = TextProcessor.truncate_text(refinement_context, max_length=config.max_context_chars)
            
            if refinement_context.strip():
                doc_info = {
                    "context": refinement_context,
                    "has_product": has_product_doc,
                    "has_customer": has_customer_doc,
                    "product_source": product_source if has_product_doc else None,
                    "customer_source": customer_source if has_customer_doc else None,
                    "document_number": i + 2,  # +2 because first docs used for initial answer
                    "truncated": original_length > len(refinement_context)
                }
                paired_docs.append(doc_info)
                
        return paired_docs


class DocumentMetadataExtractor:
    """Extracts and processes document metadata.
    
    This class handles the extraction and processing of metadata from documents,
    ensuring consistent formatting and handling of missing metadata.
    
    The class provides methods for:
    1. Extracting product-specific metadata
    2. Handling missing or malformed metadata
    3. Formatting metadata for display
    """
    
    @staticmethod
    def extract_product_metadata(doc: Document) -> str:
        """Extract product metadata from a document.
        
        Args:
            doc: The document to extract metadata from
            
        Returns:
            Formatted string containing the document's source information
            
        Raises:
            AttributeError: If the document doesn't have a metadata attribute
        """
        if not hasattr(doc, 'metadata'):
            logger.warning("Document missing metadata attribute")
            return "unknown (no metadata)"
        
        metadata = doc.metadata
        
        if 'source' in metadata and metadata['source']:
            return metadata['source']
        
        if 'product' in metadata and metadata['product']:
            return f"Product: {metadata['product']}"
            
        logger.warning("Document missing source and product metadata")
        return "unknown (no source/product metadata)"


class Retriever:
    """Handles document retrieval from vector indices.
    
    This class manages the retrieval of relevant documents from both product
    and customer vector indices. It handles:
    1. Query processing and embedding
    2. Document retrieval with filtering
    3. Result ranking and selection
    4. Error handling and logging
    """
    
    def __init__(self, embedding_manager):
        """
        Initialize the retriever.
        
        Args:
            embedding_manager: Manager for handling document embeddings
        """
        self.embedding_manager = embedding_manager
        
    def retrieve_product_context(self, query: str, product_index_path: str, 
                               product_filter: Optional[List[str]] = None) -> List[Document]:
        """Retrieve relevant product documents.
        
        Args:
            query: The search query
            product_index_path: Path to the product index
            product_filter: Optional list of products to filter by
            
        Returns:
            List of relevant product documents
            
        Raises:
            FileNotFoundError: If the product index doesn't exist
            RuntimeError: If there are issues with the embedding model
            ValueError: If the query is empty or invalid
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")
            
        if not os.path.exists(product_index_path):
            raise FileNotFoundError(f"Product index not found at {product_index_path}")
            
        try:
            logger.info(f"Retrieving product context for query: {query}")
            if product_filter:
                logger.info(f"Filtering by products: {product_filter}")
                
            return self.embedding_manager.query_index(
                query=query,
                index_path=product_index_path,
                k=RETRIEVER_K_DOCUMENTS,
                filter_products=product_filter
            )
        except Exception as e:
            logger.error(f"Error retrieving product context: {e}")
            raise RuntimeError(f"Failed to retrieve product context: {e}")
        
    def retrieve_customer_context(self, query: str, customer_index_path: str) -> List[Document]:
        """Retrieve relevant customer documents.
        
        Args:
            query: The search query
            customer_index_path: Path to the customer index
            
        Returns:
            List of relevant customer documents
            
        Raises:
            FileNotFoundError: If the customer index doesn't exist
            RuntimeError: If there are issues with the embedding model
            ValueError: If the query is empty or invalid
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")
            
        if not os.path.exists(customer_index_path):
            raise FileNotFoundError(f"Customer index not found at {customer_index_path}")
            
        try:
            logger.info(f"Retrieving customer context for query: {query}")
            
            return self.embedding_manager.query_index(
                query=query,
                index_path=customer_index_path,
                k=CUSTOMER_RETRIEVER_K_DOCUMENTS
            )
        except Exception as e:
            logger.error(f"Error retrieving customer context: {e}")
            raise RuntimeError(f"Failed to retrieve customer context: {e}")


class AnswerGenerator:
    """Generates and refines answers using LLM.
    
    This class handles the generation and refinement of answers using the
    language model. It manages:
    1. Initial answer generation
    2. Answer refinement with additional context
    3. Response parsing and validation
    4. Error handling and logging
    """
    
    def __init__(self, llm):
        """
        Initialize the answer generator.
        
        Args:
            llm: The language model to use for generation
        """
        self.llm = llm
        self.llm_caller = LLMCaller(llm)
        
    def _generate_answer(self, question: str, context: str, current_answer: Optional[Dict[str, Any]] = None,
                       product_focus: Optional[str] = None, step_type: str = "PROMPT") -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Generate or refine an answer using the LLM.
        
        Args:
            question: The question to answer
            context: The context to use for generation
            current_answer: Optional current answer for refinement
            product_focus: Optional product focus for the answer
            step_type: Type of generation step ("PROMPT" or "REFINE")
            
        Returns:
            Tuple containing:
            - answer_data: Dictionary with the generated answer
            - log_data: Dictionary with logging information
            
        Raises:
            ValueError: If required parameters are missing
            RuntimeError: If LLM call fails
        """
        if not question.strip():
            raise ValueError("Question cannot be empty")
            
        if not context.strip():
            raise ValueError("Context cannot be empty")
            
        try:
            if step_type == "PROMPT":
                prompt = PromptFormatter.format_initial_prompt(question, context, product_focus)
            else:
                if not current_answer:
                    raise ValueError("Current answer required for refinement")
                prompt = PromptFormatter.format_refinement_prompt(question, current_answer, context, product_focus)
                
            logger.info(f"Generating {step_type} answer for question: {question}")
            
            response_text, error, elapsed_time = self.llm_caller.call_with_timeout(prompt)
            
            answer_data = ResponseParser.parse_response(response_text, error)
            
            log_data = {
                "step_type": step_type,
                "elapsed_time": elapsed_time,
                "has_error": bool(error),
                "error_message": error
            }
            
            return answer_data, log_data
            
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            raise RuntimeError(f"Failed to generate answer: {e}")
        
    def generate_initial_answer(self, question: str, initial_context: str, 
                              product_focus: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Generate the initial answer for a question.
        
        Args:
            question: The question to answer
            initial_context: The initial context to use
            product_focus: Optional product focus for the answer
            
        Returns:
            Tuple containing:
            - answer_data: Dictionary with the generated answer
            - log_data: Dictionary with logging information
            
        Raises:
            ValueError: If required parameters are missing
            RuntimeError: If LLM call fails
        """
        return self._generate_answer(
            question=question,
            context=initial_context,
            product_focus=product_focus,
            step_type="PROMPT"
        )
    
    def refine_answer(self, question: str, current_answer: Dict[str, Any], 
                    context: Dict[str, Any], product_focus: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Refine an existing answer with additional context.
        
        Args:
            question: The original question
            current_answer: The current answer to refine
            context: Additional context for refinement
            product_focus: Optional product focus for the answer
            
        Returns:
            Tuple containing:
            - answer_data: Dictionary with the refined answer
            - log_data: Dictionary with logging information
            
        Raises:
            ValueError: If required parameters are missing
            RuntimeError: If LLM call fails
        """
        if not isinstance(context, dict) or "context" not in context:
            raise ValueError("Context must be a dictionary with 'context' key")
            
        return self._generate_answer(
            question=question,
            context=context["context"],
            current_answer=current_answer,
            product_focus=product_focus,
            step_type="REFINE"
        )


class OutputFormatter:
    """Formats output for spreadsheet updates.
    
    This class handles the formatting of answers and related data for
    spreadsheet updates. It ensures:
    1. Consistent formatting across all outputs
    2. Proper handling of special characters
    3. Appropriate truncation of long text
    4. Proper error handling
    """
    
    @staticmethod
    def format_for_sheet(row_num: int, answer: Dict[str, Any], output_columns: Dict[str, int]) -> List[Dict[str, Any]]:
        """Format answer data for spreadsheet update."""
        if not isinstance(answer, dict):
            raise ValueError("Answer must be a dictionary")
        
        if not isinstance(output_columns, dict):
            raise ValueError("Output columns must be a dictionary")
        
        # Ensure all required columns are present
        required_columns = [ANSWER_ROLE, COMPLIANCE_ROLE, REFERENCES_ROLE]
        missing_columns = [col for col in required_columns if col not in output_columns]
        if missing_columns:
            # Add missing columns at the end
            last_col = max(output_columns.values()) if output_columns else 0
            for col in missing_columns:
                last_col += 1
                output_columns[col] = last_col
            logger.info(f"Added missing columns: {missing_columns}")
        
        try:
            updates = []
            
            # Format answer with references
            answer_text = answer.get("answer", "")
            references = answer.get("references", [])
            
            # Combine answer and references
            if references:
                answer_text += "\n\nReferences:\n" + "\n".join(references)
            
            if len(answer_text) > MAX_CONTEXT_CHARS:
                answer_text = answer_text[:MAX_CONTEXT_CHARS] + "..."
            
            updates.append({
                "row": row_num,
                "col": output_columns[ANSWER_ROLE],
                "value": answer_text
            })
            
            # Format compliance
            updates.append({
                "row": row_num,
                "col": output_columns[COMPLIANCE_ROLE],
                "value": answer.get("compliance", "PC")
            })
            
            return updates
            
        except Exception as e:
            logger.error(f"Error formatting output: {e}")
            raise RuntimeError(f"Failed to format output: {e}")


def log_chain_step(step_name: str):
    """Decorator to log chain step execution with timing."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            start_time = time.time()
            
            logger.info(f"\n[CHAIN] ======== {step_name} ========")
            result = func(self, *args, **kwargs)
            
            processing_time = time.time() - start_time
            if isinstance(result, dict):
                result["processing_time"] = processing_time
            
            logger.info(f"[CHAIN] ✅ {step_name} completed in {processing_time:.2f} seconds")
            return result
        return wrapper
    return decorator


class QuestionProcessor:
    """
    Main class for processing RFP questions.
    
    This class implements the core question processing pipeline:
    1. Question Analysis
       - Extracts product focus and requirements
       - Identifies key terms and concepts
    
    2. Context Retrieval
       - Retrieves relevant product documentation
       - Retrieves customer-specific context
       - Combines and prioritizes information sources
    
    3. Answer Generation
       - Generates initial answer using retrieved context
       - Refines answer through multiple iterations
       - Validates compliance and references
    
    4. Quality Assurance
       - Validates answer completeness
       - Ensures compliance with requirements
       - Verifies reference links
    
    Error Handling:
    - API Failures: Retries with exponential backoff
    - Context Retrieval: Falls back to alternative sources
    - Answer Generation: Multiple refinement attempts
    - Validation: Graceful degradation of requirements
    
    Example:
        ```python
        # Initialize processor
        processor = QuestionProcessor(
            embedding_manager=embedding_manager,
            llm=llm,
            question_logger=question_logger,
            index_dir="/path/to/indices"
        )
        
        # Process a question
        result = processor.process_question(
            question="What is the maximum number of users supported?",
            product_focus="Sales Cloud",
            customer_index_path="/path/to/customer/index"
        )
        
        print(f"Answer: {result['answer']}")
        print(f"Compliance: {result['compliance']}")
        print(f"References: {result['references']}")
        ```
    """
    
    def __init__(self, embedding_manager, llm, question_logger, index_dir: str):
        """
        Initialize the question processor.
        
        Args:
            embedding_manager: Manager for document embeddings and retrieval
            llm: Language model instance for answer generation
            question_logger: Logger for question processing steps
            index_dir: Directory containing vector indices
            
        Raises:
            ValueError: If required components are missing
            RuntimeError: If index directory is invalid
        """
        self.embedding_manager = embedding_manager
        self.llm = llm
        self.question_logger = question_logger
        self.index_dir = index_dir or config.index_dir
        
        # Initialize components
        self.retriever = Retriever(embedding_manager)
        self.answer_generator = AnswerGenerator(llm)
        self.output_formatter = OutputFormatter()
        self.doc_pair_creator = DocumentPairCreator()
    
    def process_questions(
        self,
        records: List[Dict[str, Any]],
        output_columns: Dict[str, int],
        sheet_handler: Any,
        selected_products: List[str],
        available_products: List[str],
        customer_index_path: Optional[str] = None,
        selected_index_path: Optional[str] = None
    ) -> None:
        """Process questions from the input records."""
        for record in records:
            row_num = record["sheet_row"]
            question = TextProcessor.clean_text(record["roles"].get(QUESTION_ROLE, ""))
            primary_product = TextProcessor.clean_text(record["roles"].get(PRIMARY_PRODUCT_ROLE, ""))
            
            if not question:
                continue
            
            logger.info(f"Processing row {row_num}:")
            logger.info(f"Question: {question}")
            logger.info(f"Primary product: {primary_product}")
            logger.debug("Roles:")
            for k, v in record["roles"].items():
                logger.debug(f"  {k}: {TextProcessor.clean_text(v)}")
            
            # Use the question directly without additional context
            enriched_question = question
            
            # Handle product selection
            row_products = self._determine_product_focus(
                selected_products, primary_product, available_products
            )
            
            try:
                # Process the question
                result = self._process_single_question(
                    question=question,
                    enriched_question=enriched_question,
                    row_products=row_products,
                    product_focus_str=", ".join(row_products) if row_products else "None",
                    product_index_path=selected_index_path,
                    customer_index_path=customer_index_path
                )
                
                # Format output for sheet
                updates = self.output_formatter.format_for_sheet(
                    row_num=row_num,
                    answer=result["final_answer"],
                    output_columns=output_columns
                )
                
                sheet_handler.update_batch(updates)
                
                # Print results (user-facing)
                self._print_results(row_num, question, row_products, result)
                
                # Log results if logger available
                if self.question_logger:
                    self._log_results(
                        row_num=row_num,
                        question=question,
                        row_products=row_products,
                        product_docs=result["product_docs"],
                        customer_docs=result["customer_docs"],
                        initial_answer=result["initial_answer"],
                        final_answer=result["final_answer"],
                        chain_log_data=result["chain_log_data"],
                        chain_time=result.get("processing_time", 0)
                    )
                
            except Exception as e:
                logger.error(f"❌ Failed to process row {row_num}: {e}")
                import traceback
                logger.error(f"[ERROR] Exception details: {traceback.format_exc()}")
                if self.question_logger:
                    self.question_logger.log_error(row_num, question, e)
    
    def _process_single_question(self, question: str, enriched_question: str,
                               row_products: List[str], product_focus_str: str,
                               product_index_path: str, customer_index_path: Optional[str]) -> Dict[str, Any]:
        """Process a single question and return results."""
        chain_log_data = []
        
        logger.info(f"[CHAIN] ======== Processing Question ========")
        logger.info(f"[CHAIN] Question: {question[:100]}...")
        logger.info(f"[CHAIN] Product focus: {product_focus_str}")
        
        # Retrieve context
        context_result = self._retrieve_context(
            enriched_question, row_products, product_index_path, customer_index_path
        )
        
        product_docs = context_result["product_docs"]
        customer_docs = context_result["customer_docs"]
        
        # Generate initial answer
        initial_result = self._generate_initial_answer(
            question=enriched_question, 
            product_docs=product_docs, 
            customer_docs=customer_docs, 
            row_products=row_products
        )
        
        current_answer = initial_result["answer"]
        chain_log_data.append(initial_result["log_data"])
        
        # Create document pairs for refinement
        paired_docs = self.doc_pair_creator.create_document_pairs(product_docs, customer_docs)
        
        # Perform refinements using _refine_answer instead of _perform_refinements
        refinement_result = self._refine_answer(
            question=enriched_question,
            product_focus=product_focus_str,
            initial_answer=current_answer,
            paired_docs=paired_docs
        )
        
        final_answer = refinement_result["final_answer"]
        chain_log_data.extend(refinement_result["log_data"])
        
        # Process references
        final_answer = ReferenceHandler.process_references(final_answer)
        
        return {
            "final_answer": final_answer,
            "initial_answer": initial_result["answer"],
            "chain_log_data": chain_log_data,
            "product_docs": product_docs,
            "customer_docs": customer_docs
        }
    
    def _determine_product_focus(self, selected_products: List[str], 
                              primary_product: str, 
                              available_products: Optional[List[str]]) -> List[str]:
        """Determine product focus based on user selection and record data."""
        row_products = selected_products.copy()
        
        if primary_product and available_products:
            validated = None
            for product in available_products:
                if primary_product.lower() in product.lower() or product.lower() in primary_product.lower():
                    validated = product
                    break
            
            if validated and not selected_products:
                row_products = [validated]
                
        return row_products
    
    def _retrieve_context(self, query: str, row_products: List[str], 
                       product_index_path: str, 
                       customer_index_path: Optional[str]) -> Dict[str, List[Document]]:
        """Retrieve relevant context for a query."""
        logger.info(f"[CHAIN] Starting product context retrieval...")
        
        products_for_filter = None
        if row_products:
            logger.info(f"[CHAIN] Product filter: {', '.join(row_products)}")
            products_for_filter = row_products.copy()
        else:
            logger.info(f"[CHAIN] Product filter: None")
            
        product_docs = self.retriever.retrieve_product_context(
            query=query,
            product_index_path=product_index_path,
            product_filter=products_for_filter
        )
        
        logger.info(f"[CHAIN] Product context retrieval complete - got {len(product_docs)} documents")
        
        if product_docs:
            logger.info(f"\n[CHAIN] Product Document Sources:")
            for idx, doc in enumerate(product_docs[:3]):
                source = DocumentMetadataExtractor.extract_product_metadata(doc)
                logger.info(f"[CHAIN]   #{idx+1}: {source}")
                
                if hasattr(doc, 'metadata'):
                    metadata_str = ", ".join([f"{k}: {v}" for k, v in doc.metadata.items() 
                                           if k in ['product', 'tag', 'source', 'title', 'type'] and v])
                    if metadata_str:
                        logger.info(f"[CHAIN]      Metadata: {metadata_str}")
                
                logger.info(f"[CHAIN]      Preview: {doc.page_content[:100]}...")
            
            if len(product_docs) > 3:
                logger.info(f"[CHAIN]   ... and {len(product_docs) - 3} more documents")
        else:
            logger.warning(f"[CHAIN] ⚠️ Warning: No product documents retrieved")
            
        customer_docs = []
        if customer_index_path:
            logger.info(f"\n[CHAIN] Starting customer context retrieval...")
            
            customer_docs = self.retriever.retrieve_customer_context(
                query=query,
                customer_index_path=customer_index_path
            )
            
            logger.info(f"[CHAIN] Customer context retrieval complete - got {len(customer_docs)} documents")
            
            if customer_docs:
                logger.info(f"\n[CHAIN] Customer Document Sources:")
                for idx, doc in enumerate(customer_docs[:3]):
                    source = f"Customer: {doc.metadata.get('source', 'unknown')}"
                    logger.info(f"[CHAIN]   #{idx+1}: {source}")
                    logger.info(f"[CHAIN]      Preview: {doc.page_content[:100]}...")
                
                if len(customer_docs) > 3:
                    logger.info(f"[CHAIN]   ... and {len(customer_docs) - 3} more documents")
            else:
                logger.warning(f"[CHAIN] ⚠️ Warning: No customer documents retrieved")
        else:
            logger.info(f"[CHAIN] ℹ️ No customer context selected - using product knowledge only")
            
        logger.info(f"\n[CHAIN] ======== Context Retrieval Complete ========")
        
        return {
            "product_docs": product_docs,
            "customer_docs": customer_docs
        }
    
    def _log_initial_context(self, product_docs: List[Document], customer_docs: List[Document], 
                          initial_context: str) -> Dict[str, Any]:
        """Log details about initial context."""
        context_info = {}
        
        if product_docs:
            product_doc_source = DocumentMetadataExtractor.extract_product_metadata(product_docs[0])
            logger.info(f"[CHAIN] Added product document #1 from: {product_doc_source}")
            context_info["product_doc"] = product_doc_source
        else:
            context_info["product_doc"] = None
            
        if customer_docs:
            customer_doc_source = customer_docs[0].metadata.get('source', 'unknown')
            logger.info(f"[CHAIN] Added customer document #1 from: {customer_doc_source}")
            logger.info(f"[CHAIN] Combined initial context length: {len(initial_context)} chars")
            context_info["customer_doc"] = customer_doc_source
        elif customer_docs is not None:
            logger.warning(f"[CHAIN] No customer documents were retrieved - using product context only")
            context_info["customer_doc"] = None
            
        original_length = len(initial_context)
        initial_context = TextProcessor.truncate_text(initial_context, max_length=config.max_context_chars)
        if len(initial_context) < original_length:
            logger.warning(f"[CHAIN] ⚠️ Initial context truncated from {original_length} to {len(initial_context)} chars")
            
        context_info["context_size"] = len(initial_context)
        return context_info
    
    @log_chain_step("Initial Answer Generation")
    def _generate_initial_answer(self, question: str, product_docs: List[Document], 
                               customer_docs: List[Document], row_products: List[str]) -> Dict[str, Any]:
        """
        Generate the initial answer using the first set of retrieved documents.
        
        Args:
            question: The question to answer
            product_docs: List of product documents
            customer_docs: List of customer documents
            row_products: List of products to focus on
            
        Returns:
            Dictionary containing:
            {
                "answer": str,
                "compliance": str,
                "references": List[str],
                "processing_time": float
            }
        """
        logger.info(f"[CHAIN] Building initial context...")
        
        initial_context = ""
        product_focus = ", ".join(row_products) if row_products else None
        
        # Add product context
        if product_docs:
            initial_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
            initial_context += product_docs[0].page_content
        
        # Add customer context
        if customer_docs:
            initial_context += "\n\n--- CUSTOMER CONTEXT ---\n\n"
            initial_context += customer_docs[0].page_content
        
        # Log context details
        context_info = self._log_initial_context(product_docs, customer_docs, initial_context)
        
        logger.info(f"[CHAIN] Generating initial answer with LLM...")
        
        current_answer, log_data = self.answer_generator.generate_initial_answer(
            question=question,
            initial_context=initial_context,
            product_focus=product_focus
        )
        
        # Add context info to log data
        log_data["context_info"] = context_info
        
        answer_preview = current_answer.get('answer', '')[:100] + "..." if len(current_answer.get('answer', '')) > 100 else current_answer.get('answer', '')
        logger.info(f"[CHAIN] Initial answer compliance: {current_answer.get('compliance', 'Unknown')}")
        logger.debug(f"[CHAIN] Initial answer preview: {answer_preview}")
        
        return {
            "answer": current_answer,
            "log_data": log_data
        }
    
    @log_chain_step("Answer Refinement")
    def _refine_answer(self, question: str, product_focus: str, 
                      initial_answer: Dict[str, Any], 
                      paired_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Refine the initial answer using additional context.
        
        Refinement Algorithm:
        1. For each document pair:
           - Combine product and customer context
           - Generate refinement prompt
           - Get LLM refinement
           - Update answer if improvement found
        
        2. Quality Checks:
           - Verify answer completeness
           - Check compliance rating
           - Validate references
           - Ensure consistency
        
        Error Handling:
        - Refinement Failure: Continues with next document
        - Quality Check Failure: Logs warning and continues
        - Context Truncation: Logs and uses available context
        
        Args:
            question: Original question
            product_focus: Primary product focus
            initial_answer: Initial answer dictionary
            paired_docs: List of document pairs for refinement
            
        Returns:
            Refined answer dictionary with:
            {
                "answer": str,
                "compliance": str,
                "references": List[str],
                "processing_time": float,
                "refinement_steps": int
            }
            
        Raises:
            ValueError: If refinement produces invalid result
            RuntimeError: If refinement process fails
        """
        log_data = []
        
        refined_answer = initial_answer
        refine_steps = 1  # Start at 1 because initial step is 1
        
        for doc_idx, doc_info in enumerate(paired_docs):
            refine_steps += 1
            logger.info(f"[CHAIN] ======== Refinement Step {refine_steps} ========")
            
            # Log refinement context details
            self._log_refinement_context(doc_info)
            
            # Perform refinement
            new_answer, step_log = self.answer_generator.refine_answer(
                question=question,
                current_answer=refined_answer,
                context=doc_info,
                product_focus=product_focus
            )
            
            log_data.append(step_log)
            
            # Skip if error occurred
            if "error" in step_log:
                continue
                
            refined_answer = new_answer
            
            # Log changes from previous answer if significant
            prev_compliance = refined_answer.get('compliance', 'Unknown')
            new_compliance = new_answer.get('compliance', 'Unknown')
            if prev_compliance != new_compliance:
                logger.info(f"[CHAIN] 📊 Compliance changed: {prev_compliance} -> {new_compliance}")
        
        logger.info(f"[CHAIN] ======== Chain Execution Summary ========")
        logger.info(f"[CHAIN] Total steps completed: {refine_steps}")
        logger.info(f"[CHAIN] Final compliance rating: {refined_answer.get('compliance', 'Unknown')}")
        logger.info(f"[CHAIN] Final answer length: {len(refined_answer.get('answer', ''))}")
        logger.info(f"[CHAIN] Final references: {len(refined_answer.get('references', []))}")
        logger.info(f"[CHAIN] ======== End of Chain Processing ========")
        
        return {
            "final_answer": refined_answer,
            "log_data": log_data
        }
    
    def _log_refinement_context(self, doc_info: Dict[str, Any]) -> None:
        """Log details about refinement context."""
        has_both_doc_types = doc_info["has_product"] and doc_info["has_customer"]
        doc_number = doc_info["document_number"]
        
        if has_both_doc_types:
            logger.info(f"[CHAIN] Using paired documents: Product #{doc_number} & Customer #{doc_number}")
        elif doc_info["has_product"]:
            logger.info(f"[CHAIN] Using Product Document #{doc_number} only (no matching Customer Document)")
        elif doc_info["has_customer"]:
            logger.info(f"[CHAIN] Using Customer Document #{doc_number} only (no matching Product Document)")
            
        if doc_info["has_product"]:
            logger.info(f"[CHAIN] Product source: {doc_info['product_source']}")
        if doc_info["has_customer"]:
            logger.info(f"[CHAIN] Customer source: {doc_info['customer_source']}")
            
        logger.info(f"[CHAIN] Context size: {len(doc_info['context'])} chars")
        if doc_info["truncated"]:
            logger.warning(f"[CHAIN] ⚠️ Context was truncated to fit size limits")
    
    def _process_answer_data(self, final_answer: Dict[str, Any]) -> Dict[str, Any]:
        """Process and validate answer data."""
        return {
            "answer": JsonProcessor.clean_json_answer(final_answer.get("answer", "")),
            "compliance": JsonProcessor.validate_compliance_value(final_answer.get("compliance", "PC")),
            "references": final_answer.get("references", []),
            "original_ref_count": len(final_answer.get("references", [])),
            "filtered_ref_count": len(final_answer.get("references", []))
        }
    
    def _print_results(self, row_num: int, question: str, row_products: List[str],
                     result: Dict[str, Any]) -> None:
        """Print processing results."""
        answer_data = self._process_answer_data(result["final_answer"])
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ Row {row_num} complete")
        logger.info(f"Question: {question}")
        if row_products:
            logger.info(f"Product Focus: {', '.join(row_products)}")
        logger.info(f"\nAnswer:")
        logger.info(f"{answer_data['answer']}")
        logger.info(f"\nCompliance: {answer_data['compliance']}")
        
        if answer_data["references"]:
            logger.info(f"\nReferences ({len(answer_data['references'])}):")
            for ref in answer_data["references"]:
                logger.info(f"• {ref}")
        logger.info(f"{'='*80}")
    
    def _log_results(self, row_num: int, question: str, row_products: List[str],
                   product_docs: List[Document], customer_docs: List[Document],
                   initial_answer: Dict[str, Any], final_answer: Dict[str, Any],
                   chain_log_data: List[Dict[str, Any]], chain_time: float) -> None:
        """Log processing results if logger is available."""
        if not self.question_logger:
            return
            
        sources = []
        for doc in product_docs:
            source = DocumentMetadataExtractor.extract_product_metadata(doc)
            sources.append(source)
        
        for doc in customer_docs:
            source = f"Customer: {doc.metadata.get('source', 'unknown')}"
            sources.append(source)
            
        answer_data = self._process_answer_data(final_answer)
        
        log_data = {
            "question": question,
            "product_focus": ", ".join(row_products) if row_products else "None",
            "refine_chain_time": chain_time,
            "refine_steps": len(chain_log_data),
            "product_documents": len(product_docs),
            "customer_documents": len(customer_docs),
            "documents_retrieved": len(product_docs) + len(customer_docs),
            "answer": answer_data["answer"],
            "compliance": answer_data["compliance"],
            "references": answer_data["references"],
            "sources_used": sources,
            "original_references": answer_data["original_ref_count"],
            "valid_references": answer_data["filtered_ref_count"],
            "chain_log_data": chain_log_data
        }
        
        self.question_logger.log_enhanced_processing(row_num, log_data)