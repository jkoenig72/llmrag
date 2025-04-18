import os
import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import gspread
from dotenv import load_dotenv
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

# ────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────
# Load environment variables from .env file
load_dotenv()

# Load configuration from environment variables or use defaults
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "10-0PcsDFUvT2WPGaK91UYsA0zxqOwjjrs3J6g39SYD0")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", os.path.expanduser("~/llms-env/credentials.json"))

BASE_DIR = os.getenv("BASE_DIR", os.path.expanduser("~/RAG"))
INDEX_DIR = os.getenv("INDEX_DIR", os.path.expanduser("~/faiss_index_sf"))
SKIP_INDEXING = os.getenv("SKIP_INDEXING", "True").lower() == "true"
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
LLM_MODEL = os.getenv("LLM_MODEL", "mistral-small3.1")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/e5-large-v2")

# Role definitions
QUESTION_ROLE = "question"
CONTEXT_ROLE = "context"
ANSWER_ROLE = "answer"
COMPLIANCE_ROLE = "compliance"

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

# ────────────────────────────────────────────────────────────────
# Improved Prompt Templates with clearer compliance guidelines
# ────────────────────────────────────────────────────────────────
QUESTION_PROMPT = PromptTemplate.from_template(
    template="""
You are a Senior Solution Engineer at Salesforce, with deep expertise in Salesforce products — especially Communications Cloud.

Your task is to answer the following RFI (Request for Information) question using only the provided context and any additional clues from the question. Your response must be:
- Clear
- Professional
- Focused on Salesforce product relevance

---

❗️**STEP 1: EVALUATE RELEVANCE**

First, determine if the question is relevant to Salesforce products or capabilities:
- Is it about any Salesforce product (Sales Cloud, Service Cloud, Communications Cloud, etc.)?
- Does it concern business processes, customer engagement, cloud platforms, or integrations?
- Is it asking about functionality that would be expected in an enterprise CRM/PaaS system?

---

❌ **If the question is NOT relevant to Salesforce, respond ONLY with this exact JSON:**

{
  "compliance": "NA",
  "answer": "This question is not applicable to Salesforce or its product offerings and should be marked as out of scope."
}

Examples of irrelevant (NA) questions:
- "What do you think about Alexander the Great?"
- "Is red a better color than green?"
- "What will the weather be tomorrow?"
- "Explain gravity"
- "What is your favorite color?"

---

✅ **If the question IS relevant to Salesforce, proceed to STEP 2.**

---

❗️**STEP 2: DETERMINE COMPLIANCE LEVEL**

Based on the context and your knowledge, determine the compliance level:

1. **FC (Fully Compliant)** - Feature/capability is completely supported by Salesforce out-of-the-box:
   - Standard functionality without customization
   - Available in the described product line
   - Matches all requested criteria
   
   Example: "Does Salesforce support case management?" would be FC because Service Cloud has built-in case management.

2. **PC (Partially Compliant)** - Feature is supported but with limitations:
   - Requires configuration, customization, or AppExchange products
   - Available but doesn't meet all requirements
   - Requires workarounds or development
   
   Example: "Can Salesforce create custom dashboards for network performance?" would be PC because it requires custom development or integration.

3. **NC (Not Compliant)** - Feature is NOT possible in Salesforce:
   - Fundamentally incompatible with Salesforce architecture
   - Violates platform limitations or security model
   - Cannot be achieved even with customization
   
   Example: "Can Salesforce replace our network routing hardware?" would be NC because Salesforce is software, not hardware.

4. **NA (Not Applicable)** - Question is out of scope (determined in STEP 1)

---

❗️**STEP 3: FORMAT YOUR RESPONSE**

Respond ONLY in this exact JSON format with no additional text:

{
  "compliance": "FC|PC|NC|NA",
  "answer": "Your concise professional explanation (5-10 sentences)"
}

---

Final instructions:
- Your answer must be strictly valid JSON
- No markdown, commentary, or explanation outside the JSON structure
- Be precise about compliance level based on the criteria above
- Do not hedge or be vague about compliance - choose the most appropriate level

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
We are refining an earlier RFI response based on new context information.

Review the existing answer and the new context. Then update the JSON if the new context:
1. Provides information that changes the compliance level
2. Adds important details to the answer
3. Corrects information in the previous answer

Compliance level guidelines:
- FC (Fully Compliant): Standard out-of-box functionality with no customization
- PC (Partially Compliant): Requires configuration, customization, or workarounds
- NC (Not Compliant): Cannot be achieved with Salesforce in any way
- NA (Not Applicable): Out of scope for Salesforce

Your response must be ONLY valid JSON with this exact structure:

{
  "compliance": "FC|PC|NC|NA",
  "answer": "Your concise professional explanation (5-10 sentences)"
}

Important:
- Do not repeat information unnecessarily
- Keep the answer concise and focused
- Return only valid JSON without any explanation text or markdown
- If the new context doesn't change anything, return the existing answer unchanged
- Focus on accuracy and clarity

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

# ────────────────────────────────────────────────────────────────
# Google Sheets Utilities
# ────────────────────────────────────────────────────────────────
class GoogleSheetHandler:
    def __init__(self, sheet_id: str, credentials_path: str):
        """Initialize the Google Sheets Handler."""
        try:
            self.client = gspread.service_account(filename=credentials_path)
            self.sheet = self.client.open_by_key(sheet_id).sheet1
            logger.info(f"Connected to Google Sheet with ID: {sheet_id}")
        except Exception as e:
            logger.critical(f"Failed to connect to Google Sheet: {e}")
            raise

    def load_data(self) -> Tuple[List[str], List[str], List[List[str]], Any]:
        """Load data from the Google Sheet."""
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
        """Update multiple cells in batch mode for better performance."""
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
    """Parse data from the sheet into structured records."""
    records = []
    for i, row in enumerate(rows):
        row_dict = {headers[j]: row[j] if j < len(row) else "" for j in range(len(headers))}
        role_map = {roles[j]: row[j] if j < len(row) else "" for j in range(len(roles))}
        records.append({
            "raw": row_dict,
            "roles": role_map,
            "sheet_row": i + 3  # +3 due to header and role rows
        })
    return records

def find_output_columns(roles: List[str]) -> Dict[str, int]:
    """Find columns for output values based on the role row."""
    role_map = {}
    for idx, role in enumerate(roles):
        role_lower = role.strip().lower()
        if role_lower in (ANSWER_ROLE, COMPLIANCE_ROLE):
            role_map[role_lower] = idx + 1  # +1 due to 1-based index in gspread
    
    if not role_map:
        logger.warning(f"No output columns found for roles: {ANSWER_ROLE}, {COMPLIANCE_ROLE}")
        
    return role_map

# ────────────────────────────────────────────────────────────────
# FAISS Retriever
# ────────────────────────────────────────────────────────────────
def load_faiss_index(index_dir: str):
    """Load the FAISS index from disk."""
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

# ────────────────────────────────────────────────────────────────
# LLM Output Processing
# ────────────────────────────────────────────────────────────────
def extract_json_from_llm_response(response: str) -> Dict[str, str]:
    """
    Extracts JSON from the LLM response with improved robustness.
    Uses multiple strategies to find and parse valid JSON.
    Returns a default dictionary if no valid JSON is found.
    """
    default_result = {
        "answer": response.strip(),
        "compliance": "PC"  # Default compliance
    }
    
    # Try different strategies to extract JSON
    try:
        # Strategy 1: Direct JSON parsing of the whole response
        try:
            parsed = json.loads(response.strip())
            if "answer" in parsed and "compliance" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Look for JSON within code blocks
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
        
        # Strategy 3: Look for { } patterns
        json_pattern = r"\{.*?\}"
        matches = re.findall(json_pattern, cleaned, re.DOTALL)
        
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if "answer" in parsed and "compliance" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
        
        # Strategy 4: Try to clean up the response by removing common prefixes/suffixes
        for prefix in ['```json', '```']:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        for suffix in ['```']:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)]
        
        # Try one more time with the cleaned text
        try:
            parsed = json.loads(cleaned.strip())
            if "answer" in parsed and "compliance" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
            
    except Exception as e:
        logger.warning(f"All JSON extraction strategies failed: {e}")
    
    # If we still don't have valid JSON, check if we can determine compliance from text
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
    Ensures compliance value is valid.
    Maps variations to standard forms.
    """
    valid_values = ["FC", "PC", "NC", "NA"]
    
    # Normalize value
    clean_value = value.strip().upper()
    
    # Check for exact matches
    if clean_value in valid_values:
        return clean_value
    
    # Map variations to standards
    if clean_value in ["FULLY COMPLIANT", "FULLY-COMPLIANT"]:
        return "FC"
    elif clean_value in ["PARTIALLY COMPLIANT", "PARTIALLY-COMPLIANT"]:
        return "PC"
    elif clean_value in ["NOT COMPLIANT", "NON COMPLIANT", "NON-COMPLIANT"]:
        return "NC"
    elif clean_value in ["NOT APPLICABLE", "N/A"]:
        return "NA"
    
    # Default to PC if no match
    logger.warning(f"Invalid compliance value: '{value}', defaulting to 'PC'")
    return "PC"

# ────────────────────────────────────────────────────────────────
# Main Execution
# ────────────────────────────────────────────────────────────────
def main():
    try:
        logger.info("Starting RAG processing...")
        
        # Load Google Sheet
        sheet_handler = GoogleSheetHandler(GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE)
        headers, roles, rows, sheet = sheet_handler.load_data()
        records = parse_records(headers, roles, rows)
        output_columns = find_output_columns(roles)
        
        if not output_columns:
            logger.error("No output columns found. Exiting.")
            return
            
        # Initialize FAISS and LLM
        try:
            retriever = load_faiss_index(INDEX_DIR).as_retriever(search_kwargs={"k": 10})
            llm = OllamaLLM(model=LLM_MODEL, base_url=LLM_BASE_URL)
            
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
        except Exception as e:
            logger.critical(f"Failed to initialize retriever or LLM: {e}")
            return
        
        # Batch process records
        batch_updates = []
        
        for i, record in enumerate(records):
            row_num = record["sheet_row"]
            question = record["roles"].get(QUESTION_ROLE, "").strip()
            
            if not question:
                logger.warning(f"⏭️ Row {row_num} skipped: No question found.")
                continue
                
            # Process additional context
            additional_context = "\n".join([
                f"{k}: {v}" for k, v in record["roles"].items()
                if k.strip().lower() == CONTEXT_ROLE and v.strip()
            ]).strip() or "N/A"
            
            enriched_question = f"{question}\n\n[Additional Info]\n{additional_context}"
            
            try:
                # Get LLM response
                result = qa_chain.invoke({"question": enriched_question})
                raw_answer = result["result"].strip()
                
                # Parse JSON response
                parsed = extract_json_from_llm_response(raw_answer)
                answer_text = parsed.get("answer", "")
                compliance_value = validate_compliance_value(parsed.get("compliance", "PC"))
                
                # Collect updates for batch processing
                for role, col in output_columns.items():
                    if role == ANSWER_ROLE:
                        batch_updates.append({"row": row_num, "col": col, "value": answer_text})
                    elif role == COMPLIANCE_ROLE:
                        batch_updates.append({"row": row_num, "col": col, "value": compliance_value})
                
                # Execute batch updates when batch size is reached or final record
                if len(batch_updates) >= BATCH_SIZE or i == len(records) - 1:
                    sheet_handler.update_batch(batch_updates)
                    batch_updates = []
                
                logger.info(f"✅ Row {row_num} processed - Compliance: {compliance_value}")
                
                # Print summary for current record
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