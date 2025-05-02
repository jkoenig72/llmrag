import re
import time
import logging
import unicodedata
from typing import Dict, List, Any
from config import MAX_WORDS_BEFORE_SUMMARY

logger = logging.getLogger(__name__)

def clean_text(raw_text: str) -> str:
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

def clean_up_cells(records, question_role, context_role, api_throttle_delay=1):
    for record in records:
        for role, text in record["roles"].items():
            if role in (question_role, context_role):
                original_text = text
                cleaned_text = clean_text(text)
                record["roles"][role] = cleaned_text

                print(f"Before cleaning (Row {record['sheet_row']}, Role: {role}):\n{original_text}")
                print(f"After cleaning (Row {record['sheet_row']}, Role: {role}):\n{cleaned_text}")

                if cleaned_text != original_text:
                    logger.info(f"Cleaned text for role: {role} in row: {record['sheet_row']}")
                    time.sleep(api_throttle_delay)

def generate_summary(text, llm, summary_prompt):
    formatted_prompt = summary_prompt.format(text=text)
    print("\n--- Prompt Sent to LLM ---\n", formatted_prompt, "\n-------------------------\n")
    result = llm.invoke(formatted_prompt)
    return result.strip()

def summarize_long_texts(records, llm, summary_prompt, word_limit=MAX_WORDS_BEFORE_SUMMARY):
    for record in records:
        for role, text in record["roles"].items():
            if role.startswith("cleaned_"):
                continue
                
            if len(text.split()) > word_limit:
                try:
                    print(f"\n[SUMMARY] Row {record['sheet_row']}, Role: {role}\nBefore:\n{text}\n")
                    summary = generate_summary(text, llm, summary_prompt)
                    print(f"After:\n{summary}\n")
                    record["roles"][role] = summary
                    logger.info(f"Text for role '{role}' was summarized.")
                except Exception as e:
                    logger.error(f"Failed to generate summary for text in role '{role}': {e}")