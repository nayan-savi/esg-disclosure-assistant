# ESG Disclosure Assistant

An AI-powered platform for managing and generating ESG (Environmental, Social, and Governance) disclosure reports.

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

### Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
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
