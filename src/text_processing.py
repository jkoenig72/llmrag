import re
import time
import logging
import unicodedata
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

def clean_text(raw_text: str) -> str:
    """Clean and normalize text by removing special characters and extra whitespace."""
    clean_text = raw_text.strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)
    clean_text = unicodedata.normalize('NFKD', clean_text).encode('ascii', 'ignore').decode()
    clean_text = ''.join(c for c in clean_text if c.isprintable())
    clean_text = re.sub(r'[^\w\s,.!?]', '', clean_text)
    return clean_text

def clean_up_cells(records, question_role, context_role, api_throttle_delay=1):
    """Clean text in specific roles for all records."""
    for record in records:
        for role, text in record["roles"].items():
            if role in (question_role, context_role):  # Process both question and context roles
                original_text = text
                cleaned_text = clean_text(text)
                record["roles"][role] = cleaned_text
                
                # Print before and after for debugging
                print(f"Before cleaning (Row {record['sheet_row']}, Role: {role}):\n{original_text}")
                print(f"After cleaning (Row {record['sheet_row']}, Role: {role}):\n{cleaned_text}")
                
                if cleaned_text != original_text:
                    logger.info(f"Cleaned text for role: {role} in row: {record['sheet_row']}")
                    time.sleep(api_throttle_delay)

def generate_summary(text, llm, summary_prompt):
    """Generate a summary of the given text using the LLM."""
    result = llm.complete(prompt=summary_prompt, inputs={"text": text})
    summary_text = result["result"].strip()
    return summary_text

def summarize_long_texts(records, llm, summary_prompt, word_limit=200):
    """Summarize texts that are longer than the specified word limit."""
    for record in records:
        for role, text in record["roles"].items():
            if len(text.split()) > word_limit:
                try:
                    print(f"Summarizing text for role: {role}")
                    summary = generate_summary(text, llm, summary_prompt)
                    record["roles"][role] = summary
                    logger.info(f"Text for role '{role}' was summarized.")
                except Exception as e:
                    logger.error(f"Failed to generate summary for text in role '{role}': {e}")