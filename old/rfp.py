import os
import re
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import unicodedata
import gspread
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

load_dotenv()

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "10-0PcsDFUvT2WPGaK91UYsA0zxqOwjjrs3J6g39SYD0")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", os.path.expanduser("~/llms-env/credentials.json"))
BASE_DIR = os.getenv("BASE_DIR", os.path.expanduser("~/RAG"))
INDEX_DIR = os.getenv("INDEX_DIR", os.path.expanduser("~/faiss_index_sf"))
SKIP_INDEXING = os.getenv("SKIP_INDEXING", "True").lower() == "true"
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3:12b")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/e5-large-v2")

QUESTION_ROLE = "question"
CONTEXT_ROLE = "context"
ANSWER_ROLE = "answer"
COMPLIANCE_ROLE = "compliance"

API_THROTTLE_DELAY = 1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "rag_processing.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SUMMARY_PROMPT = PromptTemplate.from_template(
    template="""
You are an experienced technical writer specialized in summarizing technical documentation.
Your task is to summarize the following document text into a concise and professional paragraph:
- Ensure key technical and business points are retained
- The summary should be targeted toward an audience of engineers and technical managers
---

Original Text:
{{ text }}

Summary:
""",
    template_format="jinja2"
)

QUESTION_PROMPT = PromptTemplate.from_template(
    template="""
You are a Senior Solution Engineer at Salesforce, with deep expertise in Salesforce products — especially Communications Cloud.

Your task is to answer the following RFI (Request for Information) question using only the provided context and any additional clues from the question. Your response must be:
- Clear
- Professional
- Focused on Salesforce product relevance

---

❗️**STEP 1: EVALUATE RELEVANCE**

Is the question relevant to Salesforce?
- About any Salesforce product (Sales Cloud, Service Cloud, Communications Cloud, etc.)?
- Concerning business processes, customer engagement, cloud platforms, or integrations?

❌ **If NOT relevant**, respond ONLY with:
{
  "compliance": "NA",
  "answer": "This question is not applicable to Salesforce or its product offerings and should be marked as out of scope."
}

---

✅ **If relevant, continue to STEP 2.**

❗️**STEP 2: DETERMINE COMPLIANCE LEVEL**

1. **FC (Fully Compliant)** - Supported via standard configuration or UI-based setup
   - No custom code required (e.g., Flow, page layouts, permissions, validation rules are NOT custom code)

2. **PC (Partially Compliant)** - Requires custom development (Apex, LWC, APIs, external integrations)

3. **NC (Not Compliant)** - Not possible in Salesforce even with customization

4. **NA (Not Applicable)** - Determined in Step 1

---

❗️**STEP 3: FORMAT**
Return ONLY:
{
  "compliance": "FC|PC|NC|NA",
  "answer": "Your concise professional explanation (5–10 sentences)"
}

Context:
{{ context_str }}

Question:
{{ question }}
Answer (JSON only):
""",
    template_format="jinja2"
)

REFINE_PROMPT = PromptTemplate.from_template(
    template="""
We are refining an earlier RFI response based on new context.

Update the JSON if:
1. Compliance level should change
2. New detail needs to be added
3. Previous answer was inaccurate

Compliance levels:
- FC: Supported via standard UI/config (Flow, page layouts, no code)
- PC: Requires custom code (Apex, LWC, APIs)
- NC: Not possible in Salesforce
- NA: Out of Salesforce scope

Only return valid JSON like this:
{
  "compliance": "FC|PC|NC|NA",
  "answer": "Your concise professional explanation (5–10 sentences)"
}

Question:
{{ question }}

Existing JSON Answer:
{{ existing_answer }}

New Context:
{{ context_str }}

Refined Answer (JSON only):
""",
    template_format="jinja2"
)

class GoogleSheetHandler:
    def __init__(self, sheet_id: str, credentials_path: str):
        try:
            self.client = gspread.service_account(filename=credentials_path)
            self.sheet = self.client.open_by_key(sheet_id).sheet1
            logger.info(f"Connected to Google Sheet with ID: {sheet_id}")
        except Exception as e:
            logger.critical(f"Failed to connect to Google Sheet: {e}")
            raise

    def load_data(self) -> Tuple[List[str], List[str], List[List[str]], Any]:
        try:
            all_values = self.sheet.get_all_values()
            if len(all_values) < 2:
                logger.warning("Sheet has insufficient data (less than 2 rows).")
                return [], [], [], self.sheet

            headers = all_values[0]
            roles = all_values[1]
            rows = all_values[2:] if len(all_values) > 2 else []

            logger.info(f"Loaded {len(rows)} data rows from Google Sheet.")
            return headers, roles, rows, self.sheet
        except Exception as e:
            logger.error(f"Error loading data from Google Sheet: {e}")
            raise

    def update_batch(self, updates: List[Dict[str, Any]]):
        try:
            if not updates:
                return

            batch_updates = []
            for update in updates:
                row, col, value = update["row"], update["col"], update["value"]
                batch_updates.append({
                    'range': f'{gspread.utils.rowcol_to_a1(row, col)}',
                    'values': [[value]]
                })

            if batch_updates:
                self.sheet.batch_update(batch_updates)
                logger.info(f"Batch updated {len(batch_updates)} cells.")
        except Exception as e:
            logger.error(f"Error performing batch update: {e}")
            raise

