import os
from dotenv import load_dotenv

load_dotenv()

# Google Sheets Configuration
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "10-0PcsDFUvT2WPGaK91UYsA0zxqOwjjrs3J6g39SYD0")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", os.path.expanduser("~/llms-env/credentials.json"))

# Directory Configuration
BASE_DIR = os.getenv("BASE_DIR", os.path.expanduser("~/RAG"))
INDEX_DIR = os.getenv("INDEX_DIR", os.path.expanduser("/home/fritz/FAISSIndexV6"))
RFP_DOCUMENTS_DIR = os.getenv("RFP_DOCUMENTS_DIR", os.path.expanduser("~/RFP_Documents"))
CUSTOMER_INDEX_DIR = os.getenv("CUSTOMER_INDEX_DIR", os.path.expanduser("~/customer_indices"))

# Processing Configuration
# DEPRECATED: SKIP_INDEXING is deprecated and will be removed in a future version.
#             The system now uses EmbeddingManager for dynamic embedding loading.
SKIP_INDEXING = os.getenv("SKIP_INDEXING", "True").lower() == "true"
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
API_THROTTLE_DELAY = int(os.getenv("API_THROTTLE_DELAY", "3"))  # Increased from 1 to 3 seconds
MAX_WORDS_BEFORE_SUMMARY = int(os.getenv("MAX_WORDS_BEFORE_SUMMARY", "200"))

# Model Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "llamacpp")  # "ollama" or "llamacpp"
LLM_MODEL = os.getenv("LLM_MODEL", "mistral-small3.1")  # Used for ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLAMA_CPP_BASE_URL = os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8080")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/e5-large-v2")

# Retriever Configuration
RETRIEVER_K_DOCUMENTS = int(os.getenv("RETRIEVER_K_DOCUMENTS", "6"))  # Number of documents to retrieve
CUSTOMER_RETRIEVER_K_DOCUMENTS = int(os.getenv("CUSTOMER_RETRIEVER_K_DOCUMENTS", "6"))  # Number of customer docs to retrieve
# NOTE: If customer documents are used, CUSTOMER_RETRIEVER_K_DOCUMENTS should be set to 
# the same value as RETRIEVER_K_DOCUMENTS for optimal processing efficiency. The system
# will pair corresponding documents from both sources during refinement.

# Role Definitions
QUESTION_ROLE = os.getenv("QUESTION_ROLE", "question")
CONTEXT_ROLE = os.getenv("CONTEXT_ROLE", "context")
ANSWER_ROLE = os.getenv("ANSWER_ROLE", "answer")
COMPLIANCE_ROLE = os.getenv("COMPLIANCE_ROLE", "compliance")
PRIMARY_PRODUCT_ROLE = os.getenv("PRIMARY_PRODUCT_ROLE", "primary_product")
REFERENCES_ROLE = os.getenv("REFERENCES_ROLE", "references")

# Feature Flags
CLEAN_UP_CELL_CONTENT = os.getenv("CLEAN_UP_CELL_CONTENT", "False").lower() == "true"
SUMMARIZE_LONG_CELLS = os.getenv("SUMMARIZE_LONG_CELLS", "False").lower() == "true"
INTERACTIVE_PRODUCT_SELECTION = os.getenv("INTERACTIVE_PRODUCT_SELECTION", "True").lower() == "true"
AUTO_DISCOVER_PRODUCTS = os.getenv("AUTO_DISCOVER_PRODUCTS", "True").lower() == "true"

# Google API Rate Limits
GOOGLE_API_MAX_RETRIES = int(os.getenv("GOOGLE_API_MAX_RETRIES", "3"))
GOOGLE_API_RETRY_DELAY = int(os.getenv("GOOGLE_API_RETRY_DELAY", "5"))