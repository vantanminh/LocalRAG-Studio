# Security Policy

Thank you for helping keep this project and its users safe. This project is a local-first RAG application, but it can still process sensitive files, chat history, API keys, vector databases, and model responses. Please treat security and privacy issues seriously.

## Supported Versions

The project is currently in early open-source development. Security fixes are provided for the default branch only.

| Version | Supported |
| --- | --- |
| `main` / `master` | Yes |
| Older commits, forks, or local modifications | Best effort only |

## Reporting a Vulnerability

Please do not open a public issue for suspected vulnerabilities.

Report security issues privately by contacting the maintainer through one of these channels:

- GitHub Security Advisory, if enabled for the repository.
- A private email address listed in the repository profile or README.
- A private GitHub discussion or direct contact channel, if one is provided.

If no private channel is available yet, open a minimal public issue that says only:

```text
I would like to report a security vulnerability. Please provide a private contact channel.
```

Do not include exploit details, API keys, private documents, chat logs, screenshots containing secrets, or proof-of-concept payloads in a public issue.

## What To Include

When reporting a vulnerability privately, include as much of the following as you can:

- A short description of the issue.
- Affected files, endpoints, or UI flows.
- Steps to reproduce.
- Expected behavior and actual behavior.
- Impact assessment, such as data exposure, key leakage, unauthorized file access, prompt injection, denial of service, or remote code execution.
- Environment details: operating system, Python version, browser, model provider, and whether the app is exposed to a network.
- Logs or screenshots with secrets redacted.
- Suggested fix, if you have one.

## Expected Response

The maintainer will aim to:

- Acknowledge receipt within 7 days.
- Confirm whether the report is valid within 14 days when possible.
- Provide a fix or mitigation plan based on severity and available maintainer time.
- Credit the reporter if requested and if disclosure is coordinated responsibly.

This is a small open-source project, so timelines may vary. Responsible reports are still appreciated and will be handled with care.

## Disclosure Policy

Please allow reasonable time for a fix before public disclosure.

Recommended disclosure process:

1. Report privately.
2. Wait for acknowledgement.
3. Coordinate reproduction details and severity.
4. Allow time for a patch or mitigation.
5. Publish details only after a fix is available or after coordinated disclosure is agreed.

Public disclosure without coordination may put users' documents, chat history, API keys, or local files at risk.

## Security Scope

In scope:

- Exposure of API keys or secrets.
- Unauthorized access to uploaded files.
- Unauthorized access to chat sessions or project metadata.
- Path traversal in upload, download, delete, or project file operations.
- Unsafe handling of `.txt`, `.pdf`, or `.docx` files.
- Stored or reflected cross-site scripting in the web UI.
- Prompt injection risks that cause unintended disclosure of private context.
- Accidental inclusion of private runtime data in Git.
- Dependency vulnerabilities that affect this app in a realistic deployment.
- Denial-of-service vectors caused by unbounded file size, chunking, token usage, or request volume.

Out of scope unless they produce a realistic security impact:

- Cosmetic UI bugs.
- Model hallucinations that do not expose private data or bypass controls.
- Issues requiring full local machine compromise before attacking the app.
- Vulnerabilities in third-party model providers, unless this app mishandles provider responses.
- Attacks against deliberately exposed development servers without any additional app-specific weakness.

## Sensitive Data

This project may create or use the following sensitive local data:

- `.env` containing API keys.
- `uploads/` containing user documents.
- `chroma/` containing vector database files and embedded document chunks.
- `chats/` containing saved conversations.
- `projects/` containing project metadata.
- Browser caches or local logs created during development.

These paths must not be committed to Git. They are included in `.gitignore` by default.

Before publishing, run:

```bash
git status --short --ignored
git ls-files chats projects uploads chroma .env __pycache__
git rev-list --objects --all | grep -E 'chats/|projects/|uploads/|chroma/|\.env$|__pycache__'
```

On Windows PowerShell:

```powershell
git status --short --ignored
git ls-files chats projects uploads chroma .env __pycache__
git rev-list --objects --all | Select-String -Pattern 'chats/|projects/|uploads/|chroma/|\.env$|__pycache__'
```

The `git ls-files` and `git rev-list` checks should not show private runtime data.

## API Keys And Environment Variables

Never commit real API keys.

Use `.env.example` for placeholders only:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

Recommended practices:

- Use separate development keys from production keys.
- Rotate keys immediately if they are committed, shared, logged, or displayed in screenshots.
- Restrict provider keys by budget, organization, allowed models, or allowed origins when your provider supports it.
- Avoid printing request headers, API keys, or raw provider payloads in logs.
- Do not paste private keys into chat prompts, issues, screenshots, or bug reports.

## Running The App Safely

By default, run the app on localhost:

