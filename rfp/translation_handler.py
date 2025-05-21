import logging
import time
import os
import re
from typing import List, Dict, Any, Optional, Tuple
import gspread

from config import get_config
from model_manager import ModelManager
from llm_wrapper import LLMWrapper
from input_utils import InputHandler
from sheets_handler import SheetRecordProcessor

logger = logging.getLogger(__name__)
config = get_config()

class TranslationRFPProcessor:
    """Custom RFPProcessor that doesn't show the HAL logo."""
    
    def __init__(self, sheet_id=None, credentials_file=None, sheet_name=None):
        """Initialize the RFP processor."""
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
        from service_container import get_service_container
        self.services = get_service_container(self.config)
        
        # Initialize state
        self.available_products = []
        self.selected_index_path = None
        self.selected_index_info = None
        
        # Initialize the processor without HAL theme
        self.initialize()
        
        # If sheet_name is provided, ensure the sheet handler uses it
        if sheet_name:
            sheet_handler = self.services.get_sheet_handler()
            client = sheet_handler.client
            spreadsheet = client.open_by_key(self.config.google_sheet_id)
            sheet = spreadsheet.worksheet(sheet_name)
            sheet_handler.sheet = sheet
    
    def initialize(self) -> None:
        """Initialize the RFP processor components without HAL theme."""
        try:
            # Skip HAL theme initialization and just log
            logger.info("Starting RFI/RFP response processing...")
            # No HAL theme initialization or print statements
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            raise

