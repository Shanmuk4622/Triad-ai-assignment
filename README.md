---
title: TRIAD AI Document Management
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# TRIAD AI Document Management System

Upload documents into your division, tag them with custom fields, and find them by title, metadata, or text inside a scan. A member of the owning division can approve or reject another user’s request to download a document.

## Run with Docker

Start Docker Desktop in Linux container mode. From this repository, run:

```powershell
docker compose up --build --wait
```

Open [http://localhost:7860](http://localhost:7860). Compose starts Flask and MongoDB and installs Tesseract inside the app image. The named MongoDB volume keeps users, metadata, and files across normal stops. If port `7860` is in use, set `APP_PORT=7861` in `.env` and open that port.

## Try the assignment workflow

1. Create one account in **Division A** and another in **Division B**. Use separate browser windows or sign out between accounts.
2. Sign in to Division A. Upload a PDF or image with a **Report Type** value. Search for a word inside the file on **Advanced search**.
3. Sign in to Division B. Open **Documents → Other divisions**, select the file, and choose **Request access**.
4. In Division A, open **Access requests** and approve the request. Return to the Division B account and reopen the document to download it.
5. Promote a registered account to admin to try **Settings → Add field** or edit a field. Replace `alice` with the registered username.

```powershell
docker compose exec app flask --app dms make-admin alice
```

The dashboard and advanced search show documents from your division and documents individually approved for you. The other-division catalog shows the title, division, and your request status so you can ask for access.

## How it fits together

**Browser → Flask REST API → MongoDB and GridFS.** Flask checks division membership and approvals for each request. MongoDB stores accounts, metadata, extracted text, and approvals. GridFS stores the original file. PDFium reads PDF text and renders scanned pages. Tesseract recognizes text in images and rendered scans. Settings use a stable field ID, so renaming a field keeps values already saved on documents.

| Guide | What it covers |
| --- | --- |
| [Architecture and tool choices](docs/ARCHITECTURE.md) | Request flows, database model, authorization, and why each tool was chosen |
| [REST API](docs/API.md) | Endpoints, payloads, and examples |
| [Testing](docs/TESTING.md) | Integration suite, assignment starter test, and manual checks |
| [Setup and deployment](docs/DEPLOYMENT.md) | Windows Python or Conda, GitHub, and Hugging Face Spaces |

Stop the services with `docker compose down`.
