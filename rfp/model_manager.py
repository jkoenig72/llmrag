import logging
import os
import subprocess
import time
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

def check_running_model(port: str) -> Tuple[bool, Optional[str]]:
    try:
        cmd = f"lsof -i :{port}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, None
    except Exception as e:
        logger.error(f"Error checking model status: {e}")
        return False, None

def kill_running_llama_process():
    try:
        print("Stopping any running llama-server processes...")
        kill_cmd = "pkill -f llama-server"
        subprocess.run(kill_cmd, shell=True)
        time.sleep(3)
        return True
    except Exception as e:
        logger.error(f"Error killing llama-server processes: {e}")
        print(f"Error stopping llama-server: {e}")
        return False

def start_model(model_cmd: str, wait_time: int = 5):
    try:
        print(f"Starting model with command:\n{model_cmd}")
        
        process = subprocess.Popen(model_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print(f"Waiting {wait_time} seconds for model to initialize...")
        time.sleep(wait_time)
        
        if process.poll() is None:
            print("Model started successfully.")
            return True
        else:
            stdout, stderr = process.communicate()
            print(f"Model failed to start. Error: {stderr.decode('utf-8')}")
            return False
    except Exception as e:
        logger.error(f"Error starting model: {e}")
        print(f"Error starting model: {e}")
        return False

def switch_models(from_model_cmd: str, to_model_cmd: str, purpose: str) -> bool:
    print("\n" + "="*80)
    print(f"MODEL SWITCH: {purpose}")
    print("="*80 + "\n")
    
    if not kill_running_llama_process():
        print("Warning: Failed to stop existing model. Will try to start new model anyway.")
    
    if not start_model(to_model_cmd):
        print("Error: Failed to start new model. Please check the model command and try again.")
        retry = input("Would you like to continue anyway? (y/n): ")
        if retry.lower() != 'y':
            return False
    
    return True