```bash
uvicorn app:app --reload
```

Avoid exposing the development server directly to the public internet.

If you deploy or share it on a network:

- Put it behind authentication.
- Use HTTPS.
- Set upload size limits at the reverse proxy or application layer.
- Restrict allowed file types.
- Store runtime data outside the Git checkout.
- Back up and encrypt sensitive data when appropriate.
- Use per-user storage isolation if multiple users will access the same instance.
- Review CORS, cookies, reverse proxy headers, and host binding.

## Uploaded Documents

Uploaded files may contain confidential, copyrighted, personal, or regulated information.

Recommendations:

- Upload only documents you are allowed to process.
- Do not share `uploads/` or `chroma/` unless the contents are sanitized.
- Delete local runtime data before publishing demos or screenshots.
- Consider adding malware scanning if accepting files from untrusted users.
- Consider file size limits to prevent accidental or malicious resource exhaustion.

## Vector Database Privacy

The ChromaDB directory may contain text chunks or embeddings derived from uploaded documents. Even if raw files are deleted, the vector database can still reveal information about the documents.

To fully remove local indexed content, delete both:

```bash
uploads/
chroma/
```

If project and chat history should also be removed, delete:

```bash
chats/
projects/
```

## Prompt Injection And Model Output

RAG applications are vulnerable to prompt injection in uploaded documents. A malicious document can instruct the model to ignore rules, reveal hidden context, or produce unsafe output.

Current mitigations should include:

- Treat uploaded document text as untrusted input.
- Keep system prompts separate from retrieved document context.
- Do not expose API keys, filesystem paths, environment variables, or server internals to the model.
- Avoid giving the model tools that can modify files, call private endpoints, or execute commands unless strong controls are added.
- Display sources so users can inspect which document chunks influenced an answer.

Model responses should not be treated as authoritative security decisions.

## Frontend Security

The frontend renders model output and document-derived text. To reduce XSS risk:

- Escape user-controlled text before injecting it into HTML.
- Sanitize markdown output before rendering if untrusted content is allowed.
- Avoid inserting raw model output with `innerHTML` unless it is sanitized.
- Keep third-party browser libraries pinned or integrity-protected when possible.

If this app becomes multi-user or internet-facing, markdown sanitization and Content Security Policy should be reviewed carefully.

## Dependency Security

Install dependencies from `requirements.txt` in a virtual environment.

Recommended checks:

```bash
python -m pip install --upgrade pip
python -m pip list --outdated
python -m pip audit
```

If `pip-audit` is not installed:

```bash
python -m pip install pip-audit
python -m pip audit
```

Review dependency updates before merging because model SDKs, vector databases, PDF parsers, and document parsers can change behavior.

## Git History Cleanup

If private files were accidentally committed but not pushed:

```bash
git rm -r --cached --ignore-unmatch chats projects uploads chroma .env __pycache__
git commit -m "Remove private runtime data"
git filter-branch --force --index-filter "git rm -r --cached --ignore-unmatch chats projects uploads chroma .env __pycache__" --prune-empty --tag-name-filter cat -- --all
git for-each-ref --format="%(refname)" refs/original | xargs -n 1 git update-ref -d
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

On Windows PowerShell:

```powershell
git rm -r --cached --ignore-unmatch chats projects uploads chroma .env __pycache__
git commit -m "Remove private runtime data"
git filter-branch --force --index-filter "git rm -r --cached --ignore-unmatch chats projects uploads chroma .env __pycache__" --prune-empty --tag-name-filter cat -- --all
git for-each-ref --format="%(refname)" refs/original | ForEach-Object { git update-ref -d $_ }
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

If private files were already pushed, rotate affected secrets immediately and coordinate history cleanup with anyone who cloned or forked the repository.

## Maintainer Checklist Before Release

- Confirm `.env` contains no committed secrets.
- Confirm `.gitignore` covers runtime data.
- Confirm `git ls-files` does not list private folders.
- Confirm Git history does not contain private runtime files.
- Rotate any key that may have been exposed.
- Review README screenshots or examples for private document names, chat text, and API keys.
- Run syntax checks and basic app startup tests.
- Review dependencies for known vulnerabilities.

---

# Chinh Sach Bao Mat

Cam on ban da giup du an va nguoi dung an toan hon. Day la ung dung RAG local-first, nhung van co the xu ly tai lieu nhay cam, lich su chat, API key, vector database va phan hoi tu model. Hay xem cac van de bao mat va rieng tu la nghiem tuc.

## Phien Ban Duoc Ho Tro

Du an dang o giai doan open-source som. Cac ban va bao mat duoc ho tro cho branch mac dinh.

| Phien ban | Ho tro |
| --- | --- |
| `main` / `master` | Co |
| Commit cu, fork, hoac ban sua local | Tuy kha nang |

