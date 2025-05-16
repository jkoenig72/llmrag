import os
import re
import json
import logging
import difflib
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class QuestionLogger:
    def __init__(self, base_dir: str):
        self.refine_log_dir = os.path.join(base_dir, "refine_logs")
        os.makedirs(self.refine_log_dir, exist_ok=True)
        
        self.chain_log_dir = os.path.join(base_dir, "chain_logs")
        os.makedirs(self.chain_log_dir, exist_ok=True)
        
    def _create_filename(self, row_num: int, question: str, directory: str = None) -> str:
        clean_question = re.sub(r'[^\w\s-]', '', question.lower())
        clean_question = re.sub(r'\s+', '_', clean_question)
        clean_question = clean_question[:40]
        
        if directory:
            return os.path.join(directory, f"{row_num}_{clean_question}.log")
        else:
            return os.path.join(self.refine_log_dir, f"{row_num}_{clean_question}.log")
    
    def log_enhanced_processing(self, row_num: int, log_data: Dict[str, Any]):
        question = log_data.get("question", "Unknown question")
        filename = self._create_filename(row_num, question, self.refine_log_dir)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"ENHANCED QUESTION PROCESSING - ROW {row_num}\n")
            f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("QUESTION INFORMATION\n")
            f.write("-" * 40 + "\n")
            f.write(f"Question: {question}\n")
            f.write(f"Product Focus: {log_data.get('product_focus', 'None')}\n")
            f.write("\n")
            
            f.write("RETRIEVAL METRICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"Documents Retrieved: {log_data.get('documents_retrieved', 0)}\n")
            f.write(f"Chain Execution Time: {log_data.get('refine_chain_time', 'Unknown'):.2f} seconds\n")
            f.write("\n")
            
            if 'sources_used' in log_data and log_data['sources_used']:
                f.write("SOURCES USED IN REFINEMENT\n")
                f.write("-" * 40 + "\n")
                for i, source in enumerate(log_data['sources_used'], 1):
                    f.write(f"{i}. {source}\n")
                f.write("\n")
            
            f.write("FINAL RESULT\n")
            f.write("-" * 40 + "\n")
            f.write(f"Compliance: {log_data.get('compliance', 'Unknown')}\n")
            f.write(f"Answer:\n{log_data.get('answer', 'No answer generated')}\n\n")
            
            if 'references' in log_data and log_data['references']:
                f.write("REFERENCES\n")
                f.write("-" * 40 + "\n")
                for i, ref in enumerate(log_data['references'], 1):
                    f.write(f"{i}. {ref}\n")
                f.write("\n")
            
            additional_fields = set(log_data.keys()) - {'question', 'product_focus', 'documents_retrieved', 
                                                      'refine_chain_time', 'sources_used', 'compliance', 
                                                      'answer', 'references', 'chain_log_data'}
            if additional_fields:
                f.write("ADDITIONAL INFORMATION\n")
                f.write("-" * 40 + "\n")
                for field in additional_fields:
                    value = log_data[field]
                    f.write(f"{field}: {value}\n")
        
        logger.info(f"Created enhanced refine log: {os.path.basename(filename)}")
        
        if 'chain_log_data' in log_data and log_data['chain_log_data']:
            self.log_refinement_chain(row_num, question, log_data['chain_log_data'])
    
    def log_refinement_chain(self, row_num: int, question: str, chain_data: List[Dict[str, Any]]):
        chain_filename = self._create_filename(row_num, question, self.chain_log_dir).replace('.log', '_chain.log')
        
        with open(chain_filename, 'w', encoding='utf-8') as f:
            f.write("=" * 100 + "\n")
            f.write(f"COMPLETE REFINEMENT CHAIN LOG - ROW {row_num}\n")
            f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 100 + "\n\n")
            
            f.write(f"QUESTION: {question}\n\n")
            
            previous_answer = None
            
            for step_idx, step_data in enumerate(chain_data):
                step_num = step_idx + 1
                step_type = step_data.get('step_type', 'Unknown')
                
                f.write("=" * 100 + "\n")
                f.write(f"STEP {step_num}: {step_type} {'(INITIAL)' if step_type == 'PROMPT' and step_num == 1 else ''}\n")
                f.write("=" * 100 + "\n\n")
                
                if 'context_info' in step_data:
                    f.write("CONTEXT INFORMATION:\n")
                    f.write("-" * 80 + "\n")
                    
                    context_info = step_data['context_info']
                    
                    if 'product_doc' in context_info:
                        f.write(f"Product Document: {context_info['product_doc']}\n")
                    
                    if 'customer_doc' in context_info:
                        f.write(f"Customer Document: {context_info['customer_doc']}\n")
                    
                    if 'context_size' in context_info:
                        f.write(f"Context Size: {context_info['context_size']} characters\n")
                    
                    if 'document_number' in context_info:
                        f.write(f"Document Number: {context_info['document_number']}\n")
                        
                    if 'truncated' in context_info and context_info['truncated']:
                        f.write(f"Note: Context was truncated to fit size limits\n")
                    
                    f.write("\n")
                
                if 'prompt' in step_data:
                    f.write("PROMPT SENT TO LLM:\n")
                    f.write("-" * 80 + "\n")
                    f.write(step_data['prompt'])
                    f.write("\n\n")
                
                if 'raw_response' in step_data:
                    f.write("RAW LLM RESPONSE:\n")
                    f.write("-" * 80 + "\n")
                    f.write(step_data['raw_response'])
                    f.write("\n\n")
                
                if 'parsed_answer' in step_data:
                    f.write("PARSED ANSWER:\n")
                    f.write("-" * 80 + "\n")
                    parsed = step_data['parsed_answer']
                    
                    try:
                        if isinstance(parsed, str):
                            try:
                                parsed_dict = json.loads(parsed)
                                f.write(json.dumps(parsed_dict, indent=2))
                            except json.JSONDecodeError:
                                f.write(parsed)
                        else:
                            f.write(json.dumps(parsed, indent=2))
                    except (json.JSONDecodeError, TypeError):
                        f.write(str(parsed))
                    
                    f.write("\n\n")
                    
                    if previous_answer and isinstance(parsed, dict) and 'answer' in parsed:
                        current_answer = parsed.get('answer', '')
                        prev_answer_text = previous_answer.get('answer', '')
                        
                        if current_answer != prev_answer_text:
                            f.write("CHANGES FROM PREVIOUS STEP:\n")
                            f.write("-" * 80 + "\n")
                            
                            diff = difflib.unified_diff(
                                prev_answer_text.splitlines(),
                                current_answer.splitlines(),
                                lineterm='',
                                n=2
                            )
                            
                            diff_text = '\n'.join(diff)
                            if diff_text:
                                f.write(diff_text)
                            else:
                                f.write("No textual changes detected, but structure or metadata may have changed.")
                            
                            f.write("\n\n")
                            
                            prev_compliance = previous_answer.get('compliance', '')
                            current_compliance = parsed.get('compliance', '')
                            
                            if prev_compliance != current_compliance:
                                f.write(f"Compliance rating changed: {prev_compliance} → {current_compliance}\n\n")
                            
                            prev_refs = set(previous_answer.get('references', []))
                            current_refs = set(parsed.get('references', []))
                            
                            new_refs = current_refs - prev_refs
                            if new_refs:
                                f.write("New references added:\n")
                                for ref in new_refs:
                                    f.write(f"+ {ref}\n")
                                f.write("\n")
                            
                            removed_refs = prev_refs - current_refs
                            if removed_refs:
                                f.write("References removed:\n")
                                for ref in removed_refs:
                                    f.write(f"- {ref}\n")
                                f.write("\n")
                    
                    if isinstance(parsed, dict):
                        previous_answer = parsed
                
                if 'processing_time' in step_data:
                    f.write(f"Processing Time: {step_data['processing_time']:.2f} seconds\n\n")
                
                if 'error' in step_data:
                    f.write("ERROR INFORMATION:\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"Error: {step_data['error']}\n\n")
                
                f.write("\n" + "-" * 100 + "\n\n")
            
            f.write("=" * 100 + "\n")
            f.write("CHAIN EXECUTION SUMMARY\n")
            f.write("=" * 100 + "\n\n")
            
            if chain_data and len(chain_data) > 0 and 'parsed_answer' in chain_data[-1]:
                final_result = chain_data[-1]['parsed_answer']
                if isinstance(final_result, str):
                    try:
                        final_result = json.loads(final_result)
                    except json.JSONDecodeError:
                        pass
                
                if isinstance(final_result, dict):
                    f.write(f"Final Compliance Rating: {final_result.get('compliance', 'Unknown')}\n")
                    f.write(f"Final Answer: {final_result.get('answer', 'No answer generated')}\n\n")
                    
                    if 'references' in final_result and final_result['references']:
                        f.write("Final References:\n")
                        for ref in final_result['references']:
                            f.write(f"• {ref}\n")
                        f.write("\n")
                else:
                    f.write(f"Final Result: {str(final_result)}\n")
            
            total_time = sum(step.get('processing_time', 0) for step in chain_data if 'processing_time' in step)
            f.write(f"Total Steps: {len(chain_data)}\n")
            f.write(f"Total Processing Time: {total_time:.2f} seconds\n")
        
        logger.info(f"Created complete refinement chain log: {os.path.basename(chain_filename)}")
    
    def log_refine_steps(self, row_num: int, question: str, documents: List[Any], 
                       initial_answer: Dict[str, Any], final_answer: Dict[str, Any]):
        clean_question = re.sub(r'[^\w\s-]', '', question.lower())
        clean_question = re.sub(r'\s+', '_', clean_question)
        clean_question = clean_question[:40]
        
        filename = f"{row_num}_{clean_question}_refine_steps.log"
        filepath = os.path.join(self.refine_log_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"REFINEMENT STEPS LOG - ROW {row_num}\n")
            f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("QUESTION\n")
            f.write("-" * 40 + "\n")
            f.write(f"{question}\n\n")
            
            f.write("INITIAL ANSWER\n")
            f.write("-" * 40 + "\n")
            f.write(json.dumps(initial_answer, indent=2) + "\n\n")
            
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
            
            f.write("FINAL ANSWER\n")
            f.write("-" * 40 + "\n")
            f.write(json.dumps(final_answer, indent=2) + "\n\n")
            
            f.write("ANALYSIS OF REFINEMENT\n")
            f.write("-" * 40 + "\n")
            
            initial_compliance = initial_answer.get('compliance', 'Unknown')
            final_compliance = final_answer.get('compliance', 'Unknown')
            if initial_compliance != final_compliance:
                f.write(f"Compliance changed: {initial_compliance} -> {final_compliance}\n")
            else:
                f.write(f"Compliance unchanged: {final_compliance}\n")
            
            initial_answer_text = initial_answer.get('answer', '')
            final_answer_text = final_answer.get('answer', '')
            initial_length = len(initial_answer_text)
            final_length = len(final_answer_text)
            
            f.write(f"Answer length: {initial_length} -> {final_length} ({final_length - initial_length:+d} characters)\n")
            
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