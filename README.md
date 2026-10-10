# UC07 AI-Enhanced Document Search

This project includes a React + Vite frontend and a Python FastAPI backend for a document-search prototype based on the UC07 use case.

## Stack

- Frontend: React + Vite
- Backend: FastAPI
- Vector database: PostgreSQL with the pgvector extension
- Embedding model: OpenAI `text-embedding-3-small`
- Optional LLM: OpenAI API when `OPENAI_API_KEY` is configured

## Run PostgreSQL with pgvector locally

```powershell
docker compose up -d
```

This starts a local PostgreSQL database with the `pgvector` extension enabled and a `document_chunks` table created automatically.

## Configure environment

Update `backend/.env` with the correct database settings if needed:

```env
OPENAI_API_KEY=your_key_here
EMBEDDING_MODEL=text-embedding-3-small
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

## Run locally

### 1) Backend

```powershell
cd backend
../backend/venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 2) Frontend

```powershell
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Then open the Vite URL, usually http://localhost:5173.

## Notes

- Default sample documents are stored in `backend/data/`.
- If PostgreSQL is configured, uploaded and default chunks are indexed using embeddings and stored in the `document_chunks` table.
- If the database is unavailable, the app falls back to the in-memory scoring system.
- To enable AI-generated answers, add your OpenAI key to `backend/.env` using the format in `.env.example`.