## Bao Cao Lo Hong

Vui long khong mo public issue neu nghi ngo co lo hong bao mat.

Hay bao cao rieng tu qua:

- GitHub Security Advisory, neu repository da bat tinh nang nay.
- Email rieng cua maintainer neu co trong profile hoac README.
- Kenh lien he rieng tren GitHub neu duoc cung cap.

Neu chua co kenh rieng, hay mo mot issue public toi gian:

```text
I would like to report a security vulnerability. Please provide a private contact channel.
```

Khong dua chi tiet khai thac, API key, tai lieu rieng, chat log, anh chup man hinh co secret, hoac proof-of-concept vao public issue.

## Nen Cung Cap Gi Khi Bao Cao

Khi bao cao rieng tu, hay gui nhung thong tin sau neu co:

- Mo ta ngan gon van de.
- File, endpoint, hoac luong UI bi anh huong.
- Cac buoc tai hien.
- Hanh vi mong doi va hanh vi thuc te.
- Tac dong bao mat: lo du lieu, lo key, truy cap file trai phep, prompt injection, tu choi dich vu, hoac remote code execution.
- Moi truong: he dieu hanh, Python version, trinh duyet, provider model, va app co duoc expose ra network hay khong.
- Log hoac screenshot da che secret.
- Goi y cach sua neu co.

## Phan Hoi Du Kien

Maintainer se co gang:

- Xac nhan da nhan bao cao trong 7 ngay.
- Xac dinh bao cao hop le hay khong trong 14 ngay neu co the.
- Dua ra ban va hoac giai phap giam thieu theo muc do nghiem trong.
- Ghi credit cho nguoi bao cao neu duoc yeu cau va neu disclosure duoc phoi hop co trach nhiem.

Day la du an open-source nho, nen thoi gian co the thay doi. Cac bao cao co trach nhiem luon duoc tran trong.

## Chinh Sach Cong Bo

Vui long cho maintainer thoi gian hop ly de sua truoc khi cong bo cong khai.

Quy trinh khuyen nghi:

1. Bao cao rieng tu.
2. Cho xac nhan da nhan.
3. Phoi hop ve cach tai hien va muc do nghiem trong.
4. Cho thoi gian tao ban va hoac giai phap giam thieu.
5. Chi cong bo chi tiet sau khi co ban va hoac da thong nhat disclosure.

Cong bo som ma khong phoi hop co the lam lo tai lieu, lich su chat, API key hoac file local cua nguoi dung.

## Pham Vi Bao Mat

Nam trong pham vi:

- Lo API key hoac secret.
- Truy cap trai phep tai lieu upload.
- Truy cap trai phep chat session hoac metadata project.
- Path traversal trong upload, download, delete, hoac thao tac file project.
- Xu ly khong an toan voi file `.txt`, `.pdf`, `.docx`.
- Stored hoac reflected XSS tren web UI.
- Prompt injection gay lo private context.
- Vo tinh commit du lieu runtime rieng tu vao Git.
- Lo hong dependency co anh huong thuc te den app.
- Denial-of-service do file qua lon, chunking, token usage, hoac request volume khong gioi han.

Ngoai pham vi neu khong tao tac dong bao mat thuc te:

- Loi giao dien thuan tuy.
- Model hallucination khong lam lo du lieu hoac bypass kiem soat.
- Loi can chiem quyen may local truoc khi tan cong app.
- Lo hong cua provider model ben thu ba, tru khi app xu ly sai response tu provider.
- Tan cong vao dev server duoc co tinh expose neu khong co diem yeu rieng cua app.

## Du Lieu Nhay Cam

Du an co the tao hoac dung cac du lieu local nhay cam:

- `.env` chua API key.
- `uploads/` chua tai lieu nguoi dung.
- `chroma/` chua vector database va chunk trich tu tai lieu.
- `chats/` chua lich su chat.
- `projects/` chua metadata project.
- Cache trinh duyet hoac log local khi phat trien.

Cac path nay khong duoc commit vao Git va da co trong `.gitignore`.

Truoc khi publish, chay:

```powershell
git status --short --ignored
git ls-files chats projects uploads chroma .env __pycache__
git rev-list --objects --all | Select-String -Pattern 'chats/|projects/|uploads/|chroma/|\.env$|__pycache__'
```

Lenh `git ls-files` va `git rev-list` khong nen hien du lieu runtime rieng tu.

## API Key Va Bien Moi Truong

Khong bao gio commit API key that.

Chi dung placeholder trong `.env.example`:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

Khuyen nghi:

