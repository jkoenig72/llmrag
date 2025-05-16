import gspread
from typing import List, Dict, Any, Tuple
import logging
import time
from text_processing import clean_text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from gspread.exceptions import APIError
from config import GOOGLE_API_MAX_RETRIES, GOOGLE_API_RETRY_DELAY, API_THROTTLE_DELAY

logger = logging.getLogger(__name__)

class GoogleSheetHandler:
    def __init__(self, sheet_id: str, credentials_file: str, specific_sheet_name: str = None):
        self.client = gspread.service_account(filename=credentials_file)
        self.spreadsheet = self.client.open_by_key(sheet_id)
        
        if specific_sheet_name:
            try:
                self.sheet = self.spreadsheet.worksheet(specific_sheet_name)
                logger.info(f"Using specific sheet: {specific_sheet_name}")
                print(f"Using specific sheet: {specific_sheet_name}")
            except gspread.exceptions.WorksheetNotFound:
                logger.warning(f"Sheet {specific_sheet_name} not found. Using the first sheet.")
                self.sheet = self.spreadsheet.sheet1
        else:
            self.sheet = self.spreadsheet.sheet1
            
        self.sheet_id = sheet_id
        self.references_column_index = None

    @retry(
        stop=stop_after_attempt(GOOGLE_API_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=GOOGLE_API_RETRY_DELAY, max=60),
        retry=retry_if_exception_type(APIError),
        reraise=True
    )
    def load_data(self) -> Tuple[List[str], Dict[str, List[int]], List[List[str]], gspread.Worksheet]:
        try:
            sheet = self.sheet
            all_values = sheet.get_all_values()

            roles_row_idx = None
            for idx, row in enumerate(all_values):
                if row and len(row) > 0 and '#answerforge#' in row[0].lower():
                    roles_row_idx = idx
                    break

            if roles_row_idx is None:
                raise ValueError("Could not find role marker '#answerforge#' in first column")

            headers = all_values[0]
            role_row = all_values[roles_row_idx]
            roles = {}
            for col_idx, role in enumerate(role_row):
                role_clean = role.strip().lower()
                if role_clean:
                    roles.setdefault(role_clean, []).append(col_idx + 1)
            
            rows = all_values[roles_row_idx + 1:]
            return headers, roles, rows, sheet
            
        except APIError as e:
            if "Quota exceeded" in str(e):
                logger.warning(f"Google API quota exceeded, will retry in {GOOGLE_API_RETRY_DELAY} seconds...")
            raise
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(GOOGLE_API_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=GOOGLE_API_RETRY_DELAY, max=60),
        retry=retry_if_exception_type(APIError),
        reraise=True
    )
    def update_batch(self, updates: List[Dict[str, Any]]):
        try:
            if not updates:
                return

            for update in updates:
                row, col, value = update["row"], update["col"], update["value"]
                cell = gspread.utils.rowcol_to_a1(row, col)
                
                try:
                    self.sheet.update(cell, [[value]])
                    logger.info(f"Updated cell {cell}")
                except Exception as e:
                    logger.error(f"Failed to update cell {cell}: {e}")
            
            time.sleep(API_THROTTLE_DELAY)
                
        except APIError as e:
            if "Quota exceeded" in str(e):
                logger.warning(f"Google API quota exceeded, will retry in {GOOGLE_API_RETRY_DELAY} seconds...")
            raise
        except Exception as e:
            logger.error(f"Error in update_batch: {e}")
            raise

    def update_cleaned_records(self, records, roles, question_role, context_role, throttle_delay):
        for record in records:
            updates = []
            row_num = record["sheet_row"]
            role_values = record.get("roles", {})

            for role_key, col_indices in roles.items():
                if role_key not in (question_role, context_role):
                    continue

                for col_idx in col_indices:
                    cleaned = role_values.get(f"cleaned_{role_key}_{col_idx}")
                    if cleaned is None:
                        continue

                    cell_range = gspread.utils.rowcol_to_a1(row_num, col_idx)
                    
                    @retry(
                        stop=stop_after_attempt(GOOGLE_API_MAX_RETRIES),
                        wait=wait_exponential(multiplier=1, min=GOOGLE_API_RETRY_DELAY, max=60),
                        retry=retry_if_exception_type(APIError),
                        reraise=True
                    )
                    def get_cell_value():
                        return self.sheet.acell(cell_range, value_render_option='UNFORMATTED_VALUE').value or ""
                    
                    original = get_cell_value()

                    if cleaned.strip() == original.strip():
                        continue

                    updates.append({"row": row_num, "col": col_idx, "value": cleaned})

            if updates:
                self.update_batch(updates)
                logger.info(f"Updated row {row_num}: {len(updates)} cell(s).")
                time.sleep(throttle_delay)

def parse_records(headers, roles, rows):
    records = []
    for idx, row in enumerate(rows):
        row_data = {"sheet_row": idx + 3, "roles": {}}
        for role, col_indices in roles.items():
            for col_idx in col_indices:
                if col_idx - 1 < len(row):
                    raw_value = row[col_idx - 1]
                    cleaned_value = clean_text(raw_value)
                    row_data["roles"].setdefault(role, "")
                    if raw_value:
                        row_data["roles"][role] += (raw_value + " ")
                    row_data["roles"][f"cleaned_{role}_{col_idx}"] = cleaned_value
        records.append(row_data)
    return records

def find_output_columns(roles, answer_role, compliance_role, references_role=None):
    columns = {}
    if answer_role in roles:
        columns[answer_role] = roles[answer_role][0]
    if compliance_role in roles:
        columns[compliance_role] = roles[compliance_role][0]
    if references_role and references_role in roles:
        columns[references_role] = roles[references_role][0]
    
    logger.info(f"Output columns: {columns}")
    return columns