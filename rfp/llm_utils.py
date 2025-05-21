import re
import json
import logging
import os
import warnings
from typing import Dict, Any, List, Optional, Tuple

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

logger = logging.getLogger(__name__)

class JsonProcessor:
    """
    Utility class for processing JSON data from LLM responses.
    
    Provides methods for extracting, validating, and cleaning JSON structures.
    """
    
    @staticmethod
    def extract_json_from_llm_response(response: str) -> Dict[str, Any]:
        """
        Extract a JSON object from an LLM response.
        
        Args:
            response: Raw LLM response text
            
        Returns:
            Parsed JSON as a dictionary
        """
        default_result = {
            "answer": response.strip(),
            "compliance": "PC",
            "references": []
        }
        
        try:
            cleaned = response.strip()
            
            # Try direct JSON parsing
            try:
                if cleaned.startswith('{') and cleaned.endswith('}'):
                    parsed = json.loads(cleaned)
                    if JsonProcessor.validate_json_structure(parsed):
                        return JsonProcessor._process_parsed_json(parsed)
                    
                # Handle answers object
                if '"answers"' in cleaned or "'answers'" in cleaned:
                    match = re.search(r'(\{[\s\S]*\})', cleaned)
                    if match:
                        potential_json = match.group(1)
                        parsed = json.loads(potential_json)
                        if 'answers' in parsed:
                            if isinstance(parsed['answers'], list) and len(parsed['answers']) > 0:
                                first_answer = parsed['answers'][0]
                                if isinstance(first_answer, dict):
                                    if 'answer' in first_answer:
                                        return {
                                            "answer": first_answer['answer'],
                                            "compliance": "PC",
                                            "references": []
                                        }
                                    elif 'value' in first_answer:
                                        return {
                                            "answer": first_answer['value'],
                                            "compliance": "PC",
                                            "references": []
                                        }
                        return JsonProcessor._process_parsed_json(parsed)
            except json.JSONDecodeError:
                pass

            # Try finding JSON in code blocks
            code_block_pattern = r"```(?:json)?\s*(.*?)\s*```"
            matches = re.findall(code_block_pattern, cleaned, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                    if JsonProcessor.validate_json_structure(parsed):
                        return JsonProcessor._process_parsed_json(parsed)
                except json.JSONDecodeError:
                    continue

            # Try parsing specific patterns
            question_id_pattern = r'questionId: ([a-f0-9-]+)\. answer: (.*?)(?=\.|$)'
            match = re.search(question_id_pattern, cleaned)
            if match:
                return {
                    "answer": match.group(2).strip(),
                    "compliance": "PC",
                    "references": []
                }
                
            value_pattern = r'answer: value: (.*?)(?=\. metadata:|$)'
            match = re.search(value_pattern, cleaned)
            if match:
                return {
                    "answer": match.group(1).strip(),
                    "compliance": "PC",
                    "references": []
                }

            # Try finding JSON objects inside text
            json_pattern = r'\{[\s\S]*?\}'
            matches = re.findall(json_pattern, cleaned)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if JsonProcessor.validate_json_structure(parsed):
                        return JsonProcessor._process_parsed_json(parsed)
                except json.JSONDecodeError:
                    continue

            # Extract references if available
            references = JsonProcessor.extract_references_from_text(response)
            if references:
                default_result["references"] = references

            # Use plain text if no JSON structure found
            if not ('{' in cleaned and '}' in cleaned):
                default_result["answer"] = cleaned
                return default_result

        except Exception as e:
            logger.warning(f"Error in JSON extraction: {e}")

        # Try to infer compliance from text
        compliance_indicators = {
            "NA": ["not applicable", "out of scope", "irrelevant", "not relevant"],
            "NC": ["not compliant", "not possible", "cannot be achieved", "not supported"],
            "FC": ["fully compliant", "standard functionality", "out of the box", "built-in", "standard configuration"],
            "PC": ["partially compliant", "customization", "configuration", "workaround", "custom development"]
        }

        response_lower = response.lower()
        determined_compliance = None
        for compliance, indicators in compliance_indicators.items():
            if any(indicator in response_lower for indicator in indicators):
                determined_compliance = compliance
                break
        
        if determined_compliance:
            default_result["compliance"] = determined_compliance
        
        return default_result
    
    @staticmethod
    def _process_parsed_json(parsed: Dict) -> Dict:
        """
        Process a parsed JSON object to ensure it has the expected structure.
        
        Args:
            parsed: Parsed JSON dictionary
            
        Returns:
            Processed dictionary with standardized structure
        """
        result = {
            "answer": "",
            "compliance": "PC",
            "references": []
        }
        
        # Extract answer
        if "answer" in parsed:
            result["answer"] = JsonProcessor.clean_json_answer(str(parsed["answer"]))
        elif "question" in parsed and "answer" in parsed:
            result["answer"] = JsonProcessor.clean_json_answer(str(parsed["answer"]))
        elif "answers" in parsed and isinstance(parsed["answers"], list):
            for answer_obj in parsed["answers"]:
                if isinstance(answer_obj, dict) and "answer" in answer_obj:
                    result["answer"] = JsonProcessor.clean_json_answer(str(answer_obj["answer"]))
                    break
                elif isinstance(answer_obj, dict) and "value" in answer_obj:
                    result["answer"] = JsonProcessor.clean_json_answer(str(answer_obj["value"]))
                    break
        
        # Extract compliance
        if "compliance" in parsed:
            result["compliance"] = JsonProcessor.validate_compliance_value(parsed["compliance"])
        
        # Extract references
        if "references" in parsed and isinstance(parsed["references"], list):
            result["references"] = parsed["references"]
        
        # Fallback for answer
        if not result["answer"]:
            result["answer"] = JsonProcessor.clean_json_answer(json.dumps(parsed))
        
        return result
    
    @staticmethod
    def validate_json_structure(parsed: Dict) -> bool:
        """
        Validate that a parsed JSON dictionary has the expected structure.
        
        Args:
            parsed: Parsed JSON dictionary
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not all(key in parsed for key in ["answer", "compliance"]):
            return False
        
        if "references" in parsed and not isinstance(parsed["references"], list):
            return False
        
        if not isinstance(parsed["answer"], str):
            return False
        if not isinstance(parsed["compliance"], str):
            return False
        
        if parsed["compliance"].upper() not in ["FC", "PC", "NC", "NA"]:
            return False
        
        parsed["compliance"] = parsed["compliance"].upper()
        
        return True
    
    @staticmethod
    def extract_references_from_text(text: str) -> List[str]:
        """
        Extract URL references from text.
        
        Args:
            text: Text to extract references from
            
        Returns:
            List of extracted URLs
        """
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        urls = re.findall(url_pattern, text)
        
        cleaned_urls = []
        for url in urls:
            # Clean trailing punctuation
            url = re.sub(r'[.,;:!?)\]}]+$', '', url)
            
            # Only include Salesforce domains
            if any(domain in url.lower() for domain in [
                'salesforce.com', 
                'force.com', 
                'trailhead.com',
                'developer.salesforce.com',
                'help.salesforce.com'
            ]):
                if url not in cleaned_urls:
                    cleaned_urls.append(url)
        
        return cleaned_urls
    
    @staticmethod
    def validate_compliance_value(value: str) -> str:
        """
        Validate and normalize a compliance value.
        
        Args:
            value: Compliance value to validate
            
        Returns:
            Normalized compliance value
        """
        if not value:
            return "PC"
            
        valid_values = ["FC", "PC", "NC", "NA"]
        clean_value = value.strip().upper()
        
        if clean_value in valid_values:
            return clean_value
        
        compliance_map = {
            "FULLY COMPLIANT": "FC",
            "FULLY-COMPLIANT": "FC",
            "FULLY COMPATIBLE": "FC",
            "PARTIALLY COMPLIANT": "PC",
            "PARTIALLY-COMPLIANT": "PC",
            "PARTIALLY COMPATIBLE": "PC",
            "NOT COMPLIANT": "NC",
            "NON COMPLIANT": "NC",
            "NON-COMPLIANT": "NC",
            "NOT COMPATIBLE": "NC",
            "NOT APPLICABLE": "NA",
            "N/A": "NA",
            "IRRELEVANT": "NA"
        }
        
        for key, mapped_value in compliance_map.items():
            if key in clean_value:
                return mapped_value
        
        logger.warning(f"Invalid compliance value: '{value}', defaulting to 'PC'")
        return "PC"
    
    @staticmethod
    def clean_json_answer(answer_text: str) -> str:
        """
        Clean and normalize an answer from JSON.
        
        Args:
            answer_text: Answer text to clean
            
        Returns:
            Cleaned answer text
        """
        if not answer_text:
            return ""
            
        if '{' not in answer_text and '}' not in answer_text and ':' not in answer_text:
            return answer_text
        
        metadata_prefixes = [
            "answers:", "value:", "metadata:", "source:", "answer:", "questionId:", 
            "confidence:", "NoData"
        ]
        
        clean_text = answer_text
        
        for prefix in metadata_prefixes:
            clean_text = re.sub(r'\b' + re.escape(prefix) + r'\b', '', clean_text)
        
        clean_text = re.sub(r'[\[\]{}"]', '', clean_text)
        
        clean_text = re.sub(r'\.\s*\.', '.', clean_text)
        clean_text = re.sub(r'\s*\.\s*', '. ', clean_text)
        
        sentences = re.findall(r'[A-Z][^.!?]*[.!?]', clean_text)
        if sentences:
            clean_text = ' '.join(sentences)
        
        clean_text = re.sub(r'\b[a-zA-Z]+:\s', '', clean_text)
        
        if '{' in clean_text and '}' in clean_text:
            try:
                parsed = json.loads(re.search(r'(\{.*\})', clean_text).group(1))
                if isinstance(parsed, dict):
                    for field in ["answer", "text", "description", "content", "message"]:
                        if field in parsed and isinstance(parsed[field], str):
                            return parsed[field]
                    return json.dumps(parsed, ensure_ascii=False)
            except (json.JSONDecodeError, AttributeError):
                pass
        
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        clean_text = re.sub(r'\.{2,}', '.', clean_text)
        clean_text = re.sub(r'([.!?])\s*\1', r'\1', clean_text)
        
        if len(clean_text) < 10:
            return answer_text.strip()
        
        return clean_text.strip()


class ProductLoader:
    """
    Utility class for loading product information.
    
    Provides methods for loading and processing product data.
    """
    
    @staticmethod
    def load_products_from_json(filename: str = 'start_links.json') -> List[str]:
        """
        Load product information from JSON file.
        
        Args:
            filename: Path to JSON file containing product information
        
        Returns:
            List of product names
        """
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            
            products = []
            for item in data:
                product_name = item['product'].replace('_', ' ')
                products.append(product_name)
            
            return sorted(products)
        except Exception as e:
            logger.error(f"Failed to load products from JSON: {e}")
            return []
    
    @staticmethod
    def find_matching_product(product_name: str, available_products: List[str]) -> Optional[str]:
        """
        Find a matching product in the list of available products.
        
        Args:
            product_name: Product name to match
            available_products: List of available product names
            
        Returns:
            Matched product name or None if no match found
        """
        product_name_lower = product_name.lower()
        
        # Check for exact match
        for product in available_products:
            if product.lower() == product_name_lower:
                return product
        
        # Check for partial match
        for product in available_products:
            if product_name_lower in product.lower() or product.lower() in product_name_lower:
                return product
                
        return None


class VectorStoreManager:
    """
    Utility class for managing vector stores.
    
    Provides methods for loading and querying FAISS vector indices.
    """
    
    @staticmethod
    def load_faiss_index(index_dir: str, embedding_model: str, skip_indexing: bool = True) -> Optional[FAISS]:
        """
        Load a FAISS index from disk.
        
        Args:
            index_dir: Directory containing the index
            embedding_model: Name of embedding model to use
            skip_indexing: Whether to skip indexing if index doesn't exist
            
        Returns:
            FAISS index instance
            
        Raises:
            FileNotFoundError: If index doesn't exist and skip_indexing is True
        """
        warnings.warn(
            "load_faiss_index() is deprecated. Use EmbeddingManager.query_index() instead for better memory efficiency.",
            DeprecationWarning, 
            stacklevel=2
        )
        
        try:
            embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
            if skip_indexing:
                if os.path.exists(index_dir):
                    logger.info(f"Loading FAISS index from {index_dir}...")
                    return FAISS.load_local(index_dir, embeddings, allow_dangerous_deserialization=True)
                else:
                    logger.critical(f"FAISS index not found at: {index_dir}")
                    raise FileNotFoundError(f"FAISS index not found at {index_dir}")
            else:
                raise NotImplementedError("Indexing is currently disabled. Set SKIP_INDEXING=True to use existing index.")
        except Exception as e:
            logger.error(f"Error loading FAISS index: {e}")
            raise
    
    @staticmethod
    def query_faiss_index(index: FAISS, query: str, k: int = 4) -> List[Any]:
        """
        Query a FAISS index.
        
        Args:
            index: FAISS index to query
            query: Query string
            k: Number of results to return
            
        Returns:
            List of retrieved documents
        """
        try:
            logger.info(f"Querying FAISS index with query: {query}")
            results = index.similarity_search(query, k=k)
            logger.info(f"Retrieved {len(results)} documents")
            return results
        except Exception as e:
            logger.error(f"Error querying FAISS index: {e}")
            return []


class StrictJSONOutputParser:
    """
    Parser for handling JSON outputs from LLMs.
    
    Note: This class is deprecated. Use JsonProcessor instead.
    """
    
    @staticmethod
    def parse(text: str) -> Dict:
        """
        Parse text into JSON structure.
        
        Args:
            text: Text to parse
            
        Returns:
            Parsed JSON dictionary
        """
        warnings.warn(
            "StrictJSONOutputParser.parse() is deprecated. Use JsonProcessor.extract_json_from_llm_response() instead.",
            DeprecationWarning, 
            stacklevel=2
        )
        
        return JsonProcessor.extract_json_from_llm_response(text)

