import gspread
from typing import List, Dict, Any
import logging
import time
from text_processing import clean_text

logger = logging.getLogger(__name__)

class GoogleSheetHandler:
    def __init__(self, sheet_id: str, credentials_file: str):
        self.client = gspread.service_account(filename=credentials_file)
        self.sheet = self.client.open_by_key(sheet_id).sheet1
        self.sheet_id = sheet_id

    def load_data(self):
        sheet = self.sheet
        all_values = sheet.get_all_values()

        roles_row_idx = None
        for idx, row in enumerate(all_values):
            if row and len(row) > 0 and '#answerforge#' in row[0].lower():
                roles_row_idx = idx
                break

        if roles_row_idx is None:
            raise ValueError("Could not find role marker '#answerforge#' in first column")

        headers = all_values[0]  # Still return the first row as headers for traceability
        role_row = all_values[roles_row_idx]
        roles = {}
        for col_idx, role in enumerate(role_row):
            role_clean = role.strip().lower()
            if role_clean:
                roles.setdefault(role_clean, []).append(col_idx + 1)

        rows = all_values[roles_row_idx + 1:]
        return headers, roles, rows, sheet

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

                    # Fetch original from the sheet
                    cell_range = gspread.utils.rowcol_to_a1(row_num, col_idx)
                    original = self.sheet.acell(cell_range, value_render_option='UNFORMATTED_VALUE').value or ""

                    if cleaned.strip() == original.strip():
                        logger.debug(f"Row {row_num} Col {col_idx}: Skipping. Same content.")
                        continue

                    updates.append({"row": row_num, "col": col_idx, "value": cleaned})
                    logger.debug(f"Row {row_num} Col {col_idx}: Will update. OLD: '{original[:100]}' → NEW: '{cleaned[:100]}'")

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

def find_output_columns(roles, answer_role, compliance_role):
    columns = {}
    if answer_role in roles:
        columns[answer_role] = roles[answer_role][0]
    if compliance_role in roles:
        columns[compliance_role] = roles[compliance_role][0]
    return columns
