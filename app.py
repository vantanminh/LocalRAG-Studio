import datetime
import json as _json
import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
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
PROJECTS_DIR    = Path("./projects")
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

AGENTIC_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to a document search tool. "
    "When answering questions, use the search_documents tool to find relevant information from uploaded documents. "
    "You can call the tool multiple times with different queries to gather comprehensive information. "
    "Only give your final answer after you have gathered enough information. "
    "If the documents don't contain relevant information after searching, say so honestly."
)

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "Search through uploaded documents to find relevant information. "
            "Returns the most relevant document chunks for the given query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant information",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of chunks to retrieve (1–8, default 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 8,
                },
            },
            "required": ["query"],
        },
    },
}

MAX_TOOL_CALLS = 5

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


def execute_search(query: str, top_k: int = 5, project_id: str | None = None) -> dict:
    """Run vector search and return chunks data + full context text."""
    try:
        q_embedding = embed_query(query)
    except Exception as e:
        return {"error": str(e), "chunks": [], "context": "", "metas": []}

    total = count_filtered(project_id)
    if total == 0:
        return {"error": None, "chunks": [], "context": "", "metas": []}

    k = min(max(1, top_k), 8, total)
    query_kwargs: dict = dict(
        query_embeddings=[q_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    if project_id is not None:
        query_kwargs["where"] = {"project_id": project_id}

    results = collection.query(**query_kwargs)
    docs  = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    chunks_data = [
        {
            "source": m["source"],
            "chunk_index": m["chunk_index"],
            "preview": d[:400] + ("…" if len(d) > 400 else ""),
            "score": round(1 - dists[i], 3),
        }
        for i, (d, m) in enumerate(zip(docs, metas))
    ]
    context_parts = [
        f"[Source: {m['source']}, chunk {m['chunk_index']}]\n{d}"
        for d, m in zip(docs, metas)
    ]
    return {
        "error": None,
        "chunks": chunks_data,
        "context": "\n\n---\n\n".join(context_parts),
        "metas": metas,
    }


def load_chat_session(session_id: str) -> dict | None:
    path = CHATS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    return _json.loads(path.read_text(encoding="utf-8"))


def save_chat_session(session: dict):
    CHATS_DIR.mkdir(exist_ok=True)
    path = CHATS_DIR / f"{session['id']}.json"
    path.write_text(_json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(project_id: str) -> dict | None:
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return None
    return _json.loads(path.read_text(encoding="utf-8"))


def save_project(project: dict):
    PROJECTS_DIR.mkdir(exist_ok=True)
    path = PROJECTS_DIR / f"{project['id']}.json"
    path.write_text(_json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")


def count_filtered(project_id: str | None) -> int:
    if project_id is None:
        return collection.count()
    try:
        result = collection.get(where={"project_id": project_id}, include=[])
        return len(result["ids"])
    except Exception:
        return 0


def build_chat_histories(session: dict) -> tuple[list[dict], list[dict]]:
    tool_history = []
    thinking_history = []

    for m in session.get("messages", []):
        msg: dict = {"role": m["role"], "content": m["content"]}
        tool_history.append(msg)

        thinking_msg = dict(msg)
        if m["role"] == "assistant":
            reasoning_content = m.get("reasoning_content") or m.get("thinking")
            if reasoning_content:
                thinking_msg["reasoning_content"] = reasoning_content
        thinking_history.append(thinking_msg)

    return tool_history, thinking_history


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


async def _index_file(file_bytes: bytes, filename: str, project_id: str | None = None) -> int:
    """Index file bytes into ChromaDB. Returns chunk count."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: .txt, .pdf, .docx",
        )

    UPLOAD_DIR.mkdir(exist_ok=True)
    save_path = UPLOAD_DIR / filename
    save_path.write_bytes(file_bytes)

    try:
        raw_text = extract_text(save_path, filename)
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

    # If project_id provided: remove old chunks for this file in this project first (upsert)
    if project_id:
        try:
            collection.delete(where={"project_id": project_id, "source": filename})
        except Exception:
            pass

    ids = [f"{filename}__chunk_{i}__{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
    metadatas: list[dict] = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]
    if project_id:
        for m in metadatas:
            m["project_id"] = project_id

    collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
    return len(chunks)


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), project_id: str = Form(None)):
    n_chunks = await _index_file(await file.read(), file.filename, project_id or None)

    if project_id:
        proj = load_project(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found.")
        proj["files"] = [f for f in proj["files"] if f["filename"] != file.filename]
        proj["files"].append({
            "filename": file.filename,
            "uploaded_at": datetime.datetime.now().isoformat(),
            "chunks": n_chunks,
        })
        save_project(proj)

    return {"success": True, "filename": file.filename, "chunks": n_chunks}


# ── /files ───────────────────────────────────────────────────────────────────

@app.get("/files")
def list_files(project_id: str | None = Query(None)):
    get_kwargs: dict = dict(include=["metadatas"])
    if project_id is not None:
        get_kwargs["where"] = {"project_id": project_id}
    if count_filtered(project_id) == 0:
        return {"files": []}
    results = collection.get(**get_kwargs)
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
def list_chat_sessions(project_id: str | None = Query(None)):
    CHATS_DIR.mkdir(exist_ok=True)
    sessions = []
    for f in sorted(CHATS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
            if project_id is not None and data.get("project_id") != project_id:
                continue
            sessions.append({
                "id": data["id"],
                "title": data.get("title", "Untitled"),
                "created_at": data.get("created_at"),
                "message_count": len(data.get("messages", [])),
                "project_id": data.get("project_id"),
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
    project_id: str | None = None


@app.post("/chat/stream")
def chat_stream(body: ChatRequest):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    project_id = body.project_id or None
    session_id = body.session_id
    session = load_chat_session(session_id) if session_id else None
    if not session:
        session_id = uuid.uuid4().hex
        session = {
            "id": session_id,
            "title": message[:60],
            "created_at": datetime.datetime.now().isoformat(),
            "messages": [],
            "project_id": project_id,
        }

    has_docs = count_filtered(project_id) > 0

    def event_stream():
        def send(obj: dict) -> str:
            return f"data: {_json.dumps(obj, ensure_ascii=False)}\n\n"

        yield send({"type": "session", "session_id": session_id})

        # Keep two histories:
        # - tool_history is plain OpenAI chat history for the tool loop.
        # - thinking_history includes DeepSeek reasoning_content for thinking-mode turns.
        tool_history, thinking_history = build_chat_histories(session)

        all_sources:       list = []
        seen_sources:      set  = set()
        collected_context: list = []   # context blocks from all searches
        usage = None

        yield send({"type": "step", "message": "AI đang phân tích câu hỏi..."})

        # ── Phase 1: Agentic tool-use loop ─────────────────────────────────────
        if has_docs:
            tool_messages = (
                [{"role": "system", "content": AGENTIC_SYSTEM_PROMPT}]
                + tool_history
                + [{"role": "user", "content": message}]
            )
            tool_call_count = 0

            while tool_call_count < MAX_TOOL_CALLS:
                yield send({
                    "type": "activity",
                    "message": (
                        "AI đang chọn truy vấn tìm kiếm..."
                        if tool_call_count == 0
                        else "AI đang đọc kết quả và cân nhắc có cần tìm thêm..."
                    ),
                })
                try:
                    stream = llm_client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=tool_messages,
                        tools=[SEARCH_TOOL],
                        tool_choice="auto",
                        stream=True,
                        extra_body={"thinking": {"type": "enabled"}},
                    )
                except Exception as e:
                    yield send({"type": "error", "message": f"LLM error: {e}"})
                    return

                tool_call_acc: dict[int, dict] = {}
                current_content = ""
                current_reasoning = ""
                progress_index = 0
                progress_messages = [
                    "Đang lập kế hoạch tra cứu...",
                    "Đang đối chiếu câu hỏi với tài liệu...",
                    "Đang kiểm tra các nguồn có liên quan...",
                    "Đang chuẩn bị bước tiếp theo...",
                ]

                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    reasoning = getattr(delta, "reasoning_content", None) or ""
                    if reasoning:
                        current_reasoning += reasoning
                        next_index = min(len(current_reasoning) // 700, len(progress_messages) - 1)
                        if next_index >= progress_index:
                            yield send({"type": "activity", "message": progress_messages[progress_index]})
                            progress_index = next_index + 1

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_call_acc:
                                tool_call_acc[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc.id:
                                tool_call_acc[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_call_acc[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_call_acc[idx]["arguments"] += tc.function.arguments
                        continue

                    if delta.content:
                        current_content += delta.content

                if not tool_call_acc:
                    # AI decided no search needed — stop tool loop
                    break

                # Append assistant turn with tool_calls
                assistant_tool_message = {
                    "role":    "assistant",
                    "content": current_content or None,
                    "tool_calls": [
                        {
                            "id":   tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in tool_call_acc.values()
                    ],
                }
                if current_reasoning:
                    assistant_tool_message["reasoning_content"] = current_reasoning
                tool_messages.append(assistant_tool_message)

                # Execute tools and collect context
                for tc in tool_call_acc.values():
                    tool_call_count += 1

                    if tc["name"] != "search_documents":
                        tool_messages.append({
                            "role": "tool", "tool_call_id": tc["id"], "content": "Unknown tool.",
                        })
                        continue

                    try:
                        args  = _json.loads(tc["arguments"])
                        query = args.get("query", "").strip()
                        top_k = int(args.get("top_k", 5))
                    except Exception:
                        query, top_k = "", 5

                    yield send({"type": "tool_call", "query": query})

                    if query:
                        yield send({"type": "activity", "message": "Đang mã hóa truy vấn và tìm trong vector database..."})
                        result = execute_search(query, top_k, project_id)
                        yield send({"type": "chunks", "chunks": result["chunks"], "query": query})
                        yield send({
                            "type": "activity",
                            "message": f"Đã tìm thấy {len(result['chunks'])} đoạn, đang đưa vào ngữ cảnh...",
                        })

                        for m in result["metas"]:
                            key = (m["source"], m["chunk_index"])
                            if key not in seen_sources:
                                seen_sources.add(key)
                                all_sources.append({"source": m["source"], "chunk_index": m["chunk_index"]})

                        if not result["error"]:
                            collected_context.append(result["context"])
                        tool_content = result["context"] if not result["error"] else f"Search error: {result['error']}"
                    else:
                        tool_content = "Error: empty query provided."

                    tool_messages.append({
                        "role": "tool", "tool_call_id": tc["id"], "content": tool_content,
                    })

                yield send({"type": "step", "message": "Đang phân tích kết quả tìm kiếm..."})

        # ── Phase 2: Final synthesis (thinking enabled, clean message thread) ──
        if collected_context:
            context_block = "\n\n---\n\n".join(collected_context)
            synthesis_user_content = (
                f"[Document context from searches]\n{context_block}\n\n"
                f"[Question]\n{message}"
            )
        else:
            synthesis_user_content = message

        synthesis_messages = (
            [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
            + thinking_history
            + [{"role": "user", "content": synthesis_user_content}]
        )

        yield send({"type": "step", "message": "Đang tổng hợp câu trả lời..."})

        full_answer   = ""
        full_thinking = ""
        thinking_started  = False
        answering_started = False

        try:
            stream = llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=synthesis_messages,
                stream=True,
                stream_options={"include_usage": True},
                extra_body={"thinking": {"type": "enabled"}},
            )
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = {
                        "prompt_tokens":     chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens":      chunk.usage.total_tokens,
                    }
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                reasoning = getattr(delta, "reasoning_content", None) or ""
                content   = delta.content or ""

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

        # ── Persist session ────────────────────────────────────────────────────
        now = datetime.datetime.now().isoformat()
        session["messages"].append({"role": "user", "content": message, "timestamp": now})
        session["messages"].append({
            "role":             "assistant",
            "content":          full_answer,
            "thinking":         full_thinking,   # for display in UI
            "reasoning_content": full_thinking,  # for DeepSeek multi-turn pass-back
            "sources":          all_sources,
            "timestamp":        now,
            "usage":            usage,
        })
        session["last_usage"] = usage
        save_chat_session(session)

        yield send({
            "type":           "done",
            "sources":        all_sources,
            "session_id":     session_id,
            "usage":          usage,
            "context_window": CONTEXT_WINDOW,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── /projects ─────────────────────────────────────────────────────────────────

class ProjectCreateRequest(BaseModel):
    name: str

class ProjectRenameRequest(BaseModel):
    name: str


@app.get("/projects")
def list_projects():
    PROJECTS_DIR.mkdir(exist_ok=True)
    projects = []
    for f in sorted(PROJECTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
            projects.append({
                "id": data["id"],
                "name": data.get("name", "Untitled"),
                "created_at": data.get("created_at"),
                "file_count": len(data.get("files", [])),
            })
        except Exception:
            pass
    return {"projects": projects}


@app.post("/projects")
def create_project(body: ProjectCreateRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name must not be empty.")
    project_id = uuid.uuid4().hex
    project = {
        "id": project_id,
        "name": name,
        "created_at": datetime.datetime.now().isoformat(),
        "files": [],
    }
    save_project(project)
    return project


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    proj = load_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    return proj


@app.patch("/projects/{project_id}")
def rename_project(project_id: str, body: ProjectRenameRequest):
    proj = load_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name must not be empty.")
    proj["name"] = name
    save_project(proj)
    return proj


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    proj = load_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    try:
        collection.delete(where={"project_id": project_id})
    except Exception:
        pass

    CHATS_DIR.mkdir(exist_ok=True)
    for f in CHATS_DIR.glob("*.json"):
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
            if data.get("project_id") == project_id:
                f.unlink(missing_ok=True)
        except Exception:
            pass

    (PROJECTS_DIR / f"{project_id}.json").unlink(missing_ok=True)
    return {"ok": True}


@app.post("/projects/{project_id}/files")
async def upload_project_file(project_id: str, file: UploadFile = File(...)):
    proj = load_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    n_chunks = await _index_file(await file.read(), file.filename, project_id)

    proj["files"] = [f for f in proj["files"] if f["filename"] != file.filename]
    proj["files"].append({
        "filename": file.filename,
        "uploaded_at": datetime.datetime.now().isoformat(),
        "chunks": n_chunks,
    })
    save_project(proj)
    return {"success": True, "filename": file.filename, "chunks": n_chunks}


@app.delete("/projects/{project_id}/files/{filename:path}")
def delete_project_file(project_id: str, filename: str):
    proj = load_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    if not any(f["filename"] == filename for f in proj.get("files", [])):
        raise HTTPException(status_code=404, detail="File not found in project.")

    try:
        collection.delete(where={"project_id": project_id, "source": filename})
    except Exception:
        pass

    proj["files"] = [f for f in proj["files"] if f["filename"] != filename]
    save_project(proj)
    return {"ok": True}


# ── HTML pages for projects ───────────────────────────────────────────────────

@app.get("/projects-page")
def projects_page():
    return FileResponse("static/projects.html")


@app.get("/p/{project_id}")
def project_detail_page(project_id: str):
    return FileResponse("static/project_detail.html")
