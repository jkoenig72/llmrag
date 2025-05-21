import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Centralized configuration management for the RFP Processing system.
    
    This class handles loading of configuration from environment variables
    with fallbacks to default values. It provides validation and convenient
    access to configuration values through properties.
    
    Configuration Categories:
    1. Google API Configuration
       - Sheet IDs and credentials for Google Sheets integration
       - API retry settings for handling rate limits
    
    2. Directory Paths
       - Base directories for documents, indices, and logs
       - Customer-specific document storage
    
    3. LLM Configuration
       - Model selection and provider settings
       - API endpoints and connection details
    
    4. Processing Configuration
       - Batch sizes and throttling
       - Text processing limits
       - Workflow control settings
    
    Example:
        ```python
        # Using default configuration
        config = ConfigManager()
        
        # Using custom environment file
        config = ConfigManager(env_file="custom.env")
        
        # Accessing configuration values
        sheet_id = config.google_sheet_id
        base_dir = config.base_dir
        model = config.llm_model
        ```
    """
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize the config manager.
        
        Args:
            env_file: Optional path to an environment file (.env)
                     If provided, configuration will be loaded from this file
                     before falling back to environment variables and defaults.
        
        Example:
            ```python
            # Load from default locations
            config = ConfigManager()
            
            # Load from custom .env file
            config = ConfigManager(env_file="/path/to/custom.env")
            ```
        """
        # Load environment variables from file if provided
        if env_file and os.path.exists(env_file):
            self._load_from_env_file(env_file)
            
        # Initialize configuration values
        self._initialize_config()
        
        # Validate critical configuration
        self._validate_config()
        
        logger.info("Configuration initialized successfully")
    
    def _load_from_env_file(self, env_file: str) -> None:
        """
        Load environment variables from a file.
        
        Args:
            env_file: Path to .env file
        """
        logger.info(f"Loading environment variables from {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()
    
    def _initialize_config(self) -> None:
        """
        Initialize all configuration properties from environment variables or defaults.
        
        This method sets up all configuration values in the following order:
        1. Environment variables (if set)
        2. Default values (if no environment variable)
        
        Configuration Sections:
        
        Google API Configuration:
        - GOOGLE_SHEET_ID: ID of the Google Sheet for RFP data
        - GOOGLE_CREDENTIALS_FILE: Path to Google API credentials
        - GOOGLE_API_MAX_RETRIES: Number of retries for API calls
        - GOOGLE_API_RETRY_DELAY: Delay between retries in seconds
        
        Directory Paths:
        - BASE_DIR: Root directory for the application
        - INDEX_DIR: Directory for vector indices
        - RFP_DOCUMENTS_DIR: Directory for RFP documents
        - CUSTOMER_INDEX_DIR: Directory for customer-specific indices
        
        LLM Configuration:
        - LLM_PROVIDER: Provider for language model (e.g., "llamacpp", "ollama")
        - LLM_MODEL: Model name to use
        - OLLAMA_BASE_URL: Base URL for Ollama API
        - LLAMA_CPP_BASE_URL: Base URL for llama.cpp server
        - EMBEDDING_MODEL: Model for document embeddings
        
        Processing Configuration:
        - RETRIEVER_K_DOCUMENTS: Number of documents to retrieve
        - CUSTOMER_RETRIEVER_K_DOCUMENTS: Number of customer documents to retrieve
        - BATCH_SIZE: Size of processing batches
        - API_THROTTLE_DELAY: Delay between API calls
        - MAX_WORDS_BEFORE_SUMMARY: Word limit before summarization
        - MAX_LINKS_PROVIDED: Maximum number of reference links
        
        Example:
            ```python
            # Environment variables
            export GOOGLE_SHEET_ID="your-sheet-id"
            export LLM_PROVIDER="ollama"
            export LLM_MODEL="mistral"
            
            # Initialize config
            config = ConfigManager()
            print(f"Using model: {config.llm_model}")
            print(f"Sheet ID: {config.google_sheet_id}")
            ```
        """
        # Google API Configuration
        self._google_sheet_id = os.getenv("GOOGLE_SHEET_ID", "10-0PcsDFUvT2WPGaK91UYsA0zxqOwjjrs3J6g39SYD0")
        self._google_credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", os.path.expanduser("~/llms-env/credentials.json"))
        self._google_api_max_retries = int(os.getenv("GOOGLE_API_MAX_RETRIES", "3"))
        self._google_api_retry_delay = int(os.getenv("GOOGLE_API_RETRY_DELAY", "5"))
        
        # Directory Paths
        self._base_dir = os.getenv("BASE_DIR", os.path.expanduser("~/RAG"))
        self._index_dir = os.getenv("INDEX_DIR", os.path.expanduser("~/RAG/indexes"))
        self._rfp_documents_dir = os.getenv("RFP_DOCUMENTS_DIR", os.path.expanduser("~/RFP_Documents"))
        self._customer_index_dir = os.getenv("CUSTOMER_INDEX_DIR", os.path.expanduser("~/customer_indices"))
        
        # LLM Configuration
        self._llm_provider = os.getenv("LLM_PROVIDER", "llamacpp")
        self._llm_model = os.getenv("LLM_MODEL", "mistral-small3.1")
        self._ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._llama_cpp_base_url = os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8080")
        self._embedding_model = os.getenv("EMBEDDING_MODEL", "intfloat/e5-large-v2")
        
        # Retrieval Configuration
        self._retriever_k_documents = int(os.getenv("RETRIEVER_K_DOCUMENTS", "2"))
        self._customer_retriever_k_documents = int(os.getenv("CUSTOMER_RETRIEVER_K_DOCUMENTS", "2"))
        
        # Processing Configuration
        self._batch_size = int(os.getenv("BATCH_SIZE", "1"))
        self._api_throttle_delay = int(os.getenv("API_THROTTLE_DELAY", "3"))
        self._max_words_before_summary = int(os.getenv("MAX_WORDS_BEFORE_SUMMARY", "200"))
        self._max_links_provided = int(os.getenv("MAX_LINKS_PROVIDED", "2"))
        self._clean_up_cell_content = os.getenv("CLEAN_UP_CELL_CONTENT", "False").lower() == "true"
        self._summarize_long_cells = os.getenv("SUMMARIZE_LONG_CELLS", "False").lower() == "true"
        self._interactive_product_selection = os.getenv("INTERACTIVE_PRODUCT_SELECTION", "True").lower() == "true"
        self._translation_enabled = os.getenv("TRANSLATION_ENABLED", "True").lower() == "true"
        
        # Role Definitions
        self._question_role = os.getenv("QUESTION_ROLE", "question")
        self._context_role = os.getenv("CONTEXT_ROLE", "context")
        self._answer_role = os.getenv("ANSWER_ROLE", "answer")
        self._compliance_role = os.getenv("COMPLIANCE_ROLE", "compliance")
        self._primary_product_role = os.getenv("PRIMARY_PRODUCT_ROLE", "primary_product")
        self._references_role = os.getenv("REFERENCES_ROLE", "references")
        
        # Model Command
        self._rfp_model_cmd = os.getenv(
            "RFP_MODEL_CMD", 
            "~/llama.cpp/build/bin/llama-server --model /home/fritz/models/mistral-nemo-12b-instruct-2407/Mistral-Nemo-12B-Instruct-2407-Q5_K_M.gguf --n-gpu-layers 35 --ctx-size 8192 --port 8080"
        )
        
        # Workflow Control 
        self._rfp_sheet_name = os.getenv("RFP_SHEET_NAME")
        self._rfp_workflow_mode = os.getenv("RFP_WORKFLOW_MODE", "")
        self._rfp_skip_product_selection = os.getenv("RFP_SKIP_PRODUCT_SELECTION", "False").lower() == "true"
        self._rfp_selected_products = os.getenv("RFP_SELECTED_PRODUCTS", "")
        self._rfp_skip_customer_selection = os.getenv("RFP_SKIP_CUSTOMER_SELECTION", "False").lower() == "true"
        self._rfp_customer_index_path = os.getenv("RFP_CUSTOMER_INDEX_PATH", "")
        
        # UI/UX Configuration
        self._default_timeout = int(os.getenv("DEFAULT_TIMEOUT", "30"))
        self._llm_request_timeout = int(os.getenv("LLM_REQUEST_TIMEOUT", "60"))
        self._max_context_chars = int(os.getenv("MAX_CONTEXT_CHARS", "12000"))
        
        # Reference Handler Configuration
        self._reference_check_timeout = int(os.getenv("REFERENCE_CHECK_TIMEOUT", "10"))
        self._selenium_wait_time = int(os.getenv("SELENIUM_WAIT_TIME", "2"))
    
    def _validate_config(self) -> None:
        """
        Validate the configuration, ensuring critical values are present and valid.
        Raises ValueError if validation fails.
        """
        # Validate paths exist or can be created
        self._ensure_directory_exists(self._base_dir)
        self._ensure_directory_exists(self._index_dir)
        self._ensure_directory_exists(self._rfp_documents_dir)
        self._ensure_directory_exists(self._customer_index_dir)
        
        # Validate Google credentials file existence if specified
        if not os.path.exists(self._google_credentials_file):
            logger.warning(f"Google credentials file not found: {self._google_credentials_file}")
            
        # Validate numeric values are positive
        for name, value in [
            ("retriever_k_documents", self._retriever_k_documents),
            ("customer_retriever_k_documents", self._customer_retriever_k_documents),
            ("batch_size", self._batch_size),
            ("api_throttle_delay", self._api_throttle_delay),
            ("default_timeout", self._default_timeout),
            ("llm_request_timeout", self._llm_request_timeout),
        ]:
            if value <= 0:
                raise ValueError(f"Configuration error: {name} must be positive, got {value}")
    
    def _ensure_directory_exists(self, directory: str) -> None:
        """Ensure a directory exists, creating it if necessary."""
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create directory {directory}: {e}")
    
    def as_dict(self) -> Dict[str, Any]:
        """
        Export all configuration as a dictionary.
        
        Returns:
            Dict containing all configuration values
        """
        return {
            # Google API Configuration
            "GOOGLE_SHEET_ID": self._google_sheet_id,
            "GOOGLE_CREDENTIALS_FILE": self._google_credentials_file,
            "GOOGLE_API_MAX_RETRIES": self._google_api_max_retries,
            "GOOGLE_API_RETRY_DELAY": self._google_api_retry_delay,
            
            # Directory Paths
            "BASE_DIR": self._base_dir,
            "INDEX_DIR": self._index_dir,
            "RFP_DOCUMENTS_DIR": self._rfp_documents_dir,
            "CUSTOMER_INDEX_DIR": self._customer_index_dir,
            
            # LLM Configuration
            "LLM_PROVIDER": self._llm_provider,
            "LLM_MODEL": self._llm_model,
            "OLLAMA_BASE_URL": self._ollama_base_url,
            "LLAMA_CPP_BASE_URL": self._llama_cpp_base_url,
            "EMBEDDING_MODEL": self._embedding_model,
            
            # Retrieval Configuration
            "RETRIEVER_K_DOCUMENTS": self._retriever_k_documents,
            "CUSTOMER_RETRIEVER_K_DOCUMENTS": self._customer_retriever_k_documents,
            
            # Processing Configuration
            "BATCH_SIZE": self._batch_size,
            "API_THROTTLE_DELAY": self._api_throttle_delay,
            "MAX_WORDS_BEFORE_SUMMARY": self._max_words_before_summary,
            "MAX_LINKS_PROVIDED": self._max_links_provided,
            "CLEAN_UP_CELL_CONTENT": self._clean_up_cell_content,
            "SUMMARIZE_LONG_CELLS": self._summarize_long_cells,
            "INTERACTIVE_PRODUCT_SELECTION": self._interactive_product_selection,
            "TRANSLATION_ENABLED": self._translation_enabled,
            
            # Role Definitions
            "QUESTION_ROLE": self._question_role,
            "CONTEXT_ROLE": self._context_role,
            "ANSWER_ROLE": self._answer_role,
            "COMPLIANCE_ROLE": self._compliance_role,
            "PRIMARY_PRODUCT_ROLE": self._primary_product_role,
            "REFERENCES_ROLE": self._references_role,
            
            # Model Command
            "RFP_MODEL_CMD": self._rfp_model_cmd,
            
            # Workflow Control
            "RFP_SHEET_NAME": self._rfp_sheet_name,
            "RFP_WORKFLOW_MODE": self._rfp_workflow_mode,
            "RFP_SKIP_PRODUCT_SELECTION": self._rfp_skip_product_selection,
            "RFP_SELECTED_PRODUCTS": self._rfp_selected_products,
            "RFP_SKIP_CUSTOMER_SELECTION": self._rfp_skip_customer_selection,
            "RFP_CUSTOMER_INDEX_PATH": self._rfp_customer_index_path,
            
            # UI/UX Configuration
            "DEFAULT_TIMEOUT": self._default_timeout,
            "LLM_REQUEST_TIMEOUT": self._llm_request_timeout,
            "MAX_CONTEXT_CHARS": self._max_context_chars,
            
            # Reference Handler Configuration
            "REFERENCE_CHECK_TIMEOUT": self._reference_check_timeout,
            "SELENIUM_WAIT_TIME": self._selenium_wait_time,
        }
    
    def print_config_summary(self) -> None:
        """Print a formatted summary of the current configuration."""
        print("\n" + "="*50)
        print("CONFIGURATION SUMMARY")
        print("="*50)
        
        print("\n📄 GOOGLE SHEET CONFIGURATION:")
        print(f"Sheet ID: {self._google_sheet_id}")
        print(f"Credentials File: {self._google_credentials_file}")
        
        print("\n🧠 LLM CONFIGURATION:")
        print(f"LLM Provider: {self._llm_provider}")
        print(f"LLM Model: {self._llm_model}")
        
        if self._llm_provider == "ollama":
            print(f"Ollama Base URL: {self._ollama_base_url}")
        elif self._llm_provider == "llamacpp":
            print(f"llama.cpp Base URL: {self._llama_cpp_base_url}")
            
            import re
            model_match = re.search(r'--model\s+([^\s]+)', self._rfp_model_cmd)
            if model_match:
                model_path = model_match.group(1)
                print(f"Model Path: {model_path}")
                import os
                model_filename = os.path.basename(model_path)
                print(f"Model File: {model_filename}")
            
            gpu_layers_match = re.search(r'--n-gpu-layers\s+(\d+)', self._rfp_model_cmd)
            if gpu_layers_match:
                gpu_layers = gpu_layers_match.group(1)
                print(f"GPU Layers: {gpu_layers}")
                
            ctx_size_match = re.search(r'--ctx-size\s+(\d+)', self._rfp_model_cmd)
            if ctx_size_match:
                ctx_size = ctx_size_match.group(1)
                print(f"Context Size: {ctx_size}")
                
            port_match = re.search(r'--port\s+(\d+)', self._rfp_model_cmd)
            if port_match:
                port = port_match.group(1)
                print(f"Port: {port}")
        
        print(f"\n📊 EMBEDDING CONFIGURATION:")
        print(f"Embedding Model: {self._embedding_model}")
        
        print(f"\n🔍 VECTOR DATABASE CONFIGURATION:")
        print(f"Index Directory: {self._index_dir}")
        
        print(f"\n👥 CUSTOMER DOCUMENT CONFIGURATION:")
        print(f"RFP Documents Dir: {self._rfp_documents_dir}")
        print(f"Customer Index Dir: {self._customer_index_dir}")
        
        print(f"\n⚙️ PROCESSING CONFIGURATION:")
        print(f"Batch Size: {self._batch_size}")
        print(f"API Throttle Delay: {self._api_throttle_delay}s")
        print(f"Clean Up Cell Content: {self._clean_up_cell_content}")
        print(f"Summarize Long Cells: {self._summarize_long_cells}")
        if self._summarize_long_cells:
            print(f"  Max Words Before Summary: {self._max_words_before_summary}")
        
        print("\n" + "="*50)
    
    def save_to_env_file(self, filename: str) -> None:
        """
        Save the current configuration to an environment file.
        
        Args:
            filename: Path to save the .env file
        """
        config_dict = self.as_dict()
        
        with open(filename, 'w') as f:
            for key, value in config_dict.items():
                if value is not None:
                    f.write(f"{key}={value}\n")
        
        logger.info(f"Configuration saved to {filename}")
    
    # Properties for all configuration values
    
    # Google API Configuration
    @property
    def google_sheet_id(self) -> str:
        return self._google_sheet_id
    
    @property
    def google_credentials_file(self) -> str:
        return self._google_credentials_file
    
    @property
    def google_api_max_retries(self) -> int:
        return self._google_api_max_retries
    
    @property
    def google_api_retry_delay(self) -> int:
        return self._google_api_retry_delay
    
    # Directory Paths
    @property
    def base_dir(self) -> str:
        return self._base_dir
    
    @property
    def index_dir(self) -> str:
        return self._index_dir
    
    @property
    def rfp_documents_dir(self) -> str:
        return self._rfp_documents_dir
    
    @property
    def customer_index_dir(self) -> str:
        return self._customer_index_dir
    
    # LLM Configuration
    @property
    def llm_provider(self) -> str:
        return self._llm_provider
    
    @property
    def llm_model(self) -> str:
        return self._llm_model
    
    @property
    def ollama_base_url(self) -> str:
        return self._ollama_base_url
    
    @property
    def llama_cpp_base_url(self) -> str:
        return self._llama_cpp_base_url
    
    @property
    def embedding_model(self) -> str:
        return self._embedding_model
    
    # Retrieval Configuration
    @property
    def retriever_k_documents(self) -> int:
        return self._retriever_k_documents
    
    @property
    def customer_retriever_k_documents(self) -> int:
        return self._customer_retriever_k_documents
    
    # Processing Configuration
    @property
    def batch_size(self) -> int:
        return self._batch_size
    
    @property
    def api_throttle_delay(self) -> int:
        return self._api_throttle_delay
    
    @property
    def max_words_before_summary(self) -> int:
        return self._max_words_before_summary
    
    @property
    def max_links_provided(self) -> int:
        return self._max_links_provided
    
    @property
    def clean_up_cell_content(self) -> bool:
        return self._clean_up_cell_content
    
    @property
    def summarize_long_cells(self) -> bool:
        return self._summarize_long_cells
    
    @property
    def interactive_product_selection(self) -> bool:
        return self._interactive_product_selection
    
    @property
    def translation_enabled(self) -> bool:
        return self._translation_enabled
    
    # Role Definitions
    @property
    def question_role(self) -> str:
        return self._question_role
    
    @property
    def context_role(self) -> str:
        return self._context_role
    
    @property
    def answer_role(self) -> str:
        return self._answer_role
    
    @property
    def compliance_role(self) -> str:
        return self._compliance_role
    
    @property
    def primary_product_role(self) -> str:
        return self._primary_product_role
    
    @property
    def references_role(self) -> str:
        return self._references_role
    
    # Model Command
    @property
    def rfp_model_cmd(self) -> str:
        return self._rfp_model_cmd
    
    # Workflow Control
    @property
    def rfp_sheet_name(self) -> Optional[str]:
        return self._rfp_sheet_name
    
    @property
    def rfp_workflow_mode(self) -> str:
        return self._rfp_workflow_mode
    
    @property
    def rfp_skip_product_selection(self) -> bool:
        return self._rfp_skip_product_selection
    
    @property
    def rfp_selected_products(self) -> str:
        return self._rfp_selected_products
    
    @property
    def rfp_skip_customer_selection(self) -> bool:
        return self._rfp_skip_customer_selection
    
    @property
    def rfp_customer_index_path(self) -> str:
        return self._rfp_customer_index_path
    
    # UI/UX Configuration
    @property
    def default_timeout(self) -> int:
        return self._default_timeout
    
    @property
    def llm_request_timeout(self) -> int:
        return self._llm_request_timeout
    
    @property
    def max_context_chars(self) -> int:
        return self._max_context_chars
    
    # Reference Handler Configuration
    @property
    def reference_check_timeout(self) -> int:
        return self._reference_check_timeout
    
    @property
    def selenium_wait_time(self) -> int:
        return self._selenium_wait_time
    
    # Utility methods
    @property
    def rfp_selected_products_list(self) -> List[str]:
        """Get selected products as a list."""
        if not self._rfp_selected_products:
            return []
        return [p.strip() for p in self._rfp_selected_products.split(",")]


# Singleton instance of the configuration
_config_instance = None

def get_config(env_file: Optional[str] = None) -> ConfigManager:
    """
    Get the global configuration instance, creating it if it doesn't exist.
    
    Args:
        env_file: Optional path to an environment file (.env)
        
    Returns:
        ConfigManager instance
    """
    global _config_instance
    
    if _config_instance is None:
        _config_instance = ConfigManager(env_file)
        
    return _config_instance