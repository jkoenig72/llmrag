import logging
import os
import gc
import time
import torch
from typing import Optional, List, Dict, Any
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema import Document

logger = logging.getLogger(__name__)

class EmbeddingManager:
    """
    Manages the lifecycle of embedding models to optimize memory usage.
    Implements a load, query, unload pattern for vector database interactions.
    """
    
    def __init__(self, embedding_model_name: str):
        """
        Initialize the embedding manager with a model name.
        
        Parameters
        ----------
        embedding_model_name : str
            Name of the Hugging Face embedding model to use
        """
        self.embedding_model_name = embedding_model_name
        self.current_embeddings = None
        self.current_index_path = None
        
        # Print information about GPU availability
        if torch.cuda.is_available():
            print(f"🔥 GPU detected: {torch.cuda.get_device_name(0)}")
            print(f"🧠 Available GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        else:
            print("⚠️ No GPU detected. Running in CPU mode.")
    
    def _unload_current_model(self):
        """
        Unload the currently loaded embedding model and clear CUDA cache if available.
        """
        if self.current_embeddings is not None:
            print("🔄 Unloading embedding model and freeing GPU memory...")
            logger.info("Unloading current embedding model")
            self.current_embeddings = None
            
            # Force garbage collection
            gc.collect()
            
            # Clear CUDA cache if using GPU
            if torch.cuda.is_available():
                before_mem = torch.cuda.memory_allocated() / 1024**3
                torch.cuda.empty_cache()
                after_mem = torch.cuda.memory_allocated() / 1024**3
                freed_mem = before_mem - after_mem
                
                if freed_mem > 0:
                    print(f"🧹 Cleared {freed_mem:.2f} GB of CUDA memory")
                else:
                    print("🧹 CUDA memory cache cleared")
                
                logger.info(f"Cleared CUDA cache, freed {freed_mem:.2f} GB")
    
    def _load_embeddings(self, use_cpu: bool = False) -> HuggingFaceEmbeddings:
        """
        Load the embedding model, optionally forcing CPU usage.
        
        Parameters
        ----------
        use_cpu : bool, default False
            If True, force CPU usage even if GPU is available
            
        Returns
        -------
        HuggingFaceEmbeddings
            Loaded embedding model
        """
        # Unload any existing model first
        self._unload_current_model()
        
        start_time = time.time()
        print(f"📥 Loading embedding model: {self.embedding_model_name}")
        
        model_kwargs = {"device": "cpu"} if use_cpu else {}
        
        if use_cpu:
            print("💻 Using CPU for embeddings (GPU disabled)")
            logger.info("Using CPU for embeddings (GPU disabled)")
        else:
            if torch.cuda.is_available():
                print(f"🚀 Using GPU for embeddings: {torch.cuda.get_device_name(0)}")
                logger.info(f"Using GPU for embeddings: {torch.cuda.get_device_name(0)}")
            else:
                print("💻 Using CPU for embeddings (no GPU available)")
                logger.info("Using CPU for embeddings (no GPU available)")
                model_kwargs = {"device": "cpu"}
        
        # Create and load embeddings
        self.current_embeddings = HuggingFaceEmbeddings(
            model_name=self.embedding_model_name,
            model_kwargs=model_kwargs
        )
        
        load_time = time.time() - start_time
        print(f"✅ Embedding model loaded in {load_time:.2f} seconds")
        
        # Report memory usage if using GPU
        if torch.cuda.is_available() and not use_cpu:
            used_mem = torch.cuda.memory_allocated() / 1024**3
            total_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"🧠 GPU memory usage: {used_mem:.2f} GB / {total_mem:.2f} GB ({used_mem/total_mem*100:.1f}%)")
        
        return self.current_embeddings
    
    def query_index(self, index_path: str, query: str, k: int = 4, 
                   use_cpu: bool = False, db_name: str = "Vector DB") -> List[Document]:
        """
        Load an index, query it to retrieve all relevant documents at once, and then unload it.
        This implements the "load, query, unload" cycle for an entire batch of documents.
        
        Parameters
        ----------
        index_path : str
            Path to the FAISS index
        query : str
            Query string
        k : int, default 4
            Number of documents to retrieve
        use_cpu : bool, default False
            If True, force CPU usage even if GPU is available
        db_name : str, default "Vector DB"
            Name of the database for logging purposes
            
        Returns
        -------
        List[Document]
            Retrieved documents
            
        Note
        ----
        This function implements a complete cycle:
        1. Load embedding model
        2. Load FAISS index
        3. Query index for all k documents at once
        4. Unload model and clear GPU memory
        5. Return retrieved documents
        
        The embedding model is only in memory during this function call.
        """
        print(f"\n{'='*30} {db_name} Query {'='*30}")
        print(f"📊 Executing full query cycle for {db_name}")
        
        # Check for CPU flag file
        cpu_flag_file = os.path.join(index_path, "_created_with_cpu")
        if os.path.exists(cpu_flag_file):
            print(f"🔍 Found CPU flag file for {db_name}. Forcing CPU mode.")
            logger.info(f"Found CPU flag file for {index_path}. Forcing CPU mode.")
            use_cpu = True
        
        # STEP 1: Load embeddings
        print(f"🔄 STEP 1: Loading embeddings for {db_name}")
        start_time = time.time()
        embeddings = self._load_embeddings(use_cpu)
        
        try:
            # STEP 2: Load index
            print(f"🔄 STEP 2: Loading FAISS index from {os.path.basename(index_path)}")
            logger.info(f"Loading FAISS index from {index_path}")
            index_start = time.time()
            index = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
            index_time = time.time() - index_start
            print(f"✅ Index loaded in {index_time:.2f} seconds")
            
            # STEP 3: Query index for all documents at once
            print(f"🔄 STEP 3: Querying {db_name} for top {k} documents")
            logger.info(f"Querying index with k={k}")
            query_start = time.time()
            docs = index.similarity_search(query, k=k)
            query_time = time.time() - query_start
            print(f"✅ Retrieved {len(docs)} documents in {query_time:.2f} seconds")
            
            # Keep a copy of docs before unloading model
            results = docs.copy() if hasattr(docs, 'copy') else list(docs)
            
            # STEP 4: Unload model and clear GPU memory
            print(f"🔄 STEP 4: Unloading {db_name} embedding model")
            self._unload_current_model()
            
            # Total time
            total_time = time.time() - start_time
            print(f"✅ Total {db_name} query cycle completed in {total_time:.2f} seconds")
            print(f"{'='*75}")
            
            # STEP 5: Return the retrieved documents
            return results
            
        except Exception as e:
            error_msg = f"Error querying {db_name} index: {e}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            # Ensure model is unloaded even if there was an error
            self._unload_current_model()
            print(f"{'='*75}")
            return []
    
    def create_index(self, documents: List[Document], output_path: str, 
                    use_cpu: bool = False, db_name: str = "Vector DB") -> Optional[str]:
        """
        Create a FAISS index, save it, and then unload the model.
        
        Parameters
        ----------
        documents : List[Document]
            Documents to index
        output_path : str
            Path to save the index
        use_cpu : bool, default False
            If True, force CPU usage
        db_name : str, default "Vector DB"
            Name of the database for logging purposes
            
        Returns
        -------
        Optional[str]
            Path to the created index or None if failed
        """
        try:
            print(f"\n{'='*30} Creating {db_name} Index {'='*30}")
            
            # Load embeddings
            print(f"🔄 STEP 1: Loading embedding model for {db_name} index creation")
            start_time = time.time()
            embeddings = self._load_embeddings(use_cpu)
            
            # Create index
            print(f"🔄 STEP 2: Creating FAISS index from {len(documents)} documents")
            logger.info(f"Creating FAISS index from {len(documents)} documents")
            index_start = time.time()
            index = FAISS.from_documents(documents, embeddings)
            index_time = time.time() - index_start
            print(f"✅ Index created in {index_time:.2f} seconds")
            
            # Ensure directory exists
            os.makedirs(output_path, exist_ok=True)
            
            # Save index
            print(f"🔄 STEP 3: Saving index to {os.path.basename(output_path)}")
            logger.info(f"Saving index to {output_path}")
            save_start = time.time()
            index.save_local(output_path)
            save_time = time.time() - save_start
            print(f"✅ Index saved in {save_time:.2f} seconds")
            
            # Create CPU flag file if needed
            if use_cpu:
                flag_path = os.path.join(output_path, "_created_with_cpu")
                with open(flag_path, 'w') as f:
                    f.write("This index was created with CPU and should be loaded with CPU.")
                print(f"📝 Created CPU flag file: {os.path.basename(flag_path)}")
            
            # Unload model
            print(f"🔄 STEP 4: Unloading embedding model")
            self._unload_current_model()
            
            # Total time
            total_time = time.time() - start_time
            print(f"✅ {db_name} index creation completed in {total_time:.2f} seconds")
            print(f"{'='*75}")
            
            return output_path
            
        except Exception as e:
            error_msg = f"Error creating {db_name} index: {e}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            self._unload_current_model()
            print(f"{'='*75}")
            return None