def parse_records(headers: List[str], roles: List[str], rows: List[List[str]]) -> List[Dict[str, Any]]:
    records = []
    for i, row in enumerate(rows):
        row_dict = {headers[j]: row[j] if j < len(row) else "" for j in range(len(headers))}
        role_map = {roles[j]: row[j] if j < len(row) else "" for j in range(len(roles))}
        records.append({
            "raw": row_dict,
            "roles": role_map,
            "sheet_row": i + 3
        })
    return records

def find_output_columns(roles: List[str]) -> Dict[str, int]:
    role_map = {}
    for idx, role in enumerate(roles):
        role_lower = role.strip().lower()
        if role_lower in (ANSWER_ROLE, COMPLIANCE_ROLE):
            role_map[role_lower] = idx + 1
    if not role_map:
        logger.warning(f"No output columns found for roles: {ANSWER_ROLE}, {COMPLIANCE_ROLE}")
    return role_map

def load_faiss_index(index_dir: str):
    try:
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        if SKIP_INDEXING:
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
    default_result = {
        "answer": response.strip(),
        "compliance": "PC"
    }
    try:
        try:
            parsed = json.loads(response.strip())
            if "answer" in parsed and "compliance" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

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

        json_pattern = r"\{.*?\}"
        matches = re.findall(json_pattern, cleaned, re.DOTALL)
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if "answer" in parsed and "compliance" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

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

def clean_text(raw_text: str) -> str:
    clean_text = raw_text.strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)
    clean_text = unicodedata.normalize('NFKD', clean_text).encode('ascii', 'ignore').decode()
    clean_text = ''.join(c for c in clean_text if c.isprintable())
    clean_text = re.sub(r'[^\w\s,.!?]', '', clean_text)
    return clean_text

def clean_up_cells(records):
    for record in records:
        for role, text in record["roles"].items():
            if role in (QUESTION_ROLE, CONTEXT_ROLE):  # Process both question and context roles
                original_text = text
                cleaned_text = clean_text(text)
                record["roles"][role] = cleaned_text
                
                # Print before and after for debugging
                print(f"Before cleaning (Row {record['sheet_row']}, Role: {role}):\n{original_text}")
                print(f"After cleaning (Row {record['sheet_row']}, Role: {role}):\n{cleaned_text}")
                
                if cleaned_text != original_text:
                    logger.info(f"Cleaned text for role: {role} in row: {record['sheet_row']}")
                    time.sleep(API_THROTTLE_DELAY)

def update_cleaned_records(sheet_handler, records, headers):
    """Update the Google Sheet with cleaned records."""
    updates = []
    for record in records:
        row_num = record["sheet_row"]
        for role, text in record["roles"].items():
            if role in (QUESTION_ROLE, CONTEXT_ROLE):  # Update specific roles
                try:
                    col_index = headers.index(role) + 1  # Find column index
                    updates.append({'row': row_num, 'col': col_index, 'value': text})
                except ValueError:
                    logger.error(f"Column {role} not found in headers, skipping update.")
                    continue

    # Perform batch update to Google Sheet
    sheet_handler.update_batch(updates)

def summarize_long_texts(records, llm):
    for record in records:
        for role, text in record["roles"].items():
            if len(text.split()) > 200:
                try:
                    print(f"Summarizing text for role: {role}")
                    summary = generate_summary(text, llm)
                    record["roles"][role] = summary
                    logger.info(f"Text for role '{role}' was summarized.")
                except Exception as e:
                    logger.error(f"Failed to generate summary for text in role '{role}': {e}")

def generate_summary(text, llm):
    result = llm.complete(prompt=SUMMARY_PROMPT, inputs={"text": text})
    summary_text = result["result"].strip()
    return summary_text

def main():
    try:
        logger.info("Starting RAG processing...")
        sheet_handler = GoogleSheetHandler(GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE)
        headers, roles, rows, sheet = sheet_handler.load_data()
        llm = OllamaLLM(model=LLM_MODEL, base_url=LLM_BASE_URL)

        records = parse_records(headers, roles, rows)

        #clean_up_cells(records)
        #Update the cleaned data back to Google Sheet
        #update_cleaned_records(sheet_handler, records)

        #summarize_long_texts(records, llm)
        
        
        output_columns = find_output_columns(roles)
        if not output_columns:
            logger.error("No output columns found. Exiting.")
            return

        retriever = load_faiss_index(INDEX_DIR).as_retriever(search_kwargs={"k": 6})
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
