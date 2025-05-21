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
            logger.debug("Attempting to extract JSON from LLM response")
            
            # Try direct JSON parsing
            try:
                if cleaned.startswith('{') and cleaned.endswith('}'):
                    parsed = json.loads(cleaned)
                    if JsonProcessor.validate_json_structure(parsed):
                        logger.debug("Successfully parsed direct JSON")
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
                                        logger.debug("Found answer in answers array")
                                        return {
                                            "answer": first_answer['answer'],
                                            "compliance": "PC",
                                            "references": []
                                        }
                                    elif 'value' in first_answer:
                                        logger.debug("Found value in answers array")
                                        return {
                                            "answer": first_answer['value'],
                                            "compliance": "PC",
                                            "references": []
                                        }
                        logger.debug("Processing parsed answers object")
                        return JsonProcessor._process_parsed_json(parsed)
            except json.JSONDecodeError as e:
                logger.debug(f"Direct JSON parsing failed: {str(e)}")
                pass

            # Try finding JSON in code blocks
            code_block_pattern = r"```(?:json)?\s*(.*?)\s*```"
            matches = re.findall(code_block_pattern, cleaned, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                    if JsonProcessor.validate_json_structure(parsed):
                        logger.debug("Successfully parsed JSON from code block")
                        return JsonProcessor._process_parsed_json(parsed)
                except json.JSONDecodeError:
                    continue

            # Try parsing specific patterns
            question_id_pattern = r'questionId: ([a-f0-9-]+)\. answer: (.*?)(?=\.|$)'
            match = re.search(question_id_pattern, cleaned)
            if match:
                logger.debug("Found answer in question ID pattern")
                return {
                    "answer": match.group(2).strip(),
                    "compliance": "PC",
                    "references": []
                }
                
            value_pattern = r'answer: value: (.*?)(?=\. metadata:|$)'
            match = re.search(value_pattern, cleaned)
            if match:
                logger.debug("Found answer in value pattern")
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
                        logger.debug("Successfully parsed JSON from text")
                        return JsonProcessor._process_parsed_json(parsed)
                except json.JSONDecodeError:
                    continue

            # Extract references if available
            references = JsonProcessor.extract_references_from_text(response)
            if references:
                logger.debug(f"Extracted {len(references)} references from text")
                default_result["references"] = references

            # Use plain text if no JSON structure found
            if not ('{' in cleaned and '}' in cleaned):
                logger.debug("No JSON structure found, using plain text")
                default_result["answer"] = cleaned
                return default_result

        except Exception as e:
            logger.warning(f"Error in JSON extraction: {str(e)}")

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
            logger.debug(f"Inferred compliance level: {determined_compliance}")
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
        
        logger.debug(f"Processed JSON result - Compliance: {result['compliance']}, References: {len(result['references'])}")
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
            logger.debug("Missing required keys in JSON structure")
            return False
        
        if "references" in parsed and not isinstance(parsed["references"], list):
            logger.debug("References field is not a list")
            return False
        
        if not isinstance(parsed["answer"], str):
            logger.debug("Answer field is not a string")
            return False
        if not isinstance(parsed["compliance"], str):
            logger.debug("Compliance field is not a string")
            return False
        
        if parsed["compliance"].upper() not in ["FC", "PC", "NC", "NA"]:
            logger.debug(f"Invalid compliance value: {parsed['compliance']}")
            return False
        
        parsed["compliance"] = parsed["compliance"].upper()
        logger.debug("JSON structure validation successful")
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
        logger.debug(f"Found {len(urls)} potential URLs in text")
        
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
        
        logger.debug(f"Extracted {len(cleaned_urls)} valid Salesforce URLs")
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
        value = str(value).strip().upper()
        valid_values = ["FC", "PC", "NC", "NA"]
        
        if value in valid_values:
            logger.debug(f"Valid compliance value: {value}")
            return value
            
        logger.warning(f"Invalid compliance value: {value}, defaulting to PC")
        return "PC"
    
    @staticmethod
    def clean_json_answer(answer_text: str) -> str:
        """
        Clean and normalize an answer text from JSON.
        
        Args:
            answer_text: Answer text to clean
            
        Returns:
            Cleaned answer text
        """
        if not answer_text:
            return ""
            
        # Remove JSON artifacts
        cleaned = answer_text.replace('\\n', '\n').replace('\\"', '"')
        
        # Remove markdown code blocks
        cleaned = re.sub(r'```.*?```', '', cleaned, flags=re.DOTALL)
        
        # Remove inline code
        cleaned = re.sub(r'`.*?`', '', cleaned)
        
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Remove JSON structure artifacts
        cleaned = re.sub(r'[\{\}\[\]"]', '', cleaned)
        
        logger.debug(f"Cleaned answer text length: {len(cleaned)}")
        return cleaned


class ProductLoader:
    """
    Utility class for loading and managing product information.
    """
    
    @staticmethod
    def load_products_from_json(filename: str = 'start_links.json') -> List[str]:
        """
        Load product information from a JSON file.
        
        Args:
            filename: JSON file to load from
            
        Returns:
            List of product names
        """
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                products = [item['name'] for item in data if 'name' in item]
                logger.info(f"Loaded {len(products)} products from {filename}")
                return products
        except Exception as e:
            logger.error(f"Error loading products from {filename}: {str(e)}")
            return []
    
    @staticmethod
    def find_matching_product(product_name: str, available_products: List[str]) -> Optional[str]:
        """
        Find a matching product from available products.
        
        Args:
            product_name: Product name to match
            available_products: List of available product names
            
        Returns:
            Matching product name or None
        """
        product_name = product_name.lower()
        for product in available_products:
            if product_name in product.lower() or product.lower() in product_name:
                logger.debug(f"Found matching product: {product}")
                return product
        logger.debug(f"No matching product found for: {product_name}")
        return None


class VectorStoreManager:
    """
    Utility class for managing vector store operations.
    """
    
    @staticmethod
    def load_faiss_index(index_dir: str, embedding_model: str, skip_indexing: bool = True) -> Optional[FAISS]:
        """
        Load a FAISS index from disk.
        
        Args:
            index_dir: Directory containing the index
            embedding_model: Name of the embedding model to use
            skip_indexing: Whether to skip indexing
            
        Returns:
            Loaded FAISS index or None
        """
        try:
            logger.info(f"Loading FAISS index from {index_dir}")
            embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
            index = FAISS.load_local(index_dir, embeddings)
            logger.info("Successfully loaded FAISS index")
            return index
        except Exception as e:
            logger.error(f"Error loading FAISS index: {str(e)}")
            return None
    
    @staticmethod
    def query_faiss_index(index: FAISS, query: str, k: int = 4) -> List[Any]:
        """
        Query a FAISS index with a search query.
        
        Args:
            index: FAISS index to query
            query: Search query
            k: Number of results to return
            
        Returns:
            List of search results
        """
        try:
            logger.debug(f"Querying FAISS index with k={k}")
            results = index.similarity_search(query, k=k)
            logger.debug(f"Found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error querying FAISS index: {str(e)}")
            logger.error(f"Error querying FAISS index: {e}")
            return []


class StrictJSONOutputParser:
    """
    Parser for ensuring strict JSON output from LLM responses.
    """
    
    @staticmethod
    def parse(text: str) -> Dict:
        """
        Parse text into a strict JSON structure.
        
        Args:
            text: Text to parse
            
        Returns:
            Parsed JSON dictionary
        """
        logger.debug("Parsing text with strict JSON parser")
        warnings.warn(
            "StrictJSONOutputParser.parse() is deprecated. Use JsonProcessor.extract_json_from_llm_response() instead.",
            DeprecationWarning, 
            stacklevel=2
        )
        
        return JsonProcessor.extract_json_from_llm_response(text)

