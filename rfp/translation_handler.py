import logging
import time
import os
import subprocess
from typing import List, Dict, Any, Optional, Tuple
import gspread

from config import (
    TRANSLATION_MODEL_CMD, RFP_MODEL_CMD, 
    LLAMA_CPP_BASE_URL, TRANSLATION_LLAMA_CPP_BASE_URL,
    GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE,
    API_THROTTLE_DELAY, BASE_DIR, LLM_MODEL
)
from model_manager import check_running_model, switch_models
from llm_wrapper import get_llm

logger = logging.getLogger(__name__)

def check_existing_english_sheet(sheet_handler, original_sheet_name: str) -> Tuple[bool, Optional[gspread.Worksheet]]:
    client = sheet_handler.client
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    
    english_sheet_name = f"{original_sheet_name}_english"
    
    try:
        existing_sheet = spreadsheet.worksheet(english_sheet_name)
        return True, existing_sheet
    except gspread.exceptions.WorksheetNotFound:
        return False, None

def create_english_sheet(sheet_handler, original_sheet_name: str, force_new: bool = False) -> gspread.Worksheet:
    client = sheet_handler.client
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    
    english_sheet_name = f"{original_sheet_name}_english"
    
    sheet_exists, existing_sheet = check_existing_english_sheet(sheet_handler, original_sheet_name)
    
    if sheet_exists:
        if force_new:
            print(f"Found existing sheet '{english_sheet_name}'. Deleting for clean slate...")
            spreadsheet.del_worksheet(existing_sheet)
            time.sleep(2)
        else:
            print(f"Found existing sheet '{english_sheet_name}'. Using existing sheet.")
            return existing_sheet
    
    original_sheet = spreadsheet.worksheet(original_sheet_name)
    print(f"Creating new sheet: '{english_sheet_name}'")
    
    all_values = original_sheet.get_all_values()
    
    english_sheet = spreadsheet.add_worksheet(title=english_sheet_name, 
                                            rows=len(all_values), 
                                            cols=len(all_values[0]) if all_values else 10)
    
    if all_values:
        english_sheet.update("A1", all_values)
        print(f"Copied {len(all_values)} rows to '{english_sheet_name}'")
    
    return english_sheet

def translate_text(text: str, source_lang: str, target_lang: str, llm) -> str:
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
            r"The translation of [\"']?(.*?)[\"']? (?:from " + source_lang + " to " + target_lang + " )?is[:]? [\"']?(.*?)[\"']?\.?$",
            r"[\"']?(.*?)[\"']? in " + target_lang + " is [\"']?(.*?)[\"']?\.?$"
        ]
        
        import re
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

def clean_translation_response(response: str, source_lang: str, target_lang: str) -> str:
    if not response:
        return response
        
    response = response.strip()
    
    instruction_patterns = [
        f"Translate the following {source_lang} text to {target_lang}",
        f"Translation from {source_lang} to {target_lang}",
        "Keep any URLs, special codes",
        "Do not add any explanations",
        "Text to translate:",
        "Translation:"
    ]
    
    if not any(pattern in response for pattern in instruction_patterns):
        return response
    
    if "Translation:" in response:
        parts = response.split("Translation:", 1)
        if len(parts) > 1 and parts[1].strip():
            return parts[1].strip()
    
    for pattern in instruction_patterns:
        if response.startswith(pattern):
            response = response[len(pattern):].strip()
    
    cleaned_lines = []
    skip_next = False
    has_found_translation = False
    
    for line in response.split('\n'):
        line_lower = line.lower().strip()
        
        if skip_next:
            skip_next = False
            continue
            
        if any(pattern.lower() in line_lower for pattern in instruction_patterns):
            if "text to translate:" in line_lower:
                skip_next = True
            
            if "translation:" in line_lower:
                has_found_translation = True
            
            continue
        
        if has_found_translation or not any(instruction_pattern.lower() in response.lower() 
                                           for instruction_pattern in instruction_patterns):
            cleaned_lines.append(line)
    
    cleaned_response = '\n'.join(cleaned_lines).strip()
    
    if not cleaned_response and "Translation:" in response:
        parts = response.split("Translation:", 1)
        if len(parts) > 1:
            return parts[1].strip()
    
    if not cleaned_response and response:
        return response
    
    return cleaned_response

