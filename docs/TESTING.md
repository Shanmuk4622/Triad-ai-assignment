# Testing

## Integration suite

Start the Docker services and run:

```powershell
docker compose up --build --wait
docker compose exec -T app python -m unittest discover -s tests -v 2>&1 | Tee-Object test_report.txt
```

Each test run creates and cleans up a separately named MongoDB database. The suite uses actual GridFS and Tesseract. It creates a scanned PDF and PNG with a known phrase, then confirms the phrase appears in search results. It also checks authentication, same-division access, cross-division approval and rejection, download bytes, forged division values, field renames, filters, and invalid inputs.

The GitHub Actions workflow builds the same Compose stack, runs both test suites, and saves their reports as an artifact.

## Triad AI starter test

The [official starter script](https://github.com/rithish-sripaul-triad-ai/triad-ai-interns-dms/blob/9ee49598fbc855841a84462e1e729ec0c71761aa/test_api.py) checks one upload and expects HTTP 200 or 201. It defaults to port 5000, sends the upload without a token, and creates a placeholder file with no PDF pages if `test_sample.pdf` is absent.

Use the runner below with the app running. It creates a Division A test account, logs in, and gives the starter script an authenticated connection and a valid scanned PDF. The starter's upload assertion and reporting code run as supplied. The application's authenticated upload rules still apply.

```powershell
python -m pip install requests Pillow
python .\tests\run_triad_starter.py "$env:USERPROFILE\Downloads\test_api.py"
```

The runner saves `triad_starter_report.txt` in the current directory. Use `--base-url http://localhost:5000/api` when the app runs on port 5000. The separate integration suite checks OCR search, role and division access, and file contents.

## Browser walkthrough

| Check | Expected result |
| --- | --- |
| Upload an image containing a unique word, then use Advanced search | The uploaded file appears when the OCR recognizes the word. |
| Browse Other divisions from a second division | Opening a row shows the title and division and offers **Request access**. |
| Request access, then revisit the document before approval | The page displays **Pending**. A direct download API call returns `403`. |
| Approve from an account in the owning division | The requester can reopen the document and download the original file. |
| Reject a request for another file | The requester sees **Rejected** and download remains blocked. |
| Create and rename a metadata field as an admin | Upload and filter forms show the updated field. Values on existing documents remain visible. |
