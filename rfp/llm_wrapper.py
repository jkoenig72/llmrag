import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def check_llama_server():
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
            print("Please start the llama-server with a command like:")
            print("./llama-server --model /path/to/model.gguf --n-gpu-layers 35 --ctx-size 4096 --port 8080")
            return False
            
    except Exception as e:
        logger.error(f"Error checking for llama-server: {e}")
        return False

def get_llm(llm_provider: str, llm_model: str, 
          ollama_base_url: str, llama_cpp_base_url: str):
    logger.info(f"Initializing LLM provider: {llm_provider} (model: {llm_model})")
    
    if llm_provider == "ollama":
        from langchain_ollama import OllamaLLM
        return OllamaLLM(model=llm_model, base_url=ollama_base_url)
    elif llm_provider == "llamacpp":
        if llm_model == "translation":
            logger.info("Using translation model mode - skipping server check")
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                base_url=f"{llama_cpp_base_url}/v1",
                api_key="not-needed",
                model="local-model"
            )
            
        if check_llama_server():
            response = input("\nDo you want to continue with the running llama-server? (y/n): ")
            if response.lower() != 'y':
                logger.info("User chose not to continue. Exiting.")
                exit(0)
        else:
            response = input("\nDo you want to continue anyway? (y/n): ")
            if response.lower() != 'y':
                logger.info("User chose not to continue without llama-server. Exiting.")
                exit(0)
        
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=f"{llama_cpp_base_url}/v1",
            api_key="not-needed",
            model="local-model"
        )
    else:
        raise ValueError(f"Unknown LLM provider: {llm_provider}")