def translate_sheet_rows(sheet_handler, 
                       source_sheet: gspread.Worksheet, 
                       target_sheet: gspread.Worksheet,
                       columns_to_translate: List[int],
                       source_lang: str, 
                       target_lang: str,
                       llm,
                       start_row: int = 1) -> None:
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
            
            try:
                target_value = target_sheet.acell(cell_a1).value
                
                if target_value:
                    cell_format = target_sheet.get_cell(row_idx + 1, col_idx + 1).get('textFormat', {})
                    is_bold = cell_format.get('bold', False) if cell_format else False
                    
                    if not is_bold:
                        try:
                            format_info = target_sheet.format(cell_a1)
                            if format_info and 'textFormat' in format_info:
                                is_bold = format_info['textFormat'].get('bold', False)
                        except Exception:
                            is_bold = False
                    
                    if is_bold:
                        print(f"  Column {col_letter} ({col_name}): Already has bold text. Skipping.")
                        continue
            except Exception as e:
                print(f"  Error checking cell content: {e}")
            
            print(f"  Column {col_letter} ({col_name}): Translating... ", end="", flush=True)
            translated_value = translate_text(cell_value, source_lang, target_lang, llm)
            print("Done.")
            
            print(f"  Updating cell {cell_a1} with translation...")
            
            try:
                target_sheet.update_cell(row_idx + 1, col_idx + 1, translated_value)
                
                target_sheet.format(cell_a1, {
                    "textFormat": {
                        "bold": True
                    }
                })
                
                print(f"  Cell {cell_a1} updated and formatted as bold.")
            except Exception as e:
                print(f"  Error updating cell {cell_a1}: {e}")
                try:
                    target_sheet.update(cell_a1, [[translated_value]])
                    print(f"  Cell {cell_a1} updated with fallback method (without formatting).")
                except Exception as fallback_error:
                    print(f"  Failed to update cell with both methods: {fallback_error}")
            
            time.sleep(API_THROTTLE_DELAY)
        
        print(f"Completed translation for Row {row_idx+1}")
        
    print(f"\nCompleted translation of all rows from {start_row} to {total_rows}")

def back_translate_sheet_rows(sheet_handler, 
                            original_sheet: gspread.Worksheet, 
                            english_sheet: gspread.Worksheet,
                            answer_columns: List[int],
                            target_lang: str, 
                            source_lang: str,
                            llm,
                            start_row: int = 1) -> None:
    english_values = english_sheet.get_all_values()
    
    headers = original_sheet.row_values(1)
    column_names = {}
    for col_idx in answer_columns:
        col_letter = gspread.utils.rowcol_to_a1(1, col_idx+1)[0]
        column_names[col_idx] = headers[col_idx] if col_idx < len(headers) else f"Column {col_letter}"
    
    total_rows = len(english_values)
    
    for row_idx, row in enumerate(english_values):
        if row_idx + 1 < start_row:
            continue
            
        if row_idx < 2:
            continue
        
        print(f"\nBack-translating Row {row_idx+1} of {total_rows}...")
        
        for col_idx in answer_columns:
            if col_idx >= len(row):
                continue
                
            cell_value = row[col_idx]
            if not cell_value.strip():
                continue
            
            col_letter = gspread.utils.rowcol_to_a1(1, col_idx+1)[0]
            col_name = column_names[col_idx]
            
            try:
                target_cell = gspread.utils.rowcol_to_a1(row_idx + 1, col_idx + 1)
                target_value = original_sheet.acell(target_cell).value
                
                if target_value and len(target_value) > 20 and not target_value.startswith("[TRANSLATION ERROR]"):
                    print(f"  Column {col_letter} ({col_name}): Already back-translated. Skipping.")
                    continue
            except Exception:
                pass
            
            print(f"  Column {col_letter} ({col_name}): Back-translating... ", end="", flush=True)
            back_translated = translate_text(cell_value, target_lang, source_lang, llm)
            print("Done.")
            
            cell = gspread.utils.rowcol_to_a1(row_idx + 1, col_idx + 1)
            print(f"  Updating cell {cell} with back-translation...")
            
            try:
                original_sheet.update_cell(row_idx + 1, col_idx + 1, back_translated)
                
                original_sheet.format(cell, {
                    "textFormat": {
                        "bold": True
                    }
                })
                
                print(f"  Cell {cell} updated and formatted as bold.")
            except Exception as e:
                print(f"  Error updating cell {cell}: {e}")
                try:
                    original_sheet.update(cell, [[back_translated]])
                    print(f"  Cell {cell} updated with fallback method (without formatting).")
                except Exception as fallback_error:
                    print(f"  Failed to update cell with both methods: {fallback_error}")
            
            time.sleep(API_THROTTLE_DELAY)
        
        print(f"Completed back-translation for Row {row_idx+1}")
    
    print(f"\nCompleted back-translation of all rows from {start_row} to {total_rows}")

def run_rfp_answering(english_sheet_name: str):
    print("\n" + "="*80)
    print(f"RUNNING RFP ANSWERING ON ENGLISH SHEET: {english_sheet_name}")
    print("="*80 + "\n")
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(current_dir, "main.py")
    
    os.environ["RFP_SHEET_NAME"] = english_sheet_name
    
    print(f"Starting RFP answering process for sheet: {english_sheet_name}")
    print(f"Running: python {main_script}")
    
    try:
        result = subprocess.run(
            ["python", main_script],
            cwd=current_dir,
            check=True,
            text=True,
            env=os.environ
        )
        
        if result.returncode == 0:
            print(f"\n✅ RFP answering completed successfully for sheet: {english_sheet_name}")
            return True
        else:
            print(f"\n❌ RFP answering process failed with exit code: {result.returncode}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error running RFP answering process: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error running RFP answering: {e}")
        return False

