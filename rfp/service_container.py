import logging
from typing import Dict, Any, Optional, Type

from config import ConfigManager, get_config

logger = logging.getLogger(__name__)

class ServiceContainer:
    """
    Service container for dependency injection.
    
    This class is responsible for creating, configuring, and providing
    access to service instances throughout the application. It implements
    a service locator pattern with lazy initialization.
    """
    
    def __init__(self, config: Optional[ConfigManager] = None):
        """
        Initialize the service container.
        
        Args:
            config: Optional ConfigManager instance. If None, the global
                   singleton will be used.
        """
        self.config = config or get_config()
        self._services = {}
        logger.info("Service container initialized")
    
    def get(self, service_key: str) -> Any:
        """
        Get a service by its key.
        
        This is a generic service accessor. Most services should be accessed
        through their specific accessor methods.
        
        Args:
            service_key: The key used to store the service
            
        Returns:
            The requested service instance
            
        Raises:
            KeyError: If the service is not found
        """
        if service_key not in self._services:
            raise KeyError(f"Service '{service_key}' not found")
        return self._services[service_key]
    
    def register(self, service_key: str, service: Any) -> None:
        """
        Register a service manually.
        
        Args:
            service_key: The key to use for storing the service
            service: The service instance to register
        """
        self._services[service_key] = service
        logger.debug(f"Service '{service_key}' registered manually")
    
    def get_sheet_handler(self) -> Any:
        """
        Get the sheet handler service.
        
        Returns:
            GoogleSheetHandler instance
        """
        if "sheet_handler" not in self._services:
            from sheets_handler import GoogleSheetHandler
            
            self._services["sheet_handler"] = GoogleSheetHandler(
                self.config.google_sheet_id,
                self.config.google_credentials_file,
                self.config.rfp_sheet_name
            )
            logger.debug("Created sheet handler service")
            
        return self._services["sheet_handler"]
    
    def get_embedding_manager(self) -> Any:
        """
        Get the embedding manager service.
        
        Returns:
            EmbeddingManager instance
        """
        if "embedding_manager" not in self._services:
            from embedding_manager import EmbeddingManager
            
            self._services["embedding_manager"] = EmbeddingManager(
                self.config.embedding_model
            )
            logger.debug("Created embedding manager service")
            
        return self._services["embedding_manager"]
    
    def get_llm(self) -> Any:
        """
        Get the language model service.
        
        Returns:
            LLM instance (ChatOpenAI, OllamaLLM, etc.)
        """
        if "llm" not in self._services:
            from llm_wrapper import LLMWrapper
            
            llm_wrapper = LLMWrapper(self.config)
            self._services["llm"] = llm_wrapper.get_llm(
                self.config.llm_provider,
                self.config.llm_model,
                self.config.ollama_base_url,
                self.config.llama_cpp_base_url
            )
            logger.debug(f"Created LLM service with provider: {self.config.llm_provider}")
            
        return self._services["llm"]
    
    def get_question_logger(self) -> Any:
        """
        Get the question logger service.
        
        Returns:
            QuestionLogger instance
        """
        if "question_logger" not in self._services:
            from question_logger import QuestionLogger
            
            self._services["question_logger"] = QuestionLogger(
                self.config.base_dir
            )
            logger.debug("Created question logger service")
            
        return self._services["question_logger"]
    
    def get_question_processor(self) -> Any:
        """
        Get the question processor service.
        
        Returns:
            QuestionProcessor instance
        """
        if "question_processor" not in self._services:
            from question_processor import QuestionProcessor
            
            # Get dependencies
            embedding_manager = self.get_embedding_manager()
            llm = self.get_llm()
            question_logger = self.get_question_logger()
            
            self._services["question_processor"] = QuestionProcessor(
                embedding_manager=embedding_manager,
                llm=llm,
                question_logger=question_logger,
                index_dir=self.config.index_dir
            )
            logger.debug("Created question processor service")
            
        return self._services["question_processor"]
    
    def get_qa_chain(self) -> Any:
        """
        Get the QA chain service.
        
        Returns:
            RetrievalQA instance
        """
        if "qa_chain" not in self._services:
            from langchain.chains import RetrievalQA
            from langchain.schema import Document
            from langchain.schema.retriever import BaseRetriever
            from prompts import PromptManager
            import warnings
            
            warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")
            
            class DummyRetriever(BaseRetriever):
                search_kwargs: Dict[str, Any] = {"k": 0}
                
                def _get_relevant_documents(self, query: str, **kwargs) -> list:
                    return []
                    
                def get_relevant_documents(self, query: str, **kwargs) -> list:
                    return self._get_relevant_documents(query, **kwargs)
                
                async def _aget_relevant_documents(self, query: str, **kwargs) -> list:
                    return []
                
                async def aget_relevant_documents(self, query: str, **kwargs) -> list:
                    return await self._aget_relevant_documents(query, **kwargs)
            
            dummy_retriever = DummyRetriever()
            llm = self.get_llm()
            
            self._services["qa_chain"] = RetrievalQA.from_chain_type(
                llm=llm,
                retriever=dummy_retriever,
                chain_type="refine",
                input_key="question",
                return_source_documents=True,
                chain_type_kwargs={
                    "question_prompt": PromptManager.QUESTION_PROMPT,
                    "refine_prompt": PromptManager.REFINE_PROMPT,
                    "document_variable_name": "context_str",
                    "initial_response_name": "existing_answer",
                }
            )
            logger.debug("Created QA chain service")
            
        return self._services["qa_chain"]
    
    def get_text_processor(self) -> Any:
        """
        Get the text processor service.
        
        Returns:
            TextProcessor class
        """
        if "text_processor" not in self._services:
            from text_processing import TextProcessor
            
            self._services["text_processor"] = TextProcessor
            logger.debug("Created text processor service")
            
        return self._services["text_processor"]
    
    def get_model_manager(self) -> Any:
        """
        Get the model manager service.
        
        Returns:
            ModelManager instance
        """
        if "model_manager" not in self._services:
            from model_manager import ModelManager
            
            self._services["model_manager"] = ModelManager()
            logger.debug("Created model manager service")
            
        return self._services["model_manager"]
    
    def get_translation_handler(self) -> Any:
        """
        Get the translation handler service.
        
        Returns:
            TranslationHandler class
        """
        if "translation_handler" not in self._services:
            from translation_handler import TranslationHandler
            
            self._services["translation_handler"] = TranslationHandler
            logger.debug("Created translation handler service")
            
        return self._services["translation_handler"]
    
    def get_input_utils(self) -> Any:
        """
        Get the input utilities service.
        
        Returns:
            InputHandler class
        """
        if "input_utils" not in self._services:
            from input_utils import InputHandler
            
            self._services["input_utils"] = InputHandler
            logger.debug("Created input utils service")
            
        return self._services["input_utils"]
    
    def get_customer_docs_manager(self) -> Any:
        """
        Get the customer documents manager service.
        
        Returns:
            CustomerDocsManager
        """
        if "customer_docs_manager" not in self._services:
            from customer_docs import CustomerDocsManager
            
            self._services["customer_docs_manager"] = CustomerDocsManager(self.config)
            logger.debug("Created customer docs manager service")
            
        return self._services["customer_docs_manager"]


# Singleton instance
_service_container_instance = None

def get_service_container(config: Optional[ConfigManager] = None) -> ServiceContainer:
    """
    Get the global service container instance, creating it if it doesn't exist.
    
    Args:
        config: Optional ConfigManager instance to use
        
    Returns:
        ServiceContainer instance
    """
    global _service_container_instance
    
    if _service_container_instance is None:
        _service_container_instance = ServiceContainer(config)
        
    return _service_container_instance