import re
import time
import logging
import unicodedata
from typing import Dict, List, Any, Optional
from config import get_config

logger = logging.getLogger(__name__)
config = get_config()

class TextProcessor:
    """
    Utility class for processing and transforming text.
    
    Provides methods for cleaning, summarizing, and formatting text content
    for use in RFP processing.
    """
    
    @staticmethod
    def clean_text(raw_text: str) -> str:
        """
        Clean and normalize text by removing special characters and normalizing whitespace.
        
        Args:
            raw_text: The text to clean
            
        Returns:
            Cleaned and normalized text
        """
        if not raw_text:
            return ""
            
        original = raw_text

        clean = raw_text.strip()
        clean = re.sub(r'[\u2022\u2023\u25E6\u2043\u2219\-\*]+', ',', clean)
        clean = re.sub(r'\s+', ' ', clean)

        clean = unicodedata.normalize('NFKD', clean).encode('ascii', 'ignore').decode()

        clean = ''.join(c for c in clean if c.isprintable())

        clean = re.sub(r'[!?.,]{2,}', lambda m: m.group(0)[0], clean)

        clean = re.sub(r'[^\w\s,.!?]', '', clean)

        logger.debug("Cleaned text (first 100 chars):\nBefore: %s\nAfter: %s", original[:100], clean[:100])
        return clean
    
    @classmethod
    def clean_up_cells(cls, records: List[Dict[str, Any]], question_role: str, context_role: str, api_throttle_delay: int = 1) -> None:
        """
        Clean up question and context cells in records.
        
        Args:
            records: List of record dictionaries to process
            question_role: Role name for question fields
            context_role: Role name for context fields
            api_throttle_delay: Delay between API calls in seconds
        """
        for record in records:
            for role, text in record["roles"].items():
                if role in (question_role, context_role):
                    original_text = text
                    cleaned_text = cls.clean_text(text)
                    record["roles"][role] = cleaned_text

                    print(f"Before cleaning (Row {record['sheet_row']}, Role: {role}):\n{original_text}")
                    print(f"After cleaning (Row {record['sheet_row']}, Role: {role}):\n{cleaned_text}")

                    if cleaned_text != original_text:
                        logger.info(f"Cleaned text for role: {role} in row: {record['sheet_row']}")
                        time.sleep(api_throttle_delay)
    
    @staticmethod
    def generate_summary(text: str, llm: Any, summary_prompt: Any) -> str:
        """
        Generate a summary of the provided text using an LLM.
        
        Args:
            text: Text to summarize
            llm: Language model instance to use for summarization
            summary_prompt: Prompt template for summarization
            
        Returns:
            Summarized text
        """
        formatted_prompt = summary_prompt.format(text=text)
        print("\n--- Prompt Sent to LLM ---\n", formatted_prompt, "\n-------------------------\n")
        result = llm.invoke(formatted_prompt)
        return result.strip()
    
    @classmethod
    def summarize_long_texts(cls, records: List[Dict[str, Any]], llm: Any, summary_prompt: Any, 
                           word_limit: int = None) -> None:
        """
        Summarize long text fields in records.
        
        Args:
            records: List of record dictionaries to process
            llm: Language model instance to use for summarization
            summary_prompt: Prompt template for summarization
            word_limit: Maximum number of words before summarization is needed
        """
        config = get_config()
        if word_limit is None:
            word_limit = config.max_words_before_summary
            
        for record in records:
            for role, text in record["roles"].items():
                if role.startswith("cleaned_"):
                    continue
                    
                if len(text.split()) > word_limit:
                    try:
                        print(f"\n[SUMMARY] Row {record['sheet_row']}, Role: {role}\nBefore:\n{text}\n")
                        summary = cls.generate_summary(text, llm, summary_prompt)
                        print(f"After:\n{summary}\n")
                        record["roles"][role] = summary
                        logger.info(f"Text for role '{role}' was summarized.")
                    except Exception as e:
                        logger.error(f"Failed to generate summary for text in role '{role}': {e}")
    
    @staticmethod
    def truncate_text(text: str, max_length: int, preserve_words: bool = True) -> str:
        """
        Truncate text to a maximum length, preserving word boundaries if specified.
        
        Args:
            text: Text to truncate
            max_length: Maximum length in characters
            preserve_words: Whether to preserve word boundaries
            
        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
            
        if preserve_words:
            return text[:max_length].rsplit(' ', 1)[0] + '...'
        else:
            return text[:max_length] + '...'