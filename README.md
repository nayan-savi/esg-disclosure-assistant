# ESG Disclosure Assistant

An AI-powered platform for managing and generating ESG (Environmental, Social, and Governance) disclosure reports.

---

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Angular Frontend                            │
│                                                                     │
│  ┌──────────────┐   ┌───────────────────┐   ┌───────────────────┐   │
│  │  Investors   │   │ Investor Details  │   │    Dashboard /    │   │
│  │     Page     │   │      Page         │   │   Bankers Page    │   │
│  │  (upload +   │   │ (report, charts,  │   │  (analytics view) │   │
│  │   history)   │   │  model selector)  │   │                   │   │
│  └──────┬───────┘   └────────┬──────────┘   └────────┬──────────┘   │
│         └───────────────────┬┴──────────────────────┘               │
│                             │ HTTP (REST API)                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (app/main.py)                   │
│                                                                     │
│  POST /esg/upload          ─► Ingest documents, create request      │
│  GET  /esg/requests        ─► Fetch all ESG requests                │
│  PUT  /esg/requests/{id}/model ─► Switch LLM model & rebuild RAG    │
│  GET  /esg/requests/{id}/report/json ─► Query cached report JSON    │
│  POST /esg/requests/{id}/report/generate ─► Generate PDF report     │
│  GET  /esg/requests/report/download ─► Download versioned PDF       │
│                                                                     │
└────────┬───────────────┬──────────────────────┬────────────────────-┘
         │               │                      │
         ▼               ▼                      ▼
┌──────────────-┐ ┌───────────────────┐ ┌──────────────────────┐
│  PostgreSQL   │ │   RAG Pipeline    │ │    LLM (Gemini /     │
│   Database    │ │  (LangChain +     │ │     Llama 3)         │
│               │ │   ChromaDB)       │ │                      │
│ upload_request│ │                   │ │  Report generation   │
│ (request id,  │ │ 1. Load docs      │ │  Metric extraction   │
│  model, name, │ │ 2. Chunk & embed  │ │  JSON structuring    │
│  status)      │ │ 3. Store vectors  │ │                      │
│               │ │ 4. Similarity     │ │                      │
│               │ │    search         │ │                      │
└──────────────-┘ └─────────┬─────────┘ └──────────────────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │   Local File Store   │
                │                      │
                │  documents/          │  ← Uploaded source PDFs
                │  rag_chroma_db/      │  ← Vector embeddings
                │  esg_report/         │  ← Generated PDF reports
                └──────────────────────┘
```

### Data Flow

1. **Upload** — User uploads ESG documents (PDF/DOCX/TXT) via the frontend. The backend saves files to `documents/{requestId}/` and runs the RAG ingestion pipeline, chunking and embedding documents into ChromaDB.

2. **Model Selection** — User can switch the LLM model (Gemini 3.5 / Llama 3) on the details page. The backend updates the database and rebuilds the vector store for the new model under a separate directory (`rag_chroma_db/{requestId}_{model}`).

3. **Report Generation** — User triggers report generation with a choice of module (Basic / Comprehensive). The backend queries ChromaDB for relevant context, feeds it to the LLM with a structured prompt, and generates a typed JSON payload and a formatted PDF.

4. **Report Download** — Generated PDFs are versioned as `esg_report-v{n}-{module}.pdf` and served directly for download.

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL

---

## Backend

### Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Start the Backend Server

```bash
cd backend
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

---

## Frontend

### Setup

```bash
cd frontend
npm install
```

### Start the Frontend Dev Server

```bash
npm run dev
```

The app will be available at `http://localhost:4200`.

---

## Project Structure

```
esg-disclosure-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application & routes
│   │   ├── core/            # LLM model config
│   │   ├── ingest/          # Document ingestion & RAG pipeline
│   │   └── query/           # Report generation
│   ├── db/                  # Database session & schema
│   ├── prompts/             # LLM prompt templates
│   ├── questionnaires/      # ESG questionnaire definitions
│   └── requirements.txt
└── frontend/
    └── src/
        └── app/             # Angular components & services
```
