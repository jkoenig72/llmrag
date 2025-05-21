import logging
import time
import json
import copy
import re  # Make sure re is imported
import unicodedata  # Make sure unicodedata is imported
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
from langchain.schema import Document

from config import get_config

# Get configuration at module initialization
config = get_config()
QUESTION_ROLE = config.question_role
CONTEXT_ROLE = config.context_role
ANSWER_ROLE = config.answer_role
COMPLIANCE_ROLE = config.compliance_role
REFERENCES_ROLE = config.references_role
BATCH_SIZE = config.batch_size
API_THROTTLE_DELAY = config.api_throttle_delay
PRIMARY_PRODUCT_ROLE = config.primary_product_role
RETRIEVER_K_DOCUMENTS = config.retriever_k_documents
CUSTOMER_RETRIEVER_K_DOCUMENTS = config.customer_retriever_k_documents
MAX_CONTEXT_CHARS = config.max_context_chars
LLM_REQUEST_TIMEOUT = config.llm_request_timeout

from llm_utils import JsonProcessor
from prompts import PromptManager
from reference_handler import ReferenceHandler
from index_selector import IndexSelector

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
    """Handles calling LLMs with proper timeout handling."""
    
    def __init__(self, llm):
        self.llm = llm
        
    def call_with_timeout(self, prompt: str, timeout: int = LLM_REQUEST_TIMEOUT) -> Tuple[Optional[str], Optional[str]]:
        """Call LLM with timeout handling.
        
        Returns:
            Tuple of (response, error_message)
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
                return None, "Timeout", timeout
            except Exception as e:
                return None, str(e), 0


class ResponseParser:
    """Parses and validates LLM responses."""
    
    @staticmethod
    def parse_response(response_text: Optional[str], error: Optional[str] = None) -> Dict[str, Any]:
        """Parse LLM response text into structured format."""
        if error:
            # Create default response for error case
            return {
                "answer": f"Error generating response: {error}",
                "compliance": "NC",
                "references": []
            }
            
        if not response_text:
            return {
                "answer": "No response received from language model.",
                "compliance": "NC",
                "references": []
            }
            
        try:
            # Try to parse as JSON
            parsed_json = json.loads(response_text)
            # Validate required fields
            if "answer" in parsed_json and "compliance" in parsed_json:
                if "references" not in parsed_json:
                    parsed_json["references"] = []
                return parsed_json
        except json.JSONDecodeError:
            pass
            
        # Fallback to extraction
        return JsonProcessor.extract_json_from_llm_response(response_text)


class DocumentPairCreator:
    """Creates document pairs for refinement steps."""
    
    @staticmethod
    def create_document_pairs(product_docs: List[Document], customer_docs: List[Document]) -> List[Dict[str, Any]]:
        """Create document pairs for refinement, pairing product and customer docs."""
        remaining_product_docs = product_docs[1:] if product_docs else []
        remaining_customer_docs = customer_docs[1:] if customer_docs else []
        
        paired_docs = []
        
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
            refinement_context = TextProcessor.truncate_context(refinement_context)
            
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
    """Extracts and processes document metadata."""
    
    @staticmethod
    def extract_product_metadata(doc: Document) -> str:
        """Extract product metadata from a document."""
        if not hasattr(doc, 'metadata'):
            return "unknown (no metadata)"
        
        metadata = doc.metadata
        
        if 'source' in metadata and metadata['source']:
            return metadata['source']
        
        if 'product' in metadata and metadata['product']:
            return f"Product: {metadata['product']}"
        
        if 'tag' in metadata and metadata['tag']:
            return f"Tag: {metadata['tag']}"
        
        for key in ['title', 'name', 'document_type', 'category', 'type']:
            if key in metadata and metadata[key]:
                return f"{key.capitalize()}: {metadata[key]}"
        
        if metadata:
            for key, value in metadata.items():
                if value and isinstance(value, str) and key != 'page_content':
                    return f"{key}: {value}"
        
        return "unknown (no recognized metadata)"


class TextProcessor:
    """Processes and formats text content."""
    
    @staticmethod
    def truncate_context(context: str, max_chars: int = MAX_CONTEXT_CHARS) -> str:
        """Truncate context to fit within max characters, trying to break at natural boundaries."""
        if len(context) <= max_chars:
            return context
        
        for sep in ["\n\n", "\n", ". ", " "]:
            boundary = context[:max_chars].rfind(sep)
            if boundary > max_chars * 0.8:
                return context[:boundary + len(sep)]
        
        return context[:max_chars]


class Retriever:
    """Handles retrieval of relevant context from vector stores."""
    
    def __init__(self, embedding_manager):
        self.embedding_manager = embedding_manager
        
    def retrieve_product_context(self, query: str, product_index_path: str, 
                               product_filter: Optional[List[str]] = None) -> List[Document]:
        """Retrieve relevant product context for a query."""
        return self.embedding_manager.query_index(
            index_path=product_index_path,
            query=query,
            k=RETRIEVER_K_DOCUMENTS,
            use_cpu=False,
            db_name="Products DB",
            filter_products=product_filter
        )
        
    def retrieve_customer_context(self, query: str, customer_index_path: str) -> List[Document]:
        """Retrieve relevant customer context for a query."""
        if not customer_index_path:
            return []
            
        try:
            return self.embedding_manager.query_index(
                index_path=customer_index_path,
                query=query,
                k=CUSTOMER_RETRIEVER_K_DOCUMENTS,
                use_cpu=False,
                db_name="Customer DB"
            )
        except Exception as e:
            logger.error(f"Error retrieving customer documents: {e}")
            return []


class AnswerGenerator:
    """Generates answers using LLM based on retrieved context."""
    
    def __init__(self, llm):
        self.llm = llm
        self.llm_caller = LLMCaller(llm)
        self.prompt_formatter = PromptFormatter()
        self.response_parser = ResponseParser()
    
    def generate_initial_answer(self, question: str, initial_context: str, 
                              product_focus: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Generate the initial answer using the first documents."""
        prompt = self.prompt_formatter.format_initial_prompt(
            question=question,
            context=initial_context,
            product_focus=product_focus
        )
        
        response_text, error, processing_time = self.llm_caller.call_with_timeout(prompt)
        
        log_data = {
            "step_type": "PROMPT",
            "prompt": prompt,
            "raw_response": response_text if response_text else f"Error: {error}",
            "processing_time": processing_time
        }
        
        parsed_answer = self.response_parser.parse_response(response_text, error)
        log_data["parsed_answer"] = parsed_answer
        
        return parsed_answer, log_data
        
    def refine_answer(self, question: str, current_answer: Dict[str, Any], 
                    context: Dict[str, Any], product_focus: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Refine an answer with additional context."""
        prompt = self.prompt_formatter.format_refinement_prompt(
            question=question,
            current_answer=current_answer,
            context=context["context"],
            product_focus=product_focus
        )
        
        context_info = {
            "product_doc": context["product_source"] if context["has_product"] else None,
            "customer_doc": context["customer_source"] if context["has_customer"] else None,
            "context_size": len(context["context"]),
            "document_number": context["document_number"],
            "truncated": context["truncated"]
        }
        
        response_text, error, processing_time = self.llm_caller.call_with_timeout(prompt)
        
        log_data = {
            "step_type": "REFINE",
            "step_number": context["document_number"] - 1,  # -1 because first doc is step 1
            "context_info": context_info,
            "prompt": prompt,
            "raw_response": response_text if response_text else f"Error: {error}",
            "processing_time": processing_time
        }
        
        if error:
            log_data["error"] = error
            return current_answer, log_data
            
        parsed_answer = self.response_parser.parse_response(response_text, error)
        log_data["parsed_answer"] = parsed_answer
        
        return parsed_answer, log_data


class OutputFormatter:
    """Formats processed answers for output."""
    
    @staticmethod
    def format_for_sheet(row_num: int, answer: Dict[str, Any], output_columns: Dict[str, int]) -> List[Dict[str, Any]]:
        """Format answer for Google Sheet updates."""
        batch_updates = []
        
        answer_text = JsonProcessor.clean_json_answer(answer.get("answer", ""))
        compliance = JsonProcessor.validate_compliance_value(answer.get("compliance", "PC"))
        references = answer.get("references", [])
        
        combined_text = answer_text
        if references:
            references_text = "\n\nReferences:\n" + "\n".join(references)
            combined_text += references_text
        
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
            
        return batch_updates


class QuestionProcessor:
    """Main class for processing RFP questions."""
    
    def __init__(self, embedding_manager, llm, question_logger=None, index_dir=None):
        self.embedding_manager = embedding_manager
        self.llm = llm
        self.question_logger = question_logger
        self.index_dir = index_dir or config.index_dir
        
        # Initialize components
        self.retriever = Retriever(embedding_manager)
        self.answer_generator = AnswerGenerator(llm)
        self.output_formatter = OutputFormatter()
        self.doc_pair_creator = DocumentPairCreator()
    
    @staticmethod
    def clean_text(raw_text: str) -> str:
        """
        Clean and normalize text by removing special characters and normalizing whitespace.
        
        Args:
            raw_text: The text to clean
            
        Returns:
            Cleaned and normalized text
        """
        if not raw_text:
            return ""
            
        original = raw_text

        clean = raw_text.strip()
        clean = re.sub(r'[\u2022\u2023\u25E6\u2043\u2219\-\*]+', ',', clean)
        clean = re.sub(r'\s+', ' ', clean)

        clean = unicodedata.normalize('NFKD', clean).encode('ascii', 'ignore').decode()

        clean = ''.join(c for c in clean if c.isprintable())

        clean = re.sub(r'[!?.,]{2,}', lambda m: m.group(0)[0], clean)

        clean = re.sub(r'[^\w\s,.!?]', '', clean)

        logger.debug("Cleaned text (first 100 chars):\nBefore: %s\nAfter: %s", original[:100], clean[:100])
        return clean
    
    def process_questions(self, records: List[Dict[str, Any]], qa_chain, 
                        output_columns: Dict[str, int], sheet_handler, 
                        selected_products: Optional[List[str]] = None, 
                        available_products: Optional[List[str]] = None, 
                        customer_index_path: Optional[str] = None) -> None:
        """Process a batch of RFP questions."""
        batch_updates = []
        
        product_index_path = IndexSelector.select_index_for_products(self.index_dir, selected_products)
        IndexSelector.print_index_selection_info(self.index_dir, selected_products, product_index_path)
        
        product_focus_str = ", ".join(selected_products) if selected_products else "None"
        user_selected_products = selected_products.copy() if selected_products else []
        
        for i, record in enumerate(records):
            row_num = record["sheet_row"]
            question = self.clean_text(record["roles"].get(QUESTION_ROLE, ""))
            primary_product = self.clean_text(record["roles"].get(PRIMARY_PRODUCT_ROLE, ""))
            
            if not question:
                logger.warning(f"Row {row_num} skipped: No question found.")
                continue
                
            # Process additional context
            additional_context = "\n".join([
                f"{k}: {self.clean_text(v)}" for k, v in record["roles"].items()
                if k.strip().lower() == CONTEXT_ROLE and v.strip()
            ]).strip() or "N/A"
            
            enriched_question = f"{question}\n\n[Additional Info]\n{additional_context}"
            
            # Handle product selection
            row_products = self._determine_product_focus(
                user_selected_products, primary_product, available_products
            )
            
            try:
                # Process the question
                result = self._process_single_question(
                    row_num=row_num,
                    question=question,
                    enriched_question=enriched_question,
                    row_products=row_products,
                    product_focus_str=product_focus_str,
                    product_index_path=product_index_path,
                    customer_index_path=customer_index_path,
                    qa_chain=qa_chain
                )
                
                # Format output for sheet
                updates = self.output_formatter.format_for_sheet(
                    row_num=row_num,
                    answer=result["final_answer"],
                    output_columns=output_columns
                )
                
                batch_updates.extend(updates)
                
                # Handle batch updates
                if len(batch_updates) >= BATCH_SIZE or i == len(records) - 1:
                    sheet_handler.update_batch(batch_updates)
                    batch_updates = []
                    time.sleep(API_THROTTLE_DELAY)
                    
                # Print results
                self._print_results(row_num, question, row_products, result)
                
            except Exception as e:
                logger.error(f"❌ Failed to process row {row_num}: {e}")
                import traceback
                print(f"[ERROR] Exception details: {traceback.format_exc()}")
                if self.question_logger:
                    self.question_logger.log_error(row_num, question, e)
    
    def _process_single_question(self, row_num: int, question: str, enriched_question: str,
                               row_products: List[str], product_focus_str: str,
                               product_index_path: str, customer_index_path: Optional[str],
                               qa_chain) -> Dict[str, Any]:
        """Process a single question and return results."""
        chain_log_data = []
        
        print(f"\n[CHAIN] ======== Processing Question for Row {row_num} ========")
        print(f"[CHAIN] Question: {question[:100]}...")
        print(f"[CHAIN] Product focus: {product_focus_str}")
        
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
        
        # Perform refinements
        refinement_result = self._perform_refinements(
            question=enriched_question,
            current_answer=current_answer,
            product_docs=product_docs,
            customer_docs=customer_docs,
            row_products=row_products
        )
        
        final_answer = refinement_result["final_answer"]
        chain_log_data.extend(refinement_result["log_data"])
        
        # Process references
        final_answer = ReferenceHandler.process_references(final_answer)
        
        # Log results if logger available
        if self.question_logger:
            self._log_results(
                row_num=row_num,
                question=question,
                row_products=row_products,
                product_docs=product_docs,
                customer_docs=customer_docs,
                initial_answer=initial_result["answer"],
                final_answer=final_answer,
                chain_log_data=chain_log_data,
                chain_time=refinement_result["total_time"]
            )
            
        return {
            "final_answer": final_answer,
            "initial_answer": initial_result["answer"],
            "chain_log_data": chain_log_data,
            "product_docs": product_docs,
            "customer_docs": customer_docs
        }
    
    def _determine_product_focus(self, user_selected_products: List[str], 
                              primary_product: str, 
                              available_products: Optional[List[str]]) -> List[str]:
        """Determine product focus based on user selection and record data."""
        row_products = user_selected_products.copy()
        
        if primary_product and available_products:
            validated = None
            for product in available_products:
                if primary_product.lower() in product.lower() or product.lower() in primary_product.lower():
                    validated = product
                    break
            
            if validated and not user_selected_products:
                row_products = [validated]
                
        return row_products
    
    def _retrieve_context(self, query: str, row_products: List[str], 
                       product_index_path: str, 
                       customer_index_path: Optional[str]) -> Dict[str, List[Document]]:
        """Retrieve relevant context for a query."""
        print(f"[CHAIN] Starting product context retrieval...")
        
        products_for_filter = None
        if row_products:
            print(f"[CHAIN] Product filter: {', '.join(row_products)}")
            products_for_filter = row_products.copy()
        else:
            print(f"[CHAIN] Product filter: None")
            
        product_docs = self.retriever.retrieve_product_context(
            query=query,
            product_index_path=product_index_path,
            product_filter=products_for_filter
        )
        
        print(f"[CHAIN] Product context retrieval complete - got {len(product_docs)} documents")
        
        if product_docs:
            print(f"\n[CHAIN] Product Document Sources:")
            for idx, doc in enumerate(product_docs[:3]):
                source = DocumentMetadataExtractor.extract_product_metadata(doc)
                print(f"[CHAIN]   #{idx+1}: {source}")
                
                if hasattr(doc, 'metadata'):
                    metadata_str = ", ".join([f"{k}: {v}" for k, v in doc.metadata.items() 
                                           if k in ['product', 'tag', 'source', 'title', 'type'] and v])
                    if metadata_str:
                        print(f"[CHAIN]      Metadata: {metadata_str}")
                
                print(f"[CHAIN]      Preview: {doc.page_content[:100]}...")
            
            if len(product_docs) > 3:
                print(f"[CHAIN]   ... and {len(product_docs) - 3} more documents")
        else:
            print(f"[CHAIN] ⚠️ Warning: No product documents retrieved")
            
        customer_docs = []
        if customer_index_path:
            print(f"\n[CHAIN] Starting customer context retrieval...")
            
            customer_docs = self.retriever.retrieve_customer_context(
                query=query,
                customer_index_path=customer_index_path
            )
            
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
        else:
            print(f"[CHAIN] ℹ️ No customer context selected - using product knowledge only")
            
        print(f"\n[CHAIN] ======== Context Retrieval Complete ========")
        
        return {
            "product_docs": product_docs,
            "customer_docs": customer_docs
        }
    
    def _generate_initial_answer(self, question: str, product_docs: List[Document],
                             customer_docs: List[Document], row_products: List[str]) -> Dict[str, Any]:
        """Generate initial answer using first documents."""
        start_time = time.time()
        
        print(f"\n[CHAIN] ======== Starting LLM Chain Processing ========")
        print(f"[CHAIN] Building initial context...")
        
        initial_context = ""
        
        product_doc_source = None
        if product_docs:
            initial_context += "\n\n--- PRODUCT CONTEXT ---\n\n"
            initial_context += product_docs[0].page_content
            product_doc_source = DocumentMetadataExtractor.extract_product_metadata(product_docs[0])
            print(f"[CHAIN] Added product document #1 from: {product_doc_source}")
        
        customer_doc_source = None
        if customer_docs:
            initial_context += "\n\n--- CUSTOMER CONTEXT ---\n\n"
            customer_content = customer_docs[0].page_content
            initial_context += customer_content
            customer_doc_source = customer_docs[0].metadata.get('source', 'unknown')
            print(f"[CHAIN] Added customer document #1 from: {customer_doc_source}")
            print(f"[CHAIN] Combined initial context length: {len(initial_context)} chars")
        elif customer_docs is not None:
            print(f"[CHAIN] No customer documents were retrieved - using product context only")
            
        original_length = len(initial_context)
        initial_context = TextProcessor.truncate_context(initial_context)
        if len(initial_context) < original_length:
            print(f"[CHAIN] ⚠️ Initial context truncated from {original_length} to {len(initial_context)} chars")
            
        product_focus = ", ".join(row_products) if row_products else None
        
        print(f"[CHAIN] Generating initial answer with LLM...")
        
        if customer_docs:
            log_msg = "[CHAIN] Initial step using Product Document #1 & Customer Document #1"
        else:
            log_msg = "[CHAIN] Initial step using Product Document #1 only"
        print(log_msg)
        
        current_answer, log_data = self.answer_generator.generate_initial_answer(
            question=question,
            initial_context=initial_context,
            product_focus=product_focus
        )
        
        # Add context info to log data
        log_data["context_info"] = {
            "product_doc": product_doc_source,
            "customer_doc": customer_doc_source,
            "context_size": len(initial_context)
        }
        
        print(f"[CHAIN] ✅ Initial answer generated")
        
        answer_preview = current_answer.get('answer', '')[:100] + "..." if len(current_answer.get('answer', '')) > 100 else current_answer.get('answer', '')
        print(f"[CHAIN] Initial answer compliance: {current_answer.get('compliance', 'Unknown')}")
        print(f"[CHAIN] Initial answer preview: {answer_preview}")
        
        processing_time = time.time() - start_time
        
        return {
            "answer": current_answer,
            "log_data": log_data,
            "processing_time": processing_time
        }
    
    def _perform_refinements(self, question: str, current_answer: Dict[str, Any],
                          product_docs: List[Document], customer_docs: List[Document],
                          row_products: List[str]) -> Dict[str, Any]:
        """Perform refinement steps with additional context."""
        start_time = time.time()
        log_data = []
        
        # Create document pairs for refinement
        paired_docs = self.doc_pair_creator.create_document_pairs(
            product_docs=product_docs,
            customer_docs=customer_docs
        )
        
        print(f"\n[CHAIN] Planning refinement steps...")
        print(f"[CHAIN] Created {len(paired_docs)} refinement steps")
        
        product_focus = ", ".join(row_products) if row_products else None
        refined_answer = current_answer
        refine_steps = 1  # Start at 1 because initial step is 1
        
        for doc_idx, doc_info in enumerate(paired_docs):
            refine_steps += 1
            print(f"\n[CHAIN] ======== Refinement Step {refine_steps} ========")
            
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
                print(f"[CHAIN] 📊 Compliance changed: {prev_compliance} -> {new_compliance}")
                
        total_time = time.time() - start_time
        
        print(f"\n[CHAIN] ======== Chain Execution Summary ========")
        print(f"[CHAIN] Total execution time: {total_time:.2f} seconds")
        print(f"[CHAIN] Total steps completed: {refine_steps}")
        print(f"[CHAIN] Final compliance rating: {refined_answer.get('compliance', 'Unknown')}")
        print(f"[CHAIN] Final answer length: {len(refined_answer.get('answer', ''))}")
        print(f"[CHAIN] Final references: {len(refined_answer.get('references', []))}")
        print(f"[CHAIN] ======== End of Chain Processing ========\n")
        
        return {
            "final_answer": refined_answer,
            "log_data": log_data,
            "total_time": total_time
        }
    
    def _log_refinement_context(self, doc_info: Dict[str, Any]) -> None:
        """Log details about refinement context."""
        has_both_doc_types = doc_info["has_product"] and doc_info["has_customer"]
        doc_number = doc_info["document_number"]
        
        if has_both_doc_types:
            print(f"[CHAIN] Using paired documents: Product #{doc_number} & Customer #{doc_number}")
        elif doc_info["has_product"]:
            print(f"[CHAIN] Using Product Document #{doc_number} only (no matching Customer Document)")
        elif doc_info["has_customer"]:
            print(f"[CHAIN] Using Customer Document #{doc_number} only (no matching Product Document)")
            
        if doc_info["has_product"]:
            print(f"[CHAIN] Product source: {doc_info['product_source']}")
        if doc_info["has_customer"]:
            print(f"[CHAIN] Customer source: {doc_info['customer_source']}")
            
        print(f"[CHAIN] Context size: {len(doc_info['context'])} chars")
        if doc_info["truncated"]:
            print(f"[CHAIN] ⚠️ Context was truncated to fit size limits")
    
    def _print_results(self, row_num: int, question: str, row_products: List[str],
                     result: Dict[str, Any]) -> None:
        """Print processing results."""
        final_answer = result["final_answer"]
        answer = JsonProcessor.clean_json_answer(final_answer.get("answer", ""))
        compliance = JsonProcessor.validate_compliance_value(final_answer.get("compliance", "PC"))
        references = final_answer.get("references", [])
        
        print(f"\n{'='*80}")
        print(f"✅ Row {row_num} complete")
        print(f"Question: {question}")
        if row_products:
            print(f"Product Focus: {', '.join(row_products)}")
        print(f"\nAnswer:")
        print(f"{answer}")
        print(f"\nCompliance: {compliance}")
        
        if references:
            print(f"\nReferences ({len(references)}):")
            for ref in references:
                print(f"• {ref}")
        print(f"{'='*80}")
    
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
            
        original_ref_count = len(final_answer.get('references', []))
        filtered_ref_count = len(final_answer.get('references', []))
        
        log_data = {
            "question": question,
            "product_focus": ", ".join(row_products) if row_products else "None",
            "refine_chain_time": chain_time,
            "refine_steps": len(chain_log_data),
            "product_documents": len(product_docs),
            "customer_documents": len(customer_docs),
            "documents_retrieved": len(product_docs) + len(customer_docs),
            "answer": final_answer.get("answer", ""),
            "compliance": final_answer.get("compliance", ""),
            "references": final_answer.get("references", []),
            "sources_used": sources,
            "original_references": original_ref_count,
            "valid_references": filtered_ref_count,
            "chain_log_data": chain_log_data
        }
        
        self.question_logger.log_enhanced_processing(row_num, log_data)


def validate_products_in_sheet(records, product_role, available_products):
    """Validate products mentioned in the sheet against available products."""
    invalid_products = []
    
    for record in records:
        row_num = record["sheet_row"]
        product = QuestionProcessor.clean_text(record["roles"].get(product_role, ""))
        
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