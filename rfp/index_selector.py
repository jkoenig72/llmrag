import os
import logging
import time
import faiss
import pickle
from typing import List, Optional, Dict, Any, Tuple
from collections import Counter
from tabulate import tabulate
from datetime import datetime

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
        
        logger.info(f"Selected product(s): {product_str}")
        logger.info(f"Using index: {index_name}")
        logger.info(f"Index path: {selected_index_path}")
        
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
        
    @staticmethod
    def scan_indices_with_product_distribution() -> List[Dict[str, Any]]:
        """
        Scan available indices and analyze product distribution in each.
        
        Returns:
            List of dictionaries with index information including product distribution
        """
        config = get_config()
        index_dir = config.index_dir
        available_indices = []
        
        if not os.path.exists(index_dir):
            logger.error(f"Index directory does not exist: {index_dir}")
            print(f"❌ Index directory does not exist: {index_dir}")
            return []
        
        logger.info(f"Scanning FAISS indices in {index_dir}")
        print("\n" + "="*80)
        print("SCANNING AVAILABLE VECTOR DATABASES")
        print("="*80)
        
        # Find all directories in the base directory that contain FAISS indices
        for item in os.listdir(index_dir):
            item_path = os.path.join(index_dir, item)
            if os.path.isdir(item_path) and item.endswith('_index'):
                try:
                    logger.info(f"Analyzing index: {item}")
                    
                    # Basic index metadata
                    index_info = IndexSelector._get_index_metadata(item_path)
                    if not index_info:
                        continue
                    
                    # Product distribution analysis
                    product_distribution = IndexSelector._analyze_product_vectors(item_path)
                    index_info['product_distribution'] = product_distribution
                    
                    # Display only the product distribution table
                    print(f"\n{index_info['name'].upper()}")
                    print("=" * len(index_info['name'].upper()))
                    
                    # Product distribution table
                    print("┌" + "─" * 55 + "┐")
                    print("│ Product".ljust(45) + "│ Vectors".ljust(10) + "│")
                    print("├" + "─" * 45 + "┼" + "─" * 9 + "┤")
                    
                    if product_distribution:
                        # Sort products by vector count (descending)
                        sorted_products = sorted(product_distribution.items(), key=lambda x: -x[1])
                        for product, count in sorted_products:
                            # Convert product name back to proper case and format
                            display_name = product.replace('_', ' ').title()
                            print(f"│ {display_name[:43].ljust(43)} │ {str(count).rjust(8)} │")
                    else:
                        print("│ No product data available".ljust(55) + "│")
                    
                    print("└" + "─" * 45 + "┴" + "─" * 9 + "┘")
                    
                    available_indices.append(index_info)
                    logger.info(f"Successfully analyzed: {item}")
                except Exception as e:
                    logger.error(f"Error analyzing index {item}: {e}")
                    print(f"❌ Error analyzing index {item}: {e}")
        
        # Sort indices by name
        available_indices.sort(key=lambda x: x["name"])
        
        return available_indices
    
    @staticmethod
    def _get_index_metadata(index_path: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata about a FAISS index.
        
        Args:
            index_path: Path to the FAISS index
            
        Returns:
            Dictionary containing index metadata or None if invalid
        """
        try:
            # Check if index directory exists
            if not os.path.exists(index_path):
                logger.warning(f"Index directory does not exist: {index_path}")
                return None
                
            # Get basic index information
            index_name = os.path.basename(index_path)
            faiss_path = os.path.join(index_path, "index.faiss")
            pkl_path = os.path.join(index_path, "index.pkl")
            
            # Check if required files exist
            if not os.path.exists(faiss_path) or not os.path.exists(pkl_path):
                logger.warning(f"Missing required files in {index_path}")
                return None
                
            # Get file size
            size_bytes = os.path.getsize(faiss_path)
            size_mb = size_bytes / (1024 * 1024)
            
            # Get last modified time
            last_modified = os.path.getmtime(faiss_path)
            last_modified = datetime.fromtimestamp(last_modified)
            
            # Try to load the index to get vector count
            try:
                index = faiss.read_index(faiss_path)
                vector_count = index.ntotal
                cpu_only = not hasattr(index, 'getDevice')
            except Exception as e:
                logger.warning(f"Could not read FAISS index: {e}")
                vector_count = 0
                cpu_only = True
                
            # Get product distribution
            product_distribution = IndexSelector._analyze_product_vectors(index_path)
            
            return {
                'name': index_name,
                'path': index_path,
                'vector_count': vector_count,
                'size_mb': size_mb,
                'last_modified': last_modified,
                'cpu_only': cpu_only,
                'product_distribution': product_distribution
            }
            
        except Exception as e:
            logger.error(f"Error getting index metadata: {e}")
            return None
    
    @staticmethod
    def _analyze_product_vectors(index_path: str) -> dict:
        """
        Analyze the product distribution in a FAISS index using robust logic from RAG's get_index_info.
        Args:
            index_path: Path to the FAISS index
        Returns:
            Dictionary mapping product names to vector counts
        """
        import pickle
        import faiss
        import os
        products = {}
        index_pkl = os.path.join(index_path, "index.pkl")
        index_faiss = os.path.join(index_path, "index.faiss")
        if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
            return {}
        try:
            with open(index_pkl, 'rb') as f:
                metadata = pickle.load(f)
            # Try multiple approaches to extract product information
            # Approach 1: Direct access to docstore dictionary (newer format)
            if hasattr(metadata, 'get') and metadata.get('docstore'):
                docstore_dict = metadata.get('docstore', {}).get('_dict', {})
                for doc_id, doc_metadata in docstore_dict.items():
                    if hasattr(doc_metadata, 'metadata'):
                        # Check for 'product' field
                        if 'product' in doc_metadata.metadata:
                            product = doc_metadata.metadata.get('product', '')
                            if product:
                                product = product.lower().replace(' ', '_')
                                products[product] = products.get(product, 0) + 1
                        # Check for 'tag' field
                        elif 'tag' in doc_metadata.metadata:
                            product = doc_metadata.metadata.get('tag', '')
                            if product:
                                product = product.lower().replace(' ', '_')
                                products[product] = products.get(product, 0) + 1
            # Approach 2: Handle tuple format (older or modified format)
            elif isinstance(metadata, tuple):
                for i, element in enumerate(metadata):
                    if isinstance(element, dict) and 'docstore' in element:
                        docstore = element['docstore']
                        if hasattr(docstore, '_dict'):
                            for doc_id, doc_metadata in docstore._dict.items():
                                if hasattr(doc_metadata, 'metadata'):
                                    # Check for 'product' field
                                    if 'product' in doc_metadata.metadata:
                                        product = doc_metadata.metadata.get('product', '')
                                        if product:
                                            product = product.lower().replace(' ', '_')
                                            products[product] = products.get(product, 0) + 1
                                    # Check for 'tag' field
                                    elif 'tag' in doc_metadata.metadata:
                                        product = doc_metadata.metadata.get('tag', '')
                                        if product:
                                            product = product.lower().replace(' ', '_')
                                            products[product] = products.get(product, 0) + 1
                    elif hasattr(element, '_dict'):
                        for doc_id, doc_metadata in element._dict.items():
                            if hasattr(doc_metadata, 'metadata'):
                                # Check for 'product' field
                                if 'product' in doc_metadata.metadata:
                                    product = doc_metadata.metadata.get('product', '')
                                    if product:
                                        product = product.lower().replace(' ', '_')
                                        products[product] = products.get(product, 0) + 1
                                # Check for 'tag' field
                                elif 'tag' in doc_metadata.metadata:
                                    product = doc_metadata.metadata.get('tag', '')
                                    if product:
                                        product = product.lower().replace(' ', '_')
                                        products[product] = products.get(product, 0) + 1
            return products
        except Exception as e:
            import logging
            logging.warning(f"Could not extract product distribution: {e}")
            return {}
    
    @staticmethod
    def display_index_information(indices: List[Dict[str, Any]]) -> None:
        """
        Display information about available indices in a formatted table.
        
        Args:
            indices: List of index information dictionaries
        """
        if not indices:
            print("No indices found.")
            return
            
        print("\n" + "="*100)
        print("DETAILED INDEX INFORMATION")
        print("="*100)
        
        # Sort indices to show salesforce_index first
        sorted_indices = sorted(indices, key=lambda x: x['name'] != 'salesforce_index')
        
        for idx in sorted_indices:
            print(f"\n{idx['name'].upper()}")
            print("=" * len(idx['name'].upper()))
            
            # Basic index information
            print(f"\nLocation: {idx['path']}")
            print(f"Total Vectors: {idx.get('vector_count', 0):,}")
            print(f"Size: {idx.get('size_mb', 0):.2f} MB")
            print(f"Last Modified: {idx.get('last_modified', '').strftime('%Y-%m-%d %H:%M')}")
            print(f"CPU Only: {'Yes' if idx.get('cpu_only', False) else 'No'}")
            
            # Product distribution
            print("\nProduct Distribution Analysis:")
            print("-" * 80)
            
            analysis = idx.get('product_distribution', {})
            if analysis and 'product_counts' in analysis:
                # Sort products by vector count
                sorted_products = sorted(
                    analysis['product_counts'].items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                
                # Print header
                print(f"{'Product':<25} {'Vectors':>10} {'% of Total':>10} {'% of Docs':>10}")
                print("-" * 80)
                
                # Print each product's statistics
                total_vectors = analysis['total_vectors']
                total_docs = analysis['metadata_stats']['total_documents']
                
                for product, count in sorted_products:
                    vector_percentage = (count / total_vectors * 100) if total_vectors > 0 else 0
                    doc_percentage = (count / total_docs * 100) if total_docs > 0 else 0
                    print(f"{product:<25} {count:>10,} {vector_percentage:>9.1f}% {doc_percentage:>9.1f}%")
                
                # Print summary statistics
                print("\nSummary Statistics:")
                print(f"Total Documents: {analysis['metadata_stats']['total_documents']:,}")
                print(f"Documents with Product Info: {analysis['metadata_stats']['documents_with_product']:,}")
                print(f"Unique Products: {len(analysis['metadata_stats']['unique_products'])}")
                print(f"Products: {', '.join(sorted(analysis['metadata_stats']['unique_products']))}")
            else:
                print("No product distribution information available")
            
            print("\n" + "="*100)
    
    @staticmethod
    def get_user_index_selection(indices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Get user selection of an index from the available indices.
        
        Args:
            indices: List of index information dictionaries
            
        Returns:
            Selected index information dictionary or None if selection failed
        """
        if not indices:
            logger.error("No indices available for selection")
            return None
            
        print("\nPlease select an index to use:")
        for i, idx in enumerate(indices, 1):
            print(f"{i}. {idx['name']} ({idx['vector_count']} vectors, {idx['size_mb']} MB)")
            
        while True:
            try:
                choice = input("\nEnter the number of your choice: ").strip()
                if not choice:
                    logger.warning("No selection made")
                    return None
                    
                index_num = int(choice)
                if 1 <= index_num <= len(indices):
                    selected = indices[index_num - 1]
                    logger.info(f"User selected index: {selected['name']}")
                    return selected
                else:
                    print(f"Please enter a number between 1 and {len(indices)}")
            except ValueError:
                print("Please enter a valid number")
            except Exception as e:
                logger.error(f"Error during index selection: {e}")
                return None
    
    @staticmethod
    def extract_available_products(index: Dict[str, Any]) -> List[str]:
        """
        Extract list of available products from an index.
        
        Args:
            index: Index information dictionary
            
        Returns:
            List of product names
        """
        if not index or 'product_distribution' not in index:
            logger.warning("No product distribution information in index")
            return []
            
        # Get raw product names
        raw_products = list(index['product_distribution'].keys())
        
        # Format product names properly
        formatted_products = []
        for product in raw_products:
            # Convert from snake_case to Title Case with spaces
            formatted = product.replace('_', ' ').title()
            formatted_products.append(formatted)
        
        logger.info(f"Extracted {len(formatted_products)} products from index {index['name']}")
        return formatted_products