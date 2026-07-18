import os
import sys

# Ensure backend root is in sys.path for app module imports
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from langchain_community.document_loaders import Docx2txtLoader, TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

def ingest_docs_for_request(requestId: str, model: str = "llama3") -> bool:
    # Resolve paths relative to backend root folder
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    docs_dir = os.path.join(base_dir, "documents", requestId)
    
    # Persistent database stored under backend/rag_chroma_db/{requestId}_{model}
    chroma_dir = os.path.join(base_dir, "rag_chroma_db", f"{requestId}_{model}")
    
    print(f"Starting RAG Ingestion for request: {requestId} using model {model}...")
    print(f"Input Directory (DOCS_DIR): {docs_dir}")
    print(f"Output Vector Store (CHROMA_DIR): {chroma_dir}")
    
    # 1. Load all supported files from the directory
    raw_documents = []
    if os.path.exists(docs_dir):
        for root, dirs, files in os.walk(docs_dir):
            for file in files:
                if file.startswith("."):
                    continue
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                try:
                    if ext == ".docx":
                        loader = Docx2txtLoader(file_path)
                        raw_documents.extend(loader.load())
                    elif ext == ".pdf":
                        loader = PyPDFLoader(file_path)
                        raw_documents.extend(loader.load())
                    elif ext in [".txt", ".json", ".csv"]:
                        loader = TextLoader(file_path, encoding="utf-8")
                        raw_documents.extend(loader.load())
                    else:
                        print(f"Skipping unsupported file type: {file}")
                except Exception as e:
                    print(f"Error loading file '{file}': {str(e)}")
    else:
        print(f"DOCS_DIR '{docs_dir}' does not exist.")
        return False

    if not raw_documents:
        print("No valid documents found for ingestion.")
        return False

    # 2. Chunk the documents
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(raw_documents)

    # 3. Embed and store
    from app.core.models import get_model_provider
    provider = get_model_provider(model)
    embeddings = provider.get_embeddings()

    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=chroma_dir
    )

    print(f"Successfully processed {len(raw_documents)} files into {len(chunks)} chunks in Chroma DB.")
    return True

if __name__ == "__main__":
    req_id = os.getenv("REQUEST_ID")
    if not req_id and len(sys.argv) > 1:
        req_id = sys.argv[1]
        
    if not req_id:
        print("Error: No requestId provided.")
        sys.exit(1)
        
    model = os.getenv("MODEL", "llama3")
    if len(sys.argv) > 2:
        model = sys.argv[2]
        
    success = ingest_docs_for_request(req_id, model=model)
    if not success:
        sys.exit(1)