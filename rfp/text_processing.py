import re
import time
import logging
import unicodedata
from typing import Dict, List, Any
from config import MAX_WORDS_BEFORE_SUMMARY

logger = logging.getLogger(__name__)

def clean_text(raw_text: str) -> str:
    """
    Clean and normalize text by removing special characters and extra whitespace.
    
    This function performs multiple text normalization operations including:
    - Trimming whitespace
    - Replacing bullets/dashes with commas
    - Normalizing Unicode characters
    - Removing non-printable characters
    - Reducing excessive punctuation
    
    Parameters
    ----------
    raw_text : str
        The raw text to be cleaned
        
    Returns
    -------
    str
        The cleaned and normalized text
        
    Notes
    -----
    The cleaning process will convert special characters like bullets to commas,
    normalize Unicode (e.g., é -> e), and remove excessive punctuation.
    """
    original = raw_text

    # Trim and normalize whitespace
    clean = raw_text.strip()
    clean = re.sub(r'[\u2022\u2023\u25E6\u2043\u2219\-\*]+', ',', clean)  # Replace bullets/dashes with comma
    clean = re.sub(r'\s+', ' ', clean)  # Collapse all whitespace

    # Normalize Unicode (e.g., é -> e)
    clean = unicodedata.normalize('NFKD', clean).encode('ascii', 'ignore').decode()

    # Strip non-printables
    clean = ''.join(c for c in clean if c.isprintable())

    # Remove excessive punctuation (e.g., "!!!", "....")
    clean = re.sub(r'[!?.,]{2,}', lambda m: m.group(0)[0], clean)

    # Final pass: remove remaining strange symbols except standard ones
    clean = re.sub(r'[^\w\s,.!?]', '', clean)

    logger.debug("Cleaned text (first 100 chars):\nBefore: %s\nAfter: %s", original[:100], clean[:100])
    return clean

def clean_up_cells(records, question_role, context_role, api_throttle_delay=1):
    """
    Clean text in specific roles for all records.
    
    Applies text cleaning to question and context fields in each record,
    with optional throttling between API calls.
    
    Parameters
    ----------
    records : List[Dict]
        List of record dictionaries, each containing a "roles" dictionary
    question_role : str
        The key identifying question role fields in the record's roles dict
    context_role : str
        The key identifying context role fields in the record's roles dict
    api_throttle_delay : int, default 1
        Number of seconds to wait between processing records
        
    Returns
    -------
    None
        Modifies the records in place
        
    Notes
    -----
    This function will print before/after cleaning results and log changes.
    It applies throttling between changes to prevent API rate limiting.
    """
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
    """
    Generate a summary of the given text using the LLM.
    
    Parameters
    ----------
    text : str
        The text to summarize
    llm : Any
        Language model instance with an invoke method
    summary_prompt : Any
        Prompt template for summarization
        
    Returns
    -------
    str
        The generated summary text
        
    Notes
    -----
    This function will print the prompt sent to the LLM for debugging purposes.
    """
    formatted_prompt = summary_prompt.format(text=text)
    print("\n--- Prompt Sent to LLM ---\n", formatted_prompt, "\n-------------------------\n")
    result = llm.invoke(formatted_prompt)
    return result.strip()

def summarize_long_texts(records, llm, summary_prompt, word_limit=MAX_WORDS_BEFORE_SUMMARY):
    """
    Summarize texts that are longer than the specified word limit.
    
    For each text field that exceeds the word limit, generates a summary
    using the provided language model and prompt template.
    
    Parameters
    ----------
    records : List[Dict]
        List of record dictionaries, each containing a "roles" dictionary
    llm : Any
        Language model instance with an invoke method
    summary_prompt : Any
        Prompt template for summarization
    word_limit : int, default from config
        Maximum number of words before summarization is applied
        
    Returns
    -------
    None
        Modifies the records in place
        
    Notes
    -----
    This function will print before/after summaries and log changes.
    If summarization fails for any reason, the error is logged but processing continues.
    """
    for record in records:
        for role, text in record["roles"].items():
            if len(text.split()) > word_limit:
                try:
                    print(f"\n[SUMMARY] Row {record['sheet_row']}, Role: {role}\nBefore:\n{text}\n")
                    summary = generate_summary(text, llm, summary_prompt)
                    print(f"After:\n{summary}\n")
                    record["roles"][role] = summary
                    logger.info(f"Text for role '{role}' was summarized.")
                except Exception as e:
                    logger.error(f"Failed to generate summary for text in role '{role}': {e}")