- Dung key dev rieng voi key production.
- Rotate key ngay neu key bi commit, chia se, log, hoac lo trong screenshot.
- Gioi han key theo ngan sach, organization, model, origin neu provider ho tro.
- Tranh log request header, API key, hoac raw payload tu provider.
- Khong paste private key vao prompt, issue, screenshot, hoac bug report.

## Chay App An Toan

Mac dinh nen chay tren localhost:

```bash
uvicorn app:app --reload
```

Khong nen expose truc tiep dev server ra internet.

Neu deploy hoac chia se trong network:

- Dat sau lop authentication.
- Dung HTTPS.
- Gioi han kich thuoc upload o reverse proxy hoac application layer.
- Gioi han loai file duoc upload.
- Luu runtime data ben ngoai Git checkout.
- Backup va ma hoa du lieu nhay cam khi can.
- Tach storage theo user neu nhieu nguoi cung dung mot instance.
- Review CORS, cookies, reverse proxy headers va host binding.

## Tai Lieu Upload

File upload co the chua thong tin bi mat, co ban quyen, ca nhan, hoac duoc quan ly boi quy dinh.

Khuyen nghi:

- Chi upload tai lieu ban co quyen xu ly.
- Khong chia se `uploads/` hoac `chroma/` neu chua sanitize.
- Xoa du lieu runtime truoc khi publish demo hoac screenshot.
- Can nhac malware scanning neu nhan file tu nguoi khong tin cay.
- Can nhac gioi han kich thuoc file de tranh can tai nguyen.

## Rieng Tu Cua Vector Database

Thu muc ChromaDB co the chua text chunk hoac embedding sinh tu tai lieu upload. Ngay ca khi xoa raw file, vector database van co the tiet lo thong tin ve tai lieu.

De xoa het noi dung da index local, xoa ca:

```bash
uploads/
chroma/
```

Neu muon xoa ca project va chat history, xoa them:

```bash
chats/
projects/
```

## Prompt Injection Va Output Tu Model

Ung dung RAG de bi prompt injection trong tai lieu upload. Tai lieu doc hai co the yeu cau model bo qua quy tac, tiet lo hidden context, hoac tao output khong mong muon.

Nen ap dung:

- Xem text trong tai lieu upload la input khong tin cay.
- Tach system prompt khoi retrieved document context.
- Khong de model thay API key, filesystem path, environment variables, hoac server internals.
- Khong trao tool co quyen sua file, goi private endpoint, hoac chay command cho model neu chua co kiem soat manh.
- Hien sources de nguoi dung kiem tra chunk nao anh huong cau tra loi.

Khong nen xem response cua model la quyet dinh bao mat co tham quyen.

## Bao Mat Frontend

Frontend render output tu model va text tu tai lieu. De giam XSS:

- Escape text do user kiem soat truoc khi dua vao HTML.
- Sanitize markdown output truoc khi render neu cho phep noi dung khong tin cay.
- Tranh chen raw model output bang `innerHTML` neu chua sanitize.
- Pin version hoac dung integrity cho thu vien browser ben thu ba khi co the.

Neu app tro thanh multi-user hoac internet-facing, can review ky markdown sanitization va Content Security Policy.

## Bao Mat Dependency

Cai dependency tu `requirements.txt` trong virtual environment.

Lenh kiem tra khuyen nghi:

```bash
python -m pip install --upgrade pip
python -m pip list --outdated
python -m pip audit
```

Neu chua co `pip-audit`:

```bash
python -m pip install pip-audit
python -m pip audit
```

Hay review update dependency truoc khi merge vi SDK model, vector database, PDF parser va document parser co the doi hanh vi.

## Don Git History

Neu lo commit file rieng tu nhung chua push, xem cac lenh trong phan English o tren hoac dung PowerShell:

```powershell
git rm -r --cached --ignore-unmatch chats projects uploads chroma .env __pycache__
git commit -m "Remove private runtime data"
git filter-branch --force --index-filter "git rm -r --cached --ignore-unmatch chats projects uploads chroma .env __pycache__" --prune-empty --tag-name-filter cat -- --all
git for-each-ref --format="%(refname)" refs/original | ForEach-Object { git update-ref -d $_ }
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

Neu file rieng tu da duoc push, hay rotate secret lien quan ngay lap tuc va phoi hop don history voi bat ky ai da clone hoac fork repository.

## Checklist Cho Maintainer Truoc Khi Release

- Xac nhan `.env` khong bi commit.
- Xac nhan `.gitignore` da cover runtime data.
- Xac nhan `git ls-files` khong liet ke thu muc rieng tu.
- Xac nhan Git history khong chua file runtime rieng tu.
- Rotate key neu co kha nang da lo.
- Review screenshot hoac vi du trong README de tranh lo ten tai lieu, noi dung chat, API key.
- Chay syntax check va test khoi dong co ban.
- Review dependency co lo hong da biet.
