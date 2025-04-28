import gspread
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Fixed values exactly like your example
SHEET_ID = '10-0PcsDFUvT2WPGaK91UYsA0zxqOwjjrs3J6g39SYD0'
CREDENTIALS_FILE = '/home/fritz/llms-env/credentials.json'
TARGET_CELL = 'B20'

# Fixed text exactly like your example
TEXT = """
This is a test answer for Communications Cloud.

References:
https://help.salesforce.com/s/articleView?id=data.c360_a_create_a_segment.htm&language=en_US&type=5
https://help.salesforce.com/s/articleView?id=data.c360_a_create_a_waterfall_segment.htm&language=en_US&type=5
https://help.salesforce.com/s/articleView?id=data.c360_a_create_a_realtime_segment.htm&language=en_US&type=5
"""

def main():
    try:
        # Step 1: Connect to Google Sheets
        logger.info(f"Connecting to Google Sheet {SHEET_ID} using credentials from {CREDENTIALS_FILE}")
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.sheet1
        
        # Step 2: First format cell as TEXT - exactly like your example
        logger.info(f"Formatting cell {TARGET_CELL} as TEXT")
        ws.format(TARGET_CELL, {"numberFormat": {"type": "TEXT"}})
        
        # Step 3: Update cell with RAW value - exactly like your example
        logger.info(f"Updating cell {TARGET_CELL} with references using RAW mode")
        ws.update(TARGET_CELL, [[TEXT]], value_input_option='RAW')
        
        # Success message - exactly like your example
        print(f"Wrote links to {TARGET_CELL} in sheet {SHEET_ID}.")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        
if __name__ == "__main__":
    main()