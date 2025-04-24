"""
Query functionality for the RAG system.
Handles retrieving relevant documents and generating responses.
"""
import os
import json
import re
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import FAISS
import pickle
import numpy as np
import faiss

import config

# Import the response parser
from response_parser import parse_and_fix_json_response


def get_index_info(index_dir: str) -> dict:
    """Get information about the FAISS index.
    
    Extracts metadata and statistics about a FAISS index, including
    total vectors, dimensions, product distribution, and GPU usage.
    
    Args:
        index_dir: Directory containing the FAISS index
        
    Returns:
        Dictionary with index information including:
        - total_vectors: Number of vectors in the index
        - vector_dimension: Dimension of the vectors
        - disk_size_bytes: Size of the index on disk in bytes
        - disk_size_mb: Size of the index on disk in megabytes
        - index_type: Type of FAISS index
        - product_distribution: Counts of vectors by product category
        - gpu_available: Whether GPU is available for FAISS
        - gpu_usage: Description of GPU usage status
    """
    index_faiss = os.path.join(index_dir, "index.faiss")
    index_pkl = os.path.join(index_dir, "index.pkl")
    
    if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
        raise FileNotFoundError("FAISS index files not found. Build the index first.")
    
    # Load the index metadata
    with open(index_pkl, 'rb') as f:
        metadata = pickle.load(f)
    
    # Load the FAISS index to get its properties
    index = faiss.read_index(index_faiss)
    
    # Get document count and vector dimension
    total_vectors = index.ntotal
    vector_dim = index.d
    
    # Extract product distribution from metadata
    products = {}
    
    # Debug: print metadata structure to understand its format
    print(f"DEBUG: Metadata type: {type(metadata)}")
    if isinstance(metadata, tuple):
        print(f"DEBUG: Metadata tuple length: {len(metadata)}")
    elif isinstance(metadata, dict):
        print(f"DEBUG: Metadata dict keys: {list(metadata.keys())}")
    
    # Try multiple approaches to extract product information
    try:
        # Approach 1: Direct access to docstore dictionary (newer format)
        if hasattr(metadata, 'get') and metadata.get('docstore'):
            docstore_dict = metadata.get('docstore', {}).get('_dict', {})
            for doc_id, doc_metadata in docstore_dict.items():
                if hasattr(doc_metadata, 'metadata') and 'product' in doc_metadata.metadata:
                    product = doc_metadata.metadata.get('product', '')
                    if product:
                        products[product] = products.get(product, 0) + 1
                # Also check for 'tag' field which might contain product info
                elif hasattr(doc_metadata, 'metadata') and 'tag' in doc_metadata.metadata:
                    product = doc_metadata.metadata.get('tag', '')
                    if product:
                        products[product] = products.get(product, 0) + 1
                        
        # Approach 2: Handle tuple format (older or modified format)
        elif isinstance(metadata, tuple):
            # Try different elements of the tuple
            for i, element in enumerate(metadata):
                # Look for docstore in dict elements
                if isinstance(element, dict) and 'docstore' in element:
                    docstore = element['docstore']
                    if hasattr(docstore, '_dict'):
                        for doc_id, doc_metadata in docstore._dict.items():
                            if hasattr(doc_metadata, 'metadata'):
                                # Try product field first
                                if 'product' in doc_metadata.metadata:
                                    product = doc_metadata.metadata.get('product', '')
                                    if product:
                                        products[product] = products.get(product, 0) + 1
                                # Then try tag field
                                elif 'tag' in doc_metadata.metadata:
                                    product = doc_metadata.metadata.get('tag', '')
                                    if product:
                                        products[product] = products.get(product, 0) + 1
                                        
                # Look for direct access to documents
                elif hasattr(element, '_dict'):
                    for doc_id, doc_metadata in element._dict.items():
                        if hasattr(doc_metadata, 'metadata'):
                            # Try product field first
                            if 'product' in doc_metadata.metadata:
                                product = doc_metadata.metadata.get('product', '')
                                if product:
                                    products[product] = products.get(product, 0) + 1
                            # Then try tag field
                            elif 'tag' in doc_metadata.metadata:
                                product = doc_metadata.metadata.get('tag', '')
                                if product:
                                    products[product] = products.get(product, 0) + 1
                                    
        # Optional: Print extracted products for debugging
        if products:
            print(f"DEBUG: Successfully extracted product distribution with {len(products)} products")
        else:
            print("DEBUG: No products extracted - metadata format may be different than expected")
            
    except Exception as e:
        print(f"Warning: Could not extract product distribution: {e}")
        # Continue without product distribution
    
    # Calculate index size on disk
    index_size = os.path.getsize(index_faiss) + os.path.getsize(index_pkl)
    
    # Get index type
    if isinstance(index, faiss.IndexIVFFlat):
        index_type = "IVF Flat"
    elif isinstance(index, faiss.IndexFlat):
        index_type = "Flat"
    elif isinstance(index, faiss.IndexIVFPQ):
        index_type = "IVF PQ"
    else:
        index_type = str(type(index))
    
    # Check if GPU is being used
    gpu_available = faiss.get_num_gpus() > 0
    gpu_resources = []
    
    if gpu_available:
        try:
            # This will only work if faiss-gpu is installed and GPU is available
            for i in range(faiss.get_num_gpus()):
                res = faiss.StandardGpuResources()
                gpu_resources.append(res)
            gpu_usage = "Available and detected"
        except Exception:
            gpu_usage = "Available but not used by FAISS"
    else:
        gpu_usage = "Not available"
    
    return {
        "total_vectors": total_vectors,
        "vector_dimension": vector_dim,
        "disk_size_bytes": index_size,
        "disk_size_mb": round(index_size / (1024 * 1024), 2),
        "index_type": index_type,
        "product_distribution": products,
        "gpu_available": gpu_available,
        "gpu_usage": gpu_usage
    }


