import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "10-0PcsDFUvT2WPGaK91UYsA0zxqOwjjrs3J6g39SYD0")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", os.path.expanduser("~/llms-env/credentials.json"))

BASE_DIR = os.getenv("BASE_DIR", os.path.expanduser("~/RAG"))
INDEX_DIR = os.getenv("INDEX_DIR", os.path.expanduser("/home/fritz/FAISSIndexV6"))
RFP_DOCUMENTS_DIR = os.getenv("RFP_DOCUMENTS_DIR", os.path.expanduser("~/RFP_Documents"))
CUSTOMER_INDEX_DIR = os.getenv("CUSTOMER_INDEX_DIR", os.path.expanduser("~/customer_indices"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
API_THROTTLE_DELAY = int(os.getenv("API_THROTTLE_DELAY", "3"))
MAX_WORDS_BEFORE_SUMMARY = int(os.getenv("MAX_WORDS_BEFORE_SUMMARY", "200"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "llamacpp")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral-small3.1")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLAMA_CPP_BASE_URL = os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8080")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/e5-large-v2")

RETRIEVER_K_DOCUMENTS = int(os.getenv("RETRIEVER_K_DOCUMENTS", "8"))
CUSTOMER_RETRIEVER_K_DOCUMENTS = int(os.getenv("CUSTOMER_RETRIEVER_K_DOCUMENTS", "2"))

QUESTION_ROLE = os.getenv("QUESTION_ROLE", "question")
CONTEXT_ROLE = os.getenv("CONTEXT_ROLE", "context")
ANSWER_ROLE = os.getenv("ANSWER_ROLE", "answer")
COMPLIANCE_ROLE = os.getenv("COMPLIANCE_ROLE", "compliance")
PRIMARY_PRODUCT_ROLE = os.getenv("PRIMARY_PRODUCT_ROLE", "primary_product")
REFERENCES_ROLE = os.getenv("REFERENCES_ROLE", "references")

CLEAN_UP_CELL_CONTENT = os.getenv("CLEAN_UP_CELL_CONTENT", "False").lower() == "true"
SUMMARIZE_LONG_CELLS = os.getenv("SUMMARIZE_LONG_CELLS", "False").lower() == "true"
INTERACTIVE_PRODUCT_SELECTION = os.getenv("INTERACTIVE_PRODUCT_SELECTION", "True").lower() == "true"

GOOGLE_API_MAX_RETRIES = int(os.getenv("GOOGLE_API_MAX_RETRIES", "3"))
GOOGLE_API_RETRY_DELAY = int(os.getenv("GOOGLE_API_RETRY_DELAY", "5"))