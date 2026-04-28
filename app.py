import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

# ── config ────────────────────────────────────────────────────────────────────

OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
EMBED_MODEL         = os.getenv("EMBED_MODEL", "qwen/qwen3-embedding-8b")

DEEPSEEK_API_KEY    = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL   = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL           = os.getenv("LLM_MODEL", "deepseek-chat")

CHUNK_SIZE    = 1200
CHUNK_OVERLAP = 200
TOP_K         = 8
UPLOAD_DIR    = Path("./uploads")
CHROMA_DIR    = "./chroma"

SYSTEM_PROMPT = (
    "You are a RAG assistant. Answer only using the provided context. "
    "If the context does not contain enough information, say that the uploaded documents "
    "do not contain enough information to answer. Do not invent facts."
)

# ── clients ───────────────────────────────────────────────────────────────────

if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is not set. Check your .env file.")
if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY is not set. Check your .env file.")

from openai import OpenAI

# Embedding via OpenRouter
embed_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)

# Chat via DeepSeek
llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

import chromadb

chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

collection = chroma_client.get_or_create_collection(
    name="documents",
    metadata={"hnsw:space": "cosine"},
)

# ── helpers ───────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c.strip() for c in chunks if c.strip()]


def extract_text(file_path: Path, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".docx":
        from docx import Document
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def embed_texts(texts: list[str]) -> list[list[float]]:
    import httpx, json as _json
    payload = {"model": EMBED_MODEL, "input": texts}
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    r = httpx.post(
        f"{OPENROUTER_BASE_URL}/embeddings",
        headers=headers,
        json=payload,
        timeout=60,
    )
    body = r.json()
    if "data" not in body or not body["data"]:
        raise ValueError(f"OpenRouter embedding error (HTTP {r.status_code}): {_json.dumps(body)}")
    return [item["embedding"] for item in body["data"]]


def embed_query(query: str) -> list[float]:
    return embed_texts([query])[0]




# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="RAG Local")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


# ── /upload ───────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: .txt, .pdf, .docx",
        )

    UPLOAD_DIR.mkdir(exist_ok=True)
    save_path = UPLOAD_DIR / file.filename
    save_path.write_bytes(await file.read())

    try:
        raw_text = extract_text(save_path, file.filename)
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not extract text: {e}")

    text = clean_text(raw_text)
    if not text:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No text could be extracted from the uploaded file.")

    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=422, detail="Text extracted but no usable chunks produced.")

    try:
        embeddings = embed_texts(chunks)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding API error: {e}")

    ids = [f"{file.filename}__chunk_{i}__{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
    metadatas = [{"source": file.filename, "chunk_index": i} for i in range(len(chunks))]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )

    return {"success": True, "filename": file.filename, "chunks": len(chunks)}


# ── /files ───────────────────────────────────────────────────────────────────

@app.get("/files")
def list_files():
    if collection.count() == 0:
        return {"files": []}
    results = collection.get(include=["metadatas"])
    seen: set[str] = set()
    files: list[str] = []
    for m in results["metadatas"]:
        src = m["source"]
        if src not in seen:
            seen.add(src)
            files.append(src)
    return {"files": sorted(files)}


# ── /ask ──────────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def ask_question(body: AskRequest):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    if collection.count() == 0:
        raise HTTPException(
            status_code=400,
            detail="No documents have been indexed yet. Please upload a document first.",
        )

    try:
        q_embedding = embed_query(question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding API error: {e}")

    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(TOP_K, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]

    if not docs:
        raise HTTPException(status_code=404, detail="No relevant chunks found.")

    context_parts = [
        f"[Source: {m['source']}, chunk {m['chunk_index']}]\n{d}"
        for d, m in zip(docs, metas)
    ]
    context_block = "\n\n---\n\n".join(context_parts)
    user_message = f"Context:\n{context_block}\n\nQuestion: {question}"

    try:
        response = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        answer = response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")

    seen = set()
    sources = []
    for m in metas:
        key = (m["source"], m["chunk_index"])
        if key not in seen:
            seen.add(key)
            sources.append({"source": m["source"], "chunk_index": m["chunk_index"]})

    return {"answer": answer, "sources": sources}
