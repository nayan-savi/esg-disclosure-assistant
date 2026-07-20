import os
import sys
import json
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains.retrieval import create_retrieval_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaEmbeddings, ChatOllama
# from langchain_community.vectorstores import Chroma
from langchain_chroma import Chroma


def query_report_for_request(requestId: str, module: str = "basic", model: str = "llama3"):
    print(f"Querying Report for request {requestId} using module {module} and model {model}")
    # Construct persistent Chroma path for requestId
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    chroma_dir = os.path.join(base_dir, "rag_chroma_db", f"{requestId}_{model}")

    if not os.path.exists(chroma_dir):
        print(f"Vector store not found at {chroma_dir}. Rebuilding dynamically...")
        from app.ingest.ingest_docs import ingest_docs_for_request
        success = ingest_docs_for_request(requestId, model=model)
        if not success:
            print(f"Error: Failed to dynamically build vector store at {chroma_dir}")
            return []

    try:
        # Load the selected questionnaire file
        q_file = "basic.txt" if module == "basic" else "comprehensive.txt"
        q_path = os.path.join(base_dir, "questionnaires", q_file)
        if not os.path.exists(q_path):
            q_path = os.path.join(base_dir, "questionnaires", "basic.txt")
            
        with open(q_path, "r", encoding="utf-8") as f:
            questionnaire_text = f.read()

        # 1. Load the database with appropriate embedding class
        from app.core.models import get_model_provider
        provider = get_model_provider(model)
        embeddings = provider.get_embeddings()

        db = Chroma(persist_directory=chroma_dir, embedding_function=embeddings)

        # 2. Convert database to a retriever object
        retriever = db.as_retriever(search_kwargs={"k": 5})

        # 3. Initialize LLM based on user selection
        llm = provider.get_llm(temperature=0.0)

        # 4. Prompt
        with open(base_dir+"/prompts/query.txt", "r", encoding="utf-8") as f:
            system_prompt = f.read()

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])

        question_answer_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)

        # Invoke the chain using the loaded questionnaire text
        response = rag_chain.invoke({
            "input": f"Please answer the following questionnaire:\n\n{questionnaire_text}"
        })

        raw_answer = response.get("answer", "").strip()

        # Parse using json_repair to be extremely robust
        import json_repair
        try:
            parsed_json = json_repair.loads(raw_answer)
            # If the LLM wrapped the JSON array in a dictionary, unpack it
            if isinstance(parsed_json, dict):
                for key in ["questionnaire_data", "data", "results", "answers", "questions"]:
                    if key in parsed_json and isinstance(parsed_json[key], list):
                        parsed_json = parsed_json[key]
                        break
            
            if isinstance(parsed_json, list):
                # Ensure the keys are mapped to what Angular template expects (question, answer, score)
                # Angular template uses item.question, item.answer, item.score (or confidence_score)
                # Wait, esg.service.ts interface EsgRequest has:
                # reportData?: Array<{ question: string, answer: string, confidence_score: number }> | null;
                # But wait, query.txt outputs:
                # "question": "<Question name>", "answer": "<Extracted value>", "score": <float>
                # Let's map "score" to "confidence_score" if it is present!
                for item in parsed_json:
                    if isinstance(item, dict):
                        if "score" in item and "confidence_score" not in item:
                            item["confidence_score"] = item["score"]
                return parsed_json
        except Exception as pe:
            print(f"Error parsing JSON from RAG output: {str(pe)}")

        # Fallback list if parsing failed
        return [
            {"question": "Total employees", "answer": raw_answer, "confidence_score": 0.5}
        ]
    except Exception as e:
        print(f"Error executing query_report_for_request: {str(e)}")
        return []


if __name__ == "__main__":
    if len(sys.argv) > 1:
        req_id = sys.argv[1]
        print(json.dumps(query_report_for_request(req_id), indent=2))
    else:
        print("Please provide a request ID.")
