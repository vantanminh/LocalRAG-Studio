import datetime
import json as _json
import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
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

CHUNK_SIZE      = 1200
CHUNK_OVERLAP   = 200
TOP_K           = 8
UPLOAD_DIR      = Path("./uploads")
CHROMA_DIR      = "./chroma"
CHATS_DIR       = Path("./chats")
CONTEXT_WINDOW  = int(os.getenv("CONTEXT_WINDOW", "131072"))  # DeepSeek V4 Pro: 128K

SYSTEM_PROMPT = (
    "You are a RAG assistant. Answer only using the provided context. "
    "If the context does not contain enough information, say that the uploaded documents "
    "do not contain enough information to answer. Do not invent facts."
)

CHAT_SYSTEM_PROMPT = (
    "You are a helpful RAG assistant with access to the full conversation history. "
    "When document context is provided, use it to answer accurately. "
    "Be conversational and concise. If the context doesn't have enough information, say so honestly."
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


def load_chat_session(session_id: str) -> dict | None:
    path = CHATS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    return _json.loads(path.read_text(encoding="utf-8"))


def save_chat_session(session: dict):
    CHATS_DIR.mkdir(exist_ok=True)
    path = CHATS_DIR / f"{session['id']}.json"
    path.write_text(_json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="RAG Local")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/chat")
def chat_page():
    return FileResponse("static/chat.html")


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


# ── /ask/stream ───────────────────────────────────────────────────────────────

@app.post("/ask/stream")
def ask_stream(body: AskRequest):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    if collection.count() == 0:
        raise HTTPException(status_code=400, detail="No documents have been indexed yet.")

    def event_stream():
        def send(obj: dict) -> str:
            return f"data: {_json.dumps(obj, ensure_ascii=False)}\n\n"

        # Step 1: Embedding
        yield send({"type": "step", "step": "embedding", "status": "active", "message": "Đang mã hóa câu hỏi..."})
        try:
            q_embedding = embed_query(question)
        except Exception as e:
            yield send({"type": "error", "message": f"Embedding error: {e}"})
            return
        yield send({"type": "step", "step": "embedding", "status": "done", "message": "Mã hóa hoàn tất"})

        # Step 2: Retrieval
        yield send({"type": "step", "step": "retrieval", "status": "active", "message": "Đang tìm kiếm trong vector database..."})
        results = collection.query(
            query_embeddings=[q_embedding],
            n_results=min(TOP_K, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        if not docs:
            yield send({"type": "error", "message": "Không tìm thấy đoạn văn liên quan."})
            return

        yield send({"type": "step", "step": "retrieval", "status": "done", "message": f"Tìm thấy {len(docs)} đoạn văn liên quan"})

        chunks_data = [
            {
                "source": m["source"],
                "chunk_index": m["chunk_index"],
                "preview": d[:400] + ("…" if len(d) > 400 else ""),
                "score": round(1 - distances[i], 3),
            }
            for i, (d, m) in enumerate(zip(docs, metas))
        ]
        yield send({"type": "chunks", "chunks": chunks_data})

        # Step 3: Generating
        yield send({"type": "step", "step": "generating", "status": "active", "message": "Đang tạo câu trả lời..."})

        context_parts = [
            f"[Source: {m['source']}, chunk {m['chunk_index']}]\n{d}"
            for d, m in zip(docs, metas)
        ]
        context_block = "\n\n---\n\n".join(context_parts)
        user_message = f"Context:\n{context_block}\n\nQuestion: {question}"

        try:
            stream = llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                stream=True,
                extra_body={"thinking": {"type": "enabled"}},
            )
            thinking_started = False
            answering_started = False
            for chunk in stream:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None) or ""
                content = delta.content or ""
                if reasoning:
                    if not thinking_started:
                        thinking_started = True
                        yield send({"type": "thinking_start"})
                        yield send({"type": "step", "step": "generating", "status": "active", "message": "Đang suy nghĩ..."})
                    yield send({"type": "thinking_token", "content": reasoning})
                if content:
                    if not answering_started:
                        answering_started = True
                        yield send({"type": "thinking_end"})
                        yield send({"type": "step", "step": "generating", "status": "active", "message": "Đang viết câu trả lời..."})
                    yield send({"type": "token", "content": content})
        except Exception as e:
            yield send({"type": "error", "message": f"LLM error: {e}"})
            return

        yield send({"type": "step", "step": "generating", "status": "done", "message": "Hoàn tất"})

        seen: set = set()
        sources = []
        for m in metas:
            key = (m["source"], m["chunk_index"])
            if key not in seen:
                seen.add(key)
                sources.append({"source": m["source"], "chunk_index": m["chunk_index"]})

        yield send({"type": "done", "sources": sources})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── /chat/sessions ────────────────────────────────────────────────────────────

@app.get("/chat/sessions")
def list_chat_sessions():
    CHATS_DIR.mkdir(exist_ok=True)
    sessions = []
    for f in sorted(CHATS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "id": data["id"],
                "title": data.get("title", "Untitled"),
                "created_at": data.get("created_at"),
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            pass
    return {"sessions": sessions}


@app.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str):
    session = load_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@app.delete("/chat/sessions/{session_id}")
def delete_chat_session(session_id: str):
    path = CHATS_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found.")
    path.unlink()
    return {"ok": True}


# ── /chat/stream ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


@app.post("/chat/stream")
def chat_stream(body: ChatRequest):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    session_id = body.session_id
    session = load_chat_session(session_id) if session_id else None
    if not session:
        session_id = uuid.uuid4().hex
        session = {
            "id": session_id,
            "title": message[:60],
            "created_at": datetime.datetime.now().isoformat(),
            "messages": [],
        }

    def event_stream():
        def send(obj: dict) -> str:
            return f"data: {_json.dumps(obj, ensure_ascii=False)}\n\n"

        yield send({"type": "session", "session_id": session_id})

        # RAG retrieval (skip if no docs)
        sources: list = []
        if collection.count() > 0:
            yield send({"type": "step", "message": "Đang tìm kiếm tài liệu liên quan..."})
            try:
                q_embedding = embed_query(message)
            except Exception as e:
                yield send({"type": "error", "message": f"Embedding error: {e}"})
                return

            results = collection.query(
                query_embeddings=[q_embedding],
                n_results=min(TOP_K, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0]

            yield send({"type": "step", "message": f"Tìm thấy {len(docs)} đoạn văn liên quan"})

            chunks_data = [
                {
                    "source": m["source"],
                    "chunk_index": m["chunk_index"],
                    "preview": d[:400] + ("…" if len(d) > 400 else ""),
                    "score": round(1 - distances[i], 3),
                }
                for i, (d, m) in enumerate(zip(docs, metas))
            ]
            yield send({"type": "chunks", "chunks": chunks_data})

            context_parts = [
                f"[Source: {m['source']}, chunk {m['chunk_index']}]\n{d}"
                for d, m in zip(docs, metas)
            ]
            user_content = f"[Document context]\n{chr(10).join(context_parts)}\n\n[Question]\n{message}"

            seen_src: set = set()
            for m in metas:
                key = (m["source"], m["chunk_index"])
                if key not in seen_src:
                    seen_src.add(key)
                    sources.append({"source": m["source"], "chunk_index": m["chunk_index"]})
        else:
            user_content = message

        # Build multi-turn messages
        history = [{"role": m["role"], "content": m["content"]} for m in session["messages"]]
        messages_to_send = (
            [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
            + history
            + [{"role": "user", "content": user_content}]
        )

        yield send({"type": "step", "message": "Đang tạo câu trả lời..."})

        full_answer = ""
        full_thinking = ""
        usage = None

        try:
            stream = llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages_to_send,
                stream=True,
                stream_options={"include_usage": True},
                extra_body={"thinking": {"type": "enabled"}},
            )
            thinking_started = False
            answering_started = False
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None) or ""
                content = delta.content or ""
                if reasoning:
                    full_thinking += reasoning
                    if not thinking_started:
                        thinking_started = True
                        yield send({"type": "thinking_start"})
                        yield send({"type": "step", "message": "Đang suy nghĩ..."})
                    yield send({"type": "thinking_token", "content": reasoning})
                if content:
                    full_answer += content
                    if not answering_started:
                        answering_started = True
                        if thinking_started:
                            yield send({"type": "thinking_end"})
                        yield send({"type": "step", "message": "Đang viết câu trả lời..."})
                    yield send({"type": "token", "content": content})
        except Exception as e:
            yield send({"type": "error", "message": f"LLM error: {e}"})
            return

        now = datetime.datetime.now().isoformat()
        session["messages"].append({"role": "user", "content": message, "timestamp": now})
        session["messages"].append({
            "role": "assistant",
            "content": full_answer,
            "thinking": full_thinking,
            "sources": sources,
            "timestamp": now,
            "usage": usage,
        })
        session["last_usage"] = usage
        save_chat_session(session)

        yield send({
            "type": "done",
            "sources": sources,
            "session_id": session_id,
            "usage": usage,
            "context_window": CONTEXT_WINDOW,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
