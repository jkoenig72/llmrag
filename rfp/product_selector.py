import logging
from typing import List, Optional, Dict, Any
from input_utils import InputHandler
from text_processing import TextProcessor

logger = logging.getLogger(__name__)

class ProductSelector:
    """
    Utility class for selecting and managing product information.
    
    Provides methods for interactive product selection and question analysis
    related to products.
    """
    
    @staticmethod
    def select_products(available_products: List[str]) -> List[str]:
        """
        Interactively select products from a list of available products.
        
        Args:
            available_products: List of available product names
            
        Returns:
            List of selected product names
        """
        print("\nAvailable Salesforce Products:")
        for i, product in enumerate(available_products, 1):
            print(f"{i}. {product}")
        
        input_handler = InputHandler()
        while True:
            try:
                choice = input_handler.get_input_with_timeout(
                    f"\nSelect up to 3 products (comma-separated, e.g., 1,5,6): ", 
                    timeout=30, 
                    default="1"
                ).strip()
                
                if not choice:
                    print("Please select at least one product.")
                    continue
                
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                
                if len(indices) != len(set(indices)):
                    print("Error: Duplicate selections. Please select different products.")
                    continue
                
                if len(indices) > 3:
                    print("Error: Maximum 3 products allowed. Please try again.")
                    continue
                
                if any(idx < 0 or idx >= len(available_products) for idx in indices):
                    print(f"Error: Invalid selection. Please choose numbers between 1 and {len(available_products)}.")
                    continue
                
                selected = [available_products[idx] for idx in indices]
                return selected
                
            except ValueError:
                print("Error: Please enter valid numbers separated by commas.")
                continue
    
    @staticmethod
    def count_questions(records: List[Dict[str, Any]], question_role: str) -> int:
        """
        Count the number of questions in a list of records.
        
        Args:
            records: List of record dictionaries
            question_role: Role name for question fields
            
        Returns:
            Number of questions found
        """
        question_count = 0
        for record in records:
            question = TextProcessor.clean_text(record["roles"].get(question_role, ""))
            if question:
                question_count += 1
        return question_count
    
    @staticmethod
    def find_product_mentions(text: str, available_products: List[str]) -> List[str]:
        """
        Find mentions of available products in text.
        
        Args:
            text: Text to search for product mentions
            available_products: List of available product names
            
        Returns:
            List of found product names
        """
        text_lower = text.lower()
        found_products = []
        
        for product in available_products:
            if product.lower() in text_lower:
                found_products.append(product)
        
        return found_products
    
    @staticmethod
    def validate_products(records: List[Dict[str, Any]], product_role: str, 
                        available_products: List[str]) -> Dict[str, List[str]]:
        """
        Validate products mentioned in records against available products.
        
        Args:
            records: List of record dictionaries
            product_role: Role name for product fields
            available_products: List of available product names
            
        Returns:
            Dictionary with valid and invalid products
        """
        valid_products = []
        invalid_products = []
        
        for record in records:
            row_num = record["sheet_row"]
            product = TextProcessor.clean_text(record["roles"].get(product_role, ""))
            
            if not product:
                continue
                
            if any(product.lower() in p.lower() or p.lower() in product.lower() 
                 for p in available_products):
                valid_products.append((row_num, product))
            else:
                invalid_products.append((row_num, product))
        
        return {
            "valid": valid_products,
            "invalid": invalid_products
        }