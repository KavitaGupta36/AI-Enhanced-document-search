from __future__ import annotations

import os
import re
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pgvector.psycopg import register_vector
from psycopg import connect
from pydantic import BaseModel
from pypdf import PdfReader

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

load_dotenv(Path(__file__).resolve().parent / ".env")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="UC07 AI Document Search", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 3


DOCUMENTS: list[dict[str, Any]] = []
MIN_VECTOR_SIMILARITY = 0.45
SEARCH_STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "by", "can", "could",
    "did", "do", "does", "for", "from", "how", "i", "in", "is", "it", "me",
    "of", "on", "or", "please", "should", "tell", "the", "to", "was", "what",
    "when", "where", "which", "who", "why", "with", "would",
}


def get_database_url() -> str | None:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "postgres")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")

    if not all([host, db, user, password]):
        return None

    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def initialize_vector_database() -> bool:
    database_url = get_database_url()
    if not database_url:
        return False

    try:
        with connect(database_url) as conn:
            register_vector(conn)
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_chunks (
                        id SERIAL PRIMARY KEY,
                        source TEXT NOT NULL,
                        chunk_text TEXT NOT NULL,
                        embedding VECTOR(1536)
                    )
                    """
                )
        return True
    except Exception:
        return False


def get_openai_client():
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

    if azure_endpoint and azure_key:
        from openai import AzureOpenAI

        return AzureOpenAI(
            api_key=azure_key,
            api_version=azure_api_version,
            azure_endpoint=azure_endpoint,
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    from openai import OpenAI

    return OpenAI(api_key=api_key)


def create_embedding(text: str) -> list[float] | None:
    client = get_openai_client()
    if client is None:
        return None

    try:
        deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT") or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        response = client.embeddings.create(
            model=deployment,
            input=text,
        )
        return response.data[0].embedding
    except Exception:
        return None


def store_document_chunks_in_postgres(source: str, chunks: list[str]) -> None:
    database_url = get_database_url()
    if not database_url:
        return

    try:
        with connect(database_url) as conn:
            register_vector(conn)
            with conn.cursor() as cursor:
                for chunk in chunks:
                    embedding = create_embedding(chunk)
                    if embedding is None:
                        continue
                    cursor.execute(
                        "INSERT INTO document_chunks (source, chunk_text, embedding) VALUES (%s, %s, %s)",
                        (source, chunk, embedding),
                    )
            conn.commit()
    except Exception:
        pass


def search_postgres(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    database_url = get_database_url()
    if not database_url:
        return []

    embedding = create_embedding(query)
    if embedding is None:
        return []

    try:
        with connect(database_url) as conn:
            register_vector(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, source, chunk_text,
                           1 - (embedding <=> %s) AS similarity
                    FROM document_chunks
                    ORDER BY embedding <-> %s
                    LIMIT %s
                    """,
                    (embedding, embedding, top_k),
                )
                rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "source": row[1],
                "score": float(row[3]),
                "snippet": row[2],
            }
            for row in rows
        ]
    except Exception:
        return []


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def chunk_document(content: str, chunk_size: int = 500) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", content) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) <= chunk_size:
            current = (current + " " + paragraph).strip()
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    return chunks or [content]


def load_default_documents() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for file_path in sorted(DATA_DIR.glob("*.txt")):
        for index, chunk in enumerate(chunk_document(file_path.read_text(encoding="utf-8"))):
            docs.append(
                {
                    "id": f"{file_path.stem}-{index + 1}",
                    "source": file_path.name,
                    "content": chunk,
                }
            )
    return docs


DOCUMENTS.extend(load_default_documents())
initialize_vector_database()


