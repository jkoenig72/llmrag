import os
import glob
import logging
import time
from typing import List, Dict, Optional, Tuple
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

def load_customer_documents(folder_path: str) -> Tuple[List, Dict[str, int]]:
    """
    Load and process all PDF and DOCX files from a customer folder.
    
    Parameters
    ----------
    folder_path : str
        Path to the customer documents folder
        
    Returns
    -------
    Tuple[List, Dict[str, int]]
        A tuple containing:
        - List of processed document chunks
        - Stats dictionary with processing information
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
    
    # Identify all documents
    pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
    docx_files = glob.glob(os.path.join(folder_path, "*.docx"))
    
    stats["pdf_files"] = len(pdf_files)
    stats["docx_files"] = len(docx_files)
    stats["total_files"] = stats["pdf_files"] + stats["docx_files"]
    
    print(f"\nProcessing Customer Documents")
    print(f"Found {stats['total_files']} documents: {stats['pdf_files']} PDF files, {stats['docx_files']} DOCX files")
    
    # Process PDFs
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
    
    # Process DOCX files
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
    
    # Split documents into chunks
    print("\nSplitting documents into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    split_docs = text_splitter.split_documents(documents)
    stats["total_chunks"] = len(split_docs)
    
    print(f"Split {len(documents)} document pages into {len(split_docs)} chunks")
    
    return split_docs, stats

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
        print("\n" + "="*80)
        print(f"CREATING CUSTOMER INDEX: {folder_name}")
        print("="*80)
        
        start_time = time.time()
        
        # Ensure the customer index directory exists
        os.makedirs(CUSTOMER_INDEX_DIR, exist_ok=True)
        
        # Load documents
        print("\n📂 Loading and processing documents...")
        documents, stats = load_customer_documents(folder_path)
        
        if not documents:
            print(f"\n❌ No valid documents found in {folder_path}")
            return None
        
        # Create embeddings
        print(f"\n🔢 Creating embeddings using {EMBEDDING_MODEL}...")
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        
        # Create FAISS index with progress indication
        print(f"\n🧠 Building FAISS vector index...")
        print(f"Processing {len(documents)} document chunks...")
        
        # Create batches to show progress
        batch_size = max(1, len(documents) // 10)  # Show 10 progress updates
        
        # Process in batches just for progress display
        all_docs = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]
            current_progress = min(i + batch_size, len(documents))
            print(f"Progress: {current_progress}/{len(documents)} chunks ({(current_progress/len(documents))*100:.1f}%)")
            all_docs.extend(batch)
        
        # Create index from all documents
        index = FAISS.from_documents(documents, embeddings)
        
        # Save index
        index_path = os.path.join(CUSTOMER_INDEX_DIR, f"{folder_name}_index")
        print(f"\n💾 Saving index to {index_path}...")
        index.save_local(index_path)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Final summary
        print("\n" + "="*80)
        print(f"INDEX CREATION SUMMARY: {folder_name}")
        print("="*80)
        print(f"✅ Successfully created customer index")
        print(f"📊 Index Statistics:")
        print(f"  • Documents processed: {stats['successful_loads']}/{stats['total_files']} ({stats['pdf_files']} PDFs, {stats['docx_files']} DOCXs)")
        print(f"  • Pages processed: {stats['pages_processed']}")
        print(f"  • Total chunks in vector database: {stats['total_chunks']}")
        print(f"  • Embedding model: {EMBEDDING_MODEL}")
        print(f"  • Processing time: {processing_time:.2f} seconds")
        print(f"  • Index saved to: {index_path}")
        print("="*80)
        
        logger.info(f"Saved customer index to {index_path}")
        
        return index
        
    except Exception as e:
        logger.error(f"Failed to create customer index: {e}")
        print(f"\n❌ Error creating index: {e}")
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
        
        print(f"\n🔍 Loading customer index for {folder_name}...")
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        index = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
        print(f"✅ Successfully loaded index from {index_path}")
        
        # Try to get index statistics if possible
        try:
            vector_count = len(index.index_to_docstore_id)
            print(f"📊 Index contains {vector_count} document chunks")
        except:
            # If we can't get stats, just continue
            pass
            
        logger.info(f"Loaded customer index from {index_path}")
        
        return index
        
    except Exception as e:
        logger.error(f"Failed to load customer index: {e}")
        print(f"❌ Error loading index: {e}")
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
                print("\n🔍 Using product knowledge only (no customer context)")
                return None  # No customer context
            
            if 1 <= idx <= len(folders):
                selected = folders[idx - 1]
                
                # Check if indexing is needed
                if not selected["has_index"] and selected["total_docs"] > 0:
                    response = input(f"\nFolder '{selected['name']}' needs indexing. Create index now? (y/n): ")
                    if response.lower() == 'y':
                        index = create_customer_index(selected["name"], selected["path"])
                        if index:
                            selected["has_index"] = True
                        else:
                            print("Failed to create index. Continue anyway? (y/n): ")
                            if input().lower() != 'y':
                                continue
                elif not selected["total_docs"]:
                    print(f"\n⚠️ Warning: Folder '{selected['name']}' has no documents!")
                    response = input("Continue with this empty folder? (y/n): ")
                    if response.lower() != 'y':
                        continue
                
                print(f"\n✅ Selected customer: {selected['name']}")
                return selected
            else:
                print(f"Please select a number between 0 and {len(folders)}")
                
        except ValueError:
            print("Please enter a valid number.")
            continue