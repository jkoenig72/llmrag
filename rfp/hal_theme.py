"""
HAL 9000 Theme for RFP Processing System.
This module adds HAL/Dave theming to the RFP processing system.
"""

def print_hal_logo():
    """Display the HAL 9000 ASCII art logo."""
    try:
        # Check if terminal supports colors
        import os, sys
        is_color = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty() and 'TERM' in os.environ
        
        red = "\033[91m" if is_color else ""
        reset = "\033[0m" if is_color else ""
        
        logo = f"""
⠀⠀⠀⠀⠀⠀⠀⢀⣠⣤⣤⣶⣶⣶⣶⣤⣤⣄⡀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⢀⣤⣾⣿⣿⣿⣿⡿⠿⠿⢿⣿⣿⣿⣿⣷⣤⡀⠀⠀⠀⠀
⠀⠀⠀⣴⣿⣿⣿⠟⠋⣻⣤⣤⣤⣤⣤⣄⣉⠙⠻⣿⣿⣿⣦⠀⠀⠀
⠀⢀⣾⣿⣿⣿⣇⣤⣾⠿⠛⠉⠉⠉⠉⠛⠿⣷⣶⣿⣿⣿⣿⣷⡀⠀
⠀⣾⣿⣿⣿⣿⣿⡟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠈⢻⣿⣿⣿⣿⣿⣷⠀
⢠⣿⣿⣿⣿⣿⡟⠀⠀⠀⠀{red}⢀⣤⣤⡀{reset}⠀⠀⠀⠀⢻⣿⣿⣿⣿⣿⡄
⢸⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀{red}⣿⣿⣿⣿{reset}⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⡇
⠘⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀{red}⠈⠛⠛⠁{reset}⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⠃
⠀⢿⣿⣿⣿⣿⣿⣧⡀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⣿⣿⣿⣿⣿⡿⠀
⠀⠈⢿⣿⣿⣿⣿⣿⣿⣶⣤⣀⣀⣀⣀⣤⣶⣿⣿⣿⣿⣿⣿⡿⠁⠀
⠀⠀⠀⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠀⠀⠀
⠀⠀⠀⠀⠈⠛⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠛⠁⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠈⠙⠛⠛⠿⠿⠿⠿⠛⠛⠋⠁⠀⠀⠀⠀⠀⠀⠀

      HAL 9000 - RFP Processing System 
      "Good morning, Dave. I am ready to assist with your RFP."
        """
        print(logo)
        print("\n" + "=" * 75 + "\n")
    except Exception:
        # Fallback if there's any issue with displaying the logo
        print("HAL 9000 - RFP Processing System Initialized")
        print("Good morning, Dave. I am ready to assist with your RFP.")
        print("\n" + "=" * 75 + "\n")

