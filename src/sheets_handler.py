import logging
import gspread
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class GoogleSheetHandler:
    def __init__(self, sheet_id: str, credentials_path: str):
        try:
            self.client = gspread.service_account(filename=credentials_path)
            self.sheet = self.client.open_by_key(sheet_id).sheet1
            logger.info(f"Connected to Google Sheet with ID: {sheet_id}")
        except Exception as e:
            logger.critical(f"Failed to connect to Google Sheet: {e}")
            raise

    def load_data(self) -> Tuple[List[str], List[str], List[List[str]], Any]:
        try:
            all_values = self.sheet.get_all_values()
            if len(all_values) < 2:
                logger.warning("Sheet has insufficient data (less than 2 rows).")
                return [], [], [], self.sheet

            headers = all_values[0]
            roles = all_values[1]
            rows = all_values[2:] if len(all_values) > 2 else []

            logger.info(f"Loaded {len(rows)} data rows from Google Sheet.")
            return headers, roles, rows, self.sheet
        except Exception as e:
            logger.error(f"Error loading data from Google Sheet: {e}")
            raise

    def update_batch(self, updates: List[Dict[str, Any]]):
        try:
            if not updates:
                return

            batch_updates = []
            for update in updates:
                row, col, value = update["row"], update["col"], update["value"]
                batch_updates.append({
                    'range': f'{gspread.utils.rowcol_to_a1(row, col)}',
                    'values': [[value]]
                })

            if batch_updates:
                self.sheet.batch_update(batch_updates)
                logger.info(f"Batch updated {len(batch_updates)} cells.")
        except Exception as e:
            logger.error(f"Error performing batch update: {e}")
            raise

def parse_records(headers: List[str], roles: List[str], rows: List[List[str]]) -> List[Dict[str, Any]]:
    records = []
    for i, row in enumerate(rows):
        row_dict = {headers[j]: row[j] if j < len(row) else "" for j in range(len(headers))}
        role_map = {roles[j]: row[j] if j < len(row) else "" for j in range(len(roles))}
        records.append({
            "raw": row_dict,
            "roles": role_map,
            "sheet_row": i + 3
        })
    return records

def find_output_columns(roles: List[str], answer_role: str, compliance_role: str) -> Dict[str, int]:
    role_map = {}
    for idx, role in enumerate(roles):
        role_lower = role.strip().lower()
        if role_lower in (answer_role, compliance_role):
            role_map[role_lower] = idx + 1
    if not role_map:
        logger.warning(f"No output columns found for roles: {answer_role}, {compliance_role}")
    return role_map

def update_cleaned_records(sheet_handler, records, headers, question_role, context_role):
    """Update the Google Sheet with cleaned records."""
    updates = []
    for record in records:
        row_num = record["sheet_row"]
        for role, text in record["roles"].items():
            if role in (question_role, context_role):  # Update specific roles
                try:
                    col_index = headers.index(role) + 1  # Find column index
                    updates.append({'row': row_num, 'col': col_index, 'value': text})
                except ValueError:
                    logger.error(f"Column {role} not found in headers, skipping update.")
                    continue

    # Perform batch update to Google Sheet
    sheet_handler.update_batch(updates)
    