import re
import json
import logging
import os
from typing import Dict, Any, List
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

logger = logging.getLogger(__name__)

def load_faiss_index(index_dir: str, embedding_model: str, skip_indexing: bool = True):
    """
    Load FAISS vector index from disk.
    
    This function initializes a FAISS vector index using the specified embedding model
    and loads it from the provided directory path.
    
    Parameters
    ----------
    index_dir : str
        Path to the directory containing the FAISS index
    embedding_model : str
        Name of the Hugging Face embedding model to use
    skip_indexing : bool, default True
        If True, load existing index; if False, attempt to create a new index
        
    Returns
    -------
    FAISS
        Loaded FAISS vector store instance
        
    Raises
    ------
    FileNotFoundError
        If skip_indexing is True and the index directory doesn't exist
    NotImplementedError
        If skip_indexing is False (indexing is currently not implemented)
    Exception
        For other errors during index loading
    """
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

class StrictJSONOutputParser:
    """
    Ensures that LLM responses are properly formatted as JSON.
    
    Provides methods to format and validate JSON output from LLMs,
    with fallback mechanisms to handle partial or malformed JSON.
    """
    
    @staticmethod
    def parse(text: str) -> Dict:
        """
        Parse text that should contain JSON and extract a valid JSON object.
        
        Parameters
        ----------
        text : str
            Text that should contain a JSON object
            
        Returns
        -------
        Dict
            Extracted JSON object or default response
        """
        # Default response format
        default_response = {
            "compliance": "PC",
            "answer": text.strip(),
            "references": []
        }
        
        # Clean the text to handle common issues
        cleaned_text = StrictJSONOutputParser._clean_text(text)
        
        # Try to find and extract JSON
        try:
            # Look for JSON block between curly braces
            json_match = re.search(r'(\{[\s\S]*\})', cleaned_text)
            if json_match:
                json_str = json_match.group(1)
                parsed = json.loads(json_str)
                
                # Validate required fields
                if "compliance" in parsed and "answer" in parsed:
                    # Ensure references is a list
                    if "references" not in parsed:
                        parsed["references"] = []
                    elif not isinstance(parsed["references"], list):
                        parsed["references"] = []
                        
                    # Ensure compliance is valid
                    parsed["compliance"] = validate_compliance_value(parsed["compliance"])
                    
                    # Clean answer field
                    parsed["answer"] = clean_json_answer(str(parsed["answer"]))
                    
                    return parsed
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"Failed to parse JSON from LLM response: {e}")
        
        # If we're here, we couldn't extract valid JSON - try to find key fields
        try:
            # Try to extract compliance
            compliance_match = re.search(r'"compliance":\s*"([^"]+)"', cleaned_text)
            if compliance_match:
                default_response["compliance"] = validate_compliance_value(compliance_match.group(1))
            
            # Try to extract references
            references_match = re.search(r'"references":\s*\[(.*?)\]', cleaned_text, re.DOTALL)
            if references_match:
                refs_text = references_match.group(1)
                # Extract URLs from the references text
                urls = re.findall(r'"(https?://[^"]+)"', refs_text)
                if urls:
                    default_response["references"] = urls
            
            # Try to extract answer
            answer_match = re.search(r'"answer":\s*"([^"]+)"', cleaned_text)
            if answer_match:
                default_response["answer"] = answer_match.group(1)
            else:
                # Try to extract multi-line answer
                answer_match = re.search(r'"answer":\s*"([\s\S]*?)"[,}]', cleaned_text)
                if answer_match:
                    default_response["answer"] = answer_match.group(1)
        except Exception as e:
            logger.warning(f"Failed to extract fields from LLM response: {e}")
        
        return default_response
    
    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Clean text to prepare for JSON extraction.
        
        Parameters
        ----------
        text : str
            Raw text from LLM
            
        Returns
        -------
        str
            Cleaned text
        """
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Remove response prefixes like "Response (JSON only):"
        text = re.sub(r'^.*?Response \(JSON only\):\s*', '', text, flags=re.DOTALL)
        
        # Remove any trailing markdown
        text = re.sub(r'\s*```\s*$', '', text)
        
        return text

def discover_products_from_index(faiss_index, num_samples=100):
    """
    Discover products mentioned in the FAISS index by sampling documents.
    Returns a list of unique product names found in the index.
    """
    # Define products based on your start_links.json
    available_products = [
        "Sales Cloud",
        "Service Cloud", 
        "Agentforce",
        "Platform",
        "Communications Cloud",
        "Experience Cloud",
        "Data Cloud",
        "Marketing Cloud",
        "MuleSoft"
    ]
    
    # Sample documents to verify these products exist in the index
    found_products = set()
    
    # Search for each product to confirm it's in the index
    for product in available_products:
        try:
            # Try to find documents mentioning this product
            results = faiss_index.similarity_search(product, k=1)
            if results and len(results) > 0:
                found_products.add(product)
                logger.debug(f"Found product '{product}' in FAISS index")
        except Exception as e:
            logger.warning(f"Could not search for product '{product}': {e}")
    
    return sorted(list(found_products))

def load_products_from_json():
    """
    Load products directly from start_links.json file.
    """
    try:
        with open('start_links.json', 'r') as f:
            data = json.load(f)
        
        products = []
        for item in data:
            product_name = item['product'].replace('_', ' ')
            products.append(product_name)
        
        return sorted(products)
    except Exception as e:
        logger.error(f"Failed to load products from JSON: {e}")
        return []

def clean_json_answer(answer_text: str) -> str:
    """
    Clean JSON structures and metadata artifacts from answer text, ensuring pure text output.
    
    This function applies multiple cleaning strategies to extract plain text from various
    formats and remove any JSON artifacts, metadata, or special formatting.
    
    Parameters
    ----------
    answer_text : str
        The potentially JSON-formatted or metadata-filled answer text
        
    Returns
    -------
    str
        Clean, plain text without JSON formatting or metadata artifacts
    """
    if not answer_text:
        return ""
        
    # Skip cleaning if there's no JSON structure or metadata pattern
    if '{' not in answer_text and '}' not in answer_text and ':' not in answer_text:
        return answer_text
    
    # Try to extract content from common patterns
    
    # Pattern 1: Remove "answers:" and other metadata prefixes
    metadata_prefixes = [
        "answers:", "value:", "metadata:", "source:", "answer:", "questionId:", 
        "confidence:", "NoData"
    ]
    
    clean_text = answer_text
    
    # Replace each prefix with an empty string or a space
    for prefix in metadata_prefixes:
        clean_text = re.sub(r'\b' + re.escape(prefix) + r'\b', '', clean_text)
    
    # Pattern 2: Clean up JSON-like formatting artifacts
    clean_text = re.sub(r'[\[\]{}"]', '', clean_text)  # Remove JSON brackets and quotes
    
    # Pattern 3: Clean up dots that separate metadata fields
    clean_text = re.sub(r'\.\s*\.', '.', clean_text)  # Replace double dots with single
    clean_text = re.sub(r'\s*\.\s*', '. ', clean_text)  # Normalize spacing around dots
    
    # Pattern 4: Try to extract valid sentences
    sentences = re.findall(r'[A-Z][^.!?]*[.!?]', clean_text)
    if sentences:
        clean_text = ' '.join(sentences)
    
    # Remove any remaining structured format indicators
    clean_text = re.sub(r'\b[a-zA-Z]+:\s', '', clean_text)  # Remove "field:" patterns
    
    # Try to parse as JSON if it still looks like JSON
    if '{' in clean_text and '}' in clean_text:
        try:
            parsed = json.loads(re.search(r'(\{.*\})', clean_text).group(1))
            if isinstance(parsed, dict):
                # Try to extract text fields
                for field in ["answer", "text", "description", "content", "message"]:
                    if field in parsed and isinstance(parsed[field], str):
                        return parsed[field]
                # If no text field found, stringify the JSON
                return json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, AttributeError):
            pass
    
    # Clean up extra whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    # Handle repeated punctuation
    clean_text = re.sub(r'\.{2,}', '.', clean_text)  # Replace multiple dots with one
    clean_text = re.sub(r'([.!?])\s*\1', r'\1', clean_text)  # Deduplicate end punctuation
    
    # If the result is empty or too short, return the original (but stripped)
    if len(clean_text) < 10:
        return answer_text.strip()
    
    return clean_text.strip()

def extract_json_from_llm_response(response: str) -> Dict[str, Any]:
    """
    Extract JSON from LLM response with multiple fallback strategies.
    Enhanced to handle various response formats and nested structures.
    
    Parameters
    ----------
    response : str
        The raw text response from the LLM
        
    Returns
    -------
    Dict[str, Any]
        A dictionary containing "answer", "compliance", and "references" keys
    """
    default_result = {
        "answer": response.strip(),
        "compliance": "PC",
        "references": []
    }
    
    try:
        # Clean the response
        cleaned = response.strip()
        
        # Strategy 1: Direct JSON parsing with error handling for different formats
        try:
            # Handle root-level objects
            if cleaned.startswith('{') and cleaned.endswith('}'):
                parsed = json.loads(cleaned)
                if validate_json_structure(parsed):
                    return process_parsed_json(parsed)
                
            # Handle responses with "answers" array structure
            if '"answers"' in cleaned or "'answers'" in cleaned:
                # Extract the JSON object
                match = re.search(r'(\{[\s\S]*\})', cleaned)
                if match:
                    potential_json = match.group(1)
                    parsed = json.loads(potential_json)
                    if 'answers' in parsed:
                        # Format used in some responses: {answers: [{value: "actual answer"}]}
                        if isinstance(parsed['answers'], list) and len(parsed['answers']) > 0:
                            first_answer = parsed['answers'][0]
                            if isinstance(first_answer, dict):
                                if 'answer' in first_answer:
                                    return {
                                        "answer": first_answer['answer'],
                                        "compliance": "PC", # Default to PC for these formats
                                        "references": []
                                    }
                                elif 'value' in first_answer:
                                    return {
                                        "answer": first_answer['value'],
                                        "compliance": "PC",
                                        "references": []
                                    }
                    # If we can't extract from answers array, use the whole JSON
                    return process_parsed_json(parsed)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from code blocks
        code_block_pattern = r"```(?:json)?\s*(.*?)\s*```"
        matches = re.findall(code_block_pattern, cleaned, re.DOTALL)
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if validate_json_structure(parsed):
                    return process_parsed_json(parsed)
            except json.JSONDecodeError:
                continue

        # Strategy 3: Look for specific response patterns
        # Handle questionId pattern
        question_id_pattern = r'questionId: ([a-f0-9-]+)\. answer: (.*?)(?=\.|$)'
        match = re.search(question_id_pattern, cleaned)
        if match:
            return {
                "answer": match.group(2).strip(),
                "compliance": "PC",  # Default to PC for these formats
                "references": []
            }
            
        # Handle value pattern (seen in row 17)
        value_pattern = r'answer: value: (.*?)(?=\. metadata:|$)'
        match = re.search(value_pattern, cleaned)
        if match:
            return {
                "answer": match.group(1).strip(),
                "compliance": "PC",
                "references": []
            }

        # Strategy 4: Find any JSON object in text
        json_pattern = r'\{[\s\S]*?\}'
        matches = re.findall(json_pattern, cleaned)
        for match in matches:
            try:
                parsed = json.loads(match)
                if validate_json_structure(parsed):
                    return process_parsed_json(parsed)
            except json.JSONDecodeError:
                continue

        # Strategy 5: Extract references from text even if JSON parsing fails
        references = extract_references_from_text(response)
        if references:
            default_result["references"] = references

        # Strategy 6: Try to extract an answer from plain text if all JSON parsing fails
        # Look for sentences that might be answers
        if not ('{' in cleaned and '}' in cleaned):
            # Might be a plain text answer
            default_result["answer"] = cleaned
            return default_result

    except Exception as e:
        logger.warning(f"Error in JSON extraction: {e}")

    # Fallback: Determine compliance from text indicators
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

def process_parsed_json(parsed: Dict) -> Dict:
    """
    Process and normalize a parsed JSON structure to ensure it has the required fields.
    
    Parameters
    ----------
    parsed : Dict
        The parsed JSON dictionary
    
    Returns
    -------
    Dict
        A standardized dictionary with answer, compliance, and references
    """
    result = {
        "answer": "",
        "compliance": "PC",
        "references": []
    }
    
    # Extract answer from multiple possible locations
    if "answer" in parsed:
        result["answer"] = clean_json_answer(str(parsed["answer"]))
    elif "question" in parsed and "answer" in parsed:
        result["answer"] = clean_json_answer(str(parsed["answer"]))
    elif "answers" in parsed and isinstance(parsed["answers"], list):
        for answer_obj in parsed["answers"]:
            if isinstance(answer_obj, dict) and "answer" in answer_obj:
                result["answer"] = clean_json_answer(str(answer_obj["answer"]))
                break
            elif isinstance(answer_obj, dict) and "value" in answer_obj:
                result["answer"] = clean_json_answer(str(answer_obj["value"]))
                break
    
    # Extract compliance level
    if "compliance" in parsed:
        result["compliance"] = validate_compliance_value(parsed["compliance"])
    
    # Extract references
    if "references" in parsed and isinstance(parsed["references"], list):
        result["references"] = parsed["references"]
    
    # If we couldn't extract an answer, use the original JSON as text
    if not result["answer"]:
        result["answer"] = clean_json_answer(json.dumps(parsed))
    
    return result

def validate_json_structure(parsed: Dict) -> bool:
    """
    Validate that the parsed JSON has the required structure.
    """
    # Check for required keys
    if not all(key in parsed for key in ["answer", "compliance"]):
        return False
    
    # References is optional but must be a list if present
    if "references" in parsed and not isinstance(parsed["references"], list):
        return False
    
    # Validate types
    if not isinstance(parsed["answer"], str):
        return False
    if not isinstance(parsed["compliance"], str):
        return False
    
    # Validate compliance value
    if parsed["compliance"].upper() not in ["FC", "PC", "NC", "NA"]:
        return False
    
    # Ensure compliance is uppercase
    parsed["compliance"] = parsed["compliance"].upper()
    
    return True

def extract_references_from_text(text: str) -> List[str]:
    """
    Extract URL references from text that might contain Salesforce documentation links.
    """
    # More comprehensive URL pattern
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    urls = re.findall(url_pattern, text)
    
    # Clean and deduplicate URLs
    cleaned_urls = []
    for url in urls:
        # Remove trailing punctuation
        url = re.sub(r'[.,;:!?)\]}]+$', '', url)
        
        # Filter for Salesforce-related URLs
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

def validate_compliance_value(value: str) -> str:
    """
    Validate and normalize compliance values to standard format.
    """
    if not value:
        return "PC"  # Default to PC if empty
        
    valid_values = ["FC", "PC", "NC", "NA"]
    clean_value = value.strip().upper()
    
    if clean_value in valid_values:
        return clean_value
    
    # Map common variations
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