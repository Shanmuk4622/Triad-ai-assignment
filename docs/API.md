# REST API

The application runs at `http://localhost:7860` by default. For a protected endpoint, send `Authorization: Bearer <token>` using the `token` returned by login. JSON requests use `Content-Type: application/json`. Errors use `{"error": "message"}`.

## Endpoints

| Method and path | Input | Success response |
| --- | --- | --- |
| `GET /api/health` | Public | `200`, `status` |
| `POST /api/auth/register` | `username`, `password`, `division`, optional `email`. An email can serve as the username. | `201`, `user` |
| `POST /api/auth/login` | `username` or `email`, and `password` | `200`, `token`, `user` |
| `GET /api/auth/me` | Bearer token | `200`, `user` |
| `POST /api/documents/upload` | Multipart `file`, optional `title`, optional `metadata` JSON string | `201`, `doc_id`, `document` |
| `GET /api/documents` | Optional `Division` and custom field filters | `200`, `documents` |
| `GET /api/documents/catalog` | Bearer token | `200`, `documents` with minimal cross-division information |
| `GET /api/documents/<doc_id>` | Document ID | `200` with `document`. Restricted documents return catalog information. |
| `GET /api/documents/<doc_id>/download` | Document ID | `200` with the original file as an attachment, or `403` when approval is required |
| `POST /api/access/request` | `doc_id` | `201` with `request_id`, `status`, and `request`. A repeat returns `200` with the existing request. |
| `GET /api/access/requests` | Bearer token | `200`, incoming `requests` for the caller’s division |
| `POST /api/access/approve` | `request_id` | `200`, `status`, `request` |
| `POST /api/access/reject` | `request_id` | `200`, `status`, `request` |
| `GET /api/search` | `q` and optional field filters | `200`, `results` |
| `GET /api/fields` | Bearer token | `200`, `fields` |
| `POST /api/fields` | Admin token, `label`, optional `options` array | `201`, `field` |
| `PATCH /api/fields/<field_id>` | Admin token, `label`, optional `options` array | `200`, `field` |

## Examples

Register and sign in with PowerShell:

```powershell
$base = 'http://localhost:7860/api'
$account = @{ username='alice'; password='demo-password'; division='Division A' }
Invoke-RestMethod "$base/auth/register" -Method Post -ContentType 'application/json' -Body ($account | ConvertTo-Json)
$signIn = @{ username=$account.username; password=$account.password }
$token = (Invoke-RestMethod "$base/auth/login" -Method Post -ContentType 'application/json' -Body ($signIn | ConvertTo-Json)).token
$headers = @{ Authorization = "Bearer $token" }
```

Upload with PowerShell 7:

```powershell
$form = @{
    file = Get-Item .\test_sample.pdf
    title = 'Quarterly report'
    metadata = @{ 'Report Type' = 'Financial'; 'Quarter' = 'Q3' } | ConvertTo-Json -Compress
}
Invoke-RestMethod "$base/documents/upload" -Method Post -Headers $headers -Form $form
Invoke-RestMethod "$base/documents?Division=Division%20A&Report%20Type=Financial" -Headers $headers
Invoke-RestMethod "$base/search?q=quarterly" -Headers $headers
```

Metadata can hold up to 30 fields. Each value can be a string, number, boolean, null, or a list of these values. `Division` is fixed to the user’s division when supplied. Filters use case-insensitive exact matching against a metadata field’s values. Search uses case-insensitive substring matching across titles, filenames, divisions, metadata, and extracted text. The `q` parameter can be empty when only filters are supplied.
