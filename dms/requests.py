from datetime import datetime, timezone

from flask import Blueprint, abort, g, jsonify
from pymongo.errors import DuplicateKeyError

from .auth import require_user
from .common import database, json_body, object_id, timestamp
from .documents import load_document

access_api = Blueprint("access", __name__)


def request_response(item):
    return {
        "id": str(item["_id"]),
        "request_id": str(item["_id"]),
        "doc_id": str(item["doc_id"]),
        "title": item["title"],
        "requester": item["requester"],
        "requester_division": item["requester_division"],
        "status": item["status"],
        "created_at": timestamp(item["created_at"]),
    }


@access_api.post("/access/request")
@require_user
def request_access():
    data = json_body()
    document = load_document(data.get("doc_id"), {"title": 1, "division_key": 1})
    if document["division_key"] == g.user["division_key"]:
        abort(400, "You already have division access to this document.")
    item = {
        "doc_id": document["_id"],
        "title": document["title"],
        "division_key": document["division_key"],
        "requester_id": g.user["_id"],
        "requester": g.user["username"],
        "requester_division": g.user["division"],
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    collection = database().access_requests
    status = 201
    try:
        collection.insert_one(item)
    except DuplicateKeyError:
        item = collection.find_one({"doc_id": document["_id"], "requester_id": g.user["_id"]})
        status = 200
    result = request_response(item)
    return jsonify(request_id=result["id"], status=result["status"], request=result), status


@access_api.get("/access/requests")
@require_user
def inbox():
    items = database().access_requests.find({"division_key": g.user["division_key"]}).sort("created_at", -1)
    return jsonify(requests=[request_response(item) for item in items])


def decide_request(status):
    request_id = object_id(json_body().get("request_id"), "request ID")
    collection = database().access_requests
    item = collection.find_one({"_id": request_id})
    if not item:
        abort(404, "Request not found.")
    if item["division_key"] != g.user["division_key"]:
        abort(403, "Only the owning division can decide this request.")
    result = collection.update_one(
        {"_id": request_id, "status": "pending"},
        {"$set": {"status": status, "decided_by": g.user["_id"], "decided_at": datetime.now(timezone.utc)}},
    )
    if not result.modified_count:
        latest = collection.find_one({"_id": request_id})
        if latest["status"] != status:
            abort(409, "This request already has a decision.")
    item["status"] = status
    return jsonify(status=status, request=request_response(item))


@access_api.post("/access/approve")
@require_user
def approve():
    return decide_request("approved")


@access_api.post("/access/reject")
@require_user
def reject():
    return decide_request("rejected")
