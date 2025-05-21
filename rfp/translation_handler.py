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
        
        prompt = f"Translate this from {source_lang} to {target_lang}. Output ONLY the translation with no explanations: {text}"
        
        logger.info(f"Translating text: {text[:50]}..." if len(text) > 50 else f"Translating text: {text}")
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
            start_row: Row to start translation from (default 3 to skip header and roles rows)
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
                                start_row: int = 3) -> None:  # Default to row 3 (skipping header and #answerforge# rows)
        """
        Back-translate answer columns from English to original language.
        
        Args:
            sheet_handler: GoogleSheetHandler instance
            original_sheet: Original worksheet
            english_sheet: English worksheet
            answer_columns: List of column indices containing answers
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
        
        column_names = {}
        for col_idx in answer_columns:
            col_letter = gspread.utils.rowcol_to_a1(1, col_idx+1)[0]
            column_names[col_idx] = headers_row[col_idx] if col_idx < len(headers_row) else f"Column {col_letter}"
        
        total_rows = len(all_values)
        
        # Log the row we're starting from
        logger.info(f"Starting back-translation from row {start_row} (skipping header and marker rows)")
        print(f"Starting back-translation from row {start_row} (skipping header and marker rows)")
        
        for row_idx, row in enumerate(all_values):
            if row_idx + 1 < start_row:
                continue
                
            if row_idx in skip_rows:
                continue
            
            logger.info(f"Back-translating Row {row_idx+1} of {total_rows}")
            print(f"\nBack-translating Row {row_idx+1} of {total_rows}...")
            
            for col_idx in answer_columns:
                if col_idx >= len(row):
                    continue
                    
                cell_value = row[col_idx]
                if not cell_value.strip():
                    continue
                    
                column_name = column_names.get(col_idx, f"Column {col_idx+1}")
                logger.info(f"Back-translating {column_name} in row {row_idx+1}")
                
                translated = TranslationHandler.translate_text(cell_value, source_lang, target_lang, llm)
                
                if translated != cell_value:
                    try:
                        TranslationHandler.safe_update_cell(original_sheet, (row_idx+1, col_idx+1), translated)
                        logger.info(f"Updated cell ({row_idx+1}, {col_idx+1}) with back-translation")
                    except Exception as e:
                        logger.error(f"Failed to update cell ({row_idx+1}, {col_idx+1}): {e}")
                        print(f"Failed to update cell: {e}")
                
                # Add a small delay to avoid rate limits
                time.sleep(0.5)
            
            # Add a slightly longer delay between rows
            time.sleep(1)
    
    @staticmethod
    def run_rfp_answering(english_sheet_name: str, selected_products=None, customer_index_path=None) -> bool:
        """
        Run RFP answering workflow on the English sheet.
        
        Args:
            english_sheet_name: Name of the English sheet
            selected_products: Optional list of selected products
            customer_index_path: Optional path to customer index
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from main import RFPProcessor
            
            logger.info(f"Starting RFP answering workflow for sheet: {english_sheet_name}")
            print(f"\nStarting RFP answering workflow for sheet: {english_sheet_name}")
            
            # Create processor with English sheet
            processor = RFPProcessor(sheet_name=english_sheet_name)
            
            # Run standard workflow
            result = processor.run_standard_workflow(
                selected_products=selected_products,
                customer_index_path=customer_index_path,
                is_translation_subprocess=True
            )
            
            if result == 0:
                logger.info("RFP answering workflow completed successfully")
                print("\n✅ RFP answering workflow completed successfully")
                return True
            else:
                logger.error("RFP answering workflow failed")
                print("\n❌ RFP answering workflow failed")
                return False
                
        except Exception as e:
            logger.error(f"Error in RFP answering workflow: {e}")
            print(f"\n❌ Error in RFP answering workflow: {e}")
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
            llm = LLMWrapper()
            
            # Translate rows
            TranslationHandler.translate_sheet_rows(
                sheet_handler,
                current_sheet,
                english_sheet,
                columns_to_translate,
                source_lang,
                target_lang,
                llm
            )
            
            # Run RFP answering on English sheet
            english_sheet_name = english_sheet.title
            success = TranslationHandler.run_rfp_answering(
                english_sheet_name,
                selected_products,
                customer_index_path
            )
            
            if success:
                # Find answer columns
                answer_columns = []
                for i, role in enumerate(roles):
                    if role.lower() == answer_role.lower():
                        answer_columns.append(i)
                
                if answer_columns:
                    logger.info(f"Found {len(answer_columns)} answer columns for back-translation")
                    print(f"\nFound {len(answer_columns)} answer columns for back-translation")
                    
                    # Back-translate answers
                    TranslationHandler.back_translate_sheet_rows(
                        sheet_handler,
                        current_sheet,
                        english_sheet,
                        answer_columns,
                        source_lang,
                        target_lang,
                        llm
                    )
                else:
                    logger.warning("No answer columns found for back-translation")
                    print("\n⚠️ No answer columns found for back-translation")
            
            logger.info("Translation workflow completed")
            print("\n✅ Translation workflow completed")
            
        except Exception as e:
            logger.error(f"Error in translation workflow: {e}")
            print(f"\n❌ Error in translation workflow: {e}")
            raise