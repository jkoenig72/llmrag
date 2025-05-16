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
    def __init__(self, embedding_model_name: str):
        self.embedding_model_name = embedding_model_name
        self.current_embeddings = None
        self.current_index_path = None
        
        if torch.cuda.is_available():
            print(f"🔥 GPU detected: {torch.cuda.get_device_name(0)}")
            print(f"🧠 Available GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        else:
            print("⚠️ No GPU detected. Running in CPU mode.")
    
    def _unload_current_model(self):
        if self.current_embeddings is not None:
            print("🔄 Unloading embedding model and freeing GPU memory...")
            logger.info("Unloading current embedding model")
            self.current_embeddings = None
            
            gc.collect()
            
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
        
        self.current_embeddings = HuggingFaceEmbeddings(
            model_name=self.embedding_model_name,
            model_kwargs=model_kwargs
        )
        
        load_time = time.time() - start_time
        print(f"✅ Embedding model loaded in {load_time:.2f} seconds")
        
        if torch.cuda.is_available() and not use_cpu:
            used_mem = torch.cuda.memory_allocated() / 1024**3
            total_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"🧠 GPU memory usage: {used_mem:.2f} GB / {total_mem:.2f} GB ({used_mem/total_mem*100:.1f}%)")
        
        return self.current_embeddings
    
    def query_index(self, index_path: str, query: str, k: int = 4, 
                   use_cpu: bool = False, db_name: str = "Vector DB",
                   filter_products: List[str] = None) -> List[Document]:
        print(f"\n{'='*30} {db_name} Query {'='*30}")
        print(f"📊 Executing full query cycle for {db_name}")
        
        cpu_flag_file = os.path.join(index_path, "_created_with_cpu")
        if os.path.exists(cpu_flag_file):
            print(f"🔍 Found CPU flag file for {db_name}. Forcing CPU mode.")
            logger.info(f"Found CPU flag file for {index_path}. Forcing CPU mode.")
            use_cpu = True
        
        print(f"🔄 STEP 1: Loading embeddings for {db_name}")
        start_time = time.time()
        embeddings = self._load_embeddings(use_cpu)
        
        try:
            print(f"🔄 STEP 2: Loading FAISS index from {os.path.basename(index_path)}")
            logger.info(f"Loading FAISS index from {index_path}")
            index_start = time.time()
            index = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
            index_time = time.time() - index_start
            print(f"✅ Index loaded in {index_time:.2f} seconds")
            
            print(f"🔄 STEP 3: Querying {db_name} for top {k} documents")
            logger.info(f"Querying index with k={k}")
            query_start = time.time()
            
            if filter_products and len(filter_products) > 0:
                print(f"🔍 Applying product filter: {', '.join(filter_products)}")
                logger.info(f"Applying product filter: {', '.join(filter_products)}")
                
                docs_with_scores = index.similarity_search_with_score(query, k=k*5)
                
                filtered_docs = []
                for doc, score in docs_with_scores:
                    product = None
                    if hasattr(doc, 'metadata'):
                        if 'product' in doc.metadata:
                            product = doc.metadata.get('product', '')
                        elif 'tag' in doc.metadata:
                            product = doc.metadata.get('tag', '').replace('_', ' ')
                    
                    if product:
                        for filter_product in filter_products:
                            if (filter_product.lower() in product.lower() or
                                product.lower() in filter_product.lower()):
                                filtered_docs.append((doc, score))
                                break
                
                filtered_docs = sorted(filtered_docs, key=lambda x: x[1])[:k]
                docs = [doc for doc, _ in filtered_docs]
                
                if len(docs) < k:
                    print(f"⚠️ Warning: Found only {len(docs)}/{k} documents matching product filter")
                    logger.warning(f"Found only {len(docs)}/{k} documents matching product filter")
            else:
                docs = index.similarity_search(query, k=k)
            
            query_time = time.time() - query_start
            print(f"✅ Retrieved {len(docs)} documents in {query_time:.2f} seconds")
            
            results = docs.copy() if hasattr(docs, 'copy') else list(docs)
            
            print(f"🔄 STEP 4: Unloading {db_name} embedding model")
            self._unload_current_model()
            
            total_time = time.time() - start_time
            print(f"✅ Total {db_name} query cycle completed in {total_time:.2f} seconds")
            print(f"{'='*75}")
            
            return results
            
        except Exception as e:
            error_msg = f"Error querying {db_name} index: {e}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            self._unload_current_model()
            print(f"{'='*75}")
            return []
    
    def create_index(self, documents: List[Document], output_path: str, 
                    use_cpu: bool = False, db_name: str = "Vector DB") -> Optional[str]:
        try:
            print(f"\n{'='*30} Creating {db_name} Index {'='*30}")
            
            print(f"🔄 STEP 1: Loading embedding model for {db_name} index creation")
            start_time = time.time()
            embeddings = self._load_embeddings(use_cpu)
            
            print(f"🔄 STEP 2: Creating FAISS index from {len(documents)} documents")
            logger.info(f"Creating FAISS index from {len(documents)} documents")
            index_start = time.time()
            index = FAISS.from_documents(documents, embeddings)
            index_time = time.time() - index_start
            print(f"✅ Index created in {index_time:.2f} seconds")
            
            os.makedirs(output_path, exist_ok=True)
            
            print(f"🔄 STEP 3: Saving index to {os.path.basename(output_path)}")
            logger.info(f"Saving index to {output_path}")
            save_start = time.time()
            index.save_local(output_path)
            save_time = time.time() - save_start
            print(f"✅ Index saved in {save_time:.2f} seconds")
            
            if use_cpu:
                flag_path = os.path.join(output_path, "_created_with_cpu")
                with open(flag_path, 'w') as f:
                    f.write("This index was created with CPU and should be loaded with CPU.")
                print(f"📝 Created CPU flag file: {os.path.basename(flag_path)}")
            
            print(f"🔄 STEP 4: Unloading embedding model")
            self._unload_current_model()
            
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