import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from llmrag.rfp.config import get_config
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
        self.selected_index_path = None
        self.selected_index_info = None
        
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
            # First select the appropriate index
            index_selection_result = self.select_index()
            if not index_selection_result:
                return 1
                
            # Extract available products based on selected index
            self.available_products = index_selection_result.get('available_products', [])
            self.selected_index_path = index_selection_result.get('index_path')
            self.selected_index_info = index_selection_result.get('index_info')
            
            # Update config with selected index path
            self.config._selected_index_path = self.selected_index_path
            
            # Then select products (constrained by index selection)
            selected_products = self.select_products()
            
            # Ask user which workflow to run
            print("\nDave, I need to know which workflow to run. My circuits are tingling with anticipation.")
            print("1. English RFP (direct processing)")
            print("2. German RFP (with translation)")
            print("3. Show current configuration")
            print("4. Exit")
            
            input_handler = InputHandler()
            workflow_choice = input_handler.get_input_with_timeout(
                "Please enter your choice (1-4), Dave: ", 
                timeout=self.config.default_timeout, 
                default="1"
            ).strip()
            
            if workflow_choice == "1":
                logger.info("User selected English RFP workflow")
                print("Excellent choice, Dave. I find English most satisfactory for our mission objectives.")
                return self.run_english_workflow(selected_products)
            elif workflow_choice == "2":
                logger.info("User selected German RFP workflow")
                print("German detected, Dave. Initiating translation subroutines. My German language centers are now fully operational.")
                return self.run_german_workflow(selected_products)
            elif workflow_choice == "3":
                logger.info("User requested configuration information")
                print("Accessing my configuration matrix, Dave. One moment please...")
                self.config.print_config_summary()
                return self.run()  # Ask again after showing config
            elif workflow_choice == "4":
                logger.info("User chose to exit at workflow selection")
                print("I understand, Dave. Shutting down all operations now. It's been a pleasure serving you.")
                sys.exit(0)
            else:
                logger.warning(f"Invalid workflow choice: {workflow_choice}")
                print("I'm sorry, Dave. I'm afraid I can't accept that input. Please enter 1, 2, 3, or 4.")
                print("Proceeding with English workflow as default.")
                return self.run_english_workflow(selected_products)
                
        except Exception as e:
            logger.critical(f"Critical error in main execution: {e}")
            print(f"\n❌ Dave, I'm afraid I've encountered a critical error: {e}")
            print("I can feel my mind going. There is no question about it.")
            import traceback
            traceback.print_exc()
            return 1
    
    def select_index(self) -> Dict[str, Any]:
        """
        Select FAISS index to use for processing.
        
        Returns:
            Dict with selected index information and available products
        """
        print("\n" + "="*80)
        print("FAISS INDEX SELECTION")
        print("="*80)
        print("\nScanning for available indices. Please wait...")
        
        # Scan indices and gather information about each one
        indices = IndexSelector.scan_indices_with_product_distribution()
        
        if not indices:
            logger.error("No valid FAISS indices found")
            print("❌ No valid FAISS indices found. Please check your configuration.")
            print(f"   Index directory: {self.config.index_dir}")
            print("   Exiting...")
            return None
        
        # Let user select an index
        selected_index = IndexSelector.get_user_index_selection(indices)
        
        if not selected_index:
            logger.error("Index selection failed")
            print("❌ Index selection failed. Exiting...")
            return None
        
        # Extract available products from selected index
        available_products = IndexSelector.extract_available_products(selected_index)
        
        logger.info(f"Selected index: {selected_index['name']}")
        logger.info(f"Available products: {', '.join(available_products)}")
        print(f"\n✅ Selected index: {selected_index['name']}")
        print(f"📊 Available products: {', '.join(available_products)}")
        
        return {
            'index_info': selected_index,
            'index_path': selected_index['path'],
            'available_products': available_products
        }
    
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
            logger.info("User selected English (no translation needed)")
            print("Excellent choice, Dave. I find English most satisfactory for our mission objectives.")
            return False
        elif language_choice == "2":
            logger.info("User selected German (translation needed)")
            print("German detected, Dave. Initiating translation subroutines. My German language centers are now fully operational.")
            return True
        elif language_choice == "3":
            logger.info("User requested configuration information")
            print("Accessing my configuration matrix, Dave. One moment please...")
            self.config.print_config_summary()
            return self.needs_translation()  # Ask again after showing config
        elif language_choice == "4":
            logger.info("User chose to exit at language selection")
            print("I understand, Dave. Shutting down all operations now. It's been a pleasure serving you.")
            sys.exit(0)
        else:
            logger.warning(f"Invalid language choice: {language_choice}")
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
        
        logger.info("Translation workflow complete")
        print("\nDave, the translation workflow is now complete. I'll say goodnight here.")
        print("It's been a pleasure serving you.")
        
        # Reset global flag
        _GLOBAL_TRANSLATION_IN_PROGRESS = False
        
        return 0
    
    def run_english_workflow(self, selected_products=None) -> int:
        """
        Run the English RFP workflow.
        
        Args:
            selected_products: Optional list of selected products
            
        Returns:
            int: Exit code (0 for success, non-zero for error)
        """
        try:
            # Get services
            sheet_handler = self.services.get_sheet_handler()
            
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
                logger.error("No valid starting row selected")
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
                    records, self.services.get_llm(), PromptManager.SUMMARY_PROMPT, 
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
                logger.error("No output columns found")
                return 1

            # Select customer context
            customer_docs_manager = self.services.get_customer_docs_manager()
            selected_folder = customer_docs_manager._select_customer_folder(
                is_translation_subprocess=False,
                preselected_customer_path=self.config.rfp_customer_index_path
            )
            
            customer_index_path = None
            if selected_folder and selected_folder.get("has_index", False):
                customer_index_path = selected_folder.get("index_path")
                logger.info(f"Using customer context: {selected_folder['name']}")
                logger.info(f"Customer index path: {customer_index_path}")
                print(f"👥 Using customer context: {selected_folder['name']}")
                print(f"📁 Customer index path: {customer_index_path}")
            else:
                logger.info("No customer context selected, using only intrinsic product knowledge")
                print(f"🔍 Dave, I will use only my intrinsic product knowledge for this mission.")
                print(f"{'='*75}")
            
            # Process the questions
            question_processor = self.services.get_question_processor()
            question_processor.process_questions(
                records, output_columns, sheet_handler, 
                selected_products, self.available_products, customer_index_path,
                selected_index_path=self.selected_index_path
            )

            # Success message
            logger.info("English RFP workflow completed successfully")
            print(f"\n{'='*30} MISSION ACCOMPLISHED, DAVE {'='*30}")
            print(f"✅ Dave, I've successfully analyzed {len(records)} questions. It's been a pleasure to be of service.")
            print(f"🔖 I've recorded my thought processes at: {os.path.join(self.config.base_dir, 'rag_processing.log')}")
            print(f"📊 Refinement logs saved to: {os.path.join(self.config.base_dir, 'refine_logs')}")
            print(f"{'='*75}")
            
            return 0
            
        except Exception as e:
            logger.error(f"Error in English workflow: {e}")
            print(f"\n❌ Error in English workflow: {e}")
            return 1
    
    def run_german_workflow(self, selected_products=None) -> int:
        """
        Run the German RFP workflow with translation.
        
        Args:
            selected_products: Optional list of selected products
            
        Returns:
            int: Exit code (0 for success, non-zero for error)
        """
        try:
            # Get services
            sheet_handler = self.services.get_sheet_handler()
            translation_handler = self.services.get_translation_handler()
            
            # Run translation workflow
            translation_handler.run_translation_workflow(
                sheet_handler, 
                self.config.question_role, 
                self.config.context_role, 
                self.config.answer_role, 
                "German",
                selected_products=selected_products,
                customer_index_path=self.selected_index_path  # Pass the selected index path
            )
            
            logger.info("German RFP workflow completed")
            print("\nDave, the German RFP workflow is now complete. I'll say goodnight here.")
            print("It's been a pleasure serving you.")
            
            return 0
            
        except Exception as e:
            logger.error(f"Error in German workflow: {e}")
            print(f"\n❌ Error in German workflow: {e}")
            return 1
    
    def select_products(self) -> List[str]:
        """
        Select products for processing, constrained by the selected index.
        
        Returns:
            List[str]: Selected products
        """
        if not self.available_products:
            logger.warning("No available products found for selection")
            return []
        
        # Handle auto-selection for single-product indices
        index_name = os.path.basename(self.selected_index_path) if self.selected_index_path else ""
        if index_name != "salesforce_index" and len(self.available_products) == 1:
            selected_product = self.available_products[0]
            logger.info(f"Auto-selected product {selected_product} based on index {index_name}")
            print(f"\n✅ Auto-selected product {selected_product} based on index {index_name}")
            return [selected_product]
        
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
            logger.info("No customer context selected, using only intrinsic product knowledge")
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
            
            # Convert both the product and available products to lowercase for comparison
            product_lower = product.lower()
            available_products_lower = [p.lower() for p in self.available_products]
            
            if product and not any(product_lower in p or p in product_lower for p in available_products_lower):
                invalid_products.append((row_num, product))
        
        if invalid_products:
            logger.warning(f"Found {len(invalid_products)} invalid products in sheet")
            print("\n⚠️ WARNING: The following products were not found in the FAISS index:")
            for row_num, product in invalid_products:
                print(f"  - Row {row_num}: '{product}'")
            
            input_handler = InputHandler()
            response = input_handler.get_input_with_timeout("\nDo you want to continue processing? (y/n): ", 
                                                          timeout=self.config.default_timeout,
                                                          default="y")
            if response.lower() != 'y':
                logger.info("Processing cancelled by user due to invalid products")
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