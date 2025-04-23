import re
import json
import logging
import os
from typing import Dict, Any
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

def extract_json_from_llm_response(response: str) -> Dict[str, str]:
    """
    Extract JSON from LLM response with multiple fallback strategies.
    
    This function attempts to parse a JSON response from an LLM output using
    various extraction methods, falling back to simpler methods if initial
    attempts fail.
    
    Parameters
    ----------
    response : str
        The raw text response from the LLM
        
    Returns
    -------
    Dict[str, str]
        A dictionary containing at minimum "answer" and "compliance" keys
        If no valid JSON is found, returns a default dict with the entire response
        as the "answer" and "PC" as the "compliance" value
        
    Notes
    -----
    The function tries multiple strategies in this order:
    1. Direct JSON parsing of the entire response
    2. Extracting and parsing JSON from code blocks
    3. Using regex to find and parse JSON objects
    4. Removing markdown formatting and retrying JSON parsing
    5. Determining compliance from text indicators if JSON extraction fails
    """
    default_result = {
        "answer": response.strip(),
        "compliance": "PC"
    }
    try:
        # Direct JSON parsing
        try:
            parsed = json.loads(response.strip())
            if "answer" in parsed and "compliance" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        # Extract from code blocks
        cleaned = response.strip()
        code_block_pattern = r"```(?:json)?(.*?)```"
        matches = re.findall(code_block_pattern, cleaned, re.DOTALL)
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if "answer" in parsed and "compliance" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # Extract using regex pattern
        json_pattern = r"\{.*?\}"
        matches = re.findall(json_pattern, cleaned, re.DOTALL)
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if "answer" in parsed and "compliance" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # Remove markdown formatting and try again
        for prefix in ['```json', '```']:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        for suffix in ['```']:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)]
        try:
            parsed = json.loads(cleaned.strip())
            if "answer" in parsed and "compliance" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    except Exception as e:
        logger.warning(f"All JSON extraction strategies failed: {e}")

    # Fallback: Determine compliance from text indicators
    compliance_indicators = {
        "NA": ["not applicable", "out of scope", "irrelevant", "not relevant"],
        "NC": ["not compliant", "not possible", "cannot be achieved", "not supported"],
        "FC": ["fully compliant", "standard functionality", "out of the box", "built-in"],
        "PC": ["partially compliant", "customization", "configuration", "workaround"]
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

def validate_compliance_value(value: str) -> str:
    """
    Validate and normalize compliance values to standard format.
    
    This function takes a compliance value string and normalizes it to one of
    the standard compliance codes: FC, PC, NC, or NA.
    
    Parameters
    ----------
    value : str
        The compliance value to validate and normalize
        
    Returns
    -------
    str
        A normalized compliance value (one of: FC, PC, NC, NA)
        If the input value doesn't match any known format, defaults to "PC"
        
    Notes
    -----
    - FC = Fully Compliant
    - PC = Partially Compliant
    - NC = Not Compliant
    - NA = Not Applicable
    """
    valid_values = ["FC", "PC", "NC", "NA"]
    clean_value = value.strip().upper()
    if clean_value in valid_values:
        return clean_value
    if clean_value in ["FULLY COMPLIANT", "FULLY-COMPLIANT"]:
        return "FC"
    elif clean_value in ["PARTIALLY COMPLIANT", "PARTIALLY-COMPLIANT"]:
        return "PC"
    elif clean_value in ["NOT COMPLIANT", "NON COMPLIANT", "NON-COMPLIANT"]:
        return "NC"
    elif clean_value in ["NOT APPLICABLE", "N/A"]:
        return "NA"
    logger.warning(f"Invalid compliance value: '{value}', defaulting to 'PC'")
    return "PC"