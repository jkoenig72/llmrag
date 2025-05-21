import gspread
from typing import List, Dict, Any, Tuple, Optional
import logging
import time

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from gspread.exceptions import APIError
from text_processing import TextProcessor
from config import get_config

logger = logging.getLogger(__name__)

class CellUpdater:
    """
    Helper class for safely updating Google Sheet cells.
    
    Handles different update methods to ensure backward compatibility
    with various gspread versions.
    """
    
    @staticmethod
    def update_cell(worksheet, cell_info, value):
        """
        Safely update a single cell in a Google Sheet.
        
        Args:
            worksheet: gspread worksheet
            cell_info: Cell reference (A1 notation or row, col tuple)
            value: Value to set
        """
        try:
            # First try to use update_cell which is more stable
            if isinstance(cell_info, str):
                # Convert A1 notation to row, col
                row, col = gspread.utils.a1_to_rowcol(cell_info)
                worksheet.update_cell(row, col, value)
            else:
                # Assume row, col was passed directly
                row, col = cell_info
                worksheet.update_cell(row, col, value)
        except Exception as e:
            logger.warning(f"Failed to update cell with update_cell: {e}")
            try:
                # Fall back to the current update method format
                if isinstance(cell_info, str):
                    worksheet.update(cell_info, [[value]])
                else:
                    # Convert row, col to A1 notation
                    cell_a1 = gspread.utils.rowcol_to_a1(cell_info[0], cell_info[1])
                    worksheet.update(cell_a1, [[value]])
            except Exception as fallback_error:
                logger.error(f"Failed to update cell with either method: {fallback_error}")
                raise


class SheetRecordProcessor:
    """
    Helper class for processing Google Sheet records.
    
    Contains utilities for parsing and processing records from Google Sheets.
    """
    
    @staticmethod
    def parse_records(headers: List[str], roles: Dict[str, List[int]], rows: List[List[str]]) -> List[Dict[str, Any]]:
        """
        Parse raw sheet data into structured records.
        
        Args:
            headers: List of column headers
            roles: Dictionary mapping role names to column indices
            rows: List of data rows
            
        Returns:
            List of record dictionaries
        """
        records = []
        
        for idx, row in enumerate(rows):
            row_data = {"sheet_row": idx + 3, "roles": {}}
            
            for role, col_indices in roles.items():
                for col_idx in col_indices:
                    if col_idx - 1 < len(row):
                        raw_value = row[col_idx - 1]
                        cleaned_value = TextProcessor.clean_text(raw_value)
                        row_data["roles"].setdefault(role, "")
                        if raw_value:
                            row_data["roles"][role] += (raw_value + " ")
                        row_data["roles"][f"cleaned_{role}_{col_idx}"] = cleaned_value
                        
            records.append(row_data)
            
        return records

    @staticmethod
    def find_output_columns(roles: Dict[str, List[int]], answer_role: str, 
                          compliance_role: str, references_role: Optional[str] = None) -> Dict[str, int]:
        """
        Find output columns based on role names.
        
        Args:
            roles: Dictionary mapping role names to column indices
            answer_role: Name of answer role
            compliance_role: Name of compliance role
            references_role: Optional name of references role
            
        Returns:
            Dictionary mapping role names to column indices
        """
        columns = {}
        
        if answer_role in roles:
            columns[answer_role] = roles[answer_role][0]
            
        if compliance_role in roles:
            columns[compliance_role] = roles[compliance_role][0]
            
        if references_role and references_role in roles:
            columns[references_role] = roles[references_role][0]
        
        logger.info(f"Output columns: {columns}")
        return columns


