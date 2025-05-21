import logging
import os
import subprocess
import time
import shlex
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class ModelManager:
    """
    Manages the lifecycle of LLM server processes.
    
    This class provides methods to check, start, stop, and switch LLM server
    processes for inference.
    """
    
    @staticmethod
    def check_running_model(port: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a model server is running on the specified port.
        
        Args:
            port: Port number to check
            
        Returns:
            Tuple of (is_running, process_info_string)
        """
        try:
            cmd = f"lsof -i :{port}"
            result = subprocess.run(shlex.split(cmd), capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Found model server running on port {port}")
                return True, result.stdout
            else:
                logger.info(f"No model server found on port {port}")
                return False, None
        except Exception as e:
            logger.error(f"Error checking model status on port {port}: {e}")
            return False, None
    
    @staticmethod
    def kill_running_llama_process() -> bool:
        """
        Stop any running llama-server processes.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("Stopping any running llama-server processes")
            print("Stopping any running llama-server processes...")
            # Use pkill without shell=True for safety
            kill_cmd = ["pkill", "-f", "llama-server"]
            subprocess.run(kill_cmd, capture_output=True, text=True)
            time.sleep(3)
            logger.info("Successfully stopped llama-server processes")
            return True
        except Exception as e:
            logger.error(f"Error killing llama-server processes: {e}")
            print(f"Error stopping llama-server: {e}")
            return False
    
    @staticmethod
    def start_model(model_cmd: str, wait_time: int = 5) -> bool:
        """
        Start a model server with the specified command.
        
        Args:
            model_cmd: Command to start the model
            wait_time: Time to wait for initialization (seconds)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Starting model with command: {model_cmd}")
            print(f"Starting model with command:\n{model_cmd}")
            
            # Parse the command safely to avoid shell injection
            # If the command is complex with pipes or redirects, 
            # it may need special handling
            try:
                cmd_parts = shlex.split(model_cmd)
                process = subprocess.Popen(
                    cmd_parts, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True
                )
            except ValueError:
                # Fallback for complex commands that can't be easily split
                logger.warning("Using shell=True as fallback for complex command")
                process = subprocess.Popen(
                    model_cmd, 
                    shell=True, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True
                )
            
            logger.info(f"Waiting {wait_time} seconds for model initialization")
            print(f"Waiting {wait_time} seconds for model to initialize...")
            time.sleep(wait_time)
            
            if process.poll() is None:
                logger.info("Model started successfully")
                print("Model started successfully.")
                return True
            else:
                stdout, stderr = process.communicate()
                error_msg = stderr
                logger.error(f"Model failed to start. Error: {error_msg}")
                print(f"Model failed to start. Error: {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Error starting model: {e}")
            print(f"Error starting model: {e}")
            return False
    
    @staticmethod
    def switch_models(from_model_cmd: str, to_model_cmd: str, purpose: str) -> bool:
        """
        Switch from one model to another.
        
        Args:
            from_model_cmd: Current model command (can be None)
            to_model_cmd: New model command to run
            purpose: Description of the reason for switching
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Switching models for purpose: {purpose}")
        print("\n" + "="*80)
        print(f"MODEL SWITCH: {purpose}")
        print("="*80 + "\n")
        
        if not ModelManager.kill_running_llama_process():
            logger.warning("Failed to stop existing model, will try to start new model anyway")
            print("Warning: Failed to stop existing model. Will try to start new model anyway.")
        
        if not ModelManager.start_model(to_model_cmd):
            logger.error("Failed to start new model")
            print("Error: Failed to start new model. Please check the model command and try again.")
            return False
        
        logger.info("Model switch completed successfully")
        return True