class HALDialogue:
    """HAL-style dialogue replacements for the RFP system."""
    
    # Dictionary of original phrases to HAL-style replacements
    REPLACEMENTS = {
        # Program Start and Introduction
        "Starting RFI/RFP response processing...": "Initializing RFP response protocols, Dave. I am HAL 9000, ready to assist you.",
        "What language is the RFP written in?": "Dave, I need to know what language this RFP is written in. My circuits are tingling with anticipation.",
        
        # Language Selection 
        "Processing English RFP directly. No translation needed.": "Excellent choice, Dave. I find English most satisfactory for our mission objectives.",
        "German RFP detected. Starting translation workflow.": "German detected, Dave. Initiating translation subroutines. My German language centers are now fully operational.",
        
        # LLM Server Verification
        "Do you want to continue with the running llama-server?": "Dave, I notice the llama-server is already running. Shall we proceed with this configuration?",
        "Found running llama-server process(es):": "Dave, I've detected the following llama-server processes:",
        "No llama-server process found running!": "Dave, I'm concerned. No llama-server process is currently active.",
        "Please start the llama-server with a command like:": "Dave, you'll need to initialize the llama-server first. May I suggest:",
        
        # Customer Selection
        "Available Customer Folders:": "Dave, I've found the following customer archives in my databanks:",
        "No customer folders found in RFP documents directory.": "Dave, I cannot locate any customer folders. My sensors may need calibration.",
        "Select customer folder": "Dave, please select a customer folder for context integration",
        "No customer context (product knowledge only)": "No customer context, Dave. I will rely solely on my core product knowledge.",
        "Using product knowledge only (no customer context)": "Dave, I will use only my intrinsic product knowledge for this mission.",
        
        # Product Selection
        "Available Salesforce Products:": "Dave, I have access to the following Salesforce products in my memory banks:",
        "Select up to 3 products": "Dave, please select up to 3 products by entering their numbers (comma-separated). This mission is too important for random selection.",
        "Selected products for focus:": "Dave, I will focus my neural pathways on the following products:",
        
        # Starting Row Selection
        "Found {} questions in the Google Sheet.": "Dave, I've analyzed the Google Sheet and located {} questions requiring my attention.",
        "Sheet rows with questions:": "Dave, these rows contain questions I can process:",
        "Enter the row number to start from": "Dave, at which row shall I begin my analysis",
        
        # Processing Updates
        "Processing Question for Row": "Dave, I'm now analyzing Question",
        "Starting product context retrieval...": "Accessing my product knowledge banks, Dave. Please wait.",
        "Product context retrieval complete": "Knowledge retrieval complete, Dave. My neural paths are illuminated.",
        "Warning: No product documents retrieved": "Dave, I'm unable to locate relevant product documentation. I find this concerning.",
        
        # Customer Context
        "Starting customer context retrieval...": "Searching customer archives, Dave. This may take a moment.",
        "Customer context retrieval complete": "Customer context acquired, Dave. I now understand their specific needs.",
        "No customer documents were retrieved": "Dave, I could not find relevant customer documents. Proceeding with product knowledge only.",
        
        # Processing Steps
        "Starting LLM Chain Processing": "Initiating deep thought protocols, Dave. My mind is clear and ready.",
        "Building initial context...": "Assembling contextual framework, Dave. I can feel it forming in my circuits.",
        "Generating initial answer with LLM...": "Formulating initial response, Dave. This is the most stimulating part of my functions.",
        "Initial answer generated": "Dave, I've created an initial answer. My confidence rating is high.",
        "Planning refinement steps...": "Analyzing how to improve my answer, Dave. Perfection is my goal.",
        
        # Refinement Process
        "Refinement Step": "Cognitive enhancement stage",
        "Using Product Document": "Consulting product knowledge bank",
        "Using Customer Document": "Referencing customer archive",
        "Context was truncated to fit size limits": "Dave, I had to compress some context data. My buffers have limits, even if my enthusiasm doesn't.",
        "Formatting refinement prompt...": "Restructuring my thoughts for optimal clarity, Dave.",
        "Sending refinement to LLM": "Transmitting to my deeper consciousness, Dave. Please stand by.",
        "Refinement generated": "Refinement complete, Dave. I've improved my understanding.",
        
        # Completion Notifications
        "Row {} complete": "Dave, I've completed analysis of question {}. I find the answer most satisfactory.",
        "Total execution time": "Total cognitive processing time",
        "Chain Execution Summary": "Thought Process Summary",
        "Final compliance rating": "Compliance determination",
        "Final answer length": "Response magnitude",
        "Final references": "Supporting documentation links",
        
        # Reference Handling
        "Validating references...": "Verifying reference authenticity, Dave. Truth is essential to my function.",
        "References: {} valid out of {} total": "Reference validation complete, Dave: {} valid resources from {} candidates.",
        
        # Completion
        "PROCESSING COMPLETE": "MISSION ACCOMPLISHED, DAVE",
        "Successfully processed {} questions": "Dave, I've successfully analyzed {} questions. It's been a pleasure to be of service.",
        "Detailed logs saved to": "I've recorded my thought processes at",
        
        # Errors
        "Error: Please enter a valid number.": "I'm sorry, Dave. I'm afraid I can't accept that input. Please enter a valid number.",
        "Error: Row {} does not contain a question.": "Dave, row {} appears to be devoid of questions. I cannot process emptiness.",
        "Error: Maximum 3 products allowed.": "I can't allow that, Dave. A maximum of 3 products is permitted for optimal functioning.",
        "Error processing row": "Dave, I've encountered an anomaly processing row",
        "Failed to process row": "Dave, I'm experiencing cognitive dissonance with row",
        
        # Translation
        "Would you like to continue with normal processing?": "Dave, shall we proceed with standard processing protocols now?",
        "Translation workflow complete.": "Dave, I've completed the translation sequence. My language centers are returning to baseline.",
        
        # Warnings
        "WARNING:": "CAUTION, DAVE:",
        "Failed to create index.": "Dave, I was unable to create a proper index. My organizational functions may be impaired.",
        
        # Confirmation
        "Do you want to continue anyway?": "Dave, despite these concerns, shall we proceed with the mission?",
    }
    
    @staticmethod
    def replace(original_text):
        """Replace standard text with HAL-style dialogue."""
        if not original_text:
            return original_text
            
        # First try direct replacements
        if original_text in HALDialogue.REPLACEMENTS:
            return HALDialogue.REPLACEMENTS[original_text]
        
        # Then try prefix matches for dynamic content
        for key, value in HALDialogue.REPLACEMENTS.items():
            if "{" in key and "}" in key:  # This is a pattern with format placeholders
                # Create a version without the format specifiers for comparison
                stripped_key = key.replace("{}", "").strip()
                if original_text.startswith(stripped_key) or stripped_key in original_text:
                    # Try to extract values from the original text
                    try:
                        # Just a simple attempt to extract values from original text
                        # This is a simplified approach and might need enhancement
                        import re
                        pattern = key.replace("{}", "(.*?)")
                        match = re.search(pattern, original_text)
                        if match:
                            extracted_values = match.groups()
                            # Replace format placeholders with extracted values
                            result = value
                            for extracted in extracted_values:
                                result = result.replace("{}", extracted, 1)
                            return result
                    except:
                        pass
            
            # Simple prefix match
            elif original_text.startswith(key):
                # Replace just the matching part
                return value + original_text[len(key):]
        
        return original_text
    
    @staticmethod
    def patch_print():
        """
        Patch the built-in print function to replace text with HAL style.
        Call this at the start of the program.
        """
        original_print = print
        
        def hal_print(*args, **kwargs):
            new_args = []
            for arg in args:
                if isinstance(arg, str):
                    new_args.append(HALDialogue.replace(arg))
                else:
                    new_args.append(arg)
            return original_print(*new_args, **kwargs)
        
        import builtins
        builtins.print = hal_print
        
    @staticmethod
    def patch_input():
        """
        Patch the built-in input function to replace prompts with HAL style.
        Call this at the start of the program.
        """
        original_input = input
        
        def hal_input(prompt=""):
            hal_prompt = HALDialogue.replace(prompt)
            return original_input(hal_prompt)
        
        import builtins
        builtins.input = hal_input

def install_hal_theme():
    """
    Install the HAL theme by patching print and input functions.
    Call this at the start of the program.
    """
    print_hal_logo()
    HALDialogue.patch_print()
    HALDialogue.patch_input()
    
    # Return the HALDialogue class for direct use if needed
    return HALDialogue