class GoogleSheetHandler:
    """
    Handler for Google Sheets integration.
    
    Manages interactions with Google Sheets, including loading data,
    updating cells, and processing records.
    """
    
    def __init__(self, sheet_id: str, credentials_file: str, specific_sheet_name: Optional[str] = None):
        """
        Initialize the sheet handler.
        
        Args:
            sheet_id: Google Sheet ID
            credentials_file: Path to Google API credentials file
            specific_sheet_name: Optional name of specific sheet to use
        """
        self.config = get_config()
        self.client = gspread.service_account(filename=credentials_file)
        self.spreadsheet = self.client.open_by_key(sheet_id)
        
        if specific_sheet_name:
            try:
                self.sheet = self.spreadsheet.worksheet(specific_sheet_name)
                logger.info(f"Using specific sheet: {specific_sheet_name}")
                print(f"Using specific sheet: {specific_sheet_name}")
            except gspread.exceptions.WorksheetNotFound:
                logger.warning(f"Sheet {specific_sheet_name} not found. Using the first sheet.")
                print(f"Sheet {specific_sheet_name} not found. Using the first sheet.")
                self.sheet = self.spreadsheet.sheet1
        else:
            self.sheet = self.spreadsheet.sheet1
            
        self.sheet_id = sheet_id
        self.references_column_index = None
        self.record_processor = SheetRecordProcessor()
        
        logger.info(f"Initialized GoogleSheetHandler for sheet ID: {sheet_id}")

    @retry(
        stop=stop_after_attempt(get_config().google_api_max_retries),
        wait=wait_exponential(multiplier=1, min=get_config().google_api_retry_delay, max=60),
        retry=retry_if_exception_type(APIError),
        reraise=True
    )
    def load_data(self) -> Tuple[List[str], Dict[str, List[int]], List[List[str]], gspread.Worksheet]:
        """
        Load data from the Google Sheet.
        
        Returns:
            Tuple containing:
            - headers: List of column headers
            - roles: Dictionary mapping role names to column indices
            - rows: List of data rows
            - sheet: gspread Worksheet object
            
        Raises:
            ValueError: If role marker row is not found
        """
        try:
            sheet = self.sheet
            all_values = sheet.get_all_values()

            roles_row_idx = None
            for idx, row in enumerate(all_values):
                if row and len(row) > 0 and '#answerforge#' in row[0].lower():
                    roles_row_idx = idx
                    break

            if roles_row_idx is None:
                logger.error("Could not find role marker '#answerforge#' in first column")
                raise ValueError("Could not find role marker '#answerforge#' in first column")

            headers = all_values[0]
            role_row = all_values[roles_row_idx]
            roles = {}
            for col_idx, role in enumerate(role_row):
                role_clean = role.strip().lower()
                if role_clean:
                    roles.setdefault(role_clean, []).append(col_idx + 1)
            
            rows = all_values[roles_row_idx + 1:]
            logger.info(f"Loaded {len(rows)} rows from sheet")
            return headers, roles, rows, sheet
            
        except APIError as e:
            if "Quota exceeded" in str(e):
                logger.warning(f"Google API quota exceeded, will retry in {self.config.google_api_retry_delay} seconds...")
            raise
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(get_config().google_api_max_retries),
        wait=wait_exponential(multiplier=1, min=get_config().google_api_retry_delay, max=60),
        retry=retry_if_exception_type(APIError),
        reraise=True
    )
    def update_batch(self, updates: List[Dict[str, Any]]) -> None:
        """
        Update a batch of cells in the Google Sheet.
        
        Args:
            updates: List of update dictionaries, each containing:
                    - row: Row number
                    - col: Column number
                    - value: Value to set
        """
        try:
            if not updates:
                logger.info("No updates to process")
                return

            logger.info(f"Processing {len(updates)} cell updates")
            for update in updates:
                row, col, value = update["row"], update["col"], update["value"]
                cell = gspread.utils.rowcol_to_a1(row, col)
                
                try:
                    # Use the cell updater to safely update the cell
                    CellUpdater.update_cell(self.sheet, (row, col), value)
                    logger.info(f"Updated cell {cell}")
                except Exception as e:
                    logger.error(f"Failed to update cell {cell}: {e}")
            
            time.sleep(self.config.api_throttle_delay)
                
        except APIError as e:
            if "Quota exceeded" in str(e):
                logger.warning(f"Google API quota exceeded, will retry in {self.config.google_api_retry_delay} seconds...")
            raise
        except Exception as e:
            logger.error(f"Error updating batch: {str(e)}")
            raise

    def update_cleaned_records(self, records: List[Dict[str, Any]], roles: Dict[str, List[int]], 
                              question_role: str, context_role: str, throttle_delay: int) -> None:
        """
        Update cleaned records in the Google Sheet.
        
        Args:
            records: List of record dictionaries
            roles: Dictionary mapping role names to column indices
            question_role: Name of question role
            context_role: Name of context role
            throttle_delay: Delay between API calls
        """
        updates = []
        
        for record in records:
            row = record["sheet_row"]
            
            for role in [question_role, context_role]:
                if role in roles:
                    for col_idx in roles[role]:
                        cleaned_key = f"cleaned_{role}_{col_idx}"
                        if cleaned_key in record["roles"]:
                            updates.append({
                                "row": row,
                                "col": col_idx,
                                "value": record["roles"][cleaned_key]
                            })
        
        if updates:
            logger.info(f"Updating {len(updates)} cleaned records")
            self.update_batch(updates)
        else:
            logger.info("No cleaned records to update")

    def parse_records(self, headers: List[str], roles: Dict[str, List[int]], rows: List[List[str]]) -> List[Dict[str, Any]]:
        """
        Parse records from the Google Sheet.
        
        Args:
            headers: List of column headers
            roles: Dictionary mapping role names to column indices
            rows: List of data rows
            
        Returns:
            List of record dictionaries
        """
        logger.info(f"Parsing {len(rows)} records")
        return self.record_processor.parse_records(headers, roles, rows)

    def find_output_columns(self, roles: Dict[str, List[int]], answer_role: str, 
                          compliance_role: str, references_role: Optional[str] = None) -> Dict[str, int]:
        """
        Find output columns in the Google Sheet.
        
        Args:
            roles: Dictionary mapping role names to column indices
            answer_role: Name of answer role
            compliance_role: Name of compliance role
            references_role: Optional name of references role
            
        Returns:
            Dictionary mapping role names to column indices
        """
        logger.info("Finding output columns")
        return self.record_processor.find_output_columns(roles, answer_role, compliance_role, references_role)
