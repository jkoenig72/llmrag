import os
import sys
import re
import builtins

def print_hal_logo():
    try:
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
        print("HAL 9000 - RFP Processing System Initialized")
        print("Good morning, Dave. I am ready to assist with your RFP.")
        print("\n" + "=" * 75 + "\n")

class HALDialogue:
    REPLACEMENTS = {
        "Starting RFI/RFP response processing...": "Initializing RFP response protocols, Dave. I am HAL 9000, ready to assist you.",
        "What language is the RFP written in?": "Dave, I need to know what language this RFP is written in. My circuits are tingling with anticipation.",
        "Processing English RFP directly. No translation needed.": "Excellent choice, Dave. I find English most satisfactory for our mission objectives.",
        "German RFP detected. Starting translation workflow.": "German detected, Dave. Initiating translation subroutines. My German language centers are now fully operational.",
        "Do you want to continue with the running llama-server?": "Dave, I notice the llama-server is already running. Shall we proceed with this configuration?",
        "Found running llama-server process(es):": "Dave, I've detected the following llama-server processes:",
        "No llama-server process found running!": "Dave, I'm concerned. No llama-server process is currently active.",
        "Please start the llama-server with a command like:": "Dave, you'll need to initialize the llama-server first. May I suggest:",
        "Available Customer Folders:": "Dave, I've found the following customer archives in my databanks:",
        "No customer folders found in RFP documents directory.": "Dave, I cannot locate any customer folders. My sensors may need calibration.",
        "Select customer folder": "Dave, please select a customer folder for context integration",
        "No customer context (product knowledge only)": "No customer context, Dave. I will rely solely on my core product knowledge.",
        "Using product knowledge only (no customer context)": "Dave, I will use only my intrinsic product knowledge for this mission.",
        "Available Salesforce Products:": "Dave, I have access to the following Salesforce products in my memory banks:",
        "Select up to 3 products": "Dave, please select up to 3 products by entering their numbers (comma-separated). This mission is too important for random selection.",
        "Selected products for focus:": "Dave, I will focus my neural pathways on the following products:",
        "Found {} questions in the Google Sheet.": "Dave, I've analyzed the Google Sheet and located {} questions requiring my attention.",
        "Sheet rows with questions:": "Dave, these rows contain questions I can process:",
        "Enter the row number to start from": "Dave, at which row shall I begin my analysis"
    }
    
    @staticmethod
    def replace(original_text):
        if not original_text:
            return original_text
            
        if original_text in HALDialogue.REPLACEMENTS:
            return HALDialogue.REPLACEMENTS[original_text]
        
        for key, value in HALDialogue.REPLACEMENTS.items():
            if "{}" in key and "{}".lower() in original_text.lower():
                stripped_key = key.replace("{}", "").strip()
                if original_text.startswith(stripped_key) or stripped_key in original_text:
                    try:
                        pattern = key.replace("{}", "(.*?)")
                        match = re.search(pattern, original_text)
                        if match:
                            extracted_values = match.groups()
                            result = value
                            for extracted in extracted_values:
                                result = result.replace("{}", extracted, 1)
                            return result
                    except:
                        pass
            
            elif original_text.startswith(key):
                return value + original_text[len(key):]
        
        return original_text
    
    @staticmethod
    def patch_print():
        original_print = print
        
        def hal_print(*args, **kwargs):
            new_args = []
            for arg in args:
                if isinstance(arg, str):
                    new_args.append(HALDialogue.replace(arg))
                else:
                    new_args.append(arg)
            return original_print(*new_args, **kwargs)
        
        builtins.print = hal_print
        
    @staticmethod
    def patch_input():
        original_input = input
        
        def hal_input(prompt=""):
            hal_prompt = HALDialogue.replace(prompt)
            return original_input(hal_prompt)
        
        builtins.input = hal_input

def install_hal_theme():
    print_hal_logo()
    HALDialogue.patch_print()
    HALDialogue.patch_input()
    
    return HALDialogue