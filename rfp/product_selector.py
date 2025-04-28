import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

def select_products(available_products: List[str]) -> List[str]:
    """
    Interactive product selection with a limit of 1-3 products using comma-separated input.
    
    Parameters
    ----------
    available_products : List[str]
        List of available product names
        
    Returns
    -------
    List[str]
        List of selected product names
    """
    print("\nAvailable Salesforce Products:")
    for i, product in enumerate(available_products, 1):
        print(f"{i}. {product}")
    
    while True:
        try:
            choice = input(f"\nSelect up to 3 products (comma-separated, e.g., 1,5,6): ").strip()
            if not choice:
                print("Please select at least one product.")
                continue
            
            # Parse comma-separated input
            indices = [int(x.strip()) - 1 for x in choice.split(',')]
            
            # Check for duplicates
            if len(indices) != len(set(indices)):
                print("Error: Duplicate selections. Please select different products.")
                continue
            
            # Check maximum limit
            if len(indices) > 3:
                print("Error: Maximum 3 products allowed. Please try again.")
                continue
            
            # Check valid indices
            if any(idx < 0 or idx >= len(available_products) for idx in indices):
                print(f"Error: Invalid selection. Please choose numbers between 1 and {len(available_products)}.")
                continue
            
            # Convert indices to product names
            selected = [available_products[idx] for idx in indices]
            return selected
            
        except ValueError:
            print("Error: Please enter valid numbers separated by commas.")
            continue

def count_questions(records: List[dict], question_role: str) -> int:
    """
    Count the number of non-empty questions in the records.
    
    Parameters
    ----------
    records : List[dict]
        List of record dictionaries
    question_role : str
        The role key for questions
        
    Returns
    -------
    int
        Count of non-empty questions
    """
    from text_processing import clean_text
    
    question_count = 0
    for record in records:
        question = clean_text(record["roles"].get(question_role, ""))
        if question:
            question_count += 1
    return question_count

def select_starting_row(records: List[dict], question_role: str) -> Optional[int]:
    """
    Let user select which row to start processing from.
    
    Parameters
    ----------
    records : List[dict]
        List of record dictionaries
    question_role : str
        The role key for questions
        
    Returns
    -------
    Optional[int]
        Selected starting row or None if no valid rows
    """
    from text_processing import clean_text
    
    question_count = count_questions(records, question_role)
    
    print(f"\nFound {question_count} questions in the Google Sheet.")
    print("Sheet rows with questions:")
    
    valid_rows = []
    for record in records:
        row_num = record["sheet_row"]
        question = clean_text(record["roles"].get(question_role, ""))
        if question:
            valid_rows.append(row_num)
            # Show first 50 characters of the question
            question_preview = question[:50] + "..." if len(question) > 50 else question
            print(f"  Row {row_num}: {question_preview}")
    
    if not valid_rows:
        logger.error("No questions found in the sheet.")
        return None
    
    while True:
        try:
            choice = input(f"\nEnter the row number to start from (valid rows: {min(valid_rows)}-{max(valid_rows)}, or press Enter to start from the beginning): ").strip()
            
            if not choice:  # Start from beginning
                return min(valid_rows)
            
            start_row = int(choice)
            
            if start_row not in valid_rows:
                print(f"Error: Row {start_row} does not contain a question. Please choose from the valid rows listed above.")
                continue
            
            return start_row
            
        except ValueError:
            print("Error: Please enter a valid row number.")
            continue