def raw_llm_query(question: str = None):
    """Query the LLM with no grounding and no RAG context.
    
    Sends a query directly to the LLM without any grounding prompt or RAG context,
    to demonstrate the baseline LLM capabilities.
    
    Args:
        question: Question to ask the LLM (uses default if None)
        
    Returns:
        The LLM's raw response as a string
    """
    if not question:
        question = "How does Salesforce Communications Cloud handle product bundling?"
    
    print("\n📝 Querying LLM with no grounding or RAG (raw query)")
    
    # Initialize the LLM
    llm = OllamaLLM(model=config.LLM_MODEL, base_url=config.OLLAMA_URL)
    
    # Generate direct prompt without any grounding
    prompt = question
    
    # Generate response
    response = llm.invoke(prompt)
    
    # Print results
    print("\n" + "=" * 40)
    print(f"Question: {question}")
    print(f"Raw LLM Answer (NO GROUNDING, NO RAG): {response}")
    print("=" * 40)
    
    return response


def direct_llm_query(question: str = None):
    """Query the LLM directly with grounding prompt but without using RAG.
    
    Sends a query directly to the LLM with a grounding prompt but without providing
    any retrieved document context, for comparison with RAG-enhanced responses.
    
    Args:
        question: Question to ask the LLM (uses default if None)
        
    Returns:
        The LLM's response as a JSON string
    """
    if not question:
        question = "How does Salesforce Communications Cloud handle product bundling?"
    
    print("\n📝 Querying LLM with grounding but without RAG (no context provided)")
    
    # Initialize the LLM
    llm = OllamaLLM(model=config.LLM_MODEL, base_url=config.OLLAMA_URL)
    
    # Generate direct prompt without context
    prompt = f"""
You are a Senior Solution Engineer at Salesforce, with deep expertise in Salesforce products — especially Communications Cloud.

Your task is to answer the following RFI (Request for Information) question to the best of your knowledge. Your response must be:
- Clear
- Professional
- Focused on Salesforce product relevance

---

❗️**STEP 1: EVALUATE RELEVANCE**

Is the question relevant to Salesforce?
- About any Salesforce product (Sales Cloud, Service Cloud, Communications Cloud, etc.)?
- Concerning business processes, customer engagement, cloud platforms, or integrations?

❌ **If NOT relevant**, respond ONLY with:
{{
  "compliance": "NA",
  "answer": "This question is not applicable to Salesforce or its product offerings and should be marked as out of scope."
}}

---

✅ **If relevant, continue to STEP 2.**

❗️**STEP 2: DETERMINE COMPLIANCE LEVEL**

1. **FC (Fully Compliant)** - Supported via standard configuration or UI-based setup
   - No custom code required (e.g., Flow, page layouts, permissions, validation rules are NOT custom code)

2. **PC (Partially Compliant)** - Requires custom development (Apex, LWC, APIs, external integrations)

3. **NC (Not Compliant)** - Not possible in Salesforce even with customization

4. **NA (Not Applicable)** - Determined in Step 1

---

❗️**STEP 3: FORMAT**
Return ONLY:
{{
  "compliance": "FC|PC|NC|NA",
  "answer": "Your concise professional explanation (5–10 sentences)"
}}

Question:
{question}
Answer (JSON only):
"""

    # Generate response
    response = llm.invoke(prompt)
    
    # Print results
    print("\n" + "=" * 40)
    print(f"Question: {question}")
    print(f"Grounded LLM Answer (NO RAG): {response}")
    print("=" * 40)
    
    return response


