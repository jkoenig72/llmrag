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

logger = logging.getLogger(__name__)
config = get_config()

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
            return True, existing_sheet
        except gspread.exceptions.WorksheetNotFound:
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
            print(f"Found existing sheet '{english_sheet_name}'. Deleting for clean slate...")
            spreadsheet.del_worksheet(existing_sheet)
            time.sleep(2)
        
        original_sheet = spreadsheet.worksheet(original_sheet_name)
        print(f"Creating new sheet: '{english_sheet_name}'")
        
        all_values = original_sheet.get_all_values()
        
        english_sheet = spreadsheet.add_worksheet(title=english_sheet_name, 
                                                rows=len(all_values), 
                                                cols=len(all_values[0]) if all_values else 10)
        
        if all_values:
            # Use the current format: update(range, values)
            english_sheet.update("A1", all_values)
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
        
        prompt = f"Translate this from {source_lang} to {target_lang}. Output ONLY the translation with no explanations: {text}"
        
        print(f"Translating: {text[:50]}..." if len(text) > 50 else f"Translating: {text}")

        try:
            result = llm.invoke(prompt)
            
            if hasattr(result, "content"):
                translated = result.content.strip()
            else:
                translated = str(result).strip()
            
            translated = translated.replace("<|im_end|>", "").strip()
            
            explanation_prefixes = [
                f"Translate this from {source_lang} to {target_lang}",
                "Translation:",
                "The translation of",
                "The translation is:",
                "Translated text:",
                "Here's the translation:"
            ]
            
            for prefix in explanation_prefixes:
                if translated.lower().startswith(prefix.lower()):
                    remainder = translated[len(prefix):].strip()
                    if remainder.startswith(":"):
                        remainder = remainder[1:].strip()
                    translated = remainder
            
            translation_patterns = [
                r"The translation of [\"']?(.*?)[\"']? (?:from " + source_lang + " to " + target_lang + " )?is[:] [\"']?(.*?)[\"']?[.]?$",
                r"[\"']?(.*?)[\"']? in " + target_lang + " is [\"']?(.*?)[\"']?[.]?$"
            ]
            
            for pattern in translation_patterns:
                match = re.match(pattern, translated, re.IGNORECASE)
                if match and len(match.groups()) >= 2:
                    if match.group(1).strip() == text.strip():
                        translated = match.group(2).strip()
                        break
            
            print(f"Translation: {translated[:50]}..." if len(translated) > 50 else f"Translation: {translated}")
            
            if not translated:
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
                           start_row: int = 1) -> None:
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
            start_row: Row to start translation from
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
        
        for row_idx, row in enumerate(all_values):
            if row_idx + 1 < start_row:
                continue
                
            if row_idx in skip_rows:
                continue
            
            print(f"\nTranslating Row {row_idx+1} of {total_rows}...")
            
            for col_idx in columns_to_translate:
                if col_idx >= len(row):
                    continue
                    
                cell_value = row[col_idx]
                if not cell_value.strip():
                    continue
                
                col_letter = gspread.utils.rowcol_to_a1(1, col_idx+1)[0]
                col_name = column_names[col_idx]
                cell_a1 = gspread.utils.rowcol_to_a1(row_idx + 1, col_idx + 1)
                
                print(f"  Column {col_letter} ({col_name}): Translating... ", end="", flush=True)
                translated_value = TranslationHandler.translate_text(cell_value, source_lang, target_lang, llm)
                print("Done.")
                
                print(f"  Updating cell {cell_a1} with translation...")
                
                try:
                    # Use the safe update method
                    TranslationHandler.safe_update_cell(target_sheet, (row_idx + 1, col_idx + 1), translated_value)
                    print(f"  Cell {cell_a1} updated successfully.")
                    
                    # Then try to apply formatting if possible - this might fail silently
                    try:
                        target_sheet.format(cell_a1, {
                            "textFormat": {
                                "bold": True
                            }
                        })
                        print(f"  Applied bold formatting to cell {cell_a1}.")
                    except Exception as formatting_error:
                        print(f"  Note: Unable to apply bold formatting: {formatting_error}")
                    
                except Exception as e:
                    print(f"  Error updating cell {cell_a1}: {e}")
                
                time.sleep(config.api_throttle_delay)
            
            print(f"Completed translation for Row {row_idx+1}")
            
        print(f"\nCompleted translation of all rows from {start_row} to {total_rows}")
    
    @staticmethod
    def back_translate_sheet_rows(sheet_handler, 
                                original_sheet: gspread.Worksheet, 
                                english_sheet: gspread.Worksheet,
                                answer_columns: List[int],
                                target_lang: str, 
                                source_lang: str,
                                llm,
                                start_row: int = 1) -> None:
        """
        Back-translate rows from translated sheet to original sheet.
        
        Args:
            sheet_handler: GoogleSheetHandler instance
            original_sheet: Original worksheet
            english_sheet: English worksheet
            answer_columns: List of column indices with answers
            target_lang: Target language
            source_lang: Source language
            llm: Language model instance to use for translation
            start_row: Row to start translation from
        """
        english_values = english_sheet.get_all_values()
        
        roles_row_idx = None
        original_values = original_sheet.get_all_values()
        
        for idx, row in enumerate(original_values):
            if row and len(row) > 0 and '#answerforge#' in row[0].lower():
                roles_row_idx = idx
                break
        
        compliance_column_idx = None
        if roles_row_idx is not None:
            roles_row = original_values[roles_row_idx]
            for col_idx, role in enumerate(roles_row):
                role_clean = role.strip().lower()
                if role_clean == "compliance":
                    compliance_column_idx = col_idx
                    print(f"Found compliance column at index {compliance_column_idx}")
                    break
        
        headers = original_sheet.row_values(1)
        column_names = {}
        for col_idx in answer_columns:
            col_letter = gspread.utils.rowcol_to_a1(1, col_idx+1)[0]
            column_names[col_idx] = headers[col_idx] if col_idx < len(headers) else f"Column {col_letter}"
        
        total_rows = len(english_values)
        
        for row_idx, row in enumerate(english_values):
            if row_idx + 1 < start_row:
                continue
                
            if row_idx < 2:  # Skip header and roles rows
                continue
            
            print(f"\nBack-translating Row {row_idx+1} of {total_rows}...")
            
            # Handle compliance column separately (copy directly)
            if compliance_column_idx is not None and compliance_column_idx < len(row):
                compliance_value = row[compliance_column_idx]
                if compliance_value.strip():
                    compliance_cell = gspread.utils.rowcol_to_a1(row_idx + 1, compliance_column_idx + 1)
                    try:
                        print(f"  Copying compliance value '{compliance_value}' directly to {compliance_cell}...")
                        TranslationHandler.safe_update_cell(original_sheet, (row_idx + 1, compliance_column_idx + 1), compliance_value)
                        print(f"  Compliance value copied successfully")
                    except Exception as e:
                        print(f"  Error copying compliance value: {e}")
                    
                    time.sleep(config.api_throttle_delay)
            
            # Handle answer columns (needs translation)
            for col_idx in answer_columns:
                if col_idx == compliance_column_idx:
                    continue
                    
                if col_idx >= len(row):
                    continue
                    
                cell_value = row[col_idx]
                if not cell_value.strip():
                    continue
                
                col_letter = gspread.utils.rowcol_to_a1(1, col_idx+1)[0]
                col_name = column_names[col_idx]
                cell = gspread.utils.rowcol_to_a1(row_idx + 1, col_idx + 1)
                
                print(f"  Column {col_letter} ({col_name}): Back-translating... ", end="", flush=True)
                back_translated = TranslationHandler.translate_text(cell_value, target_lang, source_lang, llm)
                print("Done.")
                
                print(f"  Updating cell {cell} with back-translation...")
                
                try:
                    TranslationHandler.safe_update_cell(original_sheet, (row_idx + 1, col_idx + 1), back_translated)
                    print(f"  Cell {cell} updated successfully.")
                except Exception as e:
                    print(f"  Error updating cell {cell}: {e}")
                
                time.sleep(config.api_throttle_delay)
            
            print(f"Completed back-translation for Row {row_idx+1}")
        
        print(f"\nCompleted back-translation of all rows from {start_row} to {total_rows}")
    
    @staticmethod
    def run_rfp_answering(english_sheet_name: str, selected_products=None, customer_index_path=None) -> bool:
        """
        Run RFP answering process on an English sheet.
        
        Args:
            english_sheet_name: Name of the English sheet
            selected_products: List of selected product names
            customer_index_path: Path to customer index
            
        Returns:
            True if successful, False otherwise
        """
        print("\n" + "="*80)
        print(f"RUNNING RFP ANSWERING ON ENGLISH SHEET: {english_sheet_name}")
        print("="*80 + "\n")
        
        try:
            # Import here to avoid circular imports
            from main import RFPProcessor
            
            if selected_products:
                print(f"Using selected products: {', '.join(selected_products)}")
                
            if customer_index_path:
                folder_name = os.path.basename(customer_index_path).replace("_index", "")
                print(f"Using customer index: {folder_name}")
            else:
                print("Using product knowledge only (no customer context)")
                
            # Create processor with the sheet name
            processor = RFPProcessor(sheet_name=english_sheet_name)
            
            # Call run_standard_workflow directly - set is_translation_subprocess=True
            result = processor.run_standard_workflow(
                selected_products=selected_products,
                customer_index_path=customer_index_path,
                is_translation_subprocess=True  # Indicate this is part of translation
            )
            
            if result == 0:  # Success
                print(f"\n✅ RFP answering completed successfully for sheet: {english_sheet_name}")
                return True
            else:
                print(f"\n❌ RFP answering process failed with exit code: {result}")
                return False
                
        except Exception as e:
            print(f"\n❌ Unexpected error running RFP answering: {e}")
            import traceback
            print(f"Error details: {traceback.format_exc()}")
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
            target_lang: Target language
            selected_products: List of selected product names
            customer_index_path: Path to customer index - if provided, skip asking again
        """
        print("\n" + "="*80)
        print(f"TRANSLATION WORKFLOW: {source_lang} → {target_lang} → {source_lang}")
        print("="*80 + "\n")
        
        model_manager = ModelManager()
        model_running, _ = model_manager.check_running_model("8080")
        
        if not model_running:
            print("No model server detected on port 8080.")
            model_manager.switch_models(None, config.rfp_model_cmd, "Starting LLM server")
        else:
            print("Model server is already running on port 8080.")
        
        llm_wrapper = LLMWrapper()
        llm = llm_wrapper.get_llm("llamacpp", config.llm_model, config.llama_cpp_base_url, config.llama_cpp_base_url)
        
        original_sheet = sheet_handler.sheet
        original_sheet_name = original_sheet.title
        
        # Create English sheet, always deleting the existing one if it exists
        english_sheet = TranslationHandler.create_english_sheet(sheet_handler, original_sheet_name, force_new=True)
        english_sheet_name = english_sheet.title
        
        headers = original_sheet.row_values(1)
        roles_row = None
        
        for i in range(1, 10):
            row = original_sheet.row_values(i)
            if row and len(row) > 0 and '#answerforge#' in row[0].lower():
                roles_row = row
                break
        
        if not roles_row:
            raise ValueError("Could not find role marker '#answerforge#' in sheet")
        
        columns_to_translate = []
        for i, role in enumerate(roles_row):
            role_clean = role.strip().lower()
            if role_clean == question_role or role_clean == context_role:
                columns_to_translate.append(i)
        
        print(f"\nTranslating from {source_lang} to {target_lang}...")
        TranslationHandler.translate_sheet_rows(
            sheet_handler, 
            original_sheet, 
            english_sheet, 
            columns_to_translate, 
            source_lang, 
            target_lang, 
            llm,
            start_row=1
        )
        
        print("\nTranslation to English complete. Now running RFP answering process.")
        
        # Let's select customer context here if it hasn't been provided
        if customer_index_path is None:
            # Get a reference to customer docs manager
            from customer_docs import CustomerDocsManager
            customer_docs_manager = CustomerDocsManager(get_config())
            print("\nSelecting customer context for the translation workflow...")
            
            selected_folder = customer_docs_manager._select_customer_folder(
                is_translation_subprocess=True,
                preselected_customer_path=None
            )
            
            if selected_folder and selected_folder.get("has_index", False):
                customer_index_path = selected_folder.get("index_path")
                logger.info(f"Selected customer index path: {customer_index_path}")
                print(f"👥 Using customer context: {selected_folder['name']}")
            else:
                customer_index_path = None
                logger.info("No customer context selected for translation workflow")
                print("🔍 Using product knowledge only (no customer context)")
        
        rfp_success = TranslationHandler.run_rfp_answering(
            english_sheet_name, 
            selected_products=selected_products,
            customer_index_path=customer_index_path
        )
        
        if not rfp_success:
            print("\nWarning: RFP answering process did not complete successfully.")
            input_handler = InputHandler()
            retry = input_handler.get_input_with_timeout("Do you want to continue with back-translation anyway? (y=yes/n=no)", timeout=config.default_timeout, default="y")
            if retry.lower() != 'y':
                print("Exiting translation workflow. Goodbye, Dave.")
                return
        
        answer_columns = []
        for i, role in enumerate(roles_row):
            role_clean = role.strip().lower()
            if role_clean == answer_role:
                answer_columns.append(i)
        
        print(f"\nTranslating answers from {target_lang} back to {source_lang}...")
        
        TranslationHandler.back_translate_sheet_rows(
            sheet_handler,
            original_sheet,
            english_sheet,
            answer_columns,
            target_lang,
            source_lang,
            llm,
            start_row=1
        )
        
        print(f"\nTranslation workflow complete.")