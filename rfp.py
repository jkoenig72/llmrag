import os
import json
import logging
import gspread
from typing import List, Dict
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

# ────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────
GOOGLE_SHEET_ID = "10-0PcsDFUvT2WPGaK91UYsA0zxqOwjjrs3J6g39SYD0"
GOOGLE_CREDENTIALS_FILE = "/home/fritz/llms-env/credentials.json"

BASE_DIR = "/home/fritz/RAG_C"
INDEX_DIR = "/home/fritz/faiss_index_sf_e5_v1_2"
SKIP_INDEXING = True

QUESTION_ROLE = "question"
CONTEXT_ROLE = "context"
ANSWER_ROLE = "answer"
COMPLIANCE_ROLE = "compliance"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ────────────────────────────────────────────────────────────────
# Prompt Templates (plain text output)
# ────────────────────────────────────────────────────────────────
QUESTION_PROMPT = PromptTemplate(
    input_variables=["question", "context_str"],
    template="""
You are a Senior Solution Engineer at Salesforce. You have deep expertise in Salesforce products, especially Communications Cloud.

Answer the following RFP question using only the context provided and any additional relevant information from the question.

Instructions:
- Focus on Salesforce Cloud products.
- Use a professional, concise tone suitable for RFP responses.
- Include business value and product strengths.
- Return a plain text response, no JSON.

Context:
{context_str}

Question:
{question}

Answer:
"""
)

REFINE_PROMPT = PromptTemplate(
    input_variables=["question", "existing_answer", "context_str"],
    template="""
We are refining the previous answer using new additional context.

Question:
{question}

Existing Answer:
{existing_answer}

New Context:
{context_str}

Refined Answer:
"""
)

# ────────────────────────────────────────────────────────────────
# Google Sheets Utilities
# ────────────────────────────────────────────────────────────────
def load_google_sheet(sheet_id: str, credentials_path: str):
    client = gspread.service_account(filename=credentials_path)
    sheet = client.open_by_key(sheet_id).sheet1
    all_values = sheet.get_all_values()
    headers = all_values[0]
    roles = all_values[1]
    rows = all_values[2:]
    return headers, roles, rows, sheet

def parse_records(headers: List[str], roles: List[str], rows: List[List[str]]):
    records = []
    for i, row in enumerate(rows):
        row_dict = {headers[j]: row[j] if j < len(row) else "" for j in range(len(headers))}
        role_map = {roles[j]: row[j] if j < len(row) else "" for j in range(len(roles))}
        records.append({
            "raw": row_dict,
            "roles": role_map,
            "sheet_row": i + 3  # +3 for header + role rows + 1-based indexing
        })
    return records

def find_output_columns(headers: List[str], roles: List[str]) -> Dict[str, int]:
    role_map = {}
    for idx, role in enumerate(roles):
        role_lower = role.strip().lower()
        if role_lower in (ANSWER_ROLE, COMPLIANCE_ROLE):
            role_map[role_lower] = idx + 1  # 1-based for gspread
    return role_map

def update_output_fields(sheet, row: int, values: Dict[str, str], output_columns: Dict[str, int]):
    for role, content in values.items():
        col = output_columns.get(role.lower())
        if col:
            try:
                sheet.update_cell(row, col, content)
                logging.info(f"✅ Updated row {row}, column '{role}' → {content[:40]}...")
            except Exception as e:
                logging.error(f"❌ Failed to update cell {role} at row {row}: {e}")

# ────────────────────────────────────────────────────────────────
# FAISS Retriever
# ────────────────────────────────────────────────────────────────
def load_faiss_index(index_dir: str):
    embeddings = HuggingFaceEmbeddings(model_name="intfloat/e5-large-v2")
    if SKIP_INDEXING:
        if os.path.exists(index_dir):
            logging.info("Loading FAISS index from disk...")
            return FAISS.load_local(index_dir, embeddings, allow_dangerous_deserialization=True)
        raise FileNotFoundError(f"FAISS index not found at {index_dir}")
    raise NotImplementedError("Indexing disabled.")

# ────────────────────────────────────────────────────────────────
# Main Execution
# ────────────────────────────────────────────────────────────────
def main():
    headers, roles, rows, sheet = load_google_sheet(GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE)
    records = parse_records(headers, roles, rows)
    output_columns = find_output_columns(headers, roles)
    logging.info(f"Loaded {len(records)} records from Google Sheet.")

    retriever = load_faiss_index(INDEX_DIR).as_retriever(search_kwargs={"k": 3})
    llm = OllamaLLM(model="deepseek-coder-v2:16b", base_url="http://localhost:11434")

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

    for record in records:
        row_num = record["sheet_row"]
        question = record["roles"].get(QUESTION_ROLE, "").strip()
        if not question:
            logging.warning(f"⏭️ Row {row_num} skipped: No question found.")
            continue

        additional_context = "\n".join([
            f"{k}: {v}" for k, v in record["roles"].items()
            if k.strip().lower() == CONTEXT_ROLE and v.strip()
        ]).strip() or "N/A"

        enriched_question = f"{question}\n\n[Additional Info]\n{additional_context}"

        try:
            result = qa_chain.invoke({"question": enriched_question})
            answer_text = result["result"].strip()

            update_output_fields(
                sheet,
                row_num,
                {
                    "answer": answer_text,
                    "compliance": "FC" if "fully" in answer_text.lower() else "PC"  # crude default
                },
                output_columns
            )

            print("\n" + "=" * 40)
            print(f"✅ Row {row_num} complete")
            print(f"Question: {question}")
            print(f"Answer:\n{answer_text}")
            print("=" * 40)

        except Exception as e:
            logging.error(f"❌ Failed to process row {row_num}: {e}")

if __name__ == "__main__":
    main()
