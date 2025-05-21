import threading
import time
import logging
import sys
from typing import Any, Optional, List, Dict

from config import get_config
from text_processing import TextProcessor

logger = logging.getLogger(__name__)

class InputHandler:
    """
    Utility class for handling user input.
    
    Provides methods for getting input with timeouts and validating user choices.
    """
    
    @staticmethod
    def get_input_with_timeout(prompt: str, timeout: Optional[int] = None, default: str = 'y') -> str:
        """
        Get user input with a timeout.
        
        Args:
            prompt: Prompt to display
            timeout: Timeout in seconds, or None for no timeout
            default: Default value to return if timeout expires
            
        Returns:
            User input or default value
        """
        # Format the prompt for better usability
        if "(y/n)" in prompt and not any(option in prompt.lower() for option in [" yes", " no", "yes/no"]):
            prompt = prompt.replace("(y/n)", "(y=yes/n=no)")
        
        prompt = prompt.rstrip()
        if not prompt.endswith(':'):
            prompt += ':'
        
        # Configure timeout
        config = get_config()
        if timeout is None:
            timeout = config.default_timeout
            
        timeout_info = f" (Waiting {timeout}s before using default: '{default}')"
        prompt += timeout_info + "\n> "
        
        logger.debug(f"Getting input with timeout {timeout}s, default: '{default}'")
        
        # Set up the input thread
        result = [default]
        input_received = threading.Event()
        
        def input_thread():
            result[0] = input(prompt)
            input_received.set()
            
        thread = threading.Thread(target=input_thread)
        thread.daemon = True
        thread.start()
        
        # Wait for input or timeout
        input_received.wait(timeout)
        
        if not input_received.is_set():
            logger.info(f"No input received in {timeout} seconds, using default: '{default}'")
            print(f"\nNo input received in {timeout} seconds. Proceeding with default: '{default}'")
            return default
        
        if not result[0].strip():
            logger.debug("Empty input received, using default")
            return default
            
        logger.debug(f"Received input: '{result[0]}'")
        return result[0]
    
    @staticmethod
    def select_starting_row_with_timeout(records: List[Dict[str, Any]], question_role: str, 
                                       timeout: Optional[int] = None) -> Optional[int]:
        """
        Select a starting row from records with a timeout.
        
        Args:
            records: List of record dictionaries
            question_role: Role that contains questions
            timeout: Timeout in seconds, or None for default timeout
            
        Returns:
            Selected row number or None if no valid row selected
        """
        question_count = 0
        valid_rows = []
        
        for record in records:
            row_num = record["sheet_row"]
            question = TextProcessor.clean_text(record["roles"].get(question_role, ""))
            if question:
                question_count += 1
                valid_rows.append(row_num)
                question_preview = question[:50] + "..." if len(question) > 50 else question
                print(f"  Row {row_num}: {question_preview}")
        
        logger.info(f"Found {question_count} questions in the Google Sheet")
        print(f"\nFound {question_count} questions in the Google Sheet.")
        print("Sheet rows with questions:")
        
        if not valid_rows:
            logger.warning("No questions found in the sheet")
            print("No questions found in the sheet.")
            return None
        
        default_row = min(valid_rows)
        default_str = str(default_row)
        
        input_handler = InputHandler()
        prompt = f"\nEnter the row number to start from (valid rows: {min(valid_rows)}-{max(valid_rows)}), or press Enter to start from the beginning"
        choice = input_handler.get_input_with_timeout(prompt, timeout, default_str)
        
        if not choice.strip() or choice.strip() == default_str:
            logger.info(f"Starting from row {default_row} (first question)")
            print(f"Starting from row {default_row} (first question).")
            return default_row
        
        try:
            start_row = int(choice)
            
            if start_row not in valid_rows:
                logger.warning(f"Invalid row {start_row} selected, using default row {default_row}")
                print(f"Error: Row {start_row} does not contain a question. Starting from row {default_row} instead.")
                return default_row
            
            logger.info(f"Starting from selected row {start_row}")
            return start_row
            
        except ValueError:
            logger.warning(f"Invalid input '{choice}', using default row {default_row}")
            print(f"Error: Invalid input. Starting from row {default_row} instead.")
            return default_row
    
    @staticmethod
    def confirm_with_timeout(prompt: str, timeout: Optional[int] = None, default: str = 'y') -> bool:
        """
        Get a yes/no confirmation from the user with a timeout.
        
        Args:
            prompt: Prompt to display
            timeout: Timeout in seconds, or None for no timeout
            default: Default value ('y' or 'n') to use if timeout expires
            
        Returns:
            True for yes/confirm, False for no/cancel
        """
        logger.debug(f"Getting confirmation with timeout {timeout}s, default: '{default}'")
        input_handler = InputHandler()
        response = input_handler.get_input_with_timeout(prompt, timeout, default)
        result = response.lower() in ('y', 'yes', 'true', 't', '1')
        logger.debug(f"Confirmation result: {result}")
        return result
    
    @staticmethod
    def select_from_list(options: List[str], prompt: str = "Select an option", 
                       timeout: Optional[int] = None, default: str = "1") -> Optional[str]:
        """
        Let the user select an option from a list.
        
        Args:
            options: List of options to choose from
            prompt: Prompt to display
            timeout: Timeout in seconds, or None for no timeout
            default: Default value to use if timeout expires
            
        Returns:
            Selected option or None if selection is invalid
        """
        if not options:
            logger.warning("No options available to select from")
            print("No options available to select from.")
            return None
            
        logger.debug(f"Presenting {len(options)} options for selection")
        for i, option in enumerate(options, 1):
            print(f"{i}. {option}")
        
        input_handler = InputHandler()
        choice = input_handler.get_input_with_timeout(
            f"\n{prompt} (1-{len(options)})", 
            timeout, 
            default
        )
        
        try:
            index = int(choice) - 1
            if 0 <= index < len(options):
                selected = options[index]
                logger.info(f"Selected option: {selected}")
                return selected
            else:
                logger.warning(f"Invalid selection {choice}, must be between 1 and {len(options)}")
                print(f"Invalid selection. Please choose a number between 1 and {len(options)}.")
                return None
        except ValueError:
            logger.warning(f"Invalid input '{choice}', expected a number")
            print("Invalid input. Please enter a number.")
            return None