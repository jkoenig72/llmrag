import os
import glob
import logging
import time
import torch
from typing import List, Dict, Optional, Tuple
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import get_config
from embedding_manager import EmbeddingManager
from input_utils import InputHandler

logger = logging.getLogger(__name__)

class CustomerDocsManager:
    """
    Manager for customer document operations.
    
    Provides methods for scanning, loading, processing, and indexing
    customer documents for RFP processing.
    """
    
    def __init__(self, config=None):
        """
        Initialize the CustomerDocsManager.
        
        Args:
            config: Optional configuration instance. If None, the global config will be used.
        """
        self.config = config or get_config()
        self.input_handler = InputHandler()
    
    def scan_rfp_folders(self) -> List[Dict[str, any]]:
        """
        Scan RFP document folders and collect information about them.
        
        Returns:
            List of dictionaries with folder information
        """
        folders = []
        
        os.makedirs(self.config.rfp_documents_dir, exist_ok=True)
        
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
        
        return sorted(folders, key=lambda x: x["name"])
    
    def load_customer_documents(self, folder_path: str) -> Tuple[List, Dict[str, int]]:
        """
        Load customer documents from a folder.
        
        Args:
            folder_path: Path to the folder containing documents
            
        Returns:
            Tuple of (list of documents, statistics dictionary)
        """
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
        
        print(f"\nProcessing Customer Documents")
        print(f"Found {stats['total_files']} documents: {stats['pdf_files']} PDF files, {stats['docx_files']} DOCX files")
        
        for i, pdf_file in enumerate(pdf_files):
            try:
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
        
        print("\nSplitting documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        split_docs = text_splitter.split_documents(documents)
        stats["total_chunks"] = len(split_docs)
        
        print(f"Split {len(documents)} document pages into {len(split_docs)} chunks")
        
        return split_docs, stats
    
    def create_customer_index(self, folder_name: str, folder_path: str, use_cpu=False) -> Optional[str]:
        """
        Create a customer index for a folder.
        
        Args:
            folder_name: Name of the folder
            folder_path: Path to the folder
            use_cpu: Whether to use CPU instead of GPU for indexing
            
        Returns:
            Path to the created index or None if creation failed
        """
        try:
            print("\n" + "="*80)
            print(f"CREATING CUSTOMER INDEX: {folder_name}")
            print("="*80 + "\n")
            
            start_time = time.time()
            
            os.makedirs(self.config.customer_index_dir, exist_ok=True)
            
            index_path = os.path.join(self.config.customer_index_dir, f"{folder_name}_index")
            flag_file = os.path.join(index_path, "_created_with_cpu") if use_cpu else None
            
            print("\n📂 Loading and processing documents...")
            documents, stats = self.load_customer_documents(folder_path)
            
            if not documents:
                print(f"\n❌ No valid documents found in {folder_path}")
                return None
            
            print(f"\n🔢 Creating embeddings using {self.config.embedding_model}...")
            embedding_manager = EmbeddingManager(self.config.embedding_model)
            
            print(f"\n🧠 Building FAISS vector index...")
            print(f"Processing {len(documents)} document chunks...")
            
            batch_size = max(1, len(documents) // 10)
            
            for i in range(0, len(documents), batch_size):
                current_progress = min(i + batch_size, len(documents))
                print(f"Progress: {current_progress}/{len(documents)} chunks ({(current_progress/len(documents))*100:.1f}%)")
            
            result_path = embedding_manager.create_index(documents, index_path, use_cpu=use_cpu, db_name="Customer DB")
            
            if flag_file and use_cpu and result_path:
                with open(flag_file, 'w') as f:
                    f.write("This index was created with CPU and should be loaded with CPU.")
                print(f"📝 Created CPU flag file: {flag_file}")
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            print("\n" + "="*80)
            print(f"INDEX CREATION SUMMARY: {folder_name}")
            print("="*80)
            print(f"✅ Successfully created customer index")
            print(f"📊 Index Statistics:")
            print(f"  • Documents processed: {stats['successful_loads']}/{stats['total_files']} ({stats['pdf_files']} PDFs, {stats['docx_files']} DOCXs)")
            print(f"  • Pages processed: {stats['pages_processed']}")
            print(f"  • Total chunks in vector database: {stats['total_chunks']}")
            print(f"  • Embedding model: {self.config.embedding_model}")
            print(f"  • Using {'CPU' if use_cpu else 'GPU'} for embeddings")
            print(f"  • Processing time: {processing_time:.2f} seconds")
            print(f"  • Index saved to: {index_path}")
            print("="*80)
            
            logger.info(f"Saved customer index to {index_path}")
            
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
        """
        try:
            index_path = os.path.join(self.config.customer_index_dir, f"{folder_name}_index")
            
            if not os.path.exists(index_path):
                logger.error(f"Customer index not found at {index_path}")
                return None
            
            print(f"\n🔍 Verifying customer index for {folder_name}...")
            
            cpu_flag_file = os.path.join(index_path, "_created_with_cpu")
            use_cpu = os.path.exists(cpu_flag_file)
            
            if use_cpu:
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
            logger.error(f"Failed to verify customer index: {e}")
            print(f"❌ Error verifying index: {e}")
            return None
    
    @staticmethod
    def select_customer_folder() -> Optional[Dict[str, any]]:
        """
        Select a customer folder for processing.
        
        Returns:
            Dictionary with selected folder information or None if none selected
        """
        config = get_config()
        customer_docs_manager = CustomerDocsManager(config)
        return customer_docs_manager._select_customer_folder()
        
    def _select_customer_folder(self, is_translation_subprocess: bool = False, preselected_customer_path: Optional[str] = None) -> Optional[Dict[str, any]]:
        """
        Implementation of select_customer_folder that uses instance variables.
        
        Args:
            is_translation_subprocess: Whether this is being called as part of a translation subprocess
            preselected_customer_path: Path to a preselected customer index to use
            
        Returns:
            Dictionary with selected folder information or None if none selected
        """
        # Check if we're in a translation workflow and should skip customer selection
        from main import _GLOBAL_TRANSLATION_IN_PROGRESS
        if '_GLOBAL_TRANSLATION_IN_PROGRESS' in globals() and _GLOBAL_TRANSLATION_IN_PROGRESS:
            # Only show customer selection if this is specifically called from the translation handler
            if not is_translation_subprocess:
                logger.info("Skipping customer folder selection in main workflow due to translation mode")
                print("Skipping customer folder selection in main workflow (will handle in translation process)")
                return None
            # Otherwise continue to perform selection in the translation subprocess
            logger.info("Proceeding with customer selection in translation subprocess")
        
        skip_customer_selection = self.config.rfp_skip_customer_selection
        
        # If no explicit preselected path is provided, check the config
        if preselected_customer_path is None:
            preselected_customer_path = self.config.rfp_customer_index_path
        
        # Translation workflow subprocess handling - this is critical
        if is_translation_subprocess and skip_customer_selection:
            if preselected_customer_path and os.path.exists(preselected_customer_path):
                # Extract folder name from the index path
                folder_name = os.path.basename(preselected_customer_path).replace("_index", "")
                
                logger.info(f"Using pre-selected customer context from translation workflow: {preselected_customer_path}")
                print(f"👥 Using pre-selected customer context from translation workflow: {folder_name}")
                
                return {
                    "name": folder_name,
                    "path": os.path.join(self.config.rfp_documents_dir, folder_name),
                    "has_index": True,
                    "index_path": preselected_customer_path
                }
            else:
                logger.info("No customer context specified in translation workflow. Using product knowledge only.")
                print(f"🔍 Using product knowledge only for answering (no customer context)")
                return None
        
        # Handle direct preselection (non-translation workflow)
        if skip_customer_selection and preselected_customer_path:
            logger.info(f"Skipping customer folder selection, using pre-selected path: {preselected_customer_path}")
            
            # Extract folder name from the index path
            folder_name = os.path.basename(preselected_customer_path).replace("_index", "")
            
            # Check if the index path actually exists
            if os.path.exists(preselected_customer_path):
                return {
                    "name": folder_name,
                    "path": os.path.join(self.config.rfp_documents_dir, folder_name),
                    "has_index": True,
                    "index_path": preselected_customer_path
                }
            else:
                logger.warning(f"Pre-selected customer index path does not exist: {preselected_customer_path}")
                print(f"⚠️ Warning: Pre-selected customer index path not found: {preselected_customer_path}")
                # Continue to normal selection
        
        folders = self.scan_rfp_folders()
        
        if not folders:
            print("\nNo customer folders found in RFP documents directory.")
            print(f"Create folders in: {self.config.rfp_documents_dir}")
            return None
        
        print("\nAvailable Customer Folders:")
        print("0. No customer context (product knowledge only)")
        
        for i, folder in enumerate(folders, 1):
            index_status = "✓ Indexed" if folder["has_index"] else "○ Not indexed"
            print(f"{i}. {folder['name']} - {folder['total_docs']} docs ({folder['pdf_count']} PDF, {folder['docx_count']} DOCX) [{index_status}]")
        
        choice = self.input_handler.get_input_with_timeout(f"\nSelect customer folder (0-{len(folders)})", timeout=self.config.default_timeout, default="0")
        
        try:
            idx = int(choice)
            
            if idx == 0:
                print("\n🔍 Using product knowledge only (no customer context)")
                return None
            
            if 1 <= idx <= len(folders):
                selected = folders[idx - 1]
                
                if not selected["has_index"] and selected["total_docs"] > 0:
                    print(f"\nFolder '{selected['name']}' needs indexing. Creating index automatically...")
                    
                    # Auto-detect if we should use CPU based on available GPU memory
                    use_cpu = False
                    if torch.cuda.is_available():
                        try:
                            # Check available GPU memory - if low, use CPU instead
                            free_memory = torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated()
                            free_memory_gb = free_memory / (1024**3)
                            
                            # If less than 4GB free, use CPU
                            if free_memory_gb < 4:
                                print(f"Low GPU memory detected ({free_memory_gb:.2f} GB free). Using CPU for indexing.")
                                use_cpu = True
                            else:
                                print(f"Sufficient GPU memory detected ({free_memory_gb:.2f} GB free). Using GPU for indexing.")
                        except Exception as e:
                            logger.warning(f"Error checking GPU memory: {e}. Defaulting to GPU if available.")
                    else:
                        print("No GPU detected. Using CPU for indexing.")
                        use_cpu = True
                    
                    index_path = self.create_customer_index(selected["name"], selected["path"], use_cpu=use_cpu)
                    if index_path:
                        selected["has_index"] = True
                        selected["index_path"] = index_path
                    else:
                        print("Failed to create index, but continuing with selection.")
                
                elif not selected["total_docs"]:
                    print(f"\n⚠️ Warning: Folder '{selected['name']}' has no documents! Continuing anyway.")
                
                print(f"\n✅ Selected customer: {selected['name']}")
                return selected
            else:
                print(f"Please select a number between 0 and {len(folders)}")
                return self._select_customer_folder(is_translation_subprocess, preselected_customer_path)
                    
        except ValueError:
            print("Please enter a valid number.")
            return self._select_customer_folder(is_translation_subprocess, preselected_customer_path)