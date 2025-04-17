import os
import json
import hashlib
import logging
import frontmatter
import uuid

from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_community.tools.tavily_search import TavilySearchResults

# ────────────────────────────────────────────────────────────────
# Logging & Config
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SKIP_INDEXING = True
PROCESSED_RECORD = os.environ.get("PROCESSED_RECORD", "/home/fritz/RAG_sf_e5_v1_2.json")
INDEX_DIR = os.environ.get("INDEX_DIR", "/home/fritz/faiss_index_sf_e5_v1_2")
BASE_DIR = os.environ.get("BASE_DIR", "/home/fritz/RAG_C")
TAVILY_API_KEY = "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"

# ────────────────────────────────────────────────────────────────
def compute_file_hash(file_path):
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
    except Exception as e:
        logging.error(f"Error reading file {file_path} for hashing: {e}")
    return hash_md5.hexdigest()

def load_processed_records(record_file):
    if os.path.exists(record_file):
        try:
            with open(record_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"Processed record file not found: {record_file}")
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {record_file}")
    return {}

def save_processed_records(records, record_file):
    with open(record_file, "w") as f:
        json.dump(records, f, indent=2)

def get_file_paths(base_dir: str):
    file_paths = []
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".md"):
                file_paths.append(os.path.join(root, file))
    return file_paths

def extract_chunks_and_metadata(doc_text, metadata, splitter, file_path):
    raw_chunks = splitter.split_text(doc_text)
    aggregated_chunks = []
    aggregated_metadata = []
    product_name = metadata.get("tag", os.path.basename(os.path.dirname(file_path)).replace("_", " "))
    doc_title = metadata.get("title", "")
    doc_category = metadata.get("category", "")
    doc_date = metadata.get("date", "")
    for chunk in raw_chunks:
        chunk_content = chunk.page_content.strip()
        chunk_metadata = {
            "uuid": str(uuid.uuid4()),
            "title": doc_title,
            "product": product_name,
            "category": doc_category,
            "date": doc_date,
            "source": file_path,
            "section": chunk.metadata.get("section", ""),
            "subsection": chunk.metadata.get("subsection", "")
        }
        aggregated_chunks.append(chunk_content)
        aggregated_metadata.append(chunk_metadata)
    return aggregated_chunks, aggregated_metadata

def process_file(file_path: str, splitter: MarkdownHeaderTextSplitter, embeddings, faiss_index):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
        doc_text = post.content
        metadata = post.metadata

        aggregated_chunks, aggregated_metadata = extract_chunks_and_metadata(
            doc_text, metadata, splitter, file_path
        )

        num_chunks = len(aggregated_chunks)
        logging.info(f"File {file_path} split into {num_chunks} chunk(s).")

        if faiss_index is None:
            logging.info(f"Creating new FAISS index with content from: {file_path}")
            faiss_index = FAISS.from_texts(aggregated_chunks, embeddings, metadatas=aggregated_metadata)
        else:
            faiss_index.add_texts(aggregated_chunks, aggregated_metadata)

        return num_chunks, faiss_index

    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return 0, faiss_index
    except frontmatter.FrontmatterError as e:
        logging.error(f"Frontmatter parsing error in {file_path}: {e}")
        return 0, faiss_index
    except Exception as e:
        logging.error(f"Unexpected error processing file {file_path}: {e}")
        return 0, faiss_index

def validate_faiss_index(index_dir):
    # Implement validation logic as needed
    # For now, just check if the directory exists and contains expected files
    return os.path.exists(index_dir)

