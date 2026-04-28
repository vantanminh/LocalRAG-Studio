# RAG Qwen Local

A local-first Retrieval-Augmented Generation (RAG) web app for uploading documents, indexing them with embeddings, and chatting with an LLM using the indexed content as context.

This project currently uses:

- FastAPI for the backend.
- ChromaDB for local vector storage.
- OpenRouter-compatible embeddings.
- DeepSeek-compatible chat completions.
- A lightweight HTML/CSS/JavaScript frontend.

## Features

- Upload and index `.txt`, `.pdf`, and `.docx` files.
- Paste raw text and index it as a document.
- Ask one-off RAG questions with source chunks.
- Use a chat UI with saved local sessions.
- Create project-specific document collections.
- Stream answer tokens, reasoning/activity updates, retrieval steps, and source previews.
- Switch between Pro and Flash model tiers through environment variables.

## Privacy Notes

Runtime data is intentionally ignored by Git:

- `.env`
- `uploads/`
- `chroma/`
- `chats/`
- `projects/`

These folders may contain API keys, uploaded documents, vector indexes, private chat history, or project metadata. Keep them local unless you intentionally export sanitized examples.

## Requirements

- Python 3.11 or newer
- OpenRouter API key for embeddings
- DeepSeek API key or a compatible OpenAI-style chat endpoint

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set your keys:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

You can also adjust model names:

```env
EMBED_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free
LLM_MODEL_PRO=deepseek-v4-pro
LLM_MODEL_FLASH=deepseek-v4-flash
DEFAULT_LLM_TIER=pro
```

## Run

```bash
uvicorn app:app --reload
```

Then open:

- Main RAG page: <http://127.0.0.1:8000/>
- Chat page: <http://127.0.0.1:8000/chat>
- Projects page: <http://127.0.0.1:8000/projects-page>

## Project Structure

```text
.
├── app.py                 # FastAPI app, document indexing, RAG, chat, projects
├── static/                # Frontend pages, styles, and JavaScript
├── requirements.txt       # Python dependencies
├── .env.example           # Example environment config
├── uploads/               # Local uploaded documents, ignored
├── chroma/                # Local ChromaDB data, ignored
├── chats/                 # Local chat sessions, ignored
└── projects/              # Local project metadata, ignored
```

## API Overview

- `POST /upload` uploads and indexes a document.
- `GET /files` lists indexed files.
- `POST /ask` asks a one-off RAG question.
- `POST /ask/stream` streams a one-off RAG answer.
- `GET /chat/sessions` lists chat sessions.
- `POST /chat/stream` streams a chat response.
- `GET /projects` lists projects.
- `POST /projects` creates a project.
- `POST /projects/{project_id}/files` uploads a file into a project.

## License

MIT License. See [LICENSE](./LICENSE).

---

# RAG Qwen Local - Tieng Viet

Day la ung dung web RAG chay local-first: ban co the upload tai lieu, tao embedding, luu vector tren may bang ChromaDB, roi hoi dap voi LLM dua tren noi dung da index.

Du an hien dung:

- FastAPI cho backend.
- ChromaDB de luu vector local.
- Embedding endpoint tu OpenRouter hoac endpoint tuong thich.
- DeepSeek hoac chat endpoint tuong thich OpenAI.
- Frontend HTML/CSS/JavaScript gon nhe.

## Tinh Nang

- Upload va index file `.txt`, `.pdf`, `.docx`.
- Dan van ban truc tiep va index thanh tai lieu.
- Hoi dap RAG mot lan kem cac doan nguon.
- Giao dien chat co luu session local.
- Tao project rieng de gom tai lieu theo ngu canh.
- Stream token cau tra loi, qua trinh suy luan/hoat dong, buoc truy xuat va preview nguon.
- Chon model Pro hoac Flash qua bien moi truong.

## Ghi Chu Ve Rieng Tu

Du lieu runtime da duoc dua vao `.gitignore`:

- `.env`
- `uploads/`
- `chroma/`
- `chats/`
- `projects/`

Nhung thu muc nay co the chua API key, tai lieu upload, vector index, lich su chat rieng tu, hoac metadata project. Khong nen commit chung len GitHub tru khi ban da sanitize va co chu dich chia se.

## Yeu Cau

- Python 3.11 tro len
- API key OpenRouter cho embedding
- API key DeepSeek hoac endpoint chat tuong thich OpenAI

## Cai Dat

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Mo file `.env` va dien API key:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

Co the doi model trong `.env`:

```env
EMBED_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free
LLM_MODEL_PRO=deepseek-v4-pro
LLM_MODEL_FLASH=deepseek-v4-flash
DEFAULT_LLM_TIER=pro
```

## Chay Ung Dung

```bash
uvicorn app:app --reload
```

Sau do mo:

- Trang RAG chinh: <http://127.0.0.1:8000/>
- Trang chat: <http://127.0.0.1:8000/chat>
- Trang projects: <http://127.0.0.1:8000/projects-page>

## Cau Truc Du An

```text
.
├── app.py                 # FastAPI app, index tai lieu, RAG, chat, projects
├── static/                # Frontend, CSS va JavaScript
├── requirements.txt       # Thu vien Python
├── .env.example           # Cau hinh moi truong mau
├── uploads/               # Tai lieu upload local, bi ignore
├── chroma/                # Du lieu ChromaDB local, bi ignore
├── chats/                 # Lich su chat local, bi ignore
└── projects/              # Metadata project local, bi ignore
```

## Tong Quan API

- `POST /upload` upload va index tai lieu.
- `GET /files` liet ke file da index.
- `POST /ask` hoi dap RAG mot lan.
- `POST /ask/stream` stream cau tra loi RAG mot lan.
- `GET /chat/sessions` liet ke session chat.
- `POST /chat/stream` stream phan hoi chat.
- `GET /projects` liet ke project.
- `POST /projects` tao project.
- `POST /projects/{project_id}/files` upload file vao project.

## License

MIT License. Xem [LICENSE](./LICENSE).
