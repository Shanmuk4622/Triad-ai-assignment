import json
import math
import re
from datetime import datetime, timezone
from io import BytesIO

from bson import ObjectId
from flask import Blueprint, abort, current_app, g, jsonify, request, send_file
from gridfs import GridFSBucket, NoFile
from pymongo.errors import PyMongoError

from .auth import require_user
from .common import clean_text, database, object_id, timestamp
from .fields import field_maps, metadata_key
from .ocr import InvalidDocument, OcrError, extract_text

documents_api = Blueprint("documents", __name__)
LIST_FIELDS = {"ocr_text": 0, "search_metadata": 0, "file_id": 0}


def load_document(doc_id, projection=None):
    document = database().documents.find_one({"_id": object_id(doc_id, "document ID")}, projection)
    if not document:
        abort(404, "Document not found.")
    return document


def access_status(document):
    if document["division_key"] == g.user["division_key"]:
        return "own_division"
    item = database().access_requests.find_one({"doc_id": document["_id"], "requester_id": g.user["_id"]})
    return item["status"] if item else "restricted"


def visible_documents():
    approved = database().access_requests.find(
        {"requester_id": g.user["_id"], "status": "approved"}, {"doc_id": 1}
    )
    return {"$or": [{"division_key": g.user["division_key"]}, {"_id": {"$in": [item["doc_id"] for item in approved]}}]}


def public_document(document, labels, status):
    doc_id = str(document["_id"])
    result = {
        "id": doc_id,
        "doc_id": doc_id,
        "title": document["title"],
        "division": document["division"],
        "access_status": status,
        "can_download": status in {"own_division", "approved"},
    }
    if result["can_download"]:
        result.update(
            filename=document["filename"],
            content_type=document["content_type"],
            created_at=timestamp(document["created_at"]),
            metadata={labels.get(key, entry["label"]): entry["value"] for key, entry in document["metadata"].items()},
        )
    return result


def normalise_metadata(raw, aliases):
    try:
        metadata = json.loads(raw)
    except (ValueError, RecursionError):
        abort(400, "Metadata must be valid JSON.")
    if not isinstance(metadata, dict) or len(metadata) > 30:
        abort(400, "Metadata must be a JSON object with at most 30 fields.")
    result = {}
    search_values = []
    for label, value in metadata.items():
        label = clean_text(label, "Metadata field name", 60)
        if label.casefold() == "division":
            check_division(value)
            value = g.user["division"]
        values = value if isinstance(value, list) else [value]
        if len(values) > 30:
            abort(400, "A metadata field can contain up to 30 values.")
        for item in values:
            if type(item) is str:
                if len(item) > 500 or not (item.isprintable() or item == ""):
                    abort(400, "Metadata strings must use up to 500 printable characters.")
            elif type(item) is int:
                if not -(2**63) <= item < 2**63:
                    abort(400, "Metadata integers must fit in 64 bits.")
            elif type(item) is float:
                if not math.isfinite(item):
                    abort(400, "Metadata numbers must be finite.")
            elif type(item) is not bool and item is not None:
                abort(400, "Use text, numbers, booleans, null, or lists of these in metadata.")
        terms = [str(item).strip() for item in values if item is not None]
        key = metadata_key(label, aliases)
        if key in result:
            abort(400, f"Metadata field '{label}' was supplied twice.")
        result[key] = {"label": label, "value": value, "terms": terms}
        search_values.extend([label, *terms])
    return result, search_values


def check_division(value):
    choice = clean_text(value, "Division", 80)
    if choice.casefold() != g.user["division_key"]:
        abort(403, "You can upload only to your own division.")


