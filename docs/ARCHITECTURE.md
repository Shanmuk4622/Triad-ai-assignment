# Architecture and tool choices

## What happens during an upload

1. The browser sends the original file, an optional title, and the metadata as `multipart/form-data`.
2. Flask verifies the bearer token, loads the account, and assigns the document to the account’s division. An explicit Division value must match that division.
3. Flask reads searchable text. For a text PDF, PDFium can read the text already stored in the file. A scanned PDF page is rendered to an image. Tesseract recognizes text in the rendered page or an uploaded image. PDF pages containing raster images also run through Tesseract so mixed pages are searchable.
4. GridFS stores the original bytes. MongoDB stores metadata, extracted text, and the GridFS file ID. If writing the document record fails, Flask checks whether MongoDB saved it before attempting to clean up the file.
5. Search and download apply the same division or approval rule. A successful search returns the matching document summary. The download endpoint reads the original bytes back from GridFS.

## Data in MongoDB

| Collection | Main fields and purpose |
| --- | --- |
| `users` | Username, optional email, password hash, division and role. A unique identity index prevents registration under another account’s username or email. |
| `documents` | Title, owning division, file ID, original filename, metadata and text. The owning division comes from the signed-in account. |
| `fields` | Stable key, display label, prior labels, and suggested values. Old labels remain queryable after a rename. |
| `access_requests` | One record per requester and document. Includes the owning division, decision, and who made it. |
| `fs.files`, `fs.chunks` | GridFS file information and chunks of the original binary payload. |

Field definitions power the upload form and filter controls. The API accepts additional field names through the metadata JSON as well. Defining an existing field name in Settings makes it available in the UI. Each document stores its field values under stable, MongoDB-safe keys. Renaming a field changes its displayed label. Suggested values are examples users can select or type alongside their own values.

## How authorization works

| Action | Division member | Admin |
| --- | --- | --- |
| Upload | Own division | Own division |
| View full details, search, download | Own division and individually approved documents | Same rule |
| Discover a document and request access | Other-division catalog | Same rule |
| Approve or reject | Requests for their own division | Same rule |
| Add and edit field definitions | Read definitions | Read and edit definitions |

Signup assigns the chosen division for this assignment’s demo. Deploy a private review Space if you upload any material beyond sample data. For an organization, division membership would be assigned by a trusted administrator or identity provider.

Passwords are hashed with Werkzeug. Flask signs an eight-hour bearer token using `SECRET_KEY`. Protected API requests load the current account from MongoDB, so role and division checks use the current records. The request state changes from `pending` to either `approved` or `rejected` in one conditional update. The unique request index prevents duplicate requests, and approval applies to the requesting person for that specific file.

## Why these tools

| Tool or choice | Why it fits the assignment |
| --- | --- |
| Flask | Required by the brief. Separate route modules keep the code readable for a small REST API. A larger framework would introduce more conventions and setup for the same endpoints. |
| MongoDB, PyMongo, GridFS | Required by the brief. MongoDB documents can hold different metadata fields. PyMongo gives the app a direct interface to GridFS and indexes without an object mapping layer. GridFS keeps file bytes and metadata references in the same database service. [GridFS documentation](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/gridfs/) |
| Tesseract | Runs English OCR locally on CPU, inside the container. This keeps uploaded documents inside the app’s environment and avoids cloud OCR credentials or per-call fees. [Tesseract documentation](https://tesseract-ocr.github.io/tessdoc/) |
| PDFium and Pillow | PDFium both reads embedded PDF text and renders pages for OCR. Pillow opens common image formats and prepares them for Tesseract. The same OCR function handles images and rendered PDF pages. [PDFium API](https://pypdfium2.readthedocs.io/en/stable/python_api.html) |
| MongoDB queries | Escaped, case-insensitive substring matching covers titles, arbitrary metadata, and extracted text under the same authorization filter. A separate search service would require another container and an indexing pipeline. This approach is sized for an assignment-sized collection. |
| HTML, CSS and JavaScript | Flask serves one HTML page and static assets. Browser `fetch` calls the REST API for each view. The frontend has no Node build step or separate server. |
| Docker and Gunicorn | Docker installs Python, MongoDB, and English Tesseract data in repeatable environments. Compose runs app and database services locally. Gunicorn serves the Flask app in Docker. |

The app caps uploads at a 16 MiB HTTP request, 20 PDF pages or image frames, and 30 million pixels per image frame. OCR runs during upload, so a scan takes longer than a text-only PDF. The app saves up to 250,000 extracted characters per document for search. These limits keep individual OCR requests manageable for a small deployment.
