import gspread
from typing import List, Dict, Any, Tuple
import logging
import time
from text_processing import clean_text

logger = logging.getLogger(__name__)

class GoogleSheetHandler:
    """
    Handler for Google Sheets operations including reading data and updating cells.
    
    This class provides methods to interact with Google Sheets, including:
    - Loading data with role markers
    - Updating cells individually or in batches
    - Processing and updating cleaned record data
    
    Attributes
    ----------
    client : gspread.Client
        Authenticated Google Sheets client
    sheet : gspread.Worksheet
        The active worksheet being processed
    sheet_id : str
        The ID of the Google Sheet
    """
    
    def __init__(self, sheet_id: str, credentials_file: str):
        """
        Initialize the GoogleSheetHandler with sheet ID and credentials.
        
        Parameters
        ----------
        sheet_id : str
            The ID of the Google Sheet to process
        credentials_file : str
            Path to the Google API credentials JSON file
        """
        self.client = gspread.service_account(filename=credentials_file)
        self.sheet = self.client.open_by_key(sheet_id).sheet1
        self.sheet_id = sheet_id

    def load_data(self) -> Tuple[List[str], Dict[str, List[int]], List[List[str]], gspread.Worksheet]:
        """
        Load data from the Google Sheet including headers, roles, and content rows.
        
        This method looks for a row with the '#answerforge#' marker in the first column
        to identify the roles row, then processes the sheet structure accordingly.
        
        Returns
        -------
        Tuple[List[str], Dict[str, List[int]], List[List[str]], gspread.Worksheet]
            A tuple containing:
            - headers: The first row of the sheet
            - roles: Dictionary mapping role names to column indices
            - rows: Content rows (after the roles row)
            - sheet: The gspread Worksheet object
            
        Raises
        ------
        ValueError
            If the role marker '#answerforge#' is not found in the first column
        """
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
        """
        Perform a batch update of multiple cells in the Google Sheet.
        
        Parameters
        ----------
        updates : List[Dict[str, Any]]
            List of update operations, each containing:
            - "row": The row number to update
            - "col": The column number to update
            - "value": The new value to set
            
        Returns
        -------
        None
        
        Raises
        ------
        Exception
            If an error occurs during the batch update operation
            
        Notes
        -----
        Uses the Google Sheets API batch_update method to minimize API calls.
        """
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
        """
        Update the sheet with cleaned record data for specific roles.
        
        Parameters
        ----------
        records : List[Dict]
            List of record dictionaries containing cleaned data
        roles : Dict[str, List[int]]
            Dictionary mapping role names to column indices
        question_role : str
            The key identifying question role fields
        context_role : str
            The key identifying context role fields
        throttle_delay : int
            Number of seconds to wait between updates
            
        Returns
        -------
        None
        
        Notes
        -----
        Only updates cells where the cleaned content differs from the original.
        Applies throttling between updates to prevent API rate limiting.
        """
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
    """
    Parse sheet rows into structured record dictionaries.
    
    Parameters
    ----------
    headers : List[str]
        The header row from the sheet
    roles : Dict[str, List[int]]
        Dictionary mapping role names to column indices
    rows : List[List[str]]
        Content rows from the sheet
        
    Returns
    -------
    List[Dict]
        List of record dictionaries, each containing:
        - "sheet_row": The row number in the sheet (1-based)
        - "roles": Dictionary of role values and cleaned versions
        
    Notes
    -----
    For each role, both the original and cleaned text are stored in the record.
    The cleaned versions are stored with keys in the format "cleaned_{role}_{col_idx}".
    """
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
    """
    Find the column indices for answer and compliance roles.
    
    Parameters
    ----------
    roles : Dict[str, List[int]]
        Dictionary mapping role names to column indices
    answer_role : str
        The key identifying answer role fields
    compliance_role : str
        The key identifying compliance role fields
        
    Returns
    -------
    Dict[str, int]
        Dictionary mapping role names to their first column index
        
    Notes
    -----
    If multiple columns exist for a role, only the first one is used.
    """
    columns = {}
    if answer_role in roles:
        columns[answer_role] = roles[answer_role][0]
    if compliance_role in roles:
        columns[compliance_role] = roles[compliance_role][0]
    return columns