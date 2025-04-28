import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class QuestionLogger:
    """Handles detailed logging for each question processed."""
    
    def __init__(self, base_dir: str):
        """
        Initialize the question logger.
        
        Parameters
        ----------
        base_dir : str
            Base directory for storing log files
        """
        self.log_dir = os.path.join(base_dir, "question_logs")
        os.makedirs(self.log_dir, exist_ok=True)
        
    def _create_filename(self, row_num: int, question: str) -> str:
        """
        Create a safe filename from row number and question text.
        
        Parameters
        ----------
        row_num : int
            Row number in the Google Sheet
        question : str
            Question text
            
        Returns
        -------
        str
            Safe filename for logging
        """
        # Take first 40 chars of question and clean it
        clean_question = re.sub(r'[^\w\s-]', '', question.lower())
        clean_question = re.sub(r'\s+', '_', clean_question)
        clean_question = clean_question[:40]
        
        return f"{row_num}_{clean_question}.log"
    
    def log_question_processing(self, row_num: int, question: str, 
                              product_context: str, 
                              customer_context: str,
                              formatted_prompt: str,
                              raw_answer: str,
                              parsed_answer: Dict[str, Any],
                              products_focus: List[str] = None,
                              additional_info: str = None):
        """
        Create comprehensive log for a single question processing.
        
        Parameters
        ----------
        row_num : int
            Row number in the Google Sheet
        question : str
            Original question text
        product_context : str
            Retrieved product context from FAISS
        customer_context : str
            Retrieved customer context from customer index
        formatted_prompt : str
            Complete prompt sent to LLM
        raw_answer : str
            Raw response from LLM
        parsed_answer : Dict[str, Any]
            Parsed JSON response
        products_focus : List[str], optional
            List of focused products
        additional_info : str, optional
            Additional context from the sheet
        """
        filename = self._create_filename(row_num, question)
        filepath = os.path.join(self.log_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            # Write header
            f.write("=" * 80 + "\n")
            f.write(f"Question Processing Log - Row {row_num}\n")
            f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # Question details
            f.write("QUESTION DETAILS\n")
            f.write("-" * 40 + "\n")
            f.write(f"Question: {question}\n")
            if products_focus:
                f.write(f"Product Focus: {', '.join(products_focus)}\n")
            if additional_info:
                f.write(f"Additional Context: {additional_info}\n")
            f.write("\n")
            
            # RAG Context - Product
            f.write("PRODUCT CONTEXT FROM RAG\n")
            f.write("-" * 40 + "\n")
            f.write(product_context + "\n\n")
            
            # RAG Context - Customer
            if customer_context:
                f.write("CUSTOMER CONTEXT FROM RAG\n")
                f.write("-" * 40 + "\n")
                f.write(customer_context + "\n\n")
            
            # Full Prompt
            f.write("PROMPT SENT TO LLM\n")
            f.write("-" * 40 + "\n")
            f.write(formatted_prompt + "\n\n")
            
            # Raw LLM Response
            f.write("RAW LLM RESPONSE\n")
            f.write("-" * 40 + "\n")
            f.write(raw_answer + "\n\n")
            
            # Parsed Response
            f.write("PARSED RESPONSE\n")
            f.write("-" * 40 + "\n")
            f.write(json.dumps(parsed_answer, indent=2) + "\n\n")
            
            # Summary
            f.write("PROCESSING SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"Compliance: {parsed_answer.get('compliance', 'N/A')}\n")
            f.write(f"References: {len(parsed_answer.get('references', []))}\n")
            f.write(f"Answer length: {len(parsed_answer.get('answer', ''))} characters\n")
            
            # List references if any
            if parsed_answer.get('references'):
                f.write("\nReferences:\n")
                for i, ref in enumerate(parsed_answer['references'], 1):
                    f.write(f"  {i}. {ref}\n")
            
        # Log success to main logger
        logger.info(f"Created detailed log: {filename}")
        
    def log_error(self, row_num: int, question: str, error: Exception):
        """Log error information to a file."""
        filename = self._create_filename(row_num, question)
        filepath = os.path.join(self.log_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"Question Processing Error - Row {row_num}\n")
            f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Question: {question}\n\n")
            f.write(f"Error Type: {type(error).__name__}\n")
            f.write(f"Error Message: {str(error)}\n")
            f.write("\n" + "-" * 40 + "\n")
            f.write("Stack Trace:\n")
            import traceback
            f.write(traceback.format_exc())
            