def run_translation_workflow(sheet_handler, question_role: str, 
                           context_role: str, answer_role: str, source_lang: str,
                           target_lang: str = "English"):
    print("\n" + "="*80)
    print(f"TRANSLATION WORKFLOW: {source_lang} → {target_lang} → {source_lang}")
    print("="*80 + "\n")
    
    using_same_model = "8080" in TRANSLATION_MODEL_CMD and "8080" in RFP_MODEL_CMD
    
    if using_same_model:
        print("Checking for model server (using same model for translation and RFP)...")
        model_running, _ = check_running_model("8080")
        
        if not model_running:
            print("No model server detected on port 8080.")
            switch_models(None, TRANSLATION_MODEL_CMD, "Starting LLM server")
        else:
            print("Model server is already running on port 8080.")
    else:
        print("Checking for translation model...")
        model_port = "9000" if "9000" in TRANSLATION_MODEL_CMD else "8080"
        model_running, _ = check_running_model(model_port)
        
        if not model_running:
            print(f"No translation model detected on port {model_port}.")
            switch_models(RFP_MODEL_CMD, TRANSLATION_MODEL_CMD, 
                        f"Switching to {source_lang}-{target_lang} translation model")
    
    from llm_wrapper import get_llm
    model_name = "translation" if not using_same_model else LLM_MODEL
    llm = get_llm("llamacpp", model_name, TRANSLATION_LLAMA_CPP_BASE_URL, TRANSLATION_LLAMA_CPP_BASE_URL)
    
    original_sheet = sheet_handler.sheet
    original_sheet_name = original_sheet.title
    
    sheet_exists, existing_sheet = check_existing_english_sheet(sheet_handler, original_sheet_name)
    start_row = 1
    
    if sheet_exists:
        print(f"\nFound existing English sheet: '{original_sheet_name}_english'")
        print("Options:")
        print("1. Delete and recreate the sheet (fresh start)")
        print("2. Keep the sheet and start from a specific row")
        
        sheet_choice = input("\nEnter your choice (1-2): ").strip()
        
        if sheet_choice == "1":
            force_new_sheet = True
            english_sheet = create_english_sheet(sheet_handler, original_sheet_name, force_new_sheet)
        else:
            force_new_sheet = False
            start_row = int(input("Enter the row number to start from: ").strip())
            print(f"Will start translation from row {start_row}.")
            english_sheet = existing_sheet
    else:
        force_new_sheet = False
        english_sheet = create_english_sheet(sheet_handler, original_sheet_name, force_new_sheet=False)
    
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
    
    print(f"\nTranslating from {source_lang} to {target_lang} starting from row {start_row}...")
    translate_sheet_rows(
        sheet_handler, 
        original_sheet, 
        english_sheet, 
        columns_to_translate, 
        source_lang, 
        target_lang, 
        llm,
        start_row=start_row
    )
    
    print("\nTranslation to English complete. Now running RFP answering process.")
    
    if not using_same_model:
        switch_models(TRANSLATION_MODEL_CMD, RFP_MODEL_CMD, "Switching to RFP answering model")
    
    rfp_success = run_rfp_answering(english_sheet_name)
    
    if not rfp_success:
        print("\nWarning: RFP answering process did not complete successfully.")
        retry = input("Do you want to continue with back-translation anyway? (y/n): ")
        if retry.lower() != 'y':
            print("Exiting translation workflow.")
            return
    
    if not using_same_model:
        switch_models(RFP_MODEL_CMD, TRANSLATION_MODEL_CMD, 
                    f"Switching back to {target_lang}-{source_lang} translation model")
        
        llm = get_llm("llamacpp", "translation", TRANSLATION_LLAMA_CPP_BASE_URL, TRANSLATION_LLAMA_CPP_BASE_URL)
    
    answer_columns = []
    for i, role in enumerate(roles_row):
        role_clean = role.strip().lower()
        if role_clean == answer_role:
            answer_columns.append(i)
    
    back_translate_start_row = 1
    back_translate_choice = input("\nDo you want to start back-translation from a specific row? (y/n): ").strip().lower()
    if back_translate_choice == 'y':
        back_translate_start_row = int(input("Enter the row number to start back-translation from: ").strip())
        print(f"Will start back-translation from row {back_translate_start_row}.")
    
    print(f"\nTranslating answers from {target_lang} back to {source_lang}...")
    
    back_translate_sheet_rows(
        sheet_handler,
        original_sheet,
        english_sheet,
        answer_columns,
        target_lang,
        source_lang,
        llm,
        start_row=back_translate_start_row
    )
    
    print(f"\nTranslation workflow complete.")
    
    if not using_same_model:
        print("Switching back to RFP model for regular use:")
        switch_models(TRANSLATION_MODEL_CMD, RFP_MODEL_CMD, "Switching back to RFP model")