import logging
import time
import subprocess
from typing import Optional, Any, Dict, Tuple, List

from config import get_config

logger = logging.getLogger(__name__)

class LLMWrapper:
    """
    Wrapper class for language model integration.
    
    This class handles the initialization, checking, and creation of
    language model instances with different providers.
    """
    
    def __init__(self, config=None):
        """
        Initialize the LLM wrapper.
        
        Args:
            config: Optional configuration instance. If None, the global config will be used.
        """
        self.config = config or get_config()
        self.model_manager = ModelManager()
    
    def check_llama_server(self) -> bool:
        """
        Check if llama-server is running and start it if needed.
        
        Returns:
            bool: True if server is running or successfully started, False otherwise
        """
        try:
            result = subprocess.run(['ps', '-ef'], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            
            llama_processes = []
            for line in lines:
                if 'llama-server' in line and 'grep' not in line:
                    llama_processes.append(line)
            
            if llama_processes:
                print("\n✅ Found running llama-server process(es):")
                for proc in llama_processes:
                    print(f"  {proc}")
                
                for proc in llama_processes:
                    parts = proc.split()
                    if 'llama-server' in parts:
                        cmd_index = parts.index('llama-server')
                        command_line = ' '.join(parts[cmd_index:])
                        print(f"\nCommand: {command_line}")
                
                return True
            else:
                print("\n⚠️ WARNING: No llama-server process found running!")
                print("Automatically starting the llama-server with configured command...")
                return False
                
        except Exception as e:
            logger.error(f"Error checking for llama-server: {e}")
            return False
    
    def get_llm(self, provider: Optional[str] = None, model: Optional[str] = None, 
              ollama_base_url: Optional[str] = None, llama_cpp_base_url: Optional[str] = None) -> Any:
        """
        Get a language model instance based on the specified provider.
        
        Args:
            provider: LLM provider name (e.g., 'ollama', 'llamacpp')
            model: Model name to use
            ollama_base_url: Base URL for Ollama API
            llama_cpp_base_url: Base URL for llama.cpp server
            
        Returns:
            LLM instance (provider-specific)
            
        Raises:
            ValueError: If provider is unknown
        """
        # Use config values if parameters not provided
        provider = provider or self.config.llm_provider
        model = model or self.config.llm_model
        ollama_base_url = ollama_base_url or self.config.ollama_base_url
        llama_cpp_base_url = llama_cpp_base_url or self.config.llama_cpp_base_url
        
        logger.info(f"Initializing LLM provider: {provider} (model: {model})")
        
        if provider == "ollama":
            return self._get_ollama_llm(model, ollama_base_url)
        elif provider == "llamacpp":
            return self._get_llamacpp_llm(model, llama_cpp_base_url)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
    
    def _get_ollama_llm(self, model: str, base_url: str) -> Any:
        """
        Get an Ollama LLM instance.
        
        Args:
            model: Model name
            base_url: Ollama API base URL
            
        Returns:
            OllamaLLM instance
        """
        from langchain_ollama import OllamaLLM
        return OllamaLLM(model=model, base_url=base_url)
    
    def _get_llamacpp_llm(self, model: str, base_url: str) -> Any:
        """
        Get a llama.cpp LLM instance.
        
        Args:
            model: Model name (used for special handling)
            base_url: llama.cpp server base URL
            
        Returns:
            ChatOpenAI instance configured for llama.cpp
        """
        if model == "translation":
            logger.info("Using translation model mode - skipping server check")
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                base_url=f"{base_url}/v1",
                api_key="not-needed",
                model="local-model"
            )
            
        # Get the RFP model command from config
        rfp_model_cmd = self.config.rfp_model_cmd
        
        if not self.check_llama_server():
            logger.info("Automatically starting llama-server...")
            start_success = self.model_manager.start_model(rfp_model_cmd, wait_time=10)
            
            if not start_success:
                logger.error("Failed to start llama-server automatically")
                print("\n❌ Failed to start llama-server with configured command.")
                print("Please check your RFP_MODEL_CMD configuration in config.py:")
                print(f"Current command: {rfp_model_cmd}")
                print("\nShutting down all operations now. I'll be here when you're ready to continue, Dave.")
                exit(1)
            else:
                logger.info("Successfully started llama-server automatically")
                print("✅ Successfully started llama-server")
                
                time.sleep(5)
                
                is_running, _ = self.model_manager.check_running_model("8080")
                if not is_running:
                    logger.error("Server was started but is not responding on port 8080")
                    print("\n⚠️ Server was started but is not responding on port 8080.")
                    print("Please check your configuration and ensure the server is running on the correct port.")
                    print("\nShutting down all operations now. Try again later, Dave.")
                    exit(1)
        
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=f"{base_url}/v1",
            api_key="not-needed",
            model="local-model"
        )
    
    def check_running_model(self, port: str = "8080") -> Tuple[bool, Optional[str]]:
        """
        Check if a model server is running on the specified port.
        
        Args:
            port: Port number to check
            
        Returns:
            Tuple of (is_running, process_info_string)
        """
        return self.model_manager.check_running_model(port)
    
    def start_model(self, model_cmd: str, wait_time: int = 5) -> bool:
        """
        Start a model server with the specified command.
        
        Args:
            model_cmd: Command to start the model
            wait_time: Time to wait for initialization (seconds)
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.model_manager.start_model(model_cmd, wait_time)
    
    def switch_models(self, from_model_cmd: str, to_model_cmd: str, purpose: str) -> bool:
        """
        Switch from one model to another.
        
        Args:
            from_model_cmd: Current model command (can be None)
            to_model_cmd: New model command to run
            purpose: Description of the reason for switching
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.model_manager.switch_models(from_model_cmd, to_model_cmd, purpose)
    
    def kill_running_llama_process(self) -> bool:
        """
        Stop any running llama-server processes.
        
        Returns:
            bool: True if successful, False otherwise
        """
        return self.model_manager.kill_running_llama_process()

# Import ModelManager here to avoid circular imports
from model_manager import ModelManager