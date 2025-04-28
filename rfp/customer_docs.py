import os
import glob
import logging
from typing import List, Dict, Optional
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from config import RFP_DOCUMENTS_DIR, CUSTOMER_INDEX_DIR, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

def scan_rfp_folders() -> List[Dict[str, any]]:
    """
    Scan the RFP documents directory for customer folders and their contents.
    
    Returns
    -------
    List[Dict[str, any]]
        List of dictionaries containing folder information
    """
    folders = []
    
    # Ensure the RFP documents directory exists
    os.makedirs(RFP_DOCUMENTS_DIR, exist_ok=True)
    
    # Scan for subdirectories
    for folder_name in os.listdir(RFP_DOCUMENTS_DIR):
        folder_path = os.path.join(RFP_DOCUMENTS_DIR, folder_name)
        
        if os.path.isdir(folder_path):
            # Count documents
            pdf_count = len(glob.glob(os.path.join(folder_path, "*.pdf")))
            docx_count = len(glob.glob(os.path.join(folder_path, "*.docx")))
            
            # Check if index exists
            index_path = os.path.join(CUSTOMER_INDEX_DIR, f"{folder_name}_index")
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

def load_customer_documents(folder_path: str) -> List:
    """
    Load and process all PDF and DOCX files from a customer folder.
    
    Parameters
    ----------
    folder_path : str
        Path to the customer documents folder
        
    Returns
    -------
    List
        List of processed document chunks
    """
    documents = []
    
    # Load PDFs
    for pdf_file in glob.glob(os.path.join(folder_path, "*.pdf")):
        try:
            loader = PyPDFLoader(pdf_file)
            documents.extend(loader.load())
            logger.info(f"Loaded PDF: {os.path.basename(pdf_file)}")
        except Exception as e:
            logger.error(f"Failed to load PDF {pdf_file}: {e}")
    
    # Load DOCX files
    for docx_file in glob.glob(os.path.join(folder_path, "*.docx")):
        try:
            loader = Docx2txtLoader(docx_file)
            documents.extend(loader.load())
            logger.info(f"Loaded DOCX: {os.path.basename(docx_file)}")
        except Exception as e:
            logger.error(f"Failed to load DOCX {docx_file}: {e}")
    
    # Split documents into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    split_docs = text_splitter.split_documents(documents)
    logger.info(f"Split {len(documents)} documents into {len(split_docs)} chunks")
    
    return split_docs

def create_customer_index(folder_name: str, folder_path: str) -> Optional[FAISS]:
    """
    Create a FAISS index from customer documents and save it.
    
    Parameters
    ----------
    folder_name : str
        Name of the customer folder
    folder_path : str
        Path to the customer documents
        
    Returns
    -------
    Optional[FAISS]
        The created FAISS index or None if creation failed
    """
    try:
        # Ensure the customer index directory exists
        os.makedirs(CUSTOMER_INDEX_DIR, exist_ok=True)
        
        # Load documents
        documents = load_customer_documents(folder_path)
        
        if not documents:
            logger.warning(f"No documents found in {folder_path}")
            return None
        
        # Create embeddings
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        
        # Create FAISS index
        logger.info(f"Creating FAISS index for {folder_name}...")
        index = FAISS.from_documents(documents, embeddings)
        
        # Save index
        index_path = os.path.join(CUSTOMER_INDEX_DIR, f"{folder_name}_index")
        index.save_local(index_path)
        logger.info(f"Saved customer index to {index_path}")
        
        return index
        
    except Exception as e:
        logger.error(f"Failed to create customer index: {e}")
        return None

def load_customer_index(folder_name: str) -> Optional[FAISS]:
    """
    Load an existing customer FAISS index.
    
    Parameters
    ----------
    folder_name : str
        Name of the customer folder
        
    Returns
    -------
    Optional[FAISS]
        The loaded FAISS index or None if loading failed
    """
    try:
        index_path = os.path.join(CUSTOMER_INDEX_DIR, f"{folder_name}_index")
        
        if not os.path.exists(index_path):
            logger.error(f"Customer index not found at {index_path}")
            return None
        
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        index = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
        logger.info(f"Loaded customer index from {index_path}")
        
        return index
        
    except Exception as e:
        logger.error(f"Failed to load customer index: {e}")
        return None

def select_customer_folder() -> Optional[Dict[str, any]]:
    """
    Interactive selection of customer folder.
    
    Returns
    -------
    Optional[Dict[str, any]]
        Selected folder information or None if no selection
    """
    folders = scan_rfp_folders()
    
    if not folders:
        print("\nNo customer folders found in RFP documents directory.")
        print(f"Create folders in: {RFP_DOCUMENTS_DIR}")
        return None
    
    print("\nAvailable Customer Folders:")
    print("0. No customer context (product knowledge only)")
    
    for i, folder in enumerate(folders, 1):
        index_status = "✓ Indexed" if folder["has_index"] else "○ Not indexed"
        print(f"{i}. {folder['name']} - {folder['total_docs']} docs ({folder['pdf_count']} PDF, {folder['docx_count']} DOCX) [{index_status}]")
    
    while True:
        try:
            choice = input(f"\nSelect customer folder (0-{len(folders)}): ").strip()
            
            if not choice:
                print("Please make a selection.")
                continue
            
            idx = int(choice)
            
            if idx == 0:
                return None  # No customer context
            
            if 1 <= idx <= len(folders):
                selected = folders[idx - 1]
                
                # Check if indexing is needed
                if not selected["has_index"] and selected["total_docs"] > 0:
                    response = input(f"\nFolder '{selected['name']}' needs indexing. Create index now? (y/n): ")
                    if response.lower() == 'y':
                        print("Creating index...")
                        index = create_customer_index(selected["name"], selected["path"])
                        if index:
                            selected["has_index"] = True
                            print("Index created successfully!")
                        else:
                            print("Failed to create index. Continue anyway? (y/n): ")
                            if input().lower() != 'y':
                                continue
                
                return selected
            else:
                print(f"Please select a number between 0 and {len(folders)}")
                
        except ValueError:
            print("Please enter a valid number.")
            continue