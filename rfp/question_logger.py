import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

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
        # Create directory for refine chain tracking
        self.refine_log_dir = os.path.join(base_dir, "refine_logs")
        os.makedirs(self.refine_log_dir, exist_ok=True)
        
    def _create_filename(self, row_num: int, question: str, directory: str = None) -> str:
        """
        Create a safe filename from row number and question text.
        
        Parameters
        ----------
        row_num : int
            Row number in the Google Sheet
        question : str
            Question text
        directory : str, optional
            Directory to create the file in, defaults to refine_log_dir
            
        Returns
        -------
        str
            Safe filename for logging
        """
        # Take first 40 chars of question and clean it
        clean_question = re.sub(r'[^\w\s-]', '', question.lower())
        clean_question = re.sub(r'\s+', '_', clean_question)
        clean_question = clean_question[:40]
        
        if directory:
            return os.path.join(directory, f"{row_num}_{clean_question}.log")
        else:
            return os.path.join(self.refine_log_dir, f"{row_num}_{clean_question}.log")
    
    def log_enhanced_processing(self, row_num: int, log_data: Dict[str, Any]):
        """
        Enhanced logging for the refine chain process with detailed tracking of the refinement steps.
        
        Parameters
        ----------
        row_num : int
            Row number in the Google Sheet
        log_data : Dict[str, Any]
            Dictionary containing various log data fields
        """
        question = log_data.get("question", "Unknown question")
        filename = self._create_filename(row_num, question, self.refine_log_dir)
        
        with open(filename, 'w', encoding='utf-8') as f:
            # Write header
            f.write("=" * 80 + "\n")
            f.write(f"ENHANCED QUESTION PROCESSING - ROW {row_num}\n")
            f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # Basic information
            f.write("QUESTION INFORMATION\n")
            f.write("-" * 40 + "\n")
            f.write(f"Question: {question}\n")
            f.write(f"Product Focus: {log_data.get('product_focus', 'None')}\n")
            f.write("\n")
            
            # IMPROVED: Retrieval metrics 
            f.write("RETRIEVAL METRICS\n")
            f.write("-" * 40 + "\n")
            # Update this line to use the new documents_retrieved field
            f.write(f"Documents Retrieved: {log_data.get('documents_retrieved', 0)}\n")
            f.write(f"Chain Execution Time: {log_data.get('refine_chain_time', 'Unknown'):.2f} seconds\n")
            f.write("\n")
            
            # IMPROVED: Document sources used
            if 'sources_used' in log_data and log_data['sources_used']:
                f.write("SOURCES USED IN REFINEMENT\n")
                f.write("-" * 40 + "\n")
                for i, source in enumerate(log_data['sources_used'], 1):
                    f.write(f"{i}. {source}\n")
                f.write("\n")
            
            # Final result
            f.write("FINAL RESULT\n")
            f.write("-" * 40 + "\n")
            f.write(f"Compliance: {log_data.get('compliance', 'Unknown')}\n")
            f.write(f"Answer:\n{log_data.get('answer', 'No answer generated')}\n\n")
            
            # References
            if 'references' in log_data and log_data['references']:
                f.write("REFERENCES\n")
                f.write("-" * 40 + "\n")
                for i, ref in enumerate(log_data['references'], 1):
                    f.write(f"{i}. {ref}\n")
                f.write("\n")
            
            # Include any additional data fields
            additional_fields = set(log_data.keys()) - {'question', 'product_focus', 'documents_retrieved', 
                                                      'refine_chain_time', 'sources_used', 'compliance', 
                                                      'answer', 'references'}
            if additional_fields:
                f.write("ADDITIONAL INFORMATION\n")
                f.write("-" * 40 + "\n")
                for field in additional_fields:
                    value = log_data[field]
                    f.write(f"{field}: {value}\n")
        
        logger.info(f"Created enhanced refine log: {os.path.basename(filename)}")
    
    def log_refine_steps(self, row_num: int, question: str, documents: List[Any], 
                       initial_answer: Dict[str, Any], final_answer: Dict[str, Any]):
        """
        Log the individual refinement steps for a given question.
        
        Parameters
        ----------
        row_num : int
            Row number in the Google Sheet
        question : str
            Original question text
        documents : List[Any]
            List of documents used in refinement
        initial_answer : Dict[str, Any]
            Initial answer before refinement
        final_answer : Dict[str, Any]
            Final answer after refinement
        """
        clean_question = re.sub(r'[^\w\s-]', '', question.lower())
        clean_question = re.sub(r'\s+', '_', clean_question)
        clean_question = clean_question[:40]
        
        filename = f"{row_num}_{clean_question}_refine_steps.log"
        filepath = os.path.join(self.refine_log_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            # Write header
            f.write("=" * 80 + "\n")
            f.write(f"REFINEMENT STEPS LOG - ROW {row_num}\n")
            f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # Question
            f.write("QUESTION\n")
            f.write("-" * 40 + "\n")
            f.write(f"{question}\n\n")
            
            # Initial answer
            f.write("INITIAL ANSWER\n")
            f.write("-" * 40 + "\n")
            f.write(json.dumps(initial_answer, indent=2) + "\n\n")
            
            # Documents used for refinement
            f.write("DOCUMENTS USED FOR REFINEMENT\n")
            f.write("-" * 40 + "\n")
            for i, doc in enumerate(documents, 1):
                f.write(f"Document {i}:\n")
                if hasattr(doc, 'metadata') and hasattr(doc, 'page_content'):
                    f.write(f"Source: {doc.metadata.get('source', 'unknown')}\n")
                    f.write(f"Content: {doc.page_content[:200]}...\n")
                else:
                    f.write(f"Document data: {str(doc)[:200]}...\n")
                f.write("\n")
            
            # Final answer
            f.write("FINAL ANSWER\n")
            f.write("-" * 40 + "\n")
            f.write(json.dumps(final_answer, indent=2) + "\n\n")
            
            # Analysis of changes
            f.write("ANALYSIS OF REFINEMENT\n")
            f.write("-" * 40 + "\n")
            
            # Compare compliance
            initial_compliance = initial_answer.get('compliance', 'Unknown')
            final_compliance = final_answer.get('compliance', 'Unknown')
            if initial_compliance != final_compliance:
                f.write(f"Compliance changed: {initial_compliance} -> {final_compliance}\n")
            else:
                f.write(f"Compliance unchanged: {final_compliance}\n")
            
            # Compare answer content length
            initial_answer_text = initial_answer.get('answer', '')
            final_answer_text = final_answer.get('answer', '')
            initial_length = len(initial_answer_text)
            final_length = len(final_answer_text)
            
            f.write(f"Answer length: {initial_length} -> {final_length} ({final_length - initial_length:+d} characters)\n")
            
            # Compare references
            initial_refs = set(initial_answer.get('references', []))
            final_refs = set(final_answer.get('references', []))
            
            new_refs = final_refs - initial_refs
            if new_refs:
                f.write(f"New references added ({len(new_refs)}):\n")
                for ref in new_refs:
                    f.write(f"  + {ref}\n")
            
            removed_refs = initial_refs - final_refs
            if removed_refs:
                f.write(f"References removed ({len(removed_refs)}):\n")
                for ref in removed_refs:
                    f.write(f"  - {ref}\n")
        
        logger.info(f"Created refinement steps log: {filename}")
        
    def log_error(self, row_num: int, question: str, error: Exception):
        """Log error information to a file."""
        filename = self._create_filename(row_num, question)
        
        with open(filename, 'w', encoding='utf-8') as f:
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