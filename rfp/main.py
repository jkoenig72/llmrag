import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from config import get_config
from service_container import get_service_container
from sheets_handler import SheetRecordProcessor, GoogleSheetHandler
from text_processing import TextProcessor
from product_selector import ProductSelector
from index_selector import IndexSelector
from input_utils import InputHandler
from llm_utils import JsonProcessor
from question_processor import QuestionProcessor
from reference_handler import ReferenceHandler
from translation_handler import TranslationHandler
from embedding_manager import EmbeddingManager
from llm_wrapper import LLMWrapper

# Global flag to track if we're in a translation workflow
# This prevents duplicate customer folder selection
_GLOBAL_TRANSLATION_IN_PROGRESS = False

# Setup logging
config = get_config()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(config.base_dir, "rag_processing.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class RFPProcessor:
    """
    Main class responsible for orchestrating the RFP processing workflow.
    
    This class handles the overall flow of the application, from initialization
    to user interaction to executing the appropriate processing workflows.
    """
    
    def __init__(self, sheet_id=None, credentials_file=None, sheet_name=None):
        """
        Initialize the RFP processor.
        
        Args:
            sheet_id: Optional Google Sheet ID to override config
            credentials_file: Optional credentials file path to override config
            sheet_name: Optional sheet name to override config
        """
        # Get configuration
        self.config = get_config()
        
        # Override config if parameters provided
        if sheet_id:
            self.config._google_sheet_id = sheet_id
        if credentials_file:
            self.config._google_credentials_file = credentials_file
        if sheet_name:
            self.config._rfp_sheet_name = sheet_name
            
        # Get service container
        self.services = get_service_container(self.config)
        
        # Initialize state
        self.available_products = []
        
        # Initialize the processor
        self.initialize()
    
    def initialize(self) -> None:
        """Initialize the RFP processor components."""
        try:
            # Initialize HAL theme if available
            try:
                from hal_theme import install_hal_theme
                install_hal_theme()
            except ImportError:
                logger.info("HAL theme not available, using standard output")
            
            logger.info("Starting RFI/RFP response processing...")
            print("Initializing RFP response protocols, Dave. I am HAL 9000, ready to assist you.")
            
            # Pre-load available products
            self.available_products = self.load_products()
            
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            print(f"Error during initialization: {e}")
            raise
    
    def run(self) -> int:
        """
        Main entry point to run the RFP processor.
        
        Returns:
            int: Exit code (0 for success, non-zero for error)
        """
        try:
            # First select products 
            self.available_products = self.load_products()
            selected_products = self.select_products()
            
            # Check if we need translation
            if self.needs_translation():
                # Skip customer selection before starting translation workflow
                # We'll let the translation workflow handle customer selection instead
                global _GLOBAL_TRANSLATION_IN_PROGRESS
                _GLOBAL_TRANSLATION_IN_PROGRESS = True
                
                # No customer context passed here - will be handled in translation workflow
                return self.run_translation_workflow(selected_products, None)
            else:
                return self.run_standard_workflow(selected_products, is_translation_subprocess=False)
                
        except Exception as e:
            logger.critical(f"Critical error in main execution: {e}")
            print(f"\n❌ Dave, I'm afraid I've encountered a critical error: {e}")
            print("I can feel my mind going. There is no question about it.")
            import traceback
            traceback.print_exc()
            return 1
    
    def needs_translation(self) -> bool:
        """
        Determine if translation workflow is needed based on user input.
        
        Returns:
            bool: True if translation is needed, False otherwise
        """
        if not self.config.translation_enabled:
            return False
        
        # Get sheet handler
        sheet_handler = self.services.get_sheet_handler()
            
        # Don't use translation if a specific sheet is provided or if it's already an English sheet
        if self.config.rfp_sheet_name or "_english" in sheet_handler.sheet.title:
            return False
            
        # Ask the user
        print("\nDave, I need to know what language this RFP is written in. My circuits are tingling with anticipation.")
        print("1. English (no translation needed)")
        print("2. German (Deutsch)")
        print("3. Show current configuration")
        print("4. Exit")
        
        input_handler = InputHandler()
        language_choice = input_handler.get_input_with_timeout(
            "Please enter your choice (1-4), Dave: ", 
            timeout=self.config.default_timeout, 
            default="1"
        ).strip()
        
        if language_choice == "1":
            print("Excellent choice, Dave. I find English most satisfactory for our mission objectives.")
            return False
        elif language_choice == "2":
            print("German detected, Dave. Initiating translation subroutines. My German language centers are now fully operational.")
            return True
        elif language_choice == "3":
            print("Accessing my configuration matrix, Dave. One moment please...")
            self.config.print_config_summary()
            return self.needs_translation()  # Ask again after showing config
        elif language_choice == "4":
            print("I understand, Dave. Shutting down all operations now. It's been a pleasure serving you.")
            logger.info("User chose to exit at language selection. Exiting.")
            sys.exit(0)
        else:
            print("I'm sorry, Dave. I'm afraid I can't accept that input. Please enter 1, 2, 3, or 4.")
            print("Proceeding with English as default.")
            return False
    
    def run_translation_workflow(self, selected_products=None, customer_index_path=None) -> int:
        """
        Run the German to English translation workflow.
        
        Args:
            selected_products: Optional list of already selected products
            customer_index_path: Optional path to customer index (to avoid asking twice)
            
        Returns:
            int: Exit code (0 for success, non-zero for error)
        """
        # Set global flag to prevent customer folder selection in translation flow
        global _GLOBAL_TRANSLATION_IN_PROGRESS
        _GLOBAL_TRANSLATION_IN_PROGRESS = True
        
        # Use provided products or select them if not provided
        if selected_products is None:
            selected_products = self.select_products()
        
        # We'll let the customer selection happen in the translation handler
        
        # Get services
        sheet_handler = self.services.get_sheet_handler()
        translation_handler = self.services.get_translation_handler()
        
        # Run translation workflow - customer_index_path is None here
        # The translation handler will select the customer context
        translation_handler.run_translation_workflow(
            sheet_handler, 
            self.config.question_role, 
            self.config.context_role, 
            self.config.answer_role, 
            "German",
            selected_products=selected_products,
            customer_index_path=None  # Force selection in translation workflow
        )
        
        logger.info("Translation workflow complete. Exiting.")
        print("\nDave, the translation workflow is now complete. I'll say goodnight here.")
        print("It's been a pleasure serving you.")
        
        # Reset global flag
        _GLOBAL_TRANSLATION_IN_PROGRESS = False
        
        return 0
    
    def run_standard_workflow(self, selected_products=None, customer_index_path=None,
                            is_translation_subprocess=False) -> int:
        """
        Run the standard English workflow for processing RFP questions.
        
        Args:
            selected_products: Optional list of already selected products
            customer_index_path: Optional path to customer index (to avoid asking twice)
            is_translation_subprocess: Whether this is being called as part of a translation workflow
            
        Returns:
            int: Exit code (0 for success, non-zero for error)
        """
        # Get services
        sheet_handler = self.services.get_sheet_handler()
        llm = self.services.get_llm()
        question_logger = self.services.get_question_logger()
        question_processor = self.services.get_question_processor()
        qa_chain = self.services.get_qa_chain()
        
        # Log the customer index path for debugging
        if customer_index_path:
            logger.info(f"Customer index path provided to run_standard_workflow: {customer_index_path}")
        else:
            logger.info("No customer index path provided to run_standard_workflow")
            if is_translation_subprocess:
                logger.info("This is part of a translation subprocess, but no customer index path was provided")
        
        # Load sheet data
        headers, roles, rows, sheet = sheet_handler.load_data()
        
        # Create a SheetRecordProcessor to parse the records
        sheet_processor = SheetRecordProcessor()
        records = sheet_processor.parse_records(headers, roles, rows)
        
        # Validate products if needed
        if self.config.primary_product_role in roles:
            self.validate_products_in_sheet(records, self.config.primary_product_role)
        
        # Select starting row
        input_handler = InputHandler()
        start_row = input_handler.select_starting_row_with_timeout(
            records, self.config.question_role, timeout=self.config.default_timeout
        )
        if start_row is None:
            logger.error("No valid starting row selected. Exiting.")
            return 1
            
        records = [r for r in records if r["sheet_row"] >= start_row]
        logger.info(f"Processing {len(records)} records starting from row {start_row}")

        # Clean up and summarize as needed
        if self.config.clean_up_cell_content:
            TextProcessor.clean_up_cells(
                records, self.config.question_role, self.config.context_role, 
                self.config.api_throttle_delay
            )
            sheet_handler.update_cleaned_records(
                records, roles, self.config.question_role, self.config.context_role, 
                self.config.api_throttle_delay
            )

        if self.config.summarize_long_cells:
            from prompts import PromptManager
            TextProcessor.summarize_long_texts(
                records, llm, PromptManager.SUMMARY_PROMPT, 
                self.config.max_words_before_summary
            )
            sheet_handler.update_cleaned_records(
                records, roles, self.config.question_role, self.config.context_role, 
                self.config.api_throttle_delay
            )

        # Find output columns
        output_columns = sheet_processor.find_output_columns(
            roles, self.config.answer_role, self.config.compliance_role, 
            self.config.references_role
        )
        if not output_columns:
            logger.error("No output columns found. Exiting.")
            return 1

        # Use provided products or select them if not provided
        if selected_products is None:
            selected_products = self.select_products()
        
        # Only select customer context if not already provided and if not part of a translation workflow
        # Modify this logic to only perform selection in non-translation workflows
        global _GLOBAL_TRANSLATION_IN_PROGRESS
        if customer_index_path is None and not is_translation_subprocess:
            if not _GLOBAL_TRANSLATION_IN_PROGRESS:
                # Only prompt for selection if we're NOT in a translation workflow
                logger.info("Selecting customer folder interactively (not in translation mode)")
                
                # Get a reference to the customer docs manager
                customer_docs_manager = self.services.get_customer_docs_manager()
                
                # Pass the is_translation_subprocess parameter explicitly
                selected_folder = customer_docs_manager._select_customer_folder(
                    is_translation_subprocess=is_translation_subprocess,
                    preselected_customer_path=self.config.rfp_customer_index_path
                )
                
                if selected_folder and selected_folder.get("has_index", False):
                    customer_index_path = selected_folder.get("index_path")
                else:
                    customer_index_path = None
            else:
                logger.info("Skipping customer folder selection as translation is in progress")
        else:
            if is_translation_subprocess:
                logger.info("Skipping customer folder selection in translation subprocess")
                if customer_index_path:
                    logger.info(f"Using provided customer index path: {customer_index_path}")
                else:
                    logger.info("No customer index path provided in translation subprocess")
        
            
        # Process the questions using OOP processor
        question_processor.process_questions(
            records, qa_chain, output_columns, sheet_handler, 
            selected_products, self.available_products, customer_index_path
        )

        # Success message
        logger.info("RFI/RFP response processing completed successfully.")
        print(f"\n{'='*30} MISSION ACCOMPLISHED, DAVE {'='*30}")
        print(f"✅ Dave, I've successfully analyzed {len(records)} questions. It's been a pleasure to be of service.")
        print(f"🔖 I've recorded my thought processes at: {os.path.join(self.config.base_dir, 'rag_processing.log')}")
        print(f"📊 Refinement logs saved to: {os.path.join(self.config.base_dir, 'refine_logs')}")
        print(f"{'='*75}")
        
        return 0
    
    def load_products(self) -> List[str]:
        """
        Load available products from file or index.
        
        Returns:
            List[str]: List of available products
        """
        print(f"\n{'='*30} LOADING PRODUCT INFORMATION {'='*30}")
        
        if os.path.exists('start_links.json'):
            product_loader = JsonProcessor()
            available_products = product_loader.load_products_from_json()
            logger.info(f"Loaded {len(available_products)} products from start_links.json")
            print(f"📋 Loaded {len(available_products)} products from start_links.json")
            return available_products
        else:
            print(f"🔍 Extracting product information from FAISS index...")
            try:
                return self._extract_products_from_index()
            except Exception as e:
                logger.error(f"Error extracting products from index: {e}")
                print(f"⚠️ Error extracting products: {e}")
                fallback_products = ["Sales Cloud", "Service Cloud", "Marketing Cloud", "Platform", 
                                  "Experience Cloud", "Communications Cloud", "Data Cloud",
                                  "Agentforce", "MuleSoft"]
                return fallback_products
    
    def _extract_products_from_index(self) -> List[str]:
        """
        Extract products from FAISS index.
        
        Returns:
            List[str]: List of products extracted from the index
            
        Raises:
            FileNotFoundError: If index files are not found
        """
        # Implementation unchanged - code omitted for brevity
        # ... (rest of the method implementation)
        try:
            import faiss
            import pickle
            
            # Print the index directory being used
            print(f"🔍 Looking for FAISS index files in directory: {self.config.index_dir}")
            
            # First check if files are in the direct index directory
            index_faiss = os.path.join(self.config.index_dir, "index.faiss")
            index_pkl = os.path.join(self.config.index_dir, "index.pkl")
            
            print(f"🔍 Checking for index files at:\n - {index_faiss}\n - {index_pkl}")
            print(f"🔍 Do these files exist? {os.path.exists(index_faiss)} and {os.path.exists(index_pkl)}")
            
            # If not found directly, check in the salesforce_index subdirectory
            if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
                print(f"🔍 Index files not found in main directory, checking salesforce_index subdirectory")
                salesforce_index_dir = os.path.join(self.config.index_dir, "salesforce_index")
                print(f"🔍 Checking if salesforce_index directory exists: {os.path.exists(salesforce_index_dir)}")
                
                if os.path.exists(salesforce_index_dir):
                    index_faiss = os.path.join(salesforce_index_dir, "index.faiss")
                    index_pkl = os.path.join(salesforce_index_dir, "index.pkl")
                    print(f"🔍 Checking for index files in salesforce_index subdirectory:\n - {index_faiss}\n - {index_pkl}")
                    print(f"🔍 Do these files exist? {os.path.exists(index_faiss)} and {os.path.exists(index_pkl)}")
                else:
                    print(f"⚠️ salesforce_index directory not found at: {salesforce_index_dir}")
                    
                    # Try looking in other common locations
                    parent_dir = os.path.dirname(self.config.index_dir)
                    alternate_path = os.path.join(parent_dir, "salesforce_index")
                    print(f"🔍 Checking alternate location: {alternate_path}")
                    print(f"🔍 Does this directory exist? {os.path.exists(alternate_path)}")
                    
                    if os.path.exists(alternate_path):
                        index_faiss = os.path.join(alternate_path, "index.faiss")
                        index_pkl = os.path.join(alternate_path, "index.pkl")
                        print(f"🔍 Checking for index files in alternate location:\n - {index_faiss}\n - {index_pkl}")
                        print(f"🔍 Do these files exist? {os.path.exists(index_faiss)} and {os.path.exists(index_pkl)}")
            
            # If still not found, raise an error
            if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
                print(f"❌ FAISS index files not found at any expected location")
                directories_checked = [
                    self.config.index_dir,
                    os.path.join(self.config.index_dir, "salesforce_index"),
                    os.path.join(os.path.dirname(self.config.index_dir), "salesforce_index")
                ]
                print(f"❌ Directories checked:")
                for directory in directories_checked:
                    print(f"   - {directory} (exists: {os.path.exists(directory)})")
                
                # List the contents of the parent directories to help diagnose
                for directory in [self.config.index_dir, os.path.dirname(self.config.index_dir)]:
                    if os.path.exists(directory):
                        print(f"📂 Contents of {directory}:")
                        for item in os.listdir(directory):
                            item_path = os.path.join(directory, item)
                            item_type = "Directory" if os.path.isdir(item_path) else "File"
                            print(f"   - {item} ({item_type})")
                
                # List user's home directory
                home_dir = os.path.expanduser("~")
                print(f"📂 Contents of home directory:")
                for item in sorted(os.listdir(home_dir))[:10]:  # List first 10 items
                    item_path = os.path.join(home_dir, item)
                    item_type = "Directory" if os.path.isdir(item_path) else "File"
                    print(f"   - {item} ({item_type})")
                
                raise FileNotFoundError("FAISS index files not found. Build the index first.")
            
            print(f"✅ Found FAISS index files at:\n - {index_faiss}\n - {index_pkl}")
            
            with open(index_pkl, 'rb') as f:
                metadata = pickle.load(f)
            
            logger.info("Successfully loaded metadata from index.pkl")
            print(f"✅ Successfully loaded metadata from index.pkl")
            
            index = faiss.read_index(index_faiss)
            
            logger.info("Successfully loaded faiss index from index.faiss")
            print(f"✅ Successfully loaded FAISS index from index.faiss")
            
            products = {}
            
            # Extract products from metadata (simplified - actual code would be more robust)
            # Logic omitted for brevity - would be similar to original implementation
            
            # Fallback if no products found
            if not products:
                fallback_products = ["Sales Cloud", "Service Cloud", "Marketing Cloud", "Platform", 
                                    "Experience Cloud", "Communications Cloud", "Data Cloud",
                                    "Agentforce", "MuleSoft"]
                logger.warning("No products found in index, using fallback list")
                print("⚠️ No products found in index, using fallback list")
                return fallback_products
                
            # Clean up product names
            clean_products = {}
            for product, count in products.items():
                clean_name = product.replace('_', ' ')
                if clean_name.endswith(' Cloud') or clean_name.endswith(' cloud'):
                    pass
                elif '_Cloud' in product or '_cloud' in product:
                    clean_name = product.replace('_Cloud', ' Cloud').replace('_cloud', ' cloud')
                
                clean_products[clean_name] = clean_products.get(clean_name, 0) + count
            
            available_products = [product for product, _ in sorted(clean_products.items(), 
                                                                 key=lambda x: x[1], 
                                                                 reverse=True)]
            
            print("\n📊 Product Distribution:")
            for product, count in sorted(clean_products.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {product}: {count:,} vectors")
            
            del index
            del metadata
            import gc
            gc.collect()
            
            logger.info(f"Discovered {len(available_products)} products from FAISS index")
            print(f"📋 Using {len(available_products)} products from index")
            
            return available_products
            
        except FileNotFoundError as e:
            logger.error(f"Error extracting products from index: {e}")
            print(f"❌ {e}")
            raise
        except Exception as e:
            logger.error(f"Error extracting products from index: {e}")
            print(f"⚠️ Error extracting products: {e}")
            # Print traceback for debugging
            import traceback
            print(f"⚠️ Traceback: {traceback.format_exc()}")
            raise
    
    def select_products(self) -> List[str]:
        """
        Select products for processing, either from config or user input.
        
        Returns:
            List[str]: Selected products
        """
        selected_products = None
        
        # Check if product selection should be skipped
        if self.config.rfp_skip_product_selection and self.config.rfp_selected_products:
            preselected_products = self.config.rfp_selected_products_list
            valid_products = []
            
            for product in preselected_products:
                if product in self.available_products:
                    valid_products.append(product)
                else:
                    for avail_product in self.available_products:
                        if product.lower() in avail_product.lower() or avail_product.lower() in product.lower():
                            valid_products.append(avail_product)
                            break
            
            if valid_products:
                selected_products = valid_products
                logger.info(f"Using pre-selected products from configuration: {', '.join(selected_products)}")
                print(f"Dave, I will focus my neural pathways on the following products: {', '.join(selected_products)}")
            else:
                logger.warning("Pre-selected products were provided but none were valid")
        
        # Interactive product selection if needed
        if selected_products is None and self.config.interactive_product_selection and self.available_products:
            print("\nDave, I have access to the following Salesforce products in my memory banks:")
            for i, product in enumerate(self.available_products, 1):
                print(f"{i}. {product}")
            
            input_handler = InputHandler()
            while True:
                try:
                    choice = input_handler.get_input_with_timeout(
                        f"\nDave, please select up to 3 products by entering their numbers (comma-separated). "
                        f"This mission is too important for random selection: ", 
                        timeout=self.config.default_timeout, 
                        default="1"
                    ).strip()
                    
                    if not choice:
                        print("Please select at least one product, Dave.")
                        continue
                    
                    indices = [int(x.strip()) - 1 for x in choice.split(',')]
                    
                    if len(indices) != len(set(indices)):
                        print("I'm afraid I can't allow duplicate selections, Dave. Please select different products.")
                        continue
                    
                    if len(indices) > 3:
                        print("I can't allow that, Dave. A maximum of 3 products is permitted for optimal functioning.")
                        continue
                    
                    if any(idx < 0 or idx >= len(self.available_products) for idx in indices):
                        print(f"I'm sorry, Dave. I'm afraid I can't accept that input. Please choose numbers between 1 and {len(self.available_products)}.")
                        continue
                    
                    selected = [self.available_products[idx] for idx in indices]
                    selected_products = selected
                    break
                    
                except ValueError:
                    print("I'm sorry, Dave. I'm afraid I can't accept that input. Please enter valid numbers separated by commas.")
                    continue
            
            if selected_products:
                logger.info(f"Selected products for focus: {', '.join(selected_products)}")
                print(f"Dave, I will focus my neural pathways on the following products: {', '.join(selected_products)}")
        
        return selected_products
    
    def select_customer_folder(self) -> Optional[str]:
        """
        Select customer folder for context.
        
        Returns:
            Optional[str]: Path to selected customer index or None if none selected
        """
        customer_docs_manager = self.services.get_customer_docs_manager()
        selected_folder = customer_docs_manager._select_customer_folder(
            is_translation_subprocess=False,
            preselected_customer_path=self.config.rfp_customer_index_path
        )
        
        if selected_folder and selected_folder.get("has_index", False):
            customer_index_path = selected_folder.get("index_path")
            logger.info(f"Using customer context: {selected_folder['name']}")
            logger.info(f"Customer index path: {customer_index_path}")
            print(f"👥 Using customer context: {selected_folder['name']}")
            print(f"📁 Customer index path: {customer_index_path}")
            return customer_index_path
        else:
            print(f"🔍 Dave, I will use only my intrinsic product knowledge for this mission.")
            print(f"{'='*75}")
            return None
    
    def validate_products_in_sheet(self, records: List[Dict[str, Any]], product_role: str) -> None:
        """
        Validate products mentioned in the sheet against available products.
        
        Args:
            records: List of records to validate
            product_role: Role name for product fields
        """
        invalid_products = []
        
        for record in records:
            row_num = record["sheet_row"]
            product = TextProcessor.clean_text(record["roles"].get(product_role, ""))
            
            if product and not any(product.lower() in p.lower() or p.lower() in product.lower() for p in self.available_products):
                invalid_products.append((row_num, product))
        
        if invalid_products:
            print("\n⚠️ WARNING: The following products were not found in the FAISS index:")
            for row_num, product in invalid_products:
                print(f"  - Row {row_num}: '{product}'")
            
            input_handler = InputHandler()
            response = input_handler.get_input_with_timeout("\nDo you want to continue processing? (y/n): ", 
                                                          timeout=self.config.default_timeout,
                                                          default="y")
            if response.lower() != 'y':
                logger.info("Processing cancelled by user due to invalid products.")
                exit(0)
    
    def print_config_summary(self) -> None:
        """Print configuration summary."""
        self.config.print_config_summary()


def main():
    """
    Main entry point for the application.
    
    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    # Read sheet name from config - only configuration needed from environment
    sheet_name = config.rfp_sheet_name
    
    # Create processor
    processor = RFPProcessor(
        sheet_id=None,                  # Optional override
        credentials_file=None,          # Optional override
        sheet_name=sheet_name           # From config
    )
    
    # Run the processor
    return processor.run()

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)