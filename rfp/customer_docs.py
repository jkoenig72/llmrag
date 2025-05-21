import os
import glob
import logging
import time
import torch
from typing import List, Dict, Optional, Tuple, Any
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import get_config
from embedding_manager import EmbeddingManager
from input_utils import InputHandler

logger = logging.getLogger(__name__)

class CustomerDocsManager:
    """
    Manager for customer document operations.
    
    This class handles the complete lifecycle of customer document processing:
    1. Scanning RFP folders for documents
    2. Loading and processing PDF/DOCX files
    3. Creating and managing vector indices for document retrieval
    4. Handling document metadata and chunking
    
    Example:
        ```python
        # Initialize the manager
        manager = CustomerDocsManager()
        
        # Scan available RFP folders
        folders = manager.scan_rfp_folders()
        
        # Load documents from a specific folder
        docs, stats = manager.load_customer_documents("/path/to/rfp/folder")
        
        # Create an index for the documents
        index_path = manager.create_customer_index("customer_name", "/path/to/rfp/folder")
        ```
    """
    
    def __init__(self, config=None):
        """
        Initialize the CustomerDocsManager.
        
        Args:
            config: Optional configuration instance. If None, the global config will be used.
                   The config should contain settings for:
                   - rfp_documents_dir: Base directory for RFP documents
                   - customer_index_dir: Directory for storing vector indices
                   - embedding_model: Model to use for document embeddings
        
        Example:
            ```python
            # Using default config
            manager = CustomerDocsManager()
            
            # Using custom config
            from config import ConfigManager
            custom_config = ConfigManager()
            manager = CustomerDocsManager(config=custom_config)
            ```
        """
        self.config = config or get_config()
        self.input_handler = InputHandler()
        logger.info("Initialized CustomerDocsManager")
    
    def scan_rfp_folders(self) -> List[Dict[str, Any]]:
        """
        Scan RFP document folders and collect information about them.
        
        Returns:
            List of dictionaries with folder information containing:
            - name: str - Folder name
            - path: str - Full path to folder
            - pdf_count: int - Number of PDF files
            - docx_count: int - Number of DOCX files
            - total_docs: int - Total number of documents
            - has_index: bool - Whether an index exists
            - index_path: str - Path to the index if it exists
        """
        folders = []
        
        os.makedirs(self.config.rfp_documents_dir, exist_ok=True)
        logger.info(f"Scanning RFP folders in {self.config.rfp_documents_dir}")
        
        for folder_name in os.listdir(self.config.rfp_documents_dir):
            folder_path = os.path.join(self.config.rfp_documents_dir, folder_name)
            
            if os.path.isdir(folder_path):
                pdf_count = len(glob.glob(os.path.join(folder_path, "*.pdf")))
                docx_count = len(glob.glob(os.path.join(folder_path, "*.docx")))
                
                index_path = os.path.join(self.config.customer_index_dir, f"{folder_name}_index")
                has_index = os.path.exists(index_path)
                
                folders.append({
                    "name": folder_name,
                    "path": folder_path,
                    "pdf_count": pdf_count,
                    "docx_count": docx_count,
                    "total_docs": pdf_count + docx_count,
                    "has_index": has_index,
                    "index_path": index_path
                })
                
                logger.info(f"Found folder {folder_name}: {pdf_count} PDFs, {docx_count} DOCXs, index: {has_index}")
        
        return sorted(folders, key=lambda x: x["name"])
    
    def load_customer_documents(self, folder_path: str) -> Tuple[List, Dict[str, int]]:
        """
        Load and process customer documents from a folder.
        
        This method handles:
        1. Scanning for PDF and DOCX files
        2. Loading documents using appropriate loaders
        3. Splitting documents into chunks for processing
        4. Collecting processing statistics
        
        Args:
            folder_path: Path to the folder containing documents
            
        Returns:
            Tuple containing:
            - List of processed document chunks
            - Dictionary with processing statistics:
              {
                  "total_files": int,
                  "pdf_files": int,
                  "docx_files": int,
                  "successful_loads": int,
                  "failed_loads": int,
                  "pages_processed": int,
                  "total_chunks": int
              }
            
        Raises:
            FileNotFoundError: If the folder_path doesn't exist
            PermissionError: If there are permission issues accessing files
            ValueError: If no valid documents are found
            RuntimeError: If there are issues with document processing
        """
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found: {folder_path}")
            
        if not os.access(folder_path, os.R_OK):
            raise PermissionError(f"No permission to read folder: {folder_path}")
            
        documents = []
        stats = {
            "total_files": 0,
            "pdf_files": 0,
            "docx_files": 0,
            "successful_loads": 0,
            "failed_loads": 0,
            "pages_processed": 0,
            "total_chunks": 0
        }
        
        pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
        docx_files = glob.glob(os.path.join(folder_path, "*.docx"))
        
        stats["pdf_files"] = len(pdf_files)
        stats["docx_files"] = len(docx_files)
        stats["total_files"] = stats["pdf_files"] + stats["docx_files"]
        
        logger.info(f"Found {stats['total_files']} documents: {stats['pdf_files']} PDFs, {stats['docx_files']} DOCXs")
        print(f"\nProcessing Customer Documents")
        print(f"Found {stats['total_files']} documents: {stats['pdf_files']} PDF files, {stats['docx_files']} DOCX files")
        
        for i, pdf_file in enumerate(pdf_files):
            try:
                logger.info(f"Processing PDF file {i+1}/{stats['total_files']}: {os.path.basename(pdf_file)}")
                print(f"Processing file {i+1}/{stats['total_files']}: {os.path.basename(pdf_file)} (PDF)")
                loader = PyPDFLoader(pdf_file)
                pdf_docs = loader.load()
                documents.extend(pdf_docs)
                stats["successful_loads"] += 1
                stats["pages_processed"] += len(pdf_docs)
                logger.info(f"Loaded PDF: {os.path.basename(pdf_file)} ({len(pdf_docs)} pages)")
            except Exception as e:
                stats["failed_loads"] += 1
                logger.error(f"Failed to load PDF {pdf_file}: {e}")
                print(f"  ❌ Error loading PDF: {e}")
        
        for i, docx_file in enumerate(docx_files):
            try:
                logger.info(f"Processing DOCX file {i+1+stats['pdf_files']}/{stats['total_files']}: {os.path.basename(docx_file)}")
                print(f"Processing file {i+1+stats['pdf_files']}/{stats['total_files']}: {os.path.basename(docx_file)} (DOCX)")
                loader = Docx2txtLoader(docx_file)
                docx_docs = loader.load()
                documents.extend(docx_docs)
                stats["successful_loads"] += 1
                stats["pages_processed"] += len(docx_docs)
                logger.info(f"Loaded DOCX: {os.path.basename(docx_file)} ({len(docx_docs)} pages)")
            except Exception as e:
                stats["failed_loads"] += 1
                logger.error(f"Failed to load DOCX {docx_file}: {e}")
                print(f"  ❌ Error loading DOCX: {e}")
        
        logger.info("Splitting documents into chunks")
        print("\nSplitting documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        split_docs = text_splitter.split_documents(documents)
        stats["total_chunks"] = len(split_docs)
        
        logger.info(f"Split {len(documents)} document pages into {len(split_docs)} chunks")
        print(f"Split {len(documents)} document pages into {len(split_docs)} chunks")
        
        return split_docs, stats
    
    def _process_documents_for_index(self, folder_path: str) -> Tuple[List, Dict[str, int]]:
        """
        Process documents for index creation.
        
        Args:
            folder_path: Path to the folder containing documents
            
        Returns:
            Tuple of (documents, stats)
            
        Raises:
            FileNotFoundError: If the folder_path doesn't exist
            PermissionError: If there are permission issues accessing files
            ValueError: If no valid documents are found
        """
        documents, stats = self.load_customer_documents(folder_path)
        
        if not documents:
            raise ValueError(f"No valid documents found in {folder_path}")
            
        return documents, stats
        
    def _create_embeddings(self, documents: List, embedding_model: str, use_cpu: bool) -> None:
        """
        Create embeddings for documents.
        
        Args:
            documents: List of documents to create embeddings for
            embedding_model: Name of the embedding model to use
            use_cpu: Whether to use CPU for embeddings
            
        Raises:
            RuntimeError: If there are issues with the embedding model
            torch.cuda.OutOfMemoryError: If GPU memory is insufficient
        """
        logger.info(f"Creating embeddings using {embedding_model}")
        print(f"\n🔢 Creating embeddings using {embedding_model}...")
        
        embedding_manager = EmbeddingManager(embedding_model)
        
        logger.info("Building FAISS vector index")
        print(f"\n🧠 Building FAISS vector index...")
        print(f"Processing {len(documents)} document chunks...")
        
        batch_size = max(1, len(documents) // 10)
        
        for i in range(0, len(documents), batch_size):
            current_progress = min(i + batch_size, len(documents))
            logger.info(f"Progress: {current_progress}/{len(documents)} chunks ({(current_progress/len(documents))*100:.1f}%)")
            print(f"Progress: {current_progress}/{len(documents)} chunks ({(current_progress/len(documents))*100:.1f}%)")
            
        return embedding_manager
        
    def _save_index_metadata(self, index_path: str, use_cpu: bool, stats: Dict[str, int], 
                           processing_time: float, embedding_model: str) -> None:
        """
        Save index metadata and summary.
        
        Args:
            index_path: Path where the index is saved
            use_cpu: Whether CPU was used for indexing
            stats: Processing statistics
            processing_time: Time taken for processing
            embedding_model: Name of the embedding model used
        """
        if use_cpu:
            flag_file = os.path.join(index_path, "_created_with_cpu")
            with open(flag_file, 'w') as f:
                f.write("This index was created with CPU and should be loaded with CPU.")
            logger.info(f"Created CPU flag file: {flag_file}")
            print(f"📝 Created CPU flag file: {flag_file}")
            
        logger.info(f"Successfully created customer index at {index_path}")
        print("\n" + "="*80)
        print(f"INDEX CREATION SUMMARY: {os.path.basename(index_path)}")
        print("="*80)
        print(f"✅ Successfully created customer index")
        print(f"📊 Index Statistics:")
        print(f"  • Documents processed: {stats['successful_loads']}/{stats['total_files']} ({stats['pdf_files']} PDFs, {stats['docx_files']} DOCXs)")
        print(f"  • Pages processed: {stats['pages_processed']}")
        print(f"  • Total chunks in vector database: {stats['total_chunks']}")
        print(f"  • Embedding model: {embedding_model}")
        print(f"  • Using {'CPU' if use_cpu else 'GPU'} for embeddings")
        print(f"  • Processing time: {processing_time:.2f} seconds")
        print(f"  • Index saved to: {index_path}")
        print("="*80)
        
    def create_customer_index(self, folder_name: str, folder_path: str, use_cpu=False) -> Optional[str]:
        """
        Create a vector index for customer documents.
        
        This method performs the following steps:
        1. Loads and processes all documents in the folder
        2. Creates embeddings for each document chunk
        3. Builds a FAISS vector index for efficient retrieval
        4. Saves the index to disk with metadata
        
        Args:
            folder_name: Name of the folder (used for index naming)
            folder_path: Path to the folder containing documents
            use_cpu: Whether to use CPU instead of GPU for indexing.
                    Use this if GPU memory is limited or unavailable.
            
        Returns:
            Path to the created index or None if creation failed
            
        Raises:
            FileNotFoundError: If the folder_path doesn't exist
            PermissionError: If there are permission issues accessing files
            ValueError: If no valid documents are found
            RuntimeError: If there are issues with the embedding model
            OSError: If there are file system issues
            torch.cuda.OutOfMemoryError: If GPU memory is insufficient
        """
        try:
            if not os.path.exists(folder_path):
                raise FileNotFoundError(f"Folder not found: {folder_path}")
                
            if not os.access(folder_path, os.R_OK):
                raise PermissionError(f"No permission to read folder: {folder_path}")
            
            logger.info(f"Creating customer index for {folder_name}")
            print("\n" + "="*80)
            print(f"CREATING CUSTOMER INDEX: {folder_name}")
            print("="*80 + "\n")
            
            start_time = time.time()
            
            os.makedirs(self.config.customer_index_dir, exist_ok=True)
            index_path = os.path.join(self.config.customer_index_dir, f"{folder_name}_index")
            
            # Process documents
            documents, stats = self._process_documents_for_index(folder_path)
            
            # Create embeddings
            embedding_manager = self._create_embeddings(documents, self.config.embedding_model, use_cpu)
            
            # Create and save index
            result_path = embedding_manager.create_index(documents, index_path, use_cpu=use_cpu, db_name="Customer DB")
            
            if not result_path:
                raise RuntimeError("Failed to create index")
                
            # Save metadata and summary
            end_time = time.time()
            processing_time = end_time - start_time
            self._save_index_metadata(index_path, use_cpu, stats, processing_time, self.config.embedding_model)
            
            return index_path
            
        except Exception as e:
            logger.error(f"Failed to create customer index: {e}")
            print(f"\n❌ Error creating index: {e}")
            return None
    
    def load_customer_index(self, folder_name: str) -> Optional[str]:
        """
        Load a customer index.
        
        Args:
            folder_name: Name of the folder
            
        Returns:
            Path to the loaded index or None if loading failed
            
        Raises:
            FileNotFoundError: If the index directory doesn't exist
            PermissionError: If there are permission issues accessing the index
            RuntimeError: If there are issues with the index format
        """
        try:
            index_path = os.path.join(self.config.customer_index_dir, f"{folder_name}_index")
            
            if not os.path.exists(index_path):
                raise FileNotFoundError(f"Customer index not found at {index_path}")
                
            if not os.access(index_path, os.R_OK):
                raise PermissionError(f"No permission to read index at {index_path}")
            
            logger.info(f"Verifying customer index for {folder_name}")
            print(f"\n🔍 Verifying customer index for {folder_name}...")
            
            cpu_flag_file = os.path.join(index_path, "_created_with_cpu")
            use_cpu = os.path.exists(cpu_flag_file)
            
            if use_cpu:
                logger.info("Found CPU flag file, will use CPU for querying")
                print(f"📝 Found CPU flag file. CPU will be used when querying this index.")
            
            if os.path.exists(index_path):
                logger.info(f"Verified customer index at {index_path}")
                print(f"✅ Successfully verified index at {index_path}")
                return index_path
            else:
                logger.error(f"Failed to verify index at {index_path}")
                print(f"❌ Error: Index not found at {index_path}")
                return None
                    
        except Exception as e:
            logger.error(f"Error loading customer index: {e}")
            print(f"❌ Error loading index: {e}")
            return None
    
    @staticmethod
    def select_customer_folder() -> Optional[Dict[str, Any]]:
        """
        Select a customer folder interactively.
        
        Returns:
            Selected folder information dictionary containing:
            - name: str - Folder name
            - path: str - Full path to folder
            - has_index: bool - Whether an index exists
            - index_path: str - Path to the index if it exists
            Returns None if selection was cancelled
        """
        manager = CustomerDocsManager()
        return manager._select_customer_folder()
    
    def _select_customer_folder(self, is_translation_subprocess: bool = False, preselected_customer_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Select a customer folder.
        
        Args:
            is_translation_subprocess: Whether this is part of a translation workflow
            preselected_customer_path: Optional pre-selected customer path
            
        Returns:
            Selected folder information dictionary containing:
            - name: str - Folder name
            - path: str - Full path to folder
            - has_index: bool - Whether an index exists
            - index_path: str - Path to the index if it exists
            Returns None if selection was cancelled or an error occurred
        """
        try:
            if preselected_customer_path:
                logger.info(f"Using pre-selected customer path: {preselected_customer_path}")
                return {
                    "name": os.path.basename(preselected_customer_path),
                    "path": preselected_customer_path,
                    "has_index": True,
                    "index_path": os.path.join(self.config.customer_index_dir, f"{os.path.basename(preselected_customer_path)}_index")
                }
            
            folders = self.scan_rfp_folders()
            
            if not folders:
                logger.warning("No customer folders found")
                print("\n❌ No customer folders found. Please add some documents first.")
                return None
            
            logger.info(f"Found {len(folders)} customer folders")
            print("\nAvailable Customer Folders:")
            
            for i, folder in enumerate(folders, 1):
                index_status = "✅" if folder["has_index"] else "❌"
                print(f"{i}. {index_status} {folder['name']} ({folder['total_docs']} documents)")
            
            while True:
                try:
                    choice = self.input_handler.get_input_with_timeout(
                        "\nSelect a customer folder (number) or 'n' for none: ",
                        timeout=self.config.default_timeout,
                        default="n"
                    )
                    
                    if choice.lower() == 'n':
                        logger.info("User selected no customer folder")
                        return None
                    
                    idx = int(choice) - 1
                    if 0 <= idx < len(folders):
                        selected = folders[idx]
                        logger.info(f"Selected customer folder: {selected['name']}")
                        return selected
                    else:
                        logger.warning(f"Invalid folder selection: {choice}")
                        print("❌ Invalid selection. Please try again.")
                except ValueError:
                    logger.warning(f"Invalid input: {choice}")
                    print("❌ Please enter a valid number or 'n' for none.")
            
        except Exception as e:
            logger.error(f"Error selecting customer folder: {e}")
            print(f"❌ Error selecting customer folder: {e}")
            return None