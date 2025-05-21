import os
import logging
from typing import List, Optional, Dict, Any

from config import get_config

logger = logging.getLogger(__name__)

class IndexSelector:
    """
    Utility class for selecting and managing vector indices.
    
    Provides methods for discovering, selecting, and managing vector indices
    for retrieval operations.
    """
    
    @staticmethod
    def get_available_indices(base_index_dir: str) -> Dict[str, str]:
        """
        Get a dictionary of available indices in the specified directory.
        
        Args:
            base_index_dir: Directory containing the indices
            
        Returns:
            Dictionary mapping product names to index paths
        """
        indices = {}
        
        salesforce_index_path = os.path.join(base_index_dir, "salesforce_index")
        if os.path.exists(salesforce_index_path):
            indices["salesforce"] = salesforce_index_path
        
        try:
            for item in os.listdir(base_index_dir):
                item_path = os.path.join(base_index_dir, item)
                
                if os.path.isdir(item_path) and item.endswith('_index'):
                    product_name = item.replace('_index', '').lower()
                    indices[product_name] = item_path
                    
            logger.info(f"Found {len(indices)} indices in {base_index_dir}")
            for product, path in indices.items():
                logger.info(f"  {product}: {path}")
                
            return indices
        except Exception as e:
            logger.error(f"Error scanning index directory: {e}")
            return {"salesforce": salesforce_index_path} if os.path.exists(salesforce_index_path) else {}
    
    @staticmethod
    def select_index_for_products(base_index_dir: str, selected_products: List[str]) -> str:
        """
        Select the most appropriate index for the specified products.
        
        Args:
            base_index_dir: Directory containing the indices
            selected_products: List of selected product names
            
        Returns:
            Path to the selected index
        """
        # Define the default index path
        default_index_path = os.path.join(base_index_dir, "salesforce_index")
        
        # Check if base directory exists
        if not os.path.exists(base_index_dir):
            logger.warning(f"Base index directory does not exist: {base_index_dir}")
            if os.path.exists(default_index_path):
                logger.info(f"Found salesforce_index at {default_index_path}")
                return default_index_path
            return default_index_path
            
        # For multiple products or no selection, use the comprehensive salesforce_index
        if not selected_products or len(selected_products) > 1:
            logger.info(f"Using comprehensive salesforce index for {'multiple' if selected_products else 'no'} products")
            return default_index_path
            
        # For a single product, try to find a product-specific index
        if len(selected_products) == 1:
            # Convert product name to expected directory format (lowercase, underscores)
            product_name = selected_products[0].lower().replace(' ', '_')
            product_index_path = os.path.join(base_index_dir, f"{product_name}_index")
            
            # Check if product-specific index exists
            if os.path.exists(product_index_path):
                logger.info(f"Found product-specific index for {selected_products[0]}: {product_index_path}")
                return product_index_path
            
            # Try without "_cloud" suffix if present
            if "_cloud" in product_name:
                normalized_name = product_name.replace("_cloud", "")
                normalized_path = os.path.join(base_index_dir, f"{normalized_name}_index")
                if os.path.exists(normalized_path):
                    logger.info(f"Found normalized product index for {selected_products[0]}: {normalized_path}")
                    return normalized_path
            
            logger.info(f"No product-specific index found for {selected_products[0]}, using main salesforce index")
            return default_index_path
            
        # Final fallback - should never reach here but just in case
        return default_index_path
    
    @staticmethod
    def print_index_selection_info(base_index_dir: str, selected_products: List[str], selected_index_path: str) -> None:
        """
        Print information about the selected index.
        
        Args:
            base_index_dir: Directory containing the indices
            selected_products: List of selected product names
            selected_index_path: Path to the selected index
        """
        index_name = os.path.basename(selected_index_path)
        product_str = ", ".join(selected_products) if selected_products else "None"
        
        print(f"\n{'='*30} INDEX SELECTION {'='*30}")
        print(f"Selected product(s): {product_str}")
        
        if not selected_products or len(selected_products) > 1:
            print(f"Using comprehensive index: {index_name} (contains all products)")
        else:
            if "_".join(selected_products[0].lower().split()) + "_index" == index_name:
                print(f"Using product-specific index: {index_name}")
                print(f"This index contains targeted information about {selected_products[0]} only")
            else:
                print(f"Using index: {index_name}")
                print(f"Note: No product-specific index found for {selected_products[0]}")
        
        print(f"Index path: {selected_index_path}")
        print(f"{'='*75}")
    
    @staticmethod
    def validate_index(index_path: str) -> bool:
        """
        Validate that an index exists and is properly structured.
        
        Args:
            index_path: Path to the index
            
        Returns:
            True if the index is valid, False otherwise
        """
        if not os.path.exists(index_path):
            logger.warning(f"Index path does not exist: {index_path}")
            return False
            
        # Check for essential files like index.faiss and index.pkl
        required_files = ["index.faiss", "index.pkl"]
        for file in required_files:
            file_path = os.path.join(index_path, file)
            if not os.path.exists(file_path):
                logger.warning(f"Missing required file in index: {file}")
                return False
                
        return True