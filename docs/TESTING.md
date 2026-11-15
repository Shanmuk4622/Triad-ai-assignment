# Testing

## Integration suite

Start the Docker services and run:

```powershell
docker compose up --build --wait
docker compose exec -T app python -m unittest discover -s tests -v 2>&1 | Tee-Object test_report.txt
```

Each test run creates and cleans up a separately named MongoDB database. The suite uses actual GridFS and Tesseract. It creates a scanned PDF and PNG with a known phrase, then confirms the phrase appears in search results. It also checks authentication, same-division access, cross-division approval and rejection, download bytes, forged division values, field renames, filters, and invalid inputs.

The GitHub Actions workflow builds and starts the same Compose stack, runs the suite, and saves `test_report.txt` as an artifact.

## Triad AI starter test

The brief identifies [Triad AI’s starter repository](https://github.com/rithish-sripaul-triad-ai/triad-ai-interns-dms), which supplies its own test script and `test_sample.pdf`. Sign in with an account that has repository access, follow the starter README, and point the script to the running app at `http://localhost:7860` or to the port configured for your test. Use its generated `test_report.txt` when reviewing compatibility with the evaluator.

## Browser walkthrough

| Check | Expected result |
| --- | --- |
| Upload an image containing a unique word, then use Advanced search | The uploaded file appears when the OCR recognizes the word. |
| Browse Other divisions from a second division | Opening a row shows the title and division and offers **Request access**. |
| Request access, then revisit the document before approval | The page displays **Pending**. A direct download API call returns `403`. |
| Approve from an account in the owning division | The requester can reopen the document and download the original file. |
| Reject a request for another file | The requester sees **Rejected** and download remains blocked. |
| Create and rename a metadata field as an admin | Upload and filter forms show the updated field. Values on existing documents remain visible. |