def extract_text_from_bytes(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()

    if extension in {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"}:
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return ""

    if extension == ".pdf":
        try:
            with PdfReader(BytesIO(content)) as reader:
                pages = []
                for page in reader.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
                return "\n".join(pages).strip()
        except Exception:
            return ""

    if extension in {".docx", ".pptx"}:
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                text_parts: list[str] = []
                for name in archive.namelist():
                    if name.endswith(".xml") and ("word/" in name or "ppt/slides/" in name):
                        xml_content = archive.read(name)
                        root = ET.fromstring(xml_content)
                        for element in root.iter():
                            if element.tag.rsplit("}", 1)[-1] == "t" and element.text:
                                text_parts.append(element.text)
                return " ".join(text_parts).strip()
        except Exception:
            return ""

    return ""


def clean_sentence(sentence: str) -> str:
    return re.sub(r"\s+", " ", sentence).strip()


def build_snippet(document_text: str, query_tokens: list[str], max_snippets: int = 3) -> list[str]:
    sentences = [clean_sentence(s) for s in re.split(r"(?<=[.!?])\s+", document_text) if s.strip()]
    scored: list[tuple[int, str]] = []

    for sentence in sentences:
        tokens = set(tokenize(sentence))
        score = sum(2 for token in query_tokens if token in tokens)
        if query_tokens and query_tokens[0] in sentence.lower():
            score += 1
        if score > 0:
            scored.append((score, sentence))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [sentence for _, sentence in scored[:max_snippets]]


def rank_documents(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return []

    pg_results = [
        result
        for result in search_postgres(query, top_k)
        if result["score"] >= MIN_VECTOR_SIMILARITY
    ]
    if pg_results:
        return [
            {
                "id": result["id"],
                "source": result["source"],
                "score": result["score"],
                "snippet": result["snippet"],
                "snippets": [result["snippet"]],
            }
            for result in pg_results
        ]

    search_tokens = [token for token in tokenize(query) if token not in SEARCH_STOPWORDS]
    if not search_tokens:
        return []

    scored_documents: list[dict[str, Any]] = []

    for document in DOCUMENTS:
        text = document["content"]
        tokens = tokenize(text)
        doc_counter = Counter(tokens)
        total_score = sum(doc_counter.get(token, 0) for token in search_tokens)

        distinct_hits = sum(1 for token in set(search_tokens) if token in set(tokens))
        if distinct_hits / len(set(search_tokens)) < 0.5:
            continue

        phrase_bonus = 3 if query.lower() in text.lower() else 0
        score = total_score * 2 + distinct_hits * 3 + phrase_bonus

        if score <= 0:
            continue

        snippet = build_snippet(text, search_tokens, max_snippets=2)
        scored_documents.append(
            {
                "id": document["id"],
                "source": document["source"],
                "score": score,
                "snippet": snippet[0] if snippet else text[:250],
                "snippets": snippet,
            }
        )

    return sorted(scored_documents, key=lambda item: item["score"], reverse=True)[:top_k]


def create_fallback_answer(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return "I could not find any matching content in the current document set. Try another query or upload more documents."

    context = "\n".join(
        result["snippet"] for result in results if result.get("snippet")
    )

    if not context:
        return "The document library does not currently contain a good match for that question."

    return (
        "Based on the relevant excerpts from the indexed documents, the answer is: "
        f"{context[:600]}"
        f"\n\nThis was derived from the following documents: {', '.join(result['source'] for result in results)}."
    )


def create_llm_answer(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return create_fallback_answer(query, results)

    client = get_openai_client()
    if client is None:
        return create_fallback_answer(query, results)

    try:
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        context = "\n\n".join(
            f"Source: {item['source']}\n{item['snippet']}" for item in results if item.get("snippet")
        )
        response = client.responses.create(
            model=deployment,
            input=[
                {
                    "role": "system",
                    "content": "Use only the provided source snippets to answer the question. Cite the source document names and keep the response grounded in the documents.",
                },
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nSource snippets:\n{context}",
                },
            ],
        )
        return response.output_text.strip() or create_fallback_answer(query, results)
    except Exception:
        return create_fallback_answer(query, results)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "documents": len(DOCUMENTS),
        "message": "UC07 document search backend is running",
    }


@app.get("/api/documents")
def list_documents() -> list[str]:
    return sorted({doc["source"] for doc in DOCUMENTS})


@app.post("/api/search")
def search_documents(payload: SearchRequest) -> dict[str, Any]:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    results = rank_documents(payload.query, payload.top_k)
    answer = create_llm_answer(payload.query, results)

    return {
        "query": payload.query,
        "answer": answer,
        "sources": [
            {
                "id": result["id"],
                "source": result["source"],
                "score": result["score"],
                "snippet": result["snippet"],
            }
            for result in results
        ],
    }


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected.")

    extension = Path(file.filename).suffix.lower()
    supported_types = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".pdf", ".docx", ".pptx"}
    if extension not in supported_types:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload .txt, .md, .pdf, .docx, or .pptx files.",
        )

    file_path = UPLOAD_DIR / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    text = extract_text_from_bytes(file.filename, content)
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="The uploaded file does not contain readable text content.",
        )

    chunks = list(chunk_document(text))
    for index, chunk in enumerate(chunks):
        DOCUMENTS.append(
            {
                "id": f"{file.filename}-{index + 1}",
                "source": file.filename,
                "content": chunk,
            }
        )

    store_document_chunks_in_postgres(file.filename, chunks)

    return {
        "message": "Document uploaded successfully.",
        "filename": file.filename,
        "documents": len(DOCUMENTS),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