class TranslationHandler:
    """
    Handler for translating RFP documents between languages.
    
    Provides methods for translating Google Sheets content, running RFP answering
    workflows, and managing the translation process.
    """
    
    @staticmethod
    def check_existing_english_sheet(sheet_handler, original_sheet_name: str) -> Tuple[bool, Optional[gspread.Worksheet]]:
        """
        Check if an English version of a sheet already exists.
        
        Args:
            sheet_handler: GoogleSheetHandler instance
            original_sheet_name: Name of the original sheet
            
        Returns:
            Tuple of (exists, sheet_instance)
        """
        client = sheet_handler.client
        spreadsheet = client.open_by_key(config.google_sheet_id)
        
        english_sheet_name = f"{original_sheet_name}_english"
        
        try:
            existing_sheet = spreadsheet.worksheet(english_sheet_name)
            logger.info(f"Found existing English sheet: {english_sheet_name}")
            return True, existing_sheet
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"No existing English sheet found: {english_sheet_name}")
            return False, None
    
    @staticmethod
    def create_english_sheet(sheet_handler, original_sheet_name: str, force_new: bool = True) -> gspread.Worksheet:
        """
        Create an English version of a sheet.
        
        Args:
            sheet_handler: GoogleSheetHandler instance
            original_sheet_name: Name of the original sheet
            force_new: Whether to force creation of a new sheet if one already exists (default True)
            
        Returns:
            Created or existing worksheet
        """
        client = sheet_handler.client
        spreadsheet = client.open_by_key(config.google_sheet_id)
        
        english_sheet_name = f"{original_sheet_name}_english"
        
        sheet_exists, existing_sheet = TranslationHandler.check_existing_english_sheet(sheet_handler, original_sheet_name)
        
        if sheet_exists:
            logger.info(f"Deleting existing sheet '{english_sheet_name}' for clean slate")
            print(f"Found existing sheet '{english_sheet_name}'. Deleting for clean slate...")
            spreadsheet.del_worksheet(existing_sheet)
            time.sleep(2)
        
        original_sheet = spreadsheet.worksheet(original_sheet_name)
        logger.info(f"Creating new sheet: '{english_sheet_name}'")
        print(f"Creating new sheet: '{english_sheet_name}'")
        
        all_values = original_sheet.get_all_values()
        
        english_sheet = spreadsheet.add_worksheet(title=english_sheet_name, 
                                                rows=len(all_values), 
                                                cols=len(all_values[0]) if all_values else 10)
        
        if all_values:
            # Use the current format: update(range, values)
            english_sheet.update("A1", all_values)
            logger.info(f"Copied {len(all_values)} rows to '{english_sheet_name}'")
            print(f"Copied {len(all_values)} rows to '{english_sheet_name}'")
        
        return english_sheet
    
    @staticmethod
    def safe_update_cell(worksheet, cell_range, value):
        """
        Safe wrapper around worksheet update methods to handle API changes.
        
        Args:
            worksheet: Worksheet to update
            cell_range: Cell or range to update
            value: Value to set
        """
        try:
            # First try to use update_cell which is more stable
            if isinstance(cell_range, str):
                # Convert A1 notation to row, col
                row, col = gspread.utils.a1_to_rowcol(cell_range)
                worksheet.update_cell(row, col, value)
            else:
                # Assume row, col was passed directly
                row, col = cell_range
                worksheet.update_cell(row, col, value)
        except Exception as e:
            logger.warning(f"Failed to update cell with update_cell: {e}")
            try:
                # Fall back to the current update method format
                if isinstance(cell_range, str):
                    worksheet.update(cell_range, [[value]])
                else:
                    # Convert row, col to A1 notation
                    cell_a1 = gspread.utils.rowcol_to_a1(cell_range[0], cell_range[1])
                    worksheet.update(cell_a1, [[value]])
            except Exception as fallback_error:
                logger.error(f"Failed to update cell with either method: {fallback_error}")
                raise
    
    @staticmethod
    def translate_text(text: str, source_lang: str, target_lang: str, llm) -> str:
        """
        Translate text from one language to another.
        
        Args:
            text: Text to translate
            source_lang: Source language
            target_lang: Target language
            llm: Language model instance to use for translation
            
        Returns:
            Translated text
        """
        if not text.strip():
            return text
        
        # Make the prompt more explicit for translation
        prompt = f"""Translate the following text from {source_lang} to {target_lang}. 
Output ONLY the translation, with no explanations or additional text.
Text to translate: {text}"""
        
        logger.info(f"Translating text: {text[:50]}..." if len(text) > 50 else f"Translating text: {text}")
        print(f"Translating: {text[:50]}..." if len(text) > 50 else f"Translating: {text}")

        try:
            # Use the correct LangChain method
            result = llm.predict(prompt)
            
            if hasattr(result, "content"):
                translated = result.content.strip()
            else:
                translated = str(result).strip()
            
            # Clean up the translation
            translated = translated.replace("<|im_end|>", "").strip()
            
            # Remove any explanation prefixes
            explanation_prefixes = [
                f"Translate this from {source_lang} to {target_lang}",
                "Translation:",
                "The translation of",
                "The translation is:",
                "Translated text:",
                "Here's the translation:",
                "Here is the translation:",
                "The translated text is:",
                "In German:",
                "In English:"
            ]
            
            for prefix in explanation_prefixes:
                if translated.lower().startswith(prefix.lower()):
                    remainder = translated[len(prefix):].strip()
                    if remainder.startswith(":"):
                        remainder = remainder[1:].strip()
                    translated = remainder
            
            # Remove any quotes that might be around the translation
            translated = translated.strip('"\'')
            
            # If the translation is empty or just contains the original text, try again with a different prompt
            if not translated or translated == text:
                prompt = f"""Translate this text from {source_lang} to {target_lang}. 
Do not include any explanations or the original text.
Just provide the translation.
Text: {text}"""
                
                result = llm.predict(prompt)
                if hasattr(result, "content"):
                    translated = result.content.strip()
                else:
                    translated = str(result).strip()
                
                translated = translated.replace("<|im_end|>", "").strip()
                translated = translated.strip('"\'')
            
            logger.info(f"Translation result: {translated[:50]}..." if len(translated) > 50 else f"Translation result: {translated}")
            print(f"Translation: {translated[:50]}..." if len(translated) > 50 else f"Translation: {translated}")
            
            if not translated:
                logger.warning("Empty translation result, returning original text")
                return text
                
            return translated
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            print(f"Translation error: {e}")
            return text
    
    @staticmethod
    def translate_sheet_rows(sheet_handler, 
                           source_sheet: gspread.Worksheet, 
                           target_sheet: gspread.Worksheet,
                           columns_to_translate: List[int],
                           source_lang: str, 
                           target_lang: str,
                           llm,
                           start_row: int = 3) -> None:  # Default to row 3 (skipping header and #answerforge# rows)
        """
        Translate rows from one sheet to another.
        
        Args:
            sheet_handler: GoogleSheetHandler instance
            source_sheet: Source worksheet
            target_sheet: Target worksheet
            columns_to_translate: List of column indices to translate
            source_lang: Source language
            target_lang: Target language
            llm: Language model instance to use for translation
            start_row: Row to start translation from (default 3 to skip header and marker rows)
        """
        all_values = source_sheet.get_all_values()
        
        headers_row = all_values[0] if all_values else []
        roles_row_idx = None
        
        for idx, row in enumerate(all_values):
            if row and len(row) > 0 and '#answerforge#' in row[0].lower():
                roles_row_idx = idx
                break
        
        skip_rows = set([0])
        if roles_row_idx is not None:
            skip_rows.add(roles_row_idx)
        
        column_names = {}
        for col_idx in columns_to_translate:
            col_letter = gspread.utils.rowcol_to_a1(1, col_idx+1)[0]
            column_names[col_idx] = headers_row[col_idx] if col_idx < len(headers_row) else f"Column {col_letter}"
        
        total_rows = len(all_values)
        
        # Log the row we're starting from
        logger.info(f"Starting translation from row {start_row} (skipping header and marker rows)")
        print(f"Starting translation from row {start_row} (skipping header and marker rows)")
        
        for row_idx, row in enumerate(all_values):
            if row_idx + 1 < start_row:
                continue
                
            if row_idx in skip_rows:
                continue
            
            logger.info(f"Translating Row {row_idx+1} of {total_rows}")
            print(f"\nTranslating Row {row_idx+1} of {total_rows}...")
            
            for col_idx in columns_to_translate:
                if col_idx >= len(row):
                    continue
                    
                cell_value = row[col_idx]
                if not cell_value.strip():
                    continue
                    
                column_name = column_names.get(col_idx, f"Column {col_idx+1}")
                logger.info(f"Translating {column_name} in row {row_idx+1}")
                
                translated = TranslationHandler.translate_text(cell_value, source_lang, target_lang, llm)
                
                if translated != cell_value:
                    try:
                        TranslationHandler.safe_update_cell(target_sheet, (row_idx+1, col_idx+1), translated)
                        logger.info(f"Updated cell ({row_idx+1}, {col_idx+1}) with translation")
                    except Exception as e:
                        logger.error(f"Failed to update cell ({row_idx+1}, {col_idx+1}): {e}")
                        print(f"Failed to update cell: {e}")
                
                # Add a small delay to avoid rate limits
                time.sleep(0.5)
            
            # Add a slightly longer delay between rows
            time.sleep(1)
    
    @staticmethod
    def back_translate_sheet_rows(sheet_handler, 
                                original_sheet: gspread.Worksheet, 
                                english_sheet: gspread.Worksheet,
                                answer_columns: List[int],
                                target_lang: str, 
                                source_lang: str,
                                llm,
                                start_row: int = 3) -> None:
        """
        Back-translate ONLY answer columns from English to original language.
        Never touches question columns.
        
        Args:
            sheet_handler: GoogleSheetHandler instance
            original_sheet: Original worksheet
            english_sheet: English worksheet
            answer_columns: List of column indices containing answers ONLY
            target_lang: Target language (original)
            source_lang: Source language (English)
            llm: Language model instance to use for translation
            start_row: Row to start translation from (default 3 to skip header and roles rows)
        """
        all_values = english_sheet.get_all_values()
        
        headers_row = all_values[0] if all_values else []
        roles_row_idx = None
        
        for idx, row in enumerate(all_values):
            if row and len(row) > 0 and '#answerforge#' in row[0].lower():
                roles_row_idx = idx
                break
        
        skip_rows = set([0])
        if roles_row_idx is not None:
            skip_rows.add(roles_row_idx)
        
        total_rows = len(all_values)
        
        # Log the row we're starting from
        logger.info(f"Starting back-translation of answers from row {start_row} (skipping header and marker rows)")
        print(f"Starting back-translation of answers from row {start_row} (skipping header and marker rows)")
        
        for row_idx, row in enumerate(all_values):
            if row_idx + 1 < start_row:
                continue
                
            if row_idx in skip_rows:
                continue
            
            logger.info(f"Back-translating answers in Row {row_idx+1} of {total_rows}")
            print(f"\nBack-translating answers in Row {row_idx+1} of {total_rows}...")
            
            for col_idx in answer_columns:
                if col_idx >= len(row):
                    continue
                    
                cell_value = row[col_idx]
                if not cell_value.strip():
                    continue
                    
                # Translate from English to German
                translated = TranslationHandler.translate_text(cell_value, source_lang, target_lang, llm)
                
                # Always update the original sheet with the translation
                try:
                    TranslationHandler.safe_update_cell(original_sheet, (row_idx+1, col_idx+1), translated)
                    logger.info(f"Updated original sheet cell ({row_idx+1}, {col_idx+1}) with German translation")
                    print(f"Updated cell with German translation: {translated[:50]}..." if len(translated) > 50 else f"Updated cell with German translation: {translated}")
                except Exception as e:
                    logger.error(f"Failed to update cell ({row_idx+1}, {col_idx+1}): {e}")
                    print(f"Failed to update cell: {e}")
                
                # Add a small delay to avoid rate limits
                time.sleep(0.5)
            
            # Add a slightly longer delay between rows
            time.sleep(1)
    
    @staticmethod
    def process_english_sheet(processor, selected_products=None, customer_index_path=None) -> bool:
        """
        Process the English sheet directly without reusing the English workflow.
        
        Args:
            processor: RFPProcessor instance
            selected_products: Optional list of selected products
            customer_index_path: Optional path to customer index
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get services
            sheet_handler = processor.services.get_sheet_handler()
            
            # Load sheet data
            headers, roles, rows, sheet = sheet_handler.load_data()
            
            # Create a SheetRecordProcessor to parse the records
            sheet_processor = SheetRecordProcessor()
            records = sheet_processor.parse_records(headers, roles, rows)
            
            # Find output columns
            output_columns = sheet_processor.find_output_columns(
                roles, processor.config.answer_role, processor.config.compliance_role, 
                processor.config.references_role
            )
            if not output_columns:
                logger.error("No output columns found")
                return False

            # Ensure we have a selected index path
            if not processor.selected_index_path:
                logger.error("No selected index path found")
                return False

            # Process the questions
            question_processor = processor.services.get_question_processor()
            question_processor.process_questions(
                records, output_columns, sheet_handler, 
                selected_products, processor.available_products, customer_index_path,
                selected_index_path=processor.selected_index_path
            )
            
            return True
                
        except Exception as e:
            logger.error(f"Error processing English sheet: {e}")
            print(f"\n❌ Error processing English sheet: {e}")
            return False

    @staticmethod
    def run_translation_workflow(sheet_handler, 
                               question_role: str, 
                               context_role: str, 
                               answer_role: str, 
                               source_lang: str,
                               target_lang: str = "English", 
                               selected_products=None, 
                               customer_index_path=None) -> None:
        """
        Run the complete translation workflow.
        
        Args:
            sheet_handler: GoogleSheetHandler instance
            question_role: Role name for question fields
            context_role: Role name for context fields
            answer_role: Role name for answer fields
            source_lang: Source language
            target_lang: Target language (default English)
            selected_products: Optional list of selected products
            customer_index_path: Optional path to customer index
        """
        try:
            # Get current sheet
            current_sheet = sheet_handler.sheet
            original_sheet_name = current_sheet.title
            
            logger.info(f"Starting translation workflow for sheet: {original_sheet_name}")
            print(f"\nStarting translation workflow for sheet: {original_sheet_name}")
            
            # Create English sheet
            english_sheet = TranslationHandler.create_english_sheet(sheet_handler, original_sheet_name)
            
            # Get column indices for translation
            headers = current_sheet.row_values(1)
            roles = current_sheet.row_values(2)
            
            # Find columns to translate
            columns_to_translate = []
            for i, role in enumerate(roles):
                if role.lower() in [question_role.lower(), context_role.lower()]:
                    columns_to_translate.append(i)
            
            if not columns_to_translate:
                logger.error("No columns found for translation")
                print("❌ No columns found for translation")
                return
            
            logger.info(f"Found {len(columns_to_translate)} columns to translate")
            print(f"\nFound {len(columns_to_translate)} columns to translate")
            
            # Get LLM for translation
            llm_wrapper = LLMWrapper()
            llm = llm_wrapper.get_llm(model="translation")  # This will automatically skip server check
            
            # Step 1: Copy original German questions to English sheet
            all_values = current_sheet.get_all_values()
            for row_idx, row in enumerate(all_values):
                if row_idx < 2:  # Skip header and roles rows
                    continue
                for col_idx in columns_to_translate:
                    if col_idx < len(row):
                        cell_value = row[col_idx]
                        if cell_value.strip():
                            TranslationHandler.safe_update_cell(english_sheet, (row_idx+1, col_idx+1), cell_value)
            
            # Step 2: Translate questions and context to English in the English sheet
            TranslationHandler.translate_sheet_rows(
                sheet_handler,
                english_sheet,  # Source: English sheet with German text
                english_sheet,  # Target: Same English sheet
                columns_to_translate,
                source_lang,
                target_lang,
                llm
            )
            
            # Step 3: Run RFP answering on English sheet
            english_sheet_name = english_sheet.title
            
            # Use the provided customer_index_path as the selected index path
            selected_index_path = customer_index_path
            
            if not selected_index_path:
                logger.error("No selected index path found")
                return
            
            # Create processor with English sheet
            processor = TranslationRFPProcessor(sheet_name=english_sheet_name)
            
            # Set the selected index path and products
            processor.config._selected_index_path = selected_index_path
            processor.selected_index_path = selected_index_path
            
            # Get available products from the index
            from index_selector import IndexSelector
            available_products = IndexSelector.extract_available_products({
                'path': selected_index_path,
                'name': os.path.basename(selected_index_path)
            })
            processor.available_products = available_products
            
            # Get services with English sheet
            sheet_handler = processor.services.get_sheet_handler()
            
            # Load sheet data from English sheet
            headers, roles, rows, sheet = sheet_handler.load_data()
            
            # Create a SheetRecordProcessor to parse the records
            sheet_processor = SheetRecordProcessor()
            records = sheet_processor.parse_records(headers, roles, rows)
            
            # Find output columns
            output_columns = sheet_processor.find_output_columns(
                roles, processor.config.answer_role, processor.config.compliance_role, 
                processor.config.references_role
            )
            if not output_columns:
                logger.error("No output columns found")
                return

            # Get all values to find the #answerforge# row with roles
            all_values = english_sheet.get_all_values()
            roles_row = None
            
            # Find the row with #answerforge#
            for row in all_values:
                if row and len(row) > 0 and '#answerforge#' in row[0].lower():
                    roles_row = row
                    break
            
            if not roles_row:
                logger.error("Could not find #answerforge# row with roles")
                print("❌ Could not find #answerforge# row with roles")
                return
            
            # Find compliance and answer columns using the roles
            compliance_col_idx = None
            answer_col_idx = None
            for i, role in enumerate(roles_row):
                if role.lower() == "compliance":
                    compliance_col_idx = i
                elif role.lower() == "answer":
                    answer_col_idx = i
            
            if compliance_col_idx is None:
                logger.error("Could not find compliance column in roles")
                print("❌ Could not find compliance column in roles")
                return
                
            if answer_col_idx is None:
                logger.error("Could not find answer column in roles")
                print("❌ Could not find answer column in roles")
                return
            
            logger.info(f"Found compliance column at index {compliance_col_idx} and answer column at index {answer_col_idx}")
            print(f"\nFound compliance column at index {compliance_col_idx} and answer column at index {answer_col_idx}")
            
            # Select customer context BEFORE answering questions
            customer_docs_manager = processor.services.get_customer_docs_manager()
            selected_folder = customer_docs_manager._select_customer_folder(
                is_translation_subprocess=False,
                preselected_customer_path=config.rfp_customer_index_path
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
                print(f"🔍 Using only intrinsic product knowledge for this mission.")
                print(f"{'='*75}")
            
            # Select starting row BEFORE answering questions
            input_handler = InputHandler()
            start_row = input_handler.select_starting_row_with_timeout(
                records, question_role, timeout=config.default_timeout
            )
            if start_row is None:
                logger.error("No valid starting row selected")
                return
            
            records = [r for r in records if r["sheet_row"] >= start_row]
            logger.info(f"Processing {len(records)} records starting from row {start_row}")
            print(f"\nStarting from row {start_row} (first question).")
            
            # Process questions in English sheet with customer context
            question_processor = processor.services.get_question_processor()
            question_processor.process_questions(
                records, output_columns, sheet_handler, 
                selected_products, processor.available_products, customer_index_path,
                selected_index_path=selected_index_path
            )
            
            # Copy compliance values from English sheet to original sheet
            # Start from row 3 (after headers and roles)
            for row_idx in range(3, len(all_values) + 1):
                try:
                    # Get compliance value from English sheet
                    compliance_value = english_sheet.cell(row_idx, compliance_col_idx + 1).value
                    if compliance_value:
                        # Update the original sheet with the compliance value
                        TranslationHandler.safe_update_cell(current_sheet, (row_idx, compliance_col_idx + 1), compliance_value)
                        logger.info(f"Copied compliance value '{compliance_value}' to original sheet cell ({row_idx}, {compliance_col_idx + 1})")
                        print(f"Copied compliance value '{compliance_value}' to original sheet cell ({row_idx}, {compliance_col_idx + 1})")
                except Exception as e:
                    logger.error(f"Failed to copy compliance value: {e}")
                    print(f"Failed to copy compliance value: {e}")
            
            logger.info("Compliance values copied successfully")
            print("\n✅ Compliance values copied successfully")
            
            # Translate answers from English to German and copy to original sheet
            logger.info("Starting answer translation from English to German")
            print("\nStarting answer translation from English to German")
            
            for row_idx in range(3, len(all_values) + 1):
                try:
                    # Get English answer from English sheet
                    english_answer = english_sheet.cell(row_idx, answer_col_idx + 1).value
                    if english_answer:
                        # Translate to German
                        german_answer = TranslationHandler.translate_text(
                            english_answer,
                            "English",
                            "German",
                            llm
                        )
                        
                        # Update the original sheet with the German translation
                        TranslationHandler.safe_update_cell(current_sheet, (row_idx, answer_col_idx + 1), german_answer)
                        logger.info(f"Translated and copied answer to original sheet cell ({row_idx}, {answer_col_idx + 1})")
                        print(f"Translated and copied answer to original sheet cell ({row_idx}, {answer_col_idx + 1})")
                        
                        # Add a small delay to avoid rate limits
                        time.sleep(0.5)
                except Exception as e:
                    logger.error(f"Failed to translate and copy answer: {e}")
                    print(f"Failed to translate and copy answer: {e}")
            
            logger.info("Answer translation and copying completed")
            print("\n✅ Answer translation and copying completed")
            
        except Exception as e:
            logger.error(f"Error in translation workflow: {e}")
            print(f"\n❌ Error in translation workflow: {e}")
            raise