def test_query(index_dir: str, custom_question: str = None):
    """Test all query modes (raw, grounded, and RAG-enhanced) and generate responses.
    
    Loads the FAISS index, runs three types of queries for comparison:
    1. Raw LLM with no grounding and no RAG
    2. LLM with grounding but no RAG
    3. LLM with both grounding and RAG
    
    Args:
        index_dir: Directory containing the FAISS index
        custom_question: Optional custom question to test with (uses default if None)
        
    Returns:
        List of retrieved documents used for the response
    """
    # Use custom question if provided, otherwise use default
    question = custom_question or "How does Salesforce Communications Cloud handle product bundling?"
    
    print("\n🔍 Running comprehensive test query with all three modes:")
    print("  1. Raw LLM (no grounding, no RAG)")
    print("  2. Grounded LLM (with grounding, no RAG)")
    print("  3. RAG-enhanced LLM (with grounding and document context)")
    
    # Mode 1: Raw LLM query (no grounding, no RAG)
    raw_llm_query(question)
    
    # Mode 2: Direct LLM query (with grounding, no RAG)
    direct_llm_query(question)
    
    # Mode 3: RAG-enhanced query (with grounding and document context)
    print("\n📝 Running RAG-enhanced query (with grounding and document context)")
    
    embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
    index_faiss = os.path.join(index_dir, "index.faiss")
    index_pkl = os.path.join(index_dir, "index.pkl")
    
    if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
        raise FileNotFoundError("FAISS index files not found. Build the index first.")

    # Check if we're using GPU for search
    try:
        gpu_count = faiss.get_num_gpus()
        if gpu_count > 0:
            print(f"🚀 Using GPU acceleration for vector search (GPUs: {gpu_count})")
        else:
            print("⚠️ Using CPU for vector search (no GPU acceleration)")
    except Exception:
        print("⚠️ Using CPU for vector search (could not detect GPU status)")

    vectorstore = FAISS.load_local(index_dir, embeddings, allow_dangerous_deserialization=True)
    # Increase the number of documents to retrieve for more context
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    llm = OllamaLLM(model=config.LLM_MODEL, base_url=config.OLLAMA_URL, temperature=0.2)
    
    # Retrieve relevant documents
    try:
        # New way using invoke (preferred method that avoids deprecation warning)
        docs = retriever.invoke(question)
    except Exception:
        # Fallback to old method if invoke doesn't work
        docs = retriever.get_relevant_documents(question)
        
    context = "\n---\n".join([doc.page_content for doc in docs])

    # Generate prompt with context
    prompt = f"""
You are a Senior Solution Engineer at Salesforce, with deep expertise in Salesforce products — especially Communications Cloud.

Your task is to answer the following RFI (Request for Information) question using the provided context and any additional clues from the question. 

THE FORMAT OF YOUR RESPONSE IS CRITICAL. YOU MUST RETURN A JSON OBJECT WITH BOTH "compliance" AND "answer" FIELDS.

---

❗️**STEP 1: EVALUATE RELEVANCE**

Is the question relevant to Salesforce?
- About any Salesforce product (Sales Cloud, Service Cloud, Communications Cloud, etc.)?
- Concerning business processes, customer engagement, cloud platforms, or integrations?

❌ **If NOT relevant**, respond ONLY with:
{{
  "compliance": "NA",
  "answer": "This question is not applicable to Salesforce or its product offerings and should be marked as out of scope."
}}

---

✅ **If relevant, continue to STEP 2.**

❗️**STEP 2: DETERMINE COMPLIANCE LEVEL**

Carefully analyze the context to determine:

1. **FC (Fully Compliant)** - Supported via standard configuration or UI-based setup
   - No custom code required (e.g., Flow, page layouts, permissions, validation rules are NOT custom code)

2. **PC (Partially Compliant)** - Requires custom development (Apex, LWC, APIs, external integrations)

3. **NC (Not Compliant)** - Not possible in Salesforce even with customization

4. **NA (Not Applicable)** - Determined in Step 1

IMPORTANT: Even if the context doesn't explicitly state the compliance level, use your judgment to determine it based on the implementation details described.

---

❗️**STEP 3: FORMAT RESPONSE**
YOU MUST INCLUDE BOTH FIELDS IN YOUR RESPONSE:
{{
  "compliance": "FC|PC|NC|NA",
  "answer": "Your detailed explanation (8-10 sentences minimum)"
}}

CRITICAL INSTRUCTION: Always include both the compliance field and the answer field in your JSON response. NEVER OMIT THE COMPLIANCE FIELD.

Context:
{context}

Question:
{question}

Answer (JSON only with both compliance and answer fields):
"""

    # Generate response
    response = llm.invoke(prompt)
    
    # Parse and fix the response to ensure it has the required fields
    fixed_response = parse_and_fix_json_response(response)
    
    # Print results
    print("\n" + "=" * 40)
    print(f"Question: {question}")
    print(f"RAG-Enhanced Answer: {fixed_response}")
    print("=" * 40)
    
    # Return relevant documents for potential further analysis
    return docs