@documents_api.post("/documents/upload")
@require_user
def upload_document():
    file = request.files.get("file")
    if file is None or not file.filename:
        abort(400, "Choose a PDF or image to upload.")
    filename = clean_text(file.filename.replace("\\", "/").rsplit("/", 1)[-1], "File name", 230)
    title = clean_text(request.form.get("title") or filename, "Title", 230)
    for label, value in request.form.items():
        if label.casefold() == "division":
            check_division(value)
    labels, aliases = field_maps()
    metadata, search_metadata = normalise_metadata(request.form.get("metadata", "{}"), aliases)
    data = file.read()
    if not data:
        abort(400, "The uploaded file is empty.")
    try:
        content_type, ocr_text = extract_text(data)
    except InvalidDocument as error:
        abort(400, str(error))
    except OcrError as error:
        abort(503, str(error))

    db = database()
    bucket = GridFSBucket(db)
    doc_id, file_id = ObjectId(), ObjectId()
    document = {
        "_id": doc_id,
        "file_id": file_id,
        "filename": filename,
        "title": title,
        "division": g.user["division"],
        "division_key": g.user["division_key"],
        "uploader_id": g.user["_id"],
        "metadata": metadata,
        "search_metadata": search_metadata,
        "ocr_text": ocr_text,
        "content_type": content_type,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        bucket.upload_from_stream_with_id(file_id, filename, data, metadata={"content_type": content_type})
        db.documents.insert_one(document)
    except PyMongoError:
        # A network failure can occur after MongoDB accepted the insert.
        try:
            if db.documents.find_one({"_id": doc_id}, {"_id": 1}) is None:
                bucket.delete(file_id)
        except (PyMongoError, NoFile):
            current_app.logger.warning("Upload cleanup could not confirm file %s", file_id)
        raise
    result = public_document(document, labels, "own_division")
    return jsonify(message="Document uploaded.", doc_id=result["id"], id=result["id"], document=result), 201


def filtered_documents(search=False):
    labels, aliases = field_maps()
    conditions = [visible_documents()]
    for label, value in request.args.items():
        if label.casefold() == "q" or not value.strip():
            continue
        label = clean_text(label, "Filter name", 60)
        value = clean_text(value, "Filter value", 500)
        if label.casefold() == "division":
            conditions.append({"division_key": value.casefold()})
        else:
            key = metadata_key(label, aliases)
            conditions.append({f"metadata.{key}.terms": re.compile(f"^{re.escape(value)}$", re.IGNORECASE)})
    query = request.args.get("q", "").strip()
    if search and query:
        query = clean_text(query, "Search query", 150)
        match = re.compile(re.escape(query), re.IGNORECASE)
        search_fields = ["title", "filename", "division", "search_metadata", "ocr_text"]
        choices = [{field: match} for field in search_fields]
        choices.extend({f"metadata.{key}": {"$exists": True}} for key, label in labels.items() if match.search(label))
        conditions.append({"$or": choices})
    return [
        public_document(doc, labels, "own_division" if doc["division_key"] == g.user["division_key"] else "approved")
        for doc in database().documents.find({"$and": conditions}, LIST_FIELDS).sort("created_at", -1)
    ]


@documents_api.get("/documents")
@require_user
def list_documents():
    return jsonify(documents=filtered_documents())


@documents_api.get("/documents/catalog")
@require_user
def catalog():
    db = database()
    statuses = {item["doc_id"]: item["status"] for item in db.access_requests.find({"requester_id": g.user["_id"]})}
    documents = db.documents.find(
        {"division_key": {"$ne": g.user["division_key"]}}, {"title": 1, "division": 1}
    ).sort("created_at", -1)
    return jsonify(documents=[
        {"id": str(doc["_id"]), "title": doc["title"], "division": doc["division"],
         "access_status": statuses.get(doc["_id"], "restricted")}
        for doc in documents
    ])


@documents_api.get("/documents/<doc_id>")
@require_user
def document_details(doc_id):
    document = load_document(doc_id, LIST_FIELDS)
    labels, _ = field_maps()
    return jsonify(document=public_document(document, labels, access_status(document)))


@documents_api.get("/documents/<doc_id>/download")
@require_user
def download_document(doc_id):
    document = load_document(doc_id, {"division_key": 1, "file_id": 1, "filename": 1, "content_type": 1})
    if access_status(document) not in {"own_division", "approved"}:
        abort(403, "This document requires approval from its owning division.")
    try:
        with GridFSBucket(database()).open_download_stream(document["file_id"]) as file:
            data = file.read()
    except NoFile:
        abort(404, "The file is unavailable.")
    return send_file(BytesIO(data), mimetype=document["content_type"], as_attachment=True,
                     download_name=document["filename"], max_age=0)


@documents_api.get("/search")
@require_user
def search_documents():
    return jsonify(results=filtered_documents(search=True))
