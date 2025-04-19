import os
from dotenv import load_dotenv

load_dotenv()

# Google Sheets Configuration
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "10-0PcsDFUvT2WPGaK91UYsA0zxqOwjjrs3J6g39SYD0")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", os.path.expanduser("~/llms-env/credentials.json"))

# Directory Configuration
BASE_DIR = os.getenv("BASE_DIR", os.path.expanduser("~/RAG"))
INDEX_DIR = os.getenv("INDEX_DIR", os.path.expanduser("~/faiss_index_sf"))

# Processing Configuration
SKIP_INDEXING = os.getenv("SKIP_INDEXING", "True").lower() == "true"
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
API_THROTTLE_DELAY = 1

# Model Configuration
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3:12b")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/e5-large-v2")

# Role Definitions
QUESTION_ROLE = "question"
CONTEXT_ROLE = "context"
ANSWER_ROLE = "answer"
COMPLIANCE_ROLE = "compliance"