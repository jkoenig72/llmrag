import re
import json
import logging
import os
import warnings
from typing import Dict, Any, List
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

logger = logging.getLogger(__name__)

def load_faiss_index(index_dir: str, embedding_model: str, skip_indexing: bool = True):
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

class StrictJSONOutputParser:
    @staticmethod
    def parse(text: str) -> Dict:
        warnings.warn(
            "StrictJSONOutputParser.parse() is deprecated. Use extract_json_from_llm_response() instead.",
            DeprecationWarning, 
            stacklevel=2
        )
        
        return extract_json_from_llm_response(text)

def load_products_from_json():
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

def extract_json_from_llm_response(response: str) -> Dict[str, Any]:
    default_result = {
        "answer": response.strip(),
        "compliance": "PC",
        "references": []
    }
    
    try:
        cleaned = response.strip()
        
        try:
            if cleaned.startswith('{') and cleaned.endswith('}'):
                parsed = json.loads(cleaned)
                if validate_json_structure(parsed):
                    return _process_parsed_json(parsed)
                
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
                    return _process_parsed_json(parsed)
        except json.JSONDecodeError:
            pass

        code_block_pattern = r"```(?:json)?\s*(.*?)\s*```"
        matches = re.findall(code_block_pattern, cleaned, re.DOTALL)
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if validate_json_structure(parsed):
                    return _process_parsed_json(parsed)
            except json.JSONDecodeError:
                continue

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

        json_pattern = r'\{[\s\S]*?\}'
        matches = re.findall(json_pattern, cleaned)
        for match in matches:
            try:
                parsed = json.loads(match)
                if validate_json_structure(parsed):
                    return _process_parsed_json(parsed)
            except json.JSONDecodeError:
                continue

        references = extract_references_from_text(response)
        if references:
            default_result["references"] = references

        if not ('{' in cleaned and '}' in cleaned):
            default_result["answer"] = cleaned
            return default_result

    except Exception as e:
        logger.warning(f"Error in JSON extraction: {e}")

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

def _process_parsed_json(parsed: Dict) -> Dict:
    result = {
        "answer": "",
        "compliance": "PC",
        "references": []
    }
    
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
    
    if "compliance" in parsed:
        result["compliance"] = validate_compliance_value(parsed["compliance"])
    
    if "references" in parsed and isinstance(parsed["references"], list):
        result["references"] = parsed["references"]
    
    if not result["answer"]:
        result["answer"] = clean_json_answer(json.dumps(parsed))
    
    return result

def validate_json_structure(parsed: Dict) -> bool:
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

def extract_references_from_text(text: str) -> List[str]:
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    urls = re.findall(url_pattern, text)
    
    cleaned_urls = []
    for url in urls:
        url = re.sub(r'[.,;:!?)\]}]+$', '', url)
        
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