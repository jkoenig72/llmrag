import logging
import os
import time
from typing import List, Dict, Any
from langchain_ollama import OllamaLLM
from langchain.chains import RetrievalQA

# Import from local modules
from config import (
    GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, BASE_DIR, INDEX_DIR, 
    SKIP_INDEXING, BATCH_SIZE, LLM_MODEL, LLM_BASE_URL, EMBEDDING_MODEL,
    QUESTION_ROLE, CONTEXT_ROLE, ANSWER_ROLE, COMPLIANCE_ROLE, API_THROTTLE_DELAY
)
from prompts import SUMMARY_PROMPT, QUESTION_PROMPT, REFINE_PROMPT
from sheets_handler import GoogleSheetHandler, parse_records, find_output_columns, update_cleaned_records
from text_processing import clean_text, clean_up_cells, summarize_long_texts
from llm_utils import load_faiss_index, extract_json_from_llm_response, validate_compliance_value

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "rag_processing.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("Starting RAG processing...")
        sheet_handler = GoogleSheetHandler(GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE)
        headers, roles, rows, sheet = sheet_handler.load_data()
        llm = OllamaLLM(model=LLM_MODEL, base_url=LLM_BASE_URL)

        records = parse_records(headers, roles, rows)

        # Text cleaning and summarization (commented out for now)
        # clean_up_cells(records, QUESTION_ROLE, CONTEXT_ROLE, API_THROTTLE_DELAY)
        # update_cleaned_records(sheet_handler, records, headers, QUESTION_ROLE, CONTEXT_ROLE)
        # summarize_long_texts(records, llm, SUMMARY_PROMPT)
        
        output_columns = find_output_columns(roles, ANSWER_ROLE, COMPLIANCE_ROLE)
        if not output_columns:
            logger.error("No output columns found. Exiting.")
            return

        retriever = load_faiss_index(INDEX_DIR, EMBEDDING_MODEL, SKIP_INDEXING).as_retriever(search_kwargs={"k": 6})
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=retriever,
            chain_type="refine",
            input_key="question",
            return_source_documents=True,
            chain_type_kwargs={
                "question_prompt": QUESTION_PROMPT,
                "refine_prompt": REFINE_PROMPT
            }
        )

        batch_updates = []
        for i, record in enumerate(records):
            row_num = record["sheet_row"]
            question = clean_text(record["roles"].get(QUESTION_ROLE, ""))
            additional_context = clean_text("\n".join([
                f"{k}: {v}" for k, v in record["roles"].items()
                if k.strip().lower() == CONTEXT_ROLE and v.strip()
            ]).strip() or "N/A")

            if not question:
                logger.warning(f"⏭️ Row {row_num} skipped: No question found.")
                continue

            enriched_question = f"{question}\n\n[Additional Info]\n{additional_context}"

            try:
                result = qa_chain.invoke({"question": enriched_question})
                raw_answer = result["result"].strip()
                parsed = extract_json_from_llm_response(raw_answer)
                answer_text = parsed.get("answer", "")
                compliance_value = validate_compliance_value(parsed.get("compliance", "PC"))

                for role, col in output_columns.items():
                    if role == ANSWER_ROLE:
                        batch_updates.append({"row": row_num, "col": col, "value": answer_text})
                    elif role == COMPLIANCE_ROLE:
                        batch_updates.append({"row": row_num, "col": col, "value": compliance_value})

                if len(batch_updates) >= BATCH_SIZE or i == len(records) - 1:
                    sheet_handler.update_batch(batch_updates)
                    batch_updates = []

                logger.info(f"✅ Row {row_num} processed - Compliance: {compliance_value}")
                print("\n" + "=" * 40)
                print(f"✅ Row {row_num} complete")
                print(f"Question: {question}")
                print(f"Answer: {answer_text}")
                print(f"Compliance: {compliance_value}")
                print("=" * 40)

            except Exception as e:
                logger.error(f"❌ Failed to process row {row_num}: {e}")

        logger.info("RAG processing completed successfully.")

    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}")

if __name__ == "__main__":
    main()