# ────────────────────────────────────────────────────────────────
def main():
    logging.info(f"Starting processing of files from: {BASE_DIR}")
    file_paths = get_file_paths(BASE_DIR)
    total_files = len(file_paths)
    logging.info(f"Found {total_files} .md files to process.")

    processed_records = load_processed_records(PROCESSED_RECORD)
    logging.info(f"Found {len(processed_records)} processed file records.")

    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[
        ("#", "title"),
        ("##", "section"),
        ("###", "subsection")
    ])

    logging.info("Initializing local embeddings with intfloat/e5-large-v2...")
    embeddings = HuggingFaceEmbeddings(model_name="intfloat/e5-large-v2")

    if SKIP_INDEXING:
        logging.info("SKIP_INDEXING=True → Loading existing FAISS index only")
        # Validate the FAISS index file before loading
        if os.path.exists(INDEX_DIR) and validate_faiss_index(INDEX_DIR):
            logging.warning(
                "Loading FAISS index with allow_dangerous_deserialization=True. "
                "Ensure the index file is from a trusted source!"
            )
            faiss_index = FAISS.load_local(INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
        else:
            logging.error("FAISS index file is missing or failed validation.")
            return
    else:
        if os.path.exists(INDEX_DIR) and validate_faiss_index(INDEX_DIR):
            logging.info(f"Loading existing FAISS index from '{INDEX_DIR}'...")
            logging.warning(
                "Loading FAISS index with allow_dangerous_deserialization=True. "
                "Ensure the index file is from a trusted source!"
            )
            faiss_index = FAISS.load_local(INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
        else:
            faiss_index = None

        processed_files_count = 0
        total_chunks_processed = 0

        for i, file_path in enumerate(file_paths, start=1):
            progress = (i / total_files) * 100
            logging.info(f"Processing file {i}/{total_files} ({progress:.1f}%): {file_path}")
            file_hash = compute_file_hash(file_path)

            if file_path in processed_records and processed_records[file_path] == file_hash:
                logging.info(f"Skipping already processed file: {file_path}")
                continue

            chunks_processed, faiss_index = process_file(file_path, splitter, embeddings, faiss_index)
            total_chunks_processed += chunks_processed
            processed_records[file_path] = file_hash
            processed_files_count += 1

            if i % 100 == 0:
                save_processed_records(processed_records, PROCESSED_RECORD)
                if faiss_index is not None:
                    with faiss_index:
                        faiss_index.save_local(INDEX_DIR, allow_dangerous_deserialization=True)
                    logging.info(f"FAISS index saved locally to '{INDEX_DIR}'.")
                logging.info(f"Checkpoint: Processed records and FAISS index updated after {i} files.")

        logging.info(f"Finished indexing. Processed {processed_files_count} new files; Total new chunks: {total_chunks_processed}")
        save_processed_records(processed_records, PROCESSED_RECORD)
        if faiss_index is not None:
            with faiss_index:
                faiss_index.save_local(INDEX_DIR, allow_dangerous_deserialization=True)
            logging.info(f"FAISS index saved locally to '{INDEX_DIR}'.")
        else:
            logging.error("No FAISS index was created. Exiting.")
            return

    logging.info("Creating retriever from FAISS index...")
    retriever = faiss_index.as_retriever(search_kwargs={"k": 3})

    logging.info("Loading local LLM using Ollama...")
    ollama_llm = OllamaLLM(model="gemma3:12b", base_url="http://localhost:11434")

    logging.info("Defining Refine prompts...")
    question_prompt = PromptTemplate.from_template("""
You are a very Senior Solution Engineer at Salesforce. You have deep expertise in Salesforce products, including configuration, architecture, data modeling, integrations, and best practices.
You will receive questions from a RFP provided by A1, a leading Communication Service Provider (CSP) in Austria. Therefore focus on Salesforce Communications Cloud and related Salesforce Cloud products.

Answer the question below using ONLY the context provided.

Instructions:
- Focus on Salesforce Cloud products (e.g. Communications Cloud, Sales Cloud, Service Cloud).
- Highlight key benefits and best practices aligned with industry standards.
- Reference Salesforce documentation or real-world implementations if relevant.
- Use a professional, solution-oriented tone.
- Make the answer accessible to both technical and non-technical stakeholders.
- If the question is out of scope or not applicable, respond with "N/A" and briefly explain why.

Context:
{context_str}

Question:
{question}

Answer:
""")

    refine_prompt = PromptTemplate.from_template("""
We have provided an existing answer and new additional context. Please refine or expand the original answer only if the new context adds relevant value. Otherwise, return the original answer as-is.

Instructions:
- Focus on capabilities of Salesforce Cloud products.
- Be precise, relevant, and avoid repetition.
- If the question is out of scope or not addressed in the context, respond with "N/A" and briefly explain why.

Original Question:
{question}

Existing Answer:
{existing_answer}

Additional Context:
{context_str}

Refined Answer:
""")

    logging.info("Initializing Tavily Web Search tool...")
    web_search = TavilySearchResults(k=3, tavily_api_key=TAVILY_API_KEY)

    logging.info("Building Refine chain...")
    qa_chain = RetrievalQA.from_chain_type(
        llm=ollama_llm,
        retriever=retriever,
        chain_type="refine",
        return_source_documents=True,
        chain_type_kwargs={
            "question_prompt": question_prompt,
            "refine_prompt": refine_prompt
        }
    )

    #query = "What is the difference between Managed Package and Unmanaged Package in Salesforce? Give me some level of detail, around 10 sentences."
    #query = "What is the purpose of Industry Order Management as described in these documents? Give me some level of detail, around 10 sentences."
    query = "In Industry Order Managment (IOM) what is the purpose of a Point of no return (PONT)?"
    #query = "Explain Email to Case in Service Cloud. Give me some level of detail, around 10 sentences."
    #query = "Explain Salesforce Flow and how you can model / execute workflows in Salesforce. Give me some level of detail, around 10 sentences."
    #query = "In Sales Cloud, describe Lead to Opportunity process? Give me some level of detail, around 10 sentences."
    #query = "What are the options to implement product catalog synchronization from an external source?"

    logging.info(f"Running query: {query}")
    result = qa_chain.invoke({"query": query})

    if not result.get("result") or not result.get("source_documents"):
        logging.info("No relevant RAG content → Falling back to Tavily search...")
        web_results = web_search.run(query)
        print("\n--- Web Search Results (Fallback) ---")
        print(json.dumps(web_results, indent=2))
    else:
        print("\n====================================")
        print("Query:", query)
        print("Answer:", result["result"])
